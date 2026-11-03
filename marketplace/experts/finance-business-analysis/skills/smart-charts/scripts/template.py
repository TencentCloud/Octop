"""HTML 模板生成器。将 ECharts option 转为独立的交互式 HTML 文件。

架构契约（P1 重构后）：
- 占位符常量与布局阈值（DATAZOOM_THRESHOLD / MIN_PX_PER_POINT /
  NO_SERIES_CHART_TYPES）集中定义在本模块，renderers 与 chart_generator 引用。
- _save_html 从 RenderContext 显式取 texts/theme/lang，并统一消费 ctx.js 中
  收集的 JS 函数片段（占位符 → JS），不再读写生成器实例属性。
- _save_table_html 的文件名哈希覆盖全表内容（列 + 值），同 schema 同行数的
  不同数据不再互相覆盖。
"""

import json
import re
import html as html_module
import pandas as pd
from pathlib import Path
from typing import Dict
from datetime import datetime


ECHARTS_VERSION = '5.4.4'
ECHARTS_WORDCLOUD_VERSION = '2.1.0'
# ECharts JS 内联到 HTML（避免 file:// 跨域加载失败，确保离线自包含）
_STATIC_DIR = Path(__file__).resolve().parent.parent / 'assets'
ECHARTS_LOCAL = _STATIC_DIR / 'echarts.min.js'
ECHARTS_WORDCLOUD_LOCAL = _STATIC_DIR / 'echarts-wordcloud.min.js'
ECHARTS_LIQUIDFILL_LOCAL = _STATIC_DIR / 'echarts-liquidfill.min.js'

# 数据点超过此阈值时自动启用 dataZoom（slider + inside），允许用户在图内拖动/缩放查看
DATAZOOM_THRESHOLD = 15
# 单个数据点占用的最小宽度（px），用于计算 .chart 容器的 min-width 兜底
MIN_PX_PER_POINT = 18

# 无"系列"概念的图表类型：这些图的 series name 仅为写死的图表类型名（如「热力图」「桑基图」），
# 重命名面板不渲染"系列"分组（仍渲染有意义的"轴"分组，若有）。
# 判定标准：series name 是否 = 数据列名（可经 --series-name 改、且在图/tooltip 中对用户可见）。
#   是 → 必须可编辑，移出本集合；否（写死类型名）→ 留在本集合。
# 注：liquid / gauge / pie 均不在此列——它们的 series name = 数值列名（可经 --series-name 改）：
#   liquid label 第二行跟随系列名；gauge/pie 的 data[0].name 或 tooltip {a} 显示系列名。
#   三者都需渲染"系列"分组，供用户把英文列名（如 achievement / value）改成业务名。
#   histogram 虽以列名作 series name，但该名字不在图中显示（tooltip 只用 {b}{c}），
#   列名已由"轴"分组（y 轴 graphic）承担编辑，故仍留在本集合。
NO_SERIES_CHART_TYPES = {
    'heatmap', 'treemap', 'graph', 'sankey',
    'funnel', 'sunburst', 'wordcloud', 'histogram', 'boxplot', 'bubble',
    'venn', 'mindmap', 'orgchart', 'spreadsheet',
    'map', 'lines', 'calendar', 'theme_river',
}

# tooltip formatter 占位符：json.dumps 会将其序列化为字符串，
# _save_html 中再将带引号的占位符替换为真正的 JS 函数，避免 ECharts 把函数当纯文本渲染。
TOOLTIP_FORMATTER_AXIS = '__TOOLTIP_FORMATTER_AXIS__'

# bubble symbolSize 占位符：同上，json.dumps 会把 JS 函数序列化为字符串，
# 需在 _save_html 中替换为真正的 JS 函数，否则 ECharts 无法执行导致气泡不渲染。
BUBBLE_SYMBOLSIZE_PLACEHOLDER = '__BUBBLE_SYMBOLSIZE__'

# liquid（水波图）label formatter 占位符：label 第二行需跟随系列名（--series-name /
# 前端重命名面板实时可改），故用函数 formatter 在运行时读 chartOption.series[0].name，
# 而非写死列名。占位符由 _liquid 收集进 ctx.js，_save_html 统一替换为 JS 函数。
LIQUID_LABEL_PLACEHOLDER = '__LIQUID_LABEL__'

# bubble tooltip formatter 占位符：ECharts 字符串模板不支持 {c[0]} 数组索引，
# 必须使用函数 formatter 才能正确显示数组数据的各字段值。
BUBBLE_TOOLTIP_PLACEHOLDER = '__BUBBLE_TOOLTIP__'

# 通用 item tooltip 占位符（scatter/boxplot 离群点/heatmap 共用）：
# 渲染器把 JS 函数收集进 ctx.js，_save_html 统一替换为真正的 JS 函数。
ITEM_TOOLTIP_PLACEHOLDER = '__ITEM_TOOLTIP__'

# 所有内嵌 tooltip JS 共用的 HTML 转义函数（esc）：单点定义，
# 本模块与 renderers 的各 formatter 一律引用，不得内联复制。
ESC_JS_FN = (
    "var esc = function(s) { return String(s).replace(/&/g, '&amp;')"
    ".replace(/</g, '&lt;').replace(/>/g, '&gt;')"
    ".replace(/\"/g, '&quot;').replace(/'/g, '&#39;'); };\n"
)

# waterfall tooltip 占位符：柱高是绝对值，tooltip 需显示带符号的原始增量。
WATERFALL_TOOLTIP_PLACEHOLDER = '__WATERFALL_TOOLTIP__'

# 缓存 ECharts JS 内容（避免每次生成图表都读文件）
_ECHARTS_JS_CACHE = None
_WORDCLOUD_JS_CACHE = None
_LIQUIDFILL_JS_CACHE = None


def _load_echarts_js() -> str:
    """读取并缓存 ECharts JS 内容，用于内联到 HTML。"""
    global _ECHARTS_JS_CACHE
    if _ECHARTS_JS_CACHE is None:
        _ECHARTS_JS_CACHE = ECHARTS_LOCAL.read_text(encoding='utf-8')
    return _ECHARTS_JS_CACHE


def _load_wordcloud_js() -> str:
    """读取并缓存 wordcloud 插件 JS 内容，用于内联到 HTML。"""
    global _WORDCLOUD_JS_CACHE
    if _WORDCLOUD_JS_CACHE is None:
        _WORDCLOUD_JS_CACHE = ECHARTS_WORDCLOUD_LOCAL.read_text(encoding='utf-8')
    return _WORDCLOUD_JS_CACHE


def _load_liquidfill_js() -> str:
    """读取并缓存 liquidfill 插件 JS 内容，用于内联到 HTML。"""
    global _LIQUIDFILL_JS_CACHE
    if _LIQUIDFILL_JS_CACHE is None:
        _LIQUIDFILL_JS_CACHE = ECHARTS_LIQUIDFILL_LOCAL.read_text(encoding='utf-8')
    return _LIQUIDFILL_JS_CACHE


# 缓存中国省级 GeoJSON（map/lines 内联 registerMap 用，离线自包含）
_GEO_JSON_CACHE = None


def _load_china_geojson() -> Dict:
    """读取并缓存 assets/china.json，供 map/lines 图表内联 registerMap。"""
    global _GEO_JSON_CACHE
    if _GEO_JSON_CACHE is None:
        _GEO_JSON_CACHE = json.loads((_STATIC_DIR / 'china.json').read_text(encoding='utf-8'))
    return _GEO_JSON_CACHE


def tooltip_formatter_axis_js(texts: Dict[str, str]) -> str:
    """axis tooltip 的 JS formatter（千分位 + HTML 转义 + 无数据占位）。"""
    no_data = texts['tooltip_no_data']
    return (
        "function(params) {\n"
        "                " + ESC_JS_FN +
        "                var res = esc(params[0].axisValue) + '<br/>';\n"
        "                params.forEach(function(p) {\n"
        f"                    var val = (p.value === null || p.value === undefined || p.value === 'NaN' || p.value === 'Infinity') ? '{no_data}' : (typeof p.value === 'number' ? p.value.toLocaleString() : esc(p.value));\n"
        "                    res += p.marker + esc(p.seriesName) + ': ' + val + '<br/>';\n"
        "                });\n"
        "                return res;\n"
        "            }"
    )


def _content_suffix(df: pd.DataFrame) -> str:
    """表格文件名后缀：对全表内容（列 + 单元格值）取哈希。

    只用「列名 + 行数」时，同 schema 同行数的两份不同数据会得到同一文件名，
    后生成的静默覆盖先生成的；改为全内容哈希后互不覆盖。
    """
    import hashlib
    try:
        payload = pd.util.hash_pandas_object(df, index=False).values.tobytes()
    except TypeError:  # 含不可哈希对象时退化为字符串序列化
        payload = df.to_csv(index=False).encode('utf-8')
    cols = json.dumps([str(c) for c in df.columns], ensure_ascii=False).encode('utf-8')
    return hashlib.md5(payload + cols).hexdigest()[:6]


class HTMLTemplateMixin:
    """HTML 模板生成方法，由 ChartGenerator 继承。"""

    def _save_html(self, ctx, option: Dict, width: int, height: int,
                   chart_type: str = '', data_points: int = 0, annotation: str = '') -> Path:
        import hashlib
        self._ensure_output_dir()
        th = ctx.theme
        texts = ctx.texts
        content_str = json.dumps(option, ensure_ascii=False, sort_keys=True)
        suffix = hashlib.md5(content_str.encode()).hexdigest()[:6]
        raw_safe = re.sub(r'[\\/:*?"<>|]', '_', ctx.title)
        safe_title = raw_safe[:30]
        # 文件名截断可观测性：截断发生时登记，供生成器挂 advisory（完整标题见 title 字段）
        self._title_truncated = len(raw_safe) > 30
        filename = f"{safe_title}_{suffix}.html"
        path = self.output_dir / filename

        # XSS 防护：转义所有用户输入插入 HTML 的部分
        esc_title = html_module.escape(ctx.title)
        # 副标题：用户提供时置于生成时间之前（保留品牌与时间戳信息）
        subtitle_prefix = (html_module.escape(ctx.subtitle) + ' &middot; ') if ctx.subtitle else ''

        # 主题注入：画布背景 + 深色主题的全局文字颜色（浅色主题 echarts_text=None 走默认）
        option.setdefault('backgroundColor', th['chart_bg'])
        if th['echarts_text']:
            option.setdefault('textStyle', {'color': th['echarts_text']})
            if isinstance(option.get('title'), dict):
                option['title'].setdefault('textStyle', {})['color'] = th['echarts_text']
            # legend 有自己的默认色（#333），不继承根级 textStyle
            if isinstance(option.get('legend'), dict):
                option['legend'].setdefault('textStyle', {})['color'] = th['echarts_text']
            # gauge 系列文字（刻度/数值/名称，默认 #464646），不继承根级 textStyle
            for s in option.get('series', []):
                if not isinstance(s, dict):
                    continue
                if s.get('type') == 'gauge':
                    s.setdefault('axisLabel', {})['color'] = th['echarts_text']
                    s.setdefault('detail', {})['color'] = th['echarts_text']
                    s.setdefault('title', {})['color'] = th['echarts_text']
                # graph 节点标签（默认 #333），节点圆小于标签宽度，文字大部分落在深色画布上
                elif s.get('type') == 'graph':
                    s.setdefault('label', {})['color'] = th['echarts_text']

        option_json = json.dumps(option, ensure_ascii=False, indent=2, allow_nan=False)
        # XSS 防护：转义 </ 防止数据值中的 </script> 提前闭合脚本上下文。
        # JSON/JS 字符串中 \/ 合法且求值后还原为 /，ECharts 拿到的值不变。
        # 必须在占位符替换为 JS 函数之前执行：注入的受信 JS 含正则 /</g，事后替换会破坏其语法。
        option_json = option_json.replace('</', '<\\/')

        # 将占位符字符串替换为真正的 JS 函数（去掉 json.dumps 添加的引号）。
        # axis tooltip 恒有；其余片段由渲染器收集进 ctx.js（RenderContext 显式传参，
        # 不再依赖生成器实例属性），替换完成即清空。
        option_json = option_json.replace(
            f'"{TOOLTIP_FORMATTER_AXIS}"',
            tooltip_formatter_axis_js(texts),
        )
        for placeholder, js in ctx.js.items():
            option_json = option_json.replace(f'"{placeholder}"', js)
        ctx.js.clear()

        # ECharts JS 内联到 HTML（避免 file:// 跨域加载失败，确保离线自包含）
        echarts_js = _load_echarts_js()

        # wordcloud / liquidfill 插件（仅对应图表类型需要，同样内联）
        wordcloud_script = ''
        if chart_type == 'wordcloud':
            wordcloud_js = _load_wordcloud_js()
            wordcloud_script = f'<script>{wordcloud_js}</script>'
        liquidfill_script = ''
        if chart_type == 'liquid':
            liquidfill_js = _load_liquidfill_js()
            liquidfill_script = f'<script>{liquidfill_js}</script>'

        # map/lines 图表：内联 GeoJSON 并 registerMap，再 setOption 才能渲染。
        # GeoJSON 与 map 名取自 ctx（chart_generator 已解析 --geo/--geo-path）；
        # ctx.geo_json 为空时回退到内置中国省级地图（兜底，正常不会触发）。
        map_register_js = ''
        if chart_type in ('map', 'lines'):
            geo_json = ctx.geo_json if ctx.geo_json is not None else _load_china_geojson()
            geo_map_name = ctx.geo_map_name or 'china'
            geo_json_str = json.dumps(geo_json, ensure_ascii=False).replace('</', '<\\/')
            map_register_js = f'echarts.registerMap("{geo_map_name}", {geo_json_str});'

        # 宽高比，用于响应式高度计算
        aspect_ratio = width / height if height > 0 else 16 / 9

        # 数据点过多时：容器加横向滚动兜底 + 显示提示
        scroll_hint_html = ''
        if data_points and data_points > DATAZOOM_THRESHOLD:
            min_chart_width = data_points * MIN_PX_PER_POINT
            chart_style = (
                f"width: 100%; aspect-ratio: {aspect_ratio:.4f}; min-height: 300px; "
                f"min-width: {min_chart_width}px;"
            )
            wrapper_style = "width: 100%; position: relative; overflow-x: auto; overflow-y: hidden;"
            scroll_hint_html = f'<div class="scroll-hint">{html_module.escape(texts["scroll_hint"])}</div>'
        else:
            chart_style = f"width: 100%; aspect-ratio: {aspect_ratio:.4f}; min-height: 300px;"
            wrapper_style = "width: 100%; position: relative;"

        btn_save = html_module.escape(texts['btn_save'])
        btn_fullscreen = html_module.escape(texts['btn_fullscreen'])
        footer_text = html_module.escape(texts['footer'])
        annotation_html = f'<div class="annotation">{html_module.escape(annotation)}</div>' if annotation else ''
        edit_hint = html_module.escape(texts['edit_hint'])
        rename_hint = html_module.escape(texts['rename_hint'])
        rename_group_series = html_module.escape(texts['rename_group_series'])
        rename_group_axis = html_module.escape(texts['rename_group_axis'])
        title_updated_msg = html_module.escape(texts['title_updated'])
        # lang 显式来自 ctx（texts.get_texts 返回实际生效语言），不再做字典身份比较
        html_lang = 'zh-CN' if ctx.lang == 'zh' else 'en'
        # 无系列概念的图表不渲染"系列"重命名分组（series name 仅为写死的图表类型名，如 heatmap/sankey）；
        # series name = 数值列名的图（gauge/pie/liquid 等）不在 NO_SERIES_CHART_TYPES 内，仍渲染"系列"分组供改名
        show_series_js = 'false' if chart_type in NO_SERIES_CHART_TYPES else 'true'

        html = f"""<!DOCTYPE html>
<html lang="{html_lang}">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{esc_title}</title>
<script>{echarts_js}</script>
{wordcloud_script}
{liquidfill_script}
<style>
* {{ box-sizing: border-box; }}
body {{ font-family: 'Microsoft YaHei', 'PingFang SC', 'Hiragino Sans GB', 'Noto Sans CJK SC', sans-serif; margin: 0; padding: 20px; background: {th['page_bg']}; }}
.container {{ max-width: {width}px; width: 100%; margin: 0 auto; background: {th['card_bg']}; padding: 30px;
             border-radius: 12px; box-shadow: 0 4px 20px rgba(0,0,0,0.08); }}
.header {{ text-align: center; margin-bottom: 20px; padding-bottom: 15px; border-bottom: 2px solid {th['accent']}; }}
.title {{ font-size: clamp(16px, 4vw, 24px); font-weight: 700; color: {th['title_color']}; margin: 0;
          cursor: text; outline: none; border-bottom: 2px dashed transparent; transition: border-color 0.2s; }}
.title:hover {{ border-bottom-color: {th['chip_border']}; }}
.title:focus {{ border-bottom-color: {th['accent']}; }}
.edit-hint {{ font-size: 11px; color: {th['text_faint']}; margin-top: 4px; transition: color 0.3s; }}
.subtitle {{ font-size: 12px; color: {th['text_muted']}; }}
.chart-wrapper {{ {wrapper_style} }}
.chart {{ {chart_style} }}
.scroll-hint {{ text-align: center; font-size: 12px; color: {th['text_muted']}; margin: 8px 0; }}
.controls {{ text-align: center; margin: 15px 0; }}
.btn {{ display: inline-block; padding: 6px 16px; background: {th['accent']}; color: {th['btn_text']};
        border: none; border-radius: 4px; cursor: pointer; font-size: 13px; margin: 0 4px; }}
.btn:hover {{ background: {th['accent_hover']}; }}
.rename-panel {{ text-align: center; margin: 0 0 12px; font-size: 12px; color: {th['text_muted']}; }}
.rename-hint {{ display: block; color: {th['text_faint']}; margin-bottom: 6px; }}
.rename-group {{ margin: 4px 0; }}
.rename-group-label {{ color: {th['text_muted']}; margin-right: 2px; }}
.rename-chip {{ display: inline-block; padding: 2px 10px; margin: 2px 4px; border: 1px dashed {th['chip_border']};
                border-radius: 10px; color: {th['chip_text']}; cursor: text; outline: none; background: {th['chip_bg']}; }}
.rename-chip:hover, .rename-chip:focus {{ border-color: {th['accent']}; background: {th['card_bg']}; }}
.annotation {{ margin: 14px 0 0; padding: 12px 16px; background: {th['annotation_bg']}; border-left: 3px solid {th['accent']};
              border-radius: 6px; font-size: 13px; color: {th['text_main']}; line-height: 1.7; text-align: left; }}
.footer {{ margin-top: 25px; padding-top: 15px; border-top: 1px solid {th['divider']}; text-align: center;
          font-size: 11px; color: {th['text_faint']}; }}
@media (max-width: 640px) {{
  .container {{ padding: 15px; }}
  .chart {{ min-height: 250px; }}
}}
@media print {{ .controls {{ display: none; }} .container {{ box-shadow: none; }} }}
</style>
</head>
<body>
<div class="container">
  <div class="header">
    <h1 class="title" contenteditable="true" title="{edit_hint}">{esc_title}</h1>
    <div class="edit-hint">{edit_hint}</div>
    <div class="subtitle">{subtitle_prefix}Smart Charts &middot; {datetime.now().strftime('%Y-%m-%d %H:%M')}</div>
  </div>
  <div class="controls">
    <button class="btn" onclick="saveAsImage()">{btn_save}</button>
    <button class="btn" onclick="toggleFull()">{btn_fullscreen}</button>
  </div>
  {scroll_hint_html}
  <div class="rename-panel" id="renamePanel"></div>
  <div class="chart-wrapper">
    <div id="chart" class="chart"></div>
  </div>
  {annotation_html}
  <div class="footer">{footer_text} &middot; ECharts {ECHARTS_VERSION}</div>
</div>
<script>
var chartDom = document.getElementById('chart');
var chart = echarts.init(chartDom);
{map_register_js}
var chartOption = {option_json};
chart.setOption(chartOption);
// 系列名/轴名重命名面板：按"系列/轴"分组展示名称芯片，单击即可编辑，Enter 确认，Escape 取消。
// 轴名是图上的可拖拽 graphic 文本（id 以 axisName- 开头），改文字用局部 setOption 合并，
// 不回写位置属性，用户拖拽后的位置不受影响；保存图片时名称与位置均随画布生效。
(function() {{
  var panel = document.getElementById('renamePanel');
  var seriesEntries = [], axisEntries = [];
  if ({show_series_js}) {{
    (chartOption.series || []).forEach(function(s) {{
      // 排除 waterfall 透明垫底等内部辅助系列
      if (s.name && s.name.indexOf('__waterfall_base__') !== 0) seriesEntries.push(s);
    }});
  }}
  (chartOption.graphic || []).forEach(function(el) {{
    if (el.id && el.id.indexOf('axisName-') === 0) axisEntries.push(el);
  }});
  if (!seriesEntries.length && !axisEntries.length) {{ panel.style.display = 'none'; return; }}
  var hint = document.createElement('span');
  hint.className = 'rename-hint';
  hint.textContent = '{rename_hint}';
  panel.appendChild(hint);

  function addGroup(labelText, entries, apply) {{
    if (!entries.length) return;
    var group = document.createElement('div');
    group.className = 'rename-group';
    var label = document.createElement('span');
    label.className = 'rename-group-label';
    label.textContent = labelText;
    group.appendChild(label);
    entries.forEach(function(obj) {{
      var chip = document.createElement('span');
      chip.className = 'rename-chip';
      var original = apply('get', obj);
      chip.textContent = original;
      chip.contentEditable = 'true';
      chip.addEventListener('keydown', function(e) {{
        if (e.key === 'Enter') {{ e.preventDefault(); chip.blur(); }}
        if (e.key === 'Escape') {{ chip.textContent = original; chip.blur(); }}
      }});
      chip.addEventListener('blur', function() {{
        var v = chip.textContent.trim();
        if (v && v !== original) {{ apply('set', obj, v); original = v; }}
        else {{ chip.textContent = original; }}
      }});
      group.appendChild(chip);
    }});
    panel.appendChild(group);
  }}

  addGroup('{rename_group_series}', seriesEntries, function(op, s, v) {{
    if (op === 'get') return s.name;
    var old = s.name;
    s.name = v;
    // radar 等图 series.data[0].name 与 series.name 是同一名字，同步更新，避免 tooltip 显示旧名
    var syncedData = false;
    if (s.data && s.data.length && s.data[0] && s.data[0].name === old) {{
      s.data[0].name = v;
      syncedData = true;
    }}
    // legend.data 若显式列出系列名（如 waterfall），同步替换，否则改名后图例失配消失
    if (chartOption.legend && chartOption.legend.data) {{
      chartOption.legend.data = chartOption.legend.data.map(function(n) {{ return n === old ? v : n; }});
    }}
    // 局部合并：只更新系列名与图例，不触碰 graphic 等元素（保留轴名拖拽位置）；
    // 同步了 data[0].name 的系列需把完整 data 传回，否则 ECharts 保留旧 data.name
    chart.setOption({{ series: chartOption.series.map(function(x) {{
                        if (x === s && syncedData) {{ return {{ name: x.name, data: x.data }}; }}
                        return {{ name: x.name }};
                      }}),
                       legend: chartOption.legend }});
  }});
  addGroup('{rename_group_axis}', axisEntries, function(op, el, v) {{
    if (op === 'get') return el.style.text;
    el.style.text = v;
    // 按 id 局部合并，只改文字，不重置拖拽后的位置
    chart.setOption({{ graphic: [{{ id: el.id, style: {{ text: v }} }}] }});
  }});
}})();
window.addEventListener('resize', function() {{ chart.resize(); }});
new ResizeObserver(function() {{ chart.resize(); }}).observe(chartDom);
// {texts['comment_download_name']}
var currentDownloadName = {json.dumps(safe_title, ensure_ascii=False)};
function saveAsImage() {{
  // 先把已拖拽的 graphic 轴名位置持久化为绝对 x/y（清除 left/right/top/bottom 相对定位）。
  // 否则后面重置 dataZoom 触发的重渲染会按相对定位把轴名复位到初始位置。
  var zr = chart.getZr();
  var patches = [];
  var seen = {{}};
  zr.storage.getDisplayList().forEach(function(n) {{
    var p = n;
    while (p) {{
      if (p.id && String(p.id).indexOf('axisName-') === 0 && !seen[p.id]) {{
        seen[p.id] = true;
        patches.push({{ id: p.id, x: p.x, y: p.y, left: null, right: null, top: null, bottom: null }});
        break;
      }}
      p = p.parent;
    }}
  }});
  if (patches.length) {{ chart.setOption({{ graphic: patches }}); }}
  // 保存前临时把 dataZoom 窗口重置为 0~100，导出完整数据后再恢复用户窗口，避免只导出当前可见区间。
  var zooms = chart.getOption().dataZoom || [];
  var savedWindows = zooms.map(function(z) {{ return {{ start: z.start, end: z.end }}; }});
  savedWindows.forEach(function(w, i) {{
    chart.dispatchAction({{ type: 'dataZoom', dataZoomIndex: i, start: 0, end: 100 }});
  }});
  requestAnimationFrame(function() {{
    var url = chart.getDataURL({{ type: 'png', pixelRatio: 2, backgroundColor: '{th["chart_bg"]}' }});
    var a = document.createElement('a'); a.href = url; a.download = currentDownloadName + '.png'; a.click();
    savedWindows.forEach(function(w, i) {{
      chart.dispatchAction({{ type: 'dataZoom', dataZoomIndex: i, start: w.start, end: w.end }});
    }});
  }});
}}
function toggleFull() {{
  var el = document.getElementById('chart');
  if (!document.fullscreenElement) el.requestFullscreen();
  else document.exitFullscreen();
}}
// {texts['comment_title_edit']}
// {texts['comment_title_sync']}
var titleEl = document.querySelector('.title');
var editHintEl = document.querySelector('.edit-hint');
var originalTitle = titleEl.textContent;
titleEl.addEventListener('keydown', function(e) {{
  if (e.key === 'Enter') {{ e.preventDefault(); titleEl.blur(); }}
  if (e.key === 'Escape') {{ titleEl.textContent = originalTitle; titleEl.blur(); }}
}});
titleEl.addEventListener('blur', function() {{
  var newTitle = titleEl.textContent.trim();
  if (newTitle && newTitle !== originalTitle) {{
    originalTitle = newTitle;
    chart.setOption({{ title: {{ text: newTitle }} }});
    currentDownloadName = newTitle.replace(/[\\\\/:*?"<>|]/g, '_').substring(0, 30);
    editHintEl.textContent = '{title_updated_msg}';
    editHintEl.style.color = '{th["accent"]}';
    setTimeout(function() {{ editHintEl.style.color = ''; }}, 3000);
  }} else {{
    titleEl.textContent = originalTitle;
  }}
}});
</script>
</body>
</html>"""
        path.write_text(html, encoding='utf-8')
        return path

    def _save_table_html(self, ctx, df: pd.DataFrame, title: str, width: int, height: int,
                         annotation: str = '') -> Path:
        """spreadsheet 表格视图：主题化 HTML 表格（数值列右对齐、表头吸顶、容器滚动）。"""
        self._ensure_output_dir()
        th = ctx.theme
        texts = ctx.texts
        suffix = _content_suffix(df)
        raw_safe = re.sub(r'[\\/:*?"<>|]', '_', title)
        safe_title = raw_safe[:30]
        self._title_truncated = len(raw_safe) > 30
        filename = f"{safe_title}_{suffix}.html"
        path = self.output_dir / filename

        esc_title = html_module.escape(title)
        # 副标题：用户提供时置于生成时间之前（保留品牌与时间戳信息）
        subtitle_prefix = (html_module.escape(ctx.subtitle) + ' &middot; ') if ctx.subtitle else ''
        numeric_cols = {str(c) for c in df.columns if pd.api.types.is_numeric_dtype(df[c])}

        def _cell_text(v) -> str:
            if v is None or (isinstance(v, float) and pd.isna(v)) or pd.isna(v):
                return ''
            if isinstance(v, float) and v.is_integer():
                return str(int(v))
            return str(v)

        head_cells = ''.join(f'<th>{html_module.escape(str(c))}</th>' for c in df.columns)
        body_rows = []
        for _, row in df.iterrows():
            cells = []
            for c in df.columns:
                cls = ' class="num"' if str(c) in numeric_cols else ''
                cells.append(f'<td{cls}>{html_module.escape(_cell_text(row[c]))}</td>')
            body_rows.append('<tr>' + ''.join(cells) + '</tr>')
        table_body = ''.join(body_rows)

        btn_fullscreen = html_module.escape(texts['btn_fullscreen'])
        footer_text = html_module.escape(texts['footer'])
        annotation_html = f'<div class="annotation">{html_module.escape(annotation)}</div>' if annotation else ''
        edit_hint = html_module.escape(texts['edit_hint'])
        html_lang = 'zh-CN' if ctx.lang == 'zh' else 'en'

        html = f"""<!DOCTYPE html>
<html lang="{html_lang}">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{esc_title}</title>
<style>
* {{ box-sizing: border-box; }}
body {{ font-family: 'Microsoft YaHei', 'PingFang SC', 'Hiragino Sans GB', 'Noto Sans CJK SC', sans-serif; margin: 0; padding: 20px; background: {th['page_bg']}; }}
.container {{ max-width: {width}px; width: 100%; margin: 0 auto; background: {th['card_bg']}; padding: 30px;
             border-radius: 12px; box-shadow: 0 4px 20px rgba(0,0,0,0.08); }}
.header {{ text-align: center; margin-bottom: 20px; padding-bottom: 15px; border-bottom: 2px solid {th['accent']}; }}
.title {{ font-size: clamp(16px, 4vw, 24px); font-weight: 700; color: {th['title_color']}; margin: 0;
          cursor: text; outline: none; border-bottom: 2px dashed transparent; transition: border-color 0.2s; }}
.title:hover {{ border-bottom-color: {th['chip_border']}; }}
.title:focus {{ border-bottom-color: {th['accent']}; }}
.edit-hint {{ font-size: 11px; color: {th['text_faint']}; margin-top: 4px; transition: color 0.3s; }}
.subtitle {{ font-size: 12px; color: {th['text_muted']}; }}
.controls {{ text-align: center; margin: 15px 0; }}
.btn {{ display: inline-block; padding: 6px 16px; background: {th['accent']}; color: {th['btn_text']};
        border: none; border-radius: 4px; cursor: pointer; font-size: 13px; margin: 0 4px; }}
.btn:hover {{ background: {th['accent_hover']}; }}
.table-box {{ max-height: 60vh; overflow: auto; border: 1px solid {th['divider']}; border-radius: 6px; }}
table {{ border-collapse: collapse; width: 100%; font-size: 13px; color: {th['text_main']}; }}
th {{ position: sticky; top: 0; background: {th['table_header_bg']}; color: {th['text_main']};
      font-weight: 600; padding: 8px 12px; text-align: left; white-space: nowrap;
      border-bottom: 1px solid {th['divider']}; z-index: 1; }}
td {{ padding: 6px 12px; border-bottom: 1px solid {th['table_row_border']}; white-space: nowrap; }}
td.num {{ text-align: right; font-variant-numeric: tabular-nums; }}
tbody tr:hover {{ background: {th['chip_bg']}; }}
.annotation {{ margin: 14px 0 0; padding: 12px 16px; background: {th['annotation_bg']}; border-left: 3px solid {th['accent']};
              border-radius: 6px; font-size: 13px; color: {th['text_main']}; line-height: 1.7; text-align: left; }}
.footer {{ margin-top: 25px; padding-top: 15px; border-top: 1px solid {th['divider']}; text-align: center;
          font-size: 11px; color: {th['text_faint']}; }}
@media (max-width: 640px) {{ .container {{ padding: 15px; }} }}
@media print {{ .controls {{ display: none; }} .container {{ box-shadow: none; }} .table-box {{ max-height: none; }} }}
</style>
</head>
<body>
<div class="container">
  <div class="header">
    <h1 class="title">{esc_title}</h1>
    <div class="edit-hint">{edit_hint}</div>
    <div class="subtitle">{subtitle_prefix}Smart Charts &middot; {datetime.now().strftime('%Y-%m-%d %H:%M')}</div>
  </div>
  <div class="controls">
    <button class="btn" onclick="var b=document.querySelector('.table-box'); if (!document.fullscreenElement) b.requestFullscreen(); else document.exitFullscreen();">{btn_fullscreen}</button>
  </div>
  <div class="table-box">
    <table>
      <thead><tr>{head_cells}</tr></thead>
      <tbody>{table_body}</tbody>
    </table>
  </div>
  {annotation_html}
  <div class="footer">{footer_text}</div>
</div>
</body>
</html>"""
        path.write_text(html, encoding='utf-8')
        return path
