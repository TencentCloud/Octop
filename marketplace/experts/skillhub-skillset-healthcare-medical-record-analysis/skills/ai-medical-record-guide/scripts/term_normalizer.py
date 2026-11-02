#!/usr/bin/env python3
"""
术语规范化脚本 - term_normalizer.py
Source: clinical-note-writer-v2.md (Scripts Section)

将患者口语化的描述转换为标准医学术语，
同时标记需要人工确认的歧义项和缺失数值。
"""

import json
import re
import sys
import logging
from typing import Dict, List, Tuple, Any

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

# ============================================================
# 内置术语映射表（可被外部 JSON 覆盖）
# ============================================================

DEFAULT_TERMINOLOGY_MAP = {
    # --- 症状类 ---
    "肚子疼": "腹痛",
    "胃疼": "上腹疼痛",
    "胃痛": "上腹疼痛",
    "发烧": "发热",
    "发热": "发热",
    "怕冷": "畏寒",
    "发冷": "畏寒",
    "喘不上气": "呼吸困难",
    "气不够用": "呼吸困难",
    "胸闷气短": "胸闷伴呼吸困难",
    "身上没劲儿": "乏力",
    "没力气": "乏力",
    "累": "乏力",
    "心慌": "心悸",
    "心跳快": "心率增快",
    "头晕": "头晕",
    "头痛": "头痛",
    "吃不下": "食欲减退",
    "没胃口": "食欲减退",
    "不想吃饭": "食欲减退",
    "恶心": "恶心",
    "呕吐": "呕吐",
    "拉肚子": "腹泻",
    "便秘": "便秘",
    "拉不出": "便秘",
    "腿肿了": "双下肢水肿",
    "脚肿": "双下肢水肿",
    "手肿": "上肢水肿",
    "脸上肿": "面部水肿",
    "身上黄了": "皮肤黏膜黄疸",
    "眼睛黄": "巩膜黄疸",
    "尿色深": "尿色加深",
    "小便颜色深": "尿色加深",
    "出皮疹": "皮疹",
    "痒": "瘙痒",
    "身上痒": "全身瘙痒",
    "盗汗": "盗汗",
    "消瘦": "体重减轻",
    "瘦了很多": "体重减轻",
    "咳嗽": "咳嗽",
    "咳痰": "咳痰",
    "咳血": "咯血",
    "大便带血": "便血",

    # --- 体征类 ---
    "血压高": "血压升高",
    "血压低": "血压降低",
    "血糖高": "血糖升高",
    "血糖低": "血糖降低",
    "脉搏快": "心率增快",
    "脉搏慢": "心动过缓",
    "身上热": "体温升高",
    "脖子粗": "甲状腺肿大",
    "肝大": "肝脏肿大",
    "脾大了": "脾脏肿大",
    "摸到包块": "触及肿块",

    # --- 时间类 ---
    "从小就有": "自幼",
    "反复": "反复发作",
    "一直这样": "持续性",
    "有时候": "间歇性",
    "偶尔": "偶发",
    "越来越": "进行性加重",
    "断断续续": "间断性",
}

# 需要追问数值的高歧义词（无法自动转换）
AMBIGUOUS_TERMS = [
    "不舒服", "不得劲", "身体不好", "难受",
]

# 必须获取具体数值的表达式
VALUE_REQUIRED_PATTERNS = [
    ("血压高|血压低|血压多少", "血压值(SBP/DBP mmHg)"),
    ("发烧|发热|发烧多少度", "体温值(°C)"),
    ("血糖高|血糖低|血糖多少", "血糖值(mmol/L)"),
    ("疼.*?几分|有多疼|NRS", "疼痛评分(NRS 0-10)"),
    ("掉了.*?斤|瘦了.*?斤|体重变化", "体重变化量(kg)和时间"),
    ("好几天|很久|多久", "具体天数或日期"),
]


class TermNormalizer:
    """
    术语规范化引擎
    
    用法:
        normalizer = TermNormalizer()
        result = normalizer.normalize("患者说肚子疼3天了，还有点发烧")
        # result.normalized_text → "患者诉腹痛3天，伴发热"
        # result.ambiguous_terms → ["发热"]  (需确认数值)
        # result.missing_values → [("发热", "体温值(°C)")]
    """

    def __init__(self, custom_map_path: str = None):
        """
        初始化术语规范化引擎。
        
        Args:
            custom_map_path: 可选的外部映射表 JSON 文件路径，
                            格式: {"口语": "标准术语", ...}
        """
        # 加载映射表
        self.term_map = dict(DEFAULT_TERMINOLOGY_MAP)
        if custom_map_path:
            self._load_custom_map(custom_map_path)
        
        # 编译正则表达式（按词长降序排列，优先匹配长词）
        self._sorted_keys = sorted(
            self.term_map.keys(), key=len, reverse=True
        )
        self._pattern = re.compile(
            '|'.join(re.escape(k) for k in self._sorted_keys)
        )

    def _load_custom_map(self, path: str):
        """加载外部自定义映射表"""
        try:
            with open(path, 'r', encoding='utf-8') as f:
                custom_map = json.load(f)
            if isinstance(custom_map, dict):
                self.term_map.update(custom_map)
                # 重新排序
                self._sorted_keys = sorted(
                    self.term_map.keys(), key=len, reverse=True
                )
                self._pattern = re.compile(
                    '|'.join(re.escape(k) for k in self._sorted_keys)
                )
                logger.info(f"已加载外部术语映射表: {path} ({len(custom_map)} 条)")
            else:
                logger.warning(f"外部映射表格式错误（需dict）: {path}")
        except Exception as e:
            logger.warning(f"加载外部映射表失败: {path} → {e}")

    def normalize(self, raw_text: str) -> 'NormalizationResult':
        """
        对输入文本执行术语规范化。
        
        Args:
            raw_text: 原始文本（可能包含口语表达）
            
        Returns:
            NormalizationResult 对象，包含：
            - normalized_text: 规范化后的文本
            - ambiguous_terms: 检测到的歧义项列表
            - missing_values: 需要追问数值的项列表
            - replacement_log: 替换日志
        """
        result = NormalizationResult(original_text=raw_text)
        
        text = raw_text
        
        # Step 1: 术语替换
        replacements = []
        for key in self._sorted_keys:
            if key in text:
                count = text.count(key)
                text = text.replace(key, self.term_map[key])
                replacements.append({
                    "original": key,
                    "standard": self.term_map[key],
                    "count": count
                })
        
        result.replacement_log = replacements
        
        # Step 2: 歧义检测（高歧义词）
        ambiguous_found = []
        for term in AMBIGUOUS_TERMS:
            if term in raw_text:
                ambiguous_found.append(term)
        result.ambiguous_terms = ambiguous_found
        
        # Step 3: 数值缺失检测
        missing_values = []
        for pattern, value_label in VALUE_REQUIRED_PATTERNS:
            if re.search(pattern, raw_text):
                # 检查是否已经有具体数值
                if not self._has_numerical_value(raw_text, pattern):
                    missing_values.append({
                        "matched_pattern": pattern,
                        "required_value": value_label
                    })
        result.missing_values = missing_values
        
        # 最终结果
        result.normalized_text = text
        
        # 日志
        if replacements:
            logger.info(f"术语替换: {len(replacements)} 处")
        if ambiguous_found:
            logger.warning(f"检测到歧义项: {ambiguous_found}")
        if missing_values:
            logger.warning(f"需要追问数值: {[m['required_value'] for m in missing_values]}")
        
        return result
    
    @staticmethod
    def _has_numerical_value(text: str, pattern: str) -> bool:
        """检查文本中是否已包含与该模式相关的数值"""
        # 简单启发：如果附近有数字+单位，认为已有数值
        numeric_patterns = [
            r'\d+\.?\d*\s*(mmHg|℃|°C|mmol/L|分|公斤|kg|天|周|月|年|次)',
            r'\d+\s*/',
        ]
        context = text[max(0, text.find(pattern) if pattern in text else 0):
                       min(len(text), (text.find(pattern) if pattern in text else 0)+50)]
        for np in numeric_patterns:
            if re.search(np, context):
                return True
        return False


class NormalizationResult:
    """规范化结果数据类"""
    
    def __init__(self, original_text: str = ""):
        self.original_text = original_text
        self.normalized_text = ""
        self.ambiguous_terms: List[str] = []
        self.missing_values: List[Dict[str, str]] = []
        self.replacement_log: List[Dict[str, Any]] = []
    
    @property
    def has_issues(self) -> bool:
        """是否存在需要人工处理的问题"""
        return len(self.ambiguous_terms) > 0 or len(self.missing_values) > 0
    
    def summary(self) -> str:
        """生成人类可读的摘要"""
        lines = [
            f"原始文本: {self.original_text[:100]}...",
            f"规范文本: {self.normalized_text[:100]}...",
            f"",
            f"📝 术语替换: {len(self.replacement_log)} 处",
        ]
        for r in self.replacement_log:
            lines.append(f"   '{r['original']}' → '{r['standard']}' (出现{r['count']}次)")
        
        if self.ambiguous_terms:
            lines.append(f"")
            lines.append(f"⚠️  歧义项（需人工确认）: {len(self.ambiguous_terms)}")
            for t in self.ambiguous_terms:
                lines.append(f"   • '{t}' — 表达过于宽泛，需追问具体症状")
        
        if self.missing_values:
            lines.append(f"")
            lines.append(f"🔢  数值缺失（需追问）: {len(self.missing_values)}")
            for m in self.missing_values:
                lines.append(f"   • 「{m['matched_pattern']}」→ 需要: {m['required_value']}")
        
        return "\n".join(lines)
    
    def to_dict(self) -> Dict[str, Any]:
        """导出为字典（便于JSON序列化）"""
        return {
            "original_text": self.original_text,
            "normalized_text": self.normalized_text,
            "ambiguous_terms": self.ambiguous_terms,
            "missing_values": self.missing_values,
            "replacement_count": len(self.replacement_log),
            "replacements": self.replacement_log,
            "has_issues": self.has_issues,
        }


# ============================================================
# CLI 接口
# ============================================================

def main():
    """命令行入口"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='医学术语规范化：将口语转换为标准术语',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例用法:
  echo "患者说肚子疼3天了，还有点发烧" | python term_normalizer.py
  python term_normalizer.py "血压高，有点头晕"
  python term_normalizer.py "不舒服好几天了" --custom-map my_terminology.json
  python term_normalizer.py "发烧38.5度" --json
        """
    )
    parser.add_argument('input_text', nargs='?', default=None, help='待规范的文本')
    parser.add_argument('--custom-map', '-m', help='自定义术语映射表(JSON文件)')
    parser.add_argument('--json', '-j', action='store_true', help='以JSON格式输出')
    parser.add_argument('--verbose', '-v', action='store_true', help='详细输出')
    
    args = parser.parse_args()
    
    if args.verbose:
        logger.setLevel(logging.DEBUG)
    
    # 获取输入文本
    input_text = args.input_text
    if input_text is None:
        # 从 stdin 读取
        input_text = sys.stdin.read().strip()
    
    if not input_text:
        print("❌ 请提供输入文本", file=sys.stderr)
        sys.exit(1)
    
    # 执行规范化
    normalizer = TermNormalizer(custom_map_path=args.custom_map)
    result = normalizer.normalize(input_text)
    
    # 输出
    if args.json:
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    else:
        print(result.summary())


if __name__ == '__main__':
    main()
