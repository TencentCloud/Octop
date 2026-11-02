#!/usr/bin/env python3
"""Regression test for assets/intake-form.html using local headless Chrome."""

from __future__ import annotations

import json
import pathlib
import subprocess
import tempfile
import time
import urllib.parse
import urllib.request

import websocket


CHROME_CANDIDATES = (
    pathlib.Path.home() / "AppData/Local/Google/Chrome/Application/chrome.exe",
    pathlib.Path("C:/Program Files/Google/Chrome/Application/chrome.exe"),
    pathlib.Path("C:/Program Files (x86)/Google/Chrome/Application/chrome.exe"),
)


def find_chrome() -> pathlib.Path:
    for candidate in CHROME_CANDIDATES:
        if candidate.exists():
            return candidate
    raise RuntimeError("Chrome executable not found")


def wait_for_port(profile: pathlib.Path, timeout: float = 10.0) -> int:
    marker = profile / "DevToolsActivePort"
    deadline = time.time() + timeout
    while time.time() < deadline:
        if marker.exists():
            return int(marker.read_text(encoding="utf-8").splitlines()[0])
        time.sleep(0.05)
    raise RuntimeError("Chrome DevTools port did not become ready")


def get_json(url: str) -> object:
    with urllib.request.urlopen(url, timeout=5) as response:
        return json.load(response)


def main() -> None:
    skill_dir = pathlib.Path(__file__).resolve().parents[1]
    form_path = skill_dir / "assets/intake-form.html"
    if not form_path.exists():
        raise AssertionError(f"Missing asset: {form_path}")

    prefill = {
        "goal": "比较 WorkBuddy 与 JVS Claw",
        "products": "腾讯 WorkBuddy\n阿里云 JVS Claw",
        "industry": "通用办公 AI Agent",
        "scenario": ["跨端远程任务执行", "企业知识库、权限与审计"],
        "strategy": ["SWOT", "PESTLE"],
        "audience": "老板汇报",
        "format": "",
        "constraints": "转化目标 100%，不确定信息标注待验证。",
    }
    query = urllib.parse.urlencode(
        {"prefill": json.dumps(prefill, ensure_ascii=False, separators=(",", ":"))}
    )
    url = form_path.as_uri() + "?" + query

    with tempfile.TemporaryDirectory(prefix="cpr-form-test-") as profile_name:
        profile = pathlib.Path(profile_name)
        process = subprocess.Popen(
            [
                str(find_chrome()),
                "--headless=new",
                "--disable-gpu",
                "--no-first-run",
                "--remote-debugging-port=0",
                "--remote-allow-origins=*",
                f"--user-data-dir={profile}",
                url,
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            port = wait_for_port(profile)
            targets = get_json(f"http://127.0.0.1:{port}/json/list")
            page = next(target for target in targets if target.get("type") == "page")
            ws = websocket.create_connection(page["webSocketDebuggerUrl"], timeout=5)
            counter = 0

            def evaluate(expression: str) -> object:
                nonlocal counter
                counter += 1
                ws.send(
                    json.dumps(
                        {
                            "id": counter,
                            "method": "Runtime.evaluate",
                            "params": {
                                "expression": expression,
                                "returnByValue": True,
                                "awaitPromise": True,
                            },
                        }
                    )
                )
                while True:
                    message = json.loads(ws.recv())
                    if message.get("id") == counter:
                        result = message["result"]["result"]
                        if "exceptionDetails" in message["result"]:
                            raise AssertionError(message["result"]["exceptionDetails"])
                        return result.get("value")

            deadline = time.time() + 5
            while time.time() < deadline and evaluate("document.readyState") != "complete":
                time.sleep(0.05)

            state = evaluate(
                """(() => ({
                  goal: form.elements.goal.value,
                  products: form.elements.products.value,
                  industry: form.elements.industry.value,
                  constraints: form.elements.constraints.value,
                  scenarios: values('scenario'),
                  strategies: values('strategy'),
                  audience: values('audience')[0],
                  format: values('format')[0] || '',
                  columns: getComputedStyle(document.querySelector('.grid')).gridTemplateColumns
                }))()"""
            )
            assert state["goal"] == prefill["goal"]
            assert state["products"] == prefill["products"]
            assert state["industry"] == prefill["industry"]
            assert state["constraints"] == prefill["constraints"]
            assert state["scenarios"] == prefill["scenario"]
            assert state["strategies"] == prefill["strategy"]
            assert state["audience"] == prefill["audience"]
            assert state["format"] == "", "Output format must not be preselected"
            assert state["columns"].split().__len__() == 2, "Desktop layout must use two columns"

            blocked = evaluate(
                """(() => {
                  form.dispatchEvent(new Event('submit', {bubbles:true,cancelable:true}));
                  return {invalid: !form.checkValidity(), resultVisible: document.getElementById('result').classList.contains('show')};
                })()"""
            )
            assert blocked["invalid"] is True
            assert blocked["resultVisible"] is False

            submit_result = evaluate(
                """(async () => {
                  document.querySelector('[name="format"][value="HTML"]').checked = true;
                  form.dispatchEvent(new Event('submit', {bubbles:true,cancelable:true}));
                  await new Promise(resolve => setTimeout(resolve, 150));
                  return {
                    visible: document.getElementById('result').classList.contains('show'),
                    json: document.getElementById('result-json').value
                  };
                })()"""
            )
            assert submit_result["visible"] is True
            payload = json.loads(submit_result["json"])
            assert payload["schema_version"] == "1.0"
            assert payload["skill"] == "competitive-product-research"
            assert payload["action"] == "start_research"
            assert payload["data"]["输出格式"] == "HTML"
            assert payload["data"]["对标对象"] == ["腾讯 WorkBuddy", "阿里云 JVS Claw"]

            evaluate(
                """(() => {
                  Object.defineProperty(window, 'innerWidth', {value: 320, configurable: true});
                  window.dispatchEvent(new Event('resize'));
                })()"""
            )
            ws.send(json.dumps({"id": 999, "method": "Emulation.setDeviceMetricsOverride", "params": {"width": 320, "height": 900, "deviceScaleFactor": 1, "mobile": True}}))
            while json.loads(ws.recv()).get("id") != 999:
                pass
            mobile_columns = evaluate("getComputedStyle(document.querySelector('.grid')).gridTemplateColumns")
            assert len(mobile_columns.split()) == 1, "Mobile layout must collapse to one column"

            ws.close()
            print("PASS: asset exists")
            print("PASS: prefill applied")
            print("PASS: output format starts unselected")
            print("PASS: invalid submit blocked")
            print("PASS: fallback JSON generated")
            print("PASS: desktop and 320px layouts verified")
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()


if __name__ == "__main__":
    main()
