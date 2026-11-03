from __future__ import annotations

import sys
from collections.abc import Callable, Sequence
from typing import Any, cast


def _ask(kind: str, **kwargs: Any) -> Any:
    """Indirection point for tests; dispatches to the matching questionary call.

    ``unsafe_ask`` lets Ctrl-C reach ``_guard``. Plain ``ask`` swallows it and
    returns ``None``, which callers would read as an empty answer.
    """
    import questionary

    return getattr(questionary, kind)(**kwargs).unsafe_ask()


def _guard[T](callable_: Callable[[], T]) -> T:
    try:
        return callable_()
    except KeyboardInterrupt:
        print("cancelled", file=sys.stderr)
        sys.exit(130)


def select(message: str, *, choices: Sequence[str], default: str | None = None) -> str:
    return _guard(
        lambda: cast(str, _ask("select", message=message, choices=list(choices), default=default))
    )


def checkbox(message: str, *, choices: Sequence[str], defaults: Sequence[str] = ()) -> list[str]:
    payload_choices = [{"name": c, "checked": c in defaults} for c in choices]
    return _guard(
        lambda: cast(list[str], _ask("checkbox", message=message, choices=payload_choices))
    )


def text(message: str, *, default: str = "") -> str:
    return _guard(lambda: cast(str, _ask("text", message=message, default=default)))


def password(message: str) -> str:
    return _guard(lambda: cast(str, _ask("password", message=message)))


def confirm(message: str, *, default: bool = False) -> bool:
    return _guard(lambda: cast(bool, _ask("confirm", message=message, default=default)))


def editor(message: str, *, default: str = "") -> str:
    return _guard(lambda: cast(str, _ask("text", message=message, default=default, multiline=True)))
