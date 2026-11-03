#!/usr/bin/env python3
"""smart-charts 开发者回归自测脚本。

端到端验证技能全链路（真实 CLI 子进程，非 mock）：
- 校验层：黑名单/AST 单元测试、transform 错误码契约、超时机制
- 解析层：CSV/TSV/TXT/JSON/GBK/Excel、脏表头 flags、多文件合并
- 渲染层：32 种图表（契约键 + HTML 落盘）、命名覆盖、新增图表专项
- 画像层：--profile 列画像/粒度/洞察信号/图型建议、粒度口径自检
- 多图模式、flags/主题/语言/dry-run/annotation、错误路径、transform 黄金模式

用法：python scripts/regression_check.py [技能根目录]（默认为脚本上级目录）
测试数据与输出写入 tempfile 临时目录，不污染技能目录；退出码 0=全过，1=有失败。
"""
import contextlib, io, json, os, re, subprocess, sys, tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

BASE = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent
CLI = BASE / 'scripts' / 'cli.py'
DP = BASE / 'scripts' / 'data_parser.py'
ROOT = Path(tempfile.mkdtemp(prefix='sc_regression_'))
DATA = ROOT / 'data'
OUT = ROOT / 'out'
DATA.mkdir(parents=True, exist_ok=True)
OUT.mkdir(parents=True, exist_ok=True)

sys.path.insert(0, str(BASE))
import pandas as pd
import scripts.cli as cli_mod
import scripts.data_parser as dp_mod
from scripts.chart_generator import ChartGenerator, ChartType
from scripts.data_parser import DataParser
from scripts.data_transformer import DataTransformer, validate_code_ast, validate_code_blacklist
from scripts.exceptions import ErrorCode, SmartChartsError
from scripts.plot_stats import compute_plot_stats
from scripts.profile import build_profile

PASS, FAIL = 0, 0
FAILURES = []
# CLI 用例彼此独立（各起一个 Python 子进程），并发能把端到端耗时压到 1/3 左右
WORKERS = min(8, os.cpu_count() or 4)


def rec(name, ok, detail=''):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"[PASS] {name}")
    else:
        FAIL += 1
        FAILURES.append((name, detail))
        print(f"[FAIL] {name}  -- {detail}")


def run_cli(args, timeout=90):
    args = [str(a) for a in args]
    # 统一补 --output-dir：CLI 默认 ./smart_charts_output 是相对 CWD 的，
    # 漏传的用例会把 HTML 写进当前目录（跑一次就在技能包里堆出上百个文件）。
    # 但 --profile / --doctor 不写 HTML，且 --profile 对白名单外的出图参数会报错，
    # 因此这两种模式不注入 --output-dir。
    if ('--output-dir' not in args and '--profile' not in args
            and '--doctor' not in args):
        args += ['--output-dir', str(OUT)]
    proc = subprocess.run([sys.executable, str(CLI)] + args,
                          capture_output=True, text=True, timeout=timeout)
    out = None
    if proc.stdout.strip():
        with contextlib.suppress(json.JSONDecodeError):
            out = json.loads(proc.stdout)
    return proc.returncode, out, proc.stderr


def run_many(arg_lists, workers=WORKERS):
    """并行跑多条互相独立的 CLI，返回与入参同序的 (rc, out, stderr) 列表。"""
    if len(arg_lists) <= 1:
        return [run_cli(a) for a in arg_lists]
    with ThreadPoolExecutor(max_workers=workers) as ex:
        return list(ex.map(run_cli, arg_lists))


def run_dp(args, timeout=60):
    proc = subprocess.run([sys.executable, str(DP)] + [str(a) for a in args],
                          capture_output=True, text=True, timeout=timeout)
    return proc.returncode, proc.stdout, proc.stderr


def html_of(res):
    """从 run_cli/run_many 的单条结果里取 HTML 全文（未落盘返回空串）。"""
    path = (res[1] or {}).get('chart', {}).get('html_path')
    return Path(path).read_text(encoding='utf-8') if path and Path(path).exists() else ''


def seg_of(res):
    """取 HTML 中 `var chartOption = ` 之后的片段（渲染失败返回 None）。"""
    html = html_of(res)
    return html.split('var chartOption = ', 1)[1] if 'var chartOption = ' in html else None


def extra_of(res):
    """取 plot_stats.extra（各图表类型专属统计，如 region_count / edge_count / days）。"""
    return (res[1] or {}).get('chart', {}).get('plot_stats', {}).get('extra', {})


def profile(path, via='cli'):
    """取数据画像：cli --profile（不经 chart_type 校验）或 data_parser --profile。"""
    if via == 'cli':
        return run_cli([path, '--profile'])
    rc, so, se = run_dp([path, '--profile'])
    try:
        return rc, json.loads(so), se
    except json.JSONDecodeError:
        return rc, None, se

# ══════════════════ 数据准备 ══════════════════
(DATA / 'cities.csv').write_text(
    "城市,销售额,利润,人口万\n北京,1200,300,2189\n上海,1500,400,2487\n广州,900,180,1874\n深圳,1100,260,1768\n", encoding='utf-8')
(DATA / 'trend.csv').write_text(
    "月份,销售额,利润\n1月,1000,250\n2月,1150,280\n3月,1300,320\n4月,1280,310\n5月,1420,360\n6月,1550,390\n", encoding='utf-8')
(DATA / 'freq.csv').write_text(
    "类别\nA\nB\nA\nC\nA\nB\nC\nD\nA\nB\n\nC\n", encoding='utf-8')
(DATA / 'students.csv').write_text(
    "姓名,数学,语文,英语\n张三,85,78,92\n李四,92,88,95\n王五,60,72,68\n赵六,75,80,77\n钱七,88,85,90\n孙八,45,60,55\n周九,95,93,97\n吴十,70,68,74\n", encoding='utf-8')
(DATA / 'radar.csv').write_text(
    "指标,产品A,产品B\n性能,90,75\n易用性,85,80\n功能,70,92\n价格,60,85\n服务,80,70\n", encoding='utf-8')
(DATA / 'heat.csv').write_text(
    "星期,早高峰,午高峰,晚高峰\n周一,320,280,410\n周二,340,275,420\n周三,335,290,435\n周四,350,285,425\n周五,380,300,470\n", encoding='utf-8')
(DATA / 'graph.csv').write_text(
    "source,target,value\nA,B,5\nA,C,3\nB,D,2\nC,D,4\nD,E,1\n", encoding='utf-8')
(DATA / 'relation.csv').write_text(
    "来源,去向,金额\n总部,华北分部,500\n总部,华南分部,400\n华北分部,北京办,200\n", encoding='utf-8')
(DATA / 'funnel.csv').write_text(
    "阶段,人数\n浏览,10000\n加购,3000\n下单,1200\n支付,900\n复购,300\n", encoding='utf-8')
(DATA / 'words.csv').write_text(
    "关键词,频次\n数据,120\n分析,95\n可视化,88\n模型,76\n图表,70\n统计,60\n", encoding='utf-8')
(DATA / 'venn.csv').write_text(
    "name,value\n仅A,40\n仅B,25\nA∩B,15\n", encoding='utf-8')
(DATA / 'org.csv').write_text(
    "parent,child\n根,分支A\n根,分支B\n分支A,叶子1\n分支A,叶子2\n分支B,叶子3\n", encoding='utf-8')
(DATA / 'gauge.csv').write_text(
    "完成率\n78.5\n82.3\n75.0\n79.9\n", encoding='utf-8')
(DATA / 'scatter_xy.csv').write_text(
    "x_val,y_val\n10,20\n15,30\n20,40\n25,50\n", encoding='utf-8')
(DATA / 'waterfall.csv').write_text(
    "month,profit\n1月,100\n2月,120\n3月,90\n4月,110\n5月,130\n", encoding='utf-8')
(DATA / 'pareto.csv').write_text(
    "类别,数量\nA,45\nB,30\nC,15\nD,6\nE,4\n", encoding='utf-8')
(DATA / 'special.csv').write_text(
    "销售额(元),A/B\n100,5\n200,8\n150,6\n", encoding='utf-8')
(DATA / 'messy.csv').write_text(
    "这是一份导出说明\n导出时间:2026-01-01\n城市,销售额\n北京,120\n上海,180\n广州,150\n", encoding='utf-8')
(DATA / 'ffill.csv').write_text(
    "部门,经理,工资\n技术部,张三,12000\n,,11500\n市场部,李四,10000\n,,9800\n", encoding='utf-8')
(DATA / 'en.csv').write_text(
    "city,revenue,profit\nNYC,1000,250\nLA,850,180\nChicago,720,150\n", encoding='utf-8')
(DATA / 'nested.json').write_text(
    json.dumps([{"城市": "北京", "销售额": 100, "详情": {"区域": "华北"}},
                {"城市": "上海", "销售额": 150, "详情": {"区域": "华东"}}], ensure_ascii=False), encoding='utf-8')
(DATA / 'students.tsv').write_text(
    "姓名\t数学\t语文\n张三\t85\t78\n李四\t92\t88\n", encoding='utf-8')
(DATA / 'scores.txt').write_text(
    "姓名;数学\n张三;85\n李四;92\n", encoding='utf-8')
(DATA / 'm1.csv').write_text("城市,销售额\n北京,100\n上海,200\n", encoding='utf-8')
(DATA / 'sales_long.csv').write_text("month,region,revenue\n1月,east,200\n1月,north,150\n2月,east,220\n2月,north,160\n3月,east,250\n3月,north,170\n", encoding='utf-8')
(DATA / 'm2.csv').write_text("城市,销售额\n广州,150\n深圳,180\n", encoding='utf-8')
(DATA / 'm3.csv').write_text("A,B\n1,2\n3,4\n", encoding='utf-8')
# P0/P1 新增图表测试数据
(DATA / 'region.csv').write_text(
    "地区,销售额\n北京,1200\n上海,1500\n广东,900\n浙江,1100\n四川,800\n新疆,700\n", encoding='utf-8')
(DATA / 'routes.csv').write_text(
    "来源,去向,金额\n北京,上海,500\n上海,广东,300\n广东,四川,200\n北京,广东,400\n", encoding='utf-8')
# N8/N9: 自备 GeoJSON（--geo-path）测试数据——三区域自定义地图
(DATA / 'countries.csv').write_text(
    "国家,销售额\n美国,100\n日本,200\n德国,150\n", encoding='utf-8')
_custom_feats = []
for _i, _n in enumerate(['美国', '日本', '德国']):
    _x = _i * 3
    _custom_feats.append({
        'type': 'Feature', 'properties': {'name': _n},
        'geometry': {'type': 'Polygon', 'coordinates': [[[_x, 0], [_x + 2, 0], [_x + 2, 2], [_x, 2], [_x, 0]]]},
    })
(DATA / 'world_custom.json').write_text(
    json.dumps({'type': 'FeatureCollection', 'features': _custom_feats}, ensure_ascii=False), encoding='utf-8')
# N10: 内置世界地图（英文国名）测试数据
(DATA / 'world_gdp.csv').write_text(
    "国家,GDP\nChina,17.7\nUnited States,25.5\nJapan,4.2\nGermany,4.1\n", encoding='utf-8')
(DATA / 'calendar.csv').write_text(
    "日期,活跃\n2024-01-01,120\n2024-01-02,150\n2024-01-03,90\n2024-01-05,200\n2024-01-06,160\n", encoding='utf-8')
(DATA / 'river.csv').write_text(
    "日期,产品A,产品B\n2024-01-01,100,80\n2024-01-02,120,90\n2024-01-03,110,95\n2024-01-04,130,85\n", encoding='utf-8')
(DATA / 'liquid_over100.csv').write_text(
    "完成率\n72\n85\n93\n88\n96\n104\n", encoding='utf-8')
(DATA / 'ffill.csv').write_text(
    "部门,经理,工资\n技术部,张三,12000\n,,11500\n市场部,李四,10000\n,,9800\n", encoding='utf-8')
# 合计行（末行「合计」）样本：极值统计不得被合计行污染
(DATA / 'total.csv').write_text(
    "月份,销量\n1月,10\n2月,20\n3月,30\n4月,40\n5月,50\n6月,60\n合计,210\n", encoding='utf-8')
# 一次调用同时命中多类 advisory：合计行 + 数值列部分降级 + 默认 annotation
(DATA / 'multi_adv.csv').write_text(
    "月份,销量\n1月,10\n2月,20\n3月,-\n合计,30\n", encoding='utf-8')
# GBK 编码
(DATA / 'gbk.csv').write_bytes("城市,销售额\n北京,1200\n上海,1500\n".encode('gbk'))
# Excel（openpyxl 可用时）
HAS_XLSX = False
try:
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active; ws.title = '数据'
    ws.append(['城市', '销售额', '利润'])
    for r in [('北京', 1200, 300), ('上海', 1500, 400), ('广州', 900, 180)]: ws.append(list(r))
    ws2 = wb.create_sheet('脏表')
    ws2.append(['学生信息表（导出）'])
    ws2.append(['编号', '姓名', '数学', '语文'])
    for r in [('001', '张三', 85, 78), ('002', '李四', 92, 88)]: ws2.append(list(r))
    wb.save(DATA / 'book.xlsx')
    HAS_XLSX = True
except ImportError:
    print("!! openpyxl 不可用，Excel 用例跳过")

# ══════════════════ U: 校验层单元测试 ══════════════════
print("\n─── U1: 逃逸 PoC（黑名单层）───")
POCS = {
    'pd.__builtins__ 直达': "result = pd.__builtins__",
    '__getattribute__ 取 eval': "result = pd.__getattribute__('eval')",
    '__getattr__ 变体': "result = pd.__getattr__('open')",
    '__loader__ 导入机': "x = np.__loader__; result = df",
    '__spec__': "x = pd.__spec__; result = df",
    '__self__': "x = (df.sum).__self__; result = df",
    '__func__': "x = (df.sum).__func__; result = df",
    '__reduce__ 反序列化': "x = df.__reduce__; result = df",
    '旧黑名单项仍拦截(eval)': "result = eval('1')",
    '旧黑名单项仍拦截(import)': "import os",
    '旧黑名单项仍拦截(open)': f"result = open({str(ROOT / 'sc_poctest')!r})",
}
df_u = pd.DataFrame({'类别': ['A', 'B', 'A'], '数值': [1, 2, 3]})
for name, code in POCS.items():
    v = validate_code_blacklist(code)
    rec(f"U1-黑名单拦截: {name}", bool(v), f"未被拦截: {code!r}")

print("\n─── U2: 逃逸 PoC（transform() 全路径）───")
for name, code in POCS.items():
    try:
        DataTransformer().transform(df_u, code)
        rec(f"U2-transform拒绝: {name}", False, "未被拒绝，代码被执行")
    except SmartChartsError as e:
        rec(f"U2-transform拒绝: {name}", e.code == ErrorCode.TRANSFORM_EXEC_ERROR,
            f"错误码不符: {e.code}")

print("\n─── U3: 黄金模式零误报（黑名单 + AST）───")
GOLDEN = {
    '频次聚合': "result = df['类别'].fillna('未标注').value_counts().rename_axis('name').reset_index(name='value')",
    '分组聚合': "result = df.groupby('类别')['数值'].sum().rename_axis('name').reset_index(name='value')",
    '透视': "result = df.pivot_table(index='类别', columns='类别', values='数值', aggfunc='sum').reset_index()",
    'melt': "result = df.melt(id_vars=['类别'], var_name='name', value_name='value')",
    'rename': "result = df.rename(columns={'类别': 'name', '数值': 'value'})",
    'ffill': "result = df.ffill()",
    'waterfall-diff': "tmp = df.copy(); tmp['d'] = tmp['数值'].diff().fillna(tmp['数值'].iloc[0]); result = tmp[['类别', 'd']]",
    'np.select': "result = df.assign(等级=np.select([df['数值'] > 2, df['数值'] > 1], ['高', '中'], default='低'))",
    '布尔向量位运算': "result = df[(df['数值'] > 1) & (df['类别'] == 'A')]",
    '推导式+lambda': "result = df.assign(k=[x * 2 for x in df['数值']]).assign(f=lambda t: t['数值'].map(lambda v: v + 1))",
}
for name, code in GOLDEN.items():
    v = validate_code_blacklist(code) + validate_code_ast(code)
    rec(f"U3-黄金零误报: {name}", not v, f"误报: {v}")

print("\n─── U4: transform() 正常执行返回 DataFrame ───")
for name, code in GOLDEN.items():
    try:
        r = DataTransformer().transform(df_u, code)
        rec(f"U4-transform执行: {name}", isinstance(r, pd.DataFrame) and not r.empty,
            f"返回异常: {type(r)}")
    except Exception as e:
        rec(f"U4-transform执行: {name}", False, f"异常: {e}")

print("\n─── U5: transform 错误码契约 ───")
ERR_CASES = {
    '无 result 变量(3002)': ("x = 1", ErrorCode.TRANSFORM_NO_RESULT),
    'result 非 DataFrame(3003)': ("result = 42", ErrorCode.TRANSFORM_INVALID_RESULT),
    'result 为空(3004)': ("result = df.iloc[0:0]", ErrorCode.TRANSFORM_EMPTY_RESULT),
    'AST违规-类定义(3001)': ("class Foo:\n    pass", ErrorCode.TRANSFORM_EXEC_ERROR),
    'AST违规-try(3001)': ("try:\n    x = 1\nexcept:\n    pass", ErrorCode.TRANSFORM_EXEC_ERROR),
    '语法错误(3001)': ("def broken(", ErrorCode.TRANSFORM_EXEC_ERROR),
}
for name, (code, expect) in ERR_CASES.items():
    try:
        DataTransformer().transform(df_u, code)
        rec(f"U5-错误码: {name}", False, "未抛错")
    except SmartChartsError as e:
        rec(f"U5-错误码: {name}", e.code == expect, f"期望 {expect.name} 实得 {e.code.name}")

print("\n─── U6: 超时机制（while True，10s）───")
try:
    DataTransformer().transform(df_u, "while True:\n    x = 1")
    rec("U6-超时拦截", False, "未超时")
except SmartChartsError as e:
    rec("U6-超时拦截", e.code == ErrorCode.TRANSFORM_EXEC_ERROR and '超时' in e.message,
        f"{e.code.name}: {e.message}")

# ══════════════════ D: 数据解析层 ══════════════════
print("\n─── D1: 各格式解析 ───")
PARSE_CASES = {
    'CSV': 'cities.csv', 'TSV': 'students.tsv', 'TXT(分号)': 'scores.txt',
    'JSON(嵌套1层)': 'nested.json', 'GBK编码': 'gbk.csv',
}
for name, f in PARSE_CASES.items():
    try:
        df = DataParser().parse_file(DATA / f)
        rec(f"D1-解析: {name}", not df.empty, "空 DataFrame")
    except Exception as e:
        rec(f"D1-解析: {name}", False, str(e)[:120])

try:
    df = DataParser().parse_file(DATA / 'nested.json')
    rec("D1-JSON嵌套列名规范化", '详情_区域' in df.columns, f"列: {list(df.columns)}")
except Exception as e:
    rec("D1-JSON嵌套列名规范化", False, str(e)[:120])

df_sp = DataParser().parse_file(DATA / 'special.csv')
rec("D1-特殊字符列规范化(销售额(元)→销售额_元)", '销售额_元' in df_sp.columns, f"列: {list(df_sp.columns)}")
rec("D1-特殊字符列规范化(A/B→a_b)", 'a_b' in df_sp.columns, f"列: {list(df_sp.columns)}")

try:
    df_m = DataParser().parse_file(DATA / 'messy.csv', skiprows=2)
    rec("D1-skiprows脏表头", list(df_m.columns) == ['城市', '销售额'] and len(df_m) == 3,
        f"列: {list(df_m.columns)}, 行数: {len(df_m)}")
except Exception as e:
    rec("D1-skiprows脏表头", False, str(e)[:120])

if HAS_XLSX:
    try:
        df_s1 = DataParser().parse_file(DATA / 'book.xlsx', sheet_name='数据')
        rec("D1-Excel按名称选sheet", len(df_s1) == 3, f"行数: {len(df_s1)}")
    except Exception as e:
        rec("D1-Excel按名称选sheet", False, str(e)[:120])
    try:
        df_s2 = DataParser().parse_file(DATA / 'book.xlsx', sheet_name='脏表', header_row=1)
        rec("D1-Excel脏表header-row", list(df_s2.columns) == ['编号', '姓名', '数学', '语文'],
            f"列: {list(df_s2.columns)}")
    except Exception as e:
        rec("D1-Excel脏表header-row", False, str(e)[:120])
    try:
        DataParser().parse_file(DATA / 'book.xlsx', sheet_name='不存在的表')
        rec("D1-Excel错误sheet结构化报错", False, "未报错")
    except SmartChartsError as e:
        rec("D1-Excel错误sheet结构化报错", e.code == ErrorCode.DATA_PARSE_ERROR, f"{e.code.name}")

rc, so, se = run_dp([DATA / 'm1.csv', DATA / 'm2.csv', '--merge', '--summary'])
rec("D2-多文件纵向合并", rc == 0 and 'source_file' in so, f"rc={rc}, out={so[:150]}")
rc, so, se = run_dp([DATA / 'm1.csv', DATA / 'm3.csv', '--merge', '--summary'])
rec("D2-无重叠合并报错", rc != 0 and 'DATA_MERGE_ERROR' in (so + se), f"rc={rc}")

# ══════════════════ C: 32 种图表端到端 ══════════════════
print("\n─── C: 32 种图表（成功 + 契约键 + HTML 落盘）───")
CHARTS = [
    ('line', 'trend.csv', ['--x-axis', '月份', '--y-axis', '销售额', '利润']),
    ('bar', 'cities.csv', ['--x-axis', '城市', '--y-axis', '销售额']),
    ('area', 'trend.csv', ['--x-axis', '月份', '--y-axis', '销售额']),
    ('pie', 'freq.csv', ['--x-axis', 'name', '--y-axis', 'value',
     '--transform-code', "result = df['类别'].fillna('未标注').value_counts().rename_axis('name').reset_index(name='value')"]),
    ('scatter', 'students.csv', ['--x-axis', '数学', '--y-axis', '语文', '--label-col', '姓名']),
    ('radar', 'radar.csv', ['--x-axis', '指标', '--y-axis', '产品a', '产品b']),
    ('heatmap', 'heat.csv', ['--x-axis', '星期', '--y-axis', '早高峰', '午高峰', '晚高峰']),
    ('treemap', 'words.csv', ['--x-axis', '关键词', '--y-axis', '频次']),
    ('graph', 'graph.csv', ['--x-axis', 'source', '--y-axis', 'target', 'value']),
    ('boxplot', 'students.csv', ['--y-axis', '数学', '语文', '英语']),
    ('waterfall', 'waterfall.csv', ['--x-axis', 'month', '--y-axis', 'profit']),
    ('gauge', 'gauge.csv', ['--y-axis', '完成率']),
    ('sankey', 'relation.csv',
     ['--x-axis', '来源', '--y-axis', '去向', '金额']),
    ('funnel', 'funnel.csv', ['--x-axis', '阶段', '--y-axis', '人数']),
    ('sunburst', 'words.csv', ['--x-axis', '关键词', '--y-axis', '频次']),
    ('wordcloud', 'words.csv', ['--x-axis', '关键词', '--y-axis', '频次']),
    ('histogram', 'students.csv', ['--x-axis', '数学']),
    ('stacked_bar', 'cities.csv', ['--x-axis', '城市', '--y-axis', '销售额', '利润']),
    ('bubble', 'cities.csv', ['--x-axis', '销售额', '--y-axis', '利润', '人口万']),
    ('pareto', 'pareto.csv', ['--x-axis', '类别', '--y-axis', '数量']),
    ('combo', 'cities.csv', ['--x-axis', '城市', '--y-axis', '销售额', '利润']),
    ('venn', 'venn.csv', ['--x-axis', 'name', '--y-axis', 'value']),
    ('mindmap', 'org.csv', ['--x-axis', 'parent', '--y-axis', 'child']),
    ('orgchart', 'org.csv', ['--x-axis', 'parent', '--y-axis', 'child']),
    ('liquid', 'gauge.csv', ['--y-axis', '完成率']),
    ('spreadsheet', 'students.csv', []),
    # ── P0 新增 ──
    ('map', 'region.csv', ['--x-axis', '地区', '--y-axis', '销售额']),
    ('lines', 'routes.csv', ['--x-axis', '来源', '--y-axis', '去向', '金额']),
    ('effect_scatter', 'students.csv', ['--x-axis', '数学', '--y-axis', '语文', '--label-col', '姓名']),
    # ── P1 新增 ──
    ('calendar', 'calendar.csv', ['--x-axis', '日期', '--y-axis', '活跃']),
    ('pictorial_bar', 'cities.csv', ['--x-axis', '城市', '--y-axis', '销售额']),
    ('theme_river', 'river.csv', ['--x-axis', '日期', '--y-axis', '产品a', '产品b']),
]
CONTRACT_KEYS = {'success', 'html_path', 'chart_type', 'title', 'data_rows', 'data_preview', 'plot_stats'}
# 32 个图表类型互不依赖，一次性并发跑完再逐条断言（顺序与 CHARTS 一致）
for (ctype, fname, _extra), (rc, out, se) in zip(
        CHARTS,
        run_many([[DATA / f, t, '--title', f'{t}回归测试', *e] for t, f, e in CHARTS])):
    name = f"C-{ctype:12s} ({fname})"
    if rc != 0 or not out or not out.get('chart', {}).get('success'):
        rec(name, False, f"rc={rc} stdout={(json.dumps(out, ensure_ascii=False)[:200] if out else 'None')} stderr={se[:200]}")
        continue
    c = out['chart']
    missing = CONTRACT_KEYS - set(c.keys())
    html_ok = c['html_path'] and Path(c['html_path']).exists() and Path(c['html_path']).stat().st_size > 1024
    rec(name, not missing and html_ok,
        f"缺契约键: {missing or '无'}, html: {c['html_path']}")

# ══════════════════ T: transform 黄金模式端到端 ══════════════════
print("\n─── T: transform 黄金模式（CLI 端到端）───")
# 黄金模式：每条都是「transform 预处理 → 出图成功」，标题取自用例名前缀
T_CASES = {
    'T1-groupby聚合→bar': [DATA / 'm1.csv', 'bar',
        '--transform-code', "result = df.groupby('城市')['销售额'].sum().rename_axis('name').reset_index(name='value')",
        '--x-axis', 'name', '--y-axis', 'value'],
    'T2-pivot_table多系列→line': [DATA / 'sales_long.csv', 'line',
        '--transform-code', "result = df.pivot_table(index='month', columns='region', values='revenue', aggfunc='sum').reset_index()",
        '--x-axis', 'month', '--y-axis', 'east', 'north'],
    'T3-ffill多语句→pie': [DATA / 'ffill.csv', 'pie',
        '--transform-code', "tmp = df.ffill(); result = tmp['部门'].value_counts().rename_axis('name').reset_index(name='value')",
        '--x-axis', 'name', '--y-axis', 'value'],
    'T4-waterfall-diff模式': [DATA / 'waterfall.csv', 'waterfall',
        '--transform-code', "tmp = df.copy(); tmp['delta'] = tmp['profit'].diff().fillna(tmp['profit'].iloc[0]); result = tmp[['month', 'delta']]",
        '--x-axis', 'month', '--y-axis', 'delta'],
    'T5-np.select→bar': [DATA / 'students.csv', 'bar',
        '--transform-code', "result = df.assign(等级=np.select([df['数学'] > 90, df['数学'] > 60], ['优', '中'], default='及格边缘'))",
        '--x-axis', '等级', '--y-axis', '数学'],
    'T6-rename→graph显式指定': [DATA / 'relation.csv', 'graph',
        '--transform-code', "result = df.rename(columns={'来源': 'source', '去向': 'target', '金额': 'value'})",
        '--x-axis', 'source', '--y-axis', 'target', 'value'],
    'T7-特殊字符列规范化引用': [DATA / 'special.csv', 'bar', '--x-axis', '销售额_元', '--y-axis', 'a_b'],
    'T8-skiprows+transform': [DATA / 'messy.csv', 'bar', '--skiprows', '2',
        '--transform-code', "result = df.assign(销售额=df['销售额'].map(lambda v: v * 2))",
        '--x-axis', '城市', '--y-axis', '销售额'],
}
for nm, (rc, out, se) in zip(T_CASES, run_many(
        [[*a, '--title', n.split('-')[0]] for n, a in T_CASES.items()])):
    rec(nm, rc == 0 and bool(out) and out.get('chart', {}).get('success') is True,
        f"rc={rc}, {json.dumps(out, ensure_ascii=False)[:200] if out else se[:200]}")

# CLI 层逃逸拦截（结构化错误 + suggestion）
rc, out, se = run_cli([DATA / 'm1.csv', 'bar', '--title', 'T9',
    '--transform-code', "result = pd.__builtins__ and df", '--x-axis', '城市', '--y-axis', '销售额'])
ok = rc == 1 and out and not out['chart']['success'] \
     and out['chart']['error']['code_name'] == 'TRANSFORM_EXEC_ERROR' \
     and '__builtins__' in out['chart']['error']['details'].get('violations', []) \
     and 'suggestion' in out['chart']['error']['details']
rec("T9-CLI逃逸拦截(__builtins__)", ok, f"rc={rc}, {json.dumps(out, ensure_ascii=False)[:300] if out else se[:300]}")

# ══════════════════ M: 多图模式 ══════════════════
print("\n─── M: 多图模式 ───")
# 三张图共用 cities.csv：bar/combo 按城市、scatter 用两列数值
charts_cfg = [
    {"type": "bar", "title": "M柱状", "x_axis": "城市", "y_axis": ["销售额"]},
    {"type": "combo", "title": "M组合", "x_axis": "城市", "y_axis": ["销售额", "利润"]},
    {"type": "scatter", "title": "M散点", "x_axis": "销售额", "y_axis": ["利润"]},
]
cfg_path = ROOT / 'charts.json'
cfg_path.write_text(json.dumps(charts_cfg, ensure_ascii=False), encoding='utf-8')
# M1 / M6 共用这份配置，并发跑
(rc, out, se), (rcDR, outDR, seDR) = run_many([
    [DATA / 'cities.csv', '--charts-file', cfg_path],
    [DATA / 'cities.csv', '--charts-file', cfg_path, '--dry-run'],
])
ok = rc == 0 and out and out.get('summary', {}).get('total') == 3 and out['summary']['succeeded'] == 3 \
     and all(c.get('success') and Path(c['html_path']).exists() for c in out['charts'])
rec("M1-charts-file多图(3张全成功)", ok,
    f"rc={rc}, {json.dumps(out, ensure_ascii=False)[:300] if out else se[:300]}")

# 全局 transform + 单图级 transform
rc, out, se = run_cli([DATA / 'cities.csv', '--charts-file', cfg_path,
    '--transform-code', "result = df.assign(销售额=df['销售额'].map(lambda v: v / 10))"])
ok = rc == 0 and out and out['summary']['succeeded'] == 3
rec("M2-全局transform多图", ok, f"rc={rc}, {json.dumps(out, ensure_ascii=False)[:200] if out else se[:200]}")

# 部分失败（exit 0 + summary 正确）
cfg_part = [
    {"type": "bar", "title": "好图", "x_axis": "城市", "y_axis": ["销售额"]},
    {"type": "bar", "title": "坏图", "x_axis": "不存在的列", "y_axis": ["销售额"]},
]
(ROOT / 'part.json').write_text(json.dumps(cfg_part, ensure_ascii=False), encoding='utf-8')
rc, out, se = run_cli([DATA / 'cities.csv', '--charts-file', ROOT / 'part.json'])
ok = rc == 0 and out and out['summary'] == {'total': 2, 'succeeded': 1, 'failed': 1} \
     and out['charts'][0]['success'] and not out['charts'][1]['success'] \
     and 'suggestion' in out['charts'][1]['error']['details']
rec("M3-部分失败(exit 0 + per-chart错误)", ok, f"rc={rc}, {json.dumps(out, ensure_ascii=False)[:300] if out else se[:300]}")

# 内联 --charts（合法/非法各一）
rc, out, se = run_cli([DATA / 'cities.csv', '--charts', '[{"type":"bar","x_axis":"城市","y_axis":["销售额"]}]'])
rec("M4-内联--charts", rc == 0 and out and out['summary']['succeeded'] == 1,
    f"rc={rc}, {json.dumps(out, ensure_ascii=False)[:200] if out else se[:200]}")

rc, out, se = run_cli([DATA / 'cities.csv', '--charts', '[{"x_axis":"城市"}]'])
rec("M5-非法charts(缺type)结构化报错", rc == 1 and 'CHART_CONFIG_ERROR' in se, f"rc={rc}, se={se[:150]}")

# 多图 dry-run（不落盘）
ok = rcDR == 0 and outDR and all(c['success'] and c.get('dry_run') and c['html_path'] is None
                                 for c in outDR['charts'])
rec("M6-多图dry-run(不落盘)", ok, f"rc={rcDR}, {json.dumps(outDR, ensure_ascii=False)[:250] if outDR else seDR[:250]}")

# ══════════════════ F: flags / 主题 / 语言 ══════════════════
print("\n─── F: flags / 主题 / 语言 / dry-run / annotation ───")
# 只要求「出图成功」的 flag 组合，一次性并发跑完
F_OK = {
    'F1-主题 default': [DATA / 'cities.csv', 'bar', '--title', '主题default',
                        '--x-axis', '城市', '--y-axis', '销售额', '--theme', 'default'],
    'F1-主题 classic': [DATA / 'cities.csv', 'bar', '--title', '主题classic',
                        '--x-axis', '城市', '--y-axis', '销售额', '--theme', 'classic'],
    'F1-主题 dark': [DATA / 'cities.csv', 'bar', '--title', '主题dark',
                     '--x-axis', '城市', '--y-axis', '销售额', '--theme', 'dark'],
    'F2-lang=en(英文数据)': [DATA / 'en.csv', 'bar', '--title', 'Revenue by City',
                            '--x-axis', 'city', '--y-axis', 'revenue', '--lang', 'en'],
    'F3-lang=zh(覆盖自动检测)': [DATA / 'en.csv', 'bar', '--title', '城市营收',
                                '--x-axis', 'city', '--y-axis', 'revenue', '--lang', 'zh'],
    'F7-y-scale(line)': [DATA / 'trend.csv', 'line', '--title', 'F7', '--y-scale',
                         '--x-axis', '月份', '--y-axis', '销售额'],
    'F8-label=all': [DATA / 'cities.csv', 'bar', '--title', 'F8-all', '--label', 'all',
                     '--x-axis', '城市', '--y-axis', '销售额'],
    'F8-label=key': [DATA / 'cities.csv', 'bar', '--title', 'F8-key', '--label', 'key',
                     '--x-axis', '城市', '--y-axis', '销售额'],
    'F9-scatter label-col+color-by(数值)': [DATA / 'students.csv', 'scatter', '--title', 'F9',
                                            '--x-axis', '数学', '--y-axis', '语文',
                                            '--label-col', '姓名', '--color-by', '英语'],
    'F10-scatter color-by(类别)': [DATA / 'cities.csv', 'scatter', '--title', 'F10',
                                   '--x-axis', '销售额', '--y-axis', '利润', '--color-by', '城市'],
    'F11-width/height': [DATA / 'cities.csv', 'bar', '--title', 'F11', '--x-axis', '城市',
                         '--y-axis', '销售额', '--width', '1200', '--height', '800'],
    # stdout 必须是单行可解析 JSON（run_cli 解析失败会返回 out=None → 断言自然失败）
    'F13-stdout纯JSON契约': [DATA / 'cities.csv', 'bar', '--title', 'F13',
                             '--x-axis', '城市', '--y-axis', '销售额'],
}
for nm, (rc, out, se) in zip(F_OK, run_many(list(F_OK.values()))):
    rec(nm, rc == 0 and bool(out) and out.get('chart', {}).get('success') is True and not se,
        f"rc={rc}, {json.dumps(out, ensure_ascii=False)[:200] if out else se[:200]}")

# 下面几项要读回 HTML 内容比对，参数各不相同，一并并发后再断言
ANNOT = '回归测试注解：上海以 1500 领先四城。'
SUB = '2026年Q1 · 数据来源：测试套件'
(rc4, out4, se4), (rc5, out5, se5), (rcs, outs, ses), (rcn, outn, sen), (rc12, out12, se12) = run_many([
    [DATA / 'cities.csv', 'bar', '--title', 'F4', '--dry-run', '--x-axis', '城市', '--y-axis', '销售额'],
    [DATA / 'cities.csv', 'bar', '--title', 'F5注解', '--x-axis', '城市', '--y-axis', '销售额',
     '--annotation', ANNOT, '--subtitle', SUB],
    [DATA / 'cities.csv', 'bar', '--title', 'F6s', '--sort', 'value', '--x-axis', '城市', '--y-axis', '销售额'],
    [DATA / 'cities.csv', 'bar', '--title', 'F6n', '--sort', 'none', '--x-axis', '城市', '--y-axis', '销售额'],
    [DATA / 'cities.csv', 'bar', '--title', 'F12', '--x-axis', '城市', '--y-axis', '销售额'],
])

c = out4.get('chart', {}) if out4 else {}
rec("F4-dry-run(html_path=null+plot_stats)",
    rc4 == 0 and c.get('dry_run') is True and c.get('html_path') is None and 'plot_stats' in c,
    json.dumps(out4, ensure_ascii=False)[:200] if out4 else se4[:200])

ok = rc5 == 0 and out5 and out5['chart']['success']
if ok:
    html = Path(out5['chart']['html_path']).read_text(encoding='utf-8')
    ok = ANNOT in html and SUB in html
rec("F5-annotation+subtitle注入HTML", ok, f"rc={rc5}")

# sort 在渲染层生效（data_preview 是渲染前数据，原序属预期）：
# 断言 xAxis data 数组首元素——value 降序为「上海」，none 原序为「北京」，且两份 HTML 不同
ok = rcs == 0 and outs and rcn == 0 and outn
if ok:
    html_v = Path(outs['chart']['html_path']).read_text(encoding='utf-8')
    html_n = Path(outn['chart']['html_path']).read_text(encoding='utf-8')
    m_v = re.search(r'"data":\s*\[\s*"[^"]+"', html_v)
    m_n = re.search(r'"data":\s*\[\s*"[^"]+"', html_n)
    ok = (m_v is not None and m_v.group(0).rstrip().endswith('"上海"')
          and m_n is not None and m_n.group(0).rstrip().endswith('"北京"')
          and html_v != html_n)
rec("F6-sort=value渲染层降序", ok, f"rc={rcs}/{rcn}")

# 离线性：ECharts 内联、HTML 不引用任何外部 CDN
ok = rc12 == 0 and out12 and out12['chart']['success']
if ok:
    html = Path(out12['chart']['html_path']).read_text(encoding='utf-8')
    ok = 'echarts' in html.lower() and 'src="http' not in html and 'href="http' not in html
rec("F12-离线HTML(echarts内联无CDN)", ok, f"rc={rc12}, size={len(html) if ok else 'N/A'}")

# ══════════════════ E: 错误路径 ══════════════════
print("\n─── E: 错误路径（结构化 JSON + suggestion）───")
# 返回 chart.error.code_name 的两类
E_CHART_ERR = {
    'E1-不支持的图表类型(4002)': ([DATA / 'cities.csv', 'bar3d', '--title', 'E1',
                                  '--x-axis', '城市', '--y-axis', '销售额'], 'CHART_TYPE_UNSUPPORTED'),
    'E2-轴字段缺失(4003)': ([DATA / 'cities.csv', 'bar', '--title', 'E2',
                            '--x-axis', '不存在的列', '--y-axis', '销售额'], 'CHART_CONFIG_ERROR'),
}
for nm, (args, code) in E_CHART_ERR.items():
    rc, out, se = run_cli(args)
    ok = (rc == 1 and out and not out['chart']['success']
          and out['chart']['error']['code_name'] == code)
    rec(nm, ok, f"rc={rc}, {json.dumps(out, ensure_ascii=False)[:200] if out else se[:200]}")

# 错误码只落在 stderr 上的（解析期失败，尚未进入图表上下文）
(DATA / 'scores.xyz').write_text('姓名,数学\n张三,85\n', encoding='utf-8')
E_STDERR = {
    'E3-文件不存在(1001,stderr)': ([ROOT / '不存在.csv', 'bar'], ['FILE_NOT_FOUND']),
    'E4-不支持扩展名(1003)': ([DATA / 'scores.xyz', 'bar'], ['FILE_FORMAT_INVALID']),
    'E5-缺图表类型(4003)': ([DATA / 'cities.csv'], ['CHART_CONFIG_ERROR']),
    'E6-未知flag(argparse→结构化JSON)': ([DATA / 'cities.csv', 'bar', '--nope'],
                                         ['CHART_CONFIG_ERROR', 'suggestion']),
    'E7-charts-file缺失(1001)': ([DATA / 'cities.csv', '--charts-file', str(ROOT / '不存在.json')],
                                 ['FILE_NOT_FOUND']),
}
for (nm, (_, marks)), (rc, out, se) in zip(E_STDERR.items(), run_many([a for a, _ in E_STDERR.values()])):
    rec(nm, rc == 1 and all(m in se for m in marks), f"rc={rc}, se={se[:150]}")

# E8: 5 个逃逸 PoC 经 CLI（覆盖 dunder 新增项）
E8_POCS = [('__builtins__', "result = pd.__builtins__"),
           ('__getattribute__', "x = pd.__getattribute__; result = df"),
           ('__loader__', "x = np.__loader__; result = df"),
           ('__reduce__', "x = df.__reduce__; result = df"),
           ('__spec__', "x = pd.__spec__; result = df")]
for (kw, _), (rc, out, se) in zip(E8_POCS, run_many(
        [[DATA / 'm1.csv', 'bar', '--title', f'E8-{kw}', '--transform-code', code,
          '--x-axis', '城市', '--y-axis', '销售额'] for kw, code in E8_POCS])):
    ok = (rc == 1 and out and not out['chart']['success']
          and out['chart']['error']['code_name'] == 'TRANSFORM_EXEC_ERROR'
          and kw in out['chart']['error']['details'].get('violations', []))
    rec(f"E8-CLI逃逸拦截: {kw}", ok, f"rc={rc}")

# E9: P1-1 嵌套模块路径逃逸（此前 133 项全绿但真实可落盘/可出网）
# 探针路径放在临时目录：硬编码 /tmp 在非 POSIX 系统上不存在，会让用例假失败
PROBE_NPY = str(ROOT / 'sc_probe_e9.npy')
PROBE_TXT = str(ROOT / 'sc_probe_e9.txt')
for kw, code in [('open_memmap', f"x = np.lib.format.open_memmap('{PROBE_NPY}', mode='w+', dtype='float64', shape=(2,)); result = df"),
                 ('get_handle', f"h = pd.io.common.get_handle('{PROBE_TXT}', mode='w'); result = df"),
                 ('pd.io(网络)', "h = pd.io.common.get_handle('http://127.0.0.1:9/x.csv', mode='r'); result = df")]:
    v = validate_code_blacklist(code) + validate_code_ast(code)
    rec(f"E9-嵌套路径逃逸拦截: {kw}", bool(v), f"未被拦截: {code[:60]}")
    try:
        DataTransformer().transform(df_u, code)
        rec(f"E9-transform拒绝: {kw}", False, "代码被执行")
    except SmartChartsError as e:
        rec(f"E9-transform拒绝: {kw}", e.code == ErrorCode.TRANSFORM_EXEC_ERROR, f"{e.code.name}")
# 落盘取证：确认探针文件确实没有被创建
rec("E9-探针文件未落盘",
    not os.path.exists(PROBE_NPY) and not os.path.exists(PROBE_TXT),
    "逃逸代码真实创建了文件")

# ══════════════════ X: P0/P1/P2 修复项回归 ══════════════════
print("\n─── X: 问题清单修复项（P0/P1/P2）───")

# 本段要跑的 CLI 用例集中在段首并发，下面各修复项按需取结果（避免串行空等）
X_ARGS = {
    'P0-3': [DATA / 'total.csv', 'bar', '--title', 'X-P0-3', '--x-axis', '月份', '--y-axis', '销量'],
    'P1-2': [DATA / 'freq.csv', 'bar', '--title', 'X-P1-2', '--x-axis', 'name', '--y-axis', 'value',
             '--transform-code',
             "result = df['类别'].fillna('未标注').value_counts().rename_axis('name').reset_index(name='value')"],
    'P1-5a': [DATA / 'cities.csv', 'bar', '--title', 'X-P1-5', '--x-axis', '城市', '--y-axis', '销售额'],
    'P1-5b': [DATA / 'cities.csv', 'bar', '--title', 'X-P1-5b', '--x-axis', '城市', '--y-axis', '销售额',
              '--annotation', ANNOT],
    'P1-7a': [DATA / 'gauge.csv', 'gauge', '--title', 'X-P1-7', '--y-axis', '完成率'],
    'P1-7b': [DATA / 'gauge.csv', 'gauge', '--title', 'X-P1-7b', '--y-axis', '完成率', '--target', '100'],
    'P2-13': [DATA / 'multi_adv.csv', 'bar', '--title', 'X-P2-13', '--x-axis', '月份', '--y-axis', '销量'],
}
X = dict(zip(X_ARGS, run_many(list(X_ARGS.values()))))

# ── P0-1: frontmatter 必须只含平台允许键 ──
_fm = re.match(r'^---\n(.*?)\n---', (BASE / 'SKILL.md').read_text(encoding='utf-8'), re.DOTALL)
try:
    import yaml as _yaml
    _keys = set(_yaml.safe_load(_fm.group(1)).keys())
except ImportError:
    _keys = set(re.findall(r'^([a-z-]+):', _fm.group(1), re.M))
_ALLOWED = {'allowed-tools', 'compatibility', 'description', 'description_zh', 'description_en', 'display_name', 'display_name_en', 'license', 'metadata', 'name', 'version'}
rec("P0-1-frontmatter无非法键", not (_keys - _ALLOWED), f"非法键: {_keys - _ALLOWED}")
rec("P0-1-描述含TRIGGER边界段",
    'TRIGGER' in (BASE / 'SKILL.md').read_text(encoding='utf-8'),
    "description 缺 TRIGGER/DO-NOT-TRIGGER")

# ── P0-2: exec 单一命名空间（中间变量 + lambda/生成器/嵌套 def）──
# df_u 的列为 类别 / 数值，引用必须用真实列名
for _n, _code in [('lambda引用中间变量', "k = 2; result = df.assign(v2=lambda d: d['数值']*k)"),
                  ('生成器引用中间变量', "thr = 2; result = df.assign(f=list(v > thr for v in df['数值']))"),
                  ('apply引用标量', "s = 10; result = df[['数值']].apply(lambda c: c*s)"),
                  ('嵌套def引用中间变量', "m = 3\ndef f(x):\n    return x*m\nresult = df.assign(v3=df['数值'].map(f))")]:
    try:
        _r = DataTransformer().transform(df_u, _code)
        rec(f"P0-2-单一命名空间: {_n}", isinstance(_r, pd.DataFrame) and not _r.empty, f"{type(_r)}")
    except Exception as _e:
        rec(f"P0-2-单一命名空间: {_n}", False, f"{type(_e).__name__}: {_e}")

# ── P0-3（已改语义）: 合计行不再自动排除 + summary 补 tail ──
# 「哪一行是合计行」是语义判断，交 agent 从 tail 识别后用 --drop-rows/transform 处理。
_p = DataParser()
_df_t = _p.parse_file(DATA / 'total.csv')
rec("P0-3-合计行不再自动排除", len(_df_t) == 7 and int(_df_t['销量'].sum()) == 420,
    f"rows={len(_df_t)}, sum={_df_t['销量'].sum()}")
_sum_t = _p.get_data_summary(_df_t)
rec("P0-3-summary补tail供agent识别合计行", 'tail' in _sum_t
    and any('合计' in str(r) for r in _sum_t['tail']),
    f"tail={_sum_t.get('tail')}")

# ── P0-4: 趋势按自然序 + 零基线不可计算 ──
_b = pd.DataFrame({'月份': ['1月', '2月', '3月', '4月'], '销量': [100, 120, 140, 160]})
_t_up = compute_plot_stats(_b, 'line', '月份', ['销量'])['series'][0]['trend']
_t_rev = compute_plot_stats(_b.iloc[::-1].reset_index(drop=True), 'line', '月份', ['销量'])['series'][0]['trend']
_t_shf = compute_plot_stats(_b.iloc[[2, 0, 3, 1]].reset_index(drop=True), 'line', '月份', ['销量'])['series'][0]['trend']
rec("P0-4-三种行序结论一致",
    _t_up['delta_pct'] == _t_rev['delta_pct'] == _t_shf['delta_pct'] == 60.0,
    f"{_t_up} / {_t_rev} / {_t_shf}")
_z = compute_plot_stats(pd.DataFrame({'m': ['a', 'b'], 'v': [0, 5000]}), 'line', 'm', ['v'])['series'][0]['trend']
rec("P0-4-零基线不报持平", _z['direction'] == 'undefined' and _z['delta_pct'] is None, f"{_z}")
_m = compute_plot_stats(pd.DataFrame({'m': ['1月', '2月', '10月', '12月'], 'v': [10, 20, 30, 40]}),
          'line', 'm', ['v'])['series'][0]['trend']
rec("P0-4-月份按时间序非字典序", _m['first'] == 10.0 and _m['last'] == 40.0, f"{_m}")

# ── P0-5: 列名撞名消歧 + UNKNOWN_ERROR 带 suggestion ──
for _cols in (['Sales Amount', 'sales-amount'], ['营收($)', '营收'], ['Score', 'score'], ['A/B', 'A B']):
    _dd = pd.DataFrame({c: [1, 2] for c in _cols})
    try:
        _o = DataParser()._clean(_dd.copy())
        rec(f"P0-5-撞名消歧: {_cols}", len(set(_o.columns)) == len(_o.columns)
            and all(hasattr(_o[c], 'dtype') for c in _o.columns), f"列: {list(_o.columns)}")
    except Exception as _e:
        rec(f"P0-5-撞名消歧: {_cols}", False, f"{type(_e).__name__}: {_e}")
# 真正跑一遍 UNKNOWN_ERROR 兜底分支：注入一个非 SmartChartsError 异常，
# 捕获 stderr 上的结构化 JSON，断言 details 里有 suggestion

def _run_injected_failure(entry, argv):
    """把 parse_file 换成必炸的实现，跑真实入口，返回解析后的错误 JSON。"""
    _orig = DataParser.parse_file
    def _boom(*a, **k):
        raise RuntimeError("injected-for-regression")
    DataParser.parse_file = _boom
    _buf = io.StringIO()
    try:
        with contextlib.redirect_stderr(_buf):
            try:
                entry(argv) if argv is not None else entry()
            except SystemExit:
                pass
    finally:
        DataParser.parse_file = _orig
    try:
        return json.loads(_buf.getvalue().strip().splitlines()[-1])
    except Exception:
        return {}

_err = _run_injected_failure(cli_mod.main, [str(DATA / 'cities.csv'), 'bar',
                                             '--x-axis', '城市', '--y-axis', '销售额'])
rec("P0-5-cli兜底UNKNOWN_ERROR带suggestion",
    _err.get('code_name') == 'UNKNOWN_ERROR' and 'suggestion' in _err.get('details', {}),
    f"{_err}")
_argv0 = sys.argv
sys.argv = ['data_parser.py', str(DATA / 'cities.csv'), '--summary']
try:
    _err2 = _run_injected_failure(dp_mod._run_cli, None)
finally:
    sys.argv = _argv0
rec("P0-5-data_parser兜底UNKNOWN_ERROR带suggestion",
    _err2.get('code_name') == 'UNKNOWN_ERROR' and 'suggestion' in _err2.get('details', {}),
    f"{_err2}")

# ── P0-6: f-string 放行 ──
_f = "result = df.rename(columns={c: f'{c}_score' for c in df.columns})"
rec("P0-6-f-string通过校验", not (validate_code_blacklist(_f) + validate_code_ast(_f)),
    f"{validate_code_blacklist(_f) + validate_code_ast(_f)}")
try:
    _r = DataTransformer().transform(df_u, _f)
    rec("P0-6-f-string可执行", list(_r.columns) == ['类别_score', '数值_score'], f"{list(_r.columns)}")
except Exception as _e:
    rec("P0-6-f-string可执行", False, str(_e))

# ── P1-2: 粒度对账三元组 ──
rc, out, se = X['P1-2']
_c = out['chart'] if out else {}
rec("P1-2-输出source_rows/plotted_rows/unique_entities",
    rc == 0 and {'source_rows', 'plotted_rows', 'unique_entities'} <= set(_c),
    f"keys={sorted(_c)}")
# freq.csv 共 12 个数据行，其中 1 行为空 —— 解析层 _clean 先丢空行，
# 故 source_rows=11；transform 聚合成 4 个类别，plotted_rows=unique_entities=4
rec("P1-2-对账三元组数值正确",
    _c.get('source_rows') == 11 and _c.get('plotted_rows') == 4 and _c.get('unique_entities') == 4,
    f"source={_c.get('source_rows')}, plotted={_c.get('plotted_rows')}, uniq={_c.get('unique_entities')}")
rec("P1-2-三元组可判定漏去重",
    _c.get('plotted_rows', 0) < _c.get('source_rows', 0)
    and sum(r['value'] for r in _c.get('data_preview', [])) == _c.get('source_rows')
    and _c.get('unique_entities') == _c.get('plotted_rows'),
    f"三元组无法支撑去重校验: {_c.get('source_rows')}/{_c.get('plotted_rows')}/{_c.get('unique_entities')}")

# ── P1-5: annotation_source ──
rc, out, se = X['P1-5a']
rec("P1-5-默认annotation标记default",
    rc == 0 and out['chart'].get('annotation_source') == 'default'
    and any('annotation' in a for a in out['chart'].get('advisories', [])),
    f"{out['chart'].get('annotation_source') if out else se[:150]}")
rc, out, se = X['P1-5b']
rec("P1-5-用户annotation标记user",
    rc == 0 and out['chart'].get('annotation_source') == 'user'
    and 'annotation_source' not in ' '.join(out['chart'].get('advisories', [])),
    f"{out['chart'].get('annotation_source') if out else se[:150]}")

# ── P1-7: gauge --target ──
rc, out, se = X['P1-7a']
_g = out['chart']['plot_stats']['extra'] if out else {}
rec("P1-7-无target时achievement为null",
    rc == 0 and _g.get('achievement') is None and 'achievement_note' in _g, f"{_g}")
rec("P1-7-无target时挂advisory",
    any('target' in a or '达成率' in a for a in out['chart'].get('advisories', [])),
    f"{out['chart'].get('advisories')}")
rc, out, se = X['P1-7b']
_g2 = out['chart']['plot_stats']['extra'] if out else {}
rec("P1-7-有target时achievement=mean/target",
    rc == 0 and _g2.get('target') == 100.0
    and abs(_g2.get('achievement', 0) - round(_g2['mean'] / 100, 4)) < 1e-9, f"{_g2}")

# ── P1-8: 依赖区间 + --doctor ──
_req = (BASE / 'requirements.txt').read_text(encoding='utf-8')
rec("P1-8-requirements改用兼容区间",
    'pandas>=' in _req and 'pandas==' not in _req and 'numpy>=' in _req,
    f"{_req[:80]}")
_proc = subprocess.run([sys.executable, str(CLI), '--doctor'], capture_output=True, text=True, timeout=60)
try:
    _doc = json.loads(_proc.stdout)
    rec("P1-8-doctor输出版本矩阵",
        _proc.returncode == 0 and 'dependencies' in _doc and 'assets' in _doc
        and len(_doc['dependencies']) == 4,
        f"rc={_proc.returncode}, out={_proc.stdout[:150]}")
except Exception as _e:
    rec("P1-8-doctor输出版本矩阵", False, f"{_e}: {_proc.stdout[:150]}{_proc.stderr[:150]}")

# ── P1-13: 文档硬约束要求显式 --output-dir ──
_skm = (BASE / 'SKILL.md').read_text(encoding='utf-8')
rec("P1-13-文档要求显式指定--output-dir",
    'MUST 显式传 `--output-dir`' in _skm, "SKILL.md 缺该硬约束")

# ── P2-2: 文档声明 skiprows 与 header-row 等价 ──
# 判据必须落在「同一句里同时提到两个 flag」——只查「同一」二字等于恒真，抓不到回归
_refm = (BASE / 'references' / 'REFERENCE.md').read_text(encoding='utf-8')
rec("P2-2-文档声明两个flag等价",
    any('skiprows' in ln and 'header-row' in ln for ln in _refm.splitlines()),
    "REFERENCE.md 未在同一处说明二者等价")

# ── P2-9（已改语义）: 身份列不再自动探测 ──
# label_col 不传则不猜——散点图身份列由 agent 显式 --label-col 指定。
# 验证 generate_chart 不传 --label-col 时不会自动把某列塞进身份列（assumptions 无 label 探测）。
rc_lbl, out_lbl, _ = run_cli([DATA / 'students.csv', 'scatter', '--title', 'P2-9',
                              '--x-axis', '数学', '--y-axis', '语文'])
_ass_lbl = (out_lbl or {}).get('chart', {}).get('assumptions', [])
rec("P2-9-身份列不自动探测", rc_lbl == 0 and not any('label' in a for a in _ass_lbl),
    f"assumptions={_ass_lbl}")

# ── P2-12: data_points 语义改为 x 去重数 ──
_long = pd.DataFrame({'month': [f'{i}月' for i in range(1, 13)] * 5,
                      'series': [s for _ in range(12) for s in 'abcde'], 'v': range(60)})
_dp = ChartGenerator(output_dir=str(OUT))._estimate_data_points(_long, 'bar', 'month', ['v'])
rec("P2-12-data_points取nunique", _dp == 12, f"实得 {_dp}（期望 12，旧实现为 60）")

# ── P2-13: advisories 多触发点 ──
# 一次调用可同时命中多类：数值列部分降级 / annotation 用默认模板
# （外加 gauge-liquid 缺 target、粒度未聚合）。这里只做端到端取证。
# 注意：合计行已不再自动排除（语义判断交 agent），故不再产生「合计」advisory。
rc, out, se = X['P2-13']
_advs = out['chart'].get('advisories', []) if out else []
rec("P2-13-单次调用命中多类advisory",
    rc == 0 and sum(1 for a in _advs if '数值' in a or '单元格' in a)
    + sum(1 for a in _advs if 'annotation' in a) >= 2,
    f"advisories={_advs}")

# ══════════════════ 命名：--x-name/--y-name/--series-name(s) ══════════════════
print("\n─── 命名: 轴名/系列名覆盖（HTML 片段取证）───")
# (用例名, CLI 参数, HTML 必须包含的片段, 必须已消失的硬编码/列名)
NAMING = [
    ('命名-1-line三者独立覆盖',
     [DATA / 'cities.csv', 'line', '--x-axis', '城市', '--y-axis', '销售额',
      '--x-name', '城市名', '--y-name', '营收', '--series-name', '月营收'],
     ['"text": "城市名"', '"text": "营收"', '"name": "月营收"'], []),
    ('命名-2-无参数回退列名',
     [DATA / 'cities.csv', 'line', '--x-axis', '城市', '--y-axis', '销售额'],
     ['"name": "销售额"'], []),
    ('命名-3-heatmap硬编码可覆盖',
     [DATA / 'heat.csv', 'heatmap', '--x-axis', '星期', '--y-axis', '早高峰', '午高峰',
      '--series-name', '客流热力'],
     ['"name": "客流热力"'], ['"name": "热力图"']),
    ('命名-4-gauge硬编码可覆盖',
     [DATA / 'gauge.csv', 'gauge', '--y-axis', '完成率', '--series-name', '季度达成'],
     ['"name": "季度达成"'], ['"name": "仪表盘"']),
    ('命名-5-waterfall跳过底座',
     [DATA / 'waterfall.csv', 'waterfall', '--x-axis', 'month', '--y-axis', 'profit',
      '--series-name', '净利润'],
     ['__waterfall_base__', '"name": "净利润"'], ['"name": "profit"']),
    ('命名-6-combo多系列',
     [DATA / 'cities.csv', 'combo', '--x-axis', '城市', '--y-axis', '销售额', '利润',
      '--series-names', '营收额', '利润额'],
     ['"name": "营收额"', '"name": "利润额"'], []),
    ('命名-7-boxplot双系列',
     [DATA / 'students.csv', 'boxplot', '--y-axis', '数学', '语文',
      '--series-names', '主科成绩', '离群点'],
     ['"name": "主科成绩"', '"name": "离群点"'], ['"name": "箱线图"', '"name": "异常值"']),
    ('命名-8-单数覆盖第一系列',
     [DATA / 'cities.csv', 'bar', '--x-axis', '城市', '--y-axis', '销售额',
      '--series-name', '总销售额'],
     ['"name": "总销售额"'], []),
    # 无轴名的 graphic 类图传 --x-name 不应崩（只要求出图成功，故 must 为空）
    ('命名-9-无轴名图传x-name不崩',
     [DATA / 'heat.csv', 'heatmap', '--x-axis', '星期', '--y-axis', '早高峰', '--x-name', '周期'],
     [], []),
    ('命名-11-liquid系列名可覆盖',
     [DATA / 'gauge.csv', 'liquid', '--y-axis', '完成率', '--series-name', '季度达成'],
     ['"name": "季度达成"', 'chartOption.series[0].name'], ['"name": "水波图"']),
    # max>100 时渲染百分比 = mean/target（与 achievement 同源，不再用 gauge_scale(max) 当分母）
    ('命名-12-liquid超100按target',
     [DATA / 'liquid_over100.csv', 'liquid', '--y-axis', '完成率', '--target', '100'],
     ['0.8967'], ['0.8211']),
    # 无 target 时回落到 gauge_scale（max≤100 → 100，均值/100 不变）
    ('命名-13-liquid无target回落',
     [DATA / 'gauge.csv', 'liquid', '--y-axis', '完成率'],
     ['0.789'], []),
    ('命名-14-gauge数据项名跟随系列',
     [DATA / 'gauge.csv', 'gauge', '--y-axis', '完成率', '--series-name', '季度达成'],
     ['"name": "季度达成"'], ['"name": "完成率"']),
    ('命名-15-radar数据项名跟随系列',
     [DATA / 'radar.csv', 'radar', '--x-axis', '指标', '--y-axis', '产品a', '产品b',
      '--series-names', '产品甲', '产品乙'],
     ['"name": "产品甲"', '"name": "产品乙"'], ['"name": "产品a"', '"name": "产品b"']),
    ('命名-16-scatter维度名跟随轴名',
     [DATA / 'scatter_xy.csv', 'scatter', '--x-axis', 'x_val', '--y-axis', 'y_val',
      '--x-name', '自变量', '--y-name', '因变量'],
     ['["自变量", "因变量"]'], ['["x_val", "y_val"]']),
]
# 标题带序号：并发跑时避免同名 HTML 互相覆盖（文件名 = 标题 + 内容哈希）
_NM_ARGS = [[*a, '--title', f'NM{i}'] for i, (_, a, _, _) in enumerate(NAMING)]
for (nm, _, must, must_not), res in zip(NAMING, run_many(_NM_ARGS)):
    seg = seg_of(res)
    ok = seg is not None and all(m in seg for m in must) and not any(m in seg for m in must_not)
    rec(nm, ok, '' if ok else f"缺: {[m for m in must if not seg or m not in seg]} "
                              f"残留: {[m for m in must_not if seg and m in seg]} "
                              f"{(res[1] or {}).get('chart', {}).get('error', '')}")

# 多图 --charts-file 透传 series_name（走 charts[] 而非 chart{}，单独判）
_cfg = ROOT / 'names_charts.json'
_cfg.write_text(json.dumps([{"type": "gauge", "title": "A", "y_axis": ["完成率"],
                             "series_name": "达成率"}], ensure_ascii=False), encoding='utf-8')
rc, out, se = run_cli([DATA / 'gauge.csv', '--charts-file', _cfg])
_html = Path(out['charts'][0]['html_path']).read_text(encoding='utf-8') if (rc == 0 and out and out.get('charts')) else ''
rec("命名-10-多图透传series_name", rc == 0 and '"name": "达成率"' in _html and '"name": "仪表盘"' not in _html)

# ══════════════════ N: 新增图表针对性验证（map/lines/calendar/effect_scatter…）══════════════════
print("\n─── N: 新增图表针对性验证 ───")
# 并发跑完再按需读回 HTML——瓶颈是子进程启动，读文件开销可忽略
N_ARGS = {
    'N1-map': [DATA / 'region.csv', 'map', '--x-axis', '地区', '--y-axis', '销售额'],
    'N2-lines': [DATA / 'routes.csv', 'lines', '--x-axis', '来源', '--y-axis', '去向', '金额'],
    'N3-effect_scatter': [DATA / 'students.csv', 'effect_scatter', '--x-axis', '数学', '--y-axis', '语文',
                          '--label-col', '姓名', '--series-name', '成绩分布'],
    'N4-calendar': [DATA / 'calendar.csv', 'calendar', '--x-axis', '日期', '--y-axis', '活跃'],
    'N5-pictorial_bar': [DATA / 'cities.csv', 'pictorial_bar', '--x-axis', '城市', '--y-axis', '销售额',
                         '--series-name', '销量'],
    'N6-theme_river': [DATA / 'river.csv', 'theme_river', '--x-axis', '日期', '--y-axis', '产品a', '产品b'],
    'N7-map面板': [DATA / 'region.csv', 'map', '--x-axis', '地区', '--y-axis', '销售额'],
    'N8-geo-path': [DATA / 'countries.csv', 'map', '--x-axis', '国家', '--y-axis', '销售额',
                    '--geo-path', str(DATA / 'world_custom.json')],
    # 注：列名 GDP 经规范化转小写为 gdp，--y-axis 需引用规范化后的列名
    'N10-geo-world': [DATA / 'world_gdp.csv', 'map', '--x-axis', '国家', '--y-axis', 'gdp',
                      '--geo', 'world'],
}
N_RES = dict(zip(N_ARGS, run_many([[*a, '--title', k] for k, a in N_ARGS.items()])))

# N1: map 离线 registerMap + 系列类型 + plot_stats 地域聚合（6 地区全匹配）
_h = html_of(N_RES['N1-map'])
rec("N1-map-registerMap内联+type",
    'echarts.registerMap("china"' in _h and '"type": "map"' in _h, "缺 registerMap 或 type=map")
rec("N1-map-plot_stats地域聚合",
    extra_of(N_RES['N1-map']).get('region_count') == 6 and not extra_of(N_RES['N1-map']).get('unmatched'),
    f"{extra_of(N_RES['N1-map'])}")

# N2: lines 离线 registerMap + 系列类型 + 边统计（4 条边全对齐到省级）
_h = html_of(N_RES['N2-lines'])
rec("N2-lines-registerMap内联+type",
    'echarts.registerMap("china"' in _h and '"type": "lines"' in _h, "缺 registerMap 或 type=lines")
rec("N2-lines-边统计", extra_of(N_RES['N2-lines']).get('edge_count') == 4, f"{extra_of(N_RES['N2-lines'])}")

# N3: effect_scatter 复用 scatter 契约（轴名可拖拽 + 系列可改名）
_seg = seg_of(N_RES['N3-effect_scatter'])
rec("N3-effect_scatter类型+轴名可拖拽", _seg is not None and 'effectScatter' in _seg
    and '"axisName-x"' in _seg and '"draggable": true' in _seg)
rec("N3-effect_scatter系列可改名", _seg is not None and '"name": "成绩分布"' in _seg)

# N4: calendar 坐标系 + 统计天数/峰值
_h = html_of(N_RES['N4-calendar'])
rec("N4-calendar坐标系", '"calendar": {' in _h and '"type": "heatmap"' in _h
    and '"coordinateSystem": "calendar"' in _h)
rec("N4-calendar-统计天数峰值", extra_of(N_RES['N4-calendar']).get('days') == 5
    and extra_of(N_RES['N4-calendar']).get('peak_day', {}).get('value') == 200,
    f"{extra_of(N_RES['N4-calendar'])}")

# N5: pictorial_bar 复用 bar 契约（轴名可拖拽 + 系列可改名）
_seg = seg_of(N_RES['N5-pictorial_bar'])
rec("N5-pictorial_bar类型+轴名可拖拽", _seg is not None and 'pictorialBar' in _seg
    and '"axisName-x"' in _seg and '"draggable": true' in _seg)
rec("N5-pictorial_bar系列可改名", _seg is not None and '"name": "销量"' in _seg)

# N6: theme_river 单时间轴 + 多系列数据落盘
_h = html_of(N_RES['N6-theme_river'])
rec("N6-theme_river类型+singleAxis", '"type": "themeRiver"' in _h and '"singleAxis": {' in _h
    and '产品a' in _h and '产品b' in _h)

# N7: 无系列概念的图（map/calendar）不渲染系列重命名面板（NO_SERIES_CHART_TYPES 生效）
rec("N7-map无系列重命名面板", 'if (false) {' in html_of(N_RES['N7-map面板']))

# N8: --geo-path 自备 GeoJSON——registerMap 用文件名 stem、地名精确匹配、无未匹配
_h = html_of(N_RES['N8-geo-path'])
rec("N8-geopath-registerMap用文件名",
    'echarts.registerMap("world_custom"' in _h and '"map": "world_custom"' in _h,
    "自备地图 registerMap/map 名应为文件名 stem world_custom")
rec("N8-geopath-地名精确匹配无别名",
    extra_of(N_RES['N8-geo-path']).get('region_count') == 3
    and not extra_of(N_RES['N8-geo-path']).get('unmatched'), f"{extra_of(N_RES['N8-geo-path'])}")

# N9: --geo 指向不存在内置图名 → 结构化错误 + 提示 --geo-path
rc, out, se = run_cli([DATA / 'region.csv', 'map', '--title', 'N9', '--x-axis', '地区',
                       '--y-axis', '销售额', '--geo', 'no_such_map'])
rec("N9-geo不存在报错带提示", rc == 1 and out is not None
    and '内置地图资源缺失' in out.get('chart', {}).get('error', {}).get('error', '')
    and '--geo-path' in out.get('chart', {}).get('error', {}).get('details', {}).get('suggestion', ''),
    f"{out}")

# N10: 内置世界地图（--geo world）——英文国名精确匹配、registerMap 用 world
_h = html_of(N_RES['N10-geo-world'])
rec("N10-geo-world内置地图", 'echarts.registerMap("world"' in _h and '"map": "world"' in _h,
    "内置 world 地图 registerMap/map 名应为 world")
rec("N10-geo-world国名匹配",
    extra_of(N_RES['N10-geo-world']).get('region_count') == 4
    and not extra_of(N_RES['N10-geo-world']).get('unmatched'), f"{extra_of(N_RES['N10-geo-world'])}")

# ══════════════════ PF: 数据画像（--profile）与粒度口径自检 ══════════════════
print("\n─── PF: 数据画像与粒度自检 ───")

# 面板数据：月份 × 地区，其中「华南」自 4 月起腰斩（整体均值会掩盖该分化）
_rows = []
for _m in range(1, 7):
    for _r, _b in (('华东', 120), ('华南', 90), ('华北', 75), ('西南', 40)):
        _amt = _b * (1 + 0.05 * _m)
        if _r == '华南' and _m >= 4:
            _amt *= 0.45
        _rows.append({'月份': f'{_m}月', '地区': _r, '销售额': round(_amt, 1),
                      '订单数': int(_amt / 12)})
pd.DataFrame(_rows).to_csv(DATA / 'panel.csv', index=False, encoding='utf-8')

# 数据质量样本：状态列全同值（常量列）、备注列缺失 4/6
(DATA / 'quality.csv').write_text(
    "姓名,部门,状态,得分,备注\n张三,A,正常,80,\n李四,A,正常,85,x\n王五,B,正常,90,\n"
    "赵六,B,正常,,\n孙七,A,正常,88,\n周八,B,正常,,\n", encoding='utf-8')


# PF1: --profile 不需要图表类型即可运行（否则「先画像后选型」的工作流走不通）
rc, out, _ = profile(DATA / 'panel.csv')
rec("PF1-profile无需chart_type", rc == 0 and out is not None and 'chart' not in (out or {}),
    f"rc={rc} out_keys={list((out or {}).keys())[:6]}")
rec("PF1-profile结构完整", out is not None and all(
    k in out for k in ('rows', 'cols', 'columns', 'grain', 'relations', 'signals', 'row_quality')),
    f"{list((out or {}).keys())}")

# PF2: 客观类型（无 role 字段）——数值列带 numeric 块、时间列带 time 块、文本列带 top_values
_cols = {c['name']: c for c in (out or {}).get('columns', [])}
rec("PF2-profile无role只有客观事实", 'role' not in (_cols.get('月份') or {})
    and 'role' not in (_cols.get('地区') or {})
    and 'role' not in (_cols.get('销售额') or {}),
    f"{ {k: sorted(v.keys()) for k, v in _cols.items()} }")
rec("PF2-profile客观统计块", 'time' in (_cols.get('月份') or {})
    and 'top_values' in (_cols.get('地区') or {})
    and 'numeric' in (_cols.get('销售额') or {}),
    f"{ {k: [x for x in v if x in ('numeric','time','top_values')] for k, v in _cols.items()} }")
rec("PF2-profile基数与分布", _cols.get('月份', {}).get('cardinality') == 6
    and _cols.get('地区', {}).get('cardinality') == 4
    and _cols.get('地区', {}).get('top_values')
    and _cols.get('销售额', {}).get('numeric', {}).get('max') == 156.0,
    f"{_cols.get('月份', {}).get('cardinality')} {_cols.get('地区', {}).get('top_values')} "
    f"{_cols.get('销售额', {}).get('numeric')}")

# PF3: 粒度——唯一键必须来自非数值列，且能识别出「月份+地区」组合键
_grain = (out or {}).get('grain', {})
rec("PF3-profile实体粒度", '销售额' not in _grain.get('unique_keys', [])
    and ['月份', '地区'] in _grain.get('unique_key_pairs', []),
    f"{_grain}")

# PF4: 候选洞察信号——整体上行掩盖下仍能抓出「华南」逆势下滑
_kinds = [s['kind'] for s in (out or {}).get('signals', [])]
_div = next((s for s in (out or {}).get('signals', []) if s['kind'] == 'divergent_category'), None)
_trend = next((s for s in (out or {}).get('signals', []) if s['kind'] == 'trend'), None)
rec("PF4-profile趋势信号", _trend is not None and _trend['evidence'].get('change_pct') is not None
    and _trend['evidence'].get('largest_step') is not None,
    f"{_trend}")
rec("PF4-profile逆势类别信号", _div is not None and _div['evidence'].get('category') == '华南'
    and _div['evidence']['category_change'] < -0.25
    and _div['evidence']['category_change'] < _div['evidence']['overall_change'],
    f"{_div}")
rec("PF4-profile集中度信号", 'concentration' in _kinds, f"{_kinds}")

# PF5: 不产图型建议——「出什么图」由 agent 从 columns/signals 自行判断，profile 不代笔
rec("PF5-profile不产图型建议", 'recommendations' not in (out or {}),
    f"{list((out or {}).keys())}")

# PF6: data_parser.py --profile 与 cli.py --profile 输出等价（两个入口都可用）
rc2, out2, _ = profile(DATA / 'panel.csv', via='dp')
rec("PF6-dataparser同入口画像", rc2 == 0 and out2 is not None
    and out2.get('rows') == (out or {}).get('rows')
    and [s['kind'] for s in out2.get('signals', [])] == _kinds,
    f"rc={rc2} rows={out2 and out2.get('rows')}")

# PF7: 数据质量信号（常量列 / 高缺失列）
rc3, out3, _ = profile(DATA / 'quality.csv')
_k3 = {s['kind']: s for s in (out3 or {}).get('signals', [])}
rec("PF7-profile常量与缺失信号", 'constant' in _k3 and 'missing' in _k3
    and _k3['missing']['columns'] == ['备注'] and _k3['missing']['evidence']['rate'] >= 0.6,
    f"{ {k: v['columns'] for k, v in _k3.items()} }")

# PF8/PF9/PF10: 粒度口径自检——明细画 line 必须报警，聚合后与散点不误报
(rc4, out4, _), (rc5, out5, _), (rc6, out6, _) = run_many([
    [DATA / 'panel.csv', 'line', '--title', 'PF8', '--x-axis', '月份', '--y-axis', '销售额'],
    [DATA / 'panel.csv', 'bar', '--title', 'PF9', '--x-axis', 'name', '--y-axis', 'value',
     '--transform-code',
     "result = df.groupby('地区')['销售额'].sum().rename_axis('name').reset_index(name='value')"],
    [DATA / 'panel.csv', 'scatter', '--title', 'PF10', '--x-axis', '销售额', '--y-axis', '订单数'],
])
_adv4 = ' '.join((out4 or {}).get('chart', {}).get('advisories', []))
rec("PF8-未聚合line报警", rc4 == 0 and '疑似未聚合' in _adv4 and '月份' in _adv4, f"{_adv4[:160]}")
rec("PF8-报警图仍成功落盘", rc4 == 0 and (out4 or {}).get('chart', {}).get('success') is True
    and (out4 or {}).get('chart', {}).get('html_path'), "advisory 不应阻断生成")
for nm, rc, res in (('PF9-聚合后不报警', rc5, out5), ('PF10-散点明细不误报', rc6, out6)):
    rec(nm, rc == 0 and not any('疑似未聚合' in a
                                for a in (res or {}).get('chart', {}).get('advisories', [])),
        f"{(res or {}).get('chart', {}).get('advisories')}")

# PF11: --emit-charts 已删除——「出什么图」由 agent 决策，不再由 profile 代写配置。
# 传 --emit-charts 应报结构化错误（参数已移除），绝不静默忽略。
rc7, out7, se7 = run_cli([DATA / 'panel.csv', '--profile', '--emit-charts', 'x.json'])
rec("PF11-emit-charts已移除并报错", rc7 == 1 and '--emit-charts' in se7,
    f"rc={rc7} se={se7[:160]}")

# ══════════════════ R: 8.4.0 改造项回归（① ③ ⑤）══════════════════
print("\n─── R: 8.4.0 改造项回归 ───")

# 脏表样本：第 0 行是子表头（分类列有值、数值列全空 → 疑似非数据行）。
# 姓名/科目 均有重复取值，无唯一键（供 R4 验证 grain.note 动态化）。
(DATA / 'dirty.csv').write_text(
    "姓名,科目,成绩\n考核项,分值,\n张三,数学,85\n张三,数学,90\n", encoding='utf-8')
# 稀疏相关样本：y 列仅 1 个非空值，与 x 相关会触发 numpy cov 的 RuntimeWarning
(DATA / 'sparse_corr.csv').write_text(
    "x,y\n1,10\n2,\n3,\n4,\n5,\n", encoding='utf-8')

# R1: ① --profile --transform-code 生效 + 白名单外参数报错
rc, out, se = run_cli([DATA / 'panel.csv', '--profile',
                       '--transform-code', "result = df.groupby('地区')['销售额'].sum().reset_index()"])
rec("R1-profile+transform生效(rows变化)", rc == 0 and out is not None and out.get('rows') == 4,
    f"rc={rc} rows={out and out.get('rows')}")
rc, out, se = run_cli([DATA / 'panel.csv', '--profile', '--x-axis', '地区'])
rec("R1-profile白名单外参数报错", rc == 1 and 'CHART_CONFIG_ERROR' in se and '--x-axis' in se,
    f"rc={rc} se={se[:150]}")

# R2: ③a --profile --drop-rows 生效 + advisory
rc, out, se = run_cli([DATA / 'dirty.csv', '--profile', '--drop-rows', '0'])
rec("R2-profile+drop-rows生效+advisory",
    rc == 0 and out is not None and out.get('rows') == 2
    and any('--drop-rows' in a for a in out.get('advisories', [])),
    f"rc={rc} rows={out and out.get('rows')} adv={out and out.get('advisories')}")

# R3: ③b row_quality 脏表命中、整洁表零命中
rc, out, se = run_cli([DATA / 'dirty.csv', '--profile'])
_sus = (out or {}).get('row_quality', {}).get('suspicious_non_data_rows', [])
rec("R3-row_quality脏表命中", rc == 0 and [r['row'] for r in _sus] == [0], f"rc={rc} sus={_sus}")
rc2, out2, se2 = run_cli([DATA / 'panel.csv', '--profile'])
_sus2 = (out2 or {}).get('row_quality', {}).get('suspicious_non_data_rows', [])
rec("R3-row_quality整洁表零命中", rc2 == 0 and _sus2 == [], f"rc={rc2} sus={_sus2}")

# R4: ⑤-1 grain.note 随唯一键动态变化（panel 有组合键，freq 单列重复无键）
rc3, out3, _ = run_cli([DATA / 'freq.csv', '--profile'])
_note_has = (out2 or {}).get('grain', {}).get('note', '')
_note_no = (out3 or {}).get('grain', {}).get('note', '')
rec("R4-grain.note有键说存在", '存在唯一键' in _note_has and '无唯一键' not in _note_has, f"{_note_has}")
rec("R4-grain.note无键说无", '无唯一键' in _note_no and '存在唯一键' not in _note_no, f"{_note_no}")

# R5: ⑤-2 长标题截断挂 advisory
rc, out, se = run_cli([DATA / 'cities.csv', 'bar',
                       '--title', '这是一个非常非常长的中文标题用来验证文件名是否会被静默截断到三十个字符',
                       '--x-axis', '城市', '--y-axis', '销售额'])
rec("R5-长标题截断挂advisory",
    rc == 0 and out and any('截断' in a for a in out['chart'].get('advisories', [])),
    f"rc={rc} adv={out and out['chart'].get('advisories')}")

# R6: ⑤-3 相关计算不再产生 RuntimeWarning（y 列仅 1 个非空值）
rc, out, se = run_cli([DATA / 'sparse_corr.csv', '--profile'])
rec("R6-profile无RuntimeWarning", 'RuntimeWarning' not in se, f"se={se[:150]}")

# R7: 语义判断交 agent——profile 不做 role 归类、不做图型推荐。
# 值形态保护仍生效：前导零 / 超长数字保持字符串；普通数字串正常数值化（是否 ID 由 agent 判断）
_df_ghost = pd.DataFrame({
    '地区': ['华北', '华东', '华南', '西南', '华北', '华东'],
    '子表头': ['科目', '分值', None, None, None, None],
    '编号': [1, 2, 3, 4, 5, 6],
    '销售额': [120.5, 150.3, 90.2, 80.1, 125.4, 148.9],
    '利润': [30.2, 40.1, 25.5, 20.3, 32.1, 38.7],
})
_prof = build_profile(_df_ghost)
rec("R7-profile不产推荐", 'recommendations' not in _prof,
    f"{list(_prof.keys())}")
rec("R7-profile不产role", all('role' not in c for c in _prof['columns']),
    f"{[c['name'] for c in _prof['columns'] if 'role' in c]}")

# R7 后半：值形态保护——前导零、超长数字保持字符串，普通数字正常数值化。
# 「编号」是普通 1 位数字 → 数值化（是否 ID 交给 agent 判断，不再靠列名词表）。
_data = {
    '编号_前导零': ['007', '008', '012', '013'],
    '长单号': ['202409120001234567', '202409120001234568', '202409120001234569', '202409120001234570'],
    '金额': ['120.5', '150.3', '90.2', '80.1'],
}
_dfd = pd.DataFrame(_data)
_csv = DATA / 'idcols.csv'
_dfd.to_csv(_csv, index=False, encoding='utf-8')
_df_id = DataParser().parse_file(str(_csv))
rec("R7-前导零保持字符串", not pd.api.types.is_numeric_dtype(_df_id['编号_前导零'])
    and _df_id['编号_前导零'].tolist() == ['007', '008', '012', '013'],
    f"dtype={_df_id['编号_前导零'].dtype} vals={_df_id['编号_前导零'].tolist()}")
rec("R7-超长数字保持字符串", not pd.api.types.is_numeric_dtype(_df_id['长单号'])
    and len(str(_df_id['长单号'].iloc[0])) == 18,
    f"dtype={_df_id['长单号'].dtype} len={len(str(_df_id['长单号'].iloc[0]))}")
rec("R7-普通数字正常数值化", pd.api.types.is_numeric_dtype(_df_id['金额'])
    and float(_df_id['金额'].iloc[0]) == 120.5,
    f"dtype={_df_id['金额'].dtype}")

# ══════════════════ 汇总 ══════════════════
print("\n" + "═" * 60)
print(f"总计: {PASS + FAIL} | 通过: {PASS} | 失败: {FAIL}")
if FAILURES:
    print("\n失败明细:")
    for n, d in FAILURES:
        print(f"  ✗ {n}\n    {d[:250]}")
print("═" * 60)
print(f"测试数据与输出: {ROOT}（临时目录，可安全删除）")
sys.exit(1 if FAIL else 0)
