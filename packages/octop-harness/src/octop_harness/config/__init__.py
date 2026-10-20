"""Configuration objects: ``HarnessAgentConfig``, ``ProviderConfig``, ``ModelConfig``.

Per design doc §3:
    - ``HarnessAgentConfig`` is a frozen dataclass.
    - ``workspace_dir`` is an **absolute** local directory. It serves as both:
        (a) the root used by local-class backends (``local_shell`` /
            ``filesystem``) when the spec doesn't pin its own root; and
        (b) the parent for agent-managed local artifacts (``logs/``,
            ``sessions/`` JSONL, ``checkpoints.sqlite``, bootstrap marker).
      Backend-internal resources (skills, memory md, init templates) live at
      the backend's virtual root ``/`` — which, for local backends, *is*
      ``workspace_dir`` on disk.
    - Validation lives close to construction: missing providers, malformed
      ``default_model`` strings, etc. surface as ``ValueError`` at config time
      rather than at first chat invocation.

Serialization
-------------
``HarnessAgentConfig`` round-trips through JSON via :py:meth:`to_dict` /
:py:meth:`from_dict` and :py:meth:`to_file` / :py:meth:`from_file`. Fields
holding live Python objects (callables, pre-built backend instances,
checkpointers, custom tools / middleware, ``permissions``, ``interrupt_on``,
``response_format``) are silently dropped from the output: configuration
files capture *declarative* settings only. Re-attaching those fields after
load is the caller's responsibility (typically by mutating the ``cfg``
instance before passing it to ``HarnessAgent``).
"""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from dataclasses import InitVar, dataclass, field, fields
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from deepagents import SubAgent

from octop_harness.acp.models import ACPRunnerConfig, default_acp_runners
from octop_harness.decision.config import DecisionConfig

if TYPE_CHECKING:
    # State / runtime types are intentionally erased to ``Any`` to avoid
    # tightly coupling our public API to LangGraph internals.
    ModelSelector = Callable[[dict[str, Any], dict[str, Any]], str | None]
else:
    ModelSelector = Callable  # runtime placeholder; only used for type hints

ProtocolName = Literal["openai", "anthropic", "bedrock"]
InputModality = Literal["text", "image", "audio", "video"]
MediaProviderName = Literal["volcengine", "dashscope", "minimax"]

DEFAULT_CONFIG_FILENAME = "octop-harness.json"

_MEDIA_PROVIDER_DEFAULTS: dict[str, tuple[str, str, str, str]] = {
    "volcengine": (
        "ARK_API_KEY",
        "https://ark.cn-beijing.volces.com/api/v3",
        "doubao-seedream-5-0-lite-260128",
        "doubao-seedance-2-0-mini-260615",
    ),
    "dashscope": (
        "DASHSCOPE_API_KEY",
        "https://dashscope.aliyuncs.com/api/v1",
        "wan2.7-image-pro",
        "wan3.0-video-prime",
    ),
    "minimax": (
        "MINIMAX_API_KEY",
        "https://api.minimax.cn",
        "image-01",
        "MiniMax-H3",
    ),
}


@dataclass
class MediaProviderConfig:
    """One named media-provider instance.

    The instance ``id`` is a routing key, while ``provider`` selects the
    built-in protocol adapter. Multiple instances may therefore use the same
    adapter with different credentials, endpoints, or model versions.
    """

    id: str
    provider: MediaProviderName = "volcengine"
    api_key: str = field(default="", repr=False, compare=False)
    api_key_env: str = ""
    base_url: str = ""
    image_model: str = ""
    video_model: str = ""
    enabled: bool = True
    image_enabled: bool = True
    video_enabled: bool = True
    request_timeout_seconds: float = 120.0
    video_poll_interval_seconds: float = 5.0
    video_timeout_seconds: float = 600.0

    def __post_init__(self) -> None:
        self.id = self.id.strip()
        if not self.id:
            raise ValueError("MediaProviderConfig.id is required")
        if self.provider not in _MEDIA_PROVIDER_DEFAULTS:
            raise ValueError(f"Unsupported media generation provider: {self.provider!r}")
        defaults = _MEDIA_PROVIDER_DEFAULTS[self.provider]
        if not self.api_key_env:
            self.api_key_env = defaults[0]
        if not self.base_url:
            self.base_url = defaults[1]
        if not self.image_model:
            self.image_model = defaults[2]
        if not self.video_model:
            self.video_model = defaults[3]
        if not self.base_url.startswith(("https://", "http://")):
            raise ValueError(f"MediaProviderConfig({self.id}).base_url must be an HTTP(S) URL")
        if self.enabled and not self.image_enabled and not self.video_enabled:
            raise ValueError(f"MediaProviderConfig({self.id}) must enable image or video generation")
        if self.request_timeout_seconds <= 0:
            raise ValueError(f"MediaProviderConfig({self.id}).request_timeout_seconds must be positive")
        if self.video_poll_interval_seconds <= 0:
            raise ValueError(f"MediaProviderConfig({self.id}).video_poll_interval_seconds must be positive")
        if self.video_timeout_seconds <= 0:
            raise ValueError(f"MediaProviderConfig({self.id}).video_timeout_seconds must be positive")

    def resolve_api_key(self) -> str:
        """Return the injected credential, falling back to ``api_key_env``."""
        import os

        key = self.api_key or os.environ.get(self.api_key_env, "")
        if not key:
            raise ValueError(f"Media generation requires api_key or environment variable {self.api_key_env!r}")
        return key

    def has_api_key(self) -> bool:
        """Return whether a credential is available without exposing it."""
        import os

        return bool(self.api_key or os.environ.get(self.api_key_env, ""))

    def to_dict(self) -> dict[str, Any]:
        """Return declarative provider settings without runtime credentials."""
        return {
            "id": self.id,
            "provider": self.provider,
            "api_key_env": self.api_key_env,
            "base_url": self.base_url,
            "image_model": self.image_model,
            "video_model": self.video_model,
            "enabled": self.enabled,
            "image_enabled": self.image_enabled,
            "video_enabled": self.video_enabled,
            "request_timeout_seconds": self.request_timeout_seconds,
            "video_poll_interval_seconds": self.video_poll_interval_seconds,
            "video_timeout_seconds": self.video_timeout_seconds,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MediaProviderConfig:
        """Build from serialized settings while tolerating future keys."""
        valid = {item.name for item in fields(cls)}
        return cls(**{key: value for key, value in data.items() if key in valid})


@dataclass
class MediaGenerationConfig:
    """Configuration for the built-in image and video generation tools.

    Built-in adapters cover Volcengine Ark, Alibaba Cloud Model Studio and
    MiniMax. Model identifiers remain explicit so deployments can upgrade
    versions without changing octop-harness.
    """

    provider: MediaProviderName = "volcengine"
    api_key: str = field(default="", repr=False, compare=False)
    api_key_env: str = "ARK_API_KEY"
    base_url: str = "https://ark.cn-beijing.volces.com/api/v3"
    image_model: str = "doubao-seedream-5-0-lite-260128"
    video_model: str = "doubao-seedance-2-0-mini-260615"
    image_enabled: bool = True
    video_enabled: bool = True
    output_dir: str = "generated"
    defer_tools: bool = True
    request_timeout_seconds: float = 120.0
    video_poll_interval_seconds: float = 5.0
    video_timeout_seconds: float = 600.0
    providers: list[MediaProviderConfig] = field(default_factory=list)
    default_image_provider: str | None = None
    default_video_provider: str | None = None

    def __post_init__(self) -> None:
        if self.provider not in _MEDIA_PROVIDER_DEFAULTS:
            raise ValueError(f"Unsupported media generation provider: {self.provider!r}")
        volcengine_defaults = _MEDIA_PROVIDER_DEFAULTS["volcengine"]
        provider_defaults = _MEDIA_PROVIDER_DEFAULTS[self.provider]
        if self.provider != "volcengine":
            if self.api_key_env == volcengine_defaults[0]:
                self.api_key_env = provider_defaults[0]
            if self.base_url == volcengine_defaults[1]:
                self.base_url = provider_defaults[1]
            if self.image_model == volcengine_defaults[2]:
                self.image_model = provider_defaults[2]
            if self.video_model == volcengine_defaults[3]:
                self.video_model = provider_defaults[3]
        if not self.api_key_env:
            raise ValueError("MediaGenerationConfig.api_key_env is required")
        if not self.base_url.startswith(("https://", "http://")):
            raise ValueError("MediaGenerationConfig.base_url must be an HTTP(S) URL")
        if not self.providers and not self.image_enabled and not self.video_enabled:
            raise ValueError("MediaGenerationConfig must enable image or video generation")
        if not self.providers and self.image_enabled and not self.image_model:
            raise ValueError("MediaGenerationConfig.image_model is required")
        if not self.providers and self.video_enabled and not self.video_model:
            raise ValueError("MediaGenerationConfig.video_model is required")
        output = Path(self.output_dir)
        if output.is_absolute() or ".." in output.parts or not self.output_dir.strip("/."):
            raise ValueError("MediaGenerationConfig.output_dir must stay inside the workspace")
        if self.request_timeout_seconds <= 0:
            raise ValueError("MediaGenerationConfig.request_timeout_seconds must be positive")
        if self.video_poll_interval_seconds <= 0:
            raise ValueError("MediaGenerationConfig.video_poll_interval_seconds must be positive")
        if self.video_timeout_seconds <= 0:
            raise ValueError("MediaGenerationConfig.video_timeout_seconds must be positive")
        self._validate_provider_routes()

    def _validate_provider_routes(self) -> None:
        if not self.providers:
            return
        provider_ids = [item.id for item in self.providers]
        if len(provider_ids) != len(set(provider_ids)):
            raise ValueError("MediaGenerationConfig.providers must use unique ids")
        enabled = [item for item in self.providers if item.enabled]
        if not enabled:
            raise ValueError("MediaGenerationConfig.providers must enable at least one provider")
        by_id = {item.id: item for item in enabled}
        for kind, route in (
            ("image", self.default_image_provider),
            ("video", self.default_video_provider),
        ):
            if route is None:
                continue
            provider = by_id.get(route)
            if provider is None:
                raise ValueError(f"Default {kind} provider {route!r} is missing or disabled")
            if not getattr(provider, f"{kind}_enabled"):
                raise ValueError(f"Default {kind} provider {route!r} does not enable {kind} generation")

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-friendly representation without runtime credentials."""
        result: dict[str, Any] = {
            "provider": self.provider,
            "api_key_env": self.api_key_env,
            "base_url": self.base_url,
            "image_model": self.image_model,
            "video_model": self.video_model,
            "image_enabled": self.image_enabled,
            "video_enabled": self.video_enabled,
            "output_dir": self.output_dir,
            "defer_tools": self.defer_tools,
            "request_timeout_seconds": self.request_timeout_seconds,
            "video_poll_interval_seconds": self.video_poll_interval_seconds,
            "video_timeout_seconds": self.video_timeout_seconds,
        }
        if self.providers:
            result["providers"] = [item.to_dict() for item in self.providers]
        if self.default_image_provider is not None:
            result["default_image_provider"] = self.default_image_provider
        if self.default_video_provider is not None:
            result["default_video_provider"] = self.default_video_provider
        return result

    def configured_providers(self) -> list[MediaProviderConfig]:
        """Return named providers, adapting the legacy single-provider fields."""
        if self.providers:
            return list(self.providers)
        return [
            MediaProviderConfig(
                id=self.provider,
                provider=self.provider,
                api_key=self.api_key,
                api_key_env=self.api_key_env,
                base_url=self.base_url,
                image_model=self.image_model,
                video_model=self.video_model,
                image_enabled=self.image_enabled,
                video_enabled=self.video_enabled,
                request_timeout_seconds=self.request_timeout_seconds,
                video_poll_interval_seconds=self.video_poll_interval_seconds,
                video_timeout_seconds=self.video_timeout_seconds,
            )
        ]

    def resolve_api_key(self) -> str:
        """Return the injected credential, falling back to ``api_key_env``."""
        import os

        key = self.api_key or os.environ.get(self.api_key_env, "")
        if not key:
            raise ValueError(f"Media generation requires api_key or environment variable {self.api_key_env!r}")
        return key

    def has_api_key(self) -> bool:
        """Return whether a credential is currently available without exposing it."""
        return any(item.enabled and item.has_api_key() for item in self.configured_providers())

    def has_image_provider(self) -> bool:
        """Return whether a usable image route is configured."""
        return any(item.enabled and item.image_enabled and item.has_api_key() for item in self.configured_providers())

    def has_video_provider(self) -> bool:
        """Return whether a usable video route is configured."""
        return any(item.enabled and item.video_enabled and item.has_api_key() for item in self.configured_providers())

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MediaGenerationConfig:
        """Build from :meth:`to_dict` output while tolerating future keys."""
        valid = {item.name for item in fields(cls)}
        values = {key: value for key, value in data.items() if key in valid}
        raw_providers = values.get("providers", [])
        if isinstance(raw_providers, list):
            values["providers"] = [
                item if isinstance(item, MediaProviderConfig) else MediaProviderConfig.from_dict(item)
                for item in raw_providers
                if isinstance(item, (dict, MediaProviderConfig))
            ]
        return cls(**values)


@dataclass
class ModelConfig:
    """A single model exposed by a provider.

    Attributes:
        id: Provider-side identifier, e.g. ``"Kimi-K2.5"``.
        name: Optional human-readable label; defaults to ``id``.
        enabled: Disable a model without removing it from configuration.
        input: Modalities the model accepts; used by the multimodal router.
        thinking: Controls extended thinking/reasoning for this model.
            - ``None`` (default): do not pass any thinking parameter to the model,
              model uses its own default behavior.
            - ``True``: explicitly enable thinking (e.g. Anthropic adaptive thinking).
            - ``False``: explicitly disable thinking for models that default to it.
        max_input_tokens: Maximum prompt/input tokens (0 = unknown/delegate to
            the model profile). This is the value used by DeepAgents'
            summarization thresholds.
        context_window: Total input + output context window (0 = unknown). For
            legacy configurations this defaults to ``max_input_tokens``.
        max_output_tokens: Maximum generated/output tokens (0 = unknown). This
            is metadata unless a host explicitly configures ``max_tokens``.
        api_mode: OpenAI-compatible generation API selection. Defaults to
            Chat Completions; set ``"responses"`` to use ``/v1/responses``.
        api_fallback: Optional protocol fallback. ``"chat_completions"`` retries
            a Responses request only when the provider clearly reports that the
            Responses endpoint or model is unsupported. Defaults to ``"none"``.
        native_tool_search: Enable provider-hosted tool search for this model.
            Supported for OpenAI Responses and Anthropic Messages models whose
            provider endpoint implements the corresponding native protocol.
    """

    id: str
    name: str = ""
    enabled: bool = True
    input: list[InputModality] = field(default_factory=lambda: ["text"])
    thinking: bool | None = None
    max_input_tokens: int = 0
    context_window: int = 0
    max_output_tokens: int = 0
    api_mode: Literal["chat_completions", "responses"] = "chat_completions"
    api_fallback: Literal["none", "chat_completions"] = "none"
    native_tool_search: bool = False
    capabilities: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.id:
            raise ValueError("ModelConfig.id must be a non-empty string")
        if not self.name:
            object.__setattr__(self, "name", self.id)
        if not self.input:
            raise ValueError(f"ModelConfig({self.id}).input must list at least one modality")
        if self.max_input_tokens < 0 or self.context_window < 0 or self.max_output_tokens < 0:
            raise ValueError(f"ModelConfig({self.id}) token limits must be non-negative")
        if self.api_mode not in ("chat_completions", "responses"):
            raise ValueError(f"ModelConfig({self.id}).api_mode is invalid: {self.api_mode!r}")
        if self.api_fallback not in ("none", "chat_completions"):
            raise ValueError(f"ModelConfig({self.id}).api_fallback is invalid: {self.api_fallback!r}")
        if self.api_fallback != "none" and self.api_mode != "responses":
            raise ValueError(f"ModelConfig({self.id}).api_fallback requires api_mode='responses'")
        if self.api_fallback != "none" and self.native_tool_search:
            raise ValueError(f"ModelConfig({self.id}).api_fallback is incompatible with native_tool_search")
        if self.max_input_tokens <= 0 < self.context_window:
            object.__setattr__(self, "max_input_tokens", self.context_window)
        if self.context_window <= 0 < self.max_input_tokens:
            object.__setattr__(self, "context_window", self.max_input_tokens)

    @property
    def is_multimodal(self) -> bool:
        """True iff the model accepts any non-text modality."""
        return any(modality != "text" for modality in self.input)

    @property
    def effective_context_window(self) -> int:
        """Return the total context window, falling back for legacy configs."""
        return self.context_window or self.max_input_tokens

    def input_token_budget(self, *, reserved_output_tokens: int = 0) -> int:
        """Return a safe prompt budget after reserving requested output space."""
        prompt_cap = self.max_input_tokens or self.effective_context_window
        total = self.effective_context_window
        if reserved_output_tokens <= 0 or total <= 0:
            return prompt_cap
        safe_total = max(total - reserved_output_tokens, 1)
        return min(prompt_cap, safe_total) if prompt_cap > 0 else safe_total

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-friendly dict representation."""
        return {
            "id": self.id,
            "name": self.name,
            "enabled": self.enabled,
            "input": list(self.input),
            "thinking": self.thinking,
            "max_input_tokens": self.max_input_tokens,
            "context_window": self.effective_context_window,
            "max_output_tokens": self.max_output_tokens,
            "api_mode": self.api_mode,
            "api_fallback": self.api_fallback,
            "native_tool_search": self.native_tool_search,
            "capabilities": list(self.capabilities),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ModelConfig:
        """Reverse of :meth:`to_dict`.

        Legacy entries that only contain one of ``context_window`` or
        ``max_input_tokens`` use that value for both fields.
        """
        max_input = int(data.get("max_input_tokens") or 0)
        context_window = int(data.get("context_window") or 0)
        if max_input <= 0:
            max_input = context_window
        if context_window <= 0:
            context_window = max_input
        return cls(
            id=data["id"],
            name=data.get("name", ""),
            enabled=data.get("enabled", True),
            input=list(data.get("input") or ["text"]),
            thinking=data.get("thinking"),
            max_input_tokens=max_input,
            context_window=context_window,
            max_output_tokens=int(data.get("max_output_tokens") or 0),
            api_mode=data.get("api_mode", "chat_completions"),
            api_fallback=data.get("api_fallback", "none"),
            native_tool_search=bool(data.get("native_tool_search", False)),
            capabilities=tuple(str(x) for x in (data.get("capabilities") or ())),
        )


def _optional_session_header(raw: Any) -> str | None:
    if not isinstance(raw, str):
        return None
    header = raw.strip()
    return header or None


@dataclass
class ProviderConfig:
    """Connection info for an LLM provider plus its catalog of models."""

    id: str  # provider identifier
    base_url: str
    api_key: str
    name: str = ""
    protocol: ProtocolName = "openai"
    headers: dict[str, str] = field(default_factory=dict)
    # When set, each LLM HTTP request on this provider carries this header set
    # to the current invocation ``thread_id`` (see ``llm.session_header``).
    session_header: str | None = None
    models: list[ModelConfig] = field(default_factory=list)
    # openai protocol only: request streamed token usage via
    # ``stream_options: {"include_usage": true}``. langchain-openai leaves
    # this off whenever a custom ``base_url`` is set (always our case), and
    # most OpenAI-compatible vendors omit usage from streams without it.
    # Disable for relays that reject the ``stream_options`` field.
    stream_usage: bool = True

    def __post_init__(self) -> None:
        if not self.id:
            raise ValueError("ProviderConfig.id must be a non-empty string")
        if not self.base_url:
            raise ValueError("ProviderConfig.base_url is required")
        if not self.api_key:
            raise ValueError("ProviderConfig.api_key is required")
        if self.protocol not in ("openai", "anthropic", "bedrock"):
            raise ValueError(f"Unsupported provider protocol: {self.protocol!r}")
        if self.protocol == "bedrock" and any(model.native_tool_search for model in self.models):
            raise ValueError("native_tool_search is only supported for openai and anthropic protocols")
        if self.session_header is not None:
            header = self.session_header.strip()
            self.session_header = header or None
        seen: set[str] = set()
        for m in self.models:
            if m.id in seen:
                raise ValueError(f"Duplicate model id {m.id!r} in provider {self.id!r}")
            seen.add(m.id)

    def get_model(self, model_id: str) -> ModelConfig | None:
        """Look up a model by id (returns ``None`` if not found)."""
        for m in self.models:
            if m.id == model_id:
                return m
        return None

    def enabled_models(self) -> list[ModelConfig]:
        return [m for m in self.models if m.enabled]

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-friendly dict representation.

        Note: ``api_key`` is included verbatim. Callers concerned about secret
        leakage should redact or template-substitute it before persisting.
        """
        return {
            "id": self.id,
            "base_url": self.base_url,
            "api_key": self.api_key,
            "name": self.name,
            "protocol": self.protocol,
            "headers": dict(self.headers),
            "session_header": self.session_header,
            "models": [m.to_dict() for m in self.models],
            "stream_usage": self.stream_usage,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ProviderConfig:
        """Reverse of :meth:`to_dict`. ``id`` is required in ``data``."""
        return cls(
            id=data["id"],
            base_url=data["base_url"],
            api_key=data["api_key"],
            name=data.get("name", ""),
            protocol=data.get("protocol", "openai"),
            headers=dict(data.get("headers") or {}),
            session_header=_optional_session_header(data.get("session_header")),
            models=[ModelConfig.from_dict(m) for m in data.get("models") or []],
            stream_usage=bool(data.get("stream_usage", True)),
        )


# ---------------------------------------------------------------------------
# HarnessAgentConfig
# ---------------------------------------------------------------------------

DEFAULT_SESSION_LOG_MAX_BYTES = 50 * 1024 * 1024  # 50 MiB


@dataclass
class HarnessAgentConfig:
    """User-facing agent configuration.

    Most fields have sensible defaults so a minimal config only needs to
    supply ``providers`` (and optionally ``workspace_dir``).
    """

    # —— Identity ——
    name: str = "octop-harness"

    # —— Paths ——
    # Absolute local directory. Used as:
    #   - the local-disk root when ``backend`` is local_shell / filesystem
    #     and the backend spec doesn't override its own root_dir;
    #   - the parent of agent-managed artifacts that must live on disk
    #     (``logs/``, ``sessions/`` JSONL, ``checkpoints.sqlite``, bootstrap
    #     marker, etc.);
    #   - the on-disk base for all workspace content (templates, skills,
    #     bootstrap marker, memory files, …);
    #   - for the default ``local_shell`` backend (``root_dir="/"``), backend
    #     paths equal OS paths, so all workspace files are expressed as
    #     absolute paths under ``workspace_dir`` — e.g. the builtin skills
    #     directory is ``{workspace_dir}/_builtin_skills/``.
    workspace_dir: str | Path = field(default_factory=lambda: Path.cwd().absolute())
    # Optional workspace-relative directory for system files (skills, sessions,
    # ``.env``, ``.bootstrapped``, checkpoints, memory sqlite, conversation
    # history / media offloads, …). Empty keeps them at ``workspace_dir``
    # (legacy). Persona markdown such as ``AGENTS.md`` always stays at the
    # workspace root.
    system_files_path: str = ""
    skills_dir: str | Path | Sequence[str | Path] | None = None
    # Slug or frontmatter ``name`` values hidden from the skills system prompt only.
    skills_disabled: frozenset[str] = field(default_factory=frozenset)
    # Tool names hidden from the model tool list (denylist; hot-updatable).
    tools_disabled: frozenset[str] = field(default_factory=frozenset)
    subagents_path: str | Path | Sequence[str | Path] | None = None
    subagents_auto_load: bool = True
    # Keep the parent-only ``task`` tool after tools inherited by subagents so
    # provider-side prefix caches can reuse the complete shared tool block.
    task_tool_last: bool = True

    # —— Backend ——
    # One of:
    #   - ``None`` (default → "local_shell" rooted at "/")
    #   - a string: "local_shell" / "filesystem" / "state" / "store" /
    #     "composite" / "s3" / "postgres"
    #   - a dict with a "type" key plus per-type kwargs
    #   - any object that implements ``BackendProtocol``
    backend: Any = None
    # New Windows subtree experts set this. Shell commands, environment
    # values, and stdout/stderr are not scanned for paths. Callers convert a
    # virtual path through the ``virtual_to_native_path`` tool.
    explicit_virtual_paths: bool = False

    # —— Protocol ——
    protocol: str = "langgraph"

    # —— Models ——
    providers: list[ProviderConfig] = field(default_factory=list)
    default_model: str | None = None
    multimodal_model: str | None = None
    model_selector: ModelSelector | None = None
    role_bindings: dict[str, str] | None = None
    todos_enabled: bool = True

    # —— Memory ——
    memory: Sequence[str] | None = None

    # —— Checkpointer ——
    checkpointer: Any = None  # ``None`` → SqliteSaver under workspace; ``False`` → disable; or pass instance

    # —— Subagents / system prompt ——
    system_prompt: str | None = None
    subagents: list[SubAgent] | None = None

    # —— Bootstrap ——
    # When enabled, ``bootstrap_file`` content replaces the system prompt on
    # every turn until ``bootstrap_marker`` exists on the agent backend.
    # Paths may be root-relative fragments (``BOOTSTRAP.md`` → ``/BOOTSTRAP.md``)
    # or complete storage paths (``~/.octop/agents/<id>/BOOTSTRAP.md``).
    bootstrap_enabled: bool = False
    bootstrap_file: str | Path | None = None  # None → ``BOOTSTRAP.md``
    bootstrap_marker: str | Path | None = None  # None → ``.bootstrapped``

    # Accepted for hosts that still pass these on the agent config (Octop).
    # Process logging is configured on ``HarnessAgentManager`` / ``setup_logging``.
    log_dir: InitVar[str | Path | None] = None
    log_agent_id: InitVar[str | None] = None
    log_level: InitVar[Literal["DEBUG", "INFO", "WARNING", "ERROR"] | None] = None
    log_max_bytes: InitVar[int] = 10 * 1024 * 1024
    log_backup_count: InitVar[int] = 5

    # —— Session logging ——
    session_log_enabled: bool = True
    session_log_max_bytes: int = DEFAULT_SESSION_LOG_MAX_BYTES
    session_log_dir: str | Path | None = None  # None → {workspace_dir}/sessions

    # —— Model retry (default ON: indispensable for production) ——
    model_retry_enabled: bool = True
    model_retry_max_retries: int = 2
    model_retry_initial_delay: float = 1.0
    model_retry_max_delay: float = 60.0

    # —— PII redaction (default ON: secrets in inputs/outputs/tool results
    # are masked with stars before reaching the model or session log).
    # The built-in detector covers LLM provider API keys; see
    # ``octop_harness.middleware.pii`` for the format list.
    pii_enabled: bool = True
    pii_strategy: Literal["block", "redact", "mask", "hash"] = "mask"
    # Where to apply detection. By default we cover all three surfaces:
    # user input, model output, and tool results.
    pii_surfaces: tuple[
        Literal["input", "output", "tool_results"],
        ...,
    ] = ("input", "output", "tool_results")

    # —— Tool guard (L1 parameter scan for shell tools) ——
    tool_guard_enabled: bool = True
    tool_guard_mode: Literal["block", "warn", "require_approval"] = "block"
    tool_guard_rules_dir: str | Path | None = None

    # —— Ask user (agent-initiated question) ——
    # Mounts the ``ask_user_question`` tool and pauses the graph on it via a
    # ``respond``-only HITL interrupt. Independent of ``SecurityPolicy``: this
    # is a collaboration channel, not an approval gate. Turn it off for
    # unattended runs (cron, heartbeats) where nobody can answer.
    ask_user_enabled: bool = True

    # —— Peer agents (call other experts via agent_list / ask_agent) ——
    # When True and the agent is created through
    # :class:`~octop_harness.manager.HarnessAgentManager`, ``PeerAgentMiddleware``
    # mounts the tools and injects a roster + ``@name`` usage hint.
    # Standalone ``HarnessAgent(...)`` has no registry, so the flag is a no-op.
    team_enabled: bool = True
    # Optional allowlist of peer names / ids this agent may see. ``None``
    # (default) means every agent owned by the current request user, plus
    # shared agents that have no ``user_id``. An empty tuple hides everyone.
    # A request-scoped ``configurable.team_peers`` intersects this list
    # (it cannot expand it).
    team_peers: tuple[str, ...] | None = None
    # Which peer-invoke tool surface to mount.
    # ``both`` keeps today's ``ask_agent(mode=sync|background)``.
    # ``sync`` / ``async`` inject a single-mode tool (Octop team hosts use async).
    # A request-scoped ``configurable.peer_invoke_mode`` may tighten this
    # (lose async) but cannot gain background dispatch.
    peer_invoke_mode: Literal["sync", "async", "both"] = "both"

    # —— Decision model ——
    # None, or a disabled config, leaves the middleware unmounted.
    decision: DecisionConfig | None = None

    # —— Progressive tool loading ——
    # Names in this set remain registered with DeepAgents for real execution.
    # Client mode keeps name/description references visible but defers parameter
    # schemas; native mode delegates discovery to the provider.
    deferred_tools: frozenset[str] = field(default_factory=frozenset)
    # Defer every MCP tool that remains visible after per-request MCP filtering.
    defer_mcp_tools: bool = False
    # ``client`` uses an ordinary function tool and works with any model that
    # supports tool calling. ``native`` delegates discovery to supported
    # OpenAI/Anthropic APIs. ``eager`` disables deferred loading.
    tool_search_mode: Literal["client", "native", "eager"] = "client"
    # Unsupported routed models either receive eager schemas (production-safe
    # default) or fail explicitly when ``tool_search_mode="native"``.
    tool_search_fallback: Literal["eager", "error"] = "eager"

    # —— Media offload (default ON: keep large inline base64 images / audio
    # out of long-running threads). After the first turn that contains a
    # given block, the bytes are written to the backend and the block is
    # replaced with a short text placeholder; the model can pull bytes
    # back via ``read_file``. See
    # ``octop_harness.middleware.media_offload`` for details.
    media_offload_enabled: bool = True
    media_offload_min_bytes: int = 4 * 1024  # skip blocks below this size
    media_offload_dir: str = ".media-cache"  # root-relative fragment or complete storage path

    # —— Optional image/video generation tools ——
    # When configured, registers provider-neutral ``generate_image`` and
    # ``generate_video`` tools backed by the selected media provider.
    media_generation: MediaGenerationConfig | None = None

    # —— Advanced passthroughs ——
    tools: list[Any] | None = None
    middleware: list[Any] | None = None
    interrupt_on: dict[str, Any] | None = None
    response_format: Any = None
    permissions: list[Any] | None = None
    debug: bool = False

    # —— i18n ——
    language: Literal["en", "zh"] = "zh"
    default_timezone: str | None = None

    # —— Optional web-search builtin tools ——
    # Auto by default: every provider whose required env vars are set is
    # loaded. ``searchfree`` (zero-config) is always included. Accepted values:
    #   - ``"auto"`` / ``True`` (default): every provider whose required env
    #     vars are set is loaded (tavily / doubao / deepseek / exa / kimi / searchfree).
    #   - ``False``: no web-search tools loaded.
    #   - ``"all"``: every provider is loaded; the ones missing env vars
    #     return a plain-text error string when invoked.
    #   - ``["tavily", "kimi"]``: an explicit list. Unknown names raise
    #     ``ValueError``; missing env vars raise ``RuntimeError`` so
    #     misconfiguration surfaces at agent construction time.
    web_search_tools: bool | Literal["auto", "all"] | Sequence[str] = "auto"

    # —— MCP servers (langchain-mcp-adapters) ——
    # Connection specs keyed by server name. When created via
    # :class:`~octop_harness.manager.HarnessAgentManager`, manager-level
    # configs are merged in (agent keys win on conflict) before the agent
    # is constructed, so this field holds the effective connection map.
    # Tools are loaded at agent init but hidden from the model unless a
    # :class:`~octop_harness.request.ChatRequest` opts in via ``mcp_servers``
    # or ``mcp_use_default=True``.
    mcp_server_configs: dict[str, Any] = field(default_factory=dict)
    # Agent-level default server list used when ``ChatRequest.mcp_use_default=True``.
    mcp_default_servers: list[str] | None = None

    # —— ACP external agent runners (Agent Client Protocol) ——
    acp_runners: dict[str, ACPRunnerConfig] = field(default_factory=default_acp_runners)
    acp_delegate_enabled: bool = False

    # —— Memory ——
    memory_enabled: bool = True
    memory_backend: str | dict[str, Any] | Any = "sqlite"
    memory_backend_config: dict[str, Any] | None = None  # backend-specific settings
    memory_jsonl_enabled: bool = True
    memory_jsonl_dir: str | Path | None = None  # None → {workspace}/sessions

    # —— Memory: MemoryService integration ——
    # Namespace stamped on every captured event / atom / page. ``None`` →
    # use ``self.name`` so each agent gets its own isolated memory partition
    # by default (decision A: per-agent isolation).
    memory_namespace: str | None = None
    # Auxiliary model (extractor / promotion / page regen). ``False`` → run
    # MemoryService without an LLM; capture + raw FTS recall still work,
    # extraction degrades to ``failure_reason``.
    memory_aux_model_enabled: bool = True
    # Optional extract override. ``None`` → follow the live chat model, then
    # ``default_model``. Both fields are the same override (legacy light/heavy
    # names); the first non-empty value wins. Octop writes one ``aux_model``
    # into both.
    memory_aux_light_model: str | None = None
    memory_aux_heavy_model: str | None = None
    # Read path: snapshot recall per user turn and replay it on API user-message
    # copies. Disabling skips new recall; historical snapshots still replay.
    memory_recall_inject_enabled: bool = True
    # Write path: capture the user turn + assistant reply as L0 raw events
    # after each model call. Off-thread; never blocks the user.
    memory_capture_enabled: bool = True
    # Trigger L0 → L2/L3 distillation (atom extraction, entity page regen)
    # automatically. Requires the auxiliary LLM client. When False, extraction
    # runs only when a host calls ``end_session`` explicitly.
    memory_extract_on_session_end: bool = True
    # Which automatic trigger drives extraction when the above is on:
    #   "idle"     — a per-session timer fires after ``memory_extract_idle_seconds``
    #                of inactivity (waits for a quiet conversation; default).
    #   "interval" — a single timer sweeps all recently-active sessions every
    #                ``memory_extract_interval_seconds`` on a steady cadence.
    # The two are mutually exclusive; the runtime wires exactly one.
    memory_extract_trigger_mode: Literal["idle", "interval"] = "idle"
    # Idle-watchdog cadence (mode="idle"): seconds of inactivity before a
    # session's timer fires ``end_session`` → ``extract``.
    memory_extract_idle_seconds: float = 300.0
    # Fixed-interval cadence (mode="interval"): seconds between sweeps of all
    # recently-active sessions. Default 6h.
    memory_extract_interval_seconds: float = 21600.0
    # Output budget for extraction / episode completions. ``None`` keeps
    # octop-memory's built-in 2048. This is written into the memory runtime's
    # ``extraction.max_tokens`` — the extractor always sends its own
    # ``max_tokens``, so a client-side fallback cannot override it.
    memory_extract_max_tokens: int | None = None
    # How long one auxiliary request may block. ``None`` keeps
    # ``HarnessAgentLLMClient`` defaults (light 120s, heavy 300s). These are
    # not the idle/interval trigger: those decide when extraction starts.
    memory_aux_light_timeout_s: float | None = None
    memory_aux_heavy_timeout_s: float | None = None
    # Depth-thinking on OpenAI-compatible aux calls. ``auto`` turns it off
    # for known Qwen3/QwQ chat-template models. ``off`` requests the same
    # supported switch; unknown models keep their own defaults.
    # ``on`` leaves the server default. Main-chat thinking settings are not
    # reused here.
    memory_aux_thinking: Literal["auto", "off", "on"] = "auto"
    # Completion budget for aux calls that do not pass their own
    # ``max_tokens`` (promotion / page regen). Extraction is unaffected:
    # it always sends a budget, overridden only by
    # ``memory_extract_max_tokens``. ``None`` adds no client-side cap.
    memory_aux_max_tokens: int | None = None
    # Extra OpenAI-compatible request fields for the first selected model only
    # (for example ``reasoning_effort``). Merged after the thinking switch,
    # so these top-level keys win. Bound only for langchain-openai models.
    memory_aux_extra_body: dict[str, Any] | None = None
    # Retries after the first request, per candidate model. Memory owns the
    # retry loop; dedicated SDK clients have their implicit retries disabled.
    memory_aux_max_retries: int = 2
    # Exponential delay: base * 2**attempt, capped at 60 seconds.
    memory_aux_retry_backoff_s: float = 1.0

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def __post_init__(
        self,
        log_dir: str | Path | None,
        log_agent_id: str | None,
        log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] | None,
        log_max_bytes: int,
        log_backup_count: int,
    ) -> None:
        # Host-compat InitVars: accepted so ``log_dir=`` does not raise, unused.
        _ = (log_dir, log_agent_id, log_level, log_max_bytes, log_backup_count)
        if self.providers:
            # Validate no duplicate ids.
            seen_ids: set[str] = set()
            for p in self.providers:
                if p.id in seen_ids:
                    raise ValueError(f"Duplicate provider id {p.id!r} in providers list")
                seen_ids.add(p.id)
        if self.session_log_max_bytes <= 0:
            raise ValueError("session_log_max_bytes must be positive")

        if self.memory_aux_max_tokens is not None and self.memory_aux_max_tokens < 1:
            raise ValueError(f"memory_aux_max_tokens must be >= 1, got {self.memory_aux_max_tokens!r}")
        if self.memory_aux_extra_body is not None and not isinstance(self.memory_aux_extra_body, dict):
            raise ValueError("memory_aux_extra_body must be a dict when set")

        if self.language not in ("en", "zh"):
            raise ValueError(f"language must be 'en' or 'zh', got {self.language!r}")
        if self.tool_search_mode not in ("client", "native", "eager"):
            raise ValueError(
                f"tool_search_mode must be 'client', 'native', or 'eager', got {self.tool_search_mode!r}",
            )
        if self.tool_search_fallback not in ("eager", "error"):
            raise ValueError(
                f"tool_search_fallback must be 'eager' or 'error', got {self.tool_search_fallback!r}",
            )
        if self.peer_invoke_mode not in ("sync", "async", "both"):
            raise ValueError(
                f"peer_invoke_mode must be 'sync', 'async', or 'both', got {self.peer_invoke_mode!r}",
            )
        if self.memory_aux_thinking not in ("auto", "off", "on"):
            raise ValueError(
                f"memory_aux_thinking must be 'auto', 'off', or 'on', got {self.memory_aux_thinking!r}",
            )
        retries = self.memory_aux_max_retries
        if isinstance(retries, bool) or not isinstance(retries, int) or not 0 <= retries <= 10:
            raise ValueError("memory_aux_max_retries must be an integer from 0 to 10")
        backoff = self.memory_aux_retry_backoff_s
        if isinstance(backoff, bool) or not isinstance(backoff, int | float) or not 0 <= backoff <= 60:
            raise ValueError("memory_aux_retry_backoff_s must be between 0 and 60 seconds")
        _validate_extract_max_tokens(self.memory_extract_max_tokens)
        _validate_aux_timeout("memory_aux_light_timeout_s", self.memory_aux_light_timeout_s)
        _validate_aux_timeout("memory_aux_heavy_timeout_s", self.memory_aux_heavy_timeout_s)

        # Workspace must be an absolute directory: it doubles as the backend's
        # on-disk root for local backends and as the parent for all
        # agent-managed local artifacts. Agent-facing rootfs paths (e.g.
        # ``/.octop/workspaces/<id>``) count as absolute even on Windows, where
        # they carry no drive letter — ``HarnessAgent`` maps those onto
        # ``{root_dir}/…`` for local persistence.
        ws = Path(self.workspace_dir).expanduser()
        if not ws.is_absolute() and not _is_rootfs_path(self.workspace_dir):
            raise ValueError(
                f"workspace_dir must be an absolute or rootfs path, got {self.workspace_dir!r}",
            )
        # Normalize back into the field so downstream consumers always see
        # a fully-resolved Path — bypass dataclass frozen-ness via __setattr__
        # equivalent (we're not actually frozen, but this makes the intent
        # explicit and survives a future ``frozen=True`` flip).
        object.__setattr__(self, "workspace_dir", ws)

        from octop_harness.backends.workspace import normalize_system_files_path

        object.__setattr__(self, "system_files_path", normalize_system_files_path(self.system_files_path))

        if self.team_peers is not None:
            object.__setattr__(
                self,
                "team_peers",
                tuple(str(n).strip() for n in self.team_peers if str(n).strip()),
            )

        # When ``providers`` is empty the config is typically handed to
        # :class:`~octop_harness.manager.HarnessAgentManager`, which owns a
        # shared :class:`~octop_harness.llm.factory.ChatModelFactory`.
        # Defer model-ref validation to runtime in that case.
        if self.providers:
            if self.default_model is not None:
                self._check_model_ref("default_model", self.default_model)
            if self.multimodal_model is not None:
                self._check_model_ref("multimodal_model", self.multimodal_model)

    # ------------------------------------------------------------------
    # Convenience accessors
    # ------------------------------------------------------------------

    def resolve_model_ref(self, ref: str) -> tuple[ProviderConfig, ModelConfig]:
        """Resolve ``"<provider>/<model_id>"`` to its config pair.

        Raises ``ValueError`` if the provider or model id is unknown or disabled.
        """
        provider_key, model_id = self._split_ref(ref)
        for p in self.providers:
            if p.id == provider_key:
                model = p.get_model(model_id)
                if model is None:
                    raise ValueError(f"Provider {provider_key!r} has no model {model_id!r}")
                if not model.enabled:
                    raise ValueError(f"Model {ref!r} is disabled")
                return p, model
        raise ValueError(f"Unknown provider {provider_key!r} in model ref {ref!r}")

    def pick_default_model_ref(self) -> str:
        """Return ``default_model`` if set, otherwise the first enabled model."""
        if self.default_model:
            return self.default_model
        for p in self.providers:
            for model in p.enabled_models():
                return f"{p.id}/{model.id}"
        raise ValueError("No enabled models found in providers")

    def pick_multimodal_model_ref(self) -> str | None:
        """Return ``multimodal_model`` if set, else first enabled multimodal model."""
        if self.multimodal_model:
            return self.multimodal_model
        for p in self.providers:
            for model in p.enabled_models():
                if model.is_multimodal:
                    return f"{p.id}/{model.id}"
        return None

    def memory_files(self) -> list[str]:
        """Return configured memory markdown filenames, or package defaults when unset."""
        if self.memory is not None:
            return list(self.memory)
        from octop_harness.backends.workspace import DEFAULT_MEMORY_FILES

        return list(DEFAULT_MEMORY_FILES)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _split_ref(ref: str) -> tuple[str, str]:
        if "/" not in ref:
            raise ValueError(
                f"Model ref {ref!r} must be in the form '<provider>/<model_id>'",
            )
        provider_key, _, model_id = ref.partition("/")
        if not provider_key or not model_id:
            raise ValueError(f"Malformed model ref: {ref!r}")
        return provider_key, model_id

    def _check_model_ref(self, field_name: str, ref: str) -> None:
        try:
            self.resolve_model_ref(ref)
        except ValueError as exc:
            raise ValueError(f"{field_name}={ref!r}: {exc}") from exc

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    # Fields holding live Python objects we cannot serialize. These are
    # *silently* skipped on dump and ignored on load.
    _unserializable_fields: frozenset[str] = frozenset(
        {
            "model_selector",
            "checkpointer",
            "tools",
            "middleware",
            "permissions",
            "interrupt_on",
            "response_format",
        },
    )

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-friendly dict representation.

        Fields holding live Python objects (callables, pre-built backend
        instances, custom tools / middleware, etc.) are omitted. The
        resulting dict is suitable for ``json.dumps`` and round-trips
        through :py:meth:`from_dict`.
        """
        out: dict[str, Any] = {
            "name": self.name,
            "workspace_dir": _path_to_str(self.workspace_dir),
            "system_files_path": self.system_files_path,
            "skills_dir": _path_dirs_to_jsonable(self.skills_dir),
            "skills_disabled": sorted(self.skills_disabled),
            "tools_disabled": sorted(self.tools_disabled),
            "subagents_path": _path_dirs_to_jsonable(self.subagents_path),
            "subagents_auto_load": self.subagents_auto_load,
            "task_tool_last": self.task_tool_last,
            "providers": [p.to_dict() for p in self.providers],
            "default_model": self.default_model,
            "multimodal_model": self.multimodal_model,
            "role_bindings": dict(self.role_bindings) if self.role_bindings else None,
            "todos_enabled": self.todos_enabled,
            "memory": list(self.memory) if self.memory is not None else None,
            "system_prompt": self.system_prompt,
            "subagents": _subagents_to_jsonable(self.subagents),
            "session_log_enabled": self.session_log_enabled,
            "session_log_max_bytes": self.session_log_max_bytes,
            "session_log_dir": _path_to_str(self.session_log_dir) if self.session_log_dir is not None else None,
            "model_retry_enabled": self.model_retry_enabled,
            "model_retry_max_retries": self.model_retry_max_retries,
            "model_retry_initial_delay": self.model_retry_initial_delay,
            "model_retry_max_delay": self.model_retry_max_delay,
            "pii_enabled": self.pii_enabled,
            "pii_strategy": self.pii_strategy,
            "pii_surfaces": list(self.pii_surfaces),
            "tool_guard_enabled": self.tool_guard_enabled,
            "tool_guard_mode": self.tool_guard_mode,
            "tool_guard_rules_dir": _path_to_str(self.tool_guard_rules_dir)
            if self.tool_guard_rules_dir is not None
            else None,
            "ask_user_enabled": self.ask_user_enabled,
            "team_enabled": self.team_enabled,
            "team_peers": list(self.team_peers) if self.team_peers is not None else None,
            "peer_invoke_mode": self.peer_invoke_mode,
            "deferred_tools": sorted(self.deferred_tools),
            "defer_mcp_tools": self.defer_mcp_tools,
            "tool_search_mode": self.tool_search_mode,
            "tool_search_fallback": self.tool_search_fallback,
            "media_offload_enabled": self.media_offload_enabled,
            "media_offload_min_bytes": self.media_offload_min_bytes,
            "media_offload_dir": self.media_offload_dir,
            "media_generation": self.media_generation.to_dict() if self.media_generation is not None else None,
            "web_search_tools": _web_search_tools_to_jsonable(self.web_search_tools),
            "mcp_server_configs": dict(self.mcp_server_configs),
            "mcp_default_servers": list(self.mcp_default_servers) if self.mcp_default_servers else None,
            "acp_runners": _acp_runners_to_jsonable(self.acp_runners),
            "acp_delegate_enabled": self.acp_delegate_enabled,
            "bootstrap_enabled": self.bootstrap_enabled,
            "bootstrap_file": _path_to_str(self.bootstrap_file) if self.bootstrap_file else None,
            "bootstrap_marker": _path_to_str(self.bootstrap_marker) if self.bootstrap_marker else None,
            "memory_enabled": self.memory_enabled,
            "memory_backend_config": (
                dict(self.memory_backend_config) if self.memory_backend_config is not None else None
            ),
            "memory_jsonl_enabled": self.memory_jsonl_enabled,
            "memory_jsonl_dir": _path_to_str(self.memory_jsonl_dir) if self.memory_jsonl_dir else None,
            "memory_namespace": self.memory_namespace,
            "memory_aux_model_enabled": self.memory_aux_model_enabled,
            "memory_aux_light_model": self.memory_aux_light_model,
            "memory_aux_heavy_model": self.memory_aux_heavy_model,
            "memory_recall_inject_enabled": self.memory_recall_inject_enabled,
            "memory_capture_enabled": self.memory_capture_enabled,
            "memory_extract_on_session_end": self.memory_extract_on_session_end,
            "memory_extract_trigger_mode": self.memory_extract_trigger_mode,
            "memory_extract_idle_seconds": self.memory_extract_idle_seconds,
            "memory_extract_interval_seconds": self.memory_extract_interval_seconds,
            "memory_extract_max_tokens": self.memory_extract_max_tokens,
            "memory_aux_light_timeout_s": self.memory_aux_light_timeout_s,
            "memory_aux_heavy_timeout_s": self.memory_aux_heavy_timeout_s,
            "memory_aux_thinking": self.memory_aux_thinking,
            "memory_aux_max_retries": self.memory_aux_max_retries,
            "memory_aux_retry_backoff_s": self.memory_aux_retry_backoff_s,
            "memory_aux_max_tokens": self.memory_aux_max_tokens,
            "memory_aux_extra_body": (
                dict(self.memory_aux_extra_body) if self.memory_aux_extra_body is not None else None
            ),
            "debug": self.debug,
            "language": self.language,
            "default_timezone": self.default_timezone,
            "decision": self.decision.to_dict() if self.decision is not None else None,
        }
        # Backend: serialize only if it's a string or dict spec; live instances skipped.
        if isinstance(self.backend, str | dict) or self.backend is None:
            out["backend"] = self.backend
        # Memory backend: serialize only if it's a string or dict spec; live instances skipped.
        if isinstance(self.memory_backend, str | dict):
            out["memory_backend"] = self.memory_backend
        return out

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> HarnessAgentConfig:
        """Build a config from a dict produced by :py:meth:`to_dict`.

        Unknown keys are ignored (forward-compat); missing keys use defaults.
        Fields in :py:attr:`_unserializable_fields` are also ignored if
        present, so a hand-edited file is free to leave them around (e.g.
        as comments-by-key) without breaking ``from_dict``.
        """
        if not isinstance(data, dict):
            raise TypeError(f"HarnessAgentConfig.from_dict expected a dict, got {type(data).__name__}")

        kwargs: dict[str, Any] = {}
        valid_fields = {f.name for f in fields(cls)}
        for key, value in data.items():
            coerced = _coerce_config_field(key, value, valid_fields, cls._unserializable_fields)
            if coerced is _SKIP_FIELD:
                continue
            kwargs[key] = coerced
        return cls(**kwargs)

    def to_file(self, path: str | Path | None = None, *, indent: int = 2) -> Path:
        """Serialize this config as JSON to ``path``.

        When ``path`` is ``None``, writes to ``{workspace_dir}/{DEFAULT_CONFIG_FILENAME}``.
        Parent directories are created as needed.

        Returns:
            The absolute path actually written.
        """
        target = self._resolve_config_path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(self.to_dict(), indent=indent, ensure_ascii=False), encoding="utf-8")
        return target

    @classmethod
    def from_file(cls, path: str | Path | None = None) -> HarnessAgentConfig:
        """Load a config from a JSON file.

        When ``path`` is ``None``, reads ``./{DEFAULT_CONFIG_FILENAME}``
        relative to the current working directory.
        """
        target = cls._resolve_config_path_for_load(path)
        if not target.is_file():
            raise FileNotFoundError(f"Config file not found: {target}")
        data = json.loads(target.read_text(encoding="utf-8"))
        return cls.from_dict(data)

    @classmethod
    def from_env(
        cls,
        workspace_dir: str | Path,
        **kwargs: Any,
    ) -> HarnessAgentConfig:
        """Construct config with empty ``providers`` (env-driven setup intent).

        Equivalent to ``HarnessAgentConfig(workspace_dir=..., providers=[])``.
        Provider environment variables are **not** read here — they are
        detected later by :class:`~octop_harness.HarnessAgent` (when no
        ``model_factory`` is injected) or supplied via
        :class:`~octop_harness.manager.HarnessAgentManager`.

        Args:
            workspace_dir: Workspace directory (required).
            **kwargs: Additional keyword arguments forwarded to the constructor.

        Returns:
            Configured :class:`HarnessAgentConfig` instance.
        """
        return cls(workspace_dir=workspace_dir, providers=[], **kwargs)

    # ------------------------------------------------------------------
    # Path resolution helpers for config persistence
    # ------------------------------------------------------------------

    def _resolve_config_path(self, path: str | Path | None) -> Path:
        """Resolve a config-file path *for saving* (``self`` is available)."""
        if path is not None:
            return Path(path).expanduser().absolute()
        # Default: {workspace_dir}/{DEFAULT_CONFIG_FILENAME}
        return Path(self.workspace_dir) / DEFAULT_CONFIG_FILENAME

    @staticmethod
    def _resolve_config_path_for_load(path: str | Path | None) -> Path:
        """Resolve a config-file path *for loading* (no ``self`` yet).

        Falls back to ``./{DEFAULT_CONFIG_FILENAME}`` relative to CWD.
        """
        if path is not None:
            return Path(path).expanduser().absolute()
        return (Path.cwd() / DEFAULT_CONFIG_FILENAME).absolute()


# ---------------------------------------------------------------------------
# Local helpers (not part of the public API)
# ---------------------------------------------------------------------------

_SKIP_FIELD = object()


def _providers_from_raw(providers_raw: Any) -> list[ProviderConfig]:
    if isinstance(providers_raw, dict):
        return [
            ProviderConfig.from_dict({"id": key, **value}) if isinstance(value, dict) else value
            for key, value in providers_raw.items()
        ]
    if isinstance(providers_raw, list):
        return [ProviderConfig.from_dict(item) if isinstance(item, dict) else item for item in providers_raw]
    raise TypeError("'providers' must be a list or dict")


def _coerce_config_field(
    key: str,
    value: Any,
    valid_fields: set[str],
    unserializable_fields: frozenset[str],
) -> Any:
    if key in unserializable_fields or key not in valid_fields:
        return _SKIP_FIELD
    if key == "memory_backend" and value is None:
        return _SKIP_FIELD
    if key == "providers":
        coerced: Any = _providers_from_raw(value or [])
    elif value is None:
        coerced = None
    elif key == "pii_surfaces":
        coerced = tuple(value)
    elif key == "acp_runners":
        coerced = _acp_runners_from_jsonable(value)
    elif key in {"skills_disabled", "tools_disabled", "deferred_tools"}:
        coerced = frozenset(str(x) for x in value)
    elif key == "team_peers":
        coerced = tuple(str(x) for x in value)
    elif key == "media_generation":
        if not isinstance(value, dict):
            raise TypeError("'media_generation' must be a dict or null")
        coerced = MediaGenerationConfig.from_dict(value)
    elif key == "decision":
        if not isinstance(value, dict):
            raise TypeError("'decision' must be a dict or null")
        coerced = DecisionConfig.from_dict(value)
    elif key == "subagents":
        coerced = [_subagent_from_dict(item) for item in value]
    else:
        coerced = value
    return coerced


def _validate_extract_max_tokens(value: int | None) -> None:
    if value is None:
        return
    if isinstance(value, bool) or not isinstance(value, int) or not 128 <= value <= 65536:
        raise ValueError("memory_extract_max_tokens must be an int from 128 to 65536, or None")


def _validate_aux_timeout(name: str, value: float | None) -> None:
    if value is None:
        return
    if isinstance(value, bool) or not isinstance(value, int | float) or not 30 <= float(value) <= 3600:
        raise ValueError(f"{name} must be between 30 and 3600 seconds, or None")


def _path_to_str(value: str | Path) -> str:
    """Render ``Path`` / ``str`` as a plain string for JSON output."""
    return str(value)


def _is_rootfs_path(value: str | Path) -> bool:
    """True for paths anchored at the rootfs (``/foo``), drive letter aside.

    ``Path.is_absolute()`` is platform-scoped: on Windows a drive-less
    ``/.octop/workspaces/<id>`` is *not* absolute, yet it is a legitimate
    agent-facing workspace that harness maps onto the backend ``root_dir``.
    """
    return str(value).replace("\\", "/").startswith("/")


def _path_dirs_to_jsonable(value: str | Path | Sequence[str | Path] | None) -> Any:
    """Render a path or sequence of path-likes for JSON."""
    if value is None:
        return None
    if isinstance(value, str | Path):
        return _path_to_str(value)
    return [_path_to_str(p) for p in value]


def _skills_dir_to_jsonable(value: str | Path | Sequence[str | Path] | None) -> Any:
    """Render the skills_dir field for JSON.

    Accepts a single path-like or a sequence of path-likes. Single strings are
    preserved as strings; sequences become lists of strings. ``None`` stays ``None``.
    """
    return _path_dirs_to_jsonable(value)


def _subagents_to_jsonable(subagents: list[SubAgent] | None) -> Any:
    if subagents is None:
        return None
    out: list[dict[str, Any]] = []
    for spec in subagents:
        item: dict[str, Any] = {
            "name": spec["name"],
            "description": spec["description"],
            "system_prompt": spec["system_prompt"],
        }
        model = spec.get("model")
        if isinstance(model, str):
            item["model"] = model
        skills = spec.get("skills")
        if skills is not None:
            item["skills"] = list(skills)
        out.append(item)
    return out


def _subagent_from_dict(data: dict[str, Any]) -> SubAgent:
    required = ("name", "description", "system_prompt")
    for key in required:
        if key not in data:
            msg = f"subagent spec missing required field {key!r}"
            raise ValueError(msg)
    spec: SubAgent = {
        "name": str(data["name"]),
        "description": str(data["description"]),
        "system_prompt": str(data["system_prompt"]),
    }
    if data.get("model") is not None:
        spec["model"] = str(data["model"])
    if data.get("skills") is not None:
        spec["skills"] = [str(s) for s in data["skills"]]
    return spec


def _acp_runners_to_jsonable(value: dict[str, ACPRunnerConfig]) -> dict[str, Any]:
    return {name: cfg.to_dict() for name, cfg in value.items()}


def _acp_runners_from_jsonable(value: Any) -> dict[str, ACPRunnerConfig]:
    runners = default_acp_runners()
    if not isinstance(value, dict):
        return runners
    for name, item in value.items():
        if isinstance(item, dict):
            runners[str(name)] = ACPRunnerConfig.from_dict(item)
    return runners


def _web_search_tools_to_jsonable(value: bool | Literal["auto", "all"] | Sequence[str]) -> Any:
    """Render ``web_search_tools`` for JSON output.

    Booleans and the special string sentinels round-trip as themselves; an
    explicit list of provider names becomes a list of strings.
    """
    if isinstance(value, bool | str):
        return value
    return list(value)


__all__ = [
    "DEFAULT_CONFIG_FILENAME",
    "DEFAULT_SESSION_LOG_MAX_BYTES",
    "DecisionConfig",
    "HarnessAgentConfig",
    "InputModality",
    "MediaGenerationConfig",
    "MediaProviderName",
    "ModelConfig",
    "ModelSelector",
    "ProtocolName",
    "ProviderConfig",
]
