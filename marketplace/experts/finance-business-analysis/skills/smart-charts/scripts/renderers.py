"""图表渲染器。32 种图表类型的 ECharts option 生成方法。

架构契约（P1 重构后）：
- 渲染方法只接收一个 RenderContext，所有依赖（df/x/y/texts/theme/label_col/color_by）
  显式入参，不再读写生成器实例属性（消灭 Mixin 隐式状态协议）。
- 需要内嵌 JS 函数的图表（tooltip formatter / bubble symbolSize）把 JS 片段
  收集到 ctx.js（占位符 → JS 代码），由 template 层统一消费。
- 共享数值清洗与统计算法一律引用 stats_kernels（单一事实来源），
  与 plot_stats 统计层同源。
"""

import json
import math
import re
import warnings
from pathlib import Path
import pandas as pd
import numpy as np
from dataclasses import dataclass, field, replace
from typing import Any, Dict, List, Optional, Tuple

from .exceptions import ChartError, ErrorCode
from .stats_kernels import (
    sanitize_value, sanitize_series, safe_str_list, name_value_pairs,
    gauge_scale, sturges_bins, bin_labels, box_stats, waterfall_walk, pareto_stats, fmt_num,
)
from .template import (
    TOOLTIP_FORMATTER_AXIS,
    BUBBLE_SYMBOLSIZE_PLACEHOLDER,
    BUBBLE_TOOLTIP_PLACEHOLDER,
    ITEM_TOOLTIP_PLACEHOLDER,
    WATERFALL_TOOLTIP_PLACEHOLDER,
    LIQUID_LABEL_PLACEHOLDER,
    DATAZOOM_THRESHOLD,
    ESC_JS_FN,
)


# ── 地图 GeoJSON 加载与地名对齐（map/lines 共用，离线捆绑中国省级地图）──
_GEO_DIR = Path(__file__).resolve().parent.parent / 'assets'
_GEO_CACHE: Dict[str, Dict[str, Any]] = {}

# 省级简称 → GeoJSON 全称（中国 34 个省级行政区，含港澳台）。表格里常见的
# 「北京/广东/新疆」等简称与 GeoJSON 的「北京市/广东省/新疆维吾尔自治区」全称对齐。
_REGION_ALIASES = {
    '北京': '北京市', '北京市': '北京市',
    '天津': '天津市', '天津市': '天津市',
    '河北': '河北省', '河北省': '河北省',
    '山西': '山西省', '山西省': '山西省',
    '内蒙古': '内蒙古自治区', '内蒙古自治区': '内蒙古自治区',
    '辽宁': '辽宁省', '辽宁省': '辽宁省',
    '吉林': '吉林省', '吉林省': '吉林省',
    '黑龙江': '黑龙江省', '黑龙江省': '黑龙江省',
    '上海': '上海市', '上海市': '上海市',
    '江苏': '江苏省', '江苏省': '江苏省',
    '浙江': '浙江省', '浙江省': '浙江省',
    '安徽': '安徽省', '安徽省': '安徽省',
    '福建': '福建省', '福建省': '福建省',
    '江西': '江西省', '江西省': '江西省',
    '山东': '山东省', '山东省': '山东省',
    '河南': '河南省', '河南省': '河南省',
    '湖北': '湖北省', '湖北省': '湖北省',
    '湖南': '湖南省', '湖南省': '湖南省',
    '广东': '广东省', '广东省': '广东省',
    '广西': '广西壮族自治区', '广西壮族自治区': '广西壮族自治区',
    '海南': '海南省', '海南省': '海南省',
    '重庆': '重庆市', '重庆市': '重庆市',
    '四川': '四川省', '四川省': '四川省',
    '贵州': '贵州省', '贵州省': '贵州省',
    '云南': '云南省', '云南省': '云南省',
    '西藏': '西藏自治区', '西藏自治区': '西藏自治区',
    '陕西': '陕西省', '陕西省': '陕西省',
    '甘肃': '甘肃省', '甘肃省': '甘肃省',
    '青海': '青海省', '青海省': '青海省',
    '宁夏': '宁夏回族自治区', '宁夏回族自治区': '宁夏回族自治区',
    '新疆': '新疆维吾尔自治区', '新疆维吾尔自治区': '新疆维吾尔自治区',
    '台湾': '台湾省', '台湾省': '台湾省',
    '香港': '香港特别行政区', '香港特别行政区': '香港特别行政区',
    '澳门': '澳门特别行政区', '澳门特别行政区': '澳门特别行政区',
}


# 内置图名 → 别名表（简称 → GeoJSON 全称）。内置地图捆绑 china/world（assets/ 下同名
# GeoJSON）；china 有省级简称别名，world 用英文国名精确匹配、无别名，故不在此登记。
# 新增内置图时若需简称别名，在此登记对应别名表（无别名则不登记）。
_BUILTIN_ALIASES: Dict[str, Dict[str, str]] = {
    'china': _REGION_ALIASES,
}


def load_builtin_geojson(name: str) -> Dict[str, Any]:
    """加载并缓存内置 GeoJSON（assets/<name>.json，离线捆绑）。"""
    if name not in _GEO_CACHE:
        geo_file = _GEO_DIR / f'{name}.json'
        if not geo_file.exists():
            raise ChartError(
                f"内置地图资源缺失（assets/{name}.json）",
                ErrorCode.CHART_GENERATION_ERROR,
                details={'suggestion': f'确认 assets/{name}.json 存在；'
                                       '或用 --geo-path 指向自备 GeoJSON 文件'},
            )
        try:
            _GEO_CACHE[name] = json.loads(geo_file.read_text(encoding='utf-8'))
        except (OSError, json.JSONDecodeError) as e:
            raise ChartError(
                f"地图 GeoJSON 解析失败: {e}",
                ErrorCode.CHART_GENERATION_ERROR,
                details={'suggestion': f'确认 assets/{name}.json 是合法的 GeoJSON'},
            )
    return _GEO_CACHE[name]


def load_china_geojson() -> Dict[str, Any]:
    """加载并缓存中国省级 GeoJSON（兼容旧名，等价 load_builtin_geojson('china')）。"""
    return load_builtin_geojson('china')


def geojson_region_names(geojson: Dict[str, Any]) -> set:
    """返回任意 GeoJSON 中所有非空区域全称（地名对齐与可匹配地区提示共用）。"""
    return {f['properties']['name'] for f in geojson.get('features', [])
            if f.get('properties', {}).get('name')}


def china_region_names() -> set:
    """返回中国省级 GeoJSON 的所有非空区域全称（兼容旧名）。"""
    return geojson_region_names(load_china_geojson())


def resolve_region_name(name: Any, geo_names: Optional[set] = None,
                        aliases: Optional[Dict[str, str]] = None) -> Optional[str]:
    """表格地名 → GeoJSON 全称（精确匹配 + 简称映射）；无法匹配返回 None。

    geo_names/aliases 缺省时回退到中国省级地图（向后兼容）。
    """
    if name is None:
        return None
    n = str(name).strip()
    if not n:
        return None
    if geo_names is None:
        geo_names = china_region_names()
    if aliases is None:
        aliases = _REGION_ALIASES
    if n in geo_names:
        return n
    return aliases.get(n)


@dataclass
class GeoSource:
    """解析后的地图来源：registerMap / series.map 用的名字 + GeoJSON + 地名别名。"""
    map_name: str
    geojson: Dict[str, Any]
    aliases: Dict[str, str]
    source: str  # 'builtin:china' / 'file:/path/to/x.json'


def resolve_geo(geo: Optional[str] = None, geo_path: Optional[str] = None) -> GeoSource:
    """解析地图来源（--geo / --geo-path），返回 registerMap 所需的三件套。

    优先级：geo_path（用户自备）> geo（内置图名，默认 'china'）。
    - 自备文件：map_name 取文件名 stem，别名表为空（仅精确匹配）。
    - 内置图名：从 assets/<name>.json 读取，别名表按 _BUILTIN_ALIASES 登记
      （未登记则空表，仅精确匹配）。
    """
    if geo_path:
        p = Path(geo_path)
        if not p.exists():
            raise ChartError(
                f"自备地图文件不存在: {geo_path}",
                ErrorCode.FILE_NOT_FOUND,
                details={'given': geo_path, 'suggestion': '确认 --geo-path 指向一个可读的 GeoJSON 文件'},
            )
        try:
            geojson = json.loads(p.read_text(encoding='utf-8'))
        except (OSError, json.JSONDecodeError) as e:
            raise ChartError(
                f"自备地图 GeoJSON 解析失败: {e}",
                ErrorCode.CHART_GENERATION_ERROR,
                details={'given': geo_path, 'suggestion': '确认文件是合法的 GeoJSON'},
            )
        return GeoSource(map_name=p.stem, geojson=geojson, aliases={}, source=f'file:{geo_path}')

    name = (geo or 'china').strip()
    geojson = load_builtin_geojson(name)
    aliases = _BUILTIN_ALIASES.get(name, {})
    return GeoSource(map_name=name, geojson=geojson, aliases=aliases, source=f'builtin:{name}')


def _collect_coordinates(coords: Any) -> List[List[float]]:
    """递归收集 GeoJSON coordinates 里所有 [lng, lat] 点（处理 Polygon/MultiPolygon 嵌套）。

    用于无法从 properties 取到中心点时，从几何计算包围盒中心兜底。
    """
    pts: List[List[float]] = []

    def _walk(x: Any) -> None:
        if not isinstance(x, (list, tuple)):
            return
        if len(x) >= 2 and isinstance(x[0], (int, float)) and isinstance(x[1], (int, float)):
            pts.append([float(x[0]), float(x[1])])
            return
        for item in x:
            _walk(item)

    _walk(coords)
    return pts


def region_centers(geojson: Dict[str, Any]) -> Dict[str, List[float]]:
    """返回 GeoJSON 区域名 → 中心经纬度 [lng, lat] 的映射。

    中心坐标优先级：properties.cp（ECharts 约定）→ properties.center /
    properties.centroid（DataV 格式）→ 从 geometry 计算包围盒中心（兜底）。
    用于 lines 系列的 fromName/toName → coords 定位：ECharts lines 系列的
    data item 只认 `coords` 字段（fromName/toName 仅作 tooltip 标签，不参与定位）。
    """
    centers: Dict[str, List[float]] = {}
    for f in geojson.get('features', []):
        props = f.get('properties') or {}
        name = props.get('name')
        if not name:
            continue
        for key in ('cp', 'center', 'centroid'):
            val = props.get(key)
            if isinstance(val, (list, tuple)) and len(val) >= 2:
                try:
                    centers[name] = [float(val[0]), float(val[1])]
                    break
                except (TypeError, ValueError):
                    continue
        if name in centers:
            continue
        # 兜底：从 geometry 计算包围盒中心
        geom = f.get('geometry') or {}
        pts = _collect_coordinates(geom.get('coordinates'))
        if pts:
            lngs = [c[0] for c in pts]
            lats = [c[1] for c in pts]
            centers[name] = [(min(lngs) + max(lngs)) / 2, (min(lats) + max(lats)) / 2]
    return centers


def _js_dumps(obj) -> str:
    r"""序列化数据到 JS 字面量上下文，转义 </ 防 </script> 提前闭合脚本标签。

    \/ 在 JS 字符串中合法且求值后还原为 /，前端拿到的值不变。
    用于内嵌 option JSON 之外的、由 Python 直接拼接进 <script> 的数据数组
    （tooltip JS 中的列名/行标签等）。
    """
    return json.dumps(obj, ensure_ascii=False).replace('</', '<\\/')


def _labeled_points(df, x_col, num_cols, label_col=None, numeric_color_col=None, x_is_numeric=True):
    """生成带身份标识的点数据（scatter/bubble 共用）。

    每个点为 {'value': [x, *num_cols, (color)], 'name': label}：
    - name 来自 label_col（身份列），tooltip 中作为点的标题；
    - numeric_color_col 存在时把其值追加到 value 末尾，供 visualMap 按维度着色。
    x/y/color 任一为 NaN 的行被跳过（与原实现一致：无法定位的点不渲染）。
    """
    # 向量化 NaN 过滤：任一 x/y 列为 NaN 即整行跳过（color 列 NaN 不跳过，追加 None）
    # pandas 3.0 CoW 下 notna().to_numpy() 返回只读数组，就地 &= 会抛
    # "output array is read-only"，先 copy 出可写副本再累积
    mask = df[x_col].notna().to_numpy().copy()
    for c in num_cols:
        mask &= df[c].notna().to_numpy()
    sub = df[mask]
    x_list = sub[x_col].tolist()
    num_lists = [sub[c].tolist() for c in num_cols]
    color_list = sub[numeric_color_col].tolist() if numeric_color_col is not None else None
    label_list = sub[label_col].tolist() if label_col is not None else None
    pts = []
    for i in range(len(sub)):
        xv = sanitize_value(float(x_list[i])) if x_is_numeric else str(x_list[i])
        vals = [xv] + [sanitize_value(float(v)) for v in (lst[i] for lst in num_lists)]
        if color_list is not None:
            cv = color_list[i]
            vals.append(sanitize_value(float(cv)) if pd.notna(cv) else None)
        pt = {'value': vals}
        if label_list is not None:
            lv = label_list[i]
            pt['name'] = '' if pd.isna(lv) else str(lv)
        pts.append(pt)
    return pts


def _point_tooltip_js(dim_names, has_label):
    """scatter/bubble 的 item tooltip JS：点标题（身份列）+ 各维度 "列名: 值"。"""
    label_line = "if (p.name) { s += '<b>' + esc(p.name) + '</b><br/>'; }" if has_label else ""
    return (
        "function(p) {\n"
        f"  var names = {_js_dumps(list(dim_names))};\n"
        "  " + ESC_JS_FN +
        "  var fmt = function(v) { return (typeof v === 'number') ? v.toLocaleString() : esc(v); };\n"
        "  var s = '';\n"
        f"  {label_line}\n"
        "  var vals = Array.isArray(p.value) ? p.value : [p.value];\n"
        "  for (var i = 0; i < names.length && i < vals.length; i++) {\n"
        "    s += esc(names[i]) + ': ' + fmt(vals[i]) + '<br/>';\n"
        "  }\n"
        "  return s;\n"
        "}"
    )


def _maybe_rotate_labels(x_data):
    """类目过多或标签过长时旋转 x 轴标签，避免长中文类目名重叠。"""
    if len(x_data) > 8 or (x_data and max(len(s) for s in x_data) > 6):
        return {'rotate': 30}
    return None


def _all_nonnegative(df: pd.DataFrame, cols: List[str]) -> bool:
    """数值列全为有限非负值时返回 True（NaN 忽略；含负值或全空返回 False）。

    bar 类图表据此显式锁定 y 轴 min:0——全非负时 ECharts 默认本就含 0，
    此处是声明性 no-op（把"碰巧含 0"变成契约），不会改变既有渲染。
    """
    try:
        arr = df[cols].to_numpy(dtype='float64')
    except (ValueError, TypeError):
        return False
    finite = arr[np.isfinite(arr)]
    return bool(finite.size) and bool((finite >= 0).all())


def _key_label_data(vals: List[Any], top_n: int = 3) -> List[Dict[str, Any]]:
    """key 模式数据标签：仅 top_n 值 + 最大/最小值显示标签，其余靠 tooltip。

    bar 单系列类别过多时全标数值会互相挤压；交互 HTML 有 tooltip 兜底，
    静态导出（保存图片）保留极值与头部数值即可支撑结论。
    """
    finite = [(i, v) for i, v in enumerate(vals) if v is not None]
    show = set()
    if finite:
        ranked = sorted(finite, key=lambda iv: iv[1], reverse=True)
        show.update(i for i, _ in ranked[:top_n])
        show.add(ranked[0][0])   # 最大值
        show.add(ranked[-1][0])  # 最小值
    return [{'value': v, 'label': {'show': i in show}} for i, v in enumerate(vals)]


def _axis_name_graphics(theme, x_name=None, y_names=(), x_bottom=None, x_data_len=0,
                        threshold=DATAZOOM_THRESHOLD):
    """轴名称渲染为可拖拽的 graphic 文本元素。

    放在轴配置里（name/nameGap）位置固定，长名称不是压刻度数字、就是压图例。
    graphic 文本默认放在留白区（x 轴名在标签与图例之间，y 轴名在绘图区上方），
    用户可在图上直接拖拽微调，保存图片时随画布状态生效。
    id 以 axisName- 开头，供 chart_generator._apply_custom_names 按
    --x-name/--y-name 覆盖轴名文字（图上拖拽仅移动位置，不改文字）。
    x_bottom：x 轴名初始底距，显式传入时优先；未传入则按 x_data_len 是否超过
    threshold 自动选择——启用 dataZoom 的图表用 64 避开底部滑块与上移的图例。
    """
    fill = theme['graphic_text']
    if x_bottom is None:
        x_bottom = 64 if (x_data_len and x_data_len > threshold) else 42
    graphics = []
    if x_name:
        graphics.append({'id': 'axisName-x', 'type': 'text', 'draggable': True, 'cursor': 'move',
                         'left': 'center', 'bottom': x_bottom,
                         'style': {'text': x_name, 'fontSize': 12, 'fill': fill}})
    for i, name in enumerate(y_names):
        pos = {'left': '6%', 'top': 38} if i == 0 else {'right': '6%', 'top': 38}
        graphics.append({'id': f'axisName-y{i}', 'type': 'text', 'draggable': True, 'cursor': 'move',
                         **pos, 'style': {'text': name, 'fontSize': 12, 'fill': fill}})
    return graphics


@dataclass
class RenderContext:
    """渲染上下文：一次图表渲染的全部显式依赖。

    - df/x/y/texts/theme/lang：渲染输入；
    - label_col/color_by：身份列与着色列（已校验存在）；
    - y_scale：折线图 y 轴允许非零基线（opt-in，仅 _line 消费；area 由
      _area 显式压制——面积编码量级，非零基线会扭曲面积占比）；
    - sort：bar 类别排序（'value'=按第一个数值 Y 列降序；'none'=保持原序）；
    - label_mode：bar 数值标签策略（'auto'/'all'/'key'，见 _bar）；
    - subtitle：用户提供的副标题（时间范围/筛选条件/数据来源），None 时
      template 层回退到默认副标题行；
    - js：渲染过程中收集的 JS 函数片段（占位符常量 → JS 代码），
      由 template._save_html 在序列化 option 后统一替换，用完即清。
    - width/height：画布尺寸（px），venn 等 option 阶段就需要布局尺寸的图表用
      （与 template 落盘尺寸同源，--width/--height 因此对 venn 布局生效）。
    - x_name/y_names/series_names：独立轴名与系列名（--x-name/--y-name/
      --series-name/--series-names）。None 时回退到列名/默认文本；
      非 None 时由 chart_generator._apply_custom_names 在 option 生成后统一覆盖。
    - target：gauge/liquid 的业务目标值（--target）。liquid 的归一化分母与
      gauge 的满刻度应优先用它（达成率 = 均值 / 目标），缺省才回落 gauge_scale
      自动量程——否则数据 max>100 时渲染口径会与 plot_stats 的 achievement 分裂。
    """
    df: pd.DataFrame
    x: Optional[str]
    y: List[str]
    title: str
    texts: Dict[str, str]
    theme: Dict[str, Any]
    lang: str
    label_col: Optional[str] = None
    color_by: Optional[str] = None
    y_scale: bool = False
    sort: str = 'none'
    label_mode: str = 'auto'
    subtitle: Optional[str] = None
    width: int = 900
    height: int = 560
    x_name: Optional[str] = None
    y_names: Optional[List[str]] = None
    series_names: Optional[List[str]] = None
    target: Optional[float] = None
    # 地图来源（map/lines）：由 chart_generator 解析 GeoSource 后填充。
    # geo_map_name 供 series.map / geo.map / registerMap 用；geo_json 供
    # template 内联 registerMap；geo_aliases/geo_names 供地名对齐（自备图为空表）。
    geo_map_name: str = 'china'
    geo_json: Optional[Dict[str, Any]] = None
    geo_aliases: Dict[str, str] = field(default_factory=dict)
    geo_names: Optional[set] = None
    js: Dict[str, str] = field(default_factory=dict)


class ChartRenderersMixin:
    """32 种图表的 ECharts option 生成方法，由 ChartGenerator 继承。

    全部方法签名为 _xxx(self, ctx: RenderContext)，只通过 ctx 取依赖。
    """

    def _base(self, ctx: RenderContext, x_data_len=0, y_data_len=0):
        theme = ctx.theme
        opt = {
            'title': {'text': ctx.title, 'left': 'center', 'textStyle': {'fontSize': 16}},
            'tooltip': {'trigger': 'axis', 'formatter': TOOLTIP_FORMATTER_AXIS},
            'legend': {'top': 'bottom', 'type': 'scroll'},  # scroll 防止系列过多时图例溢出
            'grid': {'left': '3%', 'right': '4%', 'bottom': '12%', 'containLabel': True},
            # 系列调色板来自主题预设（default 为 Okabe-Ito 色觉安全色板）
            'color': list(theme['palette']),
        }
        # 数据点过多时启用 dataZoom，让用户可在图内拖动/缩放查看完整数据
        zooms = []
        if x_data_len and x_data_len > DATAZOOM_THRESHOLD:
            zooms.append({'type': 'inside', 'start': 0, 'end': 100})
            zooms.append({'type': 'slider', 'start': 0, 'end': 100, 'height': 20, 'bottom': 8})
            opt['grid']['bottom'] = '20%'
        if y_data_len and y_data_len > DATAZOOM_THRESHOLD:
            zooms.append({'type': 'inside', 'orient': 'vertical', 'start': 0, 'end': 100})
            zooms.append({'type': 'slider', 'orient': 'vertical', 'start': 0, 'end': 100, 'width': 16, 'right': 4})
            opt['grid']['right'] = '8%'
        if zooms:
            opt['dataZoom'] = zooms
            # 底部滑块占 0~28px，图例上移避免与滑块重叠
            opt['legend'] = {'bottom': 30, 'type': 'scroll'}
        return opt

    def _line(self, ctx: RenderContext):
        df, x, y = ctx.df, ctx.x, ctx.y
        x_data = safe_str_list(df[x])
        opt = self._base(ctx, x_data_len=len(x_data))
        opt['xAxis'] = {'type': 'category', 'data': x_data}
        rot = _maybe_rotate_labels(x_data)
        if rot:
            opt['xAxis']['axisLabel'] = rot
        opt['yAxis'] = {'type': 'value'}
        # opt-in 非零基线：波动幅度本身有意义时放大趋势（--y-scale）。
        # 默认关闭保持既有渲染；area 永不启用（见 _area）。
        if ctx.y_scale:
            opt['yAxis']['scale'] = True
        opt['graphic'] = _axis_name_graphics(ctx.theme, x, y, x_data_len=len(x_data))
        opt['series'] = [
            {'name': col, 'type': 'line', 'smooth': True, 'data': sanitize_series(df[col].tolist())}
            for col in y
        ]
        return opt

    def _bar(self, ctx: RenderContext):
        df, x, y = ctx.df, ctx.x, ctx.y
        # 类别排序（opt-in，默认 none 保持数据原序）：仅按第一个数值 Y 列降序。
        # 中文月份/流程阶段等自然顺序不会被误动——不传 --sort 即不排序。
        if ctx.sort == 'value' and y and pd.api.types.is_numeric_dtype(df[y[0]]):
            df = df.sort_values(y[0], ascending=False, na_position='last')
        x_data = safe_str_list(df[x])
        opt = self._base(ctx, x_data_len=len(x_data))
        opt['xAxis'] = {'type': 'category', 'data': x_data}
        rot = _maybe_rotate_labels(x_data)
        if rot:
            opt['xAxis']['axisLabel'] = rot
        opt['yAxis'] = {'type': 'value'}
        # 零基线契约：数据全非负时显式锁定 min:0（声明性 no-op，含负值时不锁定，
        # 负值柱照常显示）
        if _all_nonnegative(df, y):
            opt['yAxis']['min'] = 0
        opt['graphic'] = _axis_name_graphics(ctx.theme, x, y, x_data_len=len(x_data))
        opt['series'] = [
            {'name': col, 'type': 'bar', 'data': sanitize_series(df[col].tolist())}
            for col in y
        ]
        if len(y) == 1:
            # 单系列时显示数值标签（多系列显示会互相遮挡，仍靠 tooltip 读值）。
            # 类别过多（auto 阈值 20）或显式 key 模式时只标 top3 + 极值，防挤压
            key_mode = (ctx.label_mode == 'key'
                        or (ctx.label_mode == 'auto' and len(x_data) > 20))
            if key_mode:
                opt['series'][0]['data'] = _key_label_data(opt['series'][0]['data'])
            opt['series'][0]['label'] = {'show': True, 'position': 'top'}
        return opt

    def _pie(self, ctx: RenderContext):
        df, x, y = ctx.df, ctx.x, ctx.y
        opt = self._base(ctx)
        opt['tooltip'] = {'trigger': 'item', 'formatter': '{a} <br/>{b}: {c} ({d}%)'}
        # 图例置于底部（继承 _base 的横向 scroll），避免竖排左置图例与扇区外的长标签重叠
        y_col = y[0] if y else df.columns[-1]
        if not pd.api.types.is_numeric_dtype(df[y_col]):
            # 数值列为空或为分类列时，对 X 列做频数统计，展示各类占比
            counts = df[x].astype(str).value_counts()
            data = [{'name': str(k), 'value': sanitize_value(float(v))} for k, v in counts.items()]
            y_col = ctx.texts['axis_frequency']
        else:
            data = name_value_pairs(df[x].tolist(), df[y_col].tolist())
        # 系列名：--series-name 优先，缺省用数值列名；tooltip {a} 与前端"系列"重命名面板均读该名字，
        # 故用户可把英文列名改成业务名（与 gauge/liquid 同源逻辑）。
        series_name = (ctx.series_names[0] if ctx.series_names else y_col)
        opt['series'] = [{
            'name': series_name, 'type': 'pie', 'radius': ['40%', '70%'], 'data': data,
            'label': {'show': True, 'formatter': '{b}: {c} ({d}%)'},
            'emphasis': {'itemStyle': {'shadowBlur': 10, 'shadowColor': 'rgba(0,0,0,0.5)'}},
        }]
        return opt

    def _scatter(self, ctx: RenderContext):
        """散点图：每个点携带身份（label_col），tooltip 显示 身份 + 列名: 值。

        color_by（可选）：
        - 数值列 → visualMap 连续着色（dimension=2）；
        - 类别列 → 每类拆为一个 series，自动配色并进 legend。
        """
        df, x, y = ctx.df, ctx.x, ctx.y
        label_col, color_col = ctx.label_col, ctx.color_by
        y_col = y[0] if y else df.columns[-1]
        x_is_numeric = pd.api.types.is_numeric_dtype(df[x])
        numeric_color = color_col is not None and pd.api.types.is_numeric_dtype(df[color_col])

        if x_is_numeric:
            opt = self._base(ctx)
            opt['xAxis'] = {'type': 'value', 'scale': True}
            x_data_len = 0
        else:
            x_data = safe_str_list(df[x])
            x_data_len = len(x_data)
            opt = self._base(ctx, x_data_len=x_data_len)
            opt['xAxis'] = {'type': 'category', 'data': x_data}
        opt['yAxis'] = {'type': 'value', 'scale': True}
        opt['graphic'] = _axis_name_graphics(ctx.theme, x, [y_col], x_data_len=x_data_len)

        # tooltip 维度名跟随 --x-name/--y-name（缺省回落列名），否则悬停仍显示英文列名
        x_disp = ctx.x_name if ctx.x_name else x
        y_disp = (ctx.y_names[0] if ctx.y_names else y_col)
        dims = [x_disp, y_disp] + ([color_col] if numeric_color else [])
        ctx.js[ITEM_TOOLTIP_PLACEHOLDER] = _point_tooltip_js(dims, has_label=label_col is not None)
        opt['tooltip'] = {'trigger': 'item', 'formatter': ITEM_TOOLTIP_PLACEHOLDER}

        if color_col is not None and not numeric_color:
            # 类别列 → 按类别拆 series（NaN 归入"未分类"，不静默丢点）
            color_s = df[color_col].where(df[color_col].notna(), ctx.texts['series_uncategorized']).astype(str)
            opt['series'] = [
                {'name': cat, 'type': 'scatter', 'symbolSize': 10,
                 'data': _labeled_points(df[color_s == cat], x, [y_col], label_col, None, x_is_numeric)}
                for cat in color_s.unique()
            ]
        else:
            data = _labeled_points(df, x, [y_col], label_col,
                                   color_col if numeric_color else None, x_is_numeric)
            opt['series'] = [{'name': y_col, 'type': 'scatter', 'data': data, 'symbolSize': 10}]
            if numeric_color:
                cvals = [p['value'][2] for p in data if p['value'][2] is not None]
                if cvals:
                    opt['visualMap'] = {'min': min(cvals), 'max': max(cvals), 'dimension': 2,
                                        'calculable': True, 'orient': 'vertical', 'right': '1%', 'top': 'center'}
                    opt['grid']['right'] = '10%'  # 为右侧 visualMap 留出空间
        return opt

    def _area(self, ctx: RenderContext):
        # 面积图强制零基线：面积编码量级，非零基线会扭曲各段面积占比，
        # 即使 --y-scale 也在此显式压制
        opt = self._line(replace(ctx, y_scale=False))
        for s in opt['series']:
            s['areaStyle'] = {'opacity': 0.5}
        return opt

    def _radar(self, ctx: RenderContext):
        df, x, y = ctx.df, ctx.x, ctx.y
        opt = self._base(ctx)
        opt['tooltip'] = {'trigger': 'item'}
        # indicator 刻度（max）计算：
        # - 单系列（y 仅 1 列）：所有维度共用全局刻度（全局最大值 ×1.2）。
        #   旧实现对 (N,1) 数组做 nanmax(axis=1)，等于"每个维度自身的值"，
        #   ×1.2 后每个维度 value/max 恒为同一比例（83.3%），跨维度差异被
        #   完全抹平（视觉上恒为正多边形）——单系列必须用全局统一刻度。
        # - 多系列：每维度取跨系列最大值 ×1.2（同一维度内各系列可比，
        #   维度间各自归一，适合量纲差异大的多维对比）。
        arr = df[y].to_numpy(dtype='float64')
        with warnings.catch_warnings():
            # 全 NaN 时 nanmax 返回 nan 并告警，交由下方 is None 兜底（0 为合法 max，不再覆盖）
            warnings.simplefilter('ignore', RuntimeWarning)
            if arr.shape[1] <= 1:
                try:
                    gm = float(np.nanmax(arr)) * 1.2
                except ValueError:  # 空数组（y 为空列）
                    gm = float('nan')
                row_max = np.full(len(df), gm if (np.isfinite(gm) and gm > 0) else 100.0)
            else:
                row_max = np.nanmax(arr, axis=1) * 1.2
        indicator = []
        for n, m in zip(safe_str_list(df[x]), row_max):
            mv = sanitize_value(float(m))
            indicator.append({'name': n, 'max': mv if mv is not None else 100})
        opt['radar'] = {'indicator': indicator, 'shape': 'polygon'}
        # 每个数值列(y)是一个独立系列，共用同一套 indicator；
        # value 与 indicator 一一对应，长度必须一致；NaN 填充为 0 以保持多边形闭合，
        # 与上方 indicator max 计算忽略 NaN 的语义一致（缺失维度按 0 分呈现）。
        # 系列名：--series-name(s) 优先，缺省用列名；data[0].name 与 series.name 同源，
        # 否则 tooltip 会残留英文列名（radar 的 tooltip 显示 data.name 而非 series.name）。
        opt['series'] = []
        for i, c in enumerate(y):
            sname = (ctx.series_names[i] if ctx.series_names and i < len(ctx.series_names) else str(c))
            opt['series'].append({
                'name': sname,
                'type': 'radar',
                'data': [{
                    'name': sname,
                    'value': [0 if pd.isna(v) else sanitize_value(v) for v in df[c].tolist()],
                }],
            })
        return opt

    def _heatmap(self, ctx: RenderContext):
        df, x, y = ctx.df, ctx.x, ctx.y
        x_data = safe_str_list(df[x])
        y_data = y
        opt = self._base(ctx, x_data_len=len(y_data), y_data_len=len(x_data))
        # item tooltip 显示 "行标签 × 列标签: 值"，而非默认的坐标索引数组
        ctx.js[ITEM_TOOLTIP_PLACEHOLDER] = (
            "function(p) {\n"
            f"  var xs = {_js_dumps(y_data)};\n"
            f"  var ys = {_js_dumps(x_data)};\n"
            "  " + ESC_JS_FN +
            "  var fmt = function(v) { return (typeof v === 'number') ? v.toLocaleString() : esc(v); };\n"
            "  return esc(ys[p.value[1]]) + ' × ' + esc(xs[p.value[0]]) + ': ' + fmt(p.value[2]);\n"
            "}"
        )
        opt['tooltip'] = {'position': 'top', 'formatter': ITEM_TOOLTIP_PLACEHOLDER}
        # 向量化取值：一次转 NumPy 数组，替代逐单元格 df.iloc[i][col]（每次都构造 Series，大矩阵慢百倍）
        arr = np.round(df[y_data].to_numpy(dtype='float64'), 2)
        # NaN/Inf → None，与 sanitize_value 语义一致
        matrix = [[j, i, (float(arr[i, j]) if np.isfinite(arr[i, j]) else None)]
                  for i in range(arr.shape[0]) for j in range(arr.shape[1])]
        finite = arr[np.isfinite(arr)]
        vmin = float(finite.min()) if finite.size else 0
        vmax = float(finite.max()) if finite.size else 100
        opt['xAxis'] = {'type': 'category', 'data': y_data, 'splitArea': {'show': True}}
        rot = _maybe_rotate_labels(y_data)
        if rot:
            opt['xAxis']['axisLabel'] = rot
        opt['yAxis'] = {'type': 'category', 'data': x_data, 'splitArea': {'show': True}}
        # visualMap 已承担数值图例职责，series 图例只会显示图表类型名（"热力图"），移除
        opt.pop('legend', None)
        # visualMap 放在图表左侧纵向显示，不遮挡图表正文区域。
        # 渐变语义：全非负（顺序数据）→ 主题单色渐变浅→深；含负值（发散数据，
        # 如相关矩阵）→ 双色渐变 + 中性中点，避免负值被默认三色渐变错误呈现
        grad = ctx.theme['diverging'] if vmin < 0 else ctx.theme['sequential']
        opt['visualMap'] = {'min': vmin, 'max': vmax, 'calculable': True,
                            'orient': 'vertical', 'left': '1%', 'bottom': '10%',
                            'inRange': {'color': list(grad)}}
        opt['grid']['left'] = '10%'  # 为左侧 visualMap 留出空间
        opt['series'] = [{'name': ctx.texts['series_heatmap'], 'type': 'heatmap', 'data': matrix, 'label': {'show': True}}]
        return opt

    def _treemap(self, ctx: RenderContext):
        df, x, y = ctx.df, ctx.x, ctx.y
        opt = self._base(ctx)
        opt['tooltip'] = {'trigger': 'item'}
        # 区块上已有名称标签，series 图例只显示图表类型名，移除
        opt.pop('legend', None)
        y_col = y[0] if y else df.columns[-1]
        data = name_value_pairs(df[x].tolist(), df[y_col].tolist())
        opt['series'] = [{'name': ctx.texts['series_treemap'], 'type': 'treemap', 'data': data, 'roam': False, 'breadcrumb': {'show': True}}]
        return opt

    def _graph(self, ctx: RenderContext):
        df, x, y = ctx.df, ctx.x, ctx.y
        opt = self._base(ctx)
        # source/target 由 --x-axis/--y-axis 显式指定（x=source，y[0]=target，y[1]=可选权重）。
        # 不做列名词表猜测；缺失时报错（链式流程可先 transform 成 source/target 两列）。
        source_col = x
        target_col = y[0] if y else None
        weight_col = y[1] if y and len(y) > 1 else None
        if not (source_col and target_col) or source_col not in df.columns or target_col not in df.columns:
            raise ChartError(
                "关系图需要 来源列(x) + 去向列(y) 两列（可选 权重列）",
                ErrorCode.CHART_CONFIG_ERROR,
                details={'available': list(df.columns),
                         'suggestion': '用 --x-axis <来源列> --y-axis <去向列> [<权重列>] 显式指定'},
            )

        node_names = dict.fromkeys(safe_str_list(df[source_col]) + safe_str_list(df[target_col]))
        nodes = [{'name': n} for n in node_names]
        src_list = df[source_col].tolist()
        tgt_list = df[target_col].tolist()
        has_weight = weight_col and weight_col in df.columns
        w_list = df[weight_col].tolist() if has_weight else None
        links = []
        for i in range(len(src_list)):
            link = {'source': str(src_list[i]), 'target': str(tgt_list[i])}
            if has_weight:
                w = sanitize_value(float(w_list[i]))
                if w is not None:
                    link['value'] = w
            links.append(link)

        opt['tooltip'] = {'trigger': 'item'}
        # 节点上已有名称标签，series 图例只显示图表类型名，移除
        opt.pop('legend', None)
        opt['series'] = [{'name': ctx.texts['series_graph'], 'type': 'graph', 'layout': 'force', 'data': nodes, 'links': links,
                          'roam': True, 'label': {'show': True}, 'force': {'repulsion': 200, 'edgeLength': [50, 150]}}]
        return opt

    def _boxplot(self, ctx: RenderContext):
        df, y = ctx.df, ctx.y
        opt = self._base(ctx)
        opt['tooltip'] = {'trigger': 'item', 'axisPointer': {'type': 'shadow'}}
        cols = y if len(y) > 0 else df.select_dtypes(include=[np.number]).columns[:5].tolist()
        box_data = []
        outlier_data = []  # 格式: [[categoryIndex, value], ...]
        for cat_idx, col in enumerate(cols):
            s = df[col].dropna()
            if s.empty:
                box_data.append([0, 0, 0, 0, 0])
                continue
            # IQR 须线与离群点判定引用共享计算核（与 plot_stats 同源）
            st = box_stats(s)
            box_data.append([st['min'], st['q1'], st['median'], st['q3'], st['max']])
            # ECharts scatter 在 category xAxis 下需要 [xIndex, yValue] 格式
            for idx, val in st['outliers'].items():
                pt = {'value': [cat_idx, sanitize_value(float(val))]}
                if ctx.label_col is not None:
                    lv = df.loc[idx, ctx.label_col]
                    pt['name'] = '' if pd.isna(lv) else str(lv)
                outlier_data.append(pt)
        opt['xAxis'] = {'type': 'category', 'data': cols, 'boundaryGap': True}
        rot = _maybe_rotate_labels(cols)
        if rot:
            opt['xAxis']['axisLabel'] = rot
        opt['yAxis'] = {'type': 'value'}
        # 离群点 tooltip：显示身份（label_col）+ 所属列名 + 值，而非默认的坐标数组
        ctx.js[ITEM_TOOLTIP_PLACEHOLDER] = (
            "function(p) {\n"
            f"  var cols = {_js_dumps(cols)};\n"
            "  " + ESC_JS_FN +
            "  var s = p.name ? '<b>' + esc(p.name) + '</b><br/>' : '';\n"
            "  return s + esc(cols[p.value[0]]) + ': ' + p.value[1];\n"
            "}"
        )
        opt['series'] = [
            {'name': ctx.texts['series_boxplot'], 'type': 'boxplot', 'data': box_data},
            {'name': ctx.texts['series_outliers'], 'type': 'scatter', 'data': outlier_data, 'symbolSize': 8,
             'tooltip': {'formatter': ITEM_TOOLTIP_PLACEHOLDER}},
        ]
        return opt

    def _waterfall(self, ctx: RenderContext):
        """瀑布图：透明垫底 series + 增量 series（stack 实现悬浮柱）。

        增量值可正可负：柱高取绝对值，垫底高度取累计起点，保证柱子"悬浮"；
        每个柱子的 label 和 tooltip 显示带符号的原始增量，避免绝对值造成误读。
        垫底 series 透明、silent、不进 legend、tooltip 不显示。
        累计走查引用共享计算核 waterfall_walk（与 plot_stats 同源）。
        """
        df, x, y = ctx.df, ctx.x, ctx.y
        y_col = y[0] if y else df.columns[-1]
        x_data = safe_str_list(df[x])
        base, heights, signeds, _stats = waterfall_walk(df[y_col].tolist())
        bars = [{'value': h, 'label': {'formatter': s}} for h, s in zip(heights, signeds)]
        opt = self._base(ctx, x_data_len=len(x_data))
        opt['xAxis'] = {'type': 'category', 'data': x_data}
        rot = _maybe_rotate_labels(x_data)
        if rot:
            opt['xAxis']['axisLabel'] = rot
        opt['yAxis'] = {'type': 'value'}
        opt['graphic'] = _axis_name_graphics(ctx.theme, x, [y_col], x_data_len=len(x_data))
        # 图例只保留增量系列（垫底辅助系列不显示）
        opt['legend'] = {'top': 'bottom', 'type': 'scroll', 'data': [y_col]}
        ctx.js[WATERFALL_TOOLTIP_PLACEHOLDER] = (
            "function(p) {\n"
            "  " + ESC_JS_FN +
            "  var v = (p.data && p.data.label) ? p.data.label.formatter : p.value;\n"
            f"  return '<b>' + esc(p.name) + '</b><br/>' + esc(p.seriesName) + ': ' + v;\n"
            "}"
        )
        opt['tooltip'] = {'trigger': 'item', 'formatter': WATERFALL_TOOLTIP_PLACEHOLDER}
        opt['series'] = [
            {'name': '__waterfall_base__', 'type': 'bar', 'stack': 'waterfall', 'silent': True,
             'itemStyle': {'color': 'transparent'}, 'emphasis': {'itemStyle': {'color': 'transparent'}},
             'tooltip': {'show': False}, 'data': base},
            {'name': y_col, 'type': 'bar', 'stack': 'waterfall', 'data': bars,
             'label': {'show': True, 'position': 'top'}, 'itemStyle': {'color': ctx.theme['primary']}},
        ]
        return opt

    def _gauge(self, ctx: RenderContext):
        df, y = ctx.df, ctx.y
        num_cols = df.select_dtypes(include=[np.number]).columns
        y_col = y[0] if y else (num_cols[0] if len(num_cols) else None)
        if y_col is None:
            raise ChartError(
                "仪表盘需要至少一个数值列",
                ErrorCode.CHART_CONFIG_ERROR,
                details={'suggestion': '提供数值类型的列，或用 transform_code 生成数值列'},
            )
        value = sanitize_value(float(df[y_col].mean()))
        if value is None:
            value = 0
        # 量程（满刻度）：业务目标 --target 优先（满刻度 = 目标值，指针位置即达成率）；
        # 缺省回落到共享计算核 gauge_scale（≤1 比率 → 1.0；≤100 得分/百分比 → 100；
        # 其余 ×1.05；全 NaN 列兜底 100）。与 plot_stats 的 achievement 同源。
        if ctx.target:
            max_val = sanitize_value(float(ctx.target))
        else:
            max_val = sanitize_value(gauge_scale(float(df[y_col].max())))
        if max_val is None:
            max_val = 100
        opt = {'title': {'text': ctx.title, 'left': 'center'}, 'color': list(ctx.theme['palette'])}
        stops = ctx.theme['gauge_stops']
        # 系列名：--series-name 优先，缺省用列名（不再用类型名「仪表盘」）；
        # data[0].name 与 series.name 同源，tooltip 不再残留英文列名。
        series_name = (ctx.series_names[0] if ctx.series_names else y_col)
        opt['series'] = [{'name': series_name, 'type': 'gauge', 'max': max_val,
                          'detail': {'formatter': '{value}'},
                          'data': [{'value': value, 'name': series_name}],
                          'axisLine': {'lineStyle': {'width': 10, 'color': [[0.3, stops[0]], [0.7, stops[1]], [1, stops[2]]]}}}]
        return opt

    def _sankey(self, ctx: RenderContext):
        df, x, y = ctx.df, ctx.x, ctx.y
        opt = {'title': {'text': ctx.title, 'left': 'center'}, 'color': list(ctx.theme['palette'])}
        # source/target 由 --x-axis/--y-axis 显式指定（x=source，y[0]=target，y[1]=可选值列）。
        source_col = x
        target_col = y[0] if y else None
        value_col = y[1] if y and len(y) > 1 else None
        if not (source_col and target_col) or source_col not in df.columns or target_col not in df.columns:
            raise ChartError(
                "桑基图需要 来源列(x) + 去向列(y) 两列（可选 值列）",
                ErrorCode.CHART_CONFIG_ERROR,
                details={'available': list(df.columns),
                         'suggestion': '用 --x-axis <来源列> --y-axis <去向列> [<值列>] 显式指定'},
            )

        nodes, links = [], []
        node_names = dict.fromkeys(safe_str_list(df[source_col]) + safe_str_list(df[target_col]))
        nodes = [{'name': n} for n in node_names]
        src_list = df[source_col].tolist()
        tgt_list = df[target_col].tolist()
        has_value = value_col and value_col in df.columns
        v_list = df[value_col].tolist() if has_value else None
        for i in range(len(src_list)):
            val = 1
            if has_value:
                v = sanitize_value(float(v_list[i]))
                val = v if v is not None else 1
            links.append({'source': str(src_list[i]), 'target': str(tgt_list[i]), 'value': val})

        opt['tooltip'] = {'trigger': 'item'}
        opt['series'] = [{'name': ctx.texts['series_sankey'], 'type': 'sankey', 'data': nodes, 'links': links,
                          'emphasis': {'focus': 'adjacency'}, 'lineStyle': {'curveness': 0.5}}]
        return opt

    def _funnel(self, ctx: RenderContext):
        df, x, y = ctx.df, ctx.x, ctx.y
        opt = self._base(ctx)
        y_col = y[0] if y else df.columns[-1]
        data = name_value_pairs(df[x].tolist(), df[y_col].tolist())
        all_vals = [d['value'] for d in data if d['value'] is not None]
        max_val = max(all_vals) if all_vals else 100
        opt['series'] = [{'name': ctx.texts['series_funnel'], 'type': 'funnel', 'left': '10%', 'top': 60, 'bottom': 60, 'width': '80%',
                          'min': 0, 'max': max_val, 'sort': 'descending', 'gap': 2,
                          'label': {'show': True, 'position': 'inside'},
                          'data': data}]
        return opt

    def _sunburst(self, ctx: RenderContext):
        df, x, y = ctx.df, ctx.x, ctx.y
        opt = {'title': {'text': ctx.title, 'left': 'center'}, 'color': list(ctx.theme['palette'])}
        y_col = y[0] if y else df.columns[-1]
        data = name_value_pairs(df[x].tolist(), df[y_col].tolist())
        opt['series'] = [{'name': ctx.texts['series_sunburst'], 'type': 'sunburst', 'data': data, 'radius': [0, '90%'],
                          'label': {'rotate': 'radial'}}]
        return opt

    def _wordcloud(self, ctx: RenderContext):
        df, x, y = ctx.df, ctx.x, ctx.y
        opt = {'title': {'text': ctx.title, 'left': 'center'}, 'color': list(ctx.theme['palette'])}
        y_col = y[0] if y else df.columns[-1]
        data = name_value_pairs(df[x].tolist(), df[y_col].tolist())
        opt['series'] = [{'name': ctx.texts['series_wordcloud'], 'type': 'wordCloud', 'shape': 'circle',
                          'sizeRange': [12, 60], 'rotationRange': [-90, 90], 'rotationStep': 45,
                          'data': data}]
        return opt

    def _histogram(self, ctx: RenderContext):
        """直方图：对连续数值列分箱后用 bar 渲染（barCategoryGap=0 消除间隙）。

        与 bar 的本质区别：bar 用于离散类别比较，histogram 用于连续变量分布形状展示。
        分箱引用共享计算核 sturges_bins（与 plot_stats 同源）。
        """
        df, y = ctx.df, ctx.y
        num_cols = df.select_dtypes(include=[np.number]).columns
        y_col = y[0] if y else (num_cols[0] if len(num_cols) else None)
        if y_col is None:
            raise ChartError(
                "直方图需要至少一个数值列",
                ErrorCode.CHART_CONFIG_ERROR,
                details={'suggestion': '提供数值类型的列，或用 transform_code 生成数值列'},
            )
        s = df[y_col].dropna()
        if s.empty:
            raise ChartError(
                f"列 {y_col} 无有效数值，无法生成直方图",
                ErrorCode.DATA_EMPTY,
                details={'column': y_col, 'suggestion': '选择数值类型的列'},
            )
        counts, edges = sturges_bins(s)
        labels = bin_labels(edges, counts)
        opt = self._base(ctx, x_data_len=len(labels))
        opt['tooltip'] = {'trigger': 'item', 'formatter': '{b}<br/>{c}'}
        opt['xAxis'] = {'type': 'category', 'data': labels}
        rot = _maybe_rotate_labels(labels)
        if rot:
            opt['xAxis']['axisLabel'] = rot
        opt['yAxis'] = {'type': 'value'}
        # x 轴名底距由 _axis_name_graphics 按 x_data_len 是否超过 dataZoom 阈值自动选择
        # （64 避开底部滑块 / 42 常规），不再在此复制 64/42 魔法数
        opt['graphic'] = _axis_name_graphics(ctx.theme, y_col, [ctx.texts['axis_frequency']], x_data_len=len(labels))
        opt['series'] = [{
            'name': y_col, 'type': 'bar', 'data': counts.tolist(),
            'barCategoryGap': '0%',  # 直方图无间隙
            'itemStyle': {'color': ctx.theme['primary']},
        }]
        return opt

    def _stacked_bar(self, ctx: RenderContext):
        """堆叠柱状图：复用 _bar 后为每个 series 加 stack 字段。"""
        opt = self._bar(ctx)
        for s in opt['series']:
            s['stack'] = 'total'
            s['emphasis'] = {'focus': 'series'}
        return opt

    def _bubble(self, ctx: RenderContext):
        """气泡图：3 列数值（x, y, size），symbolSize 按第三列缩放。"""
        df, x, y = ctx.df, ctx.x, ctx.y
        opt = self._base(ctx)
        if len(y) < 2:
            raise ChartError(
                "气泡图至少需要 2 个 Y 轴数值列（y 值 + size 值）",
                ErrorCode.CHART_CONFIG_ERROR,
                details={'given_y': y, 'suggestion': '提供 --y-axis <y_col> <size_col> 两个数值列'},
            )
        y_col, size_col = y[0], y[1]
        if not pd.api.types.is_numeric_dtype(df[x]):
            raise ChartError(
                f"气泡图的 X 轴需要数值列，当前列 '{x}' 不是数值类型",
                ErrorCode.CHART_CONFIG_ERROR,
                details={'given_x': x, 'suggestion': '选择数值类型的 X 轴列，或用 transform_code 生成数值列'},
            )
        label_col, color_col = ctx.label_col, ctx.color_by
        numeric_color = color_col is not None and pd.api.types.is_numeric_dtype(df[color_col])
        max_size = float(df[size_col].max())
        if max_size <= 0 or np.isnan(max_size):
            max_size = 1.0
        opt['xAxis'] = {'type': 'value', 'scale': True}
        opt['yAxis'] = {'type': 'value', 'scale': True}
        opt['graphic'] = _axis_name_graphics(ctx.theme, x, [y_col])
        # tooltip / symbolSize 是 JS 函数（ECharts 字符串模板不支持 {c[0]} 数组索引），
        # 占位符写进 option，真正的 JS 函数收集到 ctx.js，由 template 层替换。
        # tooltip 显示 身份（label_col）+ 各维度 "列名: 值"
        # tooltip 维度名跟随 --x-name/--y-name（缺省回落列名），否则悬停仍显示英文列名
        x_disp = ctx.x_name if ctx.x_name else x
        y0_disp = (ctx.y_names[0] if ctx.y_names and len(ctx.y_names) > 0 else y_col)
        y1_disp = (ctx.y_names[1] if ctx.y_names and len(ctx.y_names) > 1 else size_col)
        dims = [x_disp, y0_disp, y1_disp] + ([color_col] if numeric_color else [])
        ctx.js[BUBBLE_TOOLTIP_PLACEHOLDER] = _point_tooltip_js(dims, has_label=label_col is not None)
        opt['tooltip'] = {'trigger': 'item', 'formatter': BUBBLE_TOOLTIP_PLACEHOLDER}
        ctx.js[BUBBLE_SYMBOLSIZE_PLACEHOLDER] = f'function(v){{ return Math.sqrt(v[2]/{max_size})*50+5; }}'

        def _series(sub):
            return {'type': 'scatter', 'symbolSize': BUBBLE_SYMBOLSIZE_PLACEHOLDER,
                    'data': _labeled_points(sub, x, [y_col, size_col], label_col,
                                            color_col if numeric_color else None, True)}

        if color_col is not None and not numeric_color:
            # 类别列 → 按类别拆 series（NaN 归入"未分类"，不静默丢点）
            color_s = df[color_col].where(df[color_col].notna(), ctx.texts['series_uncategorized']).astype(str)
            opt['series'] = [dict(_series(df[color_s == cat]), name=cat) for cat in color_s.unique()]
        else:
            opt['series'] = [dict(_series(df), name=ctx.texts['series_bubble'])]
            if numeric_color:
                cvals = [p['value'][3] for p in opt['series'][0]['data'] if p['value'][3] is not None]
                if cvals:
                    opt['visualMap'] = {'min': min(cvals), 'max': max(cvals), 'dimension': 3,
                                        'calculable': True, 'orient': 'vertical', 'right': '1%', 'top': 'center'}
                    opt['grid']['right'] = '10%'  # 为右侧 visualMap 留出空间
        return opt

    def _pareto(self, ctx: RenderContext):
        """帕累托图：排序后的 bar + 累积百分比折线（双 yAxis）。

        累计百分比引用共享计算核 pareto_stats（与 plot_stats 同源）。
        """
        df, x, y = ctx.df, ctx.x, ctx.y
        num_cols = df.select_dtypes(include=[np.number]).columns
        y_col = y[0] if y else (num_cols[0] if len(num_cols) else None)
        if y_col is None:
            raise ChartError(
                "帕累托图需要至少一个数值列",
                ErrorCode.CHART_CONFIG_ERROR,
                details={'suggestion': '提供数值类型的列，或用 transform_code 生成数值列'},
            )
        df_s = df[[x, y_col]].dropna().sort_values(y_col, ascending=False).reset_index(drop=True)
        x_data = safe_str_list(df_s[x])
        vals = sanitize_series(df_s[y_col].tolist())
        cum = pareto_stats(vals)['cum_pct']
        opt = self._base(ctx, x_data_len=len(x_data))
        opt['tooltip'] = {'trigger': 'axis', 'formatter': TOOLTIP_FORMATTER_AXIS}
        x_axis = {'type': 'category', 'data': x_data}
        rot = _maybe_rotate_labels(x_data)
        if rot:
            x_axis['axisLabel'] = rot
        opt['xAxis'] = [x_axis]
        opt['yAxis'] = [
            {'type': 'value', 'position': 'left'},
            {'type': 'value', 'max': 100, 'position': 'right',
             'axisLabel': {'formatter': '{value}%'}},
        ]
        opt['graphic'] = _axis_name_graphics(ctx.theme, x, [y_col, '%'], x_data_len=len(x_data))
        opt['series'] = [
            {'name': y_col, 'type': 'bar', 'data': vals, 'yAxisIndex': 0,
             'itemStyle': {'color': ctx.theme['primary']}},
            {'name': ctx.texts['series_pareto'], 'type': 'line', 'data': cum, 'yAxisIndex': 1,
             'lineStyle': {'color': ctx.theme['secondary']}, 'symbol': 'circle', 'symbolSize': 6},
        ]
        return opt

    def _combo(self, ctx: RenderContext):
        """组合图（双轴）：第一个 Y 列走 bar（左轴），其余 Y 列走 line（右轴）。"""
        df, x, y = ctx.df, ctx.x, ctx.y
        if len(y) < 2:
            raise ChartError(
                "组合图至少需要 2 个 Y 轴列（bar 列 + line 列）",
                ErrorCode.CHART_CONFIG_ERROR,
                details={'given_y': y, 'suggestion': '提供 --y-axis <bar_col> <line_col> [<line_col> ...]'},
            )
        x_data = safe_str_list(df[x])
        opt = self._base(ctx, x_data_len=len(x_data))
        opt['tooltip'] = {'trigger': 'axis', 'formatter': TOOLTIP_FORMATTER_AXIS}
        bar_col, line_cols = y[0], y[1:]
        x_axis = {'type': 'category', 'data': x_data}
        rot = _maybe_rotate_labels(x_data)
        if rot:
            x_axis['axisLabel'] = rot
        opt['xAxis'] = [x_axis]
        opt['yAxis'] = [
            {'type': 'value', 'position': 'left'},
            {'type': 'value', 'position': 'right',
             'axisLabel': {'formatter': '{value}'}},
        ]
        # bar 系列零基线契约（与 _bar 一致）：bar 列全非负时左轴显式 min:0
        if _all_nonnegative(df, [bar_col]):
            opt['yAxis'][0]['min'] = 0
        opt['graphic'] = _axis_name_graphics(ctx.theme, x, [bar_col, ' / '.join(line_cols)], x_data_len=len(x_data))
        series = [{
            'name': bar_col, 'type': 'bar', 'data': sanitize_series(df[bar_col].tolist()),
            'yAxisIndex': 0, 'itemStyle': {'color': ctx.theme['primary']},
        }]
        line_colors = ctx.theme['palette'][1:5]
        for i, col in enumerate(line_cols):
            series.append({
                'name': col, 'type': 'line', 'data': sanitize_series(df[col].tolist()),
                'yAxisIndex': 1, 'smooth': True,
                'lineStyle': {'color': line_colors[i % len(line_colors)]},
            })
        opt['series'] = series
        return opt

    # ---- venn / mindmap / orgchart / liquid ----

    def _venn(self, ctx: RenderContext):
        """维恩图：2~3 个集合的交集/并集可视化（ECharts 无内建 venn 系列，用 graphic 圆绘制）。

        数据契约（B 家族）：x = 集合名列，y[0] = 数值列。集合名含分隔符（∩ & + × 与）
        的行解析为交集，如 "A∩B"；数值列为分类列时退化为 x 频数统计。
        """
        df, x, y = ctx.df, ctx.x, ctx.y
        y_col = y[0] if y else df.columns[-1]
        if pd.api.types.is_numeric_dtype(df[y_col]):
            raw = {}
            for n, v in zip(safe_str_list(df[x]), df[y_col].tolist()):
                if n and pd.notna(v):
                    raw[n] = raw.get(n, 0.0) + float(v)
        else:
            raw = {str(k): float(c) for k, c in df[x].astype(str).value_counts().items()}
        sep_re = re.compile(r'[∩&+×]|与')
        # 两遍解析：先收简单集合，再解析交集行（成员按名称精确或包含匹配到简单集合）
        sets: Dict[str, float] = {}
        compound: List[Tuple[str, float]] = []
        for name, v in raw.items():
            if sep_re.search(name):
                compound.append((name, v))
            else:
                sets[name] = v
        if len(sets) < 2:
            raise ChartError(
                "维恩图至少需要 2 个不含分隔符（∩ & + × 与）的独立集合行",
                ErrorCode.CHART_CONFIG_ERROR,
                details={'given_sets': list(sets), 'suggestion': '每行一个集合（如 手机用户/电脑用户），交集行命名为 集合A∩集合B'},
            )
        if len(sets) > 3:
            raise ChartError(
                "维恩图最多支持 3 个集合",
                ErrorCode.CHART_CONFIG_ERROR,
                details={'given_sets': list(sets), 'suggestion': '取最关注的 3 个集合，其余用 pie/treemap 呈现'},
            )
        names = list(sets)
        # 半径 ∝ sqrt(值)（面积正比于数值），最大半径 150px
        k = 150.0 / max(math.sqrt(v) for v in sets.values())
        radii = {n: k * math.sqrt(sets[n]) for n in names}
        # 画布尺寸来自 RenderContext（与落盘尺寸同源，--width/--height 对 venn 布局生效）：
        # 先在相对坐标系布局，再整体平移/缩放适配画布。
        # 圆用 shape.cx/cy（px 坐标），文本用 left/top(px) + align/verticalAlign 居中锚定
        CW, CH = float(ctx.width), float(ctx.height)
        OVERLAP = 0.72  # 圆心距系数：0.72*(r1+r2) < r1+r2，保证任意两圆相交
        centers = {}
        if len(names) == 2:
            a, b = names
            d = OVERLAP * (radii[a] + radii[b])
            centers[a] = (0.0, 0.0)
            centers[b] = (d, 0.0)
        else:
            # 3 集合：三边定位法。A 在原点、B 在 x 轴，C 由 d_ac/d_bc 解交点；
            # 目标距离恒满足三角不等式（r3>0），交点必有解
            a, b, c = names
            d_ab = OVERLAP * (radii[a] + radii[b])
            d_ac = OVERLAP * (radii[a] + radii[c])
            d_bc = OVERLAP * (radii[b] + radii[c])
            centers[a] = (0.0, 0.0)
            centers[b] = (d_ab, 0.0)
            x_c = (d_ab ** 2 + d_ac ** 2 - d_bc ** 2) / (2 * d_ab)
            h2 = d_ac ** 2 - x_c ** 2
            centers[c] = (x_c, -math.sqrt(h2) if h2 > 0 else 0.0)  # 负 y = 画布上方
        # 包围盒适配：等比缩放 + 居中平移，保证所有圆完整显示在画布内
        min_x = min(centers[n][0] - radii[n] for n in names)
        max_x = max(centers[n][0] + radii[n] for n in names)
        min_y = min(centers[n][1] - radii[n] for n in names)
        max_y = max(centers[n][1] + radii[n] for n in names)
        margin_t, margin_b, side = 80.0, 40.0, 40.0
        scale = min((CW - 2 * side) / (max_x - min_x),
                    (CH - margin_t - margin_b) / (max_y - min_y), 1.0)
        ox = (CW - (max_x - min_x) * scale) / 2
        oy = margin_t + (CH - margin_t - margin_b - (max_y - min_y) * scale) / 2
        for n in names:
            centers[n] = (ox + (centers[n][0] - min_x) * scale,
                          oy + (centers[n][1] - min_y) * scale)
            radii[n] *= scale
        # 圆心整体质心（集合标签向外偏移的基准）
        gx = sum(centers[n][0] for n in names) / len(names)
        gy = sum(centers[n][1] for n in names) / len(names)

        palette = ctx.theme['palette']
        graphics = []
        for i, n in enumerate(names):
            px, py = centers[n]
            graphics.append({
                'id': f'venn-set-{i}', 'type': 'circle',
                'shape': {'cx': round(px, 1), 'cy': round(py, 1), 'r': round(radii[n], 1)},
                'style': {'fill': palette[i % len(palette)], 'opacity': 0.55},
            })
        # 集合标签：名称 + 数值，向质心反方向偏移，避免与交集标签重叠
        for i, n in enumerate(names):
            dx, dy = centers[n][0] - gx, centers[n][1] - gy
            dist = math.hypot(dx, dy) or 1.0
            lx, ly = centers[n][0] + dx / dist * radii[n] * 0.45, centers[n][1] + dy / dist * radii[n] * 0.45
            graphics.append({
                'id': f'venn-label-{i}', 'type': 'text',
                'left': round(lx), 'top': round(ly),
                'style': {'text': f'{n}\n{fmt_num(sets[n])}', 'fontSize': 14, 'fontWeight': 'bold',
                          'fill': ctx.theme['graphic_text'], 'align': 'center', 'verticalAlign': 'middle'},
            })
        # 交集标签：2 成员放两圆重叠段中点（圆心连线上、双方圆边之间），
        # 3 成员放三圆心重心；只匹配到 1 个集合的行无法定位，跳过
        for name, v in compound:
            parts = [p.strip() for p in sep_re.split(name) if p.strip()]
            members = []
            for p in parts:
                for n in names:
                    if n not in members and (p == n or p in n or n in p):
                        members.append(n)
                        break
            if len(members) < 2:
                continue
            if len(members) == 2:
                m1, m2 = members[0], members[1]
                x1, y1 = centers[m1]
                x2, y2 = centers[m2]
                d = math.hypot(x2 - x1, y2 - y1) or 1.0
                # 重叠段自 c1 的范围 [d - r2, r1]，取中点并钳制，避免标签贴边
                t = ((d - radii[m2]) + radii[m1]) / 2 / d
                t = max(0.2, min(0.8, t))
                mx, my = x1 + (x2 - x1) * t, y1 + (y2 - y1) * t
            else:
                mx = sum(centers[m][0] for m in members) / len(members)
                my = sum(centers[m][1] for m in members) / len(members)
            graphics.append({
                'type': 'text', 'left': round(mx), 'top': round(my),
                'style': {'text': fmt_num(v), 'fontSize': 12,
                          'fill': ctx.theme['graphic_text'], 'align': 'center', 'verticalAlign': 'middle'},
            })
        opt = {'title': {'text': ctx.title, 'left': 'center', 'textStyle': {'fontSize': 16}},
               'color': list(palette), 'series': [], 'graphic': graphics}
        return opt

    @staticmethod
    def _build_tree(edges):
        """由 (父, 子) 边列表构建树森林，返回根节点列表（ECharts tree data 格式）。

        环状脏数据防御：递归构建时跳回已访问节点（等价剪掉回边）；
        无根（全循环）时抛错。
        """
        child_map: Dict[str, List[str]] = {}
        children_set = set()
        for p, c in edges:
            child_map.setdefault(p, []).append(c)
            children_set.add(c)
        roots = [p for p in child_map if p not in children_set]
        if not roots:
            raise ChartError(
                "层级数据存在循环引用，无法确定根节点",
                ErrorCode.CHART_CONFIG_ERROR,
                details={'suggestion': '检查父/子列，确保至少存在一个只作父节点、从不作子节点的根'},
            )

        def build(name, seen):
            node = {'name': name}
            kids = []
            for c in child_map.get(name, []):
                if c in seen:  # 环防御：跳过回边
                    continue
                kids.append(build(c, seen | {c}))
            if kids:
                node['children'] = kids
            return node

        return [build(r, {r}) for r in roots]

    def _mindmap(self, ctx: RenderContext):
        """思维导图：LR 布局的 tree 系列，按顶级分支着色（调色板），根节点强调。"""
        df, x, y = ctx.df, ctx.x, ctx.y
        parent_col, child_col = x, y[0]
        edges = [(p, c) for p, c in zip(safe_str_list(df[parent_col]), safe_str_list(df[child_col]))
                 if p and c]
        if not edges:
            raise ChartError(
                "思维导图需要有效的 父→子 边（父/子列均非空）",
                ErrorCode.DATA_EMPTY,
                details={'parent_col': parent_col, 'child_col': child_col},
            )
        roots = self._build_tree(edges)
        theme = ctx.theme
        palette = theme['palette']
        # 多根时挂虚拟根（隐藏标签与连线），保证单棵树渲染
        if len(roots) == 1:
            tree_data = roots[0]
        else:
            tree_data = {'name': '', 'children': roots,
                         'label': {'show': False}, 'lineStyle': {'width': 0}, 'itemStyle': {'color': 'transparent'}}

        def paint(node, color, is_root=False):
            node['itemStyle'] = {'color': color, 'borderColor': color}
            node['label'] = {'fontSize': 14 if is_root else 12,
                             'fontWeight': 'bold' if is_root else 'normal',
                             'color': theme['graphic_text'] or '#333'}
            node['symbolSize'] = 16 if is_root else 9
            for c in node.get('children', []):
                paint(c, color)
        # 顶级分支各分配一个调色板色，整支同色（思维导图的分支色语义）
        top = tree_data.get('children', [])
        if tree_data.get('name') != '':
            paint(tree_data, theme['primary'], is_root=True)
            for i, c in enumerate(tree_data.get('children', [])):
                paint(c, palette[(i + 1) % len(palette)])
        else:
            for i, c in enumerate(top):
                paint(c, palette[i % len(palette)], is_root=True)
                for gc in c.get('children', []):
                    paint(gc, palette[i % len(palette)])
        opt = {'title': {'text': ctx.title, 'left': 'center', 'textStyle': {'fontSize': 16}},
               'tooltip': {'trigger': 'item', 'triggerOn': 'mousemove'},
               'color': list(palette),
               'series': [{'name': ctx.texts['series_mindmap'], 'type': 'tree', 'data': [tree_data],
                           'orient': 'LR', 'left': '8%', 'right': '22%', 'top': '8%', 'bottom': '8%',
                           'symbol': 'circle', 'edgeShape': 'curve',
                           'lineStyle': {'width': 2, 'curveness': 0.5},
                           'label': {'position': 'right', 'distance': 5},
                           'leaves': {'label': {'position': 'right', 'distance': 5}},
                           'expandAndCollapse': False,
                           'initialTreeDepth': -1,
                           'animationDuration': 400}]}
        return opt

    def _orgchart(self, ctx: RenderContext):
        """组织架构图：TB 布局的 tree 系列，矩形节点 + 折线连线，统一主色。"""
        df, x, y = ctx.df, ctx.x, ctx.y
        parent_col, child_col = x, y[0]
        edges = [(p, c) for p, c in zip(safe_str_list(df[parent_col]), safe_str_list(df[child_col]))
                 if p and c]
        if not edges:
            raise ChartError(
                "组织架构图需要有效的 父→子 边（父/子列均非空）",
                ErrorCode.DATA_EMPTY,
                details={'parent_col': parent_col, 'child_col': child_col},
            )
        roots = self._build_tree(edges)
        primary = ctx.theme['primary']
        if len(roots) == 1:
            tree_data = roots[0]
        else:
            tree_data = {'name': '', 'children': roots,
                         'label': {'show': False}, 'lineStyle': {'width': 0},
                         'itemStyle': {'color': 'transparent', 'borderColor': 'transparent'}}

        def paint(node):
            node['symbol'] = 'rect'
            node['symbolSize'] = [72, 30]
            node['itemStyle'] = {'color': primary, 'borderColor': primary}
            node['label'] = {'position': 'inside', 'color': '#fff', 'fontSize': 12,
                             'overflow': 'truncate', 'width': 68}
            for c in node.get('children', []):
                paint(c)
        paint(tree_data)
        # 虚拟根不渲染盒子
        if tree_data.get('name') == '':
            tree_data['symbolSize'] = [0, 0]
        opt = {'title': {'text': ctx.title, 'left': 'center', 'textStyle': {'fontSize': 16}},
               'tooltip': {'trigger': 'item', 'triggerOn': 'mousemove'},
               'color': [primary],
               'series': [{'name': ctx.texts['series_orgchart'], 'type': 'tree', 'data': [tree_data],
                           'orient': 'TB', 'left': '10%', 'right': '10%', 'top': '10%', 'bottom': '12%',
                           'edgeShape': 'polyline', 'lineStyle': {'width': 1.5},
                           'expandAndCollapse': False,
                           'initialTreeDepth': -1,
                           'animationDuration': 400}]}
        return opt

    def _liquid(self, ctx: RenderContext):
        """水波图（echarts-liquidfill）：单数值列均值 → 百分比进度，主色波浪。

        归一化分母：业务目标 --target 优先（达成率 = 均值 / 目标），缺省回落
        共享计算核 gauge_scale 自动量程（与 plot_stats 的 achievement 同源）。
        系列名：--series-name 优先，缺省用列名；label 第二行跟随系列名，
        使图中文字可自定义（不再写死列名，修复英文列名无法修改）。
        """
        df, y = ctx.df, ctx.y
        num_cols = df.select_dtypes(include=[np.number]).columns
        y_col = y[0] if y else (num_cols[0] if len(num_cols) else None)
        if y_col is None:
            raise ChartError(
                "水波图需要至少一个数值列",
                ErrorCode.CHART_CONFIG_ERROR,
                details={'suggestion': '提供数值类型的列（如完成率），或用 transform_code 生成数值列'},
            )
        value = float(df[y_col].mean())
        # 分母：--target 优先；否则数据 max>100 时 gauge_scale 会走 ×1.05 分支，
        # 导致图内百分比（value/gauge_scale）与标题/解读（value/target）分裂。
        denom = float(ctx.target) if ctx.target else gauge_scale(float(df[y_col].max()))
        frac = max(0.0, min(1.0, value / denom if denom else 0.0))
        pct = round(frac * 100, 1)
        waves = [round(frac, 4), round(frac * 0.9, 4), round(frac * 0.78, 4)]
        primary = ctx.theme['primary']
        # 系列名：--series-name 优先，缺省用列名（不再用类型名「水波图」）；
        # label 第二行跟随系列名，图中文字可自定义。
        series_name = (ctx.series_names[0] if ctx.series_names else y_col)
        # label 用函数 formatter（占位符 → JS 函数）运行时读 chartOption.series[0].name，
        # 使 --series-name 与前端重命名面板改名后，图内第二行文字自动跟随，不再写死列名。
        ctx.js[LIQUID_LABEL_PLACEHOLDER] = (
            f"function() {{ return '{pct}%' + '\\n' + chartOption.series[0].name; }}"
        )
        opt = {'title': {'text': ctx.title, 'left': 'center', 'textStyle': {'fontSize': 16}},
               'series': [{'name': series_name, 'type': 'liquidFill', 'data': waves,
                           'radius': '72%', 'center': ['50%', '52%'],
                           'color': [primary],
                           'backgroundStyle': {'color': ctx.theme['card_bg']},
                           'outline': {'show': True, 'borderDistance': 6,
                                       'itemStyle': {'borderWidth': 2, 'borderColor': primary}},
                           'label': {'fontSize': 34, 'fontWeight': 'bold',
                                     'color': primary, 'position': ['50%', '50%'],
                                     'formatter': LIQUID_LABEL_PLACEHOLDER},
                           'rippleEffect': {'period': 3000}}]}
        return opt

    # ---- P0/P1 新增：map / lines / effect_scatter / calendar / pictorial_bar / theme_river ----

    def _map(self, ctx: RenderContext):
        """地图：地区列 → 数值列的分级着色地图（离线 GeoJSON，默认中国省级）。

        数据契约：x = 地区名列（支持「北京/广东」等简称，china 内置图专用），
        y[0] = 数值列。地图来源由 ctx（--geo 内置图名 / --geo-path 自备文件）决定。
        同地区多行自动求和聚合；无法对齐到 GeoJSON 全称的地区被跳过（全名见
        geojson_region_names），避免静默丢弃——未匹配数量经 plot_stats 披露。
        """
        df, x, y = ctx.df, ctx.x, ctx.y
        y_col = y[0] if y else df.columns[-1]
        geo_names = ctx.geo_names if ctx.geo_names is not None else geojson_region_names(ctx.geo_json or {})
        aliases = ctx.geo_aliases
        # 聚合：地区名 → 值求和（同地区多行合并，口径与 B 家族 name×value 一致）
        agg: Dict[str, float] = {}
        for n, v in zip(df[x].tolist(), df[y_col].tolist()):
            if pd.isna(v):
                continue
            full = resolve_region_name(n, geo_names, aliases)
            if full is None:
                continue
            try:
                agg[full] = agg.get(full, 0.0) + float(v)
            except (TypeError, ValueError):
                continue
        if not agg:
            raise ChartError(
                "地图数据为空：地区列无法与内置地图区域对齐",
                ErrorCode.DATA_EMPTY,
                details={'given_x': x,
                         'suggestion': '地区列使用地图区域全称（china 支持 北京/广东/新疆 等简称），'
                                       '或用 transform_code 归一化'},
            )
        data = [{'name': k, 'value': sanitize_value(v)} for k, v in agg.items()]
        vals = [d['value'] for d in data if d['value'] is not None]
        vmin = min(vals) if vals else 0
        vmax = max(vals) if vals else 100
        if vmin == vmax:  # 单一值时分段图例退化为单色，上浮上限避免 visualMap 报错
            vmax = vmin + 1 if vmin is not None else 100
        opt = {
            'title': {'text': ctx.title, 'left': 'center', 'textStyle': {'fontSize': 16}},
            'tooltip': {'trigger': 'item', 'formatter': '{b}: {c}'},
            'color': list(ctx.theme['palette']),
            'visualMap': {'min': vmin, 'max': vmax, 'calculable': True, 'orient': 'vertical',
                          'left': '1%', 'bottom': '8%',
                          'inRange': {'color': list(ctx.theme['sequential'])}},
            'series': [{
                'name': ctx.texts['series_map'], 'type': 'map', 'map': ctx.geo_map_name,
                'roam': True, 'data': data,
                'label': {'show': False},
                'emphasis': {'label': {'show': True}, 'itemStyle': {'areaColor': ctx.theme['secondary']}},
            }],
        }
        return opt

    def _lines(self, ctx: RenderContext):
        """航线/迁徙图：source/target/value 关系列 → 地图上的流动线条。

        数据契约：source/target 由 --x-axis/--y-axis 显式指定（x=source，y[0]=target，
        y[1]=可选值列）。地图来源由 ctx（--geo / --geo-path）决定。两端地名均需对齐到
        区域全称；无法对齐的边被跳过（全名见 geojson_region_names）。
        """
        df = ctx.df
        source_col = ctx.x
        target_col = ctx.y[0] if ctx.y else None
        value_col = ctx.y[1] if ctx.y and len(ctx.y) > 1 else None
        if not (source_col and target_col) or source_col not in df.columns or target_col not in df.columns:
            raise ChartError(
                "航线图需要 来源列(source) + 去向列(target)（可选 值列）",
                ErrorCode.CHART_CONFIG_ERROR,
                details={'available': list(df.columns),
                         'suggestion': '用 --x-axis <来源列> --y-axis <去向列> [<值列>] 显式指定'},
            )
        geo_names = ctx.geo_names if ctx.geo_names is not None else geojson_region_names(ctx.geo_json or {})
        aliases = ctx.geo_aliases
        # ECharts lines 系列的 data item 只认 `coords` 字段定位（fromName/toName 仅作
        # tooltip 标签），故从 GeoJSON 提取区域中心点，把 fromName/toName 转成 coords。
        centers = region_centers(ctx.geo_json or {})
        data = []
        src_list = df[source_col].tolist()
        tgt_list = df[target_col].tolist()
        has_value = value_col and value_col in df.columns
        v_list = df[value_col].tolist() if has_value else None
        for i in range(len(src_list)):
            fs = resolve_region_name(src_list[i], geo_names, aliases)
            ft = resolve_region_name(tgt_list[i], geo_names, aliases)
            if fs is None or ft is None:
                continue
            c1 = centers.get(fs)
            c2 = centers.get(ft)
            if c1 is None or c2 is None:
                # 区域存在但无法定位中心点（自备 GeoJSON 缺 cp/center/centroid 且几何异常）
                continue
            item = {'coords': [c1, c2], 'fromName': fs, 'toName': ft}
            if has_value:
                v = sanitize_value(float(v_list[i]))
                if v is not None:
                    item['value'] = v
            data.append(item)
        if not data:
            raise ChartError(
                "航线图数据为空：来源/去向列无法对齐到地图区域",
                ErrorCode.DATA_EMPTY,
                details={'suggestion': '来源/去向使用地图区域全称（china 支持 北京/广东 等简称）'},
            )
        ctx.js[ITEM_TOOLTIP_PLACEHOLDER] = (
            "function(p) {\n"
            "  var d = p.data || {};\n"
            "  return (d.fromName || '') + ' → ' + (d.toName || '')"
            " + (d.value != null ? ': ' + d.value : '');\n"
            "}"
        )
        opt = {
            'title': {'text': ctx.title, 'left': 'center', 'textStyle': {'fontSize': 16}},
            'tooltip': {'trigger': 'item', 'formatter': ITEM_TOOLTIP_PLACEHOLDER},
            'color': list(ctx.theme['palette']),
            'geo': {'map': ctx.geo_map_name, 'roam': True, 'label': {'show': False},
                    'itemStyle': {'areaColor': ctx.theme['card_bg']}},
            'series': [{
                'name': ctx.texts['series_lines'], 'type': 'lines', 'data': data,
                'effect': {'show': True, 'period': 4, 'trailLength': 0.3, 'symbol': 'arrow', 'symbolSize': 6},
                'lineStyle': {'width': 1.5, 'opacity': 0.6, 'curveness': 0.2},
            }],
        }
        return opt

    def _effect_scatter(self, ctx: RenderContext):
        """涟漪散点图：复用 scatter 的数据契约与 tooltip，叠加涟漪动画强调点位。"""
        opt = self._scatter(ctx)
        for s in opt.get('series', []):
            if s.get('type') == 'scatter':
                s['type'] = 'effectScatter'
                s.setdefault('rippleEffect', {'scale': 3.5, 'brushType': 'stroke'})
                s.setdefault('showEffectOn', 'render')
        return opt

    def _calendar(self, ctx: RenderContext):
        """日历热力图：日期列 + 数值列 → 日历坐标系上的每日强度块（GitHub 贡献图式）。

        数据契约：x = 日期列（可被 to_datetime 解析），y[0] = 数值列。
        """
        df, x, y = ctx.df, ctx.x, ctx.y
        y_col = y[0] if y else df.columns[-1]
        dates = pd.to_datetime(df[x], errors='coerce')
        mask = dates.notna() & df[y_col].notna()
        data = []
        for d, v in zip(dates[mask].tolist(), df[y_col][mask].tolist()):
            data.append([d.strftime('%Y-%m-%d'), sanitize_value(float(v))])
        if not data:
            raise ChartError(
                "日历热力图需要可解析为日期的 X 轴列，且至少一个有效数据点",
                ErrorCode.DATA_EMPTY,
                details={'given_x': x,
                         'suggestion': 'X 轴使用日期列（如 2024-01-01），或用 transform_code 生成日期列'},
            )
        vmin = min(v for _, v in data if v is not None)
        vmax = max(v for _, v in data if v is not None)
        if vmin == vmax:
            vmax = vmin + 1
        year = int(dates.dropna().min().year)
        opt = {
            'title': {'text': ctx.title, 'left': 'center', 'textStyle': {'fontSize': 16}},
            'tooltip': {'trigger': 'item'},
            'visualMap': {'min': vmin, 'max': vmax, 'calculable': True, 'orient': 'vertical',
                          'left': '1%', 'top': 'center',
                          'inRange': {'color': list(ctx.theme['sequential'])}},
            'calendar': {'top': 60, 'left': 60, 'right': 20, 'range': str(year),
                         'cellSize': ['auto', 16], 'yearLabel': {'show': True}},
            'series': [{
                'name': ctx.texts['series_calendar'], 'type': 'heatmap',
                'coordinateSystem': 'calendar', 'data': data,
            }],
        }
        return opt

    def _pictorial_bar(self, ctx: RenderContext):
        """象形柱图：复用 bar 数据契约，柱子由重复的小箭头符号堆叠而成（象征增长）。"""
        opt = self._bar(ctx)
        for s in opt.get('series', []):
            if s.get('type') == 'bar':
                s['type'] = 'pictorialBar'
                s['symbol'] = 'arrow'
                s['symbolRepeat'] = True
                s['symbolSize'] = [18, 8]
                s['symbolMargin'] = 3
                s['symbolClip'] = True
                s['symbolPosition'] = 'start'
        return opt

    def _theme_river(self, ctx: RenderContext):
        """主题河流图：时间列 + 多数值列 → 平滑堆叠的河流流（各系列随时间体量变化）。

        数据契约：x = 时间列（可被 to_datetime 解析），y = 1~N 数值列。
        """
        df, x, y = ctx.df, ctx.x, ctx.y
        if len(y) < 1:
            raise ChartError(
                "主题河流图至少需要 1 个数值列",
                ErrorCode.CHART_CONFIG_ERROR,
                details={'suggestion': '提供 --y-axis <数值列> [<数值列> ...]'},
            )
        dates = pd.to_datetime(df[x], errors='coerce')
        if dates.notna().sum() == 0:
            raise ChartError(
                "主题河流图需要可解析为时间/日期的 X 轴列",
                ErrorCode.CHART_CONFIG_ERROR,
                details={'given_x': x,
                         'suggestion': 'X 轴使用日期列（如 2024-01-01），或用 transform_code 生成日期列'},
            )
        data = []
        for i in range(len(df)):
            d = dates.iloc[i]
            if pd.isna(d):
                continue
            ds = d.strftime('%Y-%m-%d')
            for col in y:
                v = df[col].iloc[i]
                if pd.notna(v):
                    data.append([ds, sanitize_value(float(v)), col])
        if not data:
            raise ChartError("主题河流图无有效数据", ErrorCode.DATA_EMPTY)
        opt = {
            'title': {'text': ctx.title, 'left': 'center', 'textStyle': {'fontSize': 16}},
            'tooltip': {'trigger': 'axis', 'axisPointer': {'type': 'line', 'lineStyle': {'color': 'rgba(0,0,0,0.2)', 'width': 1}}},
            'singleAxis': {'type': 'time', 'boundaryGap': ['5%', '5%']},
            'series': [{
                'name': ctx.texts['series_theme_river'], 'type': 'themeRiver',
                'data': data, 'label': {'show': False},
                'emphasis': {'itemStyle': {'shadowBlur': 20, 'shadowColor': 'rgba(0,0,0,0.2)'}},
            }],
        }
        return opt
