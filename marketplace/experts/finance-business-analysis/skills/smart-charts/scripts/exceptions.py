"""统一错误处理"""

import argparse
from enum import Enum
from typing import Any, Dict, Optional


class ErrorCode(Enum):
    FILE_NOT_FOUND = 1001
    FILE_NOT_REGULAR = 1002
    FILE_FORMAT_INVALID = 1003
    FILE_SIZE_EXCEEDED = 1004
    DATA_PARSE_ERROR = 2001
    DATA_MERGE_ERROR = 2002
    DATA_EMPTY = 2003
    TRANSFORM_EXEC_ERROR = 3001
    TRANSFORM_NO_RESULT = 3002
    TRANSFORM_INVALID_RESULT = 3003
    TRANSFORM_EMPTY_RESULT = 3004
    CHART_GENERATION_ERROR = 4001
    CHART_TYPE_UNSUPPORTED = 4002
    CHART_CONFIG_ERROR = 4003
    UNKNOWN_ERROR = 9999


class SmartChartsError(Exception):

    def __init__(
        self,
        message: str,
        code: ErrorCode = ErrorCode.UNKNOWN_ERROR,
        details: Optional[Dict[str, Any]] = None,
    ):
        self.message = message
        self.code = code
        self.details = details or {}
        super().__init__(f"[{code.name}] {message}")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "error": self.message,
            "code": self.code.value,
            "code_name": self.code.name,
            "details": self.details,
        }


class FileError(SmartChartsError):
    pass


class DataError(SmartChartsError):
    pass


class ChartError(SmartChartsError):
    pass


class TransformError(SmartChartsError):
    pass


class JSONArgumentParser(argparse.ArgumentParser):
    """argparse 错误也走结构化 JSON（替代默认的 usage 纯文本 + exit 2）。

    cli.py 与 data_parser.py 的 __main__ 入口共用：未知 flag / 缺参 / 非法取值
    一律抛 ChartError（由调用方 to_dict() 输出 JSON 后以退出码 1 结束）。
    """

    def error(self, message):
        raise ChartError(
            f"参数错误: {message}",
            ErrorCode.CHART_CONFIG_ERROR,
            details={'message': message, 'suggestion': f'运行 python {self.prog} --help 查看完整用法'},
        )
