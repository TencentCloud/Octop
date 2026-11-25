"""``error.type`` values for metric attributes."""

from __future__ import annotations

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
