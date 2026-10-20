"""Exception groups narrow enough for pylint ``broad-except``.

``Exception`` and ``BaseException`` are not included. Callers that must
roll back on any failure use ``try`` / ``finally`` instead of a broad
``except``.
"""

from __future__ import annotations

import json
import sqlite3

try:
    import psycopg
except ImportError:
    _DB_ERRORS: tuple[type[BaseException], ...] = (sqlite3.Error,)
else:
    _DB_ERRORS = (sqlite3.Error, psycopg.Error)

# Query, filesystem, timeout, and operational runtime failures.
DRIVER_ERRORS: tuple[type[BaseException], ...] = (*_DB_ERRORS, OSError, TimeoutError, RuntimeError)

# Bad payloads on top of driver failures. Programming errors such as
# AssertionError are still absent.
PAYLOAD_ERRORS: tuple[type[BaseException], ...] = (
    ValueError,
    KeyError,
    IndexError,
    LookupError,
    TypeError,
    AttributeError,
    UnicodeError,
    ArithmeticError,
    json.JSONDecodeError,
)

# Boundaries whose contract is to report a failure instead of crashing.
REPORTABLE_ERRORS: tuple[type[BaseException], ...] = (*DRIVER_ERRORS, *PAYLOAD_ERRORS)


def _optional_error(module: str, name: str) -> tuple[type[BaseException], ...]:
    try:
        imported = __import__(module, fromlist=[name])
    except ImportError:
        return ()
    candidate = getattr(imported, name, None)
    if isinstance(candidate, type) and issubclass(candidate, BaseException):
        return (candidate,)
    return ()


# Optional vector clients. Absent when the extra is not installed.
VECTOR_ERRORS: tuple[type[BaseException], ...] = (
    *DRIVER_ERRORS,
    ValueError,
    KeyError,
    IndexError,
    LookupError,
    UnicodeError,
    json.JSONDecodeError,
    *_optional_error("chromadb.errors", "ChromaError"),
    *_optional_error("qdrant_client.http.exceptions", "UnexpectedResponse"),
    *_optional_error("qdrant_client.http.exceptions", "ResponseHandlingException"),
)
