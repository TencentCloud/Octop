"""
合同智能助手脚本包
Contract Assistant Scripts Package

提供合同智能审查、生成、对比等核心功能
"""

from .contract_review import ContractReviewer
from .clause_extraction import ClauseExtractor, ClauseType, ExtractedClause
from .risk_detection import RiskDetector, RiskLevel, DetectedRisk
from .compliance_check import ComplianceChecker, ComplianceIssue
from .contract_generator import ContractGenerator, ContractTemplate, GeneratedContract
from .comparison_analysis import ContractComparator, ComparisonReport, ClauseDiff
from .report_generator import ReportGenerator
from . import utils

__version__ = "1.0.2"

__all__ = [
    # 主审查器
    "ContractReviewer",
    
    # 条款提取
    "ClauseExtractor",
    "ClauseType",
    "ExtractedClause",
    
    # 风险检测
    "RiskDetector",
    "RiskLevel",
    "DetectedRisk",
    
    # 合规检查
    "ComplianceChecker",
    "ComplianceIssue",
    
    # 合同生成
    "ContractGenerator",
    "ContractTemplate",
    "GeneratedContract",
    
    # 对比分析
    "ContractComparator",
    "ComparisonReport",
    "ClauseDiff",
    
    # 报告生成
    "ReportGenerator",
    
    # 工具函数
    "utils"
]
