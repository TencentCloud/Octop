"""Excel 2003 XML exports must be indexed without treating them as BIFF."""

from __future__ import annotations

from pathlib import Path

import pytest

from octop.infra.knowledge.parse import parse_document

NS = "urn:schemas-microsoft-com:office:spreadsheet"


def workbook(body: str, *, encoding: str = "utf-8") -> bytes:
    label = {
        "utf-8-sig": "UTF-8",
        "utf-16-be": "UTF-16BE",
        "utf-16-le": "UTF-16LE",
    }.get(encoding, encoding)
    return (
        f'<?xml version="1.0" encoding="{label}"?>'
        f'<Workbook xmlns="{NS}" xmlns:ss="{NS}">{body}</Workbook>'
    ).encode(encoding)


def worksheet(rows: str, *, name: str = "Sales") -> str:
    return f'<Worksheet ss:Name="{name}"><Table>{rows}</Table></Worksheet>'


def cell(value: str, kind: str = "String", attributes: str = "") -> str:
    return f'<Cell{attributes}><Data ss:Type="{kind}">{value}</Data></Cell>'


@pytest.mark.parametrize("encoding", ["utf-8", "utf-8-sig", "utf-16", "utf-16-be", "utf-16-le"])
def test_actual_xml_xls_preserves_values_and_original_bytes(tmp_path: Path, encoding: str) -> None:
    path = tmp_path / "export.xls"
    data = workbook(
        worksheet(
            "<Row>"
            + cell("编号")
            + cell("数量")
            + "</Row><Row>"
            + cell("0001234567890123456789")
            + cell("12.25", "Number")
            + "</Row>"
        ),
        encoding=encoding,
    )
    path.write_bytes(data)

    assert parse_document(path) == "# Sales\n编号\t数量\n0001234567890123456789\t12.25"
    assert path.read_bytes() == data


def test_prefixed_namespace_sparse_positions_and_multiple_sheets(tmp_path: Path) -> None:
    path = tmp_path / "sparse.xls"
    path.write_text(
        f'<s:Workbook xmlns:s="{NS}">'
        '<s:Worksheet s:Name="First"><s:Table s:ExpandedRowCount="65536">'
        '<s:Row s:Index="100"><s:Cell s:Index="3">'
        '<s:Data s:Type="String">late</s:Data></s:Cell>'
        '<s:Cell><s:Data s:Type="Number">4</s:Data></s:Cell></s:Row>'
        '</s:Table></s:Worksheet><s:Worksheet s:Name="Empty"/>'
        '<s:Worksheet s:Name="Second"><s:Table><s:Row>'
        '<s:Cell><s:Data s:Type="String">end</s:Data></s:Cell>'
        "</s:Row></s:Table></s:Worksheet></s:Workbook>",
        encoding="utf-8",
    )

    assert parse_document(path) == "# First\n\t\tlate\t4\n\n# Second\nend"


def test_cached_formulas_booleans_errors_and_rich_text(tmp_path: Path) -> None:
    path = tmp_path / "cached.xls"
    path.write_bytes(
        workbook(
            worksheet(
                "<Row>"
                + cell("3", "Number", ' ss:Formula="=1+2"')
                + '<Cell ss:Formula="=NOW()"/>'
                + cell("1", "Boolean")
                + cell("0", "Boolean")
                + cell("#DIV/0!", "Error")
                + cell('rich <b xmlns="http://www.w3.org/TR/REC-html40">text</b>')
                + "</Row>"
            )
        )
    )

    assert parse_document(path) == "# Sales\n3\t\tTRUE\tFALSE\t\trich text"


def test_merge_across_keeps_the_following_column_in_place(tmp_path: Path) -> None:
    path = tmp_path / "merged.xls"
    path.write_bytes(
        workbook(
            worksheet(
                "<Row>"
                + cell("heading", attributes=' ss:MergeAcross="2"')
                + cell("next")
                + "</Row>"
            )
        )
    )
    assert parse_document(path) == "# Sales\nheading\t\t\tnext"


@pytest.mark.parametrize(
    "rows",
    [
        '<Row ss:Index="0">' + cell("bad") + "</Row>",
        '<Row ss:Index="65537">' + cell("bad") + "</Row>",
        '<Row ss:Index="nope">' + cell("bad") + "</Row>",
        '<Row ss:Index="3"/><Row ss:Index="2">' + cell("bad") + "</Row>",
        "<Row>" + cell("bad", attributes=' ss:Index="0"') + "</Row>",
        "<Row>" + cell("bad", attributes=' ss:Index="257"') + "</Row>",
        "<Row>" + cell("first") + cell("bad", attributes=' ss:Index="1"') + "</Row>",
        "<Row>" + cell("bad", attributes=' ss:MergeAcross="-1"') + "</Row>",
        "<Row>" + cell("bad", attributes=' ss:Index="256" ss:MergeAcross="1"') + "</Row>",
    ],
)
def test_rejects_invalid_or_out_of_range_positions(tmp_path: Path, rows: str) -> None:
    path = tmp_path / "invalid.xls"
    path.write_bytes(workbook(worksheet(rows)))
    with pytest.raises(ValueError, match="SpreadsheetML"):
        parse_document(path)


@pytest.mark.parametrize("encoding", ["utf-8", "utf-16"])
def test_rejects_dtd_before_expanding_entities(tmp_path: Path, encoding: str) -> None:
    path = tmp_path / "entities.xls"
    xml = (
        f'<?xml version="1.0" encoding="{encoding}"?>'
        '<!DOCTYPE Workbook [<!ENTITY data "expanded">]>'
        f'<Workbook xmlns="{NS}" xmlns:ss="{NS}">'
        + worksheet("<Row>" + cell("&data;") + "</Row>")
        + "</Workbook>"
    )
    path.write_bytes(xml.encode(encoding))
    with pytest.raises(ValueError, match="DTD"):
        parse_document(path)


@pytest.mark.parametrize(
    "xml",
    [
        '<Workbook xmlns="urn:not-the-spreadsheet-format"/>',
        "<html><table><tr><td>not SpreadsheetML</td></tr></table></html>",
        f'<Workbook xmlns="{NS}"><Worksheet>',
    ],
)
def test_rejects_other_xml_and_malformed_workbooks(tmp_path: Path, xml: str) -> None:
    path = tmp_path / "wrong.xls"
    path.write_text(xml, encoding="utf-8")
    with pytest.raises(ValueError, match="SpreadsheetML"):
        parse_document(path)


@pytest.mark.parametrize("limit", ["_MAX_BYTES", "_MAX_ELEMENTS", "_MAX_DEPTH"])
def test_structure_limits_abort_extraction(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, limit: str
) -> None:
    from octop.infra.knowledge import spreadsheetml

    path = tmp_path / "bounded.xls"
    path.write_bytes(workbook(worksheet("<Row>" + cell("value") + "</Row>")))
    monkeypatch.setattr(spreadsheetml, limit, 2)
    with pytest.raises(ValueError, match="limit"):
        parse_document(path)


def test_external_dtd_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "external.xls"
    path.write_bytes(
        b'<!DOCTYPE Workbook SYSTEM "https://example.invalid/workbook.dtd">'
        + workbook(worksheet("<Row>" + cell("value") + "</Row>")).split(b"?>", 1)[1]
    )
    with pytest.raises(ValueError, match="DTD"):
        parse_document(path)


def test_large_sparse_rows_do_not_allocate_blank_rows(tmp_path: Path) -> None:
    path = tmp_path / "last-row.xls"
    path.write_bytes(workbook(worksheet('<Row ss:Index="65536">' + cell("last") + "</Row>")))
    assert parse_document(path) == "# Sales\nlast"


def test_uncached_formula_is_not_invented_as_a_value(tmp_path: Path) -> None:
    path = tmp_path / "formula.xls"
    path.write_bytes(workbook(worksheet('<Row><Cell ss:Formula="=1+1"/></Row>')))
    assert parse_document(path) == ""


def test_real_biff_stays_on_xlrd_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import xlwt

    from octop.infra.knowledge import spreadsheetml

    path = tmp_path / "binary.xls"
    book = xlwt.Workbook()
    book.add_sheet("Binary").write(0, 0, "unchanged")
    book.save(str(path))

    def unexpected(_path: Path) -> None:
        raise AssertionError("BIFF must not enter the XML parser")

    monkeypatch.setattr(spreadsheetml, "read_sheets", unexpected)
    assert parse_document(path) == "# Binary\nunchanged"


@pytest.mark.parametrize(
    ("origin", "row", "expected"),
    [
        ('ss:LeftCell="3"', "<Row>" + cell("C1") + "</Row>", "# Offset\n\t\tC1"),
        (
            'ss:LeftCell="3" ss:TopCell="65536"',
            '<Row ss:Index="1">' + cell("D65536", attributes=' ss:Index="2"') + "</Row>",
            "# Offset\n\t\t\tD65536",
        ),
    ],
)
def test_table_origin_and_sparse_indices_compose(
    tmp_path: Path, origin: str, row: str, expected: str
) -> None:
    path = tmp_path / "offset.xls"
    path.write_bytes(
        workbook(f'<Worksheet ss:Name="Offset"><Table {origin}>{row}</Table></Worksheet>')
    )
    assert parse_document(path) == expected


@pytest.mark.parametrize(
    ("origin", "row"),
    [
        ('ss:LeftCell="0"', "<Row>" + cell("invalid") + "</Row>"),
        ('ss:TopCell="0"', "<Row>" + cell("invalid") + "</Row>"),
        ('ss:LeftCell="257"', "<Row>" + cell("invalid") + "</Row>"),
        ('ss:TopCell="65537"', "<Row>" + cell("invalid") + "</Row>"),
        ('ss:LeftCell="invalid"', "<Row>" + cell("invalid") + "</Row>"),
        ('ss:LeftCell="256"', "<Row>" + cell("invalid", attributes=' ss:Index="2"') + "</Row>"),
        ('ss:TopCell="65536"', '<Row ss:Index="2">' + cell("invalid") + "</Row>"),
    ],
)
def test_table_origin_cannot_bypass_dimension_limits(tmp_path: Path, origin: str, row: str) -> None:
    path = tmp_path / "offset-out-of-range.xls"
    path.write_bytes(
        workbook(f'<Worksheet ss:Name="Offset"><Table {origin}>{row}</Table></Worksheet>')
    )
    with pytest.raises(ValueError, match="SpreadsheetML"):
        parse_document(path)
