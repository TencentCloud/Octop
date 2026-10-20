import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3] / "src"))

from octop.infra.gateway.channels.plain_table_format import (
    _render_plain_rows,
    convert_tables_to_plain,
)
from octop.infra.gateway.channels.telegram_table_format import (
    convert_markdown_tables,
)

N = chr(10)
F = chr(96) * 3


def _md_table(*rows: str) -> str:
    return N.join(rows)


def test_telegram_table_becomes_aligned_code_block():
    md = _md_table("| 名称 | 数值 |", "|:---|---:|", "| CPU | 80% |", "| 内存占用 | 40% |")
    out = convert_markdown_tables(md)
    assert out.startswith(F)
    assert "|---|" not in out
    # CJK 双宽：表头与数据列对齐（显示宽度一致）
    lines = out.strip("`" + N).split(N)
    assert len(lines) == 4  # 表头 + 分隔线 + 2 数据行


def test_plain_table_becomes_keyed_list_rows():
    md = _md_table("| 名称 | 数值 |", "|---|---|", "| CPU | 80% |")
    out = convert_tables_to_plain(md)
    assert out == "- 名称=CPU | 数值=80%"


def test_table_inside_code_fence_untouched():
    fenced = F + N + _md_table("| x | y |", "|---|---|", "| 1 | 2 |") + N + F
    assert convert_markdown_tables(fenced) == fenced
    assert convert_tables_to_plain(fenced) == fenced


def test_non_table_pipe_lines_untouched():
    assert convert_markdown_tables("a || b") == "a || b"
    assert convert_tables_to_plain("单行 | 竖线") == "单行 | 竖线"


def test_short_rows_padded_and_empty_rows_skipped():
    rows = [["a", "b"], ["---", "---"], ["1"], ["", ""]]
    assert _render_plain_rows(rows) == "- a=1"


def test_plain_multicolumn_keeps_headers():
    md = _md_table("| 项目 | 状态 |", "|---|---|", "| A | ok |", "| B | warn |")
    assert convert_tables_to_plain(md) == "- 项目=A | 状态=ok" + N + "- 项目=B | 状态=warn"
