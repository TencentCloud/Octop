"""SEC-17 · ``details`` 的序列化面（``SPEC · A6``）—— 两条平行渲染路径都不得二次崩。

实测口径（``team/2026-09-29-220912/RESEARCH-T98-T99.md`` §4②）：``to_envelope`` **不抛**，
抛出的是 ``JSONResponse.render → json.dumps`` ⇒ 断言必须落在**响应渲染**这一段
（``JSONResponse`` 的 body / ``json.dumps(envelope)``）。只断 ``to_envelope`` 返回值 = 假绿。
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest
from fastapi.responses import JSONResponse
from tests.support.app import ensure_control_plane_bound, write_octop_config
from tests.support.auth import bootstrap_admin

from octop.api.app import _json_dumps, _jsonable_details, _renderable_envelope, build_app
from octop.infra.errors import ErrorCode, OctopError, corrupt_config_error
from octop.infra.server import OctopServer

#: 裸异常对象（`SEC-17` 的肇事值；`str()` 里那句是「不得泄进响应体」的探针）。
_BARE = ValueError("raw secret /etc/passwd")

#: 既有 4 个 `details` 站点，值形态**逐字**取自源码 —— 用于「正常路径逐字不变」机判。
_SITES: tuple[tuple[str, OctopError], ...] = (
    (
        "api/routers/experts.py:415",
        OctopError(
            ErrorCode.EXPERT_MARKET_FAILED,
            "expert market failed: upstream_failed",
            details={"reason": "upstream_failed", "kind": "upstream_failed"},
        ),
    ),
    (
        "api/routers/skill_packages.py:233",
        OctopError(
            ErrorCode.EXPERT_MARKET_FAILED,
            "skillhub market failed: upstream_failed",
            details={"reason": "upstream_failed", "kind": "upstream_failed"},
        ),
    ),
    (
        "infra/gateway/media/inbound_store.py:329",
        OctopError(
            ErrorCode.ATTACHMENT_TOO_LARGE,
            "file too large (max 20MB)",
            details={"max_mb": 20},
        ),
    ),
    ("infra/errors.py:455", corrupt_config_error("config.json", "line 3 column 1")),
)


@pytest.mark.parametrize("exc", [exc for _, exc in _SITES], ids=[name for name, _ in _SITES])
@pytest.mark.parametrize("locale", ["zh", "en", None])
def test_normal_path_is_byte_identical(exc: OctopError, locale: str | None) -> None:
    """helper 对可序列化值是恒等映射：4 站点 × 3 locale，序列化结果**字符串相等**。"""
    assert json.dumps(
        _renderable_envelope(exc, locale), sort_keys=True, ensure_ascii=False
    ) == json.dumps(exc.to_envelope(locale=locale), sort_keys=True, ensure_ascii=False)


def test_jsonable_details_degrades_only_the_failing_value() -> None:
    safe, dropped = _jsonable_details({"reason": _BARE, "max_mb": 20})
    assert safe == {"reason": {"unserializable": "ValueError"}, "max_mb": 20}
    assert dropped == [("reason", "ValueError")]
    json.dumps(safe)  # 降级后的 details 必须可渲染


def test_unserializable_details_leave_a_log_and_never_the_raw_object(caplog) -> None:
    exc = OctopError(ErrorCode.INTERNAL_ERROR, "boom", details={"reason": _BARE})
    with caplog.at_level(logging.WARNING, logger="octop.api.app"):
        envelope = _renderable_envelope(exc, "en")

    records = [
        rec
        for rec in caplog.records
        if rec.levelno >= logging.WARNING
        and "octop.error.details-unserializable" in rec.getMessage()
    ]
    assert len(records) == 1
    rendered = records[0].getMessage()
    assert "reason" in rendered and "ValueError" in rendered

    body = json.dumps(envelope, sort_keys=True)
    assert envelope["error"]["details"] == {"reason": {"unserializable": "ValueError"}}
    assert "raw secret" not in body  # 只留类别，原文不进响应体


#: `json.dumps` 默认 `allow_nan=True` 会静默放行、而 `JSONResponse.render` 用
#: `allow_nan=False` 会抛 `ValueError` —— 正是「探针放行、渲染抛错」的活口（FIND-1）。
_NON_FINITE = (float("nan"), float("inf"), float("-inf"))


def test_jsonable_details_degrades_non_finite_floats() -> None:
    """探针与渲染同参：``nan``/``inf`` 命中降级分支，而非在渲染时才炸（FIND-1）。"""
    safe, dropped = _jsonable_details({"reason": float("nan"), "max_mb": 20})

    assert safe == {"reason": {"unserializable": "float"}, "max_mb": 20}
    assert dropped == [("reason", "float")]
    assert json.dumps(safe)  # 降级后的 details 必须可渲染


@pytest.mark.parametrize("bad", _NON_FINITE, ids=["nan", "inf", "-inf"])
def test_renderable_envelope_survives_non_finite_float(bad: float, caplog) -> None:
    """``_renderable_envelope`` + ``JSONResponse`` 真渲染一次：不抛、body 可 ``json.dumps``、留痕。"""
    exc = OctopError(ErrorCode.INTERNAL_ERROR, "boom", details={"reason": bad})
    with caplog.at_level(logging.WARNING, logger="octop.api.app"):
        envelope = _renderable_envelope(exc, "en")
        assert envelope["error"]["details"] == {"reason": {"unserializable": "float"}}
        response = JSONResponse(status_code=500, content=envelope)  # 断言落在真渲染

    assert json.loads(response.body)["error"]["details"] == {"reason": {"unserializable": "float"}}
    assert "NaN" not in response.body.decode() and "Infinity" not in response.body.decode()
    assert [
        rec
        for rec in caplog.records
        if rec.levelno >= logging.WARNING
        and "octop.error.details-unserializable" in rec.getMessage()
    ]


@pytest.mark.parametrize("bad", _NON_FINITE, ids=["nan", "inf", "-inf"])
def test_probe_dumper_shares_render_contract(bad: float) -> None:
    """回归锁：探针必须与 ``JSONResponse.render`` 同参（非有限浮点绝不能被放行）。"""
    with pytest.raises(ValueError):
        _json_dumps(bad)
    with pytest.raises(ValueError):
        JSONResponse(status_code=500, content={"reason": bad})


def test_unguarded_envelope_really_breaks_rendering() -> None:
    """炸点复现（判别性基准）：未过 helper 的 envelope ⇒ ``JSONResponse.render`` 抛。"""
    exc = OctopError(ErrorCode.INTERNAL_ERROR, "boom", details={"reason": _BARE})
    assert exc.to_envelope(locale="en")["error"]["details"]["reason"] is _BARE  # 本步不抛
    with pytest.raises(TypeError):
        JSONResponse(status_code=500, content=exc.to_envelope(locale="en"))


@pytest.fixture
async def client(tmp_path: Path):
    write_octop_config(tmp_path, enable_dashboard=False)
    srv = OctopServer(home=tmp_path)
    await srv.start()
    await ensure_control_plane_bound(srv)
    app = build_app(srv)

    # 路径一：`api/app.py` 的 OctopError 异常处理器（走 exception_handler）。
    @app.get("/_test/octop-500-bare")
    async def _boom() -> None:
        raise OctopError(ErrorCode.INTERNAL_ERROR, "boom", details={"reason": _BARE})

    # FIND-1：探针若用默认 `allow_nan=True`，这里会渲染期抛 ValueError ⇒ 裸 500、details 全失。
    @app.get("/_test/octop-500-nan")
    async def _boom_nan() -> None:
        raise OctopError(ErrorCode.INTERNAL_ERROR, "boom", details={"reason": float("nan")})

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as c:
        yield c, srv


async def test_app_handler_renders_bare_exception_details(client, caplog) -> None:
    c, srv = client
    with caplog.at_level(logging.WARNING, logger="octop.api.app"):
        r = await c.get("/_test/octop-500-bare", headers={"Accept-Language": "zh"})
    await srv.stop()

    assert r.status_code == 500
    payload = r.json()  # 能解析 = 封装没二次崩
    assert payload["error"]["message"] == "服务器内部错误。"
    assert payload["error"]["details"] == {"reason": {"unserializable": "ValueError"}}
    assert "raw secret" not in r.text
    assert [
        rec for rec in caplog.records if "octop.error.details-unserializable" in rec.getMessage()
    ]


async def test_app_handler_renders_non_finite_details(client, caplog) -> None:
    """端到端：`float('nan')` 进 details ⇒ 不再二次崩，降级 + 留痕，body 仍是可解析 JSON。"""
    c, srv = client
    with caplog.at_level(logging.WARNING, logger="octop.api.app"):
        r = await c.get("/_test/octop-500-nan", headers={"Accept-Language": "zh"})
    await srv.stop()

    assert r.status_code == 500
    payload = r.json()  # 能解析 = 异常处理器没有二次崩
    assert payload["error"]["message"] == "服务器内部错误。"
    assert payload["error"]["details"] == {"reason": {"unserializable": "float"}}
    assert "NaN" not in r.text
    assert [
        rec for rec in caplog.records if "octop.error.details-unserializable" in rec.getMessage()
    ]


async def test_jwt_middleware_renders_bare_exception_details(tmp_path: Path, caplog) -> None:
    """路径二：`api/middleware/jwt_auth.py @ 62` —— 平行渲染、同一 `details` 敞口。"""
    write_octop_config(tmp_path, enable_dashboard=False)
    srv = OctopServer(home=tmp_path)
    await srv.start()
    await ensure_control_plane_bound(srv)
    app = build_app(srv)
    boom = OctopError(ErrorCode.INTERNAL_ERROR, "boom", details={"reason": _BARE})

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as c:
        await bootstrap_admin(c, tmp_path)  # 先过 setup lockdown，才能走到 JWT 中间件
        with (
            patch("octop.api.middleware.jwt_auth.authenticate_request", side_effect=boom),
            caplog.at_level(logging.WARNING, logger="octop.api.app"),
        ):
            r = await c.get("/api/agents")
    await srv.stop()

    assert r.status_code == 500
    assert r.json()["error"]["details"] == {"reason": {"unserializable": "ValueError"}}
    assert "raw secret" not in r.text
    assert [
        rec for rec in caplog.records if "octop.error.details-unserializable" in rec.getMessage()
    ]
