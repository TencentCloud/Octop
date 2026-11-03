"""
合规检查脚本
Compliance Check Script

功能：核对合同是否符合法律法规的强制性规定
支持格式条款审查、时效条款检查、管辖约定合法性验证等
"""

import re
import json
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))


@dataclass
class ComplianceIssue:
    """合规问题"""
    clause: str                     # 相关条款
    issue_type: str               # 问题类型
    severity: str                 # 严重程度
    problem: str                  # 问题描述
    legal_basis: str              # 法律依据
    suggestion: str              # 修改建议
    regulation: str               # 具体法规


class ComplianceChecker:
    """合规检查器"""
    
    def __init__(self):
        self.mandatory_rules = self._init_mandatory_rules()
        self.format_clause_rules = self._init_format_clause_rules()
    
    def check(self, contract_text: str, clauses_data: Dict, 
              contract_type: str) -> Dict:
        """
        执行合规检查
        
        Args:
            contract_text: 合同全文
            clauses_data: 条款提取结果
            contract_type: 合同类型
            
        Returns:
            合规检查结果
        """
        issues = {
            "mandatory_violations": [],    # 强制性规定违反
            "format_clause_issues": [],    # 格式条款问题
            "pending_validity": [],        # 效力待定条款
            "jurisdiction_issues": []      # 管辖问题
        }
        
        clauses = clauses_data.get("clauses", [])
        
        # 1. 检查强制性规定违反
        mandatory_violations = self._check_mandatory_rules(
            contract_text, clauses, contract_type
        )
        issues["mandatory_violations"] = mandatory_violations
        
        # 2. 检查格式条款问题
        format_issues = self._check_format_clauses(
            contract_text, clauses, contract_type
        )
        issues["format_clause_issues"] = format_issues
        
        # 3. 检查效力待定条款
        pending_issues = self._check_pending_validity(
            contract_text, clauses, contract_type
        )
        issues["pending_validity"] = pending_issues
        
        # 4. 检查管辖约定
        jurisdiction_issues = self._check_jurisdiction(
            contract_text, clauses, contract_type
        )
        issues["jurisdiction_issues"] = jurisdiction_issues
        
        # 合并所有问题
        all_issues = (
            issues["mandatory_violations"] + 
            issues["format_clause_issues"] + 
            issues["pending_validity"] +
            issues["jurisdiction_issues"]
        )
        
        return {
            "issues": [asdict(i) for i in all_issues],
            "mandatory_violations": [asdict(i) for i in issues["mandatory_violations"]],
            "format_clause_issues": [asdict(i) for i in issues["format_clause_issues"]],
            "pending_validity": [asdict(i) for i in issues["pending_validity"]],
            "jurisdiction_issues": [asdict(i) for i in issues["jurisdiction_issues"]],
            "is_compliant": len([i for i in all_issues if i.severity == "严重"]) == 0,
            "compliance_score": self._calculate_compliance_score(issues)
        }
    
    def _init_mandatory_rules(self) -> Dict:
        """初始化强制性规定检查规则"""
        return {
            "劳动类": [
                {
                    "rule_id": "L001",
                    "name": "最低工资标准",
                    "patterns": [r"工资[^\n]*不低于", r"工资[^\n]*高于"],
                    "severity": "严重",
                    "description": "工资不得低于当地最低工资标准",
                    "legal_basis": "《劳动法》第48条：国家实行最低工资保障制度",
                    "suggestion": "确保工资不低于当地政府公布的最低工资标准"
                },
                {
                    "rule_id": "L002",
                    "name": "社会保险缴纳",
                    "patterns": [r"(?:不|无需|免于)[^\n]*社会保险", r"社会保险[^\n]*(?:不含|不包括)"],
                    "severity": "严重",
                    "description": "用人单位必须为劳动者缴纳社会保险",
                    "legal_basis": "《劳动法》第72条：用人单位和劳动者必须依法参加社会保险",
                    "suggestion": "必须为劳动者缴纳五险一金"
                },
                {
                    "rule_id": "L003",
                    "name": "加班费标准",
                    "patterns": [
                        r"加班[^\n]*按\s*\d+\s*%",
                        r"加班费[^\n]*(?:少于|低于|不低于)[^\n]*\d+\s*%"
                    ],
                    "severity": "严重",
                    "description": "加班费计算标准必须符合法律规定",
                    "legal_basis": "《劳动法》第44条",
                    "suggestion": "工作日加班不低于150%，休息日加班不低于200%，法定节假日不低于300%"
                },
                {
                    "rule_id": "L004",
                    "name": "竞业限制期限",
                    "patterns": [r"竞业限制[^\d]*(\d+)\s*年"],
                    "severity": "严重",
                    "description": "竞业限制期限不得超过二年",
                    "legal_basis": "《劳动合同法》第24条",
                    "suggestion": "将竞业限制期限缩短至不超过2年"
                },
                {
                    "rule_id": "L005",
                    "name": "押金收取",
                    "patterns": [r"(?:押金|保证金)[^\n]*(?:不得|禁止|不应)"],
                    "severity": "警告",
                    "description": "用人单位不得收取押金",
                    "legal_basis": "《劳动合同法》第9条：用人单位不得扣押劳动者证件或收取财物",
                    "suggestion": "删除押金条款或改为其他合法担保方式"
                },
                {
                    "rule_id": "L006",
                    "name": "工伤保险",
                    "patterns": [r"(?:不|无需|免于)[^\n]*工伤保险"],
                    "severity": "严重",
                    "description": "必须为劳动者缴纳工伤保险",
                    "legal_basis": "《工伤保险条例》第2条",
                    "suggestion": "必须为全部员工缴纳工伤保险"
                }
            ],
            "民事合同类": [
                {
                    "rule_id": "C001",
                    "name": "定金限额",
                    "patterns": [r"定金[^\d]*(\d+)\s*%"],
                    "severity": "警告",
                    "description": "定金不得超过合同标的额的20%",
                    "legal_basis": "《民法典》第586条：定金不得超过主合同标的额的20%",
                    "suggestion": "将定金金额调整至合同标的额的20%以内"
                },
                {
                    "rule_id": "C002",
                    "name": "违约金调整",
                    "patterns": [
                        r"违约金[^\d]*\d+\s*%[^\n]*\d+\s*%",
                        r"(?:任何|双方)[^\n]*违约金[^\n]*\d+\s*%"
                    ],
                    "severity": "警告",
                    "description": "违约金过分高于或低于损失可能面临调整",
                    "legal_basis": "《民法典》第585条",
                    "suggestion": "违约金应以实际损失为基准，不宜过高或过低"
                }
            ]
        }
    
    def _init_format_clause_rules(self) -> Dict:
        """初始化格式条款审查规则"""
        return {
            "invalid_format_clauses": [
                {
                    "rule_id": "F001",
                    "name": "不合理免责条款",
                    "patterns": [
                        r"(?:甲方|本公司|提供方)[^\n]*(?:免除|不承担|不负责)[^\n]*(?:任何|全部|所有)",
                        r"因[^\n]*(?:甲方|本公司)[^\n]*(?:造成|导致|引起)[^\n]*(?:免责|不负责)"
                    ],
                    "severity": "严重",
                    "description": "格式条款不合理地免除己方责任",
                    "legal_basis": "《民法典》第497条第2款",
                    "suggestion": "删除或修改该条款，确保双方权责对等"
                },
                {
                    "rule_id": "F002",
                    "name": "限制对方权利条款",
                    "patterns": [
                        r"(?:乙方|对方|客户)[^\n]*(?:不得|无权|不能)[^\n]*(?:主张|要求|请求)",
                        r"(?:甲方|本公司)[^\n]*(?:保留|享有)[^\n]*(?:随时|任意)[^\n]*(?:变更|修改|解除)"
                    ],
                    "severity": "严重",
                    "description": "格式条款限制对方主要权利",
                    "legal_basis": "《民法典》第497条第3款",
                    "suggestion": "修改条款，确保对方享有合理权利"
                },
                {
                    "rule_id": "F003",
                    "name": "单方面解释权",
                    "patterns": [
                        r"(?:甲方|本公司)[^\n]*(?:享有|拥有)[^\n]*(?:最终|绝对)[^\n]*(?:解释|决定)[^\n]*(?:权|效力)",
                        r"本合同[^\n]*(?:由|由)[^\n]*(?:甲方|本公司)[^\n]*(?:解释|说明)"
                    ],
                    "severity": "严重",
                    "description": "单方面保留解释权可能构成无效格式条款",
                    "legal_basis": "《民法典》第498条",
                    "suggestion": "删除该条款或改为双方协商解释"
                },
                {
                    "rule_id": "F004",
                    "name": "加重对方责任",
                    "patterns": [
                        r"(?:乙方|对方|客户)[^\n]*(?:必须|应当|需要)[^\n]*(?:承担|负责|赔偿)[^\n]*(?:任何|全部)",
                        r"无论[^\n]*(?:是否|有无)[^\n]*(?:违约|过失)[^\n]*(?:乙方|对方)[^\n]*(?:承担|负责)"
                    ],
                    "severity": "严重",
                    "description": "格式条款加重对方责任",
                    "legal_basis": "《民法典》第497条第2款",
                    "suggestion": "修改条款，确保责任分配公平合理"
                },
                {
                    "rule_id": "F005",
                    "name": "排除对方救济权利",
                    "patterns": [
                        r"(?:乙方|对方|客户)[^\n]*(?:放弃|放弃)[^\n]*(?:索赔|起诉|仲裁)",
                        r"不得[^\n]*(?:向|对)[^\n]*(?:法院|仲裁机构)[^\n]*(?:主张|请求)"
                    ],
                    "severity": "严重",
                    "description": "格式条款排除对方争议解决权利",
                    "legal_basis": "《民事诉讼法》第8条",
                    "suggestion": "删除该条款，保障对方合法救济权利"
                }
            ],
            "提醒注意条款": [
                {
                    "rule_id": "F006",
                    "name": "限制责任条款需提示",
                    "patterns": [
                        r"(?:免责|不承担责任|不负赔偿责任)"
                    ],
                    "severity": "提示",
                    "description": "免责条款应采取合理方式提示对方注意",
                    "legal_basis": "《民法典》第496条第2款",
                    "suggestion": "建议使用加粗、下划线等方式提示对方注意"
                }
            ]
        }
    
    def _check_mandatory_rules(self, text: str, clauses: List[Dict], 
                               contract_type: str) -> List[ComplianceIssue]:
        """检查强制性规定违反"""
        issues = []
        
        # 确定适用的规则类别
        if contract_type in ["劳动合同", "劳务合同"]:
            rule_category = "劳动类"
        else:
            rule_category = "民事合同类"
        
        rules = self.mandatory_rules.get(rule_category, [])
        
        for rule in rules:
            for pattern in rule["patterns"]:
                matches = re.finditer(pattern, text, re.IGNORECASE)
                for match in matches:
                    # 提取相关条款
                    clause_text = self._extract_relevant_clause(text, match.start())
                    
                    # 检查是否有限定词（如"不低于"）
                    context = text[max(0, match.start()-20):match.end()+20]
                    
                    issue = ComplianceIssue(
                        clause=self._find_clause_number(text, match.start()),
                        issue_type=rule["name"],
                        severity=rule["severity"],
                        problem=rule["description"],
                        legal_basis=rule["legal_basis"],
                        suggestion=rule["suggestion"],
                        regulation=f"规则编号: {rule['rule_id']}"
                    )
                    
                    # 检查是否有否定限定（如"不低于"是合法的）
                    if "不低于" in context or "高于" in context:
                        # 可能不是问题
                        if rule["rule_id"] not in ["L001"]:  # 最低工资是例外
                            continue
                    
                    issues.append(issue)
                    break  # 匹配一次即可
        
        return issues
    
    def _check_format_clauses(self, text: str, clauses: List[Dict],
                             contract_type: str) -> List[ComplianceIssue]:
        """检查格式条款问题"""
        issues = []
        
        all_rules = self.format_clause_rules.get("invalid_format_clauses", [])
        
        for rule in all_rules:
            for pattern in rule["patterns"]:
                matches = re.finditer(pattern, text, re.IGNORECASE)
                for match in matches:
                    issue = ComplianceIssue(
                        clause=self._find_clause_number(text, match.start()),
                        issue_type=rule["name"],
                        severity=rule["severity"],
                        problem=rule["description"],
                        legal_basis=rule["legal_basis"],
                        suggestion=rule["suggestion"],
                        regulation=f"规则编号: {rule['rule_id']}"
                    )
                    issues.append(issue)
                    break
        
        return issues
    
    def _check_pending_validity(self, text: str, clauses: List[Dict],
                                contract_type: str) -> List[ComplianceIssue]:
        """检查效力待定条款"""
        issues = []
        
        # 效力待定条款检测
        pending_patterns = [
            {
                "pattern": r"合同[^\n]*(?:经|待|尚)[^\n]*(?:批准|审批|授权|确认)",
                "issue_type": "待批准条款",
                "description": "合同或条款的效力取决于第三方批准"
            },
            {
                "pattern": r"(?:无权代理|表见代理|超越权限)[^\n]*(?:待确认)",
                "issue_type": "代理权限待确认",
                "description": "代理人权限不明确，效力待定"
            }
        ]
        
        for item in pending_patterns:
            matches = re.finditer(item["pattern"], text, re.IGNORECASE)
            for match in matches:
                issue = ComplianceIssue(
                    clause=self._find_clause_number(text, match.start()),
                    issue_type=item["issue_type"],
                    severity="警告",
                    problem=item["description"],
                    legal_basis="《民法典》第145条、第171条",
                    suggestion="建议明确代理权限或补充授权文件",
                    regulation=""
                )
                issues.append(issue)
        
        return issues
    
    def _check_jurisdiction(self, text: str, clauses: List[Dict],
                           contract_type: str) -> List[ComplianceIssue]:
        """检查管辖约定"""
        issues = []
        
        # 管辖条款检测
        jurisdiction_patterns = [
            {
                "pattern": r"提交[^\n]*(?:仲裁|诉讼)[^\n]*(?:委员会|法院)",
                "issue_type": "管辖机构不明确",
                "description": "未明确具体的仲裁机构或法院名称"
            },
            {
                "pattern": r"(?:仅能|只能|只能|应当)[^\n]*(?:向|到)[^\n]*(?:仲裁|诉讼)",
                "issue_type": "排除法定管辖",
                "description": "约定排除法定管辖权可能无效"
            }
        ]
        
        for item in jurisdiction_patterns:
            matches = re.finditer(item["pattern"], text, re.IGNORECASE)
            for match in matches:
                issue = ComplianceIssue(
                    clause=self._find_clause_number(text, match.start()),
                    issue_type=item["issue_type"],
                    severity="警告",
                    problem=item["description"],
                    legal_basis="《民事诉讼法》第34条",
                    suggestion="建议明确约定具体的仲裁委员会或管辖法院",
                    regulation=""
                )
                issues.append(issue)
        
        return issues
    
    def _extract_relevant_clause(self, text: str, position: int) -> str:
        """提取相关条款内容"""
        # 向前向后各取200字符
        start = max(0, position - 200)
        end = min(len(text), position + 200)
        return text[start:end]
    
    def _find_clause_number(self, text: str, position: int) -> str:
        """查找条款编号"""
        # 在位置前后查找条款编号
        search_text = text[max(0, position-300):min(len(text), position+100)]
        match = re.search(r'第[零一二三四五六七八九十百\d]+条', search_text)
        if match:
            return match.group(0)
        return "相关条款"
    
    def _calculate_compliance_score(self, issues: Dict) -> float:
        """计算合规评分"""
        total_issues = (
            len(issues["mandatory_violations"]) +
            len(issues["format_clause_issues"]) +
            len(issues["pending_validity"]) +
            len(issues["jurisdiction_issues"])
        )
        
        if total_issues == 0:
            return 100.0
        
        # 扣分计算
        deductions = 0.0
        
        # 严重问题每个扣20分
        severe_count = sum(1 for issue in (
            issues["mandatory_violations"] + 
            issues["format_clause_issues"] + 
            issues["pending_validity"] + 
            issues["jurisdiction_issues"]
        ) if getattr(issue, 'severity', '') == "严重")
        deductions += severe_count * 20
        
        # 警告问题每个扣10分
        warning_count = sum(1 for issue in (
            issues["mandatory_violations"] + 
            issues["format_clause_issues"] + 
            issues["pending_validity"] + 
            issues["jurisdiction_issues"]
        ) if getattr(issue, 'severity', '') == "警告")
        deductions += warning_count * 10
        
        # 提示问题每个扣5分
        tip_count = sum(1 for issue in (
            issues["mandatory_violations"] + 
            issues["format_clause_issues"] + 
            issues["pending_validity"] + 
            issues["jurisdiction_issues"]
        ) if getattr(issue, 'severity', '') == "提示")
        deductions += tip_count * 5
        
        score = max(0.0, 100.0 - deductions)
        return round(score, 1)


def main():
    """测试函数"""
    from scripts.clause_extraction import ClauseExtractor
    
    extractor = ClauseExtractor()
    checker = ComplianceChecker()
    
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
    甲方有权要求乙方加班，乙方应无条件服从，加关费按正常工资的80%计算。
    
    第十二条 争议解决
    因本合同引起的争议，提交甲方所在地仲裁委员会仲裁。
    """
    
    clauses_data = extractor.extract(test_contract, "劳动合同")
    result = checker.check(test_contract, clauses_data, "劳动合同")
    
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
