"""Unit tests for Tencent Cloud CLS (AgentObs) observability integration."""

from __future__ import annotations

import base64
from pathlib import Path
from types import SimpleNamespace
from unittest import mock
from uuid import uuid4

import pytest
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.outputs import ChatGeneration, LLMResult
from langfuse import get_client
from octop_harness.observability.langfuse import LangfuseTracer
from octop_harness.request import ChatRequest
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest
from requests import PreparedRequest, Response, Session
from tencentcloud.common.exception.tencent_cloud_sdk_exception import TencentCloudSDKException

from octop.infra.agents.settings.cls_observability import (
    ClsAgentApplication,
    ClsObservabilitySettingsStore,
    build_cls_basic_auth,
    create_agent_application,
    ensure_agent_application,
    env_cls_harness_config,
    list_agent_applications,
    mask_secret_id,
    register_cls_langfuse_client,
    verify_cls_connection,
)
from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.repos.secrets import SecretRepo
from octop.infra.db.repos.settings import SettingsRepo
from octop.infra.errors import OctopError


@pytest.fixture
def cls_store(tmp_path: Path) -> ClsObservabilitySettingsStore:
    db = SqlitePool(tmp_path / "octop.db")
    run_migrations(db)
    return ClsObservabilitySettingsStore(
        settings_repo=SettingsRepo(db),
        secret_repo=SecretRepo(db),
    )


def test_mask_secret_id() -> None:
    assert mask_secret_id("") == ""
    assert mask_secret_id("short") == "*****"
    assert mask_secret_id("AKID1234567890ABCD") == "AKID****ABCD"


def test_cls_settings_roundtrip_and_existing_topic_id(
    cls_store: ClsObservabilitySettingsStore,
) -> None:
    saved = cls_store.save(
        enabled=True,
        region="AP-Guangzhou",
        topic_id="topic-existing-001",
        application_name="my-octop",
        access_type="Langfuse",
        secret_id="AKID_CUSTOMER_9999",
        secret_key="SK_CUSTOMER_SECRET",
    )
    assert saved.enabled is True
    assert saved.region == "ap-guangzhou"
    assert saved.topic_id == "topic-existing-001"
    assert saved.application_name == "my-octop"
    assert saved.access_type == "Langfuse"
    assert saved.secret_id_set is True
    assert saved.secret_key_set is True
    assert saved.secret_id_masked == "AKID****9999"
    assert saved.configured is True
    assert saved.endpoint == "https://ap-guangzhou.cls.tencentcs.com/v1/traces"

    # Secrets must not be stored in plaintext in the settings table.
    assert cls_store._settings.get("observability_cls_secret_id_masked") == "AKID****9999"
    sid, skey = cls_store.resolve_credentials()
    assert sid == "AKID_CUSTOMER_9999"
    assert skey == "SK_CUSTOMER_SECRET"

    # Updating non-secret fields preserves existing encrypted credentials.
    updated = cls_store.save(
        enabled=True,
        region="ap-shanghai",
        topic_id="topic-existing-002",
        use_internal_endpoint=True,
        mask_content=True,
    )
    assert updated.region == "ap-shanghai"
    assert updated.endpoint == "https://ap-shanghai.cls.tencentyun.com/v1/traces"
    assert updated.mask_content is True
    assert cls_store.resolve_credentials() == ("AKID_CUSTOMER_9999", "SK_CUSTOMER_SECRET")


def test_cls_settings_validation(cls_store: ClsObservabilitySettingsStore) -> None:
    with pytest.raises(OctopError, match="topic_id"):
        cls_store.save(
            enabled=True,
            region="ap-guangzhou",
            topic_id="",
            secret_id="AKID1234567890",
            secret_key="SK123456",
        )
    with pytest.raises(OctopError, match="secret_id"):
        cls_store.save(
            enabled=True,
            region="ap-guangzhou",
            topic_id="topic-1",
        )
    with pytest.raises(OctopError, match="Invalid CLS region"):
        cls_store.save(
            enabled=True,
            region="BAD REGION!",
            topic_id="topic-1",
            secret_id="AKID1234567890",
            secret_key="SK123456",
        )


def test_create_agent_application_extracts_trace_topic() -> None:
    captured: list[tuple[str, dict[str, object]]] = []

    def fake_call(client: object, action: str, params: dict[str, object]) -> dict[str, object]:
        captured.append((action, params))
        return {
            "ApplicationId": "app-cls-123",
            "LogTopics": [
                {"TopicId": "topic-other-1", "Flag": "metric"},
                {"TopicId": "topic-trace-456", "Flag": "trace"},
            ],
            "RequestId": "req-1",
        }

    with (
        mock.patch(
            "octop.infra.agents.settings.cls_observability._build_cls_client",
            return_value=object(),
        ),
        mock.patch(
            "octop.infra.agents.settings.cls_observability._call_cls_action",
            side_effect=fake_call,
        ),
    ):
        app = create_agent_application(
            "ap-guangzhou",
            "AKID_TEST",
            "SK_TEST",
            application_name="octop-prod",
            access_type="Langfuse",
            logset_id="logset-789",
        )

    assert captured == [
        (
            "CreateAgentApplication",
            {
                "ApplicationName": "octop-prod",
                "AccessType": "Langfuse",
                "LogsetId": "logset-789",
            },
        )
    ]
    assert app.application_id == "app-cls-123"
    assert app.topic_id == "topic-trace-456"
    assert app.created is True


def test_create_agent_application_wraps_sdk_error() -> None:
    with (
        mock.patch(
            "octop.infra.agents.settings.cls_observability._build_cls_client",
            return_value=object(),
        ),
        mock.patch(
            "octop.infra.agents.settings.cls_observability._call_cls_action",
            side_effect=TencentCloudSDKException(code="AuthFailure", message="bad key"),
        ),
        pytest.raises(OctopError, match="AuthFailure"),
    ):
        create_agent_application(
            "ap-guangzhou",
            "AKID_BAD",
            "SK_BAD",
            application_name="octop",
        )


def test_ensure_agent_application_reuses_existing_or_creates() -> None:
    calls: list[str] = []

    def fake_call_reuse(
        client: object, action: str, params: dict[str, object]
    ) -> dict[str, object]:
        calls.append(action)
        if action == "DescribeAgentApplications":
            return {
                "Infos": [
                    {
                        "ApplicationId": "app-existing",
                        "ApplicationName": "octop",
                        "AccessType": "Langfuse",
                        "Region": "ap-guangzhou",
                        "LogTopics": [{"TopicId": "topic-existing-trace", "Flag": "trace"}],
                    }
                ],
                "Total": 1,
            }
        raise AssertionError(f"unexpected action {action}")

    with (
        mock.patch(
            "octop.infra.agents.settings.cls_observability._build_cls_client",
            return_value=object(),
        ),
        mock.patch(
            "octop.infra.agents.settings.cls_observability._call_cls_action",
            side_effect=fake_call_reuse,
        ),
    ):
        app = ensure_agent_application(
            "ap-guangzhou",
            "AKID_TEST",
            "SK_TEST",
            application_name="octop",
            access_type="Langfuse",
        )

    assert calls == ["DescribeAgentApplications"]
    assert app.application_id == "app-existing"
    assert app.topic_id == "topic-existing-trace"
    assert app.created is False

    calls.clear()

    def fake_call_create(
        client: object, action: str, params: dict[str, object]
    ) -> dict[str, object]:
        calls.append(action)
        if action == "DescribeAgentApplications":
            return {"Infos": [], "Total": 0}
        return {
            "ApplicationId": "app-new",
            "LogTopics": [{"TopicId": "topic-new-trace", "Flag": "trace"}],
        }

    with (
        mock.patch(
            "octop.infra.agents.settings.cls_observability._build_cls_client",
            return_value=object(),
        ),
        mock.patch(
            "octop.infra.agents.settings.cls_observability._call_cls_action",
            side_effect=fake_call_create,
        ),
    ):
        created = ensure_agent_application(
            "ap-guangzhou",
            "AKID_TEST",
            "SK_TEST",
            application_name="octop-new",
            access_type="Langfuse",
        )

    assert calls == ["DescribeAgentApplications", "CreateAgentApplication"]
    assert created.application_id == "app-new"
    assert created.topic_id == "topic-new-trace"
    assert created.created is True


def test_list_agent_applications_parses_results() -> None:
    def fake_call(client: object, action: str, params: dict[str, object]) -> dict[str, object]:
        assert action == "DescribeAgentApplications"
        return {
            "Infos": [
                {
                    "ApplicationId": "app-1",
                    "ApplicationName": "octop-a",
                    "AccessType": "Langfuse",
                    "Region": "ap-shanghai",
                    "LogsetId": "ls-1",
                    "LogTopics": [{"TopicId": "topic-a", "Flag": "trace"}],
                }
            ],
            "Total": 1,
        }

    with (
        mock.patch(
            "octop.infra.agents.settings.cls_observability._build_cls_client",
            return_value=object(),
        ),
        mock.patch(
            "octop.infra.agents.settings.cls_observability._call_cls_action",
            side_effect=fake_call,
        ),
    ):
        apps = list_agent_applications("ap-shanghai", "AKID", "SK")

    assert len(apps) == 1
    assert apps[0].application_id == "app-1"
    assert apps[0].topic_id == "topic-a"
    assert apps[0].logset_id == "ls-1"


def test_verify_cls_connection_supports_push_only_subaccount() -> None:
    def fake_call(client: object, action: str, params: dict[str, object]) -> dict[str, object]:
        raise TencentCloudSDKException(
            code="AuthFailure.UnauthorizedOperation",
            message="not allowed to describe apps",
        )

    class _FakeResp:
        status = 200

        def __enter__(self) -> _FakeResp:
            return self

        def __exit__(self, *args: object) -> None:
            return None

    def fake_urlopen(req: object, timeout: float = 10) -> _FakeResp:
        assert req.full_url == "https://ap-guangzhou.cls.tencentcs.com/v1/traces"  # type: ignore[attr-defined]
        assert req.headers["Topic_id"] == "existing-topic-1"  # type: ignore[attr-defined]
        assert req.headers["Authorization"] == build_cls_basic_auth("AKID_PUSH", "SK_PUSH")  # type: ignore[attr-defined]
        return _FakeResp()

    with (
        mock.patch(
            "octop.infra.agents.settings.cls_observability._build_cls_client",
            return_value=object(),
        ),
        mock.patch(
            "octop.infra.agents.settings.cls_observability._call_cls_action",
            side_effect=fake_call,
        ),
        mock.patch("urllib.request.urlopen", side_effect=fake_urlopen),
    ):
        result = verify_cls_connection(
            "ap-guangzhou",
            "AKID_PUSH",
            "SK_PUSH",
            topic_id="existing-topic-1",
        )

    assert result["ok"] is True
    assert result["api_ok"] is None
    assert result["otlp_ok"] is True


def _run_sample_trace(tracer: LangfuseTracer) -> None:
    assert tracer.callbacks is not None
    (callback,) = tracer.callbacks
    request = tracer.enrich_request(
        ChatRequest(
            messages="private prompt",
            user="user-1",
            thread_id="thread-1",
            agent_id="agent-1",
        )
    )
    root, model, tool = uuid4(), uuid4(), uuid4()
    callback.on_chain_start(
        None, request.messages, run_id=root, metadata=request.metadata, name="Octop"
    )
    callback.on_chat_model_start(
        {"name": "ProbeModel"},
        [[HumanMessage(content="private prompt")]],
        run_id=model,
        parent_run_id=root,
        invocation_params={"model": "probe-model"},
    )
    ai_msg = AIMessage(
        content="private response",
        usage_metadata={"input_tokens": 11, "output_tokens": 7, "total_tokens": 18},
    )
    callback.on_llm_end(
        LLMResult(generations=[[ChatGeneration(message=ai_msg)]]),
        run_id=model,
        parent_run_id=root,
    )
    callback.on_tool_start(
        {"name": "ProbeTool"}, "private argument", run_id=tool, parent_run_id=root
    )
    callback.on_tool_end("private tool output", run_id=tool, parent_run_id=root)
    callback.on_chain_end({"output": "private response"}, run_id=root)
    tracer.flush()


@pytest.mark.parametrize(
    ("access_type", "mask_content", "use_internal"),
    [
        ("Langfuse", False, False),
        ("Langfuse", True, True),
        ("Agent", False, False),
    ],
)
def test_cls_otlp_export_through_langfuse_sdk(
    monkeypatch: pytest.MonkeyPatch,
    access_type: str,
    mask_content: bool,
    use_internal: bool,
) -> None:
    monkeypatch.setenv("LANGFUSE_TRACING_ENABLED", "true")
    monkeypatch.setenv("LANGFUSE_MEDIA_UPLOAD_ENABLED", "false")
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_TRACES_COMPRESSION", "none")

    requests_sent: list[PreparedRequest] = []

    def fake_send(self: Session, request: PreparedRequest, **kwargs: object) -> Response:
        requests_sent.append(request)
        resp = Response()
        resp.status_code = 200
        return resp

    monkeypatch.setattr(Session, "send", fake_send)

    config = register_cls_langfuse_client(
        region="ap-guangzhou",
        topic_id="topic-trace-999",
        secret_id="AKID_CUSTOMER",
        secret_key="SK_CUSTOMER",
        service_name="octop-cls-test",
        access_type=access_type,
        use_internal_endpoint=use_internal,
        mask_content=mask_content,
    )
    tracer = LangfuseTracer(config)
    try:
        _run_sample_trace(tracer)
        assert len(requests_sent) == 1
        (export,) = requests_sent

        expected_domain = "cls.tencentyun.com" if use_internal else "cls.tencentcs.com"
        assert export.url == f"https://ap-guangzhou.{expected_domain}/v1/traces"
        assert export.headers["topic_id"] == "topic-trace-999"
        assert (
            base64.b64decode(export.headers["Authorization"].split()[1])
            == b"AKID_CUSTOMER:SK_CUSTOMER"
        )
        assert isinstance(export.body, bytes)

        payload = ExportTraceServiceRequest.FromString(export.body)
        (resource,) = payload.resource_spans
        resource_attrs = {
            attr.key: attr.value.string_value for attr in resource.resource.attributes
        }
        assert resource_attrs["service.name"] == "octop-cls-test"
        spans = [span for scope in resource.scope_spans for span in scope.spans]
        attributes = {
            span.name: {attr.key: attr.value for attr in span.attributes} for span in spans
        }

        if access_type == "Langfuse" and not mask_content:
            assert b"private prompt" in export.body
            assert "langfuse.observation.type" in attributes["ProbeModel"]
        elif access_type == "Langfuse" and mask_content:
            assert b"private " not in export.body
            assert "langfuse.observation.type" in attributes["ProbeModel"]
        else:
            assert b"private " not in export.body
            assert attributes["Octop"]["gen_ai.span.kind"].string_value == "entry"
            assert attributes["ProbeModel"]["gen_ai.usage.input_tokens"].int_value == 11
            assert attributes["ProbeTool"]["gen_ai.tool.name"].string_value == "ProbeTool"
    finally:
        get_client(public_key=config.public_key).shutdown()


def test_env_cls_harness_config_with_sts_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OCTOP_AGENTOBS_ENABLED", "true")
    monkeypatch.setenv("CLS_DEFAULT_REGION", "ap-guangzhou")
    monkeypatch.setenv("CLS_TOPIC_ID", "env-topic-1")
    monkeypatch.setenv("TENCENTCLOUD_SECRET_ID", "AKID_ENV")
    monkeypatch.setenv("TENCENTCLOUD_SECRET_KEY", "SK_ENV")
    monkeypatch.setenv("TENCENTCLOUD_TOKEN", "STS_TOKEN")
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_TRACES_COMPRESSION", "none")

    requests_sent: list[PreparedRequest] = []

    def fake_send(self: Session, request: PreparedRequest, **kwargs: object) -> Response:
        requests_sent.append(request)
        resp = Response()
        resp.status_code = 200
        return resp

    monkeypatch.setattr(Session, "send", fake_send)
    config = env_cls_harness_config()
    assert config is not None and config.configured
    tracer = LangfuseTracer(config)
    try:
        _run_sample_trace(tracer)
        assert len(requests_sent) == 1
        assert (
            base64.b64decode(requests_sent[0].headers["Authorization"].split()[1])
            == b"AKID_ENV#STS_TOKEN:SK_ENV"
        )
    finally:
        get_client(public_key=config.public_key).shutdown()


@pytest.mark.asyncio
async def test_agent_manager_save_cls_auto_create_and_switch(tmp_path: Path) -> None:
    from octop.api.routers import observability as obs_router
    from octop.infra.agents.manager import AgentManager
    from octop.infra.agents.settings.langfuse import LangfuseSettingsStore

    db = SqlitePool(tmp_path / "octop.db")
    run_migrations(db)
    settings_repo = SettingsRepo(db)
    secret_repo = SecretRepo(db)

    fake_harness = mock.MagicMock()
    registry = object.__new__(AgentManager)
    registry._repos = SimpleNamespace(settings_repo=settings_repo, secret_repo=secret_repo)
    registry._langfuse = LangfuseSettingsStore(settings_repo=settings_repo, secret_repo=secret_repo)
    registry._cls_observability = ClsObservabilitySettingsStore(
        settings_repo=settings_repo, secret_repo=secret_repo
    )
    registry._harness_manager = fake_harness

    fake_server = SimpleNamespace(app_runtime=SimpleNamespace(agent_registry=registry))

    # Enable Langfuse first.
    registry.save_langfuse(
        enabled=True,
        public_key="pk-lf-1",
        host="https://cloud.langfuse.com",
        secret_key="sk-lf-1",
    )
    assert registry.active_observability_backend() == "langfuse"

    # Now enable CLS through the router with auto_create_app=True and empty topic_id.
    fake_app = ClsAgentApplication(
        application_id="app-auto-1",
        application_name="octop-customer",
        access_type="Langfuse",
        region="ap-guangzhou",
        topic_id="topic-auto-1",
        created=True,
    )
    with mock.patch.object(
        registry._cls_observability,
        "create_application",
        new=mock.AsyncMock(return_value=fake_app),
    ) as create_mock:
        resp = await obs_router.put_cls_config(
            obs_router.ClsConfigBody(
                enabled=True,
                region="ap-guangzhou",
                application_name="octop-customer",
                access_type="Langfuse",
                secret_id="AKID_CUST_1234",
                secret_key="SK_CUST_5678",
                auto_create_app=True,
            ),
            _=None,
            server=fake_server,
        )

    create_mock.assert_awaited_once()
    assert resp.application_created is True
    assert resp.topic_id == "topic-auto-1"
    assert resp.application_id == "app-auto-1"
    assert resp.secret_id_masked == "AKID****1234"
    assert resp.active_backend == "cls"
    # Langfuse was automatically turned off when CLS was enabled.
    assert registry.langfuse.load().enabled is False
    # Harness manager received a hot-updated LangfuseConfig pointing to CLS.
    last_cfg = fake_harness.set_langfuse.call_args_list[-1].args[0]
    assert last_cfg.enabled is True
    assert last_cfg.host == "https://ap-guangzhou.cls.tencentcs.com"
    get_client(public_key=last_cfg.public_key).shutdown()

    # GET /cls reflects stored state without exposing raw secrets.
    got = await obs_router.get_cls_config(_=None, server=fake_server)
    assert got.topic_id == "topic-auto-1"
    assert got.secret_id_set is True
    assert got.secret_key_set is True
    assert got.active_backend == "cls"

    # Switching to an existing topic_id should NOT call create_application.
    with mock.patch.object(
        registry._cls_observability,
        "create_application",
        new=mock.AsyncMock(),
    ) as create_mock2:
        resp2 = await obs_router.put_cls_config(
            obs_router.ClsConfigBody(
                enabled=True,
                region="ap-shanghai",
                topic_id="topic-manual-existing",
                auto_create_app=False,
            ),
            _=None,
            server=fake_server,
        )
    create_mock2.assert_not_awaited()
    assert resp2.application_created is False
    assert resp2.topic_id == "topic-manual-existing"
    last_cfg2 = fake_harness.set_langfuse.call_args_list[-1].args[0]
    assert last_cfg2.host == "https://ap-shanghai.cls.tencentcs.com"
    get_client(public_key=last_cfg2.public_key).shutdown()

    # List & create application router endpoints work cleanly.
    with mock.patch.object(
        registry._cls_observability,
        "list_applications",
        new=mock.AsyncMock(return_value=[fake_app]),
    ):
        listed = await obs_router.list_cls_applications(
            obs_router.ClsListApplicationsBody(region="ap-guangzhou"),
            _=None,
            server=fake_server,
        )
    assert len(listed.applications) == 1
    assert listed.applications[0].topic_id == "topic-auto-1"

    with mock.patch.object(
        registry._cls_observability,
        "test_connection",
        new=mock.AsyncMock(return_value={"ok": True, "api_ok": True, "otlp_ok": True}),
    ):
        tested = await obs_router.test_cls_connection(
            obs_router.ClsTestBody(region="ap-shanghai", topic_id="topic-manual-existing"),
            _=None,
            server=fake_server,
        )
    assert tested["ok"] is True
