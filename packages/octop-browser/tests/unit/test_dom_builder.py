import json

from octop_browser.dom.builder import DOMBuilder
from octop_browser.dom.refs import RefCache

# Minimal synthetic CDP DOM tree
SAMPLE_DOM = {
    "nodeId": 1,
    "nodeType": 9,
    "nodeName": "#document",
    "children": [
        {
            "nodeId": 2,
            "nodeType": 1,
            "nodeName": "HTML",
            "children": [
                {
                    "nodeId": 3,
                    "nodeType": 1,
                    "nodeName": "BODY",
                    "children": [
                        {
                            "nodeId": 10,
                            "nodeType": 1,
                            "nodeName": "H1",
                            "children": [
                                {
                                    "nodeId": 11,
                                    "nodeType": 3,
                                    "nodeName": "#text",
                                    "nodeValue": "Login",
                                }
                            ],
                            "attributes": [],
                        },
                        {
                            "nodeId": 20,
                            "nodeType": 1,
                            "nodeName": "INPUT",
                            "children": [],
                            "attributes": ["type", "text", "placeholder", "Username"],
                        },
                        {
                            "nodeId": 30,
                            "nodeType": 1,
                            "nodeName": "BUTTON",
                            "children": [
                                {
                                    "nodeId": 31,
                                    "nodeType": 3,
                                    "nodeName": "#text",
                                    "nodeValue": "Sign in",
                                }
                            ],
                            "attributes": [],
                        },
                        {
                            "nodeId": 40,
                            "nodeType": 1,
                            "nodeName": "A",
                            "children": [
                                {
                                    "nodeId": 41,
                                    "nodeType": 3,
                                    "nodeName": "#text",
                                    "nodeValue": "Forgot?",
                                }
                            ],
                            "attributes": ["href", "/forgot"],
                        },
                    ],
                    "attributes": [],
                }
            ],
            "attributes": [],
        }
    ],
}


def make_builder():
    cache = RefCache()
    return DOMBuilder(
        dom=SAMPLE_DOM,
        url="https://example.com/login",
        title="Login Page",
        ref_cache=cache,
    ), cache


def test_minimal_output():
    builder, _ = make_builder()
    out = builder.build(level="minimal")
    assert "https://example.com/login" in out
    assert "Login Page" in out
    assert "Interactive elements:" in out


def test_interactive_output_has_refs():
    builder, cache = make_builder()
    out = builder.build(level="interactive")
    assert "[ref=" in out
    assert len(cache.all_refs()) > 0


def test_full_output_has_h1():
    builder, _ = make_builder()
    out = builder.build(level="full")
    assert "h1" in out.lower() or "H1" in out


def test_structured_output_is_valid_json():
    builder, _ = make_builder()
    result = builder.build(level="structured")
    data = json.loads(result)
    assert data["url"] == "https://example.com/login"
    assert isinstance(data["elements"], list)
    assert any(e["tag"].lower() == "button" for e in data["elements"])


def test_interactive_refs_stored_in_cache():
    builder, cache = make_builder()
    builder.build(level="interactive")
    refs = cache.all_refs()
    node_ids = set(refs.values())
    assert 20 in node_ids  # input
    assert 30 in node_ids  # button


def test_structured_output_marks_iframe_and_shadow_contexts():
    dom = {
        "nodeId": 1,
        "nodeType": 9,
        "nodeName": "#document",
        "children": [
            {
                "nodeId": 2,
                "nodeType": 1,
                "nodeName": "HTML",
                "attributes": [],
                "children": [
                    {
                        "nodeId": 3,
                        "nodeType": 1,
                        "nodeName": "BODY",
                        "attributes": [],
                        "children": [
                            {
                                "nodeId": 10,
                                "nodeType": 1,
                                "nodeName": "IFRAME",
                                "attributes": ["id", "login-frame"],
                                "contentDocument": {
                                    "nodeId": 11,
                                    "nodeType": 9,
                                    "nodeName": "#document",
                                    "children": [
                                        {
                                            "nodeId": 12,
                                            "nodeType": 1,
                                            "nodeName": "BUTTON",
                                            "attributes": ["id", "inside-frame"],
                                            "children": [
                                                {
                                                    "nodeId": 13,
                                                    "nodeType": 3,
                                                    "nodeName": "#text",
                                                    "nodeValue": "Frame Button",
                                                }
                                            ],
                                        }
                                    ],
                                },
                            },
                            {
                                "nodeId": 20,
                                "nodeType": 1,
                                "nodeName": "DIV",
                                "attributes": ["id", "host"],
                                "shadowRoots": [
                                    {
                                        "nodeId": 21,
                                        "nodeType": 11,
                                        "nodeName": "#document-fragment",
                                        "children": [
                                            {
                                                "nodeId": 22,
                                                "nodeType": 1,
                                                "nodeName": "BUTTON",
                                                "attributes": ["id", "inside-shadow"],
                                                "children": [
                                                    {
                                                        "nodeId": 23,
                                                        "nodeType": 3,
                                                        "nodeName": "#text",
                                                        "nodeValue": "Shadow Button",
                                                    }
                                                ],
                                            }
                                        ],
                                    }
                                ],
                            },
                        ],
                    }
                ],
            }
        ],
    }
    builder = DOMBuilder(
        dom=dom, url="https://example.com", title="Ctx", ref_cache=RefCache()
    )

    data = json.loads(builder.build(level="structured"))

    frame_button = next(e for e in data["elements"] if e.get("id") == "inside-frame")
    shadow_button = next(e for e in data["elements"] if e.get("id") == "inside-shadow")
    assert frame_button["framePath"] == ["iframe#login-frame"]
    assert shadow_button["shadowPath"] == ["#host"]
