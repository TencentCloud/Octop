"""Tencent Cloud CLS (AgentObs) observability integration via Langfuse SDK OTLP export.

Supports two onboarding paths with the customer's Tencent Cloud SecretId / SecretKey:
1. Control plane: create (or discover and reuse) an Agent application in CLS via
   ``CreateAgentApplication`` / ``DescribeAgentApplications`` and extract its trace ``TopicId``.
2. Data plane: configure the Langfuse SDK's ``OTLPSpanExporter`` to push traces to
   ``https://{region}.cls.tencentcs.com/v1/traces`` (or internal ``cls.tencentyun.com``)
   using HTTP Basic Auth (``SecretId:SecretKey``) and the ``topic_id`` header.

Also supports reporting directly to an existing CLS application / ``TopicId`` without
requiring management-plane permissions (``cls:pushLog`` only).
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from octop.infra.crypto.fernet import PURPOSE_SETTINGS, open_secret_bytes, seal_secret_bytes
from octop.infra.db.repos.secrets import SecretRepo
from octop.infra.db.repos.settings import SettingsRepo
from octop.infra.errors import ErrorCode, OctopError

logger = logging.getLogger(__name__)

CLS_ACCESS_TYPES: tuple[str, ...] = ("Langfuse", "Agent")
CLS_DEFAULT_APPLICATION_NAME = "octop"

_REGION_RE = re.compile(r"^[a-z][a-z0-9-]*$")

_KEY_ENABLED = "observability_cls_enabled"
_KEY_REGION = "observability_cls_region"
_KEY_TOPIC_ID = "observability_cls_topic_id"
_KEY_APP_ID = "observability_cls_application_id"
_KEY_APP_NAME = "observability_cls_application_name"
_KEY_ACCESS_TYPE = "observability_cls_access_type"
_KEY_INTERNAL = "observability_cls_use_internal_endpoint"
_KEY_MASK_CONTENT = "observability_cls_mask_content"
_KEY_SECRET_ID_MASKED = "observability_cls_secret_id_masked"

_SECRET_ID_KEY = "cls_observability_secret_id"
_SECRET_KEY_KEY = "cls_observability_secret_key"

_LANGFUSE_CONTENT_ATTRS = frozenset(
    {
        "langfuse.observation.input",
        "langfuse.observation.output",
        "langfuse.trace.input",
        "langfuse.trace.output",
        "input.value",
        "output.value",
        "gen_ai.prompt",
        "gen_ai.completion",
    }
)

_AGENT_GENAI_ATTR_MAP = {
    "session.id": "gen_ai.session.id",
    "user.id": "gen_ai.user.id",
    "langfuse.trace.metadata.agent_id": "gen_ai.agent.id",
    "langfuse.observation.model.name": "gen_ai.request.model",
}


def mask_secret_id(secret_id: str) -> str:
    """Return a display-safe masked preview of a Tencent Cloud SecretId."""
    cleaned = secret_id.strip()
    if not cleaned:
        return ""
    if len(cleaned) <= 8:
        return "*" * len(cleaned)
    return f"{cleaned[:4]}****{cleaned[-4:]}"


def validate_cls_region(region: str) -> str:
    cleaned = region.strip().lower()
    if not cleaned or not _REGION_RE.fullmatch(cleaned):
        raise OctopError(
            ErrorCode.SLASH_BAD_ARGS,
            "Invalid CLS region (expected format like ap-guangzhou)",
        )
    return cleaned


def validate_application_name(name: str) -> str:
    cleaned = name.strip()
    if not cleaned:
        raise OctopError(ErrorCode.SLASH_BAD_ARGS, "application_name must not be empty")
    if "|" in cleaned:
        raise OctopError(ErrorCode.SLASH_BAD_ARGS, "application_name must not contain '|'")
    if len(cleaned) > 64:
        raise OctopError(
            ErrorCode.SLASH_BAD_ARGS,
            "application_name must not exceed 64 characters",
        )
    return cleaned


def validate_access_type(access_type: str) -> str:
    cleaned = access_type.strip()
    if cleaned not in CLS_ACCESS_TYPES:
        raise OctopError(
            ErrorCode.SLASH_BAD_ARGS,
            f"access_type must be one of {', '.join(CLS_ACCESS_TYPES)}",
        )
    return cleaned


def build_cls_host(region: str, *, use_internal_endpoint: bool = False) -> str:
    validated = validate_cls_region(region)
    domain = "cls.tencentyun.com" if use_internal_endpoint else "cls.tencentcs.com"
    return f"https://{validated}.{domain}"


def build_cls_traces_endpoint(region: str, *, use_internal_endpoint: bool = False) -> str:
    return f"{build_cls_host(region, use_internal_endpoint=use_internal_endpoint)}/v1/traces"


def build_cls_basic_auth(secret_id: str, secret_key: str, *, token: str = "") -> str:
    """Build HTTP Basic Authorization value for CLS OTLP ingestion."""
    sid = secret_id.strip()
    skey = secret_key.strip()
    tok = token.strip()
    identity = f"{sid}#{tok}" if tok else sid
    encoded = base64.b64encode(f"{identity}:{skey}".encode()).decode("ascii")
    return f"Basic {encoded}"


@dataclass(frozen=True)
class ClsAgentApplication:
    """Normalized CLS AgentObs application descriptor."""

    application_id: str
    application_name: str
    access_type: str
    region: str
    topic_id: str
    logset_id: str = ""
    log_topics: tuple[dict[str, str], ...] = ()
    created: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "application_id": self.application_id,
            "application_name": self.application_name,
            "access_type": self.access_type,
            "region": self.region,
            "topic_id": self.topic_id,
            "logset_id": self.logset_id,
            "log_topics": list(self.log_topics),
            "created": self.created,
        }


@dataclass(frozen=True)
class ClsObservabilitySettings:
    """Admin-visible Tencent Cloud CLS observability configuration (secrets never exposed)."""

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

    @property
    def configured(self) -> bool:
        return self.enabled and self.can_probe

    @property
    def can_probe(self) -> bool:
        return bool(
            _REGION_RE.fullmatch(self.region or "")
            and self.access_type in CLS_ACCESS_TYPES
            and self.topic_id
            and self.secret_id_set
            and self.secret_key_set
        )

    @property
    def endpoint(self) -> str:
        if not self.region or not _REGION_RE.fullmatch(self.region):
            return ""
        return build_cls_traces_endpoint(
            self.region,
            use_internal_endpoint=self.use_internal_endpoint,
        )


def _extract_log_topics(raw_topics: Any) -> tuple[tuple[dict[str, str], ...], str]:
    """Normalize LogTopics from SDK models or raw dicts and extract the trace TopicId."""
    items: list[dict[str, str]] = []
    if isinstance(raw_topics, list):
        for entry in raw_topics:
            if isinstance(entry, dict):
                tid = str(entry.get("TopicId") or "").strip()
                flag = str(entry.get("Flag") or "").strip()
            else:
                tid = str(getattr(entry, "TopicId", "") or "").strip()
                flag = str(getattr(entry, "Flag", "") or "").strip()
            if tid:
                items.append({"topic_id": tid, "flag": flag})

    trace_topic_id = ""
    for item in items:
        if item["flag"].lower() == "trace":
            trace_topic_id = item["topic_id"]
            break
    if not trace_topic_id and items:
        trace_topic_id = items[0]["topic_id"]
    return tuple(items), trace_topic_id


def _build_cls_client(
    region: str,
    secret_id: str,
    secret_key: str,
    *,
    token: str = "",
) -> Any:
    """Construct a Tencent Cloud CLS v20201016 API client."""
    from tencentcloud.cls.v20201016 import cls_client  # noqa: PLC0415
    from tencentcloud.common.credential import Credential  # noqa: PLC0415
    from tencentcloud.common.profile.client_profile import ClientProfile  # noqa: PLC0415
    from tencentcloud.common.profile.http_profile import HttpProfile  # noqa: PLC0415

    cred = Credential(secret_id.strip(), secret_key.strip(), token.strip() or None)
    http_profile = HttpProfile(endpoint="cls.tencentcloudapi.com", reqTimeout=15)
    client_profile = ClientProfile(httpProfile=http_profile)
    return cls_client.ClsClient(cred, region, client_profile)


def _call_cls_action(client: Any, action: str, params: dict[str, Any]) -> dict[str, Any]:
    """Invoke a CLS API action, supporting both typed SDK methods and raw fallback."""
    from tencentcloud.cls.v20201016 import models as cls_models  # noqa: PLC0415

    method = getattr(client, action, None)
    req_cls = getattr(cls_models, f"{action}Request", None)
    if callable(method) and req_cls is not None:
        req = req_cls()
        req.from_json_string(json.dumps(params))
        resp = method(req)
        return dict(json.loads(resp.to_json_string()))

    raw = client.call(action, params)
    parsed = json.loads(raw)
    return dict(parsed.get("Response") or {})


def list_agent_applications(
    region: str,
    secret_id: str,
    secret_key: str,
    *,
    access_type: str | None = None,
    application_name: str | None = None,
    token: str = "",
    limit: int = 100,
) -> list[ClsAgentApplication]:
    """List existing CLS AgentObs applications in the target region."""
    from tencentcloud.common.exception.tencent_cloud_sdk_exception import (  # noqa: PLC0415
        TencentCloudSDKException,
    )

    validated_region = validate_cls_region(region)
    filters: list[dict[str, Any]] = []
    if access_type:
        filters.append({"Key": "accessType", "Values": [validate_access_type(access_type)]})
    if application_name and application_name.strip():
        filters.append({"Key": "applicationName", "Values": [application_name.strip()]})

    params: dict[str, Any] = {"Offset": 0, "Limit": max(1, min(int(limit), 100))}
    if filters:
        params["Filters"] = filters

    client = _build_cls_client(validated_region, secret_id, secret_key, token=token)
    try:
        response = _call_cls_action(client, "DescribeAgentApplications", params)
    except TencentCloudSDKException as exc:
        raise OctopError(
            ErrorCode.INTERNAL_ERROR,
            f"CLS DescribeAgentApplications failed ({exc.code}): {exc.message}",
        ) from exc
    except Exception as exc:  # noqa: BLE001
        raise OctopError(
            ErrorCode.INTERNAL_ERROR,
            f"CLS DescribeAgentApplications failed: {exc}",
        ) from exc

    apps: list[ClsAgentApplication] = []
    for info in response.get("Infos") or []:
        if not isinstance(info, dict):
            continue
        topics, trace_topic_id = _extract_log_topics(info.get("LogTopics"))
        apps.append(
            ClsAgentApplication(
                application_id=str(info.get("ApplicationId") or "").strip(),
                application_name=str(info.get("ApplicationName") or "").strip(),
                access_type=str(info.get("AccessType") or "").strip(),
                region=str(info.get("Region") or validated_region).strip(),
                topic_id=trace_topic_id,
                logset_id=str(info.get("LogsetId") or "").strip(),
                log_topics=topics,
                created=False,
            )
        )
    return apps


def create_agent_application(
    region: str,
    secret_id: str,
    secret_key: str,
    *,
    application_name: str,
    access_type: str = "Langfuse",
    logset_id: str | None = None,
    token: str = "",
) -> ClsAgentApplication:
    """Create a CLS AgentObs application via ``CreateAgentApplication`` and return its TopicId."""
    from tencentcloud.common.exception.tencent_cloud_sdk_exception import (  # noqa: PLC0415
        TencentCloudSDKException,
    )

    validated_region = validate_cls_region(region)
    validated_name = validate_application_name(application_name)
    validated_access_type = validate_access_type(access_type)

    params: dict[str, Any] = {
        "ApplicationName": validated_name,
        "AccessType": validated_access_type,
    }
    if logset_id and logset_id.strip():
        params["LogsetId"] = logset_id.strip()

    client = _build_cls_client(validated_region, secret_id, secret_key, token=token)
    try:
        response = _call_cls_action(client, "CreateAgentApplication", params)
    except TencentCloudSDKException as exc:
        raise OctopError(
            ErrorCode.INTERNAL_ERROR,
            f"CLS CreateAgentApplication failed ({exc.code}): {exc.message}",
        ) from exc
    except Exception as exc:  # noqa: BLE001
        raise OctopError(
            ErrorCode.INTERNAL_ERROR,
            f"CLS CreateAgentApplication failed: {exc}",
        ) from exc

    app_id = str(response.get("ApplicationId") or "").strip()
    topics, trace_topic_id = _extract_log_topics(response.get("LogTopics"))
    if not trace_topic_id:
        raise OctopError(
            ErrorCode.INTERNAL_ERROR,
            "CLS CreateAgentApplication succeeded but did not return a trace TopicId",
        )
    return ClsAgentApplication(
        application_id=app_id,
        application_name=validated_name,
        access_type=validated_access_type,
        region=validated_region,
        topic_id=trace_topic_id,
        logset_id=(logset_id or "").strip(),
        log_topics=topics,
        created=True,
    )


def ensure_agent_application(
    region: str,
    secret_id: str,
    secret_key: str,
    *,
    application_name: str,
    access_type: str = "Langfuse",
    logset_id: str | None = None,
    token: str = "",
) -> ClsAgentApplication:
    """Reuse an existing CLS application with matching name/access_type, or create a new one."""
    validated_region = validate_cls_region(region)
    validated_name = validate_application_name(application_name)
    validated_access_type = validate_access_type(access_type)

    existing = list_agent_applications(
        validated_region,
        secret_id,
        secret_key,
        access_type=validated_access_type,
        application_name=validated_name,
        token=token,
    )
    for app in existing:
        if (
            app.application_name == validated_name
            and app.access_type == validated_access_type
            and app.topic_id
        ):
            return app

    return create_agent_application(
        validated_region,
        secret_id,
        secret_key,
        application_name=validated_name,
        access_type=validated_access_type,
        logset_id=logset_id,
        token=token,
    )


def verify_cls_connection(
    region: str,
    secret_id: str,
    secret_key: str,
    *,
    topic_id: str = "",
    use_internal_endpoint: bool = False,
    token: str = "",
) -> dict[str, Any]:
    """Verify CLS credentials (control plane) and/or OTLP trace ingestion (data plane).

    Supports push-only sub-accounts that lack ``DescribeAgentApplications`` permission
    when ``topic_id`` is provided: if the management API returns UnauthorizedOperation
    but the OTLP ``/v1/traces`` probe succeeds, verification still passes.
    """
    from tencentcloud.common.exception.tencent_cloud_sdk_exception import (  # noqa: PLC0415
        TencentCloudSDKException,
    )

    try:
        validated_region = validate_cls_region(region)
    except OctopError as exc:
        return {"ok": False, "error": str(exc)}

    endpoint = build_cls_traces_endpoint(
        validated_region,
        use_internal_endpoint=use_internal_endpoint,
    )
    cleaned_topic = topic_id.strip()

    api_ok: bool | None = None
    api_error: str | None = None
    client = _build_cls_client(validated_region, secret_id, secret_key, token=token)
    try:
        _call_cls_action(client, "DescribeAgentApplications", {"Offset": 0, "Limit": 1})
        api_ok = True
    except TencentCloudSDKException as exc:
        code = str(getattr(exc, "code", "") or "")
        if "UnauthorizedOperation" in code:
            # Push-only sub-account (cls:pushLog only) — defer final verdict to OTLP probe.
            api_ok = None
            api_error = f"{code}: {exc.message}"
        else:
            api_ok = False
            api_error = f"{code}: {exc.message}" if code else str(exc)
            if "AuthFailure" in code:
                return {
                    "ok": False,
                    "api_ok": False,
                    "otlp_ok": False,
                    "endpoint": endpoint,
                    "error": f"authentication failed ({api_error})",
                }
    except Exception as exc:  # noqa: BLE001
        api_ok = False
        api_error = str(exc)

    if not cleaned_topic:
        if api_ok:
            return {
                "ok": True,
                "api_ok": True,
                "otlp_ok": None,
                "endpoint": endpoint,
            }
        return {
            "ok": False,
            "api_ok": api_ok,
            "otlp_ok": None,
            "endpoint": endpoint,
            "error": api_error or "CLS API check failed",
        }

    # Probe OTLP /v1/traces ingestion with an empty valid ExportTraceServiceRequest protobuf.
    from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import (  # noqa: PLC0415
        ExportTraceServiceRequest,
    )

    payload = ExportTraceServiceRequest().SerializeToString()
    req = urllib.request.Request(  # noqa: S310
        endpoint,
        data=payload,
        headers={
            "Authorization": build_cls_basic_auth(secret_id, secret_key, token=token),
            "topic_id": cleaned_topic,
            "Content-Type": "application/x-protobuf",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:  # noqa: S310
            status = int(resp.status)
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode("utf-8", errors="replace").strip()[:200]
        except Exception:  # noqa: BLE001
            detail = ""
        if exc.code in {401, 403}:
            err = f"OTLP authentication/permission failed (HTTP {exc.code})"
        else:
            err = f"OTLP endpoint returned HTTP {exc.code}"
        if detail:
            err = f"{err}: {detail}"
        return {
            "ok": False,
            "api_ok": api_ok,
            "otlp_ok": False,
            "endpoint": endpoint,
            "error": err,
        }
    except urllib.error.URLError as exc:
        return {
            "ok": False,
            "api_ok": api_ok,
            "otlp_ok": False,
            "endpoint": endpoint,
            "error": f"OTLP endpoint unreachable: {exc.reason}",
        }

    if 200 <= status < 300:
        return {
            "ok": True,
            "api_ok": api_ok,
            "otlp_ok": True,
            "endpoint": endpoint,
        }
    return {
        "ok": False,
        "api_ok": api_ok,
        "otlp_ok": False,
        "endpoint": endpoint,
        "error": f"OTLP endpoint returned HTTP {status}",
    }


def _mask_langfuse_content(*, params: Any) -> Any:
    """Strip prompt/response content while keeping Langfuse observation metadata intact."""
    from langfuse.types import MaskOtelSpansResult, OtelSpanPatch  # noqa: PLC0415

    patches = {}
    for identifier, span in params.spans.items():
        to_delete = tuple(key for key in span.attributes if key in _LANGFUSE_CONTENT_ATTRS)
        if to_delete:
            patches[identifier] = OtelSpanPatch(delete_attributes=to_delete)
    return MaskOtelSpansResult(span_patches=patches)


def _agent_genai_attributes(*, params: Any) -> Any:
    """Translate Langfuse spans to OpenTelemetry GenAI monitoring attributes without payloads."""
    from langfuse.types import MaskOtelSpansResult, OtelSpanPatch  # noqa: PLC0415

    patches = {}
    for identifier, span in params.spans.items():
        original = span.attributes
        attributes: dict[str, Any] = {
            target: original[source]
            for source, target in _AGENT_GENAI_ATTR_MAP.items()
            if source in original
        }
        attributes["gen_ai.agent.type"] = "octop"
        attributes["gen_ai.turn.id"] = span.trace_id

        observation_type = original.get("langfuse.observation.type")
        if observation_type == "generation":
            attributes["gen_ai.span.kind"] = "chat"
            attributes["gen_ai.operation.name"] = "chat"
            usage_details = original.get("langfuse.observation.usage_details")
            if isinstance(usage_details, str):
                try:
                    usage = json.loads(usage_details)
                except ValueError:
                    usage = None
                if isinstance(usage, dict):
                    for key in ("input", "output", "total"):
                        value = usage.get(key)
                        if type(value) is int:
                            attributes[f"gen_ai.usage.{key}_tokens"] = value
        elif observation_type == "tool":
            attributes["gen_ai.span.kind"] = "tool"
            attributes["gen_ai.operation.name"] = "execute_tool"
            attributes["gen_ai.tool.name"] = span.name
            attributes["gen_ai.tool.call.id"] = span.span_id
            attributes["gen_ai.tool.type"] = "function"
        elif span.parent_span_id is None:
            attributes["gen_ai.span.kind"] = "entry"
            attributes["gen_ai.operation.name"] = "enter_application"
            source = original.get("langfuse.trace.metadata.source")
            if source:
                attributes["gen_ai.entry.type"] = source

        patches[identifier] = OtelSpanPatch(
            set_attributes=attributes,
            delete_attributes=tuple(original),
        )
    return MaskOtelSpansResult(span_patches=patches)


def register_cls_langfuse_client(
    *,
    region: str,
    topic_id: str,
    secret_id: str,
    secret_key: str,
    service_name: str = CLS_DEFAULT_APPLICATION_NAME,
    access_type: str = "Langfuse",
    use_internal_endpoint: bool = False,
    mask_content: bool = False,
    token: str = "",
) -> Any:
    """Register a Langfuse SDK client exporting OTLP traces to Tencent Cloud CLS.

    Returns an ``octop_harness.observability.langfuse.LangfuseConfig`` whose ``public_key``
    matches the registered client so ``LangfuseTracer`` reuses the CLS ``OTLPSpanExporter``.
    """
    from langfuse import Langfuse  # noqa: PLC0415
    from octop_harness.observability.langfuse import LangfuseConfig  # noqa: PLC0415
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import (  # noqa: PLC0415
        OTLPSpanExporter,
    )
    from opentelemetry.sdk.resources import Resource  # noqa: PLC0415
    from opentelemetry.sdk.trace import TracerProvider  # noqa: PLC0415

    validated_region = validate_cls_region(region)
    validated_access = validate_access_type(access_type)
    cleaned_topic = topic_id.strip()
    cleaned_service = service_name.strip() or CLS_DEFAULT_APPLICATION_NAME

    host = build_cls_host(validated_region, use_internal_endpoint=use_internal_endpoint)
    endpoint = f"{host}/v1/traces"
    authorization = build_cls_basic_auth(secret_id, secret_key, token=token)

    exporter = OTLPSpanExporter(
        endpoint=endpoint,
        headers={"Authorization": authorization, "topic_id": cleaned_topic},
        timeout=5,
    )
    config = LangfuseConfig(
        enabled=True,
        public_key=f"pk-octop-cls-{uuid4().hex}",
        secret_key="sk-octop-cls-placeholder",
        host=host,
    )
    mask_fn = None
    if validated_access == "Agent":
        mask_fn = _agent_genai_attributes
    elif mask_content:
        mask_fn = _mask_langfuse_content

    os.environ.setdefault("LANGFUSE_MEDIA_UPLOAD_ENABLED", "false")
    Langfuse(
        public_key=config.public_key,
        secret_key=config.secret_key,
        base_url=config.host,
        tracer_provider=TracerProvider(resource=Resource.create({"service.name": cleaned_service})),
        span_exporter=exporter,
        mask_otel_spans=mask_fn,
    )
    return config


def env_cls_enabled() -> bool:
    """Return True when deployment-level env vars opt in to Tencent Cloud CLS/AgentObs."""
    return os.environ.get("OCTOP_AGENTOBS_ENABLED", "").strip().lower() in {"1", "true", "yes"}


def _env_cls_credentials() -> tuple[str, str, str]:
    return (
        os.environ.get("TENCENTCLOUD_SECRET_ID", "").strip(),
        os.environ.get("TENCENTCLOUD_SECRET_KEY", "").strip(),
        os.environ.get("TENCENTCLOUD_TOKEN", "").strip(),
    )


def env_cls_settings() -> ClsObservabilitySettings:
    """Read the deployment settings without registering a tracer or exposing credentials."""
    secret_id, secret_key, _ = _env_cls_credentials()
    access_type = os.environ.get("CLS_ACCESS_TYPE", "Langfuse").strip() or "Langfuse"
    service_name = (
        os.environ.get("CLS_SERVICE_NAME", "").strip()
        or os.environ.get("SERVICE_NAME", "").strip()
        or CLS_DEFAULT_APPLICATION_NAME
    )
    use_internal = os.environ.get("CLS_USE_INTERNAL_ENDPOINT", "").strip().lower() in {
        "1",
        "true",
        "yes",
    }
    mask_content = os.environ.get("CLS_MASK_CONTENT", "").strip().lower() in {
        "1",
        "true",
        "yes",
    }

    return ClsObservabilitySettings(
        enabled=env_cls_enabled(),
        region=os.environ.get("CLS_DEFAULT_REGION", "").strip(),
        topic_id=os.environ.get("CLS_TOPIC_ID", "").strip(),
        application_id="",
        application_name=service_name,
        access_type=access_type,
        use_internal_endpoint=use_internal,
        mask_content=mask_content,
        secret_id_masked=mask_secret_id(secret_id),
        secret_id_set=bool(secret_id),
        secret_key_set=bool(secret_key),
    )


async def probe_env_cls_connection(cfg: ClsObservabilitySettings) -> dict[str, Any]:
    sid, skey, token = _env_cls_credentials()
    return await asyncio.to_thread(
        verify_cls_connection,
        cfg.region,
        sid,
        skey,
        topic_id=cfg.topic_id,
        use_internal_endpoint=cfg.use_internal_endpoint,
        token=token,
    )


def env_cls_harness_config() -> Any | None:
    """Build a CLS ``LangfuseConfig`` from deployment environment variables, or ``None``."""
    if not env_cls_enabled():
        return None

    from octop_harness.observability.langfuse import LangfuseConfig  # noqa: PLC0415

    cfg = env_cls_settings()
    if not cfg.configured:
        logger.error(
            "Tencent Cloud CLS tracing disabled: set CLS_DEFAULT_REGION, CLS_TOPIC_ID, "
            "TENCENTCLOUD_SECRET_ID and TENCENTCLOUD_SECRET_KEY"
        )
        return LangfuseConfig(enabled=False)

    secret_id, secret_key, token = _env_cls_credentials()
    return register_cls_langfuse_client(
        region=cfg.region,
        topic_id=cfg.topic_id,
        secret_id=secret_id,
        secret_key=secret_key,
        service_name=cfg.application_name,
        access_type=cfg.access_type,
        use_internal_endpoint=cfg.use_internal_endpoint,
        mask_content=cfg.mask_content,
        token=token,
    )


class ClsObservabilitySettingsStore:
    """Read/write Tencent Cloud CLS observability settings in settings + secrets tables."""

    def __init__(self, *, settings_repo: SettingsRepo, secret_repo: SecretRepo) -> None:
        self._settings = settings_repo
        self._secrets = secret_repo

    def load(self) -> ClsObservabilitySettings:
        enabled = (self._settings.get(_KEY_ENABLED) or "").lower() in {"1", "true", "yes"}
        region = (self._settings.get(_KEY_REGION) or "").strip().lower()
        topic_id = (self._settings.get(_KEY_TOPIC_ID) or "").strip()
        application_id = (self._settings.get(_KEY_APP_ID) or "").strip()
        application_name = (
            self._settings.get(_KEY_APP_NAME) or CLS_DEFAULT_APPLICATION_NAME
        ).strip() or CLS_DEFAULT_APPLICATION_NAME
        raw_access = (self._settings.get(_KEY_ACCESS_TYPE) or "Langfuse").strip()
        access_type = raw_access if raw_access in CLS_ACCESS_TYPES else "Langfuse"
        use_internal = (self._settings.get(_KEY_INTERNAL) or "").lower() in {"1", "true", "yes"}
        mask_content = (self._settings.get(_KEY_MASK_CONTENT) or "").lower() in {"1", "true", "yes"}
        secret_id_set = self._secrets.get(_SECRET_ID_KEY) is not None
        secret_key_set = self._secrets.get(_SECRET_KEY_KEY) is not None
        secret_id_masked = (
            (self._settings.get(_KEY_SECRET_ID_MASKED) or "").strip() if secret_id_set else ""
        )
        return ClsObservabilitySettings(
            enabled=enabled,
            region=region,
            topic_id=topic_id,
            application_id=application_id,
            application_name=application_name,
            access_type=access_type,
            use_internal_endpoint=use_internal,
            mask_content=mask_content,
            secret_id_masked=secret_id_masked,
            secret_id_set=secret_id_set,
            secret_key_set=secret_key_set,
        )

    def _seal_secret(self, name: str, value: str) -> None:
        encoded = seal_secret_bytes(self._secrets, PURPOSE_SETTINGS, value.encode("utf-8"))
        existing = self._secrets.get(name)
        if existing is not None:
            self._secrets.rotate(name, encoded)
        else:
            self._secrets.get_or_create(name, lambda: encoded)

    def _read_secret(self, name: str) -> str | None:
        raw = self._secrets.get(name)
        if raw is None:
            return None
        return open_secret_bytes(self._secrets, PURPOSE_SETTINGS, raw).decode("utf-8")

    def resolve_credentials(
        self,
        *,
        secret_id: str | None = None,
        secret_key: str | None = None,
    ) -> tuple[str, str]:
        sid = (secret_id or "").strip() or (self._read_secret(_SECRET_ID_KEY) or "").strip()
        skey = (secret_key or "").strip() or (self._read_secret(_SECRET_KEY_KEY) or "").strip()
        if not sid or not skey:
            raise OctopError(
                ErrorCode.SLASH_BAD_ARGS,
                "Tencent Cloud SecretId and SecretKey are required",
            )
        return sid, skey

    def save(
        self,
        *,
        enabled: bool,
        region: str,
        topic_id: str,
        application_id: str = "",
        application_name: str = CLS_DEFAULT_APPLICATION_NAME,
        access_type: str = "Langfuse",
        use_internal_endpoint: bool = False,
        mask_content: bool = False,
        secret_id: str | None = None,
        secret_key: str | None = None,
    ) -> ClsObservabilitySettings:
        cleaned_region = region.strip().lower()
        cleaned_topic = topic_id.strip()
        cleaned_app_id = application_id.strip()
        cleaned_app_name = application_name.strip() or CLS_DEFAULT_APPLICATION_NAME
        cleaned_access = validate_access_type(access_type or "Langfuse")
        cleaned_sid = secret_id.strip() if secret_id else None
        cleaned_skey = secret_key.strip() if secret_key else None

        if enabled:
            validate_cls_region(cleaned_region)
            if not cleaned_topic:
                raise OctopError(
                    ErrorCode.SLASH_BAD_ARGS,
                    "topic_id is required when Tencent Cloud CLS is enabled",
                )
            if not (cleaned_sid or self._secrets.get(_SECRET_ID_KEY) is not None):
                raise OctopError(
                    ErrorCode.SLASH_BAD_ARGS,
                    "secret_id is required when Tencent Cloud CLS is enabled",
                )
            if not (cleaned_skey or self._secrets.get(_SECRET_KEY_KEY) is not None):
                raise OctopError(
                    ErrorCode.SLASH_BAD_ARGS,
                    "secret_key is required when Tencent Cloud CLS is enabled",
                )
        elif cleaned_region:
            validate_cls_region(cleaned_region)

        self._settings.set(_KEY_ENABLED, "true" if enabled else "false")
        self._settings.set(_KEY_REGION, cleaned_region)
        self._settings.set(_KEY_TOPIC_ID, cleaned_topic)
        self._settings.set(_KEY_APP_ID, cleaned_app_id)
        self._settings.set(_KEY_APP_NAME, cleaned_app_name)
        self._settings.set(_KEY_ACCESS_TYPE, cleaned_access)
        self._settings.set(_KEY_INTERNAL, "true" if use_internal_endpoint else "false")
        self._settings.set(_KEY_MASK_CONTENT, "true" if mask_content else "false")
        if cleaned_sid:
            self._seal_secret(_SECRET_ID_KEY, cleaned_sid)
            self._settings.set(_KEY_SECRET_ID_MASKED, mask_secret_id(cleaned_sid))
        if cleaned_skey:
            self._seal_secret(_SECRET_KEY_KEY, cleaned_skey)
        return self.load()

    async def list_applications(
        self,
        *,
        region: str | None = None,
        access_type: str | None = None,
        application_name: str | None = None,
        secret_id: str | None = None,
        secret_key: str | None = None,
    ) -> list[ClsAgentApplication]:
        stored = self.load()
        target_region = validate_cls_region(region or stored.region)
        sid, skey = self.resolve_credentials(secret_id=secret_id, secret_key=secret_key)
        return await asyncio.to_thread(
            list_agent_applications,
            target_region,
            sid,
            skey,
            access_type=access_type,
            application_name=application_name,
        )

    async def create_application(
        self,
        *,
        region: str | None = None,
        application_name: str | None = None,
        access_type: str = "Langfuse",
        logset_id: str | None = None,
        reuse_existing: bool = True,
        secret_id: str | None = None,
        secret_key: str | None = None,
    ) -> ClsAgentApplication:
        stored = self.load()
        target_region = validate_cls_region(region or stored.region)
        target_name = validate_application_name(application_name or stored.application_name)
        target_access = validate_access_type(access_type or stored.access_type)
        sid, skey = self.resolve_credentials(secret_id=secret_id, secret_key=secret_key)
        fn = ensure_agent_application if reuse_existing else create_agent_application
        return await asyncio.to_thread(
            fn,
            target_region,
            sid,
            skey,
            application_name=target_name,
            access_type=target_access,
            logset_id=logset_id,
        )

    async def test_connection(
        self,
        *,
        region: str | None = None,
        topic_id: str | None = None,
        use_internal_endpoint: bool | None = None,
        secret_id: str | None = None,
        secret_key: str | None = None,
    ) -> dict[str, Any]:
        stored = self.load()
        target_region = validate_cls_region(region or stored.region)
        target_topic = (topic_id if topic_id is not None else stored.topic_id).strip()
        internal = (
            stored.use_internal_endpoint
            if use_internal_endpoint is None
            else bool(use_internal_endpoint)
        )
        sid, skey = self.resolve_credentials(secret_id=secret_id, secret_key=secret_key)
        return await asyncio.to_thread(
            verify_cls_connection,
            target_region,
            sid,
            skey,
            topic_id=target_topic,
            use_internal_endpoint=internal,
        )

    def harness_config(self) -> Any | None:
        """Build and register a CLS ``LangfuseConfig`` for ``HarnessAgentManager``."""
        view = self.load()
        if not view.configured:
            return None
        sid = self._read_secret(_SECRET_ID_KEY)
        skey = self._read_secret(_SECRET_KEY_KEY)
        if not sid or not skey:
            return None
        return register_cls_langfuse_client(
            region=view.region,
            topic_id=view.topic_id,
            secret_id=sid,
            secret_key=skey,
            service_name=view.application_name,
            access_type=view.access_type,
            use_internal_endpoint=view.use_internal_endpoint,
            mask_content=view.mask_content,
        )
