"""Connector catalog — bundled presets loaded from ``catalog.json``."""

from __future__ import annotations

import json
from dataclasses import dataclass
from importlib import resources
from typing import Any, Literal, get_args

from octop.infra.utils.locale import normalize_locale

AuthKind = Literal[
    "personal_token",
    "oauth2",
    "auth_code",
    "api_key",
    "imap_app_password",
    "session_cookie",
    "api_credentials",
    "custom_fields",
]
CredentialFieldType = Literal["text", "password", "url", "tags"]
RemoteTransport = Literal["raw_http", "streamable_http", "sse"]
McpMode = Literal["remote", "gateway", "internal"]
ConnectorCategory = Literal[
    "office",
    "knowledge",
    "travel",
    "productivity",
    "media",
    "professional",
    "self_hosted",
]
ConnectorPhase = Literal["available", "coming_soon"]

_CATALOG_RESOURCE = "catalog.json"


@dataclass(frozen=True)
class LocalizedText:
    """User-facing catalog copy with English fallback and Chinese variant."""

    en: str
    zh: str

    def resolve(self, locale: str = "en") -> str:
        return self.zh if normalize_locale(locale) == "zh" else self.en


@dataclass(frozen=True)
class ConnectorCredentialField:
    key: str
    label: LocalizedText
    field_type: CredentialFieldType = "text"
    required: bool = True
    placeholder: LocalizedText | None = None
    help: LocalizedText | None = None
    secret: bool = False


@dataclass(frozen=True)
class ConnectorCatalogEntry:
    kind: str
    name: LocalizedText
    description: LocalizedText
    auth_kind: AuthKind
    doc_url: str
    icon: str
    color: str
    phase: ConnectorPhase
    # remote: harness talks to the vendor URL.
    # gateway: in-process Python adapter; harness config is a name-only placeholder.
    # internal: Octop-hosted HTTP MCP at /api/internal/mcp; harness loads via HTTP.
    mcp_mode: McpMode
    category: ConnectorCategory
    quick_auth_url: str | None = None
    login_url: str | None = None
    guide_url: str | None = None
    manual_url: str | None = None
    auth_hint: LocalizedText | None = None
    # Optional allowlist of tool names exposed to the LLM.
    # None means no restriction (all tools from the MCP server are available).
    allowed_tools: tuple[str, ...] | None = None
    # Catalog-driven remote MCP OAuth (Notion / Ardot / Linear…):
    # when auth_kind=oauth2 + mcp_mode=remote/internal and issuer + mcp_url are set,
    # Octop uses DCR + PKCE against oauth_issuer and talks to mcp_url.
    oauth_issuer: str | None = None
    mcp_url: str | None = None
    oauth_resource: str | None = None
    oauth_scopes: str | None = None
    mcp_user_agent: str | None = None
    credential_fields: tuple[ConnectorCredentialField, ...] = ()
    remote_transport: RemoteTransport = "raw_http"


def is_inprocess_gateway(entry: ConnectorCatalogEntry) -> bool:
    """Harness injects Python adapter tools; config is a name-only placeholder."""
    return entry.mcp_mode == "gateway"


def uses_internal_http_mcp(entry: ConnectorCatalogEntry) -> bool:
    """Harness loads Octop-hosted HTTP MCP at ``/api/internal/mcp``."""
    return entry.mcp_mode == "internal"


def is_mcp_oauth_remote(entry: ConnectorCatalogEntry) -> bool:
    """True when this catalog entry is a dynamic-OAuth MCP connector (remote or internal HTTP)."""
    return (
        entry.auth_kind == "oauth2"
        and entry.mcp_mode in {"remote", "internal"}
        and bool(entry.oauth_issuer)
        and bool(entry.mcp_url)
    )


def mcp_oauth_remote_kinds() -> frozenset[str]:
    return frozenset(e.kind for e in _CATALOG if is_mcp_oauth_remote(e))


def get_mcp_oauth_remote(kind: str) -> ConnectorCatalogEntry | None:
    entry = get_catalog_entry(kind)
    if entry is None or not is_mcp_oauth_remote(entry):
        return None
    return entry


def _require_str(raw: object, field: str) -> str:
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError(f"catalog field {field!r} must be a non-empty string")
    return raw


def _optional_str(raw: object, field: str) -> str | None:
    if raw is None:
        return None
    return _require_str(raw, field)


def _require_bool(raw: object, field: str, default: bool) -> bool:
    if raw is None:
        return default
    if not isinstance(raw, bool):
        raise ValueError(f"catalog field {field!r} must be a boolean")
    return raw


def _localized(raw: object, field: str) -> LocalizedText:
    if isinstance(raw, str):
        text = _require_str(raw, field)
        return LocalizedText(en=text, zh=text)
    if isinstance(raw, dict):
        en = _require_str(raw.get("en"), f"{field}.en")
        zh = _require_str(raw.get("zh"), f"{field}.zh")
        return LocalizedText(en=en, zh=zh)
    raise ValueError(f"catalog field {field!r} must be a string or {{en, zh}}")


def _optional_localized(raw: object, field: str) -> LocalizedText | None:
    if raw is None:
        return None
    return _localized(raw, field)


def _literal[T](raw: object, field: str, allowed: tuple[T, ...]) -> T:
    if raw not in allowed:
        raise ValueError(f"catalog field {field!r} must be one of {list(allowed)}")
    return raw


def _optional_str_tuple(raw: object, field: str) -> tuple[str, ...] | None:
    if raw is None:
        return None
    if not isinstance(raw, list) or not all(isinstance(item, str) and item for item in raw):
        raise ValueError(f"catalog field {field!r} must be a list of non-empty strings")
    return tuple(item for item in raw if isinstance(item, str))


def _parse_credential_field(raw: object, kind: str, index: int) -> ConnectorCredentialField:
    prefix = f"{kind}.credential_fields[{index}]"
    if not isinstance(raw, dict):
        raise ValueError(f"catalog field {prefix} must be an object")
    return ConnectorCredentialField(
        key=_require_str(raw.get("key"), f"{prefix}.key"),
        label=_localized(raw.get("label"), f"{prefix}.label"),
        field_type=_literal(
            raw.get("field_type", "text"),
            f"{prefix}.field_type",
            get_args(CredentialFieldType),
        ),
        required=_require_bool(raw.get("required"), f"{prefix}.required", True),
        placeholder=_optional_localized(raw.get("placeholder"), f"{prefix}.placeholder"),
        help=_optional_localized(raw.get("help"), f"{prefix}.help"),
        secret=_require_bool(raw.get("secret"), f"{prefix}.secret", False),
    )


def _parse_entry(raw: object) -> ConnectorCatalogEntry:
    if not isinstance(raw, dict):
        raise ValueError("catalog connector entry must be an object")
    kind = _require_str(raw.get("kind"), "kind")
    fields_raw = raw.get("credential_fields") or []
    if not isinstance(fields_raw, list):
        raise ValueError(f"catalog field {kind}.credential_fields must be a list")
    return ConnectorCatalogEntry(
        kind=kind,
        name=_localized(raw.get("name"), f"{kind}.name"),
        description=_localized(raw.get("description"), f"{kind}.description"),
        auth_kind=_literal(raw.get("auth_kind"), f"{kind}.auth_kind", get_args(AuthKind)),
        doc_url=_require_str(raw.get("doc_url"), f"{kind}.doc_url"),
        icon=_require_str(raw.get("icon"), f"{kind}.icon"),
        color=_require_str(raw.get("color"), f"{kind}.color"),
        phase=_literal(raw.get("phase"), f"{kind}.phase", get_args(ConnectorPhase)),
        mcp_mode=_literal(raw.get("mcp_mode"), f"{kind}.mcp_mode", get_args(McpMode)),
        category=_literal(raw.get("category"), f"{kind}.category", get_args(ConnectorCategory)),
        quick_auth_url=_optional_str(raw.get("quick_auth_url"), f"{kind}.quick_auth_url"),
        login_url=_optional_str(raw.get("login_url"), f"{kind}.login_url"),
        guide_url=_optional_str(raw.get("guide_url"), f"{kind}.guide_url"),
        manual_url=_optional_str(raw.get("manual_url"), f"{kind}.manual_url"),
        auth_hint=_optional_localized(raw.get("auth_hint"), f"{kind}.auth_hint"),
        allowed_tools=_optional_str_tuple(raw.get("allowed_tools"), f"{kind}.allowed_tools"),
        oauth_issuer=_optional_str(raw.get("oauth_issuer"), f"{kind}.oauth_issuer"),
        mcp_url=_optional_str(raw.get("mcp_url"), f"{kind}.mcp_url"),
        oauth_resource=_optional_str(raw.get("oauth_resource"), f"{kind}.oauth_resource"),
        oauth_scopes=_optional_str(raw.get("oauth_scopes"), f"{kind}.oauth_scopes"),
        mcp_user_agent=_optional_str(raw.get("mcp_user_agent"), f"{kind}.mcp_user_agent"),
        credential_fields=tuple(
            _parse_credential_field(item, kind, index) for index, item in enumerate(fields_raw)
        ),
        remote_transport=_literal(
            raw.get("remote_transport", "raw_http"),
            f"{kind}.remote_transport",
            get_args(RemoteTransport),
        ),
    )


def _read_catalog_payload() -> dict[str, Any]:
    raw = (
        resources.files("octop.infra.connectors")
        .joinpath(_CATALOG_RESOURCE)
        .read_text(encoding="utf-8")
    )
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError("catalog.json must be an object")
    return payload


def _load_catalog() -> tuple[ConnectorCatalogEntry, ...]:
    payload = _read_catalog_payload()
    rows = payload.get("connectors")
    if not isinstance(rows, list) or not rows:
        raise ValueError("catalog.json must contain a non-empty connectors array")
    entries = tuple(_parse_entry(row) for row in rows)
    kinds = [entry.kind for entry in entries]
    if len(kinds) != len(set(kinds)):
        raise ValueError("catalog.json has duplicate connector kinds")
    return entries


_CATALOG: tuple[ConnectorCatalogEntry, ...] = _load_catalog()


def list_catalog() -> list[ConnectorCatalogEntry]:
    return list(_CATALOG)


def get_catalog_entry(kind: str) -> ConnectorCatalogEntry | None:
    for entry in _CATALOG:
        if entry.kind == kind:
            return entry
    return None


def _resolve_optional(text: LocalizedText | None, locale: str) -> str | None:
    return None if text is None else text.resolve(locale)


def catalog_entry_to_dict(
    entry: ConnectorCatalogEntry, *, oauth_ready: bool = False, locale: str = "en"
) -> dict[str, object]:
    from octop.infra.connectors.oauth import oauth_mode_for_kind  # noqa: PLC0415

    oauth_mode = oauth_mode_for_kind(entry.kind)
    return {
        "kind": entry.kind,
        "name": entry.name.resolve(locale),
        "description": entry.description.resolve(locale),
        "auth_kind": entry.auth_kind,
        "doc_url": entry.doc_url,
        "icon": entry.icon,
        "color": entry.color,
        "phase": entry.phase,
        "mcp_mode": entry.mcp_mode,
        "category": entry.category,
        "quick_auth_url": entry.quick_auth_url,
        "login_url": entry.login_url,
        "guide_url": entry.guide_url or entry.doc_url,
        "manual_url": entry.manual_url or entry.guide_url or entry.doc_url,
        "auth_hint": _resolve_optional(entry.auth_hint, locale),
        "oauth_mode": oauth_mode,
        "oauth_ready": oauth_ready,
        "credential_fields": [
            {
                "key": field.key,
                "label": field.label.resolve(locale),
                "field_type": field.field_type,
                "required": field.required,
                "placeholder": _resolve_optional(field.placeholder, locale),
                "help": _resolve_optional(field.help, locale),
                "secret": field.secret,
            }
            for field in entry.credential_fields
        ],
        "supports_quick_auth": entry.phase == "available" and entry.auth_kind != "api_credentials",
    }
