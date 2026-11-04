from octop.infra.office_preview.formats import (
    is_convertible_filename,
    is_zip_container,
    trusted_input_name,
)


def test_convertible_office_whitelist() -> None:
    assert is_convertible_filename("report.docx")
    assert is_convertible_filename("/tmp/a.PPTX")
    assert is_convertible_filename("legacy.doc")
    assert not is_convertible_filename("book.xlsm")
    assert not is_convertible_filename("notes.csv")
    assert not is_convertible_filename("file.pdf")


def test_trusted_snapshot_name_uses_whitelist_only() -> None:
    assert trusted_input_name("../../secret.docx") == "input.docx"
    assert trusted_input_name("evil.exe") == "input.bin"


def test_zip_containers() -> None:
    assert is_zip_container("a.docx")
    assert not is_zip_container("a.doc")
