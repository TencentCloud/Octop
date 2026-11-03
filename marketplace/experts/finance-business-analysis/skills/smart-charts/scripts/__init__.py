"""Smart Charts - 智能图表生成与数据分析"""

# 版本号唯一权威来源：SKILL.md frontmatter 的 version 字段必须与本值一致
# （由 regression_check.py 强制校验，两处不一致即视为回归）。
__version__ = '8.4.0'

from .chart_generator import ChartGenerator, ChartType
from .data_parser import DataParser
from .data_transformer import DataTransformer, CodeValidationError
from .profile import build_profile
from .exceptions import (
    SmartChartsError,
    FileError,
    DataError,
    ChartError,
    TransformError,
    ErrorCode,
)

__all__ = [
    'ChartGenerator',
    'ChartType',
    'DataParser',
    'DataTransformer',
    'build_profile',
    'CodeValidationError',
    'SmartChartsError',
    'FileError',
    'DataError',
    'ChartError',
    'TransformError',
    'ErrorCode',
]
