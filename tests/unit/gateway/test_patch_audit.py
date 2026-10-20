"""Audit: every monkeypatch wrapper must preserve async/sync semantics.

Wrapping a gateway ``async def`` with a plain ``def`` makes callers await a
coroutine object instead of the real return value. That class of bug silently
killed all Telegram message handling once already. This test discovers every
wrapper installed by the local patch layer (via ``__wrapped_base__``) and
asserts its coroutine-ness matches the method it replaced.
"""

import inspect

import octop_gateway.channels.telegram.format_html as format_html
from octop_gateway.channels.telegram.channel import TelegramChannel
from octop_gateway.channels.telegram.interaction import Interactions

import octop.infra.gateway.gateway  # noqa: F401  installs every patch


def _iter_wrappers():
    """Yield (label, wrapper, base) for every installed wrapper."""
    for cls in (TelegramChannel, Interactions):
        for name, attr in vars(cls).items():
            base = getattr(attr, "__wrapped_base__", None)
            if base is not None:
                yield f"{cls.__name__}.{name}", attr, base
    func = format_html.markdown_to_telegram_html
    base = getattr(func, "__wrapped_base__", None)
    if base is not None:
        yield "format_html.markdown_to_telegram_html", func, base


def test_wrappers_preserve_async_semantics():
    found = list(_iter_wrappers())
    assert found, "no wrappers discovered - patch layer did not install"
    for label, wrapper, base in found:
        wrapper_async = inspect.iscoroutinefunction(wrapper)
        base_async = inspect.iscoroutinefunction(base)
        assert wrapper_async == base_async, (
            f"{label}: wrapper async={wrapper_async} but base async={base_async}"
        )


def test_extract_message_is_async() -> None:
    """Regression: a sync wrapper here caused "coroutine never awaited".

    It broke all inbound Telegram handling (no reply, no typing, no reaction).
    """
    assert inspect.iscoroutinefunction(TelegramChannel._extract_message)
    assert inspect.iscoroutinefunction(TelegramChannel._send_text)
    assert inspect.iscoroutinefunction(TelegramChannel._handle_callback)
    assert inspect.iscoroutinefunction(Interactions.invoke)
    assert not inspect.iscoroutinefunction(TelegramChannel.parse_inbound), (
        "parse_inbound is sync upstream"
    )
    assert not inspect.iscoroutinefunction(Interactions.register), "register is sync upstream"


def _accepts_all_of(wrapper, base) -> bool:
    """包装层必须能接住被替换方法的全部形参（或用 *args/**kwargs 透传）。"""
    w_params = inspect.signature(wrapper).parameters.values()
    kinds = {p.kind for p in w_params}
    if {inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD} <= kinds:
        return True
    w_names = {p.name for p in inspect.signature(wrapper).parameters.values()}
    b_params = inspect.signature(base).parameters.values()
    return all(p.name in w_names or p.kind in (p.VAR_POSITIONAL, p.VAR_KEYWORD) for p in b_params)


def test_wrappers_accept_base_signature():
    for label, wrapper, base in _iter_wrappers():
        assert _accepts_all_of(wrapper, base), (
            f"{label}: wrapper{inspect.signature(wrapper)} cannot accept base{inspect.signature(base)}"
        )


def test_signature_check_detects_dropped_parameter():
    def base(self, token, user, chat, topic): ...

    def narrower(self, token, user, chat): ...

    def passthrough(self, *args, **kwargs): ...

    assert not _accepts_all_of(narrower, base)
    assert _accepts_all_of(passthrough, base)


def test_all_patch_targets_are_wrapped():
    from octop.infra.gateway.channels import patch_entry

    assert patch_entry.verify() == []


def test_verify_reports_unwrapped_and_missing_targets(monkeypatch):
    from octop.infra.gateway.channels import patch_entry

    monkeypatch.setattr(
        patch_entry,
        "_TARGETS",
        (
            ("octop_gateway.channels.telegram.channel", "TelegramChannel", "_start"),
            ("octop_gateway.channels.telegram.channel", "TelegramChannel", "no_such_method"),
        ),
    )
    problems = patch_entry.verify()
    assert any("_start (not wrapped)" in item for item in problems)
    assert any("no_such_method (missing)" in item for item in problems)
