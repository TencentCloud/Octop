"""图表生成器（纯编排层）。基于 DataFrame 生成独立的 ECharts 交互式 HTML 文件。

架构契约（P1 重构后）：
- 本类只做编排：参数校验 → 轴/身份列准备 → 构建 RenderContext → 调渲染器 →
  落盘 HTML / 计算 plot_stats。不承载统计实现（plot_stats.py）、
  文案（texts.py）、算法（stats_kernels.py）、模板细节（template.py）。
- 渲染所需状态全部显式放入 RenderContext 传递，不读写生成器实例属性
  （output_dir/_theme/_dir_ready 是生成器自身合法状态，除外）。
"""

import pandas as pd
import numpy as np
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from enum import Enum

from .exceptions import ChartError, ErrorCode, SmartChartsError
from .renderers import ChartRenderersMixin, RenderContext, resolve_geo, geojson_region_names
from .template import HTMLTemplateMixin
from .texts import get_texts
from .plot_stats import compute_plot_stats, stats_spreadsheet
from .themes import THEMES
from .data_transformer import DataTransformer


class ChartType(Enum):
    LINE = 'line'
    BAR = 'bar'
    PIE = 'pie'
    SCATTER = 'scatter'
    AREA = 'area'
    RADAR = 'radar'
    HEATMAP = 'heatmap'
    TREEMAP = 'treemap'
    GRAPH = 'graph'
    BOXPLOT = 'boxplot'
    WATERFALL = 'waterfall'
    GAUGE = 'gauge'
    SANKEY = 'sankey'
    FUNNEL = 'funnel'
    SUNBURST = 'sunburst'
    WORDCLOUD = 'wordcloud'
    HISTOGRAM = 'histogram'
    STACKED_BAR = 'stacked_bar'
    BUBBLE = 'bubble'
    PARETO = 'pareto'
    COMBO = 'combo'
    VENN = 'venn'
    MINDMAP = 'mindmap'
    ORGCHART = 'orgchart'
    LIQUID = 'liquid'
    SPREADSHEET = 'spreadsheet'
    MAP = 'map'
    LINES = 'lines'
    EFFECT_SCATTER = 'effect_scatter'
    CALENDAR = 'calendar'
    PICTORIAL_BAR = 'pictorial_bar'
    THEME_RIVER = 'theme_river'


# 这些图型语义上要求「一个 x 对应一个 y」：同一 x 出现多行即为未聚合，
# plot_stats 的 max/min/mean 会退化成行级统计（而非该 x 的合计/均值）。
# 散点/气泡/箱线/直方图/关系图等本就以行为单位，故不在集合内。
# calendar 虽是时间图，但同一天多行会互相覆盖，同样需要先按天聚合。
_AGG_REQUIRED_TYPES = frozenset({
    'line', 'bar', 'area', 'stacked_bar', 'combo', 'pareto', 'pictorial_bar', 'theme_river',
    'pie', 'treemap', 'funnel', 'sunburst', 'wordcloud', 'venn', 'map', 'waterfall', 'radar',
    'calendar',
})


class ChartGenerator(ChartRenderersMixin, HTMLTemplateMixin):
    """32 种图表的编排入口；HTML 落盘方法来自 HTMLTemplateMixin。"""

    def __init__(self, output_dir: str = './smart_charts_output', theme: str = 'default'):
        if theme not in THEMES:
            raise ChartError(
                f"不支持的主题: {theme}",
                ErrorCode.CHART_CONFIG_ERROR,
                details={
                    'given': theme,
                    'supported': list(THEMES.keys()),
                    'suggestion': f"从 available 主题中选择: {', '.join(THEMES.keys())}",
                },
            )
        self.output_dir = Path(output_dir)
        self._theme = THEMES[theme]
        self._dir_ready = False

    def _ensure_output_dir(self):
        if not self._dir_ready:
            self.output_dir.mkdir(parents=True, exist_ok=True)
            self._dir_ready = True

    def generate_chart(
        self,
        df: pd.DataFrame,
        chart_type: str,
        title: Optional[str] = None,
        x_axis: Optional[str] = None,
        y_axis: Optional[List[str]] = None,
        transform_code: Optional[str] = None,
        width: int = 900,
        height: int = 560,
        lang: Optional[str] = None,
        label_col: Optional[str] = None,
        color_by: Optional[str] = None,
        annotation: Optional[str] = None,
        subtitle: Optional[str] = None,
        sort: str = 'none',
        y_scale: bool = False,
        label: str = 'auto',
        dry_run: bool = False,
        target: Optional[float] = None,
        x_name: Optional[str] = None,
        y_names: Optional[List[str]] = None,
        series_names: Optional[List[str]] = None,
        geo: Optional[str] = None,
        geo_path: Optional[str] = None,
        extra_advisories: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """生成单个图表，返回统一结构 {'chart': {'success', 'html_path'/'error', ...}}。

        lang: 'zh' / 'en' 强制指定图表文本语言；None 时按数据自动检测。
        title: None 时使用 lang 对应的默认标题。
        label_col: 身份列（如姓名），其值进数据点 name 和 tooltip（scatter/bubble/boxplot）。
            None 时按列名启发式自动探测（命中时记入返回值的 assumptions 字段）。
        color_by: 着色列（scatter/bubble）。数值列 → visualMap 连续着色；类别列 → 拆 series 分色。
        subtitle: 副标题（时间范围/筛选条件/数据来源等上下文），渲染在标题下方。
        sort: bar 类别排序。'value'=按第一个数值 Y 列降序；'none'=保持原序（默认）。
        y_scale: 折线图 y 轴允许非零基线（仅 line 生效；area 恒为零基线）。
        label: bar 单系列数值标签。'auto'=类别>20 只标关键值（默认）；'all'=全标；'key'=只标 top3+极值。
        dry_run: True 时只算 plot_stats/data_preview 并校验渲染配置，不写 HTML（html_path 为 null）。
        target: gauge/liquid 的业务目标值（P1-7）。缺失时 plot_stats 的 achievement 为 null 并挂 advisory。
        x_name: X 轴显示名（--x-name）。None 时轴名回退到列名。
        y_names: Y 轴显示名（--y-name，可多个，按 y_axis 顺序对应）。None 时回退到列名。
        series_names: 系列显示名（--series-name/--series-names，按可见系列顺序对应）。
            None 时回退到列名（A 类图）或默认文本（B 类图）。覆盖时跳过 silent 内部系列
            （如 waterfall 的透明底座），避免索引错位。
        geo: 内置地图名（--geo，map/lines 用）。None 时默认 'china'（中国省级）。
        geo_path: 自备 GeoJSON 文件路径（--geo-path，map/lines 用，任意区域地图）。
            优先级高于 geo；map_name 取文件名 stem，地名仅精确匹配（无简称别名）。
        extra_advisories: 由解析层传入的建议性提醒（合计行排除、数值列降级等），
            与渲染层自身的 advisories 合并输出。
        失败时不抛异常，返回 success=False + error 结构，便于智能体程序化处理。
        """
        try:
            # P1-2：聚合口径对账三元组。source_rows 是 transform 之前的原始行数，
            # plotted_rows 是实际喂给渲染的行数——两者之差即 transform 的聚合倍率，
            # unique_entities 是去重实体数。SKILL.md 早已警示"各行 value 之和等于
            # 原始行数而非实体数 = 忘了去重"，但此前输出里没有任何字段能验证它。
            source_rows = int(len(df))
            if df.empty:
                raise ChartError("数据为空", ErrorCode.DATA_EMPTY)
            if lang is not None and lang not in ('zh', 'en'):
                raise ChartError(
                    f"不支持的 lang: {lang}，支持: zh / en",
                    ErrorCode.CHART_CONFIG_ERROR,
                    details={'given': lang, 'supported': ['zh', 'en'],
                             'suggestion': '省略 --lang 让语言跟随数据自动检测，或显式传 zh / en'},
                )
            try:
                ct = ChartType(chart_type)
            except ValueError:
                supported = [t.value for t in ChartType]
                raise ChartError(
                    f"不支持的图表类型: {chart_type}，支持: {supported}",
                    ErrorCode.CHART_TYPE_UNSUPPORTED,
                    details={
                        'given': chart_type,
                        'supported': supported,
                        'suggestion': '参考 SKILL.md 图表类型表',
                    },
                )

            if transform_code:
                df = DataTransformer().transform(df, transform_code)

            if sort not in ('none', 'value'):
                raise ChartError(
                    f"不支持的 sort: {sort}，支持: none / value",
                    ErrorCode.CHART_CONFIG_ERROR,
                    details={'given': sort, 'supported': ['none', 'value'],
                             'suggestion': 'none=保持数据原序（默认）；value=按第一个数值 Y 列降序（仅 bar/stacked_bar）'},
                )
            if label not in ('auto', 'all', 'key'):
                raise ChartError(
                    f"不支持的 label: {label}，支持: auto / all / key",
                    ErrorCode.CHART_CONFIG_ERROR,
                    details={'given': label, 'supported': ['auto', 'all', 'key'],
                             'suggestion': 'auto=类别>20 时只标关键值（默认）；all=全部标注；key=只标 top3 与极值'},
                )

            texts, lang_resolved = get_texts(lang, df)
            if title is None:
                title = texts['default_title']
            # annotation 必选：未显式提供时生成默认说明，保证每张图都有「图表说明」区块
            # P1-5：来源必须可判别。此前静默填模板，导致 SKILL.md 硬约束 7
            # 「MUST 附解读交付」在输出层无法验证是否真的履行。
            if annotation is None or not str(annotation).strip():
                annotation = texts['default_annotation'].format(n=len(df))
                annotation_source = 'default'
            else:
                annotation_source = 'user'

            if ct is ChartType.SPREADSHEET:
                return self._generate_spreadsheet(
                    df, title, x_axis, y_axis, width, height, texts, lang_resolved,
                    annotation, dry_run, subtitle=subtitle,
                    annotation_source=annotation_source, target=target,
                    extra_advisories=extra_advisories,
                )

            gen = getattr(self, f'_{ct.value}', None)
            if gen is None:
                # 只可能因新增 ChartType 枚举尚未实现渲染器
                raise ChartError(
                    f"暂不支持该图表类型: {chart_type}",
                    ErrorCode.CHART_TYPE_UNSUPPORTED,
                    details={'given': chart_type},
                )

            x_axis, y_axis = self._prepare_axes(df, chart_type, x_axis, y_axis)

            # label_col / color_by 校验与自动探测
            assumptions = []
            for param, col in (('label_col', label_col), ('color_by', color_by)):
                if col is not None and col not in df.columns:
                    raise ChartError(
                        f"{param} 字段不存在: {col}",
                        ErrorCode.CHART_CONFIG_ERROR,
                        details={
                            'given': col,
                            'available': list(df.columns),
                            'suggestion': '从 available 列中选择一个已存在的列',
                        },
                    )
            # 身份列不做自动探测：哪列是身份是语义判断，agent 显式传 --label-col 才生效。
            # 不传则散点/气泡/箱线的数据点无身份标识（tooltip 只显示坐标值），不退化成猜。
            if chart_type in ('graph', 'sankey'):
                # 关系列同样不猜：graph/sankey 的 source/target 由 --x-axis/--y-axis 显式指定，
                # 渲染器从 ctx.x/ctx.y 取；未指定时报结构化错误（见 renderers）。
                pass

            # map/lines 图表：解析地图来源（--geo 内置图名 / --geo-path 自备文件），
            # 把 registerMap 所需三件套塞入 ctx，供渲染器与 template 共用。
            # 非地图图表不触发解析，避免无谓的文件读取与报错。
            geo_fields: Dict[str, Any] = {}
            if chart_type in ('map', 'lines'):
                gs = resolve_geo(geo, geo_path)
                geo_fields = {
                    'geo_map_name': gs.map_name,
                    'geo_json': gs.geojson,
                    'geo_aliases': gs.aliases,
                    'geo_names': geojson_region_names(gs.geojson),
                }

            ctx = RenderContext(
                df=df, x=x_axis, y=y_axis, title=title, texts=texts, theme=self._theme,
                lang=lang_resolved, label_col=label_col, color_by=color_by,
                y_scale=y_scale, sort=sort, label_mode=label, subtitle=subtitle,
                width=width, height=height,
                x_name=x_name, y_names=y_names, series_names=series_names,
                target=target,
                **geo_fields,
            )
            advisories = []
            # P0：粒度口径自检。同一 x 出现多行时，下面这些图型的 max/min/mean 是
            # 行级统计，不等于该 x 的整体——实测「月×地区」明细画 line，plot_stats
            # 报「6月 max 156」实为华东一地（华南同期仅 52.6），照抄即错误结论。
            # 判据用「x 基数 < 行数」而非 plotted_rows == source_rows：散点等以行为
            # 单位的图不该被误判，明细表也确实可能存在重复 x。
            # advisories 是建议性提醒（success 仍为 true、渲染不受影响），供 agent
            # 按语境判断是否换图，刻意不叫 suggestion 以免被当作可机械重试的错误
            if x_axis and x_axis in df.columns and chart_type in _AGG_REQUIRED_TYPES:
                n_rows, n_x = int(len(df)), int(df[x_axis].nunique(dropna=False))
                if n_rows > n_x:
                    vc = df[x_axis].value_counts()
                    advisories.append(
                        f'疑似未聚合：x 轴「{x_axis}」只有 {n_x} 个取值却是 {n_rows} 行数据'
                        f'（如「{vc.index[0]}」占 {int(vc.iloc[0])} 行）。'
                        f'此时 plot_stats 的 max/min/mean 是行级统计，不代表该「{x_axis}」的合计或均值；'
                        f'若要按「{x_axis}」维度下结论，请先 --transform-code 聚合'
                        f"（如 result = df.groupby('{x_axis}')['<数值列>'].sum().reset_index()）"
                    )
            # 饼图类别数守卫：>8 类时人眼难以比较角度
            if ct is ChartType.PIE:
                n_cat = int(df[x_axis].nunique())
                if n_cat > 8:
                    advisories.append(
                        f'饼图类别数为 {n_cat}（>8），人眼难以比较角度；'
                        '建议改用 bar --sort value 做精确对比，或用 transform 聚合小类'
                    )
            # P1-7：gauge/liquid 的"达成率"没有业务目标值时不可计算
            if ct in (ChartType.GAUGE, ChartType.LIQUID) and not target:
                advisories.append(
                    f'{chart_type} 未提供 --target：achievement（达成率）已置 null。'
                    '自动推断的量程不是业务目标，若需达成率请传 --target <目标值>'
                )
            option = gen(ctx)
            option = self._apply_custom_names(option, x_name, y_names, series_names)
            data_points = self._estimate_data_points(df, chart_type, x_axis, y_axis)
            plot_stats = compute_plot_stats(df, chart_type, x_axis, y_axis,
                                            label_col=label_col, target=target,
                                            geo_names=geo_fields.get('geo_names'),
                                            geo_aliases=geo_fields.get('geo_aliases'))
            if dry_run:
                html_path = None
            else:
                html_path = self._save_html(ctx, option, width, height, chart_type, data_points, annotation)
                if getattr(self, '_title_truncated', False):
                    advisories.append('标题超过 30 字符，文件名已截断为 30 字符；完整标题见 title 字段')
            # A3: 绘图数据内联回显——让调用方在生成当轮即可校对聚合口径，无需打开 HTML
            preview, data_rows = self._data_preview(df, x_axis, y_axis)
            # P1-2 对账三元组：unique_entities 优先取身份列（实体主键），
            # 其次取 x 轴去重数——正好对应 SKILL.md 的"按行 vs 按去重实体"校验
            entity_col = label_col if (label_col and label_col in df.columns) else x_axis
            chart_result = {
                'success': True,
                'dry_run': dry_run,
                'html_path': str(html_path) if html_path is not None else None,
                'chart_type': chart_type,
                'title': title,
                'source_rows': source_rows,
                'plotted_rows': data_rows,
                'unique_entities': int(df[entity_col].nunique()) if entity_col in df.columns else int(len(df)),
                'data_rows': data_rows,
                'data_preview': preview,
                'annotation_source': annotation_source,
            }
            if plot_stats is not None:
                chart_result['plot_stats'] = plot_stats
            if assumptions:
                chart_result['assumptions'] = assumptions
            if advisories:
                chart_result['advisories'] = advisories
            self._attach_advisories(chart_result, extra_advisories, annotation_source)
            return {'chart': chart_result}
        except SmartChartsError as e:
            return {
                'chart': {
                    'success': False,
                    'error': e.to_dict(),
                    'chart_type': chart_type,
                    'title': title or '',
                }
            }
        except Exception as e:
            return {
                'chart': {
                    'success': False,
                    'error': {'error': str(e), 'code': ErrorCode.CHART_GENERATION_ERROR.value, 'code_name': ErrorCode.CHART_GENERATION_ERROR.name},
                    'chart_type': chart_type,
                    'title': title or '',
                }
            }

    def _generate_spreadsheet(
        self, df: pd.DataFrame, title: str, x_axis: Optional[str], y_axis: Optional[List[str]],
        width: int, height: int, texts: Dict[str, str], lang: str,
        annotation: str, dry_run: bool, subtitle: Optional[str] = None,
        annotation_source: str = 'default', target: Optional[float] = None,
        extra_advisories: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        # 表格无轴/系列概念：x/y 仅用于筛选显示列（x 在前），都不传则显示全部列。
        # 聚合/透视由 transform_code 完成（与图表管线口径一致），表格只负责呈现。
        if isinstance(y_axis, str):
            y_axis = [y_axis]
        shown = ([x_axis] if x_axis is not None else []) + [c for c in (y_axis or []) if c != x_axis]
        for col in shown:
            if col not in df.columns:
                raise ChartError(
                    f"列不存在: {col}",
                    ErrorCode.CHART_CONFIG_ERROR,
                    details={
                        'given': col,
                        'available': list(df.columns),
                        'suggestion': '从 available 列中选择一个已存在的列',
                    },
                )
        df_table = df[shown] if shown else df
        plot_stats = stats_spreadsheet(df_table)
        if dry_run:
            html_path = None
        else:
            ctx = RenderContext(df=df_table, x=None, y=[], title=title, texts=texts,
                                theme=self._theme, lang=lang, subtitle=subtitle)
            html_path = self._save_table_html(ctx, df_table, title, width, height, annotation)
        preview, data_rows = self._data_preview(df, None, None)
        chart_result = {
            'success': True,
            'dry_run': dry_run,
            'html_path': str(html_path) if html_path is not None else None,
            'chart_type': 'spreadsheet',
            'title': title,
            'source_rows': int(len(df)),
            'plotted_rows': data_rows,
            'unique_entities': int(df_table.drop_duplicates().shape[0]),
            'data_rows': data_rows,
            'data_preview': preview,
            'annotation_source': annotation_source,
        }
        if plot_stats is not None:
            chart_result['plot_stats'] = plot_stats
        if not dry_run and getattr(self, '_title_truncated', False):
            chart_result['advisories'] = ['标题超过 30 字符，文件名已截断为 30 字符；完整标题见 title 字段']
        self._attach_advisories(chart_result, extra_advisories, annotation_source)
        return {'chart': chart_result}

    @staticmethod
    def _apply_custom_names(option: Dict[str, Any], x_name: Optional[str],
                            y_names: Optional[List[str]],
                            series_names: Optional[List[str]]) -> Dict[str, Any]:
        """独立轴名/系列名覆盖（--x-name/--y-name/--series-name/--series-names）。

        在渲染器生成 option 之后统一后处理，避免在 32 个渲染器里各自接线：
        - 轴名：匹配 graphic 元素 id（axisName-x / axisName-y{i}），替换 style.text。
          只改存在轴名 graphic 的图表；无轴名 graphic 的图（如 heatmap/gauge）
          本就无轴名可改，此处自然跳过。
        - 系列名：按「可见系列」顺序映射 series_names。跳过 silent 内部系列
          （waterfall 的透明底座 name 以 __ 开头且 silent=True），避免索引错位。
        均只在对应参数非 None 时生效，未提供时保持渲染器原样（列名/默认文本）。
        """
        if x_name or y_names:
            for g in option.get('graphic', []):
                gid = g.get('id', '')
                if gid == 'axisName-x' and x_name:
                    g.setdefault('style', {})['text'] = x_name
                elif gid.startswith('axisName-y') and y_names:
                    suffix = gid[len('axisName-y'):]
                    try:
                        idx = int(suffix)
                    except ValueError:
                        continue
                    if idx < len(y_names):
                        g.setdefault('style', {})['text'] = y_names[idx]
        if series_names:
            visible = 0
            for s in option.get('series', []):
                if s.get('silent') or str(s.get('name', '')).startswith('__'):
                    continue
                if visible < len(series_names):
                    s['name'] = series_names[visible]
                visible += 1
        return option

    @staticmethod
    def _attach_advisories(chart_result: Dict[str, Any], extra_advisories: Optional[List[str]],
                           annotation_source: str = 'user') -> None:
        """合并解析层 advisory 与渲染层 advisory，并标注 annotation 来源（P2-13 / P1-5）。

        advisories 恒为"建议性提醒"：success 仍为 true、渲染不受影响，是否换图/
        补材料由 agent 按语境判断（刻意不叫 suggestion，避免与错误恢复混淆）。
        """
        merged = list(extra_advisories or [])
        if annotation_source == 'default':
            merged.append(
                'annotation 未由 --annotation 提供，已使用默认模板文案填充；'
                '按交付规范需由 agent 读 plot_stats 后撰写解读并重新生成'
            )
        if merged:
            existing = chart_result.get('advisories')
            chart_result['advisories'] = (existing or []) + merged

    def generate_multi_charts(
        self,
        df: pd.DataFrame,
        chart_configs: List[Dict[str, Any]],
        width: int = 900,
        height: int = 560,
        lang: Optional[str] = None,
        dry_run: bool = False,
        target: Optional[float] = None,
        geo: Optional[str] = None,
        geo_path: Optional[str] = None,
        extra_advisories: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """批量生成多个图表，返回 {'charts': [{'success', 'html_path'/'error', ...}]}。

        每项结构与 generate_chart 的 {'chart': {...}} 内部一致，便于智能体统一解析。
        target: 全局目标值；单图配置里的 target 优先。
        geo/geo_path: 全局地图来源（map/lines 用）；单图配置里的 geo/geo_path 优先。
        """
        results = []
        for cfg in chart_configs:
            r = self.generate_chart(
                df=df,
                chart_type=cfg.get('type', 'bar'),
                title=cfg.get('title') or None,
                x_axis=cfg.get('x_axis'),
                y_axis=cfg.get('y_axis'),
                transform_code=cfg.get('transform_code'),
                width=cfg.get('width', width),
                height=cfg.get('height', height),
                lang=lang,
                label_col=cfg.get('label_col'),
                color_by=cfg.get('color_by'),
                annotation=cfg.get('annotation'),
                subtitle=cfg.get('subtitle'),
                sort=cfg.get('sort', 'none'),
                y_scale=bool(cfg.get('y_scale', False)),
                label=cfg.get('label', 'auto'),
                dry_run=dry_run,
                target=cfg.get('target', target),
                x_name=cfg.get('x_name'),
                y_names=cfg.get('y_name'),
                series_names=cfg.get('series_names') or (([cfg.get('series_name')] if cfg.get('series_name') else None)),
                geo=cfg.get('geo', geo),
                geo_path=cfg.get('geo_path', geo_path),
                extra_advisories=extra_advisories,
            )
            chart_result = r['chart']
            chart_result['config'] = cfg
            results.append(chart_result)
        return {'charts': results}

    # ---- 轴自动检测 ----

    def _prepare_axes(self, df, chart_type, x_axis, y_axis) -> Tuple[str, List[str]]:
        # 直方图无类别轴，只有一个分布数值列：用户显式传入的数值 x 就是分布列，
        # 锁定为 y，防止下方 y 自动补全换成其他数值列
        # （如 df=[学号,总成绩] + --x-axis 总成绩 时 y 被自动补成学号，画出错误分布）
        if (chart_type == 'histogram'
                and x_axis is not None and x_axis in df.columns
                and pd.api.types.is_numeric_dtype(df[x_axis])):
            y_axis = [x_axis]

        # 层级图（mindmap/orgchart）：x=父节点列，y[0]=子节点列（均为分类列）。
        # 必须显式指定，不猜关系列、不退到「前两个分类列」——哪两列构成层级是语义判断。
        if chart_type in ('mindmap', 'orgchart'):
            if y_axis is None or x_axis is None:
                raise ChartError(
                    f"{chart_type} 需要 父节点列(x) + 子节点列(y) 两个分类列",
                    ErrorCode.CHART_CONFIG_ERROR,
                    details={
                        'available': list(df.columns),
                        'suggestion': '用 --x-axis <父列> --y-axis <子列> 显式指定层级关系',
                    },
                )

        # 关系图（graph/sankey/lines）：source(x) + target(y[0]) 两列必需，value(y[1]) 可选。
        # 必须显式指定，不猜关系列——哪列是 source/target 是语义判断。
        if chart_type in ('graph', 'sankey', 'lines'):
            if x_axis is None or not y_axis:
                raise ChartError(
                    f"{chart_type} 需要 来源列(x) + 去向列(y) 两列（可选 值列）",
                    ErrorCode.CHART_CONFIG_ERROR,
                    details={
                        'available': list(df.columns),
                        'suggestion': '用 --x-axis <来源列> --y-axis <去向列> [<值列>] 显式指定',
                    },
                )

        if x_axis is None:
            date_cols = df.select_dtypes(include=['datetime', 'datetime64']).columns
            cat_cols = df.select_dtypes(include=['object', 'string', 'category']).columns
            x_axis = date_cols[0] if len(date_cols) > 0 else (cat_cols[0] if len(cat_cols) > 0 else df.columns[0])

        if y_axis is None:
            avail = [c for c in df.columns if c != x_axis]
            nums = df[avail].select_dtypes(include=[np.number]).columns.tolist()
            y_axis = nums[:5] if nums else avail[:3]
        elif isinstance(y_axis, str):
            y_axis = [y_axis]

        if x_axis not in df.columns:
            raise ChartError(
                f"X轴字段不存在: {x_axis}",
                ErrorCode.CHART_CONFIG_ERROR,
                details={
                    'given': x_axis,
                    'available': list(df.columns),
                    'suggestion': '从 available 列中选择一个已存在的列，或提供 transform_code 生成所需列',
                },
            )
        for y in y_axis:
            if y not in df.columns:
                raise ChartError(
                    f"Y轴字段不存在: {y}",
                    ErrorCode.CHART_CONFIG_ERROR,
                    details={
                        'given': y,
                        'available': list(df.columns),
                        'suggestion': '从 available 列中选择一个已存在的列，或提供 transform_code 生成所需列',
                    },
                )
        return x_axis, y_axis

    def _data_preview(self, df: pd.DataFrame, x_axis: Optional[str], y_axis: Optional[List[str]], limit: int = 10) -> Tuple[List[Dict[str, Any]], int]:
        """生成最终绘图数据的紧凑预览（stdout 的 data_preview / data_rows 字段）。

        取 transform 之后、渲染所用的同一份 DataFrame 中 [x_axis] + y_axis 列的前 limit 行：
        NaN/NaT → None；数值统一转 JSON 可序列化的 int/float；其余转 str。
        x_axis/y_axis 均为 None 时（spreadsheet 全列模式）取全部列。
        供调用方在生成当轮校对聚合口径（按行 vs 按去重实体），无需打开 HTML 文件。
        """
        cols = list(dict.fromkeys(
            ([x_axis] if x_axis is not None else []) + list(y_axis or []))) or list(df.columns)
        records: List[Dict[str, Any]] = []
        for _, row in df[cols].head(limit).iterrows():
            rec: Dict[str, Any] = {}
            for c in cols:
                v = row[c]
                try:
                    if v is None or pd.isna(v):
                        rec[c] = None
                        continue
                except (TypeError, ValueError):
                    pass
                if isinstance(v, str):
                    rec[c] = v
                elif isinstance(v, (bool, np.bool_)):
                    rec[c] = bool(v)
                else:
                    try:
                        f = float(v)
                        rec[c] = int(f) if f.is_integer() and abs(f) < 2 ** 53 else f
                    except (TypeError, ValueError):
                        rec[c] = str(v)
            records.append(rec)
        return records, len(df)

    def _estimate_data_points(self, df: pd.DataFrame, chart_type: str, x_axis: str, y_axis: List[str]) -> int:
        """估算图表 X 轴类别数量，用于决定 HTML 容器是否需要横向滚动兜底。

        只有 X 轴为类别轴且数据点可能过多的图表（bar/line/area 等）才返回非零值；
        heatmap 是网格布局，每个单元格远窄于柱状图柱子，不需要横向滚动；
        scatter（数值轴）/boxplot（列名轴）/pie/treemap 等也不需要，返回 0。
        """
        try:
            if chart_type in ('bar', 'line', 'area', 'stacked_bar', 'combo', 'pareto', 'pictorial_bar'):
                # P2-12：语义是 X 轴类别数，不是 DataFrame 行数。长格式数据
                # （12 个月 × 5 系列 = 60 行）此前被算成 60 个数据点，
                # 会把容器撑到 60×最小像素宽，横向滚动兜底被无谓触发。
                if x_axis is not None and x_axis in df.columns:
                    return int(df[x_axis].nunique())
                return len(df)
        except Exception:
            pass
        return 0
