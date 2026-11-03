"""
条款提取脚本
Clause Extraction Script

功能：智能提取合同中的各类条款，包括标的条款、价款条款、期限条款、违约责任等
支持多语言、多格式合同文本的条款识别与分类
"""

import re
import json
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict
from enum import Enum


class ClauseType(Enum):
    """条款类型枚举"""
    # 基础信息条款
    BASIC_INFO = "basic_info"           # 基本信息条款
    PARTIES = "parties"                 # 当事人条款
    
    # 核心权利义务条款
    SUBJECT_MATTER = "subject_matter"   # 标的条款
    PRICE_PAYMENT = "price_payment"     # 价款支付条款
    TIME_PERIOD = "time_period"         # 期限条款
    DELIVERY_PERFORMANCE = "delivery"   # 履行交付条款
    QUALITY_STANDARD = "quality"        # 质量标准条款
    
    # 责任条款
    BREACH_RESPONSIBILITY = "breach"    # 违约责任条款
    LIABILITY_EXEMPTION = "exemption"   # 免责条款
    DAMAGES_COMPENSATION = "damages"    # 损害赔偿条款
    
    # 限制性条款
    CONFIDENTIALITY = "confidentiality" # 保密条款
    NON_COMPETE = "non_compete"         # 竞业限制条款
    NON_SOLICITATION = "non_solicit"    # 竞业禁止条款
    INTELLECTUAL_PROPERTY = "ip"        # 知识产权条款
    
    # 程序性条款
    DISPUTE_RESOLUTION = "dispute"      # 争议解决条款
    JURISDICTION = "jurisdiction"       # 管辖条款
    GOVERNING_LAW = "governing_law"     # 适用法律条款
    FORCE_MAJEURE = "force_majeure"     # 不可抗力条款
    
    # 其他条款
    TERMINATION = "termination"         # 解除终止条款
    ASSIGNMENT = "assignment"           # 转让条款
    AMENDMENT = "amendment"             # 变更条款
    MISCELLANEOUS = "miscellaneous"     # 其他条款
    ATTACHMENTS = "attachments"         # 附件条款


@dataclass
class ExtractedClause:
    """提取的条款数据类"""
    clause_type: str                    # 条款类型
    clause_number: Optional[str]         # 条款编号
    clause_title: Optional[str]          # 条款标题
    clause_content: str                  # 条款内容
    key_elements: Dict                  # 关键要素
    raw_text: str                       # 原始文本片段
    confidence: float                   # 提取置信度


class ClauseExtractor:
    """条款提取器"""
    
    def __init__(self):
        self.clause_patterns = self._init_clause_patterns()
        self.contract_type_patterns = self._init_contract_type_patterns()
    
    def extract(self, contract_text: str, contract_type: str = "auto") -> Dict:
        """
        从合同文本中提取条款
        
        Args:
            contract_text: 合同文本内容
            contract_type: 合同类型
            
        Returns:
            包含提取条款和元信息的字典
        """
        # 自动识别合同类型
        if contract_type == "auto":
            contract_type = self._identify_type(contract_text)
        
        # 文本预处理
        cleaned_text = self._preprocess_text(contract_text)
        
        # 提取条款结构
        clause_structures = self._extract_clause_structures(cleaned_text)
        
        # 按类型分类提取
        classified_clauses = self._classify_clauses(clause_structures, contract_type)
        
        # 提取关键要素
        extracted_elements = self._extract_key_elements(classified_clauses, contract_type)
        
        # 检查条款完整性
        completeness = self._check_completeness(classified_clauses, contract_type)
        
        return {
            "contract_type": contract_type,
            "clauses": [asdict(c) for c in classified_clauses],
            "key_elements": extracted_elements,
            "completeness": completeness,
            "total_clauses": len(classified_clauses)
        }
    
    def _init_clause_patterns(self) -> Dict:
        """初始化条款匹配模式"""
        return {
            ClauseType.SUBJECT_MATTER: {
                "patterns": [
                    r"第[零一二三四五六七八九十百\d]+条[^\n]*标[的物]",
                    r"(?:标的|标的物|服务内容|工作内容|租赁物)[：:]\s*(.+?)(?=\n|$)",
                    r"甲[方乙]?[^\n]*向[甲乙]方[^\n]*(?:提供|交付|转让|出租)[^\n]*"
                ],
                "keywords": ["标的", "标的物", "服务内容", "工作内容", "租赁物", "货物"]
            },
            ClauseType.PRICE_PAYMENT: {
                "patterns": [
                    r"第[零一二三四五六七八九十百\d]+条[^\n]*价[款金]",
                    r"(?:价款|货款|租金|服务费|报酬|工资|费用)[：:]\s*(.+?)(?=\n|$)",
                    r"(?:支付|付款|结算)[^\n]*(?:方式|期限|时间)[^\n]*"
                ],
                "keywords": ["价款", "货款", "租金", "服务费", "报酬", "工资", "支付", "付款"]
            },
            ClauseType.TIME_PERIOD: {
                "patterns": [
                    r"第[零一二三四五六七八九十百\d]+条[^\n]*期限",
                    r"(?:合同期限|有效期|租赁期限|合作期限|任职期限)[：:]\s*(.+?)(?=\n|$)",
                    r"\d{4}[-/年]\d{1,2}[-/月]\d{1,2}[日]?(?:\s*至\s*|\s*-\s*)\d{4}[-/年]\d{1,2}[-/月]\d{1,2}[日]?"
                ],
                "keywords": ["期限", "有效期", "起始", "终止", "届满", "续签", "到期"]
            },
            ClauseType.BREACH_RESPONSIBILITY: {
                "patterns": [
                    r"第[零一二三四五六七八九十百\d]+条[^\n]*违约",
                    r"(?:违约金|违约责任)[：:]\s*(.+?)(?=\n|$)",
                    r"违约[^\n]*支付[^\n]*"
                ],
                "keywords": ["违约", "违约金", "违约责任", "赔偿"]
            },
            ClauseType.CONFIDENTIALITY: {
                "patterns": [
                    r"第[零一二三四五六七八九十百\d]+条[^\n]*保密",
                    r"(?:保密|机密|商业秘密)[：:]\s*(.+?)(?=\n|$)",
                    r"泄密[^\n]*责任"
                ],
                "keywords": ["保密", "机密", "商业秘密", "泄密", "信息安全"]
            },
            ClauseType.NON_COMPETE: {
                "patterns": [
                    r"第[零一二三四五六七八九十百\d]+条[^\n]*竞业",
                    r"(?:竞业限制|竞业禁止)[：:]\s*(.+?)(?=\n|$)",
                    r"离职后[^\n]*不得[^\n]*"
                ],
                "keywords": ["竞业限制", "竞业禁止", "竞争", "同行"]
            },
            ClauseType.TERMINATION: {
                "patterns": [
                    r"第[零一二三四五六七八九十百\d]+条[^\n]*(?:解除|终止|结束)",
                    r"(?:解除|终止)[^\n]*条件",
                    r"提前[^\n]*(?:解约|终止|解除)"
                ],
                "keywords": ["解除", "终止", "解约", "到期", "续签"]
            },
            ClauseType.DISPUTE_RESOLUTION: {
                "patterns": [
                    r"第[零一二三四五六七八九十百\d]+条[^\n]*(?:争议|纠纷)",
                    r"(?:仲裁|诉讼|管辖)[^\n]*(?:机构|法院|委员会)",
                    r"提交[^\n]*(?:仲裁|诉讼)"
                ],
                "keywords": ["争议", "纠纷", "仲裁", "诉讼", "管辖", "法院"]
            },
            ClauseType.FORCE_MAJEURE: {
                "patterns": [
                    r"第[零一二三四五六七八九十百\d]+条[^\n]*不可抗力",
                    r"(?:不可抗力)[：:]\s*(.+?)(?=\n|$)",
                    r"(?:自然灾害|战争|疫情)[^\n]*(?:属于|属于)"
                ],
                "keywords": ["不可抗力", "自然灾害", "战争", "疫情", "政府行为"]
            },
            ClauseType.QUALITY_STANDARD: {
                "patterns": [
                    r"第[零一二三四五六七八九十百\d]+条[^\n]*质量",
                    r"(?:质量标准|技术参数|规格型号)[：:]\s*(.+?)(?=\n|$)",
                    r"(?:验收|检验|合格)[^\n]*(?:标准|期限|方式)"
                ],
                "keywords": ["质量", "标准", "规格", "验收", "检验", "合格"]
            },
            ClauseType.DELIVERY_PERFORMANCE: {
                "patterns": [
                    r"第[零一二三四五六七八九十百\d]+条[^\n]*交付",
                    r"(?:交付|交货|履行)[^\n]*(?:时间|地点|方式)",
                    r"(?:交付|发货|运输|运送)[：:]\s*(.+?)(?=\n|$)"
                ],
                "keywords": ["交付", "交货", "发货", "运输", "送达"]
            }
        }
    
    def _init_contract_type_patterns(self) -> Dict:
        """初始化合同类型识别模式"""
        return {
            "劳动合同": {
                "keywords": ["劳动合同", "用人单位", "劳动者", "工作岗位", "劳动报酬", "社会保险"],
                "required_clauses": [ClauseType.BASIC_INFO, ClauseType.SUBJECT_MATTER, 
                                    ClauseType.PRICE_PAYMENT, ClauseType.TIME_PERIOD,
                                    ClauseType.BREACH_RESPONSIBILITY]
            },
            "买卖合同": {
                "keywords": ["买卖", "买方", "卖方", "标的物", "货款", "交货"],
                "required_clauses": [ClauseType.BASIC_INFO, ClauseType.SUBJECT_MATTER,
                                    ClauseType.PRICE_PAYMENT, ClauseType.DELIVERY_PERFORMANCE,
                                    ClauseType.QUALITY_STANDARD, ClauseType.BREACH_RESPONSIBILITY]
            },
            "租赁合同": {
                "keywords": ["租赁", "出租人", "承租人", "租赁物", "租金", "押金"],
                "required_clauses": [ClauseType.BASIC_INFO, ClauseType.SUBJECT_MATTER,
                                    ClauseType.PRICE_PAYMENT, ClauseType.TIME_PERIOD,
                                    ClauseType.BREACH_RESPONSIBILITY]
            },
            "服务合同": {
                "keywords": ["服务", "委托", "受托", "服务内容", "服务费"],
                "required_clauses": [ClauseType.BASIC_INFO, ClauseType.SUBJECT_MATTER,
                                    ClauseType.PRICE_PAYMENT, ClauseType.TIME_PERIOD,
                                    ClauseType.BREACH_RESPONSIBILITY]
            },
            "借款合同": {
                "keywords": ["借款", "借款人", "出借人", "借款金额", "利率", "还款"],
                "required_clauses": [ClauseType.BASIC_INFO, ClauseType.PRICE_PAYMENT,
                                    ClauseType.TIME_PERIOD, ClauseType.BREACH_RESPONSIBILITY]
            },
            "技术合同": {
                "keywords": ["技术", "开发", "转让", "许可", "知识产权", "成果"],
                "required_clauses": [ClauseType.BASIC_INFO, ClauseType.SUBJECT_MATTER,
                                    ClauseType.PRICE_PAYMENT, ClauseType.QUALITY_STANDARD,
                                    ClauseType.INTELLECTUAL_PROPERTY]
            }
        }
    
    def _preprocess_text(self, text: str) -> str:
        """预处理合同文本"""
        # 规范化空白字符
        text = re.sub(r'\s+', ' ', text)
        # 规范化引号
        text = text.replace('"', '"').replace('"', '"')
        text = text.replace(''', "'").replace(''', "'")
        # 规范化破折号
        text = text.replace('—', '-').replace('–', '-')
        return text
    
    def _identify_type(self, text: str) -> str:
        """识别合同类型"""
        scores = {}
        for contract_type, info in self.contract_type_patterns.items():
            score = sum(1 for kw in info["keywords"] if kw in text)
            scores[contract_type] = score
        
        max_type = max(scores, key=scores.get)
        return max_type if scores[max_type] > 0 else "其他合同"
    
    def _extract_clause_structures(self, text: str) -> List[Dict]:
        """提取条款结构"""
        clauses = []
        
        # 按编号提取条款
        clause_pattern = r'第([零一二三四五六七八九十百\d]+)条\s*([^：:]+)?[：:]?\s*(.+?)(?=(?:第[零一二三四五六七八九十百\d]+条)|$)'
        
        matches = re.finditer(clause_pattern, text)
        for match in matches:
            clause_num = match.group(1)
            clause_title = match.group(2).strip() if match.group(2) else ""
            clause_content = match.group(3).strip()
            
            clauses.append({
                "number": clause_num,
                "title": clause_title,
                "content": clause_content,
                "raw_match": match.group(0)
            })
        
        # 如果没有按条款编号提取，尝试按段落提取
        if not clauses:
            paragraphs = text.split('\n')
            for i, para in enumerate(paragraphs):
                if para.strip() and len(para.strip()) > 20:
                    clauses.append({
                        "number": str(i + 1),
                        "title": "",
                        "content": para.strip(),
                        "raw_match": para.strip()
                    })
        
        return clauses
    
    def _classify_clauses(self, clause_structures: List[Dict], contract_type: str) -> List[ExtractedClause]:
        """对条款进行分类"""
        classified = []
        
        for clause in clause_structures:
            content = clause["content"]
            matched_type = None
            confidence = 0.0
            
            # 遍历所有条款类型模式
            for clause_type, pattern_info in self.clause_patterns.items():
                # 检查关键词
                keyword_count = sum(1 for kw in pattern_info["keywords"] if kw in content)
                if keyword_count > 0:
                    pattern_score = keyword_count / len(pattern_info["keywords"])
                    
                    # 检查正则匹配
                    pattern_match = False
                    for pattern in pattern_info["patterns"]:
                        if re.search(pattern, content):
                            pattern_match = True
                            break
                    
                    if pattern_match:
                        score = 0.5 + pattern_score * 0.5
                    else:
                        score = pattern_score * 0.7
                    
                    if score > confidence:
                        confidence = score
                        matched_type = clause_type
            
            # 如果没有匹配到特定类型，归类为杂项
            if matched_type is None:
                matched_type = ClauseType.MISCELLANEOUS
                confidence = 0.3
            
            classified.append(ExtractedClause(
                clause_type=matched_type.value,
                clause_number=clause["number"],
                clause_title=clause["title"],
                clause_content=content[:500],  # 限制长度
                key_elements={},
                raw_text=clause["raw_match"],
                confidence=round(confidence, 2)
            ))
        
        return classified
    
    def _extract_key_elements(self, clauses: List[ExtractedClause], 
                              contract_type: str) -> Dict:
        """提取关键要素"""
        elements = {
            "parties": {},       # 当事人信息
            "dates": [],         # 日期信息
            "amounts": [],       # 金额信息
            "periods": [],       # 期限信息
            "locations": []      # 地点信息
        }
        
        full_text = " ".join([c.clause_content for c in clauses])
        
        # 提取金额
        amount_patterns = [
            r'([¥￥$])\s*(\d+(?:,\d{3})*(?:\.\d{2})?)',
            r'(?:人民币|美元|欧元)?\s*(\d+(?:,\d{3})*(?:\.\d{2})?)\s*(?:元|万|亿)',
            r'(\d+(?:\.\d+)?)\s*%(?:\s*(?:日|月|年))?'
        ]
        
        for pattern in amount_patterns:
            matches = re.finditer(pattern, full_text)
            for match in matches:
                elements["amounts"].append(match.group(0))
        
        # 提取日期
        date_patterns = [
            r'\d{4}年\d{1,2}月\d{1,2}日',
            r'\d{4}-\d{1,2}-\d{1,2}',
            r'\d{4}/\d{1,2}/\d{1,2}'
        ]
        
        for pattern in date_patterns:
            matches = re.finditer(pattern, full_text)
            for match in matches:
                elements["dates"].append(match.group(0))
        
        # 提取期限
        period_patterns = [
            r'(\d+)\s*(?:年|个月?|日|天)',
            r'自[^\d]*(\d{4}[年/-]\d{1,2}[月/-]\d{1,2}[日]?)\s*(?:至|至|起)'
        ]
        
        for pattern in period_patterns:
            matches = re.finditer(pattern, full_text)
            for match in matches:
                elements["periods"].append(match.group(0))
        
        # 提取当事人
        party_patterns = [
            r'甲方[：:]\s*([^\n，,。]+)',
            r'乙方[：:]\s*([^\n，,。]+)',
            r'(?:公司|企业|单位|个人)[^\n，,。]*(?:以下|以下简称)[^\n，,。]+'
        ]
        
        for pattern in party_patterns:
            matches = re.finditer(pattern, full_text)
            for match in matches:
                if match.group(1):
                    elements["parties"][f"party_{len(elements['parties']) + 1}"] = match.group(1).strip()
        
        return elements
    
    def _check_completeness(self, clauses: List[ExtractedClause], 
                           contract_type: str) -> Dict:
        """检查条款完整性"""
        # 获取合同类型要求的必需条款
        if contract_type in self.contract_type_patterns:
            required = self.contract_type_patterns[contract_type]["required_clauses"]
        else:
            required = []
        
        # 检查实际提取的条款类型
        extracted_types = set(c.clause_type for c in clauses)
        required_types = set(r.value for r in required)
        
        missing = required_types - extracted_types
        present = required_types & extracted_types
        
        return {
            "is_complete": len(missing) == 0,
            "missing_clauses": list(missing),
            "present_clauses": list(present),
            "missing_count": len(missing),
            "total_required": len(required)
        }


def main():
    """测试函数"""
    extractor = ClauseExtractor()
    
    # 测试用劳动合同文本
    test_contract = """
    劳动合同
    
    甲方：深圳市XX科技有限公司
    乙方：张三
    
    第三条 工作内容
    乙方同意在技术部门担任高级工程师，工作地点为深圳市南山区。
    
    第五条 薪酬待遇
    乙方的月工资为税前28000元，每月15日前发放。
    
    第七条 竞业限制
    乙方离职后两年内不得在同行业从事相关工作，违反者需支付违约金50万元。
    
    第九条 加班条款
    甲方有权要求乙方加班，乙方应无条件服从，加班费按正常工资的80%计算。
    
    第十二条 争议解决
    因本合同引起的争议，提交甲方所在地仲裁委员会仲裁。
    """
    
    result = extractor.extract(test_contract)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
