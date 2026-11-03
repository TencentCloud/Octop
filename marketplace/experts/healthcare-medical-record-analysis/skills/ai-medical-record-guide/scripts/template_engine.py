#!/usr/bin/env python3
"""
模板引擎（预留接口）- template_engine.py
Source: clinical-note-writer-v2.md (Scripts Section)

功能：
- 加载 Markdown 格式的病历模板
- 接收字典格式的字段数据
- 渲染生成最终 Markdown 病历文档
- 支持条件渲染（某些段落根据条件可选显示）
- 预留 .docx / PDF 输出接口
"""

import json
import re
import sys
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)


class TemplateEngine:
    """
    Markdown 模板渲染引擎。
    
    支持的模板语法：
      {{field_name}}          → 变量替换
      {{#condition}}...{{/}}  → 条件块（字段存在且非空时渲染）
      {{^condition}}...{{/}}  → 反向条件块（字段不存在时渲染）
      {{> partial}}           → 包含子模板（预留）
      
    用法:
        engine = TemplateEngine()
        engine.load_template('templates/admission_record.md')
        output = engine.render(data_dict)
    """

    PLACEHOLDER_PATTERN = re.compile(r'\{\{(\w+)\}\}')
    CONDITION_START = re.compile(r'\{\{#(\w+)\}\}')
    CONDITION_ELSE = re.compile(r'\{\{\^(\w+)\}\}')
    CONDITION_END = re.compile(r'\{\{/\}\}')

    def __init__(self):
        self.template_content = ""
        self.template_name = ""

    def load_template(self, template_path: str) -> bool:
        """
        加载 Markdown 模板文件。
        
        Args:
            template_path: 模板文件的绝对或相对路径
            
        Returns:
            True 表示加载成功
        """
        path = Path(template_path)
        if not path.exists():
            logger.error(f"模板文件不存在: {template_path}")
            return False
        
        self.template_content = path.read_text(encoding='utf-8')
        self.template_name = path.name
        logger.info(f"模板加载成功: {template_path} ({len(self.template_content)} 字节)")
        return True

    def load_template_from_string(self, content: str, name: str = "<string>"):
        """从字符串加载模板"""
        self.template_content = content
        self.template_name = name

    def render(self, data: Dict[str, Any]) -> str:
        """
        使用给定数据渲染模板。
        
        Args:
            data: 字段字典，key 为变量名，value 为值
                  支持嵌套字典访问（如 data["patient"]["name"]）
                  
        Returns:
            渲染后的完整 Markdown 文本
        """
        if not self.template_content:
            raise RuntimeError("未加载模板，请先调用 load_template()")
        
        result = self._render_template(self.template_content, data)
        
        # 后处理：清理多余的空行
        result = self._cleanup(result)
        
        logger.info(f"模板渲染完成: {self.template_name} → {len(result)} 字符")
        return result

    def _render_template(self, template: str, data: Dict[str, Any]) -> str:
        """递归渲染模板（处理嵌套条件块）"""
        result = template

        # 1. 先处理条件块（可能有嵌套，需要循环直到没有更多条件块）
        max_iterations = 20  # 防止无限循环
        iteration = 0
        while (self.CONDITION_START.search(result) or 
               self.CONDITION_ELSE.search(result)) and iteration < max_iterations:
            result = self._process_conditions(result, data)
            iteration += 1

        if iteration >= max_iterations:
            logger.warning("条件块处理达到最大迭代次数，可能存在未闭合的条件标签")

        # 2. 替换普通占位符
        result = self.PLACEHOLDER_PATTERN.sub(
            lambda match: self._resolve_value(match.group(1), data),
            result
        )

        return result

    def _process_conditions(self, text: str, data: Dict[str, Any]) -> str:
        """处理条件块 {{#key}} ... {{/}} 和 {{^key}} ... {{/}}"""
        result = text

        # 正向条件：{{#key}} → 如果 key 存在且非空则渲染
        def replace_positive_condition(match):
            condition_key = match.group(1)
            start_tag = match.group(0)
            # 找到对应的 {{/}}
            after_start = result[match.end():]
            end_match = self.CONDITION_END.search(after_start)
            if end_match:
                block_content = after_start[:end_match.start()]
                remaining = after_start[end_match.end():]
                value = self._resolve_value(condition_key, data)
                if value and value.strip():
                    return self._render_template(block_content, data) + remaining
                else:
                    return remaining
            return start_tag  # 没有找到结束标记，保持原样

        # 反向条件：{{^key}} → 如果 key 不存在或为空则渲染
        def replace_negative_condition(match):
            condition_key = match.group(1)
            start_tag = match.group(0)
            after_start = result[match.end():]
            end_match = self.CONDITION_END.search(after_start)
            if end_match:
                block_content = after_start[:end_match.start()]
                remaining = after_start[end_match.end():]
                value = self._resolve_value(condition_key, data)
                if not value or not value.strip():
                    return self._render_template(block_content, data) + remaining
                else:
                    return remaining
            return start_tag

        # 注意：这里简化处理，实际应该用更精确的状态机
        # 对于当前使用场景足够
        result = self.CONDITION_START.sub(replace_positive_condition, result)
        result = self.CONDITION_ELSE.sub(replace_negative_condition, result)
        
        # 清理残留的孤立结束标记
        result = self.CONDITION_END.sub('', result)
        
        return result

    @staticmethod
    def _resolve_value(key: str, data: Dict[str, Any], default: str = "") -> str:
        """
        解析变量值，支持点号分隔的嵌套访问。
        
        示例:
          "patient.name" → data["patient"]["name"]
          "chief_complaint" → data["chief_complaint"]
        """
        keys = key.split('.')
        current = data
        try:
            for k in keys:
                if isinstance(current, dict):
                    current = current[k]
                else:
                    return default
            if current is None:
                return default
            return str(current)
        except (KeyError, TypeError):
            return default

    @staticmethod
    def _cleanup(text: str) -> str:
        """清理渲染输出"""
        # 合并多余空行（保留最多2个连续换行）
        text = re.sub(r'\n{3,}', '\n\n', text)
        # 行尾去空白
        text = '\n'.join(line.rstrip() for line in text.split('\n'))
        # 首尾空白
        text = text.strip()
        return text


# ============================================================
# 预设模板工厂
# ============================================================

class ClinicalTemplates:
    """
    内置临床病历模板集合。
    提供 get_admission_record() / get_discharge_summary() 等快捷方法。
    """

    @staticmethod
    def get_admission_record() -> str:
        """入院记录模板"""
        return """# 入院记录

**姓名**：{{patient_name}}　**性别**：{{gender}}　**年龄**：{{age}}
**民族**：{{ethnicity}}　**婚况**：{{marital_status}}　**职业**：{{occupation}}

## 主诉

{{chief_complaint}}

## 现病史

{{present_illness}}

## 既往史

{{past_history}}

## 个人史

{{personal_history}}

## 家族史

{{family_history}}

## 体格检查

T {{temp_c}}°C　P {{hr_bpm}}次/分　R {{rr_bpm}}次/分　BP {{sbp_mmhg}}/{{dbp_mmhg}} mmHg

{{physical_exam_findings}}

## 辅助检查

{{lab_and_imaging_results}}

## 初步诊断

{{admission_diagnosis}}

                                    记录医师：____________
                                    日期：{{record_datetime}}"""

    @staticmethod
    def get_discharge_summary() -> str:
        """出院小结模板"""
        return """# 出院记录（出院小结）

**姓名**：{{patient_name}}　**性别**：{{gender}}　**年龄**：{{age}}岁
**科室**：{{department}}　**床号**：{{bed_no}}

## 入院诊断
{{admission_diagnosis}}

## 诊治经过
{{treatment_summary}}

## 出院诊断
{{discharge_diagnosis}}

## 出院时情况
T {{temp_c}}°C　P {{hr_bpm}}次/分　R {{rr_bpm}}次/分　BP {{sbp_mmhg}}/{{dbp_mmhg}} mmHg
{{discharge_condition}}

## 出院医嘱

### 用药指导
{{discharge_medications}}

### 生活指导
- 活动：{{activity_instruction}}
- 饮食：{{diet_instruction}}

## 随复诊安排
- **复诊时间**：{{followup_date}}
- **复查项目**：{{followup_exams}}
- **红线症状**：{{red_flag_symptoms}}

---
记录医师：____________
日期：{{record_datetime}}"""

    @staticmethod
    def get_outpatient_note() -> str:
        """门诊病历模板"""
        return """# 门诊病历

**就诊时间**：{{visit_datetime}}　**科室**：{{department}}

## 主诉
{{chief_complaint}}

## 现病史
{{present_illness}}

## 既往史
{{past_history}}

## 过敏史
{{allergy_history}}

## 体格检查
T {{temp_c}}°C　P {{hr_bpm}}次/分　R {{rr_bpm}}次/分　BP {{sbp_mmhg}}/{{dbp_mmhg}} mmHg
{{physical_exam_findings}}

## 辅助检查
{{lab_results}}

## 初步诊断
{{diagnosis}}

## 处置
### 处方
{{prescription}}

### 医嘱
{{instructions}}

---
医师：____________"""

    @staticmethod
    def get_surgery_record() -> str:
        """手术记录模板"""
        return """# 手术记录

**手术日期**：{{surgery_date}} **开始时间**：{{start_time}} **结束时间**：{{end_time}}

**手术名称**：{{surgery_name}}

**术前诊断**：{{preop_diagnosis}}　**术后诊断**：{{postop_diagnosis}}

**术者**：{{surgeon}}　**一助**：{{first_assistant}}
**麻醉方式**：{{anesthesia_type}}　**麻醉医师**：{{anesthesiologist}}

## 手术经过
{{surgical_procedure}}

## 术中情况
- **术中出血量**：{{blood_loss_ml}} ml
- **输血**：{{transfusion_info}}
- **切除标本**：{{specimen_info}}
- **引流管放置**：{{drain_placement}}

## 术后处理
{{postop_instructions}}

---
术者签名：____________
记录者签名：____________"""


# ============================================================
# CLI 接口
# ============================================================

def main():
    """命令行入口"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Markdown 模板渲染引擎',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例用法:
  # 使用内置模板
  echo '{"name":"张三","gender":"男","age":"45","chief_complaint":"胸痛3天"}' | \\
    python template_engine.py --template admission
  
  # 使用自定义模板文件
  python template_engine.py -t my_template.json -f custom_template.md
  
  # 列出内置模板名称
  python template_engine.py --list-templates
        """
    )
    parser.add_argument('--template', '-t',
                        choices=['admission', 'discharge', 'outpatient', 'surgery'],
                        help='使用内置模板')
    parser.add_argument('--file', '-f', help='使用自定义模板文件(.md)')
    parser.add_argument('--data', '-d', help='JSON格式的字段数据（或通过stdin传入）')
    parser.add_argument('--output', '-o', help='输出文件路径（默认stdout）')
    parser.add_argument('--list-templates', action='store_true', help='列出内置模板')

    args = parser.parse_args()

    if args.list_templates:
        print("可用的内置模板:")
        print("  admission     - 入院记录")
        print("  discharge     - 出院小结")
        print("  outpatient    - 门诊病历")
        print("  surgery       - 手术记录")
        return

    # 加载模板
    engine = TemplateEngine()

    if args.template:
        template_getter = {
            'admission': ClinicalTemplates.get_admission_record,
            'discharge': ClinicalTemplates.get_discharge_summary,
            'outpatient': ClinicalTemplates.get_outpatient_note,
            'surgery': ClinicalTemplates.get_surgery_record,
        }
        template_content = template_getter[args.template]()
        engine.load_template_from_string(template_content, f"<builtin:{args.template}>")
    elif args.file:
        if not engine.load_template(args.file):
            sys.exit(1)
    else:
        print("❌ 请指定模板 (--template 或 --file)", file=sys.stderr)
        sys.exit(1)

    # 加载数据
    data_str = args.data
    if not data_str:
        data_str = sys.stdin.read().strip()

    if not data_str:
        print("❌ 请提供JSON格式数据", file=sys.stderr)
        sys.exit(1)

    try:
        data = json.loads(data_str)
    except json.JSONDecodeError as e:
        print(f"❌ JSON解析错误: {e}", file=sys.stderr)
        sys.exit(1)

    # 渲染
    output = engine.render(data)

    # 输出
    if args.output:
        Path(args.output).write_text(output, encoding='utf-8')
        print(f"✅ 已写入: {args.output} ({len(output)} 字符)")
    else:
        print(output)


if __name__ == '__main__':
    main()
