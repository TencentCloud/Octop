"""
对比分析脚本
Comparison Analysis Script

功能：对比两个版本合同的差异
支持条款级别对比、变更类型识别、风险变更分析
"""

import re
import json
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, asdict
from enum import Enum
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))


class ChangeType(Enum):
    """变更类型"""
    ADDED = "added"           # 新增
    REMOVED = "removed"       # 删除
    MODIFIED = "modified"     # 修改
    UNCHANGED = "unchanged"   # 未变更


@dataclass
class ClauseDiff:
    """条款差异"""
    clause_id: str
    clause_title: str
    change_type: str
    old_content: Optional[str]
    new_content: Optional[str]
    diff_summary: str
    risk_impact: str  # positive, negative, neutral


@dataclass
class ComparisonReport:
    """对比报告"""
    total_changes: int
    additions: int
    removals: int
    modifications: int
    clause_diffs: List[ClauseDiff]
    risk_summary: Dict[str, Any]
    overall_assessment: str


class ContractComparator:
    """合同对比器"""
    
    def __init__(self):
        self.risk_keywords = self._init_risk_keywords()
    
    def compare(self, old_contract: str, new_contract: str,
                contract_type: str = "auto") -> ComparisonReport:
        """
        对比两个版本的合同
        
        Args:
            old_contract: 旧版合同文本
            new_contract: 新版合同文本
            contract_type: 合同类型
            
        Returns:
            对比报告
        """
        # 提取条款
        old_clauses = self._extract_clauses(old_contract)
        new_clauses = self._extract_clauses(new_contract)
        
        # 进行对比
        clause_diffs = self._compare_clauses(old_clauses, new_clauses)
        
        # 统计变更
        stats = self._calculate_stats(clause_diffs)
        
        # 分析风险变更
        risk_summary = self._analyze_risk_changes(clause_diffs)
        
        # 生成总体评估
        assessment = self._generate_assessment(clause_diffs, risk_summary)
        
        return ComparisonReport(
            total_changes=stats["total"],
            additions=stats["additions"],
            removals=stats["removals"],
            modifications=stats["modifications"],
            clause_diffs=clause_diffs,
            risk_summary=risk_summary,
            overall_assessment=assessment
        )
    
    def _extract_clauses(self, text: str) -> Dict[str, Dict]:
        """提取合同条款"""
        clauses = {}
        
        # 按条款编号提取
        clause_pattern = r'第([零一二三四五六七八九十百\d]+)条\s*([^\n：:]+)?[：:]?\s*\n?(.*?)(?=(?:第[零一二三四五六七八九十百\d]+条)|$)'
        
        matches = re.finditer(clause_pattern, text, re.DOTALL)
        for match in matches:
            clause_num = match.group(1)
            clause_title = match.group(2).strip() if match.group(2) else ""
            clause_content = match.group(3).strip()
            
            # 标准化条款ID
            clause_id = f"第{self._normalize_number(clause_num)}条"
            
            clauses[clause_id] = {
                "id": clause_id,
                "title": clause_title,
                "content": clause_content,
                "raw": match.group(0)
            }
        
        # 如果没有条款结构，按段落提取
        if not clauses:
            paragraphs = [p.strip() for p in text.split('\n') if p.strip() and len(p.strip()) > 20]
            for i, para in enumerate(paragraphs):
                clause_id = f"条款{i+1}"
                clauses[clause_id] = {
                    "id": clause_id,
                    "title": "",
                    "content": para,
                    "raw": para
                }
        
        return clauses
    
    def _normalize_number(self, num_str: str) -> str:
        """标准化中文数字"""
        mapping = {
            '零': '0', '一': '1', '二': '2', '三': '3', '四': '4',
            '五': '5', '六': '6', '七': '7', '八': '8', '九': '9', '十': '10'
        }
        
        if num_str in mapping:
            return mapping[num_str]
        
        # 处理复合数字
        result = num_str
        for cn, num in mapping.items():
            result = result.replace(cn, num)
        
        return result
    
    def _compare_clauses(self, old_clauses: Dict, 
                         new_clauses: Dict) -> List[ClauseDiff]:
        """对比条款差异"""
        diffs = []
        
        # 收集所有条款ID
        all_ids = set(old_clauses.keys()) | set(new_clauses.keys())
        
        for clause_id in sorted(all_ids, key=self._sort_clause_id):
            old_clause = old_clauses.get(clause_id)
            new_clause = new_clauses.get(clause_id)
            
            if old_clause and not new_clause:
                # 被删除的条款
                diffs.append(ClauseDiff(
                    clause_id=clause_id,
                    clause_title=old_clause.get("title", ""),
                    change_type=ChangeType.REMOVED.value,
                    old_content=old_clause.get("content", ""),
                    new_content=None,
                    diff_summary=f"删除了「{clause_id}」条款",
                    risk_impact=self._assess_risk_of_removal(old_clause.get("content", ""))
                ))
            
            elif new_clause and not old_clause:
                # 新增的条款
                diffs.append(ClauseDiff(
                    clause_id=clause_id,
                    clause_title=new_clause.get("title", ""),
                    change_type=ChangeType.ADDED.value,
                    old_content=None,
                    new_content=new_clause.get("content", ""),
                    diff_summary=f"新增了「{clause_id}」条款",
                    risk_impact=self._assess_risk_of_addition(new_clause.get("content", ""))
                ))
            
            elif old_clause and new_clause:
                old_content = old_clause.get("content", "")
                new_content = new_clause.get("content", "")
                
                if old_content != new_content:
                    # 内容有修改
                    diff_details = self._analyze_content_diff(
                        old_content, new_content, clause_id
                    )
                    
                    diffs.append(ClauseDiff(
                        clause_id=clause_id,
                        clause_title=new_clause.get("title", ""),
                        change_type=ChangeType.MODIFIED.value,
                        old_content=old_content,
                        new_content=new_content,
                        diff_summary=diff_details["summary"],
                        risk_impact=diff_details["risk_impact"]
                    ))
        
        return diffs
    
    def _analyze_content_diff(self, old_content: str, new_content: str,
                             clause_id: str) -> Dict[str, str]:
        """分析内容差异"""
        details = {
            "summary": "",
            "risk_impact": "neutral"
        }
        
        changes = []
        
        # 检测金额变化
        old_amounts = re.findall(r'(\d+(?:\.\d+)?)\s*(?:万|亿|元|%)', old_content)
        new_amounts = re.findall(r'(\d+(?:\.\d+)?)\s*(?:万|亿|元|%)', new_content)
        
        if old_amounts and new_amounts:
            old_val = float(old_amounts[0])
            new_val = float(new_amounts[0])
            if new_val > old_val:
                changes.append("金额增加")
            elif new_val < old_val:
                changes.append("金额减少")
        
        # 检测期限变化
        old_periods = re.findall(r'(\d+)\s*(?:年|个月?|日)', old_content)
        new_periods = re.findall(r'(\d+)\s*(?:年|个月?|日)', new_content)
        
        if old_periods and new_periods:
            old_val = int(old_periods[0])
            new_val = int(new_periods[0])
            if new_val > old_val:
                changes.append("期限延长")
            elif new_val < old_val:
                changes.append("期限缩短")
        
        # 检测关键词变化
        risk_keywords = ["违约金", "违约责任", "无条件", "不得", "必须", "应当"]
        for kw in risk_keywords:
            old_has = kw in old_content
            new_has = kw in new_content
            
            if new_has and not old_has:
                changes.append(f"新增「{kw}」")
            elif old_has and not new_has:
                changes.append(f"删除「{kw}」")
        
        if changes:
            details["summary"] = f"修改内容：{'；'.join(changes)}"
        else:
            details["summary"] = "内容有修改，具体变更需查看详情"
        
        # 评估风险影响
        details["risk_impact"] = self._assess_risk_of_change(
            old_content, new_content, changes
        )
        
        return details
    
    def _assess_risk_of_removal(self, content: str) -> str:
        """评估删除条款的风险影响"""
        negative_keywords = ["保密", "竞业", "限制", "保护", "权益", "赔偿"]
        positive_keywords = ["违约金", "无条件", "强制"]
        
        content_lower = content.lower()
        
        neg_count = sum(1 for kw in negative_keywords if kw in content)
        pos_count = sum(1 for kw in positive_keywords if kw in content)
        
        if neg_count > pos_count:
            return "negative"  # 删除保护性条款，风险增加
        elif pos_count > neg_count:
            return "positive"  # 删除限制性条款，风险降低
        else:
            return "neutral"
    
    def _assess_risk_of_addition(self, content: str) -> str:
        """评估新增条款的风险影响"""
        positive_keywords = ["保密", "竞业", "保护", "权益", "赔偿"]
        negative_keywords = ["违约金", "无条件", "强制", "不得", "必须"]
        
        pos_count = sum(1 for kw in positive_keywords if kw in content)
        neg_count = sum(1 for kw in negative_keywords if kw in content)
        
        if neg_count > pos_count:
            return "negative"  # 新增限制性条款，风险增加
        elif pos_count > neg_count:
            return "positive"  # 新增保护性条款，风险降低
        else:
            return "neutral"
    
    def _assess_risk_of_change(self, old_content: str, new_content: str,
                               changes: List[str]) -> str:
        """评估修改条款的风险影响"""
        # 统计风险关键词变化
        risk_keywords = ["违约金", "无条件", "强制", "不得", "必须", "应当"]
        
        old_count = sum(1 for kw in risk_keywords if kw in old_content)
        new_count = sum(1 for kw in risk_keywords if kw in new_content)
        
        if new_count > old_count:
            return "negative"  # 限制性内容增加
        elif new_count < old_count:
            return "positive"  # 限制性内容减少
        
        # 检查具体变化
        for change in changes:
            if any(x in change for x in ["增加", "延长", "新增限制"]):
                return "negative"
            elif any(x in change for x in ["减少", "缩短", "删除限制"]):
                return "positive"
        
        return "neutral"
    
    def _calculate_stats(self, diffs: List[ClauseDiff]) -> Dict[str, int]:
        """统计变更"""
        stats = {
            "total": len(diffs),
            "additions": 0,
            "removals": 0,
            "modifications": 0
        }
        
        for diff in diffs:
            if diff.change_type == ChangeType.ADDED.value:
                stats["additions"] += 1
            elif diff.change_type == ChangeType.REMOVED.value:
                stats["removals"] += 1
            elif diff.change_type == ChangeType.MODIFIED.value:
                stats["modifications"] += 1
        
        return stats
    
    def _analyze_risk_changes(self, diffs: List[ClauseDiff]) -> Dict[str, Any]:
        """分析风险变更"""
        positive_count = sum(1 for d in diffs if d.risk_impact == "positive")
        negative_count = sum(1 for d in diffs if d.risk_impact == "negative")
        neutral_count = sum(1 for d in diffs if d.risk_impact == "neutral")
        
        negative_diffs = [d for d in diffs if d.risk_impact == "negative"]
        positive_diffs = [d for d in diffs if d.risk_impact == "positive"]
        
        return {
            "risk_increased": negative_count,
            "risk_decreased": positive_count,
            "risk_unchanged": neutral_count,
            "negative_changes": [asdict(d) for d in negative_diffs],
            "positive_changes": [asdict(d) for d in positive_diffs]
        }
    
    def _generate_assessment(self, diffs: List[ClauseDiff],
                            risk_summary: Dict) -> str:
        """生成总体评估"""
        if not diffs:
            return "合同内容无变更"
        
        assessment_parts = []
        
        # 整体变更数量
        if risk_summary["risk_increased"] > risk_summary["risk_decreased"]:
            assessment_parts.append("⚠️ 合同变更后整体风险有所增加")
        elif risk_summary["risk_increased"] < risk_summary["risk_decreased"]:
            assessment_parts.append("✅ 合同变更后整体风险有所降低")
        else:
            assessment_parts.append("📊 合同变更后整体风险基本持平")
        
        # 具体问题
        negative_diffs = risk_summary.get("negative_changes", [])
        if negative_diffs:
            assessment_parts.append(f"\n⚠️ 需要关注的风险变更（{len(negative_diffs)}项）：")
            for diff in negative_diffs[:3]:  # 最多显示3个
                assessment_parts.append(f"  • {diff['clause_id']}：{diff['diff_summary']}")
        
        return "\n".join(assessment_parts)
    
    def _init_risk_keywords(self) -> Dict:
        """初始化风险关键词"""
        return {
            "increase_risk": ["违约金", "无条件", "强制", "不得", "必须", "应当", "全权"],
            "decrease_risk": ["保密", "竞业", "保护", "权益", "赔偿", "补偿", "不得擅自"]
        }
    
    def _sort_clause_id(self, clause_id: str) -> Tuple:
        """条款排序"""
        # 提取数字
        match = re.search(r'\d+', clause_id)
        if match:
            return (0, int(match.group()))
        return (1, clause_id)
    
    def generate_diff_markdown(self, report: ComparisonReport) -> str:
        """生成Markdown格式的对比报告"""
        lines = [
            "# 合同对比分析报告",
            "",
            f"**总变更数**: {report.total_changes} | "
            f"新增: {report.additions} | "
            f"删除: {report.removals} | "
            f"修改: {report.modifications}",
            ""
        ]
        
        # 风险摘要
        lines.extend([
            "## 风险变更摘要",
            "",
            f"- ⚠️ 风险增加: {report.risk_summary['risk_increased']}项",
            f"- ✅ 风险降低: {report.risk_summary['risk_decreased']}项",
            f"- 📊 风险不变: {report.risk_summary['risk_unchanged']}项",
            ""
        ])
        
        # 变更详情
        lines.extend([
            "## 变更详情",
            ""
        ])
        
        for diff in report.clause_diffs:
            icon = {
                "added": "➕",
                "removed": "➖",
                "modified": "✏️",
                "unchanged": "➡️"
            }.get(diff.change_type, "•")
            
            lines.append(f"### {icon} {diff.clause_id} {diff.clause_title}")
            lines.append(f"**变更类型**: {diff.change_type}")
            lines.append(f"**影响**: {diff.risk_impact}")
            lines.append("")
            
            if diff.old_content:
                lines.append("**原内容**:")
                lines.append(f"```\n{diff.old_content[:300]}...\n```")
                lines.append("")
            
            if diff.new_content:
                lines.append("**新内容**:")
                lines.append(f"```\n{diff.new_content[:300]}...\n```")
                lines.append("")
            
            if diff.diff_summary:
                lines.append(f"**说明**: {diff.diff_summary}")
            
            lines.append("---")
            lines.append("")
        
        # 总体评估
        lines.extend([
            "## 总体评估",
            "",
            report.overall_assessment
        ])
        
        return "\n".join(lines)


def main():
    """测试函数"""
    comparator = ContractComparator()
    
    # 测试用合同
    old_contract = """
    劳动合同
    
    第三条 工作内容
    乙方同意在技术部门担任工程师。
    
    第五条 薪酬待遇
    乙方的月工资为税前25000元。
    
    第七条 竞业限制
    乙方离职后一年内不得在同类行业从事相关工作。
    
    第九条 违约责任
    违约方需支付违约金10000元。
    """
    
    new_contract = """
    劳动合同
    
    第三条 工作内容
    乙方同意在技术部门担任高级工程师。
    
    第五条 薪酬待遇
    乙方的月工资为税前28000元。
    
    第六条 保密条款
    乙方应当保守在工作期间知悉的商业秘密。
    
    第七条 竞业限制
    乙方离职后两年内不得在同类行业从事相关工作，违约金50万元。
    
    第九条 违约责任
    任何一方违约需支付违约金20000元。
    """
    
    report = comparator.compare(old_contract, new_contract)
    
    print("=== 对比报告 ===")
    print(f"总变更数: {report.total_changes}")
    print(f"新增: {report.additions}")
    print(f"删除: {report.removals}")
    print(f"修改: {report.modifications}")
    print()
    
    print("=== Markdown格式报告 ===")
    print(comparator.generate_diff_markdown(report))


if __name__ == "__main__":
    main()
