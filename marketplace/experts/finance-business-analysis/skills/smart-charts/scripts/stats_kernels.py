"""渲染与统计共享的纯计算函数（单一事实来源）。

renderers.py（画图）与 plot_stats.py（plot_stats 摘要）必须引用本模块的同一实现，
保证 plot_stats 报告的事实与实际渲染的图形永远同源——任何一侧不得私改公式。
"""

import numpy as np
import pandas as pd
from typing import Any, Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# 数值清洗与格式化
# ---------------------------------------------------------------------------

def sanitize_value(v, ndigits: Optional[int] = 2):
    """NaN/Inf → None；浮点保留 ndigits 位小数（ndigits=None 时不取整）。

    精度可按数据场景配置（金融/科学数据可调高），默认 2 位。
    """
    if isinstance(v, float):
        if np.isnan(v) or np.isinf(v):
            return None
        return round(v, ndigits) if ndigits is not None else v
    return v


def sanitize_series(data, ndigits: Optional[int] = 2) -> List[Any]:
    return [sanitize_value(v, ndigits) for v in data]


def pt(v) -> Optional[float]:
    """统计摘要用数值规整：None/NaN/非数值 → None，其余保留 2 位小数。"""
    if v is None:
        return None
    try:
        f = float(v)
        if pd.isna(f):
            return None
        return round(f, 2)
    except (TypeError, ValueError):
        return None


def fmt_num(v) -> str:
    """紧凑数字文本：千分位、最多 2 位小数、绝不用科学计数法（waterfall/venn 标签用）。"""
    s = f'{v:,.2f}'.rstrip('0').rstrip('.')
    return '0' if s in ('', '-', '-0') else s


def safe_str_series(series) -> pd.Series:
    """字符串列安全化：NaN/None → ''。

    Categorical 列先转 object 再 astype(str)，避免 pandas 3.0 下
    astype(str) 不转 NaN、'nan' 字符串混入 JSON 的问题。
    """
    if isinstance(series.dtype, pd.CategoricalDtype):
        series = series.astype('object')
    return series.fillna('').astype(str)


def safe_str_list(series) -> List[str]:
    return safe_str_series(series).tolist()


def name_value_pairs(names, values, ndigits: Optional[int] = 2) -> List[Dict[str, Any]]:
    """B 家族（pie/treemap/funnel/sunburst/wordcloud/venn）共用的 name/value 提取。"""
    return [{'name': str(n), 'value': sanitize_value(float(v), ndigits)}
            for n, v in zip(names, values)]


# ---------------------------------------------------------------------------
# 图表族共享算法（渲染与统计两侧必须引用以下函数，不得各自实现）
# ---------------------------------------------------------------------------

def gauge_scale(data_max: float) -> float:
    """gauge/liquid 量程（按数据分布三段定标）：
    - max ≤ 1 的比率数据 → 1.0（如 0.87 → 量程 1.0，指针不再贴零）；
    - 1 < max ≤ 100 的得分/百分比数据 → 100（满分刻度，达成率直观可读）；
    - 其余量纲 → max × 1.05（上浮 5% 留白）。
    """
    if data_max <= 1.0:
        return 1.0
    if data_max <= 100.0:
        return 100.0
    return data_max * 1.05


def sturges_bins(values) -> Tuple[np.ndarray, np.ndarray]:
    """Sturges 规则分箱：n_bins = max(10, log2(N)+1)。返回 (counts, edges)。"""
    n_bins = max(10, int(np.log2(len(values)) + 1))
    return np.histogram(values, bins=n_bins)


def bin_labels(edges, counts) -> List[str]:
    """半开区间记号 [a, b)，末箱闭区间 [a, b]。"""
    labels = [f'[{edges[i]:.1f}, {edges[i + 1]:.1f})' for i in range(len(counts))]
    labels[-1] = labels[-1][:-1] + ']'
    return labels


def box_stats(s: pd.Series) -> Dict[str, Any]:
    """四分位/IQR 须线（q1-1.5*iqr）。s 需已 dropna。返回 outliers 为 Series。"""
    q1, q2, q3 = float(s.quantile(0.25)), float(s.quantile(0.5)), float(s.quantile(0.75))
    iqr = q3 - q1
    lo = max(float(s.min()), q1 - 1.5 * iqr)
    hi = min(float(s.max()), q3 + 1.5 * iqr)
    outliers = s[(s < lo) | (s > hi)]
    return {'min': lo, 'q1': q1, 'median': q2, 'q3': q3, 'max': hi, 'outliers': outliers}


def waterfall_walk(values) -> Tuple[List[float], List[float], List[str], Dict[str, Any]]:
    """瀑布图单遍累计走查。

    返回 (base, heights, signeds, stats)：
    - base/heights：透明垫底高度与悬浮柱高（绝对值），供渲染 stack；
    - signeds：带符号的原始增量文本（fmt_num，无科学计数法），供 label/tooltip；
    - stats：total_delta/first/max_pos_i/max_neg_i/max_positive/max_negative，供 plot_stats。
    """
    base, heights, signeds = [], [], []
    cum = 0.0
    first = None
    max_pos = max_neg = None
    max_pos_i = max_neg_i = None
    for i, v in enumerate(values):
        fv = float(v) if pd.notna(v) else 0.0
        if first is None:
            first = fv
        signeds.append(fmt_num(fv))
        if fv >= 0:
            base.append(round(cum, 2))
            heights.append(round(fv, 2))
            if max_pos is None or fv > max_pos:
                max_pos, max_pos_i = fv, i
        else:
            base.append(round(cum + fv, 2))
            heights.append(round(-fv, 2))
            if max_neg is None or fv < max_neg:
                max_neg, max_neg_i = fv, i
        cum += fv
    stats = {'total_delta': round(cum, 2),
             'first': round(first, 2) if first is not None else None,
             'max_pos_i': max_pos_i, 'max_neg_i': max_neg_i,
             'max_positive': max_pos, 'max_negative': max_neg}
    return base, heights, signeds, stats


def pareto_stats(vals) -> Dict[str, Any]:
    """帕累托累计（vals 需已按降序排列，可含 None）。

    返回 total/n_items/top3_share/items_to_80pct/cum_pct：cum_pct 供渲染折线，
    其余供 plot_stats 摘要——两侧同源。
    """
    clean = [float(v) for v in vals if v is not None]
    total = float(sum(clean)) or 1.0
    cum_pct: List[float] = []
    c = 0.0
    n80 = None
    for i, v in enumerate(vals, start=1):
        c += float(v) if v is not None else 0.0
        cum_pct.append(round(c / total * 100, 2))
        if n80 is None and c / total >= 0.8:
            n80 = i
    top3 = float(sum(clean[:3]))
    return {'total': round(total, 2), 'n_items': len(vals),
            'top3_share': round(top3 / total, 4),
            'items_to_80pct': n80, 'cum_pct': cum_pct}
