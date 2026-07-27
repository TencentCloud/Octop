from __future__ import annotations

from octop.infra.db.pool import qmark_to_pyformat


def test_qmark_to_pyformat_replaces_placeholders():
    assert qmark_to_pyformat("SELECT * FROM t WHERE a = ? AND b = ?") == (
        "SELECT * FROM t WHERE a = %s AND b = %s"
    )


def test_qmark_to_pyformat_leaves_percent_alone():
    assert qmark_to_pyformat("SELECT %s") == "SELECT %s"
