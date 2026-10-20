from octop_browser.record.semantic import SemanticProcessor


def test_semantic_merges_click_input_and_navigation_expectation():
    events = [
        {
            "seq": 1,
            "kind": "recorder_installed",
            "page": {"url": "https://example.com/form"},
        },
        {
            "seq": 2,
            "kind": "click",
            "target": {
                "role": "textbox",
                "accessibleName": "Email",
                "nameAttr": "email",
                "selectorCandidates": ['input[name="email"]'],
            },
        },
        {
            "seq": 3,
            "kind": "input",
            "target": {
                "role": "textbox",
                "accessibleName": "Email",
                "nameAttr": "email",
                "selectorCandidates": ['input[name="email"]'],
            },
            "value": "alice@example.com",
        },
        {
            "seq": 4,
            "kind": "click",
            "target": {"role": "button", "accessibleName": "Submit", "text": "Submit"},
        },
        {"seq": 5, "kind": "navigation", "urlAfter": "https://example.com/done"},
    ]
    doc = SemanticProcessor("rec_test", events).process()
    assert doc.start_url == "https://example.com/form"
    assert [s.kind for s in doc.steps] == ["open", "fill", "click"]
    assert doc.steps[1].value == "{{email}}"
    assert doc.steps[2].expect["urlContains"] == "/done"
    assert doc.verification == [{"type": "url_contains", "value": "/done"}]


def test_semantic_converts_blank_click_navigation_to_navigate_step():
    events = [
        {
            "seq": 1,
            "kind": "click",
            "page": {"url": "about:blank"},
            "target": {
                "tag": "body",
                "xpath": "/html/body[1]",
                "selectorCandidates": ["html > body"],
            },
        },
        {"seq": 2, "kind": "navigation", "urlAfter": "https://www.baidu.com/"},
    ]
    doc = SemanticProcessor("rec_blank", events).process()
    assert [s.kind for s in doc.steps] == ["open", "navigate"]
    assert doc.steps[1].url == "https://www.baidu.com/"


def test_semantic_keeps_last_scroll_before_click():
    events = [
        {
            "seq": 1,
            "kind": "recorder_installed",
            "page": {"url": "https://example.com"},
        },
        {"seq": 2, "kind": "scroll", "scroll": {"x": 0, "y": 10}},
        {"seq": 3, "kind": "scroll", "scroll": {"x": 0, "y": 500}},
        {
            "seq": 4,
            "kind": "click",
            "target": {
                "role": "link",
                "accessibleName": "Details",
                "selectorCandidates": ["a.details"],
            },
        },
    ]
    doc = SemanticProcessor("rec_scroll", events).process()
    assert [s.kind for s in doc.steps] == ["open", "scroll_to", "click"]
    assert doc.steps[1].value == "0.000,500.000"


def test_semantic_records_new_tabs_from_page_opened_events():
    events = [
        {
            "seq": 1,
            "kind": "recorder_installed",
            "targetId": "tab_a",
            "page": {"targetId": "tab_a", "url": "about:blank"},
        },
        {
            "seq": 2,
            "kind": "page_opened",
            "targetId": "tab_b",
            "url": "https://weibo.com/",
            "title": "微博",
        },
        {
            "seq": 3,
            "kind": "page_opened",
            "targetId": "tab_c",
            "url": "https://www.xiaohongshu.com/explore",
            "title": "小红书",
        },
        {
            "seq": 4,
            "kind": "navigation",
            "targetId": "tab_c",
            "urlAfter": "https://www.xiaohongshu.com/explore",
        },
    ]
    doc = SemanticProcessor("rec_tabs", events).process()
    assert [s.kind for s in doc.steps] == ["open", "new_tab", "new_tab"]
    assert doc.steps[1].url == "https://weibo.com/"
    assert doc.steps[1].target == {"targetId": "tab_b"}
    assert doc.steps[2].url == "https://www.xiaohongshu.com/explore"


def test_semantic_drops_weather_result_area_click_after_search_navigation():
    events = [
        {"seq": 1, "kind": "recorder_installed", "page": {"url": "about:blank"}},
        {
            "seq": 2,
            "kind": "click",
            "page": {"url": "about:blank"},
            "target": {
                "tag": "body",
                "xpath": "/html/body[1]",
                "selectorCandidates": ["html > body"],
            },
        },
        {"seq": 3, "kind": "navigation", "urlAfter": "https://www.baidu.com/"},
        {
            "seq": 4,
            "kind": "input",
            "target": {
                "role": "textbox",
                "accessibleName": "百度一下",
                "nameAttr": "wd",
                "selectorCandidates": ['input[name="wd"]'],
            },
            "value": "今天北京天气",
        },
        {
            "seq": 5,
            "kind": "keydown",
            "key": "Enter",
            "target": {
                "role": "textbox",
                "accessibleName": "百度一下",
                "nameAttr": "wd",
                "selectorCandidates": ['input[name="wd"]'],
            },
        },
        {
            "seq": 6,
            "kind": "navigation",
            "urlAfter": "https://www.baidu.com/s?wd=%E4%BB%8A%E5%A4%A9%E5%8C%97%E4%BA%AC%E5%A4%A9%E6%B0%94",
        },
        {"seq": 7, "kind": "scroll", "scroll": {"x": 0, "y": 1040.5}},
        {
            "seq": 8,
            "kind": "click",
            "target": {
                "role": "",
                "accessibleName": "北京 13:35更新 30° 21~34°C 阴 44 优 体感32° 西南风3级 "
                * 4,
                "text": "北京 13:35更新 30° 21~34°C 阴 44 优 体感32° 西南风3级 " * 4,
                "selectorCandidates": ["div:nth-of-type(3)"],
            },
        },
    ]

    doc = SemanticProcessor("rec_weather", events).process()

    assert [s.kind for s in doc.steps] == ["open", "navigate", "fill", "press"]
    assert doc.steps[-1].expect["urlContains"] == "/s"
    assert all("13:35更新" not in str(s.target) for s in doc.steps)


def test_semantic_attach_submit_navigation_to_previous_click():
    events = [
        {
            "seq": 1,
            "kind": "recorder_installed",
            "page": {"url": "https://example.com/form"},
        },
        {
            "seq": 2,
            "kind": "input",
            "target": {
                "role": "textbox",
                "accessibleName": "Search query",
                "nameAttr": "query",
                "selectorCandidates": ['input[name="query"]'],
            },
            "value": "alpha",
        },
        {
            "seq": 3,
            "kind": "click",
            "target": {
                "role": "button",
                "accessibleName": "Search",
                "id": "submit",
                "selectorCandidates": ["#submit"],
            },
        },
        {"seq": 4, "kind": "submit", "target": {"tag": "form", "id": "demo-form"}},
        {
            "seq": 5,
            "kind": "navigation",
            "urlAfter": "https://example.com/done?q=alpha",
        },
    ]

    doc = SemanticProcessor("rec_submit", events).process()

    assert [s.kind for s in doc.steps] == ["open", "fill", "click"]
    assert doc.steps[-1].expect["urlContains"] == "/done"
    assert doc.verification == [{"type": "url_contains", "value": "/done"}]


def test_semantic_uses_initial_page_when_recorder_reinstalls_after_navigation():
    events = [
        {
            "seq": 1,
            "kind": "click",
            "page": {"url": "https://example.com/form"},
            "target": {
                "role": "textbox",
                "accessibleName": "Search query",
                "nameAttr": "query",
                "selectorCandidates": ['input[name="query"]'],
            },
        },
        {
            "seq": 2,
            "kind": "change",
            "page": {"url": "https://example.com/form"},
            "target": {
                "role": "textbox",
                "accessibleName": "Search query",
                "nameAttr": "query",
                "selectorCandidates": ['input[name="query"]'],
            },
            "value": "alpha",
        },
        {
            "seq": 3,
            "kind": "click",
            "page": {"url": "https://example.com/form"},
            "target": {
                "role": "button",
                "accessibleName": "Search",
                "id": "submit",
                "selectorCandidates": ["#submit"],
            },
        },
        {
            "seq": 4,
            "kind": "submit",
            "page": {"url": "https://example.com/form"},
            "target": {"tag": "form", "id": "demo-form"},
        },
        {
            "seq": 5,
            "kind": "navigation",
            "targetId": "tab_a",
            "urlAfter": "https://example.com/done?query=alpha",
        },
        {
            "seq": 6,
            "kind": "recorder_installed",
            "targetId": "tab_a",
            "page": {
                "targetId": "tab_a",
                "url": "https://example.com/done?query=alpha",
            },
            "url": "https://example.com/done?query=alpha",
        },
    ]

    doc = SemanticProcessor("rec_reinstall", events).process()

    assert doc.start_url == "https://example.com/form"
    assert [s.kind for s in doc.steps] == ["open", "fill", "click"]
    assert doc.steps[-1].expect["urlContains"] == "/done"


def test_semantic_treats_navigation_on_new_target_as_new_tab_when_page_opened_missing():
    events = [
        {
            "seq": 1,
            "kind": "recorder_installed",
            "targetId": "tab_a",
            "page": {"targetId": "tab_a", "url": "https://example.com/start"},
        },
        {
            "seq": 2,
            "kind": "navigation",
            "targetId": "tab_b",
            "urlAfter": "https://weibo.com/",
        },
        {
            "seq": 3,
            "kind": "navigation",
            "targetId": "tab_c",
            "urlAfter": "https://www.bilibili.com/",
        },
    ]

    doc = SemanticProcessor("rec_targets", events).process()

    assert [s.kind for s in doc.steps] == ["open", "new_tab", "new_tab"]
    assert doc.steps[1].target == {"targetId": "tab_b"}
    assert doc.steps[1].url == "https://weibo.com/"
    assert doc.steps[2].target == {"targetId": "tab_c"}
    assert doc.steps[2].url == "https://www.bilibili.com/"


def test_semantic_names_baidu_wd_input_as_query():
    events = [
        {
            "seq": 1,
            "kind": "recorder_installed",
            "page": {"url": "https://www.baidu.com/"},
        },
        {
            "seq": 2,
            "kind": "input",
            "target": {
                "role": "textbox",
                "accessibleName": "百度一下",
                "nameAttr": "wd",
                "selectorCandidates": ['input[name="wd"]'],
            },
            "value": "今天北京天气",
        },
    ]

    doc = SemanticProcessor("rec_baidu", events).process()

    assert doc.inputs == [
        {"name": "query", "kind": "string", "required": True, "example": "今天北京天气"}
    ]
    assert doc.steps[1].value == "{{query}}"


def test_semantic_turns_select_change_into_select_step():
    events = [
        {
            "seq": 1,
            "kind": "recorder_installed",
            "page": {"url": "https://example.com/form"},
        },
        {
            "seq": 2,
            "kind": "change",
            "target": {
                "tag": "select",
                "role": "combobox",
                "accessibleName": "Country",
                "nameAttr": "country",
                "selectorCandidates": ['select[name="country"]'],
            },
            "value": "CN",
        },
    ]

    doc = SemanticProcessor("rec_select", events).process()

    assert [s.kind for s in doc.steps] == ["open", "select"]
    assert doc.steps[1].value == "{{country}}"
    assert doc.inputs == [
        {"name": "country", "kind": "string", "required": True, "example": "CN"}
    ]


def test_semantic_turns_checkbox_change_into_set_checked_step():
    events = [
        {
            "seq": 1,
            "kind": "recorder_installed",
            "page": {"url": "https://example.com/form"},
        },
        {
            "seq": 2,
            "kind": "click",
            "target": {
                "tag": "input",
                "type": "checkbox",
                "role": "checkbox",
                "accessibleName": "Subscribe",
                "id": "subscribe",
                "selectorCandidates": ["#subscribe"],
            },
        },
        {
            "seq": 3,
            "kind": "change",
            "target": {
                "tag": "input",
                "type": "checkbox",
                "role": "checkbox",
                "accessibleName": "Subscribe",
                "id": "subscribe",
                "selectorCandidates": ["#subscribe"],
            },
            "value": "on",
            "checked": True,
        },
    ]

    doc = SemanticProcessor("rec_check", events).process()

    assert [s.kind for s in doc.steps] == ["open", "set_checked"]
    assert doc.steps[1].value == "true"
    assert doc.steps[1].target["id"] == "subscribe"


def test_semantic_ignores_about_blank_noise_after_real_tab_navigation():
    events = [
        {
            "seq": 1,
            "kind": "recorder_installed",
            "targetId": "tab_a",
            "page": {"targetId": "tab_a", "url": "https://www.baidu.com/"},
        },
        {
            "seq": 2,
            "kind": "page_opened",
            "targetId": "tab_b",
            "url": "chrome://newtab/",
            "title": "新标签页",
        },
        {
            "seq": 3,
            "kind": "navigation",
            "targetId": "tab_b",
            "urlAfter": "https://www.bilibili.com/",
        },
        {
            "seq": 4,
            "kind": "recorder_installed",
            "targetId": "tab_b",
            "page": {"targetId": "tab_b", "url": "https://www.bilibili.com/"},
            "url": "https://www.bilibili.com/",
        },
        {
            "seq": 5,
            "kind": "page_opened",
            "targetId": "tab_c",
            "url": "chrome://newtab/",
            "title": "新标签页",
        },
        {
            "seq": 6,
            "kind": "navigation",
            "targetId": "tab_b",
            "urlAfter": "about:blank",
        },
        {
            "seq": 7,
            "kind": "recorder_installed",
            "targetId": "tab_b",
            "page": {
                "targetId": "tab_b",
                "url": "about:blank",
                "viewport": {"width": 0, "height": 0},
            },
            "url": "about:blank",
        },
        {
            "seq": 8,
            "kind": "navigation",
            "targetId": "tab_c",
            "urlAfter": "https://www.xiaohongshu.com/explore",
        },
        {
            "seq": 9,
            "kind": "recorder_installed",
            "targetId": "tab_c",
            "page": {"targetId": "tab_c", "url": "https://www.xiaohongshu.com/explore"},
            "url": "https://www.xiaohongshu.com/explore",
        },
        {
            "seq": 10,
            "kind": "navigation",
            "targetId": "tab_c",
            "urlAfter": "about:blank",
        },
        {
            "seq": 11,
            "kind": "recorder_installed",
            "targetId": "tab_c",
            "page": {
                "targetId": "tab_c",
                "url": "about:blank",
                "viewport": {"width": 0, "height": 0},
            },
            "url": "about:blank",
        },
    ]

    doc = SemanticProcessor("rec_blank_noise", events).process()

    urls = [s.url for s in doc.steps if s.url]
    assert "about:blank" not in urls
    assert [(s.kind, s.url, s.target) for s in doc.steps] == [
        ("open", "https://www.baidu.com/", None),
        ("new_tab", "https://www.bilibili.com/", {"targetId": "tab_b"}),
        ("new_tab", "https://www.xiaohongshu.com/explore", {"targetId": "tab_c"}),
    ]


def test_semantic_ignores_known_transient_auth_and_risk_redirects_after_requested_pages():
    events = [
        {
            "seq": 1,
            "kind": "navigation",
            "targetId": "tab_bili",
            "urlAfter": "https://www.bilibili.com/",
        },
        {
            "seq": 2,
            "kind": "page_opened",
            "targetId": "tab_xhs",
            "url": "https://www.xiaohongshu.com/explore",
        },
        {
            "seq": 3,
            "kind": "page_opened",
            "targetId": "tab_weibo",
            "url": "https://weibo.com/",
        },
        {
            "seq": 4,
            "kind": "page_opened",
            "targetId": "tab_baidu",
            "url": "https://www.baidu.com/s?wd=%E4%BB%8A%E5%A4%A9%E5%A4%A9%E6%B0%94%E6%80%8E%E4%B9%88%E6%A0%B7",
        },
        {
            "seq": 5,
            "kind": "page_opened",
            "targetId": "tab_weather",
            "url": "https://www.weather.com.cn/",
        },
        {
            "seq": 6,
            "kind": "navigation",
            "targetId": "tab_weibo",
            "urlAfter": (
                "https://passport.weibo.com/visitor/visitor?entry=miniblog"
                "&a=enter&url=https%3A%2F%2Fweibo.com%2F&domain=weibo.com"
            ),
        },
        {
            "seq": 7,
            "kind": "navigation",
            "targetId": "tab_baidu",
            "urlAfter": (
                "https://wappass.baidu.com/static/captcha/tuxing_v2.html"
                "?backurl=https%3A%2F%2Fwww.baidu.com%2Fs%3Fwd%3Dweather"
            ),
        },
        {
            "seq": 8,
            "kind": "navigation",
            "targetId": "tab_xhs",
            "urlAfter": (
                "https://www.xiaohongshu.com/website-login/error"
                "?redirectPath=https%3A%2F%2Fwww.xiaohongshu.com%2Fexplore"
                "&error_code=300012&error_msg=IP%E5%AD%98%E5%9C%A8%E9%A3%8E%E9%99%A9"
            ),
        },
        {
            "seq": 9,
            "kind": "navigation",
            "targetId": "tab_weibo",
            "urlAfter": "https://weibo.com/newlogin?url=https%3A%2F%2Fweibo.com%2F",
        },
        {
            "seq": 10,
            "kind": "history.replaceState",
            "targetId": "tab_weibo",
            "urlAfter": (
                "https://weibo.com/newlogin?tabtype=weibo&gid=102803"
                "&openLoginLayer=0&url=https%3A%2F%2Fweibo.com%2F"
            ),
        },
    ]

    doc = SemanticProcessor("rec_transient_redirects", events).process()

    assert [(step.kind, step.url, step.target) for step in doc.steps] == [
        ("open", "https://www.bilibili.com/", None),
        ("new_tab", "https://www.xiaohongshu.com/explore", {"targetId": "tab_xhs"}),
        ("new_tab", "https://weibo.com/", {"targetId": "tab_weibo"}),
        (
            "new_tab",
            "https://www.baidu.com/s?wd=%E4%BB%8A%E5%A4%A9%E5%A4%A9%E6%B0%94%E6%80%8E%E4%B9%88%E6%A0%B7",
            {"targetId": "tab_baidu"},
        ),
        ("new_tab", "https://www.weather.com.cn/", {"targetId": "tab_weather"}),
    ]
