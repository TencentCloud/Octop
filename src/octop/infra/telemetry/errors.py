"""``error.type`` values for metric attributes."""

from __future__ import annotations

import enum

OTHER = "_OTHER"


def exception_type(exc: BaseException | None) -> str:
    """Canonical exception name: ``module.QualName``, bare for builtins; ``""`` for no error."""
    if exc is None:
        return ""
    cls = type(exc)
    name = getattr(cls, "__qualname__", "") or getattr(cls, "__name__", "")
    if not name:
        return OTHER
    module = getattr(cls, "__module__", "") or ""
    return name if module in ("", "builtins") else f"{module}.{name}"


def error_code(exc: BaseException | None) -> str:
    """Octop ``ErrorCode`` value (``TOKEN_QUOTA_EXCEEDED``, …) carried by *exc*, else ``""``.

    Duck-typed on an enum ``code`` attribute so this leaf module does not import
    ``infra.errors``.
    """
    code = getattr(exc, "code", None)
    if isinstance(code, enum.Enum) and isinstance(code.value, str):
        return code.value
    return ""
