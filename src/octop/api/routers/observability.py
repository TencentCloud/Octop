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


class ClsTopicItem(BaseModel):
    topic_id: str
    flag: str = ""


class ClsApplicationItem(BaseModel):
    application_id: str
    application_name: str
    access_type: str
    region: str
    topic_id: str
    logset_id: str = ""
    log_topics: list[ClsTopicItem] = Field(default_factory=list)
    created: bool = False


class ClsConfigResponse(BaseModel):
    enabled: bool
    region: str
    topic_id: str
    application_id: str
    application_name: str
    access_type: str
    use_internal_endpoint: bool
    mask_content: bool
    secret_id_masked: str
    secret_id_set: bool
    secret_key_set: bool
    configured: bool
    endpoint: str
    active_backend: str = "none"
    application_created: bool = False


class ClsConfigBody(BaseModel):
    enabled: bool = False
    region: str = Field(
        default="ap-guangzhou", description="Tencent Cloud region, e.g. ap-guangzhou"
    )
    topic_id: str = Field(
        default="",
        description="Existing CLS Trace TopicId. Leave empty with auto_create_app=true to create automatically.",
    )
    application_id: str = ""
    application_name: str = Field(
        default="octop",
        description="CLS AgentObs application name (also used as OpenTelemetry service.name).",
    )
    access_type: str = Field(
        default="Langfuse",
        description="CLS AgentObs access type: Langfuse or Agent.",
    )
    use_internal_endpoint: bool = False
    mask_content: bool = False
    secret_id: str | None = Field(
        default=None,
        description="Tencent Cloud SecretId. Omit to keep the existing SecretId unchanged.",
    )
    secret_key: str | None = Field(
        default=None,
        description="Tencent Cloud SecretKey. Omit to keep the existing SecretKey unchanged.",
    )
    auto_create_app: bool = Field(
        default=False,
        description="When enabled=true and topic_id is empty, auto-create (or reuse) a CLS application.",
    )
    logset_id: str | None = Field(
        default=None,
        description="Optional existing CLS LogsetId when creating an application.",
    )
    reuse_existing: bool = Field(
        default=True,
        description="When auto-creating an application, reuse an existing one with the same name and access_type.",
    )


class ClsListApplicationsBody(BaseModel):
    region: str | None = None
    access_type: str | None = None
    application_name: str | None = None
    secret_id: str | None = None
    secret_key: str | None = None


class ClsApplicationListResponse(BaseModel):
    applications: list[ClsApplicationItem]


class ClsCreateApplicationBody(BaseModel):
    region: str | None = None
    application_name: str = "octop"
    access_type: str = "Langfuse"
    logset_id: str | None = None
    reuse_existing: bool = True
    secret_id: str | None = None
    secret_key: str | None = None


class ClsTestBody(BaseModel):
    region: str | None = None
    topic_id: str | None = None
    use_internal_endpoint: bool | None = None
    secret_id: str | None = None
    secret_key: str | None = None


def _to_response(cfg: Any) -> LangfuseConfigResponse:
    return LangfuseConfigResponse(
        enabled=cfg.enabled,
        public_key=cfg.public_key,
        host=cfg.host,
        secret_key_set=cfg.secret_key_set,
        configured=cfg.configured,
    )


def _to_cls_response(
    cfg: Any,
    *,
    active_backend: str,
    application_created: bool = False,
) -> ClsConfigResponse:
    return ClsConfigResponse(
        enabled=cfg.enabled,
        region=cfg.region,
        topic_id=cfg.topic_id,
        application_id=cfg.application_id,
        application_name=cfg.application_name,
        access_type=cfg.access_type,
        use_internal_endpoint=cfg.use_internal_endpoint,
        mask_content=cfg.mask_content,
        secret_id_masked=cfg.secret_id_masked,
        secret_id_set=cfg.secret_id_set,
        secret_key_set=cfg.secret_key_set,
        configured=cfg.configured,
        endpoint=cfg.endpoint,
        active_backend=active_backend,
        application_created=application_created,
    )


def _to_cls_app_item(app: Any) -> ClsApplicationItem:
    return ClsApplicationItem(
        application_id=app.application_id,
        application_name=app.application_name,
        access_type=app.access_type,
        region=app.region,
        topic_id=app.topic_id,
        logset_id=app.logset_id,
        log_topics=[
            ClsTopicItem(topic_id=t["topic_id"], flag=t.get("flag", "")) for t in app.log_topics
        ],
        created=bool(app.created),
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


@router.get("/cls", summary="Get Tencent Cloud CLS observability config")
async def get_cls_config(
    _: Any = Depends(require_permission("observability")),
    server: Any = Depends(get_server),
) -> ClsConfigResponse:
    registry = server.app_runtime.agent_registry
    return _to_cls_response(
        registry.cls_observability.load(),
        active_backend=registry.active_observability_backend(),
    )


@router.put("/cls", summary="Update Tencent Cloud CLS observability config")
async def put_cls_config(
    body: ClsConfigBody,
    _: Any = Depends(require_permission("observability")),
    server: Any = Depends(get_server),
) -> ClsConfigResponse:
    registry = server.app_runtime.agent_registry
    cfg, provisioned = await registry.save_cls(
        enabled=body.enabled,
        region=body.region,
        topic_id=body.topic_id,
        application_id=body.application_id,
        application_name=body.application_name,
        access_type=body.access_type,
        use_internal_endpoint=body.use_internal_endpoint,
        mask_content=body.mask_content,
        secret_id=body.secret_id,
        secret_key=body.secret_key,
        auto_create_app=body.auto_create_app,
        logset_id=body.logset_id,
        reuse_existing=body.reuse_existing,
    )
    return _to_cls_response(
        cfg,
        active_backend=registry.active_observability_backend(),
        application_created=bool(provisioned and provisioned.created),
    )


@router.post(
    "/cls/applications/list", summary="List existing Tencent Cloud CLS AgentObs applications"
)
async def list_cls_applications(
    body: ClsListApplicationsBody,
    _: Any = Depends(require_permission("observability")),
    server: Any = Depends(get_server),
) -> ClsApplicationListResponse:
    apps = await server.app_runtime.agent_registry.cls_observability.list_applications(
        region=body.region,
        access_type=body.access_type,
        application_name=body.application_name,
        secret_id=body.secret_id,
        secret_key=body.secret_key,
    )
    return ClsApplicationListResponse(applications=[_to_cls_app_item(app) for app in apps])


@router.post(
    "/cls/applications", summary="Create or reuse a Tencent Cloud CLS AgentObs application"
)
async def create_cls_application(
    body: ClsCreateApplicationBody,
    _: Any = Depends(require_permission("observability")),
    server: Any = Depends(get_server),
) -> ClsApplicationItem:
    app = await server.app_runtime.agent_registry.cls_observability.create_application(
        region=body.region,
        application_name=body.application_name,
        access_type=body.access_type,
        logset_id=body.logset_id,
        reuse_existing=body.reuse_existing,
        secret_id=body.secret_id,
        secret_key=body.secret_key,
    )
    return _to_cls_app_item(app)


@router.post("/cls/test", summary="Test Tencent Cloud CLS observability connection")
async def test_cls_connection(
    body: ClsTestBody,
    _: Any = Depends(require_permission("observability")),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    return cast(
        dict[str, Any],
        await server.app_runtime.agent_registry.cls_observability.test_connection(
            region=body.region,
            topic_id=body.topic_id,
            use_internal_endpoint=body.use_internal_endpoint,
            secret_id=body.secret_id,
            secret_key=body.secret_key,
        ),
    )
