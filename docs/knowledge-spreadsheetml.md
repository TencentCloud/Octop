# Excel 2003 XML exports in knowledge bases

Some business systems export a file named `.xls` whose content is an Excel 2003
XML Spreadsheet (SpreadsheetML), rather than a binary Excel workbook. Upload
these files through the existing knowledge-base document upload. Octop recognizes
the XML Workbook namespace; binary `.xls` files continue through `xlrd`.

The extracted text uses the same sheet headings and tab-separated rows as other
spreadsheets. UTF-8 (with or without BOM) and UTF-16 exports are supported.
`ss:Index` positions and the table's `ss:LeftCell` / `ss:TopCell` origin are
combined before checking row/column bounds. Sparse columns preserve their gaps,
including gaps after horizontally merged cells. Empty rows and sheets are omitted, rather than allocating all rows
declared by `ExpandedRowCount`. String cells retain leading zeros and long
identifiers; boolean cells become `TRUE` / `FALSE`. Number and DateTime values
remain textual, without float rounding or applying Excel display formats.

Only cached formula values are indexed. A formula without cached `Data`, or a
cached Excel error, contributes an empty cell. Octop does not calculate formulas,
follow links, or execute macros. Rich-text cell runs are flattened to plain text.
The uploaded original remains unchanged.

Extraction is limited to 16 MiB of XML, 500,000 XML elements, a nesting depth of
64, and Excel 2003's 65,536 rows / 256 columns. Invalid, overlapping or out-of-range
row and column indices fail extraction rather than silently shifting values.
DTD declarations are rejected, including external DTDs. Other XML vocabularies
and HTML disguised as `.xls` are not accepted by this parser. The normal upload
size setting still applies; the XML extraction limit is an additional bound.

This is plain-text extraction for preview and retrieval, not a full workbook
renderer or schema validator. Formatting, charts and Excel display styles are
not reproduced; merged ranges are not fully validated or expanded vertically.
The `.xml` extension is not added to the accepted upload types.
