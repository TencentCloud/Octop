"""Slash command catalog — metadata for handlers, API, and dashboard UI."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from octop.i18n import tr
from octop.infra.utils.locale import normalize_locale

Origin = Literal["all", "im", "ui", "cli"]
ClientAction = Literal["none", "new_chat", "cancel_stream", "switch_agent"]
Category = Literal["core", "session", "media", "system", "debug"]

# Display order for /help and dashboard grouping.
CATEGORY_ORDER: tuple[Category, ...] = ("core", "session", "media", "system", "debug")


@dataclass(frozen=True)
class SlashCommandSpec:
    """Public metadata for one slash command (primary name)."""

    name: str
    aliases: tuple[str, ...] = ()
    usage: str = ""
    icon: str = "Zap"
    tone: str = "blue"
    category: Category = "system"
    origins: frozenset[Origin] = frozenset({"all"})
    client_action: ClientAction = "none"
    hidden: bool = False

    @property
    def command(self) -> str:
        return f"/{self.name}"

    @property
    def label_en(self) -> str:
        return tr(f"slash.catalog.{self.name}.label", "en")

    @property
    def label_zh(self) -> str:
        return tr(f"slash.catalog.{self.name}.label", "zh")

    @property
    def description_en(self) -> str:
        return tr(f"slash.catalog.{self.name}.description", "en")

    @property
    def description_zh(self) -> str:
        return tr(f"slash.catalog.{self.name}.description", "zh")

    def visible_in(self, origin: str) -> bool:
        if self.hidden:
            return False
        if "all" in self.origins:
            return True
        return origin in self.origins

    def description_for(self, locale: str) -> str:
        return tr(f"slash.catalog.{self.name}.description", normalize_locale(locale))

    def label_for(self, locale: str) -> str:
        return tr(f"slash.catalog.{self.name}.label", normalize_locale(locale))


CATALOG: tuple[SlashCommandSpec, ...] = (
    SlashCommandSpec(
        name="help",
        usage="/help",
        icon="CircleHelp",
        tone="blue",
        category="system",
    ),
    SlashCommandSpec(
        name="status",
        usage="/status",
        icon="Activity",
        tone="blue",
        category="core",
    ),
    SlashCommandSpec(
        name="model",
        aliases=("models",),
        usage="/model [provider:model | reset]",
        icon="Cpu",
        tone="violet",
        category="core",
    ),
    SlashCommandSpec(
        name="new",
        aliases=("clear",),
        usage="/new [title]",
        icon="RefreshCw",
        tone="emerald",
        category="core",
        client_action="new_chat",
    ),
    SlashCommandSpec(
        name="compact",
        usage="/compact",
        icon="Archive",
        tone="violet",
        category="core",
    ),
    SlashCommandSpec(
        name="stop",
        aliases=("cancel",),
        usage="/stop",
        icon="Square",
        tone="rose",
        category="core",
        origins=frozenset({"all"}),
        client_action="cancel_stream",
    ),
    SlashCommandSpec(
        name="history",
        usage="/history",
        icon="BarChart3",
        tone="blue",
        category="core",
    ),
    SlashCommandSpec(
        name="token",
        usage="/token",
        icon="Coins",
        tone="orange",
        category="core",
    ),
    SlashCommandSpec(
        name="list",
        aliases=("topics", "sessions"),
        usage="/list",
        icon="List",
        tone="amber",
        category="session",
    ),
    SlashCommandSpec(
        name="switch",
        usage="/switch <short_id>",
        icon="ArrowLeftRight",
        tone="amber",
        category="session",
    ),
    SlashCommandSpec(
        name="resume",
        usage="/resume [short_id]",
        icon="Undo2",
        tone="amber",
        category="session",
        origins=frozenset({"im", "cli", "all"}),
    ),
    SlashCommandSpec(
        name="approve",
        usage="/approve [pending_id]",
        icon="CheckCircle",
        tone="green",
        category="session",
        origins=frozenset({"im", "cli"}),
    ),
    SlashCommandSpec(
        name="reject",
        usage="/reject [reason]",
        icon="XCircle",
        tone="rose",
        category="session",
        origins=frozenset({"im", "cli"}),
    ),
    SlashCommandSpec(
        name="pending",
        usage="/pending",
        icon="ShieldAlert",
        tone="amber",
        category="session",
        origins=frozenset({"im", "cli"}),
    ),
    SlashCommandSpec(
        name="answer",
        usage="/answer [pending_id] <answer>",
        icon="MessageCircleQuestion",
        tone="blue",
        category="session",
        origins=frozenset({"im", "cli"}),
    ),
    SlashCommandSpec(
        name="title",
        usage="/title <text>",
        icon="Type",
        tone="slate",
        category="session",
    ),
    SlashCommandSpec(
        name="delete",
        usage="/delete <short_id>",
        icon="Trash2",
        tone="rose",
        category="session",
    ),
    SlashCommandSpec(
        name="pin",
        usage="/pin",
        icon="Pin",
        tone="amber",
        category="session",
    ),
    SlashCommandSpec(
        name="unpin",
        usage="/unpin",
        icon="PinOff",
        tone="slate",
        category="session",
        hidden=True,
    ),
    SlashCommandSpec(
        name="cron",
        usage="/cron [list]",
        icon="Clock",
        tone="slate",
        category="system",
        origins=frozenset({"ui", "cli"}),
    ),
    SlashCommandSpec(
        name="agent",
        usage="/agent list | switch <name>",
        icon="Bot",
        tone="violet",
        category="system",
        origins=frozenset({"ui", "cli"}),
        client_action="switch_agent",
    ),
    SlashCommandSpec(
        name="skills",
        usage="/skills [list]",
        icon="Sparkles",
        tone="amber",
        category="system",
        origins=frozenset({"ui", "cli"}),
    ),
    SlashCommandSpec(
        name="connectors",
        usage="/connectors [list]",
        icon="Plug",
        tone="emerald",
        category="system",
        origins=frozenset({"ui", "cli"}),
    ),
    SlashCommandSpec(
        name="exit",
        aliases=("quit",),
        usage="/exit",
        icon="LogOut",
        tone="slate",
        category="system",
        origins=frozenset({"cli"}),
        hidden=True,
    ),
)

_CATALOG_BY_NAME: dict[str, SlashCommandSpec] = {}
for _spec in CATALOG:
    _CATALOG_BY_NAME[_spec.name] = _spec
    for _alias in _spec.aliases:
        _CATALOG_BY_NAME[_alias] = _spec


def spec_for(name: str) -> SlashCommandSpec | None:
    return _CATALOG_BY_NAME.get(name.lower())


def list_specs(*, origin: str = "all") -> list[SlashCommandSpec]:
    """Return primary specs (no alias duplicates) visible for *origin*."""
    seen: set[str] = set()
    out: list[SlashCommandSpec] = []
    for spec in CATALOG:
        if spec.name in seen:
            continue
        if not spec.visible_in(origin):
            continue
        seen.add(spec.name)
        out.append(spec)
    return out


def category_label(category: Category, locale: str) -> str:
    return tr(f"slash.catalog.categories.{category}", normalize_locale(locale))


def group_specs_by_category(
    specs: list[SlashCommandSpec],
) -> list[tuple[Category, list[SlashCommandSpec]]]:
    """Group *specs* by category in ``CATEGORY_ORDER``."""
    buckets: dict[Category, list[SlashCommandSpec]] = {}
    for spec in specs:
        buckets.setdefault(spec.category, []).append(spec)
    return [(cat, buckets[cat]) for cat in CATEGORY_ORDER if cat in buckets]


def channel_origin(channel_type: str) -> str:
    """Map gateway channel type to slash command *origin* filter."""
    return "ui" if channel_type == "dashboard" else channel_type
