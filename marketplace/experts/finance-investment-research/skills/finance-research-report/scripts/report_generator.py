"""
报告生成模块 - 生成每周金融投研报告 (PDF格式)
参考西南证券研报格式，使用 HTML+CSS 渲染后通过 weasyprint 转为 PDF。
内容紧凑排版，嵌入 matplotlib 图表。
"""
from datetime import datetime
from technical_analysis import TechnicalSignal
from chart_generator import (
    chart_stock_price_ma,
    chart_macd_rsi,
    chart_index_comparison,
    chart_signal_summary,
)
from weasyprint import HTML
import pandas as pd


# ============================================================
# CSS
# ============================================================
CSS = """
@page {
    size: A4;
    margin: 1.8cm 1.6cm 2cm 1.6cm;
    @bottom-center {
        content: "请务必阅读正文后的重要声明部分";
        font-size: 7pt; color: #aaa;
    }
    @bottom-right {
        content: counter(page);
        font-size: 8pt; color: #888;
    }
}
@page :first {
    @bottom-center { content: none; }
    @bottom-right  { content: none; }
}

body {
    font-family: "PingFang SC","Hiragino Sans GB","Microsoft YaHei","Noto Sans CJK SC",sans-serif;
    font-size: 9.5pt; line-height: 1.55; color: #333;
}
h1,h2,h3,h4 { margin-top: 0.5em; margin-bottom: 0.2em; }
p { margin: 0.3em 0; }
ul { margin: 0.3em 0; padding-left: 1.4em; }
li { margin-bottom: 2px; }
img.chart { width: 100%; margin: 6px 0; }

/* ---- 封面 ---- */
.cover { page-break-after: always; padding-top: 30px; }
.cover-header {
    border-bottom: 3px solid #b00;
    padding-bottom: 4px; margin-bottom: 6px;
}
.cover-brand { color: #b00; font-size: 12pt; font-weight: bold; }
.cover-type { font-size: 9pt; color: #777; margin-left: 12px; }
.cover-title { font-size: 20pt; font-weight: bold; color: #222; margin: 18px 0 6px 0; }
.cover-period { font-size: 10pt; color: #555; margin-bottom: 16px; }
.cover-meta { font-size: 9pt; color: #555; line-height: 1.8; margin-bottom: 14px; }
.cover-meta strong { color: #333; }

.kp-box {
    border: 1px solid #b00; border-radius: 4px;
    padding: 10px 14px; background: #fdf6f6; margin-top: 14px;
}
.kp-box h3 { color: #b00; font-size: 11pt; margin: 0 0 6px 0; border-bottom: 1px solid #ecc; padding-bottom: 4px; }
.kp-box ul { padding-left: 16px; margin: 0; }
.kp-box li { font-size: 9pt; margin-bottom: 3px; }

.tag { display: inline-block; padding: 1px 8px; border-radius: 3px; font-size: 8pt; font-weight: bold; margin-right: 4px; }
.tag-r { background: #ffe0e0; color: #b00; }
.tag-g { background: #e0ffe0; color: #060; }
.tag-n { background: #e8e8e8; color: #555; }

/* ---- 章节 ---- */
h2.sec { color: #b00; font-size: 12pt; border-bottom: 2px solid #b00; padding-bottom: 3px; margin-top: 1em; }
h3.sub { font-size: 10pt; color: #333; border-left: 3px solid #b00; padding-left: 6px; margin-top: 0.8em; }

/* ---- 表格 ---- */
table { width: 100%; border-collapse: collapse; margin: 6px 0 10px 0; font-size: 8.5pt; }
th { background: #b00; color: #fff; padding: 4px 6px; text-align: center; font-weight: bold; font-size: 8pt; }
td { padding: 3px 6px; border-bottom: 1px solid #ddd; text-align: center; }
tr:nth-child(even) td { background: #f9f9f9; }

/* ---- 个股卡片 ---- */
.sc {
    border: 1px solid #ddd; border-radius: 4px;
    padding: 8px 12px; margin: 8px 0; background: #fafafa;
    page-break-inside: avoid;
}
.sc h4 { margin: 0 0 4px 0; color: #b00; font-size: 10.5pt; }
.sc .pl { font-size: 9pt; color: #555; margin-bottom: 6px; }
.sc .pl .pr { font-size: 14pt; font-weight: bold; color: #222; }
.up { color: #c00; } .dn { color: #090; }

/* 信号卡片 */
.sig-card {
    border-left: 3px solid #b00; padding: 6px 10px; margin: 6px 0;
    background: #fafafa; page-break-inside: avoid;
}
.sig-card h4 { margin: 0 0 4px 0; font-size: 10pt; }
.buy { color: #c00; font-weight: bold; }
.sell { color: #090; font-weight: bold; }

/* ---- 两栏指标 ---- */
.two-col { display: flex; gap: 10px; }
.two-col > div { flex: 1; }

/* ---- 风险/免责 ---- */
.risk-box {
    border: 1px solid #f5c6c6; background: #fef8f8;
    padding: 8px 12px; border-radius: 4px; margin: 8px 0; font-size: 8.5pt;
}
.disclaimer {
    margin-top: 16px; padding-top: 8px; border-top: 2px solid #b00;
    font-size: 8pt; color: #888; line-height: 1.7;
}
"""


# ============================================================
# HTML 片段
# ============================================================

def _cover(report_date, start, end, author, signals):
    bull = sum(1 for s in signals if len(s.buy_signals) > len(s.sell_signals))
    bear = sum(1 for s in signals if len(s.sell_signals) > len(s.buy_signals))
    neut = len(signals) - bull - bear

    items = ""
    for s in signals:
        d = "看多" if len(s.buy_signals) > len(s.sell_signals) else "看空" if len(s.sell_signals) > len(s.buy_signals) else "中性"
        items += f'<li><strong>{s.name}（{s.symbol}）</strong>：{d}，信号{s.signal_strength}，风险{s.risk_score:.1f}/10，仓位{s.position_coeff:.0%}</li>\n'

    return f"""
<div class="cover">
  <div class="cover-header">
    <span class="cover-brand">AI 投研助手</span>
    <span class="cover-type">证券研究报告 · 每周技术分析</span>
  </div>
  <div class="cover-title">每周金融投研报告</div>
  <div class="cover-period">报告周期：{start} 至 {end}</div>
  <div class="cover-meta">
    <strong>发布日期</strong>：{report_date} &nbsp;&nbsp;
    <strong>分析师</strong>：{author} &nbsp;&nbsp;
    <strong>数据来源</strong>：AKShare / 新浪财经 / 东方财富
  </div>
  <div class="kp-box">
    <h3>投资要点</h3>
    <p style="font-size:9pt">本周跟踪 {len(signals)} 只标的：
      <span class="tag tag-r">看多 {bull}</span>
      <span class="tag tag-g">看空 {bear}</span>
      <span class="tag tag-n">中性 {neut}</span>
    </p>
    <ul>{items}
      <li><em style="font-size:8.5pt">风险提示：市场波动、政策变化、流动性、模型误差风险。本报告仅供参考，不构成投资建议。</em></li>
    </ul>
  </div>
  <table style="margin-top:14px;font-size:8.5pt">
    <tr><th>数据类型</th><th>数据来源</th></tr>
    <tr><td>A股日线行情（前复权）</td><td>新浪财经</td></tr>
    <tr><td>主要指数日线</td><td>新浪财经</td></tr>
    <tr><td>个股实时行情</td><td>新浪财经</td></tr>
    <tr><td>市场涨跌统计</td><td>新浪财经</td></tr>
    <tr><td>北向资金</td><td>东方财富</td></tr>
    <tr><td>个股相关新闻</td><td>东方财富</td></tr>
    <tr><td>全球财经要闻</td><td>东方财富</td></tr>
  </table>
</div>"""


def _market(index_data, breadth, north_flow, headlines, idx_chart_b64, stock_news, signals):
    rows = ""
    for name, d in index_data.items():
        if d:
            p = d.get("pct_change", "0")
            c = "class='up'" if float(p) > 0 else "class='dn'" if float(p) < 0 else ""
            rows += f'<tr><td style="text-align:left">{name}</td><td>{d.get("close","-")}</td><td {c}>{p}%</td><td>{d.get("high","-")}</td><td>{d.get("low","-")}</td><td>{d.get("volume","-")}</td></tr>\n'

    chart_html = f'<img class="chart" src="data:image/png;base64,{idx_chart_b64}">' if idx_chart_b64 else ""

    breadth_html = ""
    if breadth:
        breadth_html = f"""
        <h3 class="sub">1.2 市场情绪</h3>
        <table><tr><th>上涨</th><th>下跌</th><th>平盘</th><th>涨停</th><th>跌停</th><th>总计</th></tr>
        <tr><td class="up">{breadth.get('上涨家数','-')}</td><td class="dn">{breadth.get('下跌家数','-')}</td>
        <td>{breadth.get('平盘家数','-')}</td><td class="up">{breadth.get('涨停家数','-')}</td>
        <td class="dn">{breadth.get('跌停家数','-')}</td><td>{breadth.get('总家数','-')}</td></tr></table>"""

    north = north_flow.get("total", 0) if north_flow else 0
    nc = "class='up'" if north > 0 else "class='dn'" if north < 0 else ""

    # 持仓相关资讯（个股新闻）
    stock_news_html = ""
    if stock_news:
        # 建立 symbol -> name 映射
        name_map = {s.symbol: s.name for s in signals}
        items = ""
        for symbol, news_list in stock_news.items():
            sname = name_map.get(symbol, symbol)
            for n in news_list[:3]:
                title = n.get("title", "")[:60]
                time_str = n.get("time", "")[:10]
                items += f'<li><strong>{sname}</strong>：{title} <span style="color:#aaa;font-size:7.5pt">({time_str})</span></li>\n'
        if items:
            stock_news_html = f"""
<h3 class="sub">1.4 持仓相关资讯</h3>
<ul style="font-size:8.5pt">{items}</ul>"""

    # 宏观要闻（精简）
    macro_html = ""
    if headlines:
        macro_items = ""
        for h in headlines[:4]:
            text = h[:70] + "…" if len(h) > 70 else h
            macro_items += f"<li>{text}</li>\n"
        macro_html = f"""
<h3 class="sub">1.5 宏观要闻</h3>
<ul style="font-size:8.5pt">{macro_items}</ul>"""

    return f"""
<h2 class="sec">1 &nbsp; 市场概览</h2>
<h3 class="sub">1.1 主要指数</h3>
<table><tr><th>指数</th><th>收盘价</th><th>涨跌幅</th><th>最高</th><th>最低</th><th>成交量</th></tr>{rows}</table>
{chart_html}
{breadth_html}
<h3 class="sub">1.3 北向资金</h3>
<p>本周净流入：<strong {nc}>{north:.2f} 亿元</strong></p>
{stock_news_html}
{macro_html}
"""


def _stock_section(signals, stock_dfs):
    blocks = ""
    for i, sig in enumerate(signals, 1):
        d = "看多" if len(sig.buy_signals) > len(sig.sell_signals) else "看空" if len(sig.sell_signals) > len(sig.buy_signals) else "中性"
        dc = "up" if d == "看多" else "dn" if d == "看空" else ""
        p1c = "up" if sig.pct_change_1d > 0 else "dn" if sig.pct_change_1d < 0 else ""
        p5c = "up" if sig.pct_change_5d > 0 else "dn" if sig.pct_change_5d < 0 else ""

        rsi_s = "超买" if sig.rsi > 70 else "超卖" if sig.rsi < 30 else "正常"
        macd_s = "多头" if sig.macd > sig.macd_signal else "空头"
        hist_s = "红柱" if sig.macd_hist > 0 else "绿柱"
        kdj_s = "超买" if sig.kdj_j > 100 else "超卖" if sig.kdj_j < 0 else "正常"
        vol_s = "放量" if sig.volume_ratio > 1.5 else "缩量" if sig.volume_ratio < 0.7 else "正常"
        ma_h = "趋势向好" if sig.ma_alignment == "多头排列" else "趋势偏弱" if sig.ma_alignment == "空头排列" else "方向不明"

        # 图表
        df = stock_dfs.get(sig.symbol)
        price_chart = ""
        indicator_chart = ""
        if df is not None and len(df) > 20:
            b64_price = chart_stock_price_ma(df, sig.name, sig.symbol)
            b64_ind = chart_macd_rsi(df, sig.name, sig.symbol)
            price_chart = f'<img class="chart" src="data:image/png;base64,{b64_price}">'
            indicator_chart = f'<img class="chart" src="data:image/png;base64,{b64_ind}">'

        blocks += f"""
<div class="sc">
  <h4>2.{i} &nbsp; {sig.name}（{sig.symbol}）</h4>
  <div class="pl">
    最新价 <span class="pr">{sig.close:.2f}</span> 元 &nbsp;|&nbsp;
    日涨跌 <span class="{p1c}">{sig.pct_change_1d:+.2f}%</span> &nbsp;|&nbsp;
    5日涨跌 <span class="{p5c}">{sig.pct_change_5d:+.2f}%</span> &nbsp;|&nbsp;
    趋势 <span class="{dc}" style="font-weight:bold">{d}</span>
  </div>
  {price_chart}
  <div class="two-col">
    <div>
      <table>
        <tr><th colspan="3">均线 &amp; 量价</th></tr>
        <tr><td>MA5</td><td>{sig.ma5:.2f}</td><td>MA10: {sig.ma10:.2f}</td></tr>
        <tr><td>MA20</td><td>{sig.ma20:.2f}</td><td>{sig.ma_alignment}（{ma_h}）</td></tr>
        <tr><td>量比</td><td>{sig.volume_ratio:.2f}（{vol_s}）</td><td>换手率: {sig.turnover_rate:.2f}%</td></tr>
      </table>
    </div>
    <div>
      <table>
        <tr><th colspan="3">动量 &amp; 波动</th></tr>
        <tr><td>RSI(14)</td><td>{sig.rsi:.1f}</td><td>{rsi_s}</td></tr>
        <tr><td>MACD柱</td><td>{sig.macd_hist:.4f}</td><td style="color:{'#c00' if sig.macd_hist > 0 else '#090'}">{hist_s}</td></tr>
        <tr><td>KDJ-J</td><td>{sig.kdj_j:.1f}</td><td>{kdj_s}</td></tr>
        <tr><td>ATR(14)</td><td>{sig.atr:.2f}</td><td>振幅: {sig.intraday_range:.2f}%</td></tr>
      </table>
    </div>
  </div>
  {indicator_chart}
</div>"""

    return f'<h2 class="sec">2 &nbsp; 个股技术分析</h2>\n{blocks}'


def _sector_flow(sector_flow):
    if not sector_flow:
        return ""  # 无数据不占空间
    rows = ""
    for s in sector_flow[:15]:
        rows += f'<tr><td style="text-align:left">{s.get("name","-")}</td><td>{s.get("change","-")}</td><td>{s.get("net_flow","-")}</td><td>{s.get("main_flow","-")}</td></tr>\n'
    return f"""
<h2 class="sec">3 &nbsp; 行业板块资金流向</h2>
<table><tr><th>行业</th><th>涨跌幅</th><th>净流入(亿)</th><th>主力净流入(亿)</th></tr>{rows}</table>"""


def _signals(signals, summary_chart_b64):
    chart_html = f'<img class="chart" src="data:image/png;base64,{summary_chart_b64}">' if summary_chart_b64 else ""
    cards = ""
    for sig in signals:
        d = "看多" if len(sig.buy_signals) > len(sig.sell_signals) else "看空" if len(sig.sell_signals) > len(sig.buy_signals) else "中性"
        dc = "#b00" if d == "看多" else "#090" if d == "看空" else "#666"
        buy = "、".join(sig.buy_signals) or "无"
        sell = "、".join(sig.sell_signals) or "无"
        cards += f"""
<div class="sig-card" style="border-left-color:{dc}">
  <h4>{sig.name}（{sig.symbol}）—— <span style="color:{dc}">{d}</span></h4>
  <table><tr><th>类型</th><th>详情</th></tr>
  <tr><td class="buy">买入</td><td style="text-align:left">{buy}</td></tr>
  <tr><td class="sell">卖出</td><td style="text-align:left">{sell}</td></tr>
  <tr><td>强度</td><td>{sig.signal_strength}</td></tr></table>
</div>"""

    return f"""
<h2 class="sec">__SEC_SIGNAL__ &nbsp; 交易信号汇总</h2>
{chart_html}
{cards}"""


def _risk(signals):
    rows = ""
    for s in signals:
        rows += f'<tr><td style="text-align:left">{s.name}（{s.symbol}）</td><td>{s.risk_score:.1f}</td><td>{s.position_coeff:.0%}</td><td>{s.stop_loss:.2f}</td><td>{s.take_profit:.2f}</td></tr>\n'
    return f"""
<h2 class="sec">__SEC_RISK__ &nbsp; 风险评估与仓位建议</h2>
<table><tr><th>标的</th><th>风险评分</th><th>仓位系数</th><th>止损位</th><th>止盈位</th></tr>{rows}</table>
<p style="font-size:8.5pt"><strong>止损位</strong> = min(前日低点×0.995, MA10×0.99, 入场价×0.95)
&nbsp;&nbsp; <strong>止盈位</strong> = 当前价 + ATR×2
&nbsp;&nbsp; <strong>仓位系数</strong> = (10−风险评分)/10</p>"""


def _disclaimer(author):
    return f"""
<h2 class="sec">__SEC_DISCL__ &nbsp; 风险提示</h2>
<div class="risk-box">
<ul>
  <li><strong>市场系统性风险</strong>：宏观经济下行、地缘政治等可能导致整体下跌</li>
  <li><strong>政策风险</strong>：监管变化可能对行业/个股产生重大影响</li>
  <li><strong>流动性风险</strong>：部分标的流动性不足，可能无法及时止损</li>
  <li><strong>模型风险</strong>：技术分析基于历史数据，不代表未来走势</li>
  <li><strong>数据风险</strong>：公开市场数据可能存在延迟或误差</li>
</ul>
</div>
<div class="disclaimer">
  <strong>重要声明</strong>：本报告由 {author} 基于公开市场数据自动生成（AKShare / 新浪财经 / 东方财富），仅供参考和学习交流，<strong>不构成任何投资建议</strong>。<br>
  <strong>指标体系</strong>：均线 MA5/10/20 | RSI(14) | MACD(12,26,9) | KDJ(9,3,3) | ATR(14) | 量比(5日) | 换手率
  <p style="text-align:center;margin-top:12px;color:#aaa;font-size:7.5pt">
    报告生成：{datetime.now().strftime("%Y-%m-%d %H:%M:%S")} &nbsp; Powered by AKShare &amp; OpenClaw AI
  </p>
</div>"""


# ============================================================
# 公开接口
# ============================================================

def generate_report(
    report_date: str,
    week_range: tuple[str, str],
    index_data: dict,
    stock_signals: list[TechnicalSignal],
    sector_flow: list[dict],
    market_breadth: dict,
    north_flow_summary: dict,
    macro_headlines: list[str],
    author: str = "AI投研助手",
    stock_dfs: dict[str, pd.DataFrame] | None = None,
    stock_news: dict[str, list[dict]] | None = None,
) -> str:
    """生成完整 HTML（含内嵌图表），通过 render_pdf 转 PDF"""
    start = f"{week_range[0][:4]}-{week_range[0][4:6]}-{week_range[0][6:]}"
    end = f"{week_range[1][:4]}-{week_range[1][4:6]}-{week_range[1][6:]}"
    stock_dfs = stock_dfs or {}
    stock_news = stock_news or {}

    # 生成图表
    idx_chart = chart_index_comparison(index_data)
    sig_chart = chart_signal_summary(stock_signals)

    has_sector = bool(sector_flow)

    body = "".join([
        _cover(report_date, start, end, author, stock_signals),
        _market(index_data, market_breadth, north_flow_summary, macro_headlines, idx_chart, stock_news, stock_signals),
        _stock_section(stock_signals, stock_dfs),
        _sector_flow(sector_flow),
        _signals(stock_signals, sig_chart),
        _risk(stock_signals),
        _disclaimer(author),
    ])

    # 动态章节编号
    if has_sector:
        body = body.replace("__SEC_SIGNAL__", "4")
        body = body.replace("__SEC_RISK__", "5")
        body = body.replace("__SEC_DISCL__", "6")
    else:
        body = body.replace("__SEC_SIGNAL__", "3")
        body = body.replace("__SEC_RISK__", "4")
        body = body.replace("__SEC_DISCL__", "5")

    return f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8"><style>{CSS}</style></head>
<body>{body}</body></html>"""


def render_pdf(html_content: str, output_path: str) -> str:
    """将 HTML 渲染为 PDF，通过 Ghostscript 优化以兼容 macOS Preview"""
    import subprocess, tempfile, shutil, os

    tmp_path = output_path + ".tmp.pdf"
    HTML(string=html_content).write_pdf(tmp_path)

    gs_bin = shutil.which("gs")
    if gs_bin:
        try:
            subprocess.run([
                gs_bin, "-dNOPAUSE", "-dBATCH", "-dSAFER",
                "-sDEVICE=pdfwrite", "-dCompatibilityLevel=1.4",
                "-dPDFSETTINGS=/prepress",
                "-dEmbedAllFonts=true", "-dSubsetFonts=true",
                f"-sOutputFile={output_path}", tmp_path,
            ], check=True, capture_output=True)
            os.remove(tmp_path)
        except subprocess.CalledProcessError:
            os.replace(tmp_path, output_path)
    else:
        os.replace(tmp_path, output_path)

    return output_path
