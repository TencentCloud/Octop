"""
风险检测脚本
Risk Detection Script

功能：智能检测合同中的各类风险，包括高风险、中风险、低风险条款
支持显性风险（明确不利条款）和隐性风险（模糊表述、灰色地带）的识别
"""

import re
import json
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from enum import Enum
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))


class RiskLevel(Enum):
    """风险等级枚举"""
    HIGH = "high"      # 高风险
    MEDIUM = "medium"   # 中风险
    LOW = "low"        # 低风险


@dataclass
class DetectedRisk:
    """检测到的风险"""
    clause: str                    # 相关条款
    clause_type: str               # 条款类型
    risk_type: str                 # 风险类型
    risk_level: str               # 风险等级
    description: str              # 风险描述
    problem: str                  # 问题分析
    suggestion: str               # 修改建议
    legal_basis: Optional[str]    # 法律依据
    severity_score: float         # 严重程度评分(0-10)


class RiskDetector:
    """风险检测器"""
    
    def __init__(self):
        self.risk_rules = self._init_risk_rules()
        self.legal_basis_db = self._init_legal_basis_db()
    
    def detect(self, clauses_data: Dict, contract_type: str) -> Dict:
        """
        检测合同风险
        
        Args:
            clauses_data: 条款提取结果
            contract_type: 合同类型
            
        Returns:
            包含高、中、低风险条款的字典
        """
        risks = {
            "high_risk": [],
            "medium_risk": [],
            "low_risk": [],
            "risk_summary": {}
        }
        
        clauses = clauses_data.get("clauses", [])
        key_elements = clauses_data.get("key_elements", {})
        
        # 遍历每个条款进行风险检测
        for clause in clauses:
            clause_type = clause.get("clause_type", "")
            clause_content = clause.get("clause_content", "")
            clause_number = clause.get("clause_number", "")
            
            # 获取该条款类型的风险规则
            type_rules = self.risk_rules.get(clause_type, [])
            
            for rule in type_rules:
                if self._check_rule_match(clause_content, rule):
                    detected_risk = self._create_risk(
                        clause_number=clause_number,
                        clause_type=clause_type,
                        clause_content=clause_content,
                        rule=rule,
                        contract_type=contract_type
                    )
                    
                    # 根据风险等级分类
                    if detected_risk.risk_level == RiskLevel.HIGH.value:
                        risks["high_risk"].append(asdict(detected_risk))
                    elif detected_risk.risk_level == RiskLevel.MEDIUM.value:
                        risks["medium_risk"].append(asdict(detected_risk))
                    else:
                        risks["low_risk"].append(asdict(detected_risk))
        
        # 进行跨条款关联分析
        cross_clause_risks = self._analyze_cross_clause_risks(clauses, contract_type)
        for risk in cross_clause_risks:
            if risk.risk_level == RiskLevel.HIGH.value:
                risks["high_risk"].append(asdict(risk))
            elif risk.risk_level == RiskLevel.MEDIUM.value:
                risks["medium_risk"].append(asdict(risk))
            else:
                risks["low_risk"].append(asdict(risk))
        
        # 生成风险摘要
        risks["risk_summary"] = self._generate_risk_summary(risks)
        
        return risks
    
    def _init_risk_rules(self) -> Dict:
        """初始化风险检测规则"""
        return {
            # 违约责任条款风险
            "breach": [
                {
                    "name": "违约金过高",
                    "patterns": [
                        r"违约金\s*[为:：]?\s*\d+(?:\.\d+)?\s*%",
                        r"每日\s*\d+(?:\.\d+)?\s*%",
                        r"按\s*(?:合同\s*)?(?:总价|总额|总金额)\s*(?:\d+(?:\.\d+)?\s*%)"
                    ],
                    "risk_level": RiskLevel.HIGH,
                    "description": "违约金比例可能过高",
                    "problem": "违约金比例超过法定标准或商业惯例，可能被法院调减",
                    "suggestion": "建议将违约金比例调整为：逾期付款不超过同期贷款利率的1.5倍；逾期交货不超过每日0.05%",
                    "legal_basis": "《民法典》第585条：约定的违约金过分高于造成的损失的，当事人可以请求法院予以适当减少"
                },
                {
                    "name": "违约金不对等",
                    "patterns": [
                        r"甲方[^\n]*违约金[^\n]*0\.[5-9]?\d?%",
                        r"乙方[^\n]*违约金[^\n]*0\.[0-3]?\d?%"
                    ],
                    "risk_level": RiskLevel.HIGH,
                    "description": "双方违约金比例严重不对等",
                    "problem": "一方违约金明显高于另一方，显失公平",
                    "suggestion": "建议双方违约金比例保持一致或相近",
                    "legal_basis": "《民法典》第497条：提供格式条款一方不得利用优势地位订立不公平条款"
                }
            ],
            
            # 竞业限制条款风险
            "non_compete": [
                {
                    "name": "竞业限制期限过长",
                    "patterns": [
                        r"离职后[^\d]*(\d+)\s*年",
                        r"竞业限制[^\d]*(\d+)\s*年"
                    ],
                    "risk_level": RiskLevel.HIGH,
                    "description": "竞业限制期限超过法定期限",
                    "problem": "竞业限制期限超过2年，违反法律规定",
                    "suggestion": "建议将竞业限制期限缩短至不超过2年",
                    "legal_basis": "《劳动合同法》第24条：竞业限制期限不得超过二年"
                },
                {
                    "name": "竞业限制范围过宽",
                    "patterns": [
                        r"不得[^\n]*(?:从事|进入|就职|任职)[^\n]*(?:任何|所有|相关)?(?:行业|工作|领域|业务)",
                        r"竞业范围[^\n]*(?:不限于|包括但不限于)[^\n]*所有"
                    ],
                    "risk_level": RiskLevel.MEDIUM,
                    "description": "竞业限制范围过于宽泛",
                    "problem": "竞业范围没有明确限定，可能影响劳动者正常就业",
                    "suggestion": "建议明确限定竞业限制的行业范围、地域范围",
                    "legal_basis": "《劳动合同法》第24条：竞业限制的范围、地域、期限由用人单位与劳动者约定"
                },
                {
                    "name": "无经济补偿",
                    "patterns": [
                        r"竞业限制[^\n]*义务[^\n]*(?:但|但|但)(?:未|没有|不包含)[^\n]*补偿",
                        r"(?:无|无|无需)[^\n]*补偿[^\n]*竞业限制"
                    ],
                    "risk_level": RiskLevel.HIGH,
                    "description": "竞业限制未约定经济补偿",
                    "problem": "仅约定竞业限制义务而未约定经济补偿，可能被认定无效",
                    "suggestion": "建议补充约定经济补偿，标准不低于劳动者离职前12个月平均工资的30%",
                    "legal_basis": "《劳动合同法》第23条：用人单位应在竞业限制期限内按月给予劳动者经济补偿"
                }
            ],
            
            # 保密条款风险
            "confidentiality": [
                {
                    "name": "保密范围过宽",
                    "patterns": [
                        r"保密范围[^\n]*(?:包括|涵盖|包含)[^\n]*任何(?:信息|资料|内容)",
                        r"商业秘密[^\n]*(?:包括|不限于)[^\n]*所有"
                    ],
                    "risk_level": RiskLevel.MEDIUM,
                    "description": "保密范围定义过于宽泛",
                    "problem": "将公知信息也纳入保密范围，可能被认定无效",
                    "suggestion": "建议明确界定商业秘密的具体范围，包括但不限于：客户名单、技术方案等",
                    "legal_basis": "《反不正当竞争法》第9条：商业秘密是指不为公众所知悉、具有商业价值并经权利人采取相应保密措施的技术信息、经营信息等商业信息"
                },
                {
                    "name": "违约金过高",
                    "patterns": [
                        r"违反保密义务[^\n]*违约金[^\n]*\d+"
                    ],
                    "risk_level": RiskLevel.MEDIUM,
                    "description": "保密违约金可能过高",
                    "problem": "保密违约金过高，可能被法院调减",
                    "suggestion": "建议违约金与实际可能造成的损失相匹配",
                    "legal_basis": "《民法典》第585条"
                }
            ],
            
            # 加班条款风险
            "time_period": [
                {
                    "name": "加班费计算标准违法",
                    "patterns": [
                        r"加班费[^\d]*(?:\d+(?:\.\d+)?\s*%)",
                        r"按\s*(?:正常\s*)?工资\s*(?:的\s*)?(?:\d+(?:\.\d+)?\s*%)",
                        r"加班[^\n]*(?:无|不用|无需)[^\n]*费用"
                    ],
                    "risk_level": RiskLevel.HIGH,
                    "description": "加班费计算标准低于法定标准",
                    "problem": "加班费低于法定标准，违反劳动法强制性规定",
                    "suggestion": "工作日加班不低于150%；休息日加班又不能补休不低于200%；法定节假日不低于300%",
                    "legal_basis": "《劳动法》第44条"
                }
            ],
            
            # 质量条款风险
            "quality": [
                {
                    "name": "质量标准模糊",
                    "patterns": [
                        r"质量标准[^\n]*(?:按|按照)[^\n]*(?:国家|行业|相关)[^\n]*执行",
                        r"质量[^\n]*(?:合格|达标|符合)[^\n]*(?:即可|即可|即可)"
                    ],
                    "risk_level": RiskLevel.MEDIUM,
                    "description": "质量标准约定过于模糊",
                    "problem": "未明确具体质量标准，可能导致验收争议",
                    "suggestion": "建议明确质量标准编号（如GB/T标准），规定检验期限和异议处理流程",
                    "legal_basis": "《民法典》第615条：出卖人交付的标的物需要符合约定的质量标准"
                }
            ],
            
            # 期限条款风险
            "time_period": [
                {
                    "name": "合同期限过长",
                    "patterns": [
                        r"合同期限[^\n]*(\d+)\s*年(?:\s*以上|以上|\s*及|及)\s*自动续约"
                    ],
                    "risk_level": RiskLevel.MEDIUM,
                    "description": "合同期限过长且自动续约",
                    "problem": "合同期限过长且无正当理由自动续约，可能影响当事人权益",
                    "suggestion": "建议明确合同期限，或增加续约条件和提前通知期限",
                    "legal_basis": "《民法典》第470条：合同内容由当事人约定"
                }
            ],
            
            # 解除条款风险
            "termination": [
                {
                    "name": "单方解除权限制过多",
                    "patterns": [
                        r"甲方[^\n]*有权[^\n]*随时[^\n]*(?:解除|终止|解约)",
                        r"乙方[^\n]*(?:不得|无权|不能)[^\n]*(?:解除|终止|解约)"
                    ],
                    "risk_level": RiskLevel.HIGH,
                    "description": "单方解除权严重不对等",
                    "problem": "一方有权随时解除，另一方却无权解除，权利义务严重失衡",
                    "suggestion": "建议赋予双方对等的解除权，或明确解除条件和程序",
                    "legal_basis": "《民法典》第563条：当事人可以解除合同的情形"
                },
                {
                    "name": "提前解约违约金过高",
                    "patterns": [
                        r"提前[^\n]*解(?:约|除)[^\n]*违约金[^\n]*\d+\s*(?:个月?|年)?\s*工资",
                        r"提前[^\n]*解(?:约|除)[^\n]*支付[^\n]*(?:总金额|总额|全部)[^\n]*"
                    ],
                    "risk_level": RiskLevel.MEDIUM,
                    "description": "提前解约违约金过高",
                    "problem": "提前解约违约金与剩余合同价值不匹配",
                    "suggestion": "建议将违约金与剩余合同期限挂钩",
                    "legal_basis": "《民法典》第585条"
                }
            ],
            
            # 管辖条款风险
            "dispute": [
                {
                    "name": "管辖约定不明确",
                    "patterns": [
                        r"管辖[^\n]*(?:由|为|在)[^\n]*(?:所在地|住所地)",
                        r"提交[^\n]*(?:仲裁|诉讼)[^\n]*(?:委员会|法院)"
                    ],
                    "risk_level": RiskLevel.MEDIUM,
                    "description": "管辖约定不够明确具体",
                    "problem": "未明确具体的仲裁机构或法院，可能导致管辖争议",
                    "suggestion": "建议明确约定具体的仲裁委员会名称或法院名称",
                    "legal_basis": "《民事诉讼法》第34条：合同或者其他财产权益纠纷的当事人可以书面协议选择管辖法院"
                },
                {
                    "name": "格式条款加重对方责任",
                    "patterns": [
                        r"(?:甲方|本公司|我方)[^\n]*享有[^\n]*(?:最终|绝对)[^\n]*解释[^\n]*权",
                        r"(?:甲方|本公司)[^\n]*有权[^\n]*随时[^\n]*(?:修改|变更|调整)"
                    ],
                    "risk_level": RiskLevel.HIGH,
                    "description": "格式条款加重对方责任",
                    "problem": "单方面保留修改权和解释权，可能构成无效格式条款",
                    "suggestion": "建议删除或修改该条款，改为双方协商确定",
                    "legal_basis": "《民法典》第497条：提供格式条款一方不得排除对方主要权利"
                }
            ]
        }
    
    def _init_legal_basis_db(self) -> Dict:
        """初始化法律依据数据库"""
        return {
            "劳动法": {
                "第44条": "安排劳动者延长工作时间的，支付不低于工资的150%的工资报酬；休息日安排工作又不能安排补休的，支付不低于工资的200%的工资报酬；法定休假日安排工作的，支付不低于工资的300%的工资报酬。",
                "第24条": "竞业限制期限不得超过二年。",
                "第23条": "用人单位应当在竞业限制期限内按月给予劳动者经济补偿。"
            },
            "民法典": {
                "第585条": "约定的违约金过分高于造成的损失的，当事人可以请求人民法院或者仲裁机构予以适当减少。",
                "第497条": "提供格式条款一方不合理地免除或者减轻其责任、加重对方责任、限制对方主要权利的，该格式条款无效。",
                "第563条": "有下列情形之一的，当事人可以解除合同：因不可抗力致使不能实现合同目的；在履行期限届满前，当事人一方明确表示或者以自己的行为表明不履行主要债务；当事人一方迟延履行主要债务，经催告后在合理期限内仍未履行等。"
            }
        }
    
    def _check_rule_match(self, text: str, rule: Dict) -> bool:
        """检查文本是否匹配风险规则"""
        for pattern in rule.get("patterns", []):
            if re.search(pattern, text, re.IGNORECASE):
                return True
        return False
    
    def _create_risk(self, clause_number: str, clause_type: str, 
                    clause_content: str, rule: Dict, contract_type: str) -> DetectedRisk:
        """创建风险对象"""
        # 计算严重程度评分
        severity_score = self._calculate_severity(
            clause_content, rule, contract_type
        )
        
        # 确定风险等级
        risk_level = rule["risk_level"].value
        
        return DetectedRisk(
            clause=f"第{clause_number}条" if clause_number else "条款",
            clause_type=clause_type,
            risk_type=rule["name"],
            risk_level=risk_level,
            description=rule["description"],
            problem=rule["problem"],
            suggestion=rule["suggestion"],
            legal_basis=rule.get("legal_basis"),
            severity_score=severity_score
        )
    
    def _calculate_severity(self, text: str, rule: Dict, contract_type: str) -> float:
        """计算风险严重程度评分"""
        base_score = {
            RiskLevel.HIGH: 8.0,
            RiskLevel.MEDIUM: 5.0,
            RiskLevel.LOW: 3.0
        }.get(rule["risk_level"], 5.0)
        
        # 关键词加成
        risk_keywords = ["无", "任何", "所有", "无条件", "绝对", "随时"]
        for kw in risk_keywords:
            if kw in text:
                base_score += 0.5
        
        # 金额数字加成（检测到具体金额）
        if re.search(r'\d+\s*(?:万|亿|%)', text):
            base_score += 1.0
        
        return min(10.0, base_score)
    
    def _analyze_cross_clause_risks(self, clauses: List[Dict], 
                                   contract_type: str) -> List[DetectedRisk]:
        """进行跨条款关联风险分析"""
        risks = []
        
        # 收集关键要素
        amounts = []
        periods = []
        
        for clause in clauses:
            content = clause.get("clause_content", "")
            # 提取金额
            amount_matches = re.findall(r'(\d+(?:\.\d+)?)\s*(?:万|亿|元|%)', content)
            amounts.extend([float(a) for a in amount_matches])
            # 提取期限
            period_matches = re.findall(r'(\d+)\s*(?:年|个月?|日)', content)
            periods.extend([int(p) for p in period_matches])
        
        # 关联风险检测
        # 1. 违约金与金额的关系
        if amounts:
            max_amount = max(amounts)
            for clause in clauses:
                content = clause.get("clause_content", "")
                clause_number = clause.get("clause_number", "")
                
                # 检测到固定金额违约金超过合同金额30%
                amount_in_clause = re.findall(r'(\d+(?:\.\d+)?)', content)
                if amount_in_clause:
                    clause_amount = max([float(a) for a in amount_in_clause])
                    if max_amount > 0 and clause_amount / max_amount > 0.3:
                        if "违约金" in content:
                            risks.append(DetectedRisk(
                                clause=f"第{clause_number}条",
                                clause_type="cross_clause",
                                risk_type="违约金金额占比过高",
                                risk_level=RiskLevel.MEDIUM.value,
                                description="违约金金额占合同金额比例过高",
                                problem=f"违约金{clause_amount}万元，占合同金额比例超过30%",
                                suggestion="建议将违约金比例调整至合同金额的30%以内",
                                legal_basis="《民法典》第585条：违约金以补偿性为主，惩罚性为辅",
                                severity_score=6.5
                            ))
        
        # 2. 竞业限制与其他条款的关联
        has_non_compete = any(c.get("clause_type") == "non_compete" for c in clauses)
        has_confidentiality = any(c.get("clause_type") == "confidentiality" for c in clauses)
        
        if has_non_compete and not has_confidentiality:
            for clause in clauses:
                if clause.get("clause_type") == "non_compete":
                    risks.append(DetectedRisk(
                        clause=f"第{clause.get('clause_number')}条",
                        clause_type="cross_clause",
                        risk_type="竞业限制缺少配套保密条款",
                        risk_level=RiskLevel.LOW.value,
                        description="竞业限制未配套保密条款",
                        problem="单独约定竞业限制而未约定保密条款，保护不完整",
                        suggestion="建议同时签订保密协议，明确保密范围和期限",
                        legal_basis=None,
                        severity_score=4.0
                    ))
        
        return risks
    
    def _generate_risk_summary(self, risks: Dict) -> Dict:
        """生成风险摘要"""
        high_count = len(risks.get("high_risk", []))
        medium_count = len(risks.get("medium_risk", []))
        low_count = len(risks.get("low_risk", []))
        
        # 统计风险类型分布
        risk_types = {}
        for level in ["high_risk", "medium_risk", "low_risk"]:
            for risk in risks.get(level, []):
                risk_type = risk.get("risk_type", "")
                risk_types[risk_type] = risk_types.get(risk_type, 0) + 1
        
        # 识别高风险条款类型
        high_risk_types = [r.get("risk_type", "") for r in risks.get("high_risk", [])]
        
        return {
            "total_risks": high_count + medium_count + low_count,
            "high_risk_count": high_count,
            "medium_risk_count": medium_count,
            "low_risk_count": low_count,
            "risk_types_distribution": risk_types,
            "high_risk_keywords": high_risk_types,
            "overall_risk_level": "高危" if high_count > 0 else ("中危" if medium_count > 0 else "低危")
        }


def main():
    """测试函数"""
    from scripts.clause_extraction import ClauseExtractor
    
    extractor = ClauseExtractor()
    detector = RiskDetector()
    
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
    
    clauses_data = extractor.extract(test_contract, "劳动合同")
    risks = detector.detect(clauses_data, "劳动合同")
    
    print(json.dumps(risks, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
