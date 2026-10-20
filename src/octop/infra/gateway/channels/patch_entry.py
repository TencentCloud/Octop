"""Serialized Telegram channel patch entry point.

Several local patches wrap the same gateway classes. Installing them from one
place keeps the wrap order deterministic and makes double-install a no-op.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_installed = False

# 本地补丁依赖的 gateway 私有入口（模块路径, 类名 | None, 属性名）。
# gateway 升级后改名/移除会让补丁静默失效，install() 末尾据此告警。
_TARGETS: tuple[tuple[str, str | None, str], ...] = (
    ("octop_gateway.channels.telegram.channel", "TelegramChannel", "_send_text"),
    ("octop_gateway.channels.telegram.channel", "TelegramChannel", "_handle_callback"),
    ("octop_gateway.channels.telegram.channel", "TelegramChannel", "_extract_message"),
    ("octop_gateway.channels.telegram.channel", "TelegramChannel", "parse_inbound"),
    ("octop_gateway.channels.telegram.interaction", "Interactions", "invoke"),
    ("octop_gateway.channels.telegram.format_html", None, "markdown_to_telegram_html"),
)


def verify() -> list[str]:
    """Return patch targets that are missing or were not wrapped (empty when healthy)."""
    import importlib

    problems: list[str] = []
    for module_name, class_name, attr in _TARGETS:
        label = f"{module_name}.{class_name + '.' if class_name else ''}{attr}"
        try:
            owner = importlib.import_module(module_name)
            if class_name:
                owner = getattr(owner, class_name)
            target = getattr(owner, attr)
        except (ImportError, AttributeError):
            problems.append(f"{label} (missing)")
            continue
        if getattr(target, "__wrapped_base__", None) is None:
            problems.append(f"{label} (not wrapped)")
    return problems


def install() -> None:
    global _installed
    if _installed:
        return
    from octop.infra.gateway.channels import (
        plain_table_format,
        telegram_button_ux,
        telegram_interaction,
        telegram_reply_quote,
        telegram_table_format,
    )

    telegram_table_format.install()
    plain_table_format.install()
    telegram_button_ux.install()
    telegram_interaction.install()
    telegram_reply_quote.install()
    _installed = True
    problems = verify()
    if problems:
        logger.warning(
            "telegram channel patches inactive after gateway change: %s", ", ".join(problems)
        )
