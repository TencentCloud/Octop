"""数据解析器。将 CSV、TSV、Excel、JSON、TXT 等文件解析为 DataFrame。

P0/P2/P3 重构要点：
- CSV/TSV 合并为单一分隔符解析器（同一编码回退、同一错误结构）
- 编码回退列表收敛为模块级常量 ENCODING_FALLBACKS，所有格式共用
- 横向合并的 _dup 后缀处理修复：只回收 pandas 追加的后缀列，并用
  combine_first 保留第二份数据中的非空值（不再丢数据、不再误伤真实
  以 _dup 结尾的列名）
- 值形态保护（只看值、不看列名）：值含前导零（007）或超长纯数字（≥16 位，
  float64 丢末位精度）时跳过"字符串转数值"，避免不可逆的信息丢失。是否
  「标识符列」是语义判断，交给 agent 从 profile 的 sample 自行判断，不用
  列名词表去猜（词表穷举不完且必然漏）
- P0-5：列名规范化撞名加 _2/_3 后缀消歧（此前撞名列使 df[col] 返回
  DataFrame，触发 'DataFrame' object has no attribute 'dtype' 硬崩溃）
- P1-6：数值化可观测性——支持「万/亿/千」数量级，部分失败时按成功率决定
  是否转换，并披露被丢弃的非数值单元格数
- Excel sheet 语义：显式指定的 sheet 不存在 → 结构化错误（附可用列表）；
  默认第 0 个 sheet 为空 → 自动回退到第一个非空 sheet
- __main__ 入口统一走 argparse（含未知 flag 在内，参数错误一律结构化 JSON）
"""

import sys
import json
import re
import pandas as pd
import numpy as np
from functools import partial
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple, Union

if __name__ == '__main__' and __package__ is None:
    import _bootstrap  # noqa: F401 — 单点 sys.path 引导，见 _bootstrap.py
    from scripts.exceptions import FileError, DataError, SmartChartsError, ErrorCode, JSONArgumentParser
    from scripts.profile import build_profile
else:
    from .exceptions import FileError, DataError, SmartChartsError, ErrorCode, JSONArgumentParser
    from .profile import build_profile


# 所有文本格式共用的编码回退列表（按命中率排序，latin1 兜底从不抛 UnicodeDecodeError）
ENCODING_FALLBACKS: Tuple[str, ...] = ('utf-8', 'utf-8-sig', 'gbk', 'gb2312', 'utf-16', 'latin1')

# 值判断（只看「值」不看「列名」）：前导零数值字符串（如 007、000123）。
# 转数值会丢失前导零这一不可逆信息，故保持字符串。是否「标识符」是语义判断，
# 交给 agent 从 sample 自行判断，不用列名词表去猜（列名穷举不完且必然漏）。
_LEADING_ZERO_RE = re.compile(r'^0\d+$')

# 值判断：超长纯数字（≥16 位，如身份证号/长订单号）。float64 只能精确表示约
# 15 位有效数字，超过即丢末位精度（实测 18 位证件号转数值后末位被吞）。
# 与前导零同类：都是「转数值会不可逆丢信息」的值形态，不是列名猜测。
_LONG_INT_RE = re.compile(r'^\d{16,}$')

# 中文数量级后缀 → 倍数（P1-6：'8.5万' / '1.2亿' 此前整列退化为字符串）
_CN_MAGNITUDE = (('亿', 1e8), ('万', 1e4), ('千', 1e3))

# 部分数值化的成功率下限：低于该比例说明整列本就是文本，不做半吊子转换
_NUMERIC_SUCCESS_THRESHOLD = 0.5


class DataParser:

    MAX_FILE_SIZE_MB = 100  # 单文件最大允许大小（MB）

    def __init__(self):
        # 解析期的可观测性通道：汇总行排除、数值化降级等"改了数据"的动作
        # 全部登记在此，由 get_data_summary 的 warnings 与 cli.py 的 advisories 对外披露，
        # 绝不做不声不响的数据改动。
        self.advisories: List[str] = []
        self._parsers = {
            '.csv': partial(DataParser._parse_delimited, sep=','),
            '.tsv': partial(DataParser._parse_delimited, sep='\t'),
            '.xlsx': DataParser._parse_excel,
            '.xls': DataParser._parse_excel,
            '.json': DataParser._parse_json,
            '.txt': DataParser._parse_text,
        }

    def parse_file(
        self,
        file_path: str,
        skiprows: Optional[int] = None,
        header_row: Optional[int] = None,
        sheet_name: Union[int, str] = 0,
        drop_rows: Optional[List[int]] = None,
        **kwargs,
    ) -> pd.DataFrame:
        """解析单个文件。

        多行表头/前导冗余行处理（参数互斥，按需传一个即可）：
        - skiprows: 跳过前 N 行后再读取（pandas read_csv/read_excel 的 skiprows 语义）
        - header_row: 指定第 N 行作为列名（0-based），其上方行被丢弃，下方作为数据
        - sheet_name: Excel 工作表索引或名称（默认第 0 个；第 0 个为空时自动回退到
          第一个非空 sheet；显式指定的 sheet 不存在时报错并列出可用 sheet）
        - drop_rows: 清洗后 DataFrame 中按位置（0-based）丢弃非数据行（如多行表头里
          残留下来的子表头行/分值行）。先表头定位 → 再 drop_rows → 再 transform。
        参数值由调用方根据实际数据决定，本技能不预设任何固定行数。
        """
        path = Path(file_path)
        self.advisories = []
        if not path.exists():
            raise FileError(
                f"文件不存在: {file_path}",
                ErrorCode.FILE_NOT_FOUND,
                details={'path': file_path, 'suggestion': '检查路径是否正确，或使用绝对路径'},
            )
        if not path.is_file():
            raise FileError(
                f"不是文件: {file_path}",
                ErrorCode.FILE_NOT_REGULAR,
                details={'path': file_path, 'suggestion': '路径指向的不是常规文件（可能是目录）'},
            )
        size_mb = path.stat().st_size / 1024 / 1024
        if size_mb > self.MAX_FILE_SIZE_MB:
            raise FileError(
                f"文件超过{self.MAX_FILE_SIZE_MB}MB限制",
                ErrorCode.FILE_SIZE_EXCEEDED,
                details={
                    'path': file_path,
                    'size_mb': round(size_mb, 2),
                    'limit_mb': self.MAX_FILE_SIZE_MB,
                    'suggestion': f'拆分文件或筛选行/列后重试，单文件上限 {self.MAX_FILE_SIZE_MB}MB',
                },
            )

        ext = path.suffix.lower()
        if ext not in self._parsers:
            # 有明确但不受支持的扩展名直接走下方 1003 报错，不做内容嗅探；
            # 仅无扩展名文件才按内容识别真实格式
            if not ext:
                ext = self._detect_type(path)
        if ext not in self._parsers:
            supported = list(self._parsers.keys())
            raise FileError(
                f"不支持的格式: {ext}，支持: {supported}",
                ErrorCode.FILE_FORMAT_INVALID,
                details={
                    'path': file_path,
                    'given_ext': ext,
                    'supported': supported,
                    'suggestion': '将文件转为支持的格式（CSV/Excel/JSON）后重试',
                },
            )

        # 统一把表头清洗参数塞进 kwargs，每个 _parse_* 按需读取
        if skiprows is not None:
            kwargs['skiprows'] = skiprows
        if header_row is not None:
            kwargs['header_row'] = header_row
        # 显式传 None 视同未指定：回退到第 0 个 sheet（None 会让 read_excel 返回 dict）
        kwargs.setdefault('sheet_name', 0 if sheet_name is None else sheet_name)

        df = self._parsers[ext](self, path, **kwargs)
        if df.empty:
            raise DataError(
                "文件内容为空",
                ErrorCode.DATA_EMPTY,
                details={'path': file_path, 'suggestion': '检查文件是否只有表头无数据行，或用 --sheet 指定其他工作表'},
            )

        df = self._clean(df)
        if drop_rows:
            df = self._drop_rows(df, drop_rows)
        self._validate(df)
        return df

    def parse_files(self, file_paths: List[str], merge: bool = False) -> Dict[str, Any]:
        """解析多个文件，返回统一结构 {'merged': bool, 'data': ..., 'merge_type': Optional[str]}。

        - merge=False: data 为 List[Dict[str, pd.DataFrame]]，每项含 {'file', 'data'}
        - merge=True:  data 为合并后的 pd.DataFrame，merge_type 描述合并方式
        """
        results = []
        for fp in file_paths:
            df = self.parse_file(fp)
            results.append({'file': Path(fp).name, 'data': df})

        if not merge:
            return {'merged': False, 'data': results, 'merge_type': None}

        merged_df, merge_type = self._merge(results)
        return {'merged': True, 'data': merged_df, 'merge_type': merge_type}

    def get_data_summary(self, df: pd.DataFrame) -> Dict[str, Any]:
        # tail 与 head 并显：汇总行/合计行几乎总在表尾，「样例看起来正常、统计量却
        # 虚高一倍」的陷阱靠 tail 才能当场发现——是否排除哪一行由 agent 自行判断。
        summary: Dict[str, Any] = {
            'shape': list(df.shape),
            'columns': list(df.columns),
            'dtypes': {col: str(dtype) for col, dtype in df.dtypes.items()},
            'missing': {k: int(v) for k, v in df.isnull().sum().to_dict().items()},
            'sample': df.head(5).to_dict('records'),
            'tail': df.tail(5).to_dict('records'),
        }
        # 统计直接基于全表：不替 agent 判断「哪行是汇总行」。若数据含合计行，
        # agent 会从 tail 看到并自行用 --drop-rows / transform 排除后再重取统计。
        numeric_cols = df.select_dtypes(include=[np.number]).columns
        if len(numeric_cols) > 0:
            summary['stats'] = df[numeric_cols].describe().to_dict()
        warnings = list(self.advisories)
        if warnings:
            summary['warnings'] = warnings
        return summary

    @staticmethod
    def _dedupe_columns(cols: List[Any]) -> List[str]:
        """列名规范化后的撞名消歧：第二次出现起加 _2 / _3 后缀（P0-5）。

        撞名时 df[col] 会返回 DataFrame 而非 Series，下游 .dtype 访问直接
        AttributeError 崩溃。这里保证输出列名两两不同，且不与原始列名冲突。
        """
        used = set()
        out: List[str] = []
        for c in cols:
            name = str(c)
            if name not in used:
                used.add(name)
                out.append(name)
                continue
            n = 2
            while f'{name}_{n}' in used:
                n += 1
            new = f'{name}_{n}'
            used.add(new)
            out.append(new)
        return out

    def _merge(self, results: List[Dict]) -> Tuple[pd.DataFrame, str]:
        """尝试合并多个 DataFrame。返回 (merged_df, merge_type)。"""
        dfs = [r['data'] for r in results]
        col_sets = [set(df.columns) for df in dfs]

        # 纵向拼接：所有文件列名完全相同
        if all(len(cs) > 0 for cs in col_sets) and all(cs == col_sets[0] for cs in col_sets):
            merged = pd.concat(dfs, ignore_index=True)
            merged['source_file'] = [r['file'] for r in results for _ in range(len(r['data']))]
            cols = list(merged.columns)
            cols.remove('source_file')
            merged = merged[cols + ['source_file']]
            return merged, '纵向拼接'

        # 横向关联：公共列占比 >= 50%
        if len(dfs) >= 2 and all(len(cs) > 0 for cs in col_sets):
            intersection = col_sets[0]
            for cs in col_sets[1:]:
                intersection = intersection & cs
            avg_col_count = sum(len(cs) for cs in col_sets) / len(col_sets)
            if len(intersection) >= avg_col_count * 0.5:
                # 记录原始列名集合：只有 pandas 追加的 _dup 后缀列才允许回收，
                # 真实以 _dup 结尾的列名保持原样（修复旧实现 replace('_dup','') 的误伤）
                original_cols = set()
                for df in dfs:
                    original_cols.update(str(c) for c in df.columns)
                merged = dfs[0]
                for df in dfs[1:]:
                    merged = pd.merge(merged, df, on=list(intersection), how='outer', suffixes=('', '_dup'))
                merged = self._collapse_merge_suffixes(merged, original_cols)
                return merged, '横向关联'

        # 无法自动合并
        summary_parts = []
        for r in results:
            summary_parts.append(f"{r['file']}: {r['data'].shape[0]}行 {r['data'].shape[1]}列, 列={list(r['data'].columns)}")
        raise DataError(
            f"文件结构差异大，无法自动合并。各文件信息：\n" + "\n".join(summary_parts) +
            "\n请指定关联方式，或分别分析。",
            ErrorCode.DATA_MERGE_ERROR,
            details={
                'files': [{'file': r['file'], 'shape': list(r['data'].shape), 'columns': list(r['data'].columns)} for r in results],
                'suggestion': '请指定关联方式（如 merge_files 时提供 on 列），或对每个文件分别分析',
            },
        )

    @staticmethod
    def _collapse_merge_suffixes(merged: pd.DataFrame, original_cols: set) -> pd.DataFrame:
        """回收 pandas 横向合并追加的 _dup 后缀列。

        语义：base（第一份数据）与 base_dup（第二份数据）是同一业务列的两份来源，
        用 combine_first 保留两份中的非空值后再去掉 _dup 列；真实名为 xxx_dup 的
        原始列不在回收范围内，原样保留。

        回收后若仍存在重名列（如第一份数据本身有 v 与 v_dup 两列、第二份数据又
        含 v 列，pandas 加后缀后与真实 v_dup 撞名），显式报 DATA_MERGE_ERROR，
        不再静默丢弃任一列——静默丢列等于丢数据。
        """
        dup_cols = [
            c for c in merged.columns
            if c.endswith('_dup') and c not in original_cols and c[:-4] in merged.columns
        ]
        for dc in dup_cols:
            base = dc[:-4]
            merged[base] = merged[base].combine_first(merged[dc])
        merged = merged.drop(columns=dup_cols)
        duplicated = merged.columns[merged.columns.duplicated()].tolist()
        if duplicated:
            raise DataError(
                f"横向合并后出现重名列，无法自动处理: {duplicated}",
                ErrorCode.DATA_MERGE_ERROR,
                details={
                    'duplicated_columns': duplicated,
                    'suggestion': '先重命名撞名列（如 xxx_dup）后再合并，或显式指定关联列',
                },
            )
        return merged

    # ---- 解析实现 ----

    def _parse_delimited(self, path: Path, sep: str, **kw) -> pd.DataFrame:
        """解析 CSV/TSV 等单字符分隔文本（同一套编码回退与错误结构）。"""
        label = 'CSV' if sep == ',' else 'TSV'
        read_kwargs = self._build_header_kwargs(kw)
        for _enc in ENCODING_FALLBACKS:
            try:
                return pd.read_csv(path, sep=sep, encoding=_enc, dtype=str, **read_kwargs)
            except pd.errors.EmptyDataError:
                raise DataError(
                    "文件内容为空",
                    ErrorCode.DATA_EMPTY,
                    details={'path': str(path), 'suggestion': '检查文件是否只有表头无数据行'},
                )
            except pd.errors.ParserError as e:
                raise DataError(
                    f"{label} 解析失败: {e}",
                    ErrorCode.DATA_PARSE_ERROR,
                    details={
                        'path': str(path),
                        'error': str(e),
                        'suggestion': '文件可能含前导说明行或列数不一致，先不加参数运行查看原始布局，再用 --skiprows N 或 --header-row N 跳过冗余行',
                    },
                )
            except UnicodeDecodeError:
                continue
        raise DataError(
            "无法解码文件",
            ErrorCode.DATA_PARSE_ERROR,
            details={'path': str(path), 'tried_encodings': list(ENCODING_FALLBACKS),
                     'suggestion': '用文本编辑器另存为 UTF-8 后重试'},
        )

    def _parse_excel(self, path: Path, **kw) -> pd.DataFrame:
        sheet = kw.get('sheet_name', 0)
        # 根据扩展名选择引擎：.xlsx 用 openpyxl，.xls 用 xlrd
        ext = path.suffix.lower()
        engine = 'xlrd' if ext == '.xls' else 'openpyxl'
        read_kwargs = self._build_header_kwargs(kw)
        # dtype=str：与 CSV/TSV 对齐——统一按字符串读入，再由 _clean 统一数值化。
        # 否则 pandas 会把纯数字无前导零的 ID（学号/订单号）提前转成 float64，
        # 绕过 _is_id_like 的列名保护，导致标识符被误当度量轴。
        read_kwargs['dtype'] = str
        try:
            xl = pd.ExcelFile(path, engine=engine)
        except Exception as e:
            raise DataError(
                f"Excel读取失败: {e}",
                ErrorCode.DATA_PARSE_ERROR,
                details={'path': str(path), 'engine': engine, 'error': str(e),
                         'suggestion': '检查文件是否损坏、是否为真正的 Excel 文件（非改扩展名的 CSV）'},
            )
        sheets = list(xl.sheet_names)
        # 显式指定的 sheet 不存在 → 报错并列出可用 sheet（不再静默回退）
        if isinstance(sheet, str) and sheet not in sheets:
            raise DataError(
                f"工作表不存在: {sheet}",
                ErrorCode.DATA_PARSE_ERROR,
                details={'path': str(path), 'given_sheet': sheet, 'available_sheets': sheets,
                         'suggestion': f'从 available_sheets 中选择，或用 --sheet <索引> 指定（共 {len(sheets)} 个）'},
            )
        if isinstance(sheet, int) and not (-len(sheets) <= sheet < len(sheets)):
            raise DataError(
                f"工作表索引越界: {sheet}",
                ErrorCode.DATA_PARSE_ERROR,
                details={'path': str(path), 'given_index': sheet, 'available_sheets': sheets,
                         'suggestion': f'索引范围 0~{len(sheets) - 1}，或直接用 --sheet <名称>'},
            )
        try:
            df = pd.read_excel(path, sheet_name=sheet, engine=engine, **read_kwargs)
            # 仅默认第 0 个 sheet 为空时自动回退到第一个非空 sheet；
            # 用户显式指定的 sheet 为空则原样返回（由 parse_file 统一报 DATA_EMPTY）
            if df.empty and sheet == 0:
                for s in sheets[1:]:
                    df2 = pd.read_excel(path, sheet_name=s, engine=engine, **read_kwargs)
                    if not df2.empty:
                        return df2
            return df
        except DataError:
            raise
        except Exception as e:
            raise DataError(
                f"Excel读取失败: {e}",
                ErrorCode.DATA_PARSE_ERROR,
                details={'path': str(path), 'engine': engine, 'error': str(e),
                         'available_sheets': sheets,
                         'suggestion': '检查文件是否损坏、是否为真正的 Excel 文件（非改扩展名的 CSV）'},
            )

    @staticmethod
    def _build_header_kwargs(kw: Dict[str, Any]) -> Dict[str, Any]:
        """从调用 kwargs 中提取表头清洗参数，转为 pandas read_csv/read_excel 接受的形式。

        - skiprows: 整数 N，跳过前 N 行
        - header_row: 整数 N（0-based），将第 N 行作为列名，丢弃其上方行
        两者互斥；同时给出时以 header_row 优先（更精确）。
        """
        out: Dict[str, Any] = {}
        skiprows = kw.get('skiprows')
        header_row = kw.get('header_row')
        if header_row is not None:
            # header=N 等价于：第 N 行作为列名，前面行被 pandas 自动跳过
            out['header'] = int(header_row)
        elif skiprows is not None:
            out['skiprows'] = int(skiprows)
        return out

    def _parse_json(self, path: Path, **kw) -> pd.DataFrame:
        """解析 JSON 文件，支持多编码回退。"""
        data = None
        last_error = None
        for enc in ENCODING_FALLBACKS:
            try:
                with open(path, 'r', encoding=enc) as f:
                    data = json.load(f)
                break
            except UnicodeDecodeError:
                continue
            except json.JSONDecodeError as e:
                last_error = e
                continue
        if data is None:
            if last_error:
                raise DataError(
                    f"JSON 解析失败: {last_error}",
                    ErrorCode.DATA_PARSE_ERROR,
                    details={'path': str(path), 'error': str(last_error), 'suggestion': '用 JSON 校验工具检查格式（如 jsonlint.com）'},
                )
            raise DataError(
                "无法解码 JSON 文件",
                ErrorCode.DATA_PARSE_ERROR,
                details={'path': str(path), 'tried_encodings': list(ENCODING_FALLBACKS), 'suggestion': '用文本编辑器另存为 UTF-8 后重试'},
            )

        # 提取待转表的记录集，并检测字段值是否含 dict/list（即嵌套超过 1 层）
        if isinstance(data, list):
            records = data
        elif isinstance(data, dict):
            list_value = next((v for v in data.values() if isinstance(v, list)), None)
            records = list_value if list_value is not None else [data]
        else:
            raise DataError(
                "不支持的JSON结构",
                ErrorCode.DATA_PARSE_ERROR,
                details={'path': str(path), 'top_level_type': type(data).__name__,
                         'suggestion': 'JSON 顶层必须是数组、或含数组值的对象'},
            )

        # 校验嵌套深度：允许 1 层嵌套对象（展开为 "父.子" 点分列，与文档声明一致），
        # 深度 ≥2 的 dict 与任何 list 值仍不支持
        for r in records:
            if not isinstance(r, dict):
                continue
            for k, v in r.items():
                if isinstance(v, list):
                    raise DataError(
                        f"JSON 字段 '{k}' 的值为数组，暂不支持",
                        ErrorCode.DATA_PARSE_ERROR,
                        details={'path': str(path), 'field': k,
                                 'suggestion': '请将数组字段转为标量（如取首元素、求和），或用工具先转为 CSV 再生成图表'},
                    )
                if isinstance(v, dict):
                    if any(isinstance(x, (dict, list)) for x in v.values()):
                        raise DataError(
                            "JSON 嵌套超过 1 层，暂不支持",
                            ErrorCode.DATA_PARSE_ERROR,
                            details={'path': str(path), 'field': k,
                                     'suggestion': '每条记录最多嵌套 1 层对象（展开为 "父.子" 列），更深的结构请先展平或转为 CSV'},
                        )
                    # 展开名 "父.子" 与记录内已有键撞名时，json_normalize 会静默用
                    # 嵌套值覆盖原始标量值（丢数据）——这里前置拦截，显式报错
                    clash = [f'{k}.{sk}' for sk in v if f'{k}.{sk}' in r]
                    if clash:
                        raise DataError(
                            f"JSON 嵌套字段展开后与已有列重名: {clash}",
                            ErrorCode.DATA_PARSE_ERROR,
                            details={'path': str(path), 'duplicated_columns': clash,
                                     'suggestion': '展开产生的 "父.子" 列名与现有字段撞名，请重命名字段后再试'},
                        )

        # 含 1 层嵌套对象 → json_normalize 展平为点分列；扁平数据维持原有路径（行为不变）
        has_nested = any(
            isinstance(v, dict)
            for r in records if isinstance(r, dict) for v in r.values()
        )
        if has_nested:
            if not all(isinstance(r, dict) for r in records):
                raise DataError(
                    "JSON 记录结构不一致（对象与标量混排），暂不支持",
                    ErrorCode.DATA_PARSE_ERROR,
                    details={'path': str(path),
                             'suggestion': '数组元素须全部为对象，请清理数据或先转为 CSV'},
                )
            df = pd.json_normalize(records, max_level=1)
            dup = df.columns[df.columns.duplicated()].tolist()
            if dup:
                raise DataError(
                    f"JSON 嵌套字段展开后与已有列重名: {dup}",
                    ErrorCode.DATA_PARSE_ERROR,
                    details={'path': str(path), 'duplicated_columns': dup,
                             'suggestion': '展开产生的 "父.子" 列名与现有字段撞名，请重命名字段后再试'},
                )
            return df
        if isinstance(data, list):
            return pd.DataFrame(data)
        if list_value is not None:
            return pd.DataFrame(list_value)
        return pd.json_normalize(data)

    def _parse_text(self, path: Path, **kw) -> pd.DataFrame:
        """解析文本文件，支持多编码回退与分隔符探测。"""
        lines = None
        detected_enc = ENCODING_FALLBACKS[0]
        for enc in ENCODING_FALLBACKS:
            try:
                with open(path, 'r', encoding=enc) as f:
                    lines = [l.strip() for l in f if l.strip()]
                detected_enc = enc
                break
            except UnicodeDecodeError:
                continue
        if not lines:
            raise DataError(
                "文件为空",
                ErrorCode.DATA_EMPTY,
                details={'path': str(path), 'suggestion': '检查文件是否有内容'},
            )
        read_kwargs = self._build_header_kwargs(kw)
        for delim in (',', '\t', ';', '|'):
            if delim in lines[0] and len(lines[0].split(delim)) > 1:
                return pd.read_csv(path, sep=delim, encoding=detected_enc, dtype=str, **read_kwargs)
        return pd.DataFrame({'content': lines})

    def _detect_type(self, path: Path) -> str:
        try:
            header = path.read_bytes()[:1024]
            text = header.decode('utf-8', errors='ignore')
            if text.strip().startswith(('{', '[')):
                return '.json'
            if header.startswith(b'\x50\x4B\x03\x04'):
                return '.xlsx'
            for delim in (',', '\t', ';'):
                if delim in text:
                    return '.csv'
        except Exception:
            pass
        return path.suffix.lower()

    def _clean(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.dropna(axis=1, how='all').dropna(axis=0, how='all').reset_index(drop=True)
        # P0-5：撞名消歧必须在任何按名取列之前完成
        df.columns = self._dedupe_columns([self._normalize_col(c) for c in df.columns])
        for col in df.columns:
            if df[col].dtype == 'object' or pd.api.types.is_string_dtype(df[col]):
                # 值形态保护：前导零 / 超长纯数字保持字符串（转数值会不可逆丢信息），
                # 其余按客观的数值化规则转换。「是不是标识符」交给 agent 判断
                if not self._is_id_like(col, df[col]):
                    converted, note = self._to_numeric_if_possible(df[col])
                    if note is not None:
                        self.advisories.append(note)
                    df[col] = converted
        # 不在此处排除汇总行——「哪一行是合计行」是语义判断，交 agent 从
        # summary.tail / profile 自行识别后用 --drop-rows 或 transform 处理。
        return df

    @staticmethod
    def _is_id_like(col: str, series: pd.Series) -> bool:
        """判断列是否需保持字符串（跳过数值化）。

        只做值判断：转数值会不可逆丢信息的两类形态——前导零（007 → 7 丢前导零）、
        超长纯数字（≥16 位，float64 丢末位精度）。「这列是不是标识符」是语义判断，
        不用列名词表去猜（穷举不完）；agent 从 profile 的 sample + cardinality 自行判断。
        """
        try:
            s = series.dropna().astype(str).str.strip()
            return bool(s.str.match(_LEADING_ZERO_RE).any() or s.str.match(_LONG_INT_RE).any())
        except Exception:
            return False

    @staticmethod
    def _to_numeric_if_possible(series: pd.Series) -> Tuple[pd.Series, Optional[str]]:
        """尝试将字符串列转换为数值列。返回 (结果列, 提示语或 None)。

        清理链条：货币符号 → 千分位逗号 → 百分号 → 中文数量级（万/亿/千）。
        转换策略（P1-6）：用 errors='coerce' 逐格转换后按成功率决策——

        - 全部成功：整列转数值（与旧行为一致）；
        - 部分成功且成功率 ≥ 0.5：转数值，失败格置 NaN，并**返回提示语**披露
          被丢弃的非数值单元格数（旧行为是整列静默退化为字符串，图表从数值型
          悄悄变成分类型，全程无任何告警）；
        - 成功率 < 0.5：整列保持字符串，不做半吊子转换。

        百分号整体转为小数。避免使用 errors='ignore'，消除 FutureWarning。
        """
        # 先把缺失值归一为空串再转 str：否则 NaN 经 astype(str) 变成字符串 'nan'，
        # 导致 to_numeric 整列失败、列静默回退 object（下游聚合退化为字符串拼接）
        s = series.fillna('').astype(str).str.strip()
        non_empty = s != ''
        n_non_empty = int(non_empty.sum())
        if n_non_empty == 0:
            return series, None
        cleaned = s.str.replace(r'[¥$€£￥]', '', regex=True).str.replace(',', '', regex=False)
        has_pct = cleaned.str.endswith('%')
        cleaned = cleaned.str.rstrip('%')
        # 中文数量级：8.5万 → 85000，1.2亿 → 120000000
        mult = pd.Series(1.0, index=cleaned.index)
        for unit, factor in _CN_MAGNITUDE:
            is_u = cleaned.str.endswith(unit)
            if is_u.any():
                mult = mult.where(~is_u, factor)
                cleaned = cleaned.where(~is_u, cleaned.str.rstrip(unit))
        converted = pd.to_numeric(cleaned.mask(~non_empty), errors='coerce') * mult
        if has_pct.any():
            converted = converted.where(~has_pct, converted / 100.0)
        n_ok = int(converted.notna().sum())
        if n_ok == 0:
            return series, None
        if n_ok < n_non_empty:
            if n_ok / n_non_empty < _NUMERIC_SUCCESS_THRESHOLD:
                return series, None
            return converted, (
                f'列 "{series.name}" 有 {n_non_empty - n_ok}/{n_non_empty} 个单元格不是合法数值，'
                f'已置为缺失后转数值列（原值如 "-"、"N/A" 会被丢弃）；'
                f'如需保留为分类，请用 --transform-code 显式处理'
            )
        return converted, None

    @staticmethod
    def _normalize_col(name: Any) -> str:
        if pd.isna(name):
            return 'unnamed'
        s = re.sub(r'[^\w\s]', '_', str(name).strip())
        s = re.sub(r'[\s_]+', '_', s).strip('_').lower()
        return s or 'unnamed'

    def _drop_rows(self, df: pd.DataFrame, positions: List[int]) -> pd.DataFrame:
        """按位置（0-based）丢弃非数据行，并登记 advisory。

        位置是 _clean 之后、reset_index 之后的 DataFrame 行索引（0..n-1），
        不是原始文件行号。越界位置报结构化错误，绝不静默忽略——静默忽略等于
        让 agent 以为删掉了脏行，实际却没删，后续结论全部建立在错误数据上。
        """
        n = int(len(df))
        positions = sorted(set(positions))
        bad = [p for p in positions if p < 0 or p >= n]
        if bad:
            raise DataError(
                f"--drop-rows 位置越界: {bad}（清洗后数据只有 {n} 行，位置须在 0~{n - 1}）",
                ErrorCode.DATA_PARSE_ERROR,
                details={
                    'positions': positions,
                    'rows': n,
                    'suggestion': '位置是清洗后 DataFrame 的行索引（0-based），'
                                  '先用 --profile 看 row_quality 与 rows 确认行数，'
                                  '或 --transform-code result = df.drop(index=[...])',
                },
            )
        if positions:
            df = df.drop(index=positions).reset_index(drop=True)
            self.advisories.append(
                f'已按 --drop-rows 丢弃 {len(positions)} 行（位置 {positions}，0-based），'
                f'剩余 {int(len(df))} 行'
            )
        return df

    @staticmethod
    def _validate(df: pd.DataFrame):
        if df.empty:
            raise DataError(
                "数据为空",
                ErrorCode.DATA_EMPTY,
                details={'suggestion': '清洗后数据为空，检查原始数据是否全为空行/空列'},
            )


def _build_arg_parser() -> JSONArgumentParser:
    p = JSONArgumentParser(
        prog='data_parser.py',
        description='Smart Charts 数据解析器：数据文件 → DataFrame（预览/JSON 摘要）',
    )
    p.add_argument('files', nargs='+', help='数据文件路径（单个或多个）')
    p.add_argument('--summary', action='store_true', help='输出 JSON 数据摘要（shape/列/类型/缺失/样本/统计）')
    p.add_argument('--profile', action='store_true',
                   help='输出 JSON 数据画像（列角色/基数/分布/粒度/候选洞察信号/图型建议）——出图前的第 0 步，不依赖图表类型')
    p.add_argument('--merge', action='store_true', help='多文件自动合并（列相同纵向拼接，公共列>=50%横向关联）')
    p.add_argument('--skiprows', type=int, default=None, metavar='N', help='跳过前 N 行再读取（单文件模式）')
    p.add_argument('--header-row', dest='header_row', type=int, default=None, metavar='N',
                   help='第 N 行（0-based）作为列名，其上方行丢弃（单文件模式）')
    p.add_argument('--drop-rows', dest='drop_rows', default=None, metavar='0,1',
                   help='丢弃清洗后 DataFrame 中指定行位置（0-based，逗号分隔；单文件模式）')
    p.add_argument('--sheet', default=None, metavar='NAME|INDEX',
                   help='Excel 工作表名称或索引（单文件模式，默认第 0 个）')
    return p


def _run_cli() -> int:
    try:
        ns = _build_arg_parser().parse_args()
    except SmartChartsError as e:
        print(json.dumps(e.to_dict(), ensure_ascii=False), file=sys.stderr)
        return 1

    sheet_name = 0
    if ns.sheet is not None:
        v = ns.sheet
        sheet_name = int(v) if v.lstrip('-').isdigit() else v

    drop_rows: List[int] = []
    if ns.drop_rows is not None:
        try:
            drop_rows = sorted({int(x) for x in str(ns.drop_rows).split(',') if x.strip()})
        except ValueError:
            err = SmartChartsError(
                f"--drop-rows 需要逗号分隔的整数: {ns.drop_rows}",
                ErrorCode.DATA_PARSE_ERROR,
                details={'given': ns.drop_rows, 'suggestion': '形如 --drop-rows 0,1（0-based 行位置，逗号分隔）'},
            )
            print(json.dumps(err.to_dict(), ensure_ascii=False), file=sys.stderr)
            return 1

    # 单文件清洗参数（仅对单文件模式生效；多文件场景请在 transform_code 阶段处理）
    single = len(ns.files) == 1 and not ns.merge
    parser = DataParser()
    try:
        if single:
            df = parser.parse_file(
                ns.files[0], skiprows=ns.skiprows, header_row=ns.header_row, sheet_name=sheet_name,
                drop_rows=drop_rows,
            )
            if ns.profile:
                print(json.dumps(build_profile(df), ensure_ascii=False, indent=2, default=str))
            elif ns.summary:
                print(json.dumps(parser.get_data_summary(df), ensure_ascii=False, indent=2, default=str))
            else:
                print(f"解析成功: {df.shape[0]} 行, {df.shape[1]} 列")
                print(f"列名: {list(df.columns)}")
                print(df.head(5).to_string())
        else:
            result = parser.parse_files(ns.files, merge=ns.merge)
            if result['merged']:
                merged_df, merge_type = result['data'], result['merge_type']
                if ns.profile:
                    prof = build_profile(merged_df)
                    prof['merge_type'] = merge_type
                    print(json.dumps(prof, ensure_ascii=False, indent=2, default=str))
                elif ns.summary:
                    # summary 模式 stdout 必须是纯 JSON（agent 机器可读），merge_type 放入 JSON 内
                    summary = parser.get_data_summary(merged_df)
                    summary['merge_type'] = merge_type
                    print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))
                else:
                    print(f"合并方式: {merge_type}")
                    print(f"合并后: {merged_df.shape[0]} 行, {merged_df.shape[1]} 列")
                    print(f"列名: {list(merged_df.columns)}")
                    print(merged_df.head(5).to_string())
            else:
                items = result['data']
                if ns.profile:
                    profiles = [{'file': it['file'], **build_profile(it['data'])} for it in items]
                    print(json.dumps(profiles, ensure_ascii=False, indent=2, default=str))
                elif ns.summary:
                    summaries = [{'file': it['file'], **parser.get_data_summary(it['data'])} for it in items]
                    print(json.dumps(summaries, ensure_ascii=False, indent=2, default=str))
                else:
                    for it in items:
                        df = it['data']
                        print(f"\n--- {it['file']}: {df.shape[0]} 行, {df.shape[1]} 列 ---")
                        print(f"列名: {list(df.columns)}")
                        print(df.head(3).to_string())
        return 0
    except SmartChartsError as e:
        print(json.dumps(e.to_dict(), ensure_ascii=False), file=sys.stderr)
        return 1
    except Exception as e:
        # P0-5：兜底路径也必须带 suggestion。REFERENCE.md 承诺 details 恒含
        # suggestion，其余 24 处 raise 都逐一对应，唯独兜底缺失——而这正是
        # 撞名崩溃等未预期异常唯一会走到的分支。
        err = SmartChartsError(
            f"未知错误: {e}", ErrorCode.UNKNOWN_ERROR,
            details={'error': str(e), 'type': type(e).__name__,
                     'suggestion': '先不带任何 flags 运行一次查看原始布局；'
                                   '若列名规范化后撞名（如 Sales Amount 与 sales-amount），'
                                   '请重命名源文件的列后重试'},
        )
        print(json.dumps(err.to_dict(), ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(_run_cli())
