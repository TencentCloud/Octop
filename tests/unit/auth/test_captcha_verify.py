"""ensure_captcha — slider no-op and mocked siteverify."""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from urllib.parse import parse_qs, urlparse

import pytest

from octop.infra.auth.captcha import set_test_siteverify_url
from octop.infra.auth.captcha.store import EffectiveCaptcha
from octop.infra.auth.captcha.verify import ensure_captcha
from octop.infra.errors import ErrorCode, OctopError


def _effective(
    slug: str,
    *,
    site_key: str = "site",
    secret: str = "secret",
    v3_min_score: float = 0.5,
    cam_id: str = "",
    cam_key: str = "",
) -> EffectiveCaptcha:
    return EffectiveCaptcha(
        slug=slug,
        site_key=site_key,
        secret=secret,
        source="env",
        stored_active=None,
        v3_min_score=v3_min_score,
        cam_id=cam_id,
        cam_key=cam_key,
    )


class _Siteverify(BaseHTTPRequestHandler):
    payload: dict[str, object] = {"success": True}
    status: int = 200
    hang: bool = False
    last_query: dict[str, list[str]] = {}
    last_body: dict[str, object] = {}

    def _reply(self) -> None:
        if self.hang:
            return
        raw = json.dumps(self.payload).encode("utf-8")
        self.send_response(self.status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        # Avoid keep-alive reuse after form POSTs on Windows CI.
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(raw)

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        # Always drain the body — form posts (reCAPTCHA) leave unread bytes
        # otherwise, which flaky-breaks the next keep-alive request on Windows.
        raw_body = self.rfile.read(length) if length else b""
        ctype = self.headers.get("Content-Type") or ""
        if raw_body and ctype.startswith("application/json"):
            type(self).last_body = json.loads(raw_body)
        elif raw_body and ctype.startswith("application/x-www-form-urlencoded"):
            type(self).last_body = {k: v[0] for k, v in parse_qs(raw_body.decode("utf-8")).items()}
        type(self).last_query = parse_qs(urlparse(self.path).query)
        self._reply()

    def do_GET(self) -> None:
        type(self).last_query = parse_qs(urlparse(self.path).query)
        self._reply()

    def log_message(self, format: str, *args: object) -> None:
        del format, args


@pytest.fixture
def siteverify() -> tuple[str, type[_Siteverify]]:
    _Siteverify.last_query = {}
    _Siteverify.last_body = {}
    _Siteverify.payload = {"success": True}
    _Siteverify.status = 200
    _Siteverify.hang = False
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Siteverify)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address[:2]
    url = f"http://{host}:{port}/siteverify"
    yield url, _Siteverify
    server.shutdown()
    server.server_close()


@pytest.fixture(autouse=True)
def _clear_test_urls() -> None:
    yield
    for slug in ("turnstile", "hcaptcha", "recaptcha", "recaptcha-v3", "tencent", "geetest-v4"):
        set_test_siteverify_url(slug, None)


@pytest.mark.asyncio
async def test_slider_ignores_token() -> None:
    await ensure_captcha(_effective("slider"), "ignored")


@pytest.mark.asyncio
async def test_strong_blank_token_is_required() -> None:
    with pytest.raises(OctopError) as exc:
        await ensure_captcha(_effective("turnstile"), "  ")
    assert exc.value.code is ErrorCode.CAPTCHA_REQUIRED


@pytest.mark.asyncio
async def test_mocked_success_passes(siteverify: tuple[str, type[_Siteverify]]) -> None:
    url, handler = siteverify
    handler.payload = {"success": True}
    set_test_siteverify_url("turnstile", url)
    await ensure_captcha(_effective("turnstile"), "tok")


@pytest.mark.asyncio
async def test_success_false_fails(siteverify: tuple[str, type[_Siteverify]]) -> None:
    url, handler = siteverify
    handler.payload = {"success": False}
    set_test_siteverify_url("turnstile", url)
    with pytest.raises(OctopError) as exc:
        await ensure_captcha(_effective("turnstile"), "tok")
    assert exc.value.code is ErrorCode.CAPTCHA_FAILED


@pytest.mark.asyncio
async def test_bad_json_fails(siteverify: tuple[str, type[_Siteverify]]) -> None:
    url, handler = siteverify
    handler.payload = "not-an-object"  # type: ignore[assignment]
    set_test_siteverify_url("turnstile", url)
    with pytest.raises(OctopError) as exc:
        await ensure_captcha(_effective("turnstile"), "tok")
    assert exc.value.code is ErrorCode.CAPTCHA_FAILED


@pytest.mark.asyncio
async def test_v3_score_and_action(siteverify: tuple[str, type[_Siteverify]]) -> None:
    url, handler = siteverify
    set_test_siteverify_url("recaptcha-v3", url)
    handler.payload = {"success": True, "score": 0.4, "action": "login"}
    with pytest.raises(OctopError) as exc:
        await ensure_captcha(_effective("recaptcha-v3"), "tok")
    assert exc.value.code is ErrorCode.CAPTCHA_FAILED
    handler.payload = {"success": True, "score": 0.5, "action": "login"}
    await ensure_captcha(_effective("recaptcha-v3"), "tok")
    handler.payload = {"success": True, "score": 0.9, "action": "signup"}
    with pytest.raises(OctopError) as exc2:
        await ensure_captcha(_effective("recaptcha-v3"), "tok")
    assert exc2.value.code is ErrorCode.CAPTCHA_FAILED


@pytest.mark.asyncio
async def test_tencent_ok_sends_ticket_pair_and_ip(
    siteverify: tuple[str, type[_Siteverify]],
) -> None:
    url, handler = siteverify
    handler.payload = {"Response": {"CaptchaCode": 1, "CaptchaMsg": "OK"}}
    set_test_siteverify_url("tencent", url)
    await ensure_captcha(
        _effective(
            "tencent",
            site_key="195642000",
            secret="app-secret",
            cam_id="AKIDcam",
            cam_key="camkey",
        ),
        "tr03ticket:@rand",
        "203.0.113.7",
    )
    assert handler.last_body == {
        "CaptchaType": 9,
        "Ticket": "tr03ticket",
        "Randstr": "@rand",
        "UserIp": "203.0.113.7",
        "CaptchaAppId": 195642000,
        "AppSecretKey": "app-secret",
    }


@pytest.mark.asyncio
async def test_tencent_rejected_response_fails(
    siteverify: tuple[str, type[_Siteverify]],
) -> None:
    url, handler = siteverify
    handler.payload = {"Response": {"CaptchaCode": 7, "CaptchaMsg": "captcha no match"}}
    set_test_siteverify_url("tencent", url)
    with pytest.raises(OctopError) as exc:
        await ensure_captcha(
            _effective("tencent", site_key="195642000", cam_id="AKIDcam", cam_key="camkey"),
            "tr03ticket:@rand",
        )
    assert exc.value.code is ErrorCode.CAPTCHA_FAILED


@pytest.mark.asyncio
async def test_tencent_malformed_token_fails_before_http(
    siteverify: tuple[str, type[_Siteverify]],
) -> None:
    url, handler = siteverify
    set_test_siteverify_url("tencent", url)
    with pytest.raises(OctopError) as exc:
        await ensure_captcha(_effective("tencent"), "no-randstr")
    assert exc.value.code is ErrorCode.CAPTCHA_FAILED
    assert handler.last_query == {}


@pytest.mark.asyncio
async def test_geetest_posts_signed_form_and_passes(
    siteverify: tuple[str, type[_Siteverify]],
) -> None:
    import hashlib
    import hmac as hmac_mod

    url, handler = siteverify
    set_test_siteverify_url("geetest-v4", url)
    handler.payload = {"result": "success", "reason": ""}
    token = json.dumps(
        {
            "lot_number": "lot-9",
            "captcha_output": "out-9",
            "pass_token": "pt-9",
            "gen_time": "2026-09-20T12:00:00",
        }
    )
    await ensure_captcha(_effective("geetest-v4", site_key="gt-id", secret="gt-key"), token)
    # NOTE: captcha_id query is pinned in the provider unit test — the test
    # seam swaps the whole URL, so it never reaches the mock server.
    expected_sign = hmac_mod.new(b"gt-key", b"lot-9", hashlib.sha256).hexdigest()
    assert handler.last_body == {
        "lot_number": "lot-9",
        "captcha_output": "out-9",
        "pass_token": "pt-9",
        "gen_time": "2026-09-20T12:00:00",
        "sign_token": expected_sign,
    }


@pytest.mark.asyncio
async def test_geetest_fail_result_rejected(
    siteverify: tuple[str, type[_Siteverify]],
) -> None:
    url, handler = siteverify
    set_test_siteverify_url("geetest-v4", url)
    handler.payload = {"result": "fail", "reason": "pass_token expire"}
    token = json.dumps(
        {
            "lot_number": "lot-9",
            "captcha_output": "out-9",
            "pass_token": "pt-9",
            "gen_time": "2026-09-20T12:00:00",
        }
    )
    with pytest.raises(OctopError) as exc:
        await ensure_captcha(_effective("geetest-v4", site_key="gt-id", secret="gt-key"), token)
    assert exc.value.code is ErrorCode.CAPTCHA_FAILED
