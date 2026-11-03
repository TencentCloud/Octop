#!/usr/bin/env python3
"""
自动化数据分析核心引擎
支持：CSV/Excel 数据加载 → 清洗 → 多维分析 → 结构化输出
"""

import argparse
import json
import sys
from pathlib import Path

import pandas as pd
import numpy as np


def load_data(filepath: str, sheet_name: str = None) -> pd.DataFrame:
    """加载 CSV 或 Excel 文件"""
    path = Path(filepath)
    if not path.exists():
        raise FileNotFoundError(f"文件不存在: {filepath}")
    if path.suffix.lower() in (".csv", ".tsv"):
        sep = "\t" if path.suffix.lower() == ".tsv" else ","
        return pd.read_csv(filepath, sep=sep)
    elif path.suffix.lower() in (".xlsx", ".xls"):
        return pd.read_excel(filepath, sheet_name=sheet_name or 0)
    else:
        raise ValueError(f"不支持的文件格式: {path.suffix}")


def profile_data(df: pd.DataFrame) -> dict:
    """数据概览：行数、列数、类型、空值、基本统计"""
    profile = {
        "shape": list(df.shape),
        "columns": list(df.columns),
        "dtypes": {col: str(df[col].dtype) for col in df.columns},
        "null_counts": {col: int(df[col].isnull().sum()) for col in df.columns},
        "null_pct": {col: round(df[col].isnull().mean() * 100, 2) for col in df.columns},
    }
    numeric = df.select_dtypes(include="number")
    if not numeric.empty:
        profile["describe"] = numeric.describe().to_dict()
    return profile


def clean_data(
    df: pd.DataFrame,
    drop_empty_cols: bool = True,
    fill_numeric: str = "median",
    fill_categorical: str = "mode",
) -> pd.DataFrame:
    """数据清洗"""
    df = df.copy()
    if drop_empty_cols:
        df = df.drop(columns=[c for c in df.columns if df[c].isnull().all()])
    numeric_cols = df.select_dtypes(include="number").columns
    cat_cols = df.select_dtypes(include=["object", "category"]).columns
    if fill_numeric == "median":
        df[numeric_cols] = df[numeric_cols].fillna(df[numeric_cols].median())
    elif fill_numeric == "mean":
        df[numeric_cols] = df[numeric_cols].fillna(df[numeric_cols].mean())
    if fill_categorical == "mode":
        for col in cat_cols:
            mode_val = df[col].mode()
            if not mode_val.empty:
                df[col] = df[col].fillna(mode_val.iloc[0])
    return df


def variance_analysis(df: pd.DataFrame, value_col: str, group_col: str = None, period_col: str = None) -> dict:
    """差异分析：同比、环比、分组对比"""
    result = {}
    df = df.copy()
    if period_col and period_col in df.columns:
        df = df.sort_values(period_col)
        # 环比
        df["_pct_change"] = df[value_col].pct_change() * 100
        result["month_over_month"] = df[[period_col, value_col, "_pct_change"]].dropna().to_dict(orient="records")
        # 同比 (如果有足够数据)
        if len(df) >= len(df[value_col].dropna()):
            df["_yoy"] = df[value_col].pct_change(periods=max(1, len(df) // 2)) * 100
            result["year_over_year"] = df[[period_col, value_col, "_yoy"]].dropna().to_dict(orient="records")
    if group_col and group_col in df.columns:
        grouped = df.groupby(group_col)[value_col].agg(["sum", "mean", "count", "std"])
        result["group_comparison"] = grouped.round(2).to_dict(orient="index")
    return result


def trend_analysis(df: pd.DataFrame, date_col: str, value_col: str, freq: str = "M") -> dict:
    """趋势分析：按时间维度聚合，计算移动平均"""
    df = df.copy()
    df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
    df = df.dropna(subset=[date_col, value_col])
    # 兼容新旧 pandas 频率别名
    freq_map = {"M": "ME", "Q": "QE", "Y": "YE", "A": "YE", "D": "D", "W": "W"}
    resample_freq = freq_map.get(freq, freq)
    ts = df.set_index(date_col)[value_col]
    agg = ts.resample(resample_freq).agg(["sum", "mean", "count"])
    agg["ma_3"] = agg["mean"].rolling(3).mean()
    agg["ma_6"] = agg["mean"].rolling(6).mean()
    agg = agg.dropna(subset=["ma_3"])
    return {
        "frequency": freq,
        "data": {str(k): v for k, v in agg.round(2).to_dict(orient="index").items()},
    }


def kpi_compute(df: pd.DataFrame, kpis: list[dict]) -> dict:
    """
    计算 KPI。
    kpis 格式: [{"name": "总收入", "formula": "sum(revenue)", ...}, ...]
    支持: sum, mean, median, std, min, max, count, percentile(p)
    """
    results = {}
    for kpi in kpis:
        name = kpi["name"]
        formula = kpi["formula"]
        col = kpi.get("column")
        # 解析公式
        if "(" in formula and ")" in formula:
            func_part, col_part = formula.split("(", 1)
            col_part = col_part.rstrip(")")
            actual_col = col or col_part.strip()
            if actual_col not in df.columns:
                results[name] = {"error": f"列 '{actual_col}' 不存在"}
                continue
            func = func_part.strip().lower()
            series = df[actual_col].dropna()
            if func == "sum":
                results[name] = {"value": round(float(series.sum()), 2)}
            elif func == "mean":
                results[name] = {"value": round(float(series.mean()), 2)}
            elif func == "median":
                results[name] = {"value": round(float(series.median()), 2)}
            elif func == "std":
                results[name] = {"value": round(float(series.std()), 2)}
            elif func == "min":
                results[name] = {"value": round(float(series.min()), 2)}
            elif func == "max":
                results[name] = {"value": round(float(series.max()), 2)}
            elif func == "count":
                results[name] = {"value": int(series.count())}
            elif func.startswith("percentile"):
                p = int(func.split("(")[1]) if "(" in func else 50
                results[name] = {"value": round(float(np.percentile(series, p)), 2)}
            else:
                results[name] = {"error": f"不支持的方法: {func}"}
        elif col and col in df.columns:
            results[name] = {"value": round(float(df[col].iloc[-1]), 2) if len(df) > 0 else None}
        else:
            results[name] = {"error": f"无法解析公式: {formula}"}
    return results


def correlation_matrix(df: pd.DataFrame, columns: list[str] = None) -> dict:
    """相关性矩阵"""
    numeric = df.select_dtypes(include="number")
    if columns:
        available = [c for c in columns if c in numeric.columns]
        numeric = numeric[available]
    if numeric.shape[1] < 2:
        return {"error": "至少需要两个数值列"}
    corr = numeric.corr()
    return corr.round(3).to_dict()


def export_results(results: dict, output_path: str = None, fmt: str = "json"):
    """输出分析结果"""
    if fmt == "json":
        text = json.dumps(results, ensure_ascii=False, indent=2)
        if output_path:
            Path(output_path).write_text(text, encoding="utf-8")
            print(f"✅ 结果已保存到 {output_path}")
        else:
            print(text)
    elif fmt == "markdown":
        lines = []
        _dict_to_md(results, lines, depth=0)
        text = "\n".join(lines)
        if output_path:
            Path(output_path).write_text(text, encoding="utf-8")
            print(f"✅ 结果已保存到 {output_path}")
        else:
            print(text)
    return text


def _dict_to_md(obj, lines: list, depth: int = 0):
    """递归将 dict 转为 Markdown"""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(v, (dict, list)):
                lines.append(f"{'#' * min(depth + 3, 6)} {k}")
                _dict_to_md(v, lines, depth + 1)
            else:
                lines.append(f"- **{k}**: {v}")
    elif isinstance(obj, list):
        for item in obj:
            if isinstance(item, dict):
                for k, v in item.items():
                    lines.append(f"  - **{k}**: {v}")
            else:
                lines.append(f"- {item}")


# ---------- CLI ----------
def main():
    parser = argparse.ArgumentParser(description="自动化数据分析引擎")
    sub = parser.add_subparsers(dest="command")

    # profile
    p_profile = sub.add_parser("profile", help="数据概览")
    p_profile.add_argument("file", help="CSV/Excel 文件路径")
    p_profile.add_argument("--sheet", default=None, help="Excel sheet 名称")

    # clean
    p_clean = sub.add_parser("clean", help="数据清洗")
    p_clean.add_argument("file", help="CSV/Excel 文件路径")
    p_clean.add_argument("-o", "--output", help="输出文件路径")
    p_clean.add_argument("--sheet", default=None)
    p_clean.add_argument("--fill-numeric", default="median", choices=["median", "mean"])
    p_clean.add_argument("--fill-categorical", default="mode", choices=["mode", "drop"])

    # variance
    p_var = sub.add_parser("variance", help="差异分析")
    p_var.add_argument("file", help="文件路径")
    p_var.add_argument("--value", required=True, help="数值列")
    p_var.add_argument("--group", help="分组列")
    p_var.add_argument("--period", help="时间列")

    # trend
    p_trend = sub.add_parser("trend", help="趋势分析")
    p_trend.add_argument("file", help="文件路径")
    p_trend.add_argument("--date", required=True, help="日期列")
    p_trend.add_argument("--value", required=True, help="数值列")
    p_trend.add_argument("--freq", default="M", choices=["D", "W", "M", "Q", "Y"])

    # kpi
    p_kpi = sub.add_parser("kpi", help="KPI 计算")
    p_kpi.add_argument("file", help="文件路径")
    p_kpi.add_argument("--config", required=True, help="KPI 配置 JSON 文件")

    # correlate
    p_corr = sub.add_parser("correlate", help="相关性分析")
    p_corr.add_argument("file", help="文件路径")
    p_corr.add_argument("--columns", nargs="+", help="指定列（默认所有数值列）")

    # 通用参数
    for p in [p_profile, p_clean, p_var, p_trend, p_kpi, p_corr]:
        p.add_argument("--format", default="json", choices=["json", "markdown"])
        p.add_argument("--output", default=None, help="输出文件路径")
        p.add_argument("--sheet", default=None, help="Excel sheet 名称")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    df = load_data(args.file, sheet_name=getattr(args, "sheet", None))

    if args.command == "profile":
        result = profile_data(df)
    elif args.command == "clean":
        cleaned = clean_data(df, fill_numeric=args.fill_numeric, fill_categorical=args.fill_categorical)
        out = args.output or args.file.replace(".", "_cleaned.")
        ext = Path(out).suffix.lower()
        if ext in (".csv", ".tsv"):
            cleaned.to_csv(out, index=False)
        else:
            cleaned.to_excel(out, index=False)
        result = {"cleaned_shape": list(cleaned.shape), "output": out}
    elif args.command == "variance":
        result = variance_analysis(df, args.value, args.group, args.period)
    elif args.command == "trend":
        result = trend_analysis(df, args.date, args.value, args.freq)
    elif args.command == "kpi":
        config = json.loads(Path(args.config).read_text(encoding="utf-8"))
        result = kpi_compute(df, config["kpis"])
    elif args.command == "correlate":
        result = correlation_matrix(df, getattr(args, "columns", None))

    export_results(result, args.output, getattr(args, "format", "json"))


if __name__ == "__main__":
    main()
