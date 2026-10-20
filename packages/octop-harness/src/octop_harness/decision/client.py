"""HTTP client for a yes/no decision model.

The body matches the OpenRouter decisions API (also used by Jev): ``questions``
is a map of noul items, and each answer's ``noul`` field is P(yes). A transport
or parse failure returns an empty map so the caller keeps the current catalog.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT = httpx.Timeout(15.0)
_LAYA_TIMEOUT = httpx.Timeout(60.0)


def _timeout_for(provider: str) -> httpx.Timeout:
    """Local CPU Laya can take about a second per question."""
    return _LAYA_TIMEOUT if provider == "laya" else _DEFAULT_TIMEOUT


def _criteria(text: str) -> dict[str, str]:
    if any("\u4e00" <= char <= "\u9fff" for char in text):
        return {"true": "适用", "false": "不适用"}
    return {"true": "Yes, this applies.", "false": "No, this does not apply."}


def build_decision_body(
    *,
    state: str,
    statements: list[tuple[str, str]],
    model: str = "",
) -> dict[str, Any]:
    """Build an OpenRouter-style decisions request."""
    body: dict[str, Any] = {
        "state": state,
        "questions": {
            item_id: {
                "type": "noul",
                "instructions": text,
                "criteria": _criteria(text),
            }
            for item_id, text in statements
        },
    }
    if model:
        body["model"] = model
    return body


def _read_probability(row: object) -> float | None:
    if not isinstance(row, dict):
        return None
    raw = row.get("noul", row.get("probability", row.get("p_yes", row.get("yes"))))
    answer = row.get("answer")
    if raw is None and isinstance(answer, dict):
        raw = answer.get("noul", answer.get("probability", answer.get("p_yes", answer.get("yes"))))
    if isinstance(raw, bool) or not isinstance(raw, (int, float, str)):
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def parse_probabilities(payload: object) -> dict[str, float]:
    """Read ``id -> P(yes)`` from an OpenRouter answers object or a list of rows."""
    if not isinstance(payload, dict):
        return {}
    answers = payload.get("answers")
    out: dict[str, float] = {}
    if isinstance(answers, dict):
        for item_id, row in answers.items():
            probability = _read_probability(row)
            if probability is not None:
                out[str(item_id)] = probability
        if out:
            return out
    rows = answers if isinstance(answers, list) else payload.get("results") or payload.get("questions") or []
    if not isinstance(rows, list):
        return {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        item_id = str(row.get("id") or "").strip()
        probability = _read_probability(row)
        if item_id and probability is not None:
            out[item_id] = probability
    return out


class HttpDecisionClient:
    """POST a batch of yes/no questions to ``endpoint``."""

    def __init__(
        self,
        *,
        endpoint: str,
        api_key: str = "",
        model: str = "",
        provider: str = "",
    ) -> None:
        self._endpoint = endpoint.strip()
        self._api_key = api_key
        self._model = model.strip()
        self._provider = provider.strip()
        self._timeout = _timeout_for(self._provider)

    def score(self, *, state: str, statements: list[tuple[str, str]], strict: bool = False) -> dict[str, float]:
        if not statements or not self._endpoint:
            return {}
        try:
            response = httpx.post(
                self._endpoint,
                json=self._body(state, statements),
                headers=self._headers(),
                timeout=self._timeout,
            )
            response.raise_for_status()
            return parse_probabilities(response.json())
        except Exception:
            logger.warning("decision request failed endpoint=%s", self._endpoint, exc_info=True)
            if strict:
                raise
            return {}

    async def score_async(
        self,
        *,
        state: str,
        statements: list[tuple[str, str]],
        strict: bool = False,
    ) -> dict[str, float]:
        if not statements or not self._endpoint:
            return {}
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(
                    self._endpoint,
                    json=self._body(state, statements),
                    headers=self._headers(),
                )
            response.raise_for_status()
            return parse_probabilities(response.json())
        except Exception:
            logger.warning("decision request failed endpoint=%s", self._endpoint, exc_info=True)
            if strict:
                raise
            return {}

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        return headers

    def _body(self, state: str, statements: list[tuple[str, str]]) -> dict[str, Any]:
        return build_decision_body(state=state, statements=statements, model=self._model)
