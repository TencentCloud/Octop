"""Per-user preferences (locale, etc.)."""

from __future__ import annotations

import json
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from typing import Any, Self

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, model_validator

from octop.api.deps import current_user, get_server
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.users.preferences import (
    MAX_REMOTE_BROWSER_BOOKMARKS,
    PREFERENCES_KEY_TIMEZONE,
    ModelReasoningPreference,
    get_model_reasoning_from_json,
    get_preferred_model_from_json,
    get_remote_browser_bookmarks_from_json,
    parse_preferences_json,
)
from octop.infra.utils.locale import normalize_locale

router = APIRouter()


class RemoteBrowserBookmarkModel(BaseModel):
    url: str = Field(description="Bookmark URL (`http://` or `https://`).")
    title: str = Field(description="Short display label.")


class ModelReasoningPreferenceModel(BaseModel):
    mode: str = Field(default="auto", pattern="^(auto|enabled|disabled)$")
    effort: str | None = None


class PreferencesResponse(BaseModel):
    locale: str = Field(description="UI locale: `zh` or `en`.")
    remote_browser_bookmarks: list[RemoteBrowserBookmarkModel] = Field(
        default_factory=list,
        description="Saved URLs for the remote-browser page.",
    )
    preferred_model: str | None = Field(
        default=None,
        description="Per-user preferred model ref. The global active model is only a fallback.",
    )
    model_reasoning: dict[str, ModelReasoningPreferenceModel] = Field(
        default_factory=dict,
        description="Per-model reasoning defaults for this user.",
    )
    timezone: str | None = Field(default=None, description="Preferred IANA timezone.")


class PatchPreferencesBody(BaseModel):
    locale: str | None = Field(default=None, description="UI locale: `zh` or `en`.")
    remote_browser_bookmarks: list[RemoteBrowserBookmarkModel] | None = Field(
        default=None,
        description="Replace remote-browser bookmarks (max 12).",
    )
    preferred_model: str | None = None
    model_reasoning: dict[str, ModelReasoningPreferenceModel] | None = None
    timezone: str | None = None

    @model_validator(mode="after")
    def at_least_one_field(self) -> Self:
        if not self.model_fields_set.intersection(
            {"locale", "remote_browser_bookmarks", "preferred_model", "model_reasoning", "timezone"}
        ):
            raise ValueError("at least one preference field is required")
        if (
            self.remote_browser_bookmarks is not None
            and len(self.remote_browser_bookmarks) > MAX_REMOTE_BROWSER_BOOKMARKS
        ):
            raise ValueError(
                f"remote_browser_bookmarks must have at most {MAX_REMOTE_BROWSER_BOOKMARKS} items"
            )
        return self


def _bookmarks_response(row: Any) -> list[RemoteBrowserBookmarkModel]:
    raw = row.preferences_json if row else None
    return [
        RemoteBrowserBookmarkModel(url=b.url, title=b.title)
        for b in get_remote_browser_bookmarks_from_json(raw)
    ]


def _response(row: Any) -> PreferencesResponse:
    raw = row.preferences_json if row else None
    return PreferencesResponse(
        locale=normalize_locale(row.locale if row else None),
        remote_browser_bookmarks=_bookmarks_response(row),
        preferred_model=get_preferred_model_from_json(raw),
        model_reasoning={
            ref: ModelReasoningPreferenceModel(mode=pref.mode, effort=pref.effort)
            for ref, pref in get_model_reasoning_from_json(raw).items()
        },
        timezone=parse_preferences_json(raw).get(PREFERENCES_KEY_TIMEZONE),
    )


@router.get("/preferences", summary="Current user preferences", response_model=PreferencesResponse)
async def get_preferences(
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> PreferencesResponse:
    row = server.services.user_repo.get(user.id)
    return _response(row)


@router.patch("/preferences", summary="Update user preferences", response_model=PreferencesResponse)
async def patch_preferences(
    body: PatchPreferencesBody,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> PreferencesResponse:
    if body.locale is not None:
        await server.user_manager.set_locale(user.username, body.locale)
    if body.remote_browser_bookmarks is not None:
        items = [b.model_dump() for b in body.remote_browser_bookmarks]
        await server.user_manager.set_remote_browser_bookmarks(user.username, items)
    if "preferred_model" in body.model_fields_set or body.model_reasoning is not None:
        preferred: str | None | object = ...
        if "preferred_model" in body.model_fields_set:
            preferred = body.preferred_model
            if (
                preferred is not None
                and not server.app_runtime.agent_registry.providers.is_model_ref_usable(preferred)
            ):
                raise OctopError(
                    ErrorCode.SLASH_BAD_ARGS,
                    "preferred_model must reference an enabled model",
                )
        reasoning = None
        if body.model_reasoning is not None:
            reasoning = {
                ref: ModelReasoningPreference(mode=value.mode, effort=value.effort)
                for ref, value in body.model_reasoning.items()
            }
        await server.user_manager.set_model_preferences(
            user.username,
            preferred_model=preferred,
            model_reasoning=reasoning,
        )
    if "timezone" in body.model_fields_set:
        raw_timezone = body.timezone
        row = server.services.user_repo.get(user.id)
        data = parse_preferences_json(row.preferences_json if row else None)
        if raw_timezone is not None:
            trimmed = raw_timezone.strip()
            if not trimmed:
                raise OctopError(ErrorCode.SLASH_BAD_ARGS, "timezone cannot be empty")
            try:
                ZoneInfo(trimmed)
            except ZoneInfoNotFoundError:
                raise OctopError(
                    ErrorCode.SLASH_BAD_ARGS,
                    "timezone must be a valid IANA timezone",
                ) from None
            data[PREFERENCES_KEY_TIMEZONE] = trimmed
        else:
            data.pop(PREFERENCES_KEY_TIMEZONE, None)
        server.services.user_repo.set_preferences_json(user.id, json.dumps(data))
    row = server.services.user_repo.get(user.id)
    return _response(row)
