"""Bounded text extraction from Excel 2003 XML (not the XLSX XML format)."""

from __future__ import annotations

import codecs
import xml.etree.ElementTree as ET
from collections.abc import Iterator
from pathlib import Path

_SS = "{urn:schemas-microsoft-com:office:spreadsheet}"
_MAX_BYTES = 16 * 1024 * 1024
_MAX_ELEMENTS = 500_000
_MAX_DEPTH = 64
_MAX_ROWS = 65_536
_MAX_COLUMNS = 256


def looks_like_xml(prefix: bytes) -> bool:
    """Recognize XML encodings without decoding binary BIFF as text."""
    if prefix.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)):
        return True
    return prefix.removeprefix(codecs.BOM_UTF8).replace(b"\0", b"").lstrip().startswith(b"<")


class _BoundedTreeBuilder(ET.TreeBuilder):
    def __init__(self) -> None:
        super().__init__()
        self._depth = 0
        self._elements = 0

    def start(self, tag: str, attrs: dict[str, str]) -> ET.Element:
        self._depth += 1
        self._elements += 1
        if self._depth > _MAX_DEPTH or self._elements > _MAX_ELEMENTS:
            raise ValueError("SpreadsheetML XML structure exceeds extraction limits")
        return super().start(tag, attrs)

    def end(self, tag: str) -> ET.Element:
        self._depth -= 1
        return super().end(tag)

    def doctype(self, name: str, pubid: str | None, system: str | None) -> None:
        raise ValueError("SpreadsheetML DTD declarations are not supported")


def _index(raw: str | None, *, minimum: int, maximum: int) -> int:
    try:
        value = minimum if raw is None else int(raw)
    except ValueError as exc:
        raise ValueError("SpreadsheetML index must be an integer") from exc
    if not minimum <= value <= maximum:
        raise ValueError("SpreadsheetML index is out of range or overlaps an earlier cell/row")
    return value


def _cell_value(cell: ET.Element) -> object:
    data = cell.find(f"{_SS}Data")
    if data is None:
        # A formula without cached Data has no value to index. Never evaluate it.
        return None
    kind = data.get(f"{_SS}Type", "String")
    text = "".join(data.itertext())
    if kind == "Error":
        return None
    if kind == "Boolean":
        value = text.strip().lower()
        if value not in {"0", "1", "false", "true"}:
            raise ValueError("SpreadsheetML Boolean value is invalid")
        return value in {"1", "true"}
    if kind not in {"String", "Number", "DateTime"}:
        raise ValueError(f"SpreadsheetML Data type is unsupported: {kind}")
    # Text extraction needs no float conversion (which would round long IDs).
    return text


def _rows(table: ET.Element) -> Iterator[list[object]]:
    left = _index(table.get(f"{_SS}LeftCell"), minimum=1, maximum=_MAX_COLUMNS)
    top = _index(table.get(f"{_SS}TopCell"), minimum=1, maximum=_MAX_ROWS)
    next_row = 1
    for row in table.iterfind(f"{_SS}Row"):
        row_index = _index(row.get(f"{_SS}Index"), minimum=next_row, maximum=_MAX_ROWS - top + 1)
        next_row = row_index + 1
        cells: list[object] = []
        next_column = 1
        for cell in row.iterfind(f"{_SS}Cell"):
            relative_column = _index(
                cell.get(f"{_SS}Index"), minimum=next_column, maximum=_MAX_COLUMNS - left + 1
            )
            column = left + relative_column - 1
            merge = _index(cell.get(f"{_SS}MergeAcross"), minimum=0, maximum=_MAX_COLUMNS - column)
            cells.extend([None] * (column - 1 - len(cells)))
            cells.append(_cell_value(cell))
            next_column = relative_column + merge + 1
        # Blank/sparse rows need not be expanded: the shared text renderer omits them.
        yield cells


def read_sheets(path: Path) -> Iterator[tuple[str, Iterator[list[object]]]]:
    """Read actual SpreadsheetML workbooks with bounded XML and spreadsheet indices.

    Only cached cell values are extracted. Styles, macros, links, and formulas
    are never executed; ExpandedRowCount/ExpandedColumnCount do not allocate data.
    """
    with path.open("rb") as stream:
        raw = stream.read(_MAX_BYTES + 1)
    if len(raw) > _MAX_BYTES:
        raise ValueError("SpreadsheetML XML exceeds the 16 MiB extraction limit")
    try:
        root = ET.fromstring(raw, parser=ET.XMLParser(target=_BoundedTreeBuilder()))
    except ET.ParseError as exc:
        raise ValueError("SpreadsheetML XML is malformed") from exc
    if root.tag != f"{_SS}Workbook":
        raise ValueError("SpreadsheetML Workbook namespace is required for XML .xls files")
    for sheet in root.iterfind(f"{_SS}Worksheet"):
        table = sheet.find(f"{_SS}Table")
        if table is not None:
            yield sheet.get(f"{_SS}Name", "Sheet"), _rows(table)
