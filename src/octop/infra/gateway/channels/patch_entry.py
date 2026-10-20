"""Serialized Telegram channel patch entry point.

Several local patches wrap the same gateway classes. Installing them from one
place keeps the wrap order deterministic and makes double-install a no-op.
"""

from __future__ import annotations

_installed = False


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
