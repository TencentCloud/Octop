"""Tests for the B1 silence-list judge and the REVIEW-SPEC template it anchors to.

The judge is a pure function over the artifact's **text lines**, so every case here is
written the way a reviewer would break the template: delete the section, delete a column,
write an illegal ruling, overflow the 50-row budget. Each mutation must produce its own
code — and the two codes must never appear together.
"""

from __future__ import annotations

from pathlib import Path

from octop.infra.agents.teams import silence_list
from octop.infra.agents.teams.silence_list import (
    ALLOWED_VERDICT_PREFIXES,
    CODE_INCOMPLETE,
    CODE_MISSING,
    MAX_ROWS,
    REQUIRED_COLUMNS,
    SilenceReport,
    missing,
)

_MODULE_FILE = silence_list.__file__
assert _MODULE_FILE is not None
TEMPLATES = Path(_MODULE_FILE).resolve().parent / "templates" / "run"
REVIEW_SPEC = TEMPLATES / "REVIEW-SPEC.md"
SPEC = TEMPLATES / "SPEC.md"

HEADING = "## 沉默清单（见一个，扫全部）"
HEADER = "| 建议裁定 | 依据 | 风险 |"
SEPARATOR = "|---|---|---|"


def _row(verdict: str = "允许：按现状放行", basis: str = "SPEC R1", risk: str = "低") -> str:
    return f"| {verdict} | {basis} | {risk} |"


def _body(rows: list[str], heading: str = HEADING) -> str:
    return "\n".join([heading, "", HEADER, SEPARATOR, *rows, ""])


# --- A3 正对照：三列齐 + ≤ 50 行 ⇒ 两码皆空 -------------------------------------------


def test_complete_list_is_green() -> None:
    report = missing(_body([_row(), _row("禁止：不得跳过锚点", "PLAN R4", "中")]))
    assert report == SilenceReport(missing=(), incomplete=(), rows=2, details=())
    assert hash(report) == hash(
        missing(_body([_row(), _row("禁止：不得跳过锚点", "PLAN R4", "中")]))
    )


def test_exactly_max_rows_is_green() -> None:
    report = missing(_body([_row() for _ in range(MAX_ROWS)]))
    assert report.missing == ()
    assert report.incomplete == ()
    assert report.rows == MAX_ROWS == 50


def test_section_scope_stops_at_next_same_level_heading() -> None:
    """A junk table after the next `##` heading is not this section's rows (R1)."""
    text = _body([_row()]) + f"\n## 复核记录\n\n{HEADER}\n{SEPARATOR}\n| | | |\n"
    report = missing(text)
    assert report.missing == ()
    assert report.incomplete == ()
    assert report.rows == 1


def test_verdict_prefix_is_prefix_not_equality() -> None:
    """`允许` / `禁止` are prefix matches, so a ruling may carry its detail after a colon."""
    assert ALLOWED_VERDICT_PREFIXES == ("允许", "禁止")
    for verdict in ("允许", "禁止：不得沉默", "允许：留待运行期观测"):
        assert missing(_body([_row(verdict=verdict)])).incomplete == ()


# --- A1 缺章节 / 空章节 / 只有表头 ⇒ SILENCE_LIST_MISSING -----------------------------


def test_missing_when_no_section_at_all() -> None:
    report = missing("# 规格说明（SPEC）\n\n## 业务规则\n\n无。\n")
    assert report == SilenceReport(missing=(CODE_MISSING,), incomplete=(), rows=0, details=())


def test_missing_when_heading_without_table() -> None:
    report = missing(f"# 规格审查\n\n{HEADING}\n\n(待填)\n\n## 复核记录\n")
    assert report.missing == (CODE_MISSING,)
    assert report.incomplete == ()
    assert report.rows == 0


def test_missing_when_header_only() -> None:
    """Header + separator with no data row is still an empty section (R2)."""
    report = missing(f"{HEADING}\n\n{HEADER}\n{SEPARATOR}\n")
    assert report.missing == (CODE_MISSING,)
    assert report.incomplete == ()
    assert report.rows == 0


def test_heading_matches_any_level_and_numbering_is_optional() -> None:
    for heading in ("# 沉默清单", "### 沉默清单", "###### 沉默清单（见一个，扫全部）"):
        assert missing(_body([_row()], heading=heading)).missing == ()


# --- A2 缺列 / 裁定非法 / 51 行 ⇒ SILENCE_LIST_INCOMPLETE（且 missing 为空） ------------


def test_incomplete_when_a_required_column_is_deleted() -> None:
    text = "\n".join([HEADING, "", "| 建议裁定 | 风险 |", "|---|---|", "| 允许 | 低 |", ""])
    report = missing(text)
    assert report.incomplete == (CODE_INCOMPLETE,)
    assert report.missing == ()
    assert report.rows == 1
    assert report.details == ("L5 · 依据",)


def test_incomplete_when_one_cell_of_a_column_is_blank() -> None:
    report = missing(_body([_row(), _row(risk="")]))
    assert report.missing == ()
    assert report.incomplete == (CODE_INCOMPLETE,)
    assert report.details == ("L6 · 风险",)


def test_incomplete_when_verdict_is_illegal() -> None:
    report = missing(_body([_row(verdict="待定")]))
    assert report.missing == ()
    assert report.incomplete == (CODE_INCOMPLETE,)
    assert report.details == ("L5 · verdict · invalid verdict",)


def test_incomplete_when_rows_exceed_max() -> None:
    report = missing(_body([_row() for _ in range(MAX_ROWS + 1)]))
    assert report.missing == ()
    assert report.incomplete == (CODE_INCOMPLETE,)
    assert report.rows == 51
    assert report.details == ("rows · too many rows",)


def test_codes_are_mutually_exclusive() -> None:
    texts = [
        "# 无清单\n",
        f"{HEADING}\n",
        f"{HEADING}\n\n{HEADER}\n{SEPARATOR}\n",
        _body([_row()]),
        _body([_row(verdict="待定")]),
        _body([_row() for _ in range(MAX_ROWS + 1)]),
    ]
    for text in texts:
        report = missing(text)
        assert not (report.missing and report.incomplete), text


def test_required_columns_and_prefixes_are_the_verbatim_plan_values() -> None:
    assert REQUIRED_COLUMNS == ("建议裁定", "依据", "风险")
    assert ALLOWED_VERDICT_PREFIXES == ("允许", "禁止")
    assert MAX_ROWS == 50


def test_judge_is_pure() -> None:
    """`missing` writes nothing and reads nothing: no I/O calls in the module source."""
    source = Path(_MODULE_FILE).read_text(encoding="utf-8")
    for forbidden in ("open(", "write_text", "read_text", "os.", "Path(", "subprocess"):
        assert forbidden not in source, forbidden


# --- 模板：必需章节与三列逐字（PLAN §2.5） -------------------------------------------


def test_review_spec_template_has_the_required_sections_and_columns() -> None:
    text = REVIEW_SPEC.read_text(encoding="utf-8")
    assert "# 规格审查（REVIEW-SPEC）" in text
    assert HEADING in text
    assert HEADER in text
    assert SEPARATOR in text
    assert "## 复核记录" in text


def test_review_spec_template_placeholder_row_is_a_visible_red() -> None:
    """The shipped placeholder row is empty ⇒ incomplete, and never missing."""
    report = missing(REVIEW_SPEC.read_text(encoding="utf-8"))
    assert report.missing == ()
    assert report.incomplete == (CODE_INCOMPLETE,)
    assert report.rows == 1


def test_review_spec_boundary_table_satisfies_the_host_gate_shape() -> None:
    """Heading without a numeric prefix, and at least one non-empty 期望拒绝 cell."""
    lines = REVIEW_SPEC.read_text(encoding="utf-8").splitlines()
    start = lines.index("## 边界与禁止项（强制 · 沉默 ≠ 允许）")
    table = [line for line in lines[start:] if line.strip().startswith("|")]
    header, *rows = table
    assert [cell.strip() for cell in header.strip("|").split("|")] == [
        "边界族",
        "规则（禁止什么）",
        "期望拒绝",
        "验收方式",
    ]
    rejections = [cell for row in rows[1:] if (cell := row.strip("|").split("|")[2].strip())]
    assert rejections


def test_spec_template_points_at_the_silence_list() -> None:
    text = SPEC.read_text(encoding="utf-8")
    assert "## 沉默清单" in text
    assert "REVIEW-SPEC.md" in text
    assert "沉默不得作为通过理由" in text
