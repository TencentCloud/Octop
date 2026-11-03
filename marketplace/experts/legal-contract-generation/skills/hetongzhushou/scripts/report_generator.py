"""
报告生成脚本
Report Generator Script

功能：生成结构化合同审查报告
支持多种输出格式：JSON、Markdown、Text、HTML
"""

import json
import datetime
from typing import Dict, List, Optional, Any
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))


class ReportGenerator:
    """报告生成器"""
    
    def __init__(self):
        self.template_dir = Path(__file__).parent.parent / "templates"
    
    def generate(self, review_result: Dict, 
                output_path: Optional[str] = None,
                format: str = "markdown") -> str:
        """
        生成审查报告
        
        Args:
            review_result: 审查结果
            output_path: 输出文件路径
            format: 输出格式 (json/markdown/text/html)
            
        Returns:
            报告文本
        """
        if format == "json":
            return self._generate_json(review_result)
        elif format == "markdown":
            return self._generate_markdown(review_result)
        elif format == "html":
            return self._generate_html(review_result)
        else:
            return self._generate_text(review_result)
    
    def _generate_json(self, result: Dict) -> str:
        """生成JSON格式报告"""
        return json.dumps(result, ensure_ascii=False, indent=2)
    
    def _generate_markdown(self, result: Dict) -> str:
        """生成Markdown格式报告"""
        lines = []
        
        # 标题
        lines.append("# 📋 合同智能审查报告")
        lines.append("")
        lines.append(f"**生成时间**: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append(f"**合同类型**: {result.get('contract_type', '未知')}")
        lines.append("")
        lines.append("---")
        lines.append("")
        
        # 综合评级
        rating = result.get("overall_rating", "未知")
        rating_emoji = {
            "高危": "🔴",
            "中危": "🟡",
            "低危": "🟢"
        }.get(rating, "⚪")
        
        lines.append(f"## {rating_emoji} 综合风险评级: {rating}")
        lines.append("")
        
        # 风险摘要
        risks_summary = result.get("risks_summary", {})
        lines.append("### 📊 风险统计")
        lines.append("")
        lines.append("| 风险等级 | 数量 |")
        lines.append("|---------|------|")
        lines.append(f"| 🔴 高风险 | {risks_summary.get('high_risk_count', 0)} |")
        lines.append(f"| 🟡 中风险 | {risks_summary.get('medium_risk_count', 0)} |")
        lines.append(f"| 🟢 低风险 | {risks_summary.get('low_risk_count', 0)} |")
        lines.append("")
        
        # 合规摘要
        compliance_summary = result.get("compliance_summary", {})
        lines.append("### ⚖️ 合规检查摘要")
        lines.append("")
        lines.append(f"- 合规评分: **{result.get('phases', {}).get('compliance_check', {}).get('compliance_score', 100)}分**")
        lines.append(f"- 存在问题: **{compliance_summary.get('total_issues', 0)}项**")
        lines.append(f"- 强制性规定违反: **{compliance_summary.get('mandatory_violations', 0)}项**")
        lines.append(f"- 格式条款问题: **{compliance_summary.get('format_clause_issues', 0)}项**")
        lines.append("")
        
        # 风险详情
        phases = result.get("phases", {})
        risk_data = phases.get("risk_detection", {})
        high_risks = risk_data.get("high_risk", [])
        medium_risks = risk_data.get("medium_risk", [])
        
        if high_risks:
            lines.append("---")
            lines.append("")
            lines.append("## 🔴 高风险条款 (需重点关注)")
            lines.append("")
            for risk in high_risks:
                lines.append(f"### {risk.get('clause', '条款')} - {risk.get('risk_type', '')}")
                lines.append("")
                lines.append(f"**风险等级**: 🔴 高")
                lines.append("")
                lines.append(f"**问题分析**:")
                lines.append(f"> {risk.get('problem', '无')}")
                lines.append("")
                if risk.get('legal_basis'):
                    lines.append(f"**法律依据**:")
                    lines.append(f"> 📜 {risk.get('legal_basis', '')}")
                    lines.append("")
                lines.append(f"**修改建议**:")
                lines.append(f"> ✏️ {risk.get('suggestion', '无')}")
                lines.append("")
                lines.append(f"**严重程度**: {risk.get('severity_score', 0)}/10")
                lines.append("")
                lines.append("---")
                lines.append("")
        
        if medium_risks:
            lines.append("")
            lines.append("## 🟡 中风险条款")
            lines.append("")
            for risk in medium_risks:
                lines.append(f"### {risk.get('clause', '条款')} - {risk.get('risk_type', '')}")
                lines.append("")
                lines.append(f"**风险等级**: 🟡 中")
                lines.append("")
                lines.append(f"**问题分析**: {risk.get('problem', '无')}")
                lines.append("")
                lines.append(f"**修改建议**: {risk.get('suggestion', '无')}")
                lines.append("")
        
        # 合规问题详情
        compliance_data = phases.get("compliance_check", {})
        compliance_issues = compliance_data.get("mandatory_violations", []) + \
                           compliance_data.get("format_clause_issues", [])
        
        if compliance_issues:
            lines.append("")
            lines.append("## ⚠️ 合规问题")
            lines.append("")
            for issue in compliance_issues:
                lines.append(f"### {issue.get('clause', '条款')} - {issue.get('issue_type', '')}")
                lines.append("")
                lines.append(f"**严重程度**: {issue.get('severity', '警告')}")
                lines.append("")
                lines.append(f"**法律依据**: {issue.get('legal_basis', '无')}")
                lines.append("")
                lines.append(f"**建议**: {issue.get('suggestion', '无')}")
                lines.append("")
        
        # 条款亮点
        lines.append("")
        lines.append("## ✅ 条款亮点")
        lines.append("")
        lines.append("以下条款设计合理，符合法律规定：")
        lines.append("")
        clauses_data = phases.get("clause_extraction", {})
        clauses = clauses_data.get("clauses", [])
        
        # 简单列出提取的条款
        for clause in clauses[:5]:
            lines.append(f"- {clause.get('clause_number', '')} {clause.get('clause_title', clause.get('clause_type', ''))}")
        
        lines.append("")
        lines.append("---")
        lines.append("")
        lines.append("## 📌 总结与建议")
        lines.append("")
        
        # 生成总结
        if result.get("overall_rating") == "高危":
            lines.append("⚠️ **本份合同存在较高法律风险，建议在签署前与对方协商修改以下条款：**")
            for risk in high_risks[:3]:
                lines.append(f"1. {risk.get('clause', '')} {risk.get('risk_type', '')}")
        elif result.get("overall_rating") == "中危":
            lines.append("💡 **本份合同存在一定风险，建议关注以下条款并视情况进行协商：**")
            for risk in medium_risks[:3]:
                lines.append(f"1. {risk.get('clause', '')} {risk.get('risk_type', '')}")
        else:
            lines.append("✅ **本份合同整体风险较低，可正常签署使用。**")
        
        lines.append("")
        lines.append(f"*报告生成时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*")
        lines.append("*本报告仅供参考，具体法律问题请咨询专业律师。*")
        
        return "\n".join(lines)
    
    def _generate_text(self, result: Dict) -> str:
        """生成纯文本格式报告"""
        lines = []
        
        lines.append("=" * 60)
        lines.append("           合同智能审查报告")
        lines.append("=" * 60)
        lines.append("")
        lines.append(f"合同类型: {result.get('contract_type', '未知')}")
        lines.append(f"综合评级: {result.get('overall_rating', '未知')}")
        lines.append(f"生成时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append("")
        lines.append("-" * 60)
        
        # 风险摘要
        risks_summary = result.get("risks_summary", {})
        lines.append("")
        lines.append("【风险统计】")
        lines.append(f"  高风险: {risks_summary.get('high_risk_count', 0)} 项")
        lines.append(f"  中风险: {risks_summary.get('medium_risk_count', 0)} 项")
        lines.append(f"  低风险: {risks_summary.get('low_risk_count', 0)} 项")
        
        # 风险详情
        phases = result.get("phases", {})
        risk_data = phases.get("risk_detection", {})
        high_risks = risk_data.get("high_risk", [])
        
        if high_risks:
            lines.append("")
            lines.append("【高风险条款】")
            for risk in high_risks:
                lines.append("")
                lines.append(f"  条款: {risk.get('clause', '')}")
                lines.append(f"  风险: {risk.get('risk_type', '')}")
                lines.append(f"  问题: {risk.get('problem', '')}")
                lines.append(f"  建议: {risk.get('suggestion', '')}")
        
        lines.append("")
        lines.append("-" * 60)
        lines.append("报告完毕")
        lines.append("=" * 60)
        
        return "\n".join(lines)
    
    def _generate_html(self, result: Dict) -> str:
        """生成HTML格式报告"""
        markdown = self._generate_markdown(result)
        
        # 简单的Markdown转HTML
        html = markdown.replace("# ", "<h1>").replace("## ", "<h2>").replace("### ", "<h3>")
        html = html.replace("\n\n", "</p><p>")
        html = html.replace("\n", "<br>")
        
        html = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>合同审查报告</title>
    <style>
        body {{ font-family: Arial, sans-serif; max-width: 800px; margin: 0 auto; padding: 20px; }}
        h1 {{ color: #333; border-bottom: 2px solid #333; }}
        h2 {{ color: #555; }}
        h3 {{ color: #777; }}
        table {{ border-collapse: collapse; width: 100%; }}
        td, th {{ border: 1px solid #ddd; padding: 8px; }}
        .high-risk {{ color: #d32f2f; }}
        .medium-risk {{ color: #f57c00; }}
        .low-risk {{ color: #388e3c; }}
    </style>
</head>
<body>
    <p>{html}</p>
</body>
</html>
"""
        return html
    
    def export_to_file(self, content: str, output_path: str, 
                      format: str = "markdown") -> bool:
        """
        导出报告到文件
        
        Args:
            content: 报告内容
            output_path: 输出文件路径
            format: 文件格式
            
        Returns:
            是否成功
        """
        try:
            # 根据格式确定文件扩展名
            extension_map = {
                "json": ".json",
                "markdown": ".md",
                "html": ".html",
                "text": ".txt"
            }
            
            extension = extension_map.get(format, ".txt")
            if not output_path.endswith(extension):
                output_path = output_path + extension
            
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(content)
            
            return True
        except Exception as e:
            print(f"导出失败: {e}")
            return False


def main():
    """测试函数"""
    from scripts.clause_extraction import ClauseExtractor
    from scripts.risk_detection import RiskDetector
    from scripts.compliance_check import ComplianceChecker
    
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
    
    extractor = ClauseExtractor()
    detector = RiskDetector()
    checker = ComplianceChecker()
    
    clauses_data = extractor.extract(test_contract, "劳动合同")
    review_result = {
        "contract_type": "劳动合同",
        "overall_rating": "高危",
        "phases": {
            "clause_extraction": clauses_data,
            "risk_detection": detector.detect(clauses_data, "劳动合同"),
            "compliance_check": checker.check(test_contract, clauses_data, "劳动合同")
        },
        "risks_summary": {},
        "compliance_summary": {}
    }
    
    # 计算摘要
    risks_summary = {
        "high_risk_count": len(review_result["phases"]["risk_detection"].get("high_risk", [])),
        "medium_risk_count": len(review_result["phases"]["risk_detection"].get("medium_risk", [])),
        "low_risk_count": len(review_result["phases"]["risk_detection"].get("low_risk", []))
    }
    review_result["risks_summary"] = risks_summary
    
    compliance_summary = {
        "total_issues": len(review_result["phases"]["compliance_check"].get("issues", [])),
        "mandatory_violations": len(review_result["phases"]["compliance_check"].get("mandatory_violations", [])),
        "format_clause_issues": len(review_result["phases"]["compliance_check"].get("format_clause_issues", []))
    }
    review_result["compliance_summary"] = compliance_summary
    
    generator = ReportGenerator()
    
    # 生成Markdown报告
    print("=== Markdown格式报告预览 ===")
    print(generator.generate(review_result, format="markdown")[:2000])
    print("...")


if __name__ == "__main__":
    main()
