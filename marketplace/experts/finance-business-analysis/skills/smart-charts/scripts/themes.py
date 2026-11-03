"""图表主题预设。统一系列配色与页面配色，保证批量出图的视觉一致性。

ChartGenerator 构造时按名称解析主题（--theme default|classic|dark），渲染器与
HTML 模板统一从 self._theme 取色，不再散落硬编码颜色。
"""

from typing import Dict, Any

# 主题字段说明：
# palette       系列调色板（option['color']，按序取用）
# primary       单系列主色（waterfall/histogram/pareto/combo 的 bar、liquid 波浪）
# secondary     对比强调色（pareto 累计折线）
# gauge_stops   gauge 轴线三段渐变色
# sequential    顺序数据单色渐变（浅→深；heatmap 等全非负数据用）
# diverging     发散数据双色渐变 + 中性中点（heatmap 等含负值数据用，中点≈页面底色）
# echarts_text  ECharts 内部文字颜色（浅色主题用 None 走默认；深色主题必须给亮色）
# 其余为 HTML 页面配色（背景/卡片/标题/按钮/注释块/表格等）
THEMES: Dict[str, Dict[str, Any]] = {
    # 默认主题：沿用既有页面观感；系列色统一为 Okabe-Ito 色觉安全色板（红绿色弱可区分）
    'default': {
        'palette': ['#0072B2', '#E69F00', '#009E73', '#D55E00', '#CC79A7', '#56B4E9', '#F0E442', '#999999'],
        'primary': '#0072B2',
        'secondary': '#D55E00',
        'gauge_stops': ['#67e0e3', '#37a2da', '#fd666d'],
        'sequential': ['#dceefb', '#0072B2'],
        'diverging': ['#0072B2', '#f2f2f2', '#E69F00'],
        'echarts_text': None,
        'graphic_text': '#666666',
        'page_bg': '#f8f9fa',
        'card_bg': '#ffffff',
        'title_color': '#2E7D32',
        'accent': '#4CAF50',
        'accent_hover': '#45a049',
        'btn_text': '#ffffff',
        'text_main': '#444444',
        'text_muted': '#999999',
        'text_faint': '#bbbbbb',
        'divider': '#eeeeee',
        'chip_border': '#cccccc',
        'chip_text': '#555555',
        'chip_bg': '#fafafa',
        'annotation_bg': '#f2f7f2',
        'table_header_bg': '#f2f7f2',
        'table_row_border': '#eeeeee',
        'chart_bg': '#ffffff',
    },
    # 经典主题：ECharts 原生调色板，蓝色系页面点缀
    'classic': {
        'palette': ['#5470c6', '#91cc75', '#fac858', '#ee6666', '#73c0de', '#3ba272', '#fc8452', '#9a60b4'],
        'primary': '#5470c6',
        'secondary': '#ee6666',
        'gauge_stops': ['#73c0de', '#5470c6', '#ee6666'],
        'sequential': ['#e2e8f7', '#5470c6'],
        'diverging': ['#5470c6', '#f5f5f5', '#ee6666'],
        'echarts_text': None,
        'graphic_text': '#666666',
        'page_bg': '#f8f9fa',
        'card_bg': '#ffffff',
        'title_color': '#3d5a99',
        'accent': '#5470c6',
        'accent_hover': '#4761b3',
        'btn_text': '#ffffff',
        'text_main': '#444444',
        'text_muted': '#999999',
        'text_faint': '#bbbbbb',
        'divider': '#eeeeee',
        'chip_border': '#cccccc',
        'chip_text': '#555555',
        'chip_bg': '#fafafa',
        'annotation_bg': '#f0f3fb',
        'table_header_bg': '#f0f3fb',
        'table_row_border': '#eeeeee',
        'chart_bg': '#ffffff',
    },
    # 深色主题：深底亮字，适合暗色环境与截图嵌入
    'dark': {
        'palette': ['#5B8FF9', '#61DDAA', '#F6BD16', '#F08BB4', '#7666F9', '#78D3F8', '#9270CA', '#FF9D4D'],
        'primary': '#5B8FF9',
        'secondary': '#F6BD16',
        'gauge_stops': ['#78D3F8', '#5B8FF9', '#F08BB4'],
        'sequential': ['#2d2d4a', '#78D3F8'],
        'diverging': ['#5B8FF9', '#2d2d4a', '#F6BD16'],
        'echarts_text': '#c8c8dc',
        'graphic_text': '#c8c8dc',
        'page_bg': '#16162a',
        'card_bg': '#262640',
        'title_color': '#f0f0f8',
        'accent': '#61DDAA',
        'accent_hover': '#4bc795',
        'btn_text': '#101020',
        'text_main': '#e8e8f0',
        'text_muted': '#9a9ab0',
        'text_faint': '#6e6e85',
        'divider': '#3a3a52',
        'chip_border': '#4a4a66',
        'chip_text': '#c8c8dc',
        'chip_bg': '#22223a',
        'annotation_bg': '#2d2d4a',
        'table_header_bg': '#2d2d4a',
        'table_row_border': '#3a3a52',
        'chart_bg': '#262640',
    },
}
