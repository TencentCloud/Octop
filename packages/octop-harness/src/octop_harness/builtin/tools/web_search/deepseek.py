"""DeepSeek Search tool. Requires ``DEEPSEEK_API_KEY``."""

from __future__ import annotations

import json
import os

import httpx
from langchain_core.tools import tool

DEFAULT_ENDPOINT = "https://api.deepseek.com/v1/tools/search"
DEFAULT_TIMEOUT = 30.0


def _http_error(status_code: int) -> str:
    if status_code == 401:
        return "Error: DeepSeek Search authentication failed. Check DEEPSEEK_API_KEY."
    if status_code == 402:
        return "Error: DeepSeek Search account has insufficient balance."
    if status_code == 429:
        return "Error: DeepSeek Search rate limit reached. Retry later."
    return f"Error: DeepSeek Search returned HTTP {status_code}."


@tool
async def deepseek_search(  # noqa: PLR0911 - explicit API failures keep remediation clear
    query: str,
    count: int = 5,
    need_content: bool = False,
    ori_question: str | None = None,
) -> str:
    """Search the web with DeepSeek Search and return ranked results.

    Keep ``need_content`` disabled for normal searches. Each result already
    includes a model-ready summary and source URL. Enable page content only
    when the task requires the full source text.

    Args:
        query: Search query, from 1 to 128 Unicode characters.
        count: Number of results to return, from 1 to 50. The default is 5.
        need_content: Include extracted page content. The default is false.
        ori_question: Optional original user question, up to 128 characters.

    Returns:
        A JSON array of ranked results, or a plain-text error message.
    """
    api_key = os.getenv("DEEPSEEK_API_KEY", "")
    if not api_key:
        return "Error: DEEPSEEK_API_KEY environment variable is not set."

    clean_query = query.strip()
    if not clean_query or len(clean_query) > 128:
        return "Error: DeepSeek Search query must contain 1 to 128 characters."
    if not 1 <= count <= 50:
        return "Error: DeepSeek Search count must be between 1 and 50."

    payload: dict[str, str | int | bool] = {
        "query": clean_query,
        "count": count,
        "need_content": need_content,
    }
    if ori_question is not None:
        clean_question = ori_question.strip()
        if not clean_question or len(clean_question) > 128:
            return "Error: DeepSeek Search ori_question must contain 1 to 128 characters."
        payload["ori_question"] = clean_question

    try:
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
            response = await client.post(
                DEFAULT_ENDPOINT,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
    except httpx.HTTPError as exc:
        return f"Error: DeepSeek Search request failed: {exc}"

    if response.status_code >= 400:
        return _http_error(response.status_code)

    try:
        body = response.json()
    except ValueError:
        return "Error: DeepSeek Search returned a non-JSON response."
    results = body.get("results") if isinstance(body, dict) else None
    if not isinstance(results, list):
        return "Error: DeepSeek Search returned an invalid response."
    return json.dumps(results, ensure_ascii=False) if results else "No results found."
