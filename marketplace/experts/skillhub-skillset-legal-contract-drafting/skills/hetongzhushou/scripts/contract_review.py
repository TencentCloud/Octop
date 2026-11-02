"""
合同智能审查主脚本
Contract Review Main Script

功能：合同智能审查主入口，整合条款提取、风险检测、合规检查等核心能力
用法：python scripts/contract_review.py --input <合同文本文件或内容> --type <合同类型> --output <输出路径>
"""

import json
import re
import sys
import argparse
from typing import Dict, List, Optional, Any
from pathlib import Path

# 添加父目录到路径以便导入模块
sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.clause_extraction import ClauseExtractor
from scripts.risk_detection import RiskDetector
from scripts.compliance_check import ComplianceChecker
from scripts.report_generator import ReportGenerator


class ContractReviewer:
    """合同审查器主类"""
    
    def __init__(self, contract_type: Optional[str] = None):
        self.contract_type = contract_type
        self.clause_extractor = ClauseExtractor()
        self.risk_detector = RiskDetector()
        self.compliance_checker = ComplianceChecker()
        self.report_generator = ReportGenerator()
        
    def review(self, contract_text: str) -> Dict[str, Any]:
        """
        执行完整合同审查流程
        
        Args:
            contract_text: 合同文本内容
            
        Returns:
            审查结果字典，包含综合评级、风险列表、合规问题等
        """
        result = {
            "status": "success",
            "phases": {}
        }
        
        # 阶段一：合同识别
        if not self.contract_type:
            self.contract_type = self._identify_contract_type(contract_text)
        result["contract_type"] = self.contract_type
        
        # 阶段二：条款提取
        clauses = self.clause_extractor.extract(contract_text, self.contract_type)
        result["phases"]["clause_extraction"] = clauses
        
        # 阶段三：风险扫描
        risks = self.risk_detector.detect(clauses, self.contract_type)
        result["phases"]["risk_detection"] = risks
        
        # 阶段四：合规检查
        compliance = self.compliance_checker.check(contract_text, clauses, self.contract_type)
        result["phases"]["compliance_check"] = compliance
        
        # 阶段五：综合评级
        result["overall_rating"] = self._calculate_overall_rating(risks, compliance)
        result["risks_summary"] = self._summarize_risks(risks)
        result["compliance_summary"] = self._summarize_compliance(compliance)
        
        return result
    
    def _identify_contract_type(self, text: str) -> str:
        """识别合同类型"""
        # 常见合同类型关键词
        type_patterns = {
            "劳动合同": ["劳动合同", "甲方", "乙方", "工作内容", "劳动报酬", "社会保险"],
            "买卖合同": ["买卖", "买方", "卖方", "标的物", "货款", "交货"],
            "租赁合同": ["租赁", "出租方", "承租方", "租金", "租赁物", "押金"],
            "服务合同": ["服务", "委托", "受托", "服务费", "服务内容"],
            "借款合同": ["借款", "借款人", "出借人", "借款金额", "利率", "还款"],
            "技术合同": ["技术", "开发", "转让", "许可", "知识产权", "成果"]
        }
        
        scores = {}
        for contract_type, keywords in type_patterns.items():
            score = sum(1 for kw in keywords if kw in text)
            scores[contract_type] = score
        
        # 返回得分最高的类型
        max_type = max(scores, key=scores.get)
        if scores[max_type] > 0:
            return max_type
        return "未知类型合同"
    
    def _calculate_overall_rating(self, risks: Dict, compliance: Dict) -> str:
        """计算综合风险评级"""
        high_risk_count = len(risks.get("high_risk", []))
        medium_risk_count = len(risks.get("medium_risk", []))
        compliance_issues = len(compliance.get("issues", []))
        
        # 高危/中危/低危评级
        if high_risk_count > 0 or compliance_issues > 2:
            return "高危"
        elif medium_risk_count > 0 or compliance_issues > 0:
            return "中危"
        else:
            return "低危"
    
    def _summarize_risks(self, risks: Dict) -> Dict:
        """汇总风险信息"""
        return {
            "high_risk_count": len(risks.get("high_risk", [])),
            "medium_risk_count": len(risks.get("medium_risk", [])),
            "low_risk_count": len(risks.get("low_risk", [])),
            "total_risk_count": len(risks.get("high_risk", [])) + 
                              len(risks.get("medium_risk", [])) + 
                              len(risks.get("low_risk", []))
        }
    
    def _summarize_compliance(self, compliance: Dict) -> Dict:
        """汇总合规信息"""
        return {
            "total_issues": len(compliance.get("issues", [])),
            "mandatory_violations": len(compliance.get("mandatory_violations", [])),
            "format_clause_issues": len(compliance.get("format_clause_issues", [])),
            "pending_validity": len(compliance.get("pending_validity", []))
        }
    
    def generate_report(self, result: Dict, output_path: Optional[str] = None) -> str:
        """
        生成结构化审查报告
        
        Args:
            result: 审查结果
            output_path: 输出文件路径（可选）
            
        Returns:
            报告文本内容
        """
        return self.report_generator.generate(result, output_path)


def parse_arguments():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(
        description="合同智能审查工具 - 智能识别合同类型、提取条款、检测风险、检查合规性"
    )
    parser.add_argument(
        "--input", "-i",
        type=str,
        help="合同文本内容或文件路径"
    )
    parser.add_argument(
        "--type", "-t",
        type=str,
        choices=["劳动合同", "买卖合同", "租赁合同", "服务合同", "借款合同", "技术合同", "auto"],
        default="auto",
        help="合同类型（auto表示自动识别）"
    )
    parser.add_argument(
        "--output", "-o",
        type=str,
        help="输出报告文件路径（可选）"
    )
    parser.add_argument(
        "--format", "-f",
        type=str,
        choices=["json", "markdown", "text"],
        default="markdown",
        help="输出格式"
    )
    parser.add_argument(
        "--file",
        type=str,
        help="从文件读取合同内容"
    )
    return parser.parse_args()


def main():
    """主函数"""
    args = parse_arguments()
    
    # 获取合同文本
    if args.file:
        with open(args.file, "r", encoding="utf-8") as f:
            contract_text = f.read()
    elif args.input:
        contract_text = args.input
    else:
        print("错误：请提供合同文本内容（--input）或合同文件路径（--file）")
        sys.exit(1)
    
    # 确定合同类型
    contract_type = None if args.type == "auto" else args.type
    
    # 执行审查
    print("🔍 合同智能审查系统启动...")
    print(f"📄 合同类型：{'自动识别中' if contract_type is None else contract_type}")
    
    reviewer = ContractReviewer(contract_type)
    
    print("⏳ 正在进行条款提取...")
    print("⏳ 正在进行风险检测...")
    print("⏳ 正在进行合规检查...")
    
    result = reviewer.review(contract_text)
    
    # 生成报告
    print("⏳ 正在生成审查报告...")
    report = reviewer.generate_report(result, args.output)
    
    # 输出结果
    if args.format == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(report)
    
    # 如果指定了输出路径，保存报告
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(report)
        print(f"\n✅ 报告已保存至：{args.output}")
    
    return result


if __name__ == "__main__":
    main()
