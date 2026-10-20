from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from octop_browser.cdp.client import CDPSessionError
from octop_browser.models import ActionMetrics, ToolResult
from octop_browser.tool_interface import browser_tool


def make_tool_result(action: str = "navigate") -> ToolResult:
    return ToolResult(
        success=True,
        content="ok",
        metrics=ActionMetrics(
            action=action, duration_ms=10, dom_nodes_scanned=0, estimated_tokens=5
        ),
    )


async def test_browser_tool_unknown_action():
    result = await browser_tool(
        action="nonexistent_action_xyz", profile="_test_unknown_"
    )
    assert result.success is False
    assert "Unknown action" in (result.error or "")


async def test_browser_tool_missing_required_param():
    # navigate requires url; omitting it should return error
    with patch("octop_browser.tool_interface._get_or_create_session") as mock_get:
        mock_sess = AsyncMock()
        mock_sess.navigate = AsyncMock(side_effect=TypeError("missing url"))
        mock_get.return_value = mock_sess
        result = await browser_tool(action="navigate", profile="_test_missing_")
    assert result.success is False


async def test_browser_tool_recovers_once_from_disconnected_session(monkeypatch):
    from octop_browser import tool_interface as tool_interface_mod

    profile = "_test_recover_disconnected_"
    tool_interface_mod._registry.pop(profile, None)
    events: list[str] = []

    class BrokenSession:
        async def navigate(self, url: str) -> ToolResult:
            events.append(f"broken.navigate:{url}")
            raise CDPSessionError("Not connected")

        async def close(self) -> None:
            events.append("broken.close")

    class FreshSession:
        async def navigate(self, url: str) -> ToolResult:
            events.append(f"fresh.navigate:{url}")
            return make_tool_result("navigate")

        async def close(self) -> None:
            events.append("fresh.close")

    sessions = [BrokenSession(), FreshSession()]

    async def fake_create(*args, **kwargs):
        events.append("create")
        return sessions.pop(0)

    monkeypatch.setattr(tool_interface_mod.BrowserSession, "create", fake_create)

    try:
        result = await browser_tool(
            action="navigate", profile=profile, url="https://example.com"
        )
    finally:
        tool_interface_mod._registry.pop(profile, None)

    assert result.success is True
    assert events == [
        "create",
        "broken.navigate:https://example.com",
        "broken.close",
        "create",
        "fresh.navigate:https://example.com",
    ]


async def test_new_tab_reuses_existing_blank_tab_for_first_url(monkeypatch):
    calls: list[tuple[str, dict[str, object]]] = []

    class FakeRefCache:
        pass

    class FakeInternal:
        def __init__(self) -> None:
            self.client = self
            self.ref_cache = FakeRefCache()
            self._profile = SimpleNamespace(load_target=lambda: "CURRENT")
            self._cfg = SimpleNamespace(cdp_ws_url=None)

        async def send(
            self, method: str, params: dict[str, object] | None = None
        ) -> dict[str, object]:
            calls.append((method, params or {}))
            if method == "Runtime.evaluate":
                return {"result": {"value": "about:blank"}}
            raise AssertionError(f"unexpected CDP command {method}")

        async def switch_to_target(
            self, target_id: str, *, activate: bool = True
        ) -> None:
            calls.append(
                ("switch_to_target", {"target_id": target_id, "activate": activate})
            )

    async def fake_navigate(
        client: FakeInternal, ref_cache: FakeRefCache, url: str
    ) -> ToolResult:
        assert isinstance(client, FakeInternal)
        assert isinstance(ref_cache, FakeRefCache)
        calls.append(("nav_actions.navigate", {"url": url}))
        return ToolResult(
            success=True,
            content="navigated",
            metrics=make_tool_result("navigate").metrics,
        )

    from octop_browser import session as session_mod
    from octop_browser.session import BrowserSession

    monkeypatch.setattr(session_mod.nav_actions, "navigate", fake_navigate)

    sess = BrowserSession(FakeInternal(), profile_name="test")  # type: ignore[arg-type]
    result = await sess.new_tab("https://example.com")

    assert result.success is True
    assert result.content == "CURRENT"
    assert calls == [
        ("Runtime.evaluate", {"expression": "location.href", "returnByValue": True}),
        ("nav_actions.navigate", {"url": "https://example.com"}),
    ]


async def test_new_tab_reports_navigation_failure_when_reusing_current_blank(
    monkeypatch,
):
    calls: list[tuple[str, dict[str, object]]] = []

    class FakeRefCache:
        pass

    class FakeInternal:
        def __init__(self) -> None:
            self.client = self
            self.ref_cache = FakeRefCache()
            self._profile = SimpleNamespace(load_target=lambda: "CURRENT")
            self._cfg = SimpleNamespace(cdp_ws_url=None)

        async def send(
            self, method: str, params: dict[str, object] | None = None
        ) -> dict[str, object]:
            calls.append((method, params or {}))
            if method == "Runtime.evaluate":
                return {"result": {"value": "about:blank"}}
            raise AssertionError(f"unexpected CDP command {method}")

    async def fake_navigate(
        client: FakeInternal, ref_cache: FakeRefCache, url: str
    ) -> ToolResult:
        assert isinstance(client, FakeInternal)
        assert isinstance(ref_cache, FakeRefCache)
        calls.append(("nav_actions.navigate", {"url": url}))
        return ToolResult(
            success=False,
            content="",
            error="Navigation failed for https://bad.invalid: net::ERR_FAILED",
            metrics=make_tool_result("navigate").metrics,
        )

    from octop_browser import session as session_mod
    from octop_browser.session import BrowserSession

    monkeypatch.setattr(session_mod.nav_actions, "navigate", fake_navigate)

    sess = BrowserSession(FakeInternal(), profile_name="test")  # type: ignore[arg-type]
    result = await sess.new_tab("https://bad.invalid")

    assert result.success is False
    assert result.content == ""
    assert result.error == "Navigation failed for https://bad.invalid: net::ERR_FAILED"
    assert result.metadata == {"target_id": "CURRENT"}
    assert calls == [
        ("Runtime.evaluate", {"expression": "location.href", "returnByValue": True}),
        ("nav_actions.navigate", {"url": "https://bad.invalid"}),
    ]


async def test_new_tab_reuses_background_blank_tab_before_creating_target(
    monkeypatch,
):
    calls: list[tuple[str, dict[str, object]]] = []

    class FakeRefCache:
        pass

    class FakeInternal:
        def __init__(self) -> None:
            self.client = self
            self.ref_cache = FakeRefCache()
            self._profile = SimpleNamespace(
                cdp_port=9222, load_target=lambda: "CURRENT"
            )
            self._cfg = SimpleNamespace(cdp_ws_url=None, cdp_host="localhost")

        async def send(
            self, method: str, params: dict[str, object] | None = None
        ) -> dict[str, object]:
            calls.append((method, params or {}))
            if method == "Runtime.evaluate":
                return {"result": {"value": "https://example.com/current"}}
            raise AssertionError(f"unexpected CDP command {method}")

        async def switch_to_target(
            self, target_id: str, *, activate: bool = True
        ) -> None:
            calls.append(
                ("switch_to_target", {"target_id": target_id, "activate": activate})
            )

    class FakeResponse:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def json(self, content_type=None):
            return [
                {
                    "type": "page",
                    "id": "CURRENT",
                    "url": "https://example.com/current",
                },
                {"type": "page", "id": "BLANK", "url": "about:blank"},
            ]

    class FakeClientSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        def get(self, url: str):
            calls.append(("http.get", {"url": url}))
            return FakeResponse()

    async def fake_navigate(
        client: FakeInternal, ref_cache: FakeRefCache, url: str
    ) -> ToolResult:
        assert isinstance(client, FakeInternal)
        assert isinstance(ref_cache, FakeRefCache)
        calls.append(("nav_actions.navigate", {"url": url}))
        return ToolResult(
            success=True,
            content="navigated",
            metrics=make_tool_result("navigate").metrics,
        )

    from octop_browser import session as session_mod
    from octop_browser.session import BrowserSession

    monkeypatch.setattr(session_mod.nav_actions, "navigate", fake_navigate)
    monkeypatch.setattr(
        session_mod.aiohttp, "ClientSession", lambda: FakeClientSession()
    )

    sess = BrowserSession(FakeInternal(), profile_name="test")  # type: ignore[arg-type]
    result = await sess.new_tab("https://example.com/next")

    assert result.success is True
    assert result.content == "BLANK"
    assert calls == [
        ("Runtime.evaluate", {"expression": "location.href", "returnByValue": True}),
        ("http.get", {"url": "http://localhost:9222/json"}),
        ("switch_to_target", {"target_id": "BLANK", "activate": True}),
        ("nav_actions.navigate", {"url": "https://example.com/next"}),
    ]


async def test_new_tab_creates_target_with_url_and_activates_it(monkeypatch):
    calls: list[tuple[str, dict[str, object]]] = []

    class FakeRefCache:
        pass

    class FakeInternal:
        def __init__(self) -> None:
            self.client = self
            self.ref_cache = FakeRefCache()
            self._profile = SimpleNamespace(
                cdp_port=9222, load_target=lambda: "CURRENT"
            )
            self._cfg = SimpleNamespace(cdp_ws_url=None, cdp_host="localhost")

        async def send(
            self, method: str, params: dict[str, object] | None = None
        ) -> dict[str, object]:
            calls.append((method, params or {}))
            if method == "Runtime.evaluate":
                return {"result": {"value": "https://example.com/current"}}
            if method == "Target.createTarget":
                assert params == {"url": "https://example.com/new"}
                return {"targetId": "NEW"}
            raise AssertionError(f"unexpected CDP command {method}")

        async def switch_to_target(
            self, target_id: str, *, activate: bool = True
        ) -> None:
            calls.append(
                ("switch_to_target", {"target_id": target_id, "activate": activate})
            )

    class FakeResponse:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def json(self, content_type=None):
            return [
                {
                    "type": "page",
                    "id": "CURRENT",
                    "url": "https://example.com/current",
                }
            ]

    class FakeClientSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        def get(self, url: str):
            calls.append(("http.get", {"url": url}))
            return FakeResponse()

    async def unexpected_navigate(*args, **kwargs) -> ToolResult:
        raise AssertionError(
            "new_tab should pass the URL directly to Target.createTarget"
        )

    from octop_browser import session as session_mod
    from octop_browser.session import BrowserSession

    monkeypatch.setattr(session_mod.nav_actions, "navigate", unexpected_navigate)
    monkeypatch.setattr(
        session_mod.aiohttp, "ClientSession", lambda: FakeClientSession()
    )

    sess = BrowserSession(FakeInternal(), profile_name="test")  # type: ignore[arg-type]
    result = await sess.new_tab("https://example.com/new")

    assert result.success is True
    assert result.content == "NEW"
    assert calls == [
        ("Runtime.evaluate", {"expression": "location.href", "returnByValue": True}),
        ("http.get", {"url": "http://localhost:9222/json"}),
        ("Target.createTarget", {"url": "https://example.com/new"}),
        ("switch_to_target", {"target_id": "NEW", "activate": True}),
    ]


async def test_new_tab_creates_target_with_destination_url_to_avoid_blank_flash(
    monkeypatch,
):
    calls: list[tuple[str, dict[str, object]]] = []

    class FakeRefCache:
        pass

    class FakeInternal:
        def __init__(self) -> None:
            self.client = self
            self.ref_cache = FakeRefCache()
            self._profile = SimpleNamespace(
                cdp_port=9222, load_target=lambda: "CURRENT"
            )
            self._cfg = SimpleNamespace(cdp_ws_url=None, cdp_host="localhost")

        async def send(
            self, method: str, params: dict[str, object] | None = None
        ) -> dict[str, object]:
            calls.append((method, params or {}))
            if method == "Runtime.evaluate":
                return {"result": {"value": "https://example.com/current"}}
            if method == "Target.createTarget":
                assert params == {"url": "https://example.com/new"}
                return {"targetId": "NEW"}
            raise AssertionError(f"unexpected CDP command {method}")

        async def switch_to_target(
            self, target_id: str, *, activate: bool = True
        ) -> None:
            calls.append(
                ("switch_to_target", {"target_id": target_id, "activate": activate})
            )

    class FakeResponse:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def json(self, content_type=None):
            return [
                {
                    "type": "page",
                    "id": "CURRENT",
                    "url": "https://example.com/current",
                }
            ]

    class FakeClientSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        def get(self, url: str):
            calls.append(("http.get", {"url": url}))
            return FakeResponse()

    async def unexpected_navigate(*args, **kwargs) -> ToolResult:
        raise AssertionError(
            "new tabs with a URL should not first create about:blank and then navigate"
        )

    from octop_browser import session as session_mod
    from octop_browser.session import BrowserSession

    monkeypatch.setattr(session_mod.nav_actions, "navigate", unexpected_navigate)
    monkeypatch.setattr(
        session_mod.aiohttp, "ClientSession", lambda: FakeClientSession()
    )

    sess = BrowserSession(FakeInternal(), profile_name="test")  # type: ignore[arg-type]
    result = await sess.new_tab("https://example.com/new")

    assert result.success is True
    assert result.content == "NEW"
    assert result.metadata == {"target_id": "NEW"}
    assert calls == [
        ("Runtime.evaluate", {"expression": "location.href", "returnByValue": True}),
        ("http.get", {"url": "http://localhost:9222/json"}),
        ("Target.createTarget", {"url": "https://example.com/new"}),
        ("switch_to_target", {"target_id": "NEW", "activate": True}),
    ]


async def test_new_tab_retries_switch_when_created_target_is_not_ready(monkeypatch):
    calls: list[tuple[str, dict[str, object]]] = []
    switch_attempts = 0
    sleeps: list[float] = []

    class FakeRefCache:
        pass

    class FakeInternal:
        def __init__(self) -> None:
            self.client = self
            self.ref_cache = FakeRefCache()
            self._profile = SimpleNamespace(
                cdp_port=9222, load_target=lambda: "CURRENT"
            )
            self._cfg = SimpleNamespace(cdp_ws_url=None, cdp_host="localhost")

        async def send(
            self, method: str, params: dict[str, object] | None = None
        ) -> dict[str, object]:
            calls.append((method, params or {}))
            if method == "Runtime.evaluate":
                return {"result": {"value": "https://example.com/current"}}
            if method == "Target.createTarget":
                return {"targetId": "NEW"}
            raise AssertionError(f"unexpected CDP command {method}")

        async def switch_to_target(
            self, target_id: str, *, activate: bool = True
        ) -> None:
            nonlocal switch_attempts
            switch_attempts += 1
            calls.append(
                ("switch_to_target", {"target_id": target_id, "activate": activate})
            )
            if switch_attempts == 1:
                raise RuntimeError("No page target found for tab NEW")

    class FakeResponse:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def json(self, content_type=None):
            return [
                {
                    "type": "page",
                    "id": "CURRENT",
                    "url": "https://example.com/current",
                }
            ]

    class FakeClientSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        def get(self, url: str):
            calls.append(("http.get", {"url": url}))
            return FakeResponse()

    async def fake_sleep(delay: float) -> None:
        sleeps.append(delay)

    from octop_browser import session as session_mod
    from octop_browser.session import BrowserSession

    monkeypatch.setattr(
        session_mod.aiohttp, "ClientSession", lambda: FakeClientSession()
    )
    monkeypatch.setattr(session_mod.asyncio, "sleep", fake_sleep)

    sess = BrowserSession(FakeInternal(), profile_name="test")  # type: ignore[arg-type]
    result = await sess.new_tab("https://example.com/new")

    assert result.success is True
    assert result.content == "NEW"
    assert switch_attempts == 2
    assert sleeps == [0.1]


async def test_new_tab_reports_create_target_failure(monkeypatch):
    calls: list[tuple[str, dict[str, object]]] = []

    class FakeRefCache:
        pass

    class FakeInternal:
        def __init__(self) -> None:
            self.client = self
            self.ref_cache = FakeRefCache()
            self._profile = SimpleNamespace(
                cdp_port=9222, load_target=lambda: "CURRENT"
            )
            self._cfg = SimpleNamespace(cdp_ws_url=None, cdp_host="localhost")

        async def send(
            self, method: str, params: dict[str, object] | None = None
        ) -> dict[str, object]:
            calls.append((method, params or {}))
            if method == "Runtime.evaluate":
                return {"result": {"value": "https://example.com/current"}}
            if method == "Target.createTarget":
                assert params == {"url": "https://bad.invalid"}
                raise RuntimeError("Target.createTarget failed")
            raise AssertionError(f"unexpected CDP command {method}")

        async def switch_to_target(
            self, target_id: str, *, activate: bool = True
        ) -> None:
            calls.append(
                ("switch_to_target", {"target_id": target_id, "activate": activate})
            )

    class FakeResponse:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def json(self, content_type=None):
            return [
                {
                    "type": "page",
                    "id": "CURRENT",
                    "url": "https://example.com/current",
                }
            ]

    class FakeClientSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        def get(self, url: str):
            calls.append(("http.get", {"url": url}))
            return FakeResponse()

    async def unexpected_navigate(*args, **kwargs) -> ToolResult:
        raise AssertionError(
            "new_tab should not run a second Page.navigate after Target.createTarget"
        )

    from octop_browser import session as session_mod
    from octop_browser.session import BrowserSession

    monkeypatch.setattr(session_mod.nav_actions, "navigate", unexpected_navigate)
    monkeypatch.setattr(
        session_mod.aiohttp, "ClientSession", lambda: FakeClientSession()
    )

    sess = BrowserSession(FakeInternal(), profile_name="test")  # type: ignore[arg-type]
    result = await sess.new_tab("https://bad.invalid")

    assert result.success is False
    assert result.content == ""
    assert result.error == "Target.createTarget failed"
    assert result.metadata is None
    assert calls == [
        ("Runtime.evaluate", {"expression": "location.href", "returnByValue": True}),
        ("http.get", {"url": "http://localhost:9222/json"}),
        ("Target.createTarget", {"url": "https://bad.invalid"}),
    ]


async def test_list_tabs_marks_only_sticky_target_active(monkeypatch):
    calls: list[tuple[str, dict[str, object]]] = []

    class FakeInternal:
        def __init__(self) -> None:
            self._profile = SimpleNamespace(
                cdp_port=9222,
                load_target=lambda: "TAB-2",
            )
            self._cfg = SimpleNamespace(cdp_host="localhost")

    class FakeResponse:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def json(self, content_type=None):
            return [
                {
                    "type": "page",
                    "id": "TAB-1",
                    "url": "https://www.bilibili.com/",
                    "title": "B站",
                },
                {
                    "type": "page",
                    "id": "TAB-2",
                    "url": "https://weibo.com/",
                    "title": "微博",
                },
            ]

    class FakeClientSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        def get(self, url: str):
            calls.append(("http.get", {"url": url}))
            return FakeResponse()

    from octop_browser import session as session_mod
    from octop_browser.session import BrowserSession

    monkeypatch.setattr(
        session_mod.aiohttp, "ClientSession", lambda: FakeClientSession()
    )

    sess = BrowserSession(FakeInternal(), profile_name="test")  # type: ignore[arg-type]
    result = await sess.list_tabs()

    assert result.success is True
    assert result.metadata == {
        "tabs": [
            {
                "tab_id": "TAB-1",
                "url": "https://www.bilibili.com/",
                "title": "B站",
                "active": False,
            },
            {
                "tab_id": "TAB-2",
                "url": "https://weibo.com/",
                "title": "微博",
                "active": True,
            },
        ]
    }


async def test_new_tab_force_new_does_not_reuse_current_blank_tab(monkeypatch):
    calls: list[tuple[str, dict[str, object]]] = []

    class FakeRefCache:
        pass

    class FakeInternal:
        def __init__(self) -> None:
            self.client = self
            self.ref_cache = FakeRefCache()
            self._profile = SimpleNamespace(
                cdp_port=9222, load_target=lambda: "CURRENT"
            )
            self._cfg = SimpleNamespace(cdp_ws_url=None, cdp_host="localhost")

        async def send(
            self, method: str, params: dict[str, object] | None = None
        ) -> dict[str, object]:
            calls.append((method, params or {}))
            if method == "Target.createTarget":
                return {"targetId": "NEW"}
            raise AssertionError(f"unexpected CDP command {method}")

        async def switch_to_target(
            self, target_id: str, *, activate: bool = True
        ) -> None:
            calls.append(
                ("switch_to_target", {"target_id": target_id, "activate": activate})
            )

    async def unexpected_navigate(*args, **kwargs) -> ToolResult:
        raise AssertionError(
            "force_new=True must create a target directly, not reuse and navigate blank tabs"
        )

    from octop_browser import session as session_mod
    from octop_browser.session import BrowserSession

    monkeypatch.setattr(session_mod.nav_actions, "navigate", unexpected_navigate)

    sess = BrowserSession(FakeInternal(), profile_name="test")  # type: ignore[arg-type]
    result = await sess.new_tab("https://example.com/new", force_new=True)

    assert result.success is True
    assert result.content == "NEW"
    assert calls == [
        ("Target.createTarget", {"url": "https://example.com/new"}),
        ("switch_to_target", {"target_id": "NEW", "activate": True}),
    ]


async def test_close_session_kill_pops_registry_before_close():
    from octop_browser import tool_interface as tool_interface_mod

    profile = "_test_close_kill_"
    events: list[str] = []

    class FakeSession:
        async def close(self, *, kill: bool = False) -> None:
            events.append(f"close:{kill}")
            tool_interface_mod._registry.pop(profile, None)

    tool_interface_mod._registry[profile] = FakeSession()
    try:
        result = await browser_tool(action="close_session", profile=profile, kill=True)
    finally:
        tool_interface_mod._registry.pop(profile, None)

    assert result.success is True
    assert events == ["close:True"]
    assert profile not in tool_interface_mod._registry
