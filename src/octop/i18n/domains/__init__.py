"""Per-namespace i18n helpers (each maps to a top-level JSON key)."""

from octop.i18n.domains.agents import (
    MODEL_REF_UNAVAILABLE,
    NO_MODELS_CONFIGURED,
    agent_error_message,
    agent_state_label,
    classify_agent_start_error_message,
    format_agent_start_error,
)
from octop.i18n.domains.attachment import (
    attachment_empty_image,
    attachment_empty_message,
    attachment_image_unavailable,
    attachment_path_hint,
)
from octop.i18n.domains.channel import channel_tool_hint_end, channel_tool_hint_start
from octop.i18n.domains.errors import error_message
from octop.i18n.domains.slash import field_label, localized_rows
from octop.i18n.domains.slash import tr as slash_tr
from octop.i18n.domains.stream import (
    classify_stream_error_message,
    format_stream_error,
    stream_error_message,
)
from octop.i18n.domains.tools import (
    HITL_TOOL_EXCLUDE,
    HitlToolCatalogEntry,
    all_tool_labels,
    hitl_tool_catalog,
    tool_display_name,
)

__all__ = [
    "MODEL_REF_UNAVAILABLE",
    "NO_MODELS_CONFIGURED",
    "agent_error_message",
    "agent_state_label",
    "attachment_empty_image",
    "attachment_empty_message",
    "attachment_image_unavailable",
    "attachment_path_hint",
    "classify_agent_start_error_message",
    "classify_stream_error_message",
    "format_agent_start_error",
    "format_stream_error",
    "HITL_TOOL_EXCLUDE",
    "HitlToolCatalogEntry",
    "all_tool_labels",
    "hitl_tool_catalog",
    "channel_tool_hint_end",
    "channel_tool_hint_start",
    "error_message",
    "field_label",
    "localized_rows",
    "slash_tr",
    "stream_error_message",
    "tool_display_name",
]
