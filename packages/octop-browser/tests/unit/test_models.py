from octop_browser.models import ActionMetrics, TabInfo, ToolResult


def test_action_metrics_defaults():
    m = ActionMetrics(
        action="click",
        duration_ms=120,
        dom_nodes_scanned=45,
        estimated_tokens=180,
    )
    assert m.screenshot_size_kb == 0


def test_tool_result_success():
    m = ActionMetrics(
        action="navigate", duration_ms=300, dom_nodes_scanned=0, estimated_tokens=20
    )
    r = ToolResult(success=True, content="Navigated to https://example.com", metrics=m)
    assert r.error is None
    assert r.success is True


def test_tool_result_failure():
    m = ActionMetrics(
        action="click", duration_ms=10, dom_nodes_scanned=0, estimated_tokens=0
    )
    r = ToolResult(success=False, content="", error="Element not found", metrics=m)
    assert r.success is False
    assert r.error == "Element not found"


def test_tool_result_structured_content():
    m = ActionMetrics(
        action="dom_tree", duration_ms=200, dom_nodes_scanned=120, estimated_tokens=350
    )
    data = {"url": "https://example.com", "elements": []}
    r = ToolResult(success=True, content=data, metrics=m)
    assert isinstance(r.content, dict)


def test_tab_info():
    t = TabInfo(tab_id="tab_0", url="https://example.com", title="Example", active=True)
    assert t.active is True
