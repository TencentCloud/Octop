"""Decision-model switch (Settings → Models → Decision)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, Literal, cast

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from octop.api.deps import get_server, require_permission
from octop.infra.agents.settings.decision import DecisionSettings
from octop.infra.agents.settings.laya_runtime import get_laya_runtime
from octop.infra.utils.locale import resolve_request_locale

router = APIRouter()


class DecisionServiceResponse(BaseModel):
    provider: Literal["laya", "jev", "microsoft", "custom"]
    endpoint: str
    model: str
    api_key_set: bool


class DecisionSettingsResponse(BaseModel):
    enabled: bool
    provider: Literal["laya", "jev", "microsoft", "custom"]
    endpoint: str
    model: str
    services: list[DecisionServiceResponse]
    skills: bool
    tools: bool
    team: bool
    threshold: float
    tool_min_count: int
    api_key_set: bool
    active: bool


class DecisionServiceBody(BaseModel):
    provider: Literal["laya", "jev", "microsoft", "custom"]
    endpoint: str = ""
    model: str = ""
    api_key: str | None = Field(
        default=None,
        description="Omit to keep this service's key. Send an empty string to clear it.",
    )


class DecisionSettingsBody(BaseModel):
    enabled: bool = False
    provider: Literal["laya", "jev", "microsoft", "custom"] = "laya"
    endpoint: str = ""
    model: str = ""
    services: list[DecisionServiceBody] | None = Field(
        default=None,
        description="Every saved service. The provider field is the default.",
    )
    skills: bool = True
    tools: bool = True
    team: bool = True
    threshold: float = Field(default=0.6, gt=0, lt=1)
    tool_min_count: int = Field(default=8, ge=1, le=100)
    api_key: str | None = Field(
        default=None,
        description="Omit to keep the stored key. Send an empty string to clear it.",
    )


class DecisionTestBody(BaseModel):
    endpoint: str | None = None
    api_key: str | None = None
    model: str | None = None
    provider: Literal["laya", "jev", "microsoft", "custom"] | None = None


def _view(settings: DecisionSettings) -> DecisionSettingsResponse:
    return DecisionSettingsResponse(
        enabled=settings.enabled,
        provider=settings.provider,  # type: ignore[arg-type]
        endpoint=settings.endpoint,
        model=settings.model,
        skills=settings.skills,
        tools=settings.tools,
        team=settings.team,
        threshold=settings.threshold,
        tool_min_count=settings.tool_min_count,
        api_key_set=settings.api_key_set,
        active=settings.active,
        services=[
            DecisionServiceResponse(
                provider=item.provider,  # type: ignore[arg-type]
                endpoint=item.endpoint,
                model=item.model,
                api_key_set=item.api_key_set,
            )
            for item in settings.services
        ],
    )


@router.get("/settings/decision", summary="Get the decision-model switch")
async def get_decision_settings(
    _: Any = Depends(require_permission("providers")),
    server: Any = Depends(get_server),
) -> DecisionSettingsResponse:
    """Return the decision-model settings. The API key itself is not included."""
    return _view(server.app_runtime.agent_registry.decision.load())


@router.put("/settings/decision", summary="Update the decision-model switch")
async def put_decision_settings(
    body: DecisionSettingsBody,
    _: Any = Depends(require_permission("providers")),
    server: Any = Depends(get_server),
) -> DecisionSettingsResponse:
    """Save the switch and rebuild running agents so the middleware mounts or unmounts."""
    saved = await server.app_runtime.agent_registry.save_decision(
        enabled=body.enabled,
        provider=body.provider,
        endpoint=body.endpoint,
        model=body.model,
        skills=body.skills,
        tools=body.tools,
        team=body.team,
        threshold=body.threshold,
        tool_min_count=body.tool_min_count,
        api_key=body.api_key,
        services=(
            [item.model_dump() for item in body.services] if body.services is not None else None
        ),
    )
    return _view(saved)


@router.post("/settings/decision/test", summary="Probe the decision-model endpoint")
async def test_decision_settings(
    body: DecisionTestBody,
    _: Any = Depends(require_permission("providers")),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    """Send one yes/no question. A probability in the reply means the endpoint is reachable."""
    return cast(
        dict[str, Any],
        await server.app_runtime.agent_registry.probe_decision(
            endpoint=body.endpoint,
            api_key=body.api_key,
            model=body.model,
            provider=body.provider,
        ),
    )


@router.get("/settings/decision/laya", summary="Get the local Laya install status")
async def get_laya_status(
    _: Any = Depends(require_permission("providers")),
) -> dict[str, Any]:
    """Report whether the managed Laya process is installed and responding."""
    return await get_laya_runtime().status()


@router.post("/settings/decision/laya/install", summary="Install Laya on this machine")
async def install_laya(
    request: Request,
    _: Any = Depends(require_permission("providers")),
) -> StreamingResponse:
    """Install Laya into Octop's environment and stream the log.

    A second request attaches to an install that is already running.
    Closing the page does not stop the install.
    """
    locale = resolve_request_locale(request)

    async def _gen() -> AsyncIterator[str]:
        async for event in get_laya_runtime().install_events(locale):
            yield event

    return StreamingResponse(_gen(), media_type="text/event-stream")


@router.post("/settings/decision/laya/start", summary="Start the local Laya service")
async def start_laya(
    request: Request,
    _: Any = Depends(require_permission("providers")),
) -> dict[str, Any]:
    """Start the already installed laya-serve process."""
    return await get_laya_runtime().start(resolve_request_locale(request))


@router.post("/settings/decision/laya/stop", summary="Stop the local Laya service")
async def stop_laya(
    request: Request,
    _: Any = Depends(require_permission("providers")),
) -> dict[str, Any]:
    """Stop only the Laya process Octop started."""
    return await get_laya_runtime().stop(resolve_request_locale(request))
