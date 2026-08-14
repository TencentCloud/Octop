"""Observability configuration API (admin)."""

from __future__ import annotations

from typing import Any, cast

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from octop.api.deps import get_server, require_permission

router = APIRouter()


class LangfuseConfigResponse(BaseModel):
    enabled: bool
    public_key: str
    host: str
    secret_key_set: bool
    configured: bool


class LangfuseConfigBody(BaseModel):
    enabled: bool = False
    public_key: str = ""
    host: str = Field(
        default="", description="Langfuse server URL, e.g. https://cloud.langfuse.com"
    )
    secret_key: str | None = Field(
        default=None,
        description="Omit to keep the existing secret key unchanged.",
    )


class LangfuseTestBody(BaseModel):
    public_key: str | None = None
    host: str | None = None
    secret_key: str | None = None


def _to_response(cfg: Any) -> LangfuseConfigResponse:
    return LangfuseConfigResponse(
        enabled=cfg.enabled,
        public_key=cfg.public_key,
        host=cfg.host,
        secret_key_set=cfg.secret_key_set,
        configured=cfg.configured,
    )


@router.get("/langfuse", summary="Get Langfuse observability config")
async def get_langfuse_config(
    _: Any = Depends(require_permission("observability")),
    server: Any = Depends(get_server),
) -> LangfuseConfigResponse:
    return _to_response(server.app_runtime.agent_registry.langfuse.load())


@router.put("/langfuse", summary="Update Langfuse observability config")
async def put_langfuse_config(
    body: LangfuseConfigBody,
    _: Any = Depends(require_permission("observability")),
    server: Any = Depends(get_server),
) -> LangfuseConfigResponse:
    cfg = server.app_runtime.agent_registry.save_langfuse(
        enabled=body.enabled,
        public_key=body.public_key,
        host=body.host,
        secret_key=body.secret_key,
    )
    return _to_response(cfg)


@router.post("/langfuse/test", summary="Test Langfuse connection")
async def test_langfuse_connection(
    body: LangfuseTestBody,
    _: Any = Depends(require_permission("observability")),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    return cast(
        dict[str, Any],
        await server.app_runtime.agent_registry.langfuse.test_connection(
            public_key=body.public_key,
            host=body.host,
            secret_key=body.secret_key,
        ),
    )
