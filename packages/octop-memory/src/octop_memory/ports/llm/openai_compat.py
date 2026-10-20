"""OpenAICompatClient — production OpenAI-compatible LLM client.

This is the supported production path for **self-hosted bridge
deployments** (claw production deployment): the OpenClaw TS shell passes an ``llm``
block via ``--config-json`` and the bridge constructs this client to
power L1 candidate extraction, promotion escalation, and entity page
regeneration. It deliberately speaks the OpenAI chat-completions wire
format so one client covers OpenAI / DeepSeek / Qwen DashScope / vLLM /
LM Studio / most internal gateways.

Key properties (D25):

- **Tier-aware model mapping** — ``tier="light"`` and ``tier="heavy"``
  can target different models (cheap extraction vs. strong page regen).
- **API key is optional** — local gateways (vLLM, LM Studio, Ollama's
  OpenAI endpoint) don't require one; when absent no ``Authorization``
  header is sent. Prefer ``api_key_env`` (default
  ``OCTOPMEMORY_LLM_API_KEY``) over an inline ``api_key`` — config JSON
  travels through process argv and is visible in ``ps`` output.
- **Transient-failure retries** — network errors, timeouts, HTTP 408 /
  429 / 5xx are retried with exponential backoff before surfacing
  ``LLMClientError``. The extractor / promotion worker still degrade
  gracefully when retries are exhausted.
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any, Literal
from urllib import error, request

from octop_memory.ports.llm._protocol import LLMClientError, LLMTier

logger = logging.getLogger(__name__)

DEFAULT_LLM_API_KEY_ENV = "OCTOPMEMORY_LLM_API_KEY"
"""Default environment variable consulted for the API key.

The bridge's ``--config-json`` is passed on the command line, so an
inline ``api_key`` leaks into process listings. Deployments should set
this env var on the host process instead (the bridge subprocess
inherits it).
"""

_RETRYABLE_HTTP_STATUS = {408, 429, 500, 502, 503, 504}


class OpenAICompatClient:
    """Production OpenAI-compatible chat-completions client.

    Args:
        base_url: e.g. ``"https://api.openai.com/v1"``. The trailing
            ``/chat/completions`` path is appended automatically.
        model: model id used for ``tier="light"`` calls (extraction,
            promotion escalation).
        model_heavy: optional model id for ``tier="heavy"`` calls (page
            regeneration, daily consolidation). Defaults to ``model``.
        api_key: explicit key. Prefer ``api_key_env`` — see module
            docstring for why.
        api_key_env: env var to read the key from when ``api_key`` is
            not given. Missing env var means "no auth header" (fine for
            local gateways; remote providers will reject with 401).
        timeout_seconds: per-call timeout.
        max_retries: extra attempts after the first on transient
            failures (network error / timeout / 408 / 429 / 5xx).
        retry_backoff_seconds: base backoff; attempt ``n`` sleeps
            ``base * 2**n``. Set to 0 in tests.
    """

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        model_heavy: str | None = None,
        api_key: str | None = None,
        api_key_env: str = DEFAULT_LLM_API_KEY_ENV,
        timeout_seconds: float = 60.0,
        max_retries: int = 2,
        retry_backoff_seconds: float = 1.0,
    ) -> None:
        if not base_url:
            raise LLMClientError("OpenAICompatClient: base_url is required")
        if not model:
            raise LLMClientError("OpenAICompatClient: model is required")
        self._base_url = base_url.rstrip("/")
        self._models: dict[LLMTier, str] = {
            "light": model,
            "heavy": model_heavy or model,
        }
        self._timeout = timeout_seconds
        self._max_retries = max(0, int(max_retries))
        self._backoff = retry_backoff_seconds

        if api_key is not None:
            self._api_key: str | None = api_key
        else:
            self._api_key = os.environ.get(api_key_env) or None

    @classmethod
    def from_config(cls, cfg: dict[str, Any]) -> OpenAICompatClient:
        """Build a client from the bridge's ``--config-json`` ``llm`` block.

        Recognized keys: ``endpoint`` (alias ``base_url``), ``model``,
        ``model_heavy``, ``api_key``, ``api_key_env``,
        ``timeout_seconds``, ``max_retries``. Raises ``LLMClientError``
        when ``endpoint`` / ``model`` are missing.
        """
        endpoint = cfg.get("endpoint") or cfg.get("base_url")
        model = cfg.get("model")
        if not isinstance(endpoint, str) or not endpoint:
            raise LLMClientError("llm config: 'endpoint' is required")
        if not isinstance(model, str) or not model:
            raise LLMClientError("llm config: 'model' is required")
        kwargs: dict[str, Any] = {"base_url": endpoint, "model": model}
        if isinstance(cfg.get("model_heavy"), str) and cfg["model_heavy"]:
            kwargs["model_heavy"] = cfg["model_heavy"]
        if isinstance(cfg.get("api_key"), str) and cfg["api_key"]:
            kwargs["api_key"] = cfg["api_key"]
        if isinstance(cfg.get("api_key_env"), str) and cfg["api_key_env"]:
            kwargs["api_key_env"] = cfg["api_key_env"]
        if isinstance(cfg.get("timeout_seconds"), int | float):
            kwargs["timeout_seconds"] = float(cfg["timeout_seconds"])
        if isinstance(cfg.get("max_retries"), int):
            kwargs["max_retries"] = cfg["max_retries"]
        return cls(**kwargs)

    def call_llm(
        self,
        prompt: str,
        *,
        tier: LLMTier = "light",
        system: str | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
        response_format: Literal["text", "json"] = "text",
    ) -> str:
        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        body: dict[str, object] = {
            "model": self._models.get(tier, self._models["light"]),
            "messages": messages,
            "stream": False,
        }
        if temperature is not None:
            body["temperature"] = float(temperature)
        if max_tokens is not None:
            body["max_tokens"] = int(max_tokens)
        if response_format == "json":
            body["response_format"] = {"type": "json_object"}

        url = f"{self._base_url}/chat/completions"
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        last_error: LLMClientError | None = None
        for attempt in range(1 + self._max_retries):
            if attempt > 0 and self._backoff > 0:
                time.sleep(self._backoff * (2 ** (attempt - 1)))
            req = request.Request(url, data=data, headers=headers, method="POST")
            try:
                with request.urlopen(req, timeout=self._timeout) as resp:
                    payload_bytes = resp.read()
            except error.HTTPError as e:
                body_excerpt = ""
                try:
                    body_excerpt = e.read().decode("utf-8", errors="replace")[:500]
                except (OSError, TimeoutError, UnicodeError, ValueError):
                    logger.warning("failed to read LLM error response body", exc_info=True)
                last_error = LLMClientError(
                    f"OpenAICompatClient: HTTP {e.code} from {url}: {e.reason}. Response body excerpt: {body_excerpt!r}"
                )
                if e.code in _RETRYABLE_HTTP_STATUS:
                    logger.warning("LLM HTTP %s (attempt %d/%d)", e.code, attempt + 1, 1 + self._max_retries)
                    continue
                raise last_error from e
            except TimeoutError:
                last_error = LLMClientError(f"OpenAICompatClient: request to {url} timed out after {self._timeout}s")
                logger.warning("LLM timeout (attempt %d/%d)", attempt + 1, 1 + self._max_retries)
                continue
            except error.URLError as e:
                last_error = LLMClientError(f"OpenAICompatClient: network error reaching {url}: {e!s}")
                logger.warning("LLM network error (attempt %d/%d): %s", attempt + 1, 1 + self._max_retries, e)
                continue

            return _parse_chat_completion(payload_bytes)

        assert last_error is not None
        raise last_error


def _parse_chat_completion(payload_bytes: bytes) -> str:
    try:
        payload = json.loads(payload_bytes.decode("utf-8"))
    except json.JSONDecodeError as e:
        raise LLMClientError(f"OpenAICompatClient: non-JSON response: {payload_bytes[:300]!r}") from e

    # OpenAI shape: {"choices": [{"message": {"role": "...", "content": "..."}}], ...}
    try:
        content = payload["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as e:
        raise LLMClientError(f"OpenAICompatClient: unexpected response shape: {payload!r}") from e

    if not isinstance(content, str):
        raise LLMClientError(f"OpenAICompatClient: message.content is not a string: {content!r}")
    return content


__all__ = ["DEFAULT_LLM_API_KEY_ENV", "OpenAICompatClient"]
