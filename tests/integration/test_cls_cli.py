"""Exercise the installed CLI over HTTP; replace only the Tencent Cloud calls."""

from __future__ import annotations

import asyncio
import base64
import json
import os
import socket
import sys
import urllib.error
import urllib.request
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any
from unittest.mock import MagicMock

import httpx
import pytest
import uvicorn
from tencentcloud.common.exception.tencent_cloud_sdk_exception import TencentCloudSDKException

from octop.infra.agents.settings import cls_observability as cls
from octop.infra.server import OctopServer

RunCLI = Callable[..., Awaitable[dict[str, Any]]]


@pytest.fixture
async def run_cls(
    env: tuple[httpx.AsyncClient, OctopServer, dict[str, str]],
) -> AsyncIterator[RunCLI]:
    client, _, auth = env
    app = client._octop_app
    server = uvicorn.Server(uvicorn.Config(app, lifespan="off", log_config=None, access_log=False))
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        address = f"http://127.0.0.1:{sock.getsockname()[1]}"
        task = asyncio.create_task(server.serve(sockets=[sock]))
        try:
            async with asyncio.timeout(10):
                while not server.started:
                    if task.done():
                        await task
                    await asyncio.sleep(0.01)

            async def run(
                *args: str,
                stdin: str = "",
                variables: dict[str, str] | None = None,
                exit_code: int = 0,
                as_json: bool = True,
            ) -> dict[str, Any]:
                child_env = {
                    **os.environ,
                    "OCTOP_SERVER_URL": address,
                    "OCTOP_ACCESS_TOKEN": auth["Authorization"].removeprefix("Bearer "),
                }
                for key in (
                    "TENCENTCLOUD_SECRET_ID",
                    "TENCENTCLOUD_SECRET_KEY",
                    "TENCENTCLOUD_TOKEN",
                ):
                    child_env.pop(key, None)
                proc = await asyncio.create_subprocess_exec(
                    sys.executable,
                    "-m",
                    "octop.cli.main",
                    *(["--json"] if as_json else []),
                    "cls",
                    *args,
                    env={**child_env, **(variables or {})},
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(stdin.encode()), timeout=30
                )
                assert proc.returncode == exit_code, (stdout, stderr)
                assert b"fake-secret-key" not in stdout + stderr
                assert child_env["OCTOP_ACCESS_TOKEN"].encode() not in stdout + stderr
                return (
                    json.loads(stdout)
                    if stdout and as_json
                    else {"output": (stdout + stderr).decode()}
                )

            yield run
        finally:
            server.should_exit = True
            await task


async def test_configure_show_test_both_modes(
    run_cls: RunCLI, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []
    apps: list[dict[str, Any]] = []
    push_only = False

    def cloud_call(client: object, action: str, params: dict[str, Any]) -> dict[str, Any]:
        calls.append(action)
        if action == "DescribeAgentApplications":
            if push_only:
                raise TencentCloudSDKException(code="UnauthorizedOperation", message="push only")
            return {"Infos": apps}
        assert action == "CreateAgentApplication"
        app = {
            **params,
            "ApplicationId": "app-1",
            "LogTopics": [{"Flag": "trace", "TopicId": "new-topic"}],
        }
        apps.append(app)
        return app

    probes: list[urllib.request.Request] = []

    def probe(req: urllib.request.Request, timeout: int) -> MagicMock:
        probes.append(req)
        response = MagicMock()
        response.__enter__.return_value.status = 200
        return response

    monkeypatch.setattr(cls, "_call_cls_action", cloud_call)
    monkeypatch.setattr(urllib.request, "urlopen", probe)
    incomplete = await run_cls("test", exit_code=1)
    assert incomplete["otlp_ok"] is None and "octop cls configure" in incomplete["error"]
    flags = [
        "configure",
        "--new",
        "--region",
        "ap-guangzhou",
        "--app-name",
        "demo",
        "--mask-content",
    ]
    saved = await run_cls(
        *flags,
        variables={
            "TENCENTCLOUD_SECRET_ID": "test-credential-id",
            "TENCENTCLOUD_SECRET_KEY": "fake-secret-key",
        },
    )
    assert saved["action"] == "created"
    current = await run_cls("show")
    assert (current["source"], current["active_backend"], current["topic_id"]) == (
        "database",
        "cls",
        "new-topic",
    )
    assert current["secret_key_set"] and current["mask_content"]
    assert (await run_cls("test"))["otlp_ok"]
    assert probes[-1].get_header("Topic_id") == "new-topic"
    assert (await run_cls(*flags))["action"] == "reused"
    assert calls.count("CreateAgentApplication") == 1

    # Wizard: accept the existing mode/region and saved credentials, then pick an application.
    selected = await run_cls("configure", stdin="\n\n\nlist\n1\n")
    assert (selected["action"], selected["application_id"]) == ("bound", "app-1")

    push_only = True
    before = calls.copy()
    bound = await run_cls(
        "configure", "--existing", "--topic-id", "my-topic", "--region", "ap-shanghai"
    )
    assert bound["action"] == "bound" and bound["application_id"] == ""
    assert calls == before
    # A failed cloud-side provision must leave the working Topic binding intact.
    await run_cls(*flags, exit_code=1)
    current = await run_cls("show")
    assert (current["topic_id"], current["region"]) == ("my-topic", "ap-shanghai")
    assert current["mask_content"]
    result = await run_cls("test")
    assert result["ok"] and result["otlp_ok"] and result["api_ok"] is None
    assert probes[-1].get_header("Topic_id") == "my-topic"
    assert "my-topic" in (await run_cls("show", as_json=False))["output"]

    def reject(req: urllib.request.Request, timeout: int) -> None:
        raise urllib.error.HTTPError(req.full_url, 403, "Forbidden", {}, None)

    monkeypatch.setattr(urllib.request, "urlopen", reject)
    failed = await run_cls("test", exit_code=1)
    assert not failed["otlp_ok"] and "403" in failed["error"]

    def bad_credentials(*args: object) -> None:
        raise TencentCloudSDKException(code="AuthFailure", message="invalid key")

    monkeypatch.setattr(cls, "_call_cls_action", bad_credentials)
    failed = await run_cls("test", exit_code=1)
    assert not failed["api_ok"] and "AuthFailure" in failed["error"]
    assert (
        "401"
        in (await run_cls("show", variables={"OCTOP_ACCESS_TOKEN": "invalid"}, exit_code=1))[
            "output"
        ]
    )
    await run_cls("configure", "--existing", "--new", exit_code=2)
    await run_cls("configure", "--new", "--topic-id", "ambiguous", exit_code=2)


async def test_show_and_test_use_server_environment(
    run_cls: RunCLI, monkeypatch: pytest.MonkeyPatch
) -> None:
    for key, value in {
        "OCTOP_AGENTOBS_ENABLED": "true",
        "CLS_DEFAULT_REGION": "ap-shanghai",
        "CLS_TOPIC_ID": "env-topic",
        "CLS_ACCESS_TYPE": "Agent",
        "CLS_USE_INTERNAL_ENDPOINT": "true",
        "CLS_MASK_CONTENT": "true",
        "TENCENTCLOUD_SECRET_ID": "server-credential",
        "TENCENTCLOUD_SECRET_KEY": "fake-secret-key",
        "TENCENTCLOUD_TOKEN": "server-sts",
    }.items():
        monkeypatch.setenv(key, value)
    current = await run_cls("show")
    assert current["configured"] and current["active_backend"] == "cls_env"
    assert (current["source"], current["topic_id"]) == ("environment", "env-topic")
    assert current["mask_content"] and current["use_internal_endpoint"]
    assert current["secret_id_masked"] == "serv****tial"
    monkeypatch.setattr(cls, "_call_cls_action", lambda *args: {})

    def probe(req: urllib.request.Request, timeout: int) -> MagicMock:
        assert req.full_url == "https://ap-shanghai.cls.tencentyun.com/v1/traces"
        assert req.get_header("Topic_id") == "env-topic"
        assert (
            base64.b64decode(req.get_header("Authorization").split()[1])
            == b"server-credential#server-sts:fake-secret-key"
        )
        response = MagicMock()
        response.__enter__.return_value.status = 200
        return response

    monkeypatch.setattr(urllib.request, "urlopen", probe)
    assert (await run_cls("test"))["otlp_ok"]
    monkeypatch.delenv("CLS_TOPIC_ID")
    assert not (await run_cls("show"))["configured"]
    failed = await run_cls("test", exit_code=1)
    assert not failed["ok"] and "Topic ID" in failed["error"]

    # Switching from STS deployment settings to a saved binding preserves the
    # active privacy and endpoint options, but needs persistable credentials.
    monkeypatch.setenv("CLS_TOPIC_ID", "env-topic")
    await run_cls("configure", "--existing", "--topic-id", "saved-topic", exit_code=2)
    saved = await run_cls(
        "configure",
        "--existing",
        "--topic-id",
        "saved-topic",
        variables={
            "TENCENTCLOUD_SECRET_ID": "stored-credential",
            "TENCENTCLOUD_SECRET_KEY": "fake-secret-key",
        },
    )
    assert saved["mask_content"] and saved["use_internal_endpoint"]
    assert saved["access_type"] == "Agent" and saved["region"] == "ap-shanghai"
    current = await run_cls("show")
    assert current["source"] == "database" and current["topic_id"] == "saved-topic"
