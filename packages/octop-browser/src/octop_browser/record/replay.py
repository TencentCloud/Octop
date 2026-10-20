"""Replay recorded semantic steps using octop-browser actions."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus, urlsplit, urlunsplit

from octop_browser.record.matcher import match_target
from octop_browser.record.store import RecordingStore
from octop_browser.record.url_filter import is_transient_auth_or_risk_url
from octop_browser.tool_interface import browser_tool


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ReplayRunner:
    def __init__(self, store: RecordingStore | None = None) -> None:
        self.store = store or RecordingStore()

    async def run(
        self,
        recording_id: str,
        profile: str = "default",
        inputs: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        steps_doc = self.store.read_steps(recording_id)
        values = inputs or {}
        target_map: dict[str, str] = {}
        current_recorded_target = ""
        report: dict[str, Any] = {
            "recordingId": recording_id,
            "startedAt": _now(),
            "status": "running",
            "inputs": values,
            "stepsLoaded": len(steps_doc.steps),
            "steps": [],
            "verification": [],
        }
        try:
            if not steps_doc.steps:
                raise RuntimeError("Recording has no replayable steps")
            for step in steps_doc.steps:
                entry: dict[str, Any] = {
                    "id": step.id,
                    "kind": step.kind,
                    "status": "running",
                }
                if step.kind == "open" and step.url:
                    recorded_target_id = self._step_target_id(step)
                    url = self._resolve_url(step.url, values)
                    res = await browser_tool("navigate", profile=profile, url=url)
                    entry.update(
                        {
                            "status": "passed" if res.success else "failed",
                            "urlAfter": url,
                            "error": res.error,
                        }
                    )
                    if recorded_target_id:
                        current_recorded_target = recorded_target_id
                elif step.kind == "new_tab" and step.url:
                    url = self._resolve_url(step.url, values)
                    res = await browser_tool(
                        "new_tab", profile=profile, url=url, force_new=True
                    )
                    new_tab_id = str(res.content) if res.success and res.content else ""
                    recorded_target_id = self._step_target_id(step)
                    if recorded_target_id and new_tab_id:
                        target_map[recorded_target_id] = new_tab_id
                        current_recorded_target = recorded_target_id
                    entry.update(
                        {
                            "status": "passed" if res.success else "failed",
                            "tabId": new_tab_id or None,
                            "urlAfter": url,
                            "error": res.error,
                        }
                    )
                elif (
                    step.kind in {"click", "fill", "select", "set_checked"}
                    and step.target
                ):
                    switched = await self._switch_for_step_target(
                        step,
                        profile=profile,
                        target_map=target_map,
                        current_recorded_target=current_recorded_target,
                    )
                    if switched is not None:
                        entry["switchTab"] = switched.success
                        if not switched.success:
                            entry.update({"status": "failed", "error": switched.error})
                            report["steps"].append(entry)
                            report[
                                "failureArtifacts"
                            ] = await self._capture_failure_artifacts(
                                recording_id,
                                profile,
                                step.id,
                                reason=switched.error or "switch_tab failed",
                            )
                            report["status"] = "failed"
                            break
                        current_recorded_target = (
                            self._step_target_id(step) or current_recorded_target
                        )
                    dom = await browser_tool(
                        "dom_tree", profile=profile, level="structured"
                    )
                    if not dom.success or not isinstance(dom.content, str):
                        raise RuntimeError(dom.error or "Could not get DOM snapshot")
                    ref, matched_by = match_target(step.target, dom.content)
                    if ref:
                        if step.kind == "click":
                            res = await browser_tool("click", profile=profile, ref=ref)
                        elif step.kind == "fill":
                            text = self._resolve_value(step.value or "", values)
                            res = await browser_tool(
                                "fill", profile=profile, ref=ref, text=text
                            )
                        elif step.kind == "select":
                            value = self._resolve_value(step.value or "", values)
                            res = await browser_tool(
                                "select", profile=profile, ref=ref, value=value
                            )
                        else:
                            fallback = await self._fallback_dom_action(
                                step, profile, values
                            )
                            if fallback is not None:
                                res, matched_by = fallback
                            else:
                                desired = self._resolve_checked(step.value)
                                res = await browser_tool(
                                    "eval_js",
                                    profile=profile,
                                    expression=self._set_checked_by_ref_js(
                                        ref, desired
                                    ),
                                )
                        entry.update(
                            {
                                "status": "passed" if res.success else "failed",
                                "ref": ref,
                                "matchedBy": matched_by,
                                "error": res.error,
                            }
                        )
                    else:
                        fallback = await self._fallback_dom_action(
                            step, profile, values
                        )
                        if fallback is None:
                            message = (
                                f"Could not match target for {step.id}: {step.target}"
                            )
                            entry.update(
                                {
                                    "status": "failed",
                                    "matchedBy": "not-found",
                                    "error": message,
                                }
                            )
                            report["steps"].append(entry)
                            report[
                                "failureArtifacts"
                            ] = await self._capture_failure_artifacts(
                                recording_id,
                                profile,
                                step.id,
                                reason=message,
                                dom_content=dom.content,
                            )
                            report["status"] = "failed"
                            break
                        res, matched_by = fallback
                        entry.update(
                            {
                                "status": "passed" if res.success else "failed",
                                "matchedBy": matched_by,
                                "error": res.error,
                            }
                        )
                    if step.expect and step.expect.get("urlContains"):
                        wait = await browser_tool(
                            "wait",
                            profile=profile,
                            url_contains=str(step.expect["urlContains"]),
                            timeout_ms=10000,
                        )
                        entry["wait"] = wait.success
                        if not wait.success:
                            entry["status"] = "failed"
                            entry["error"] = wait.error
                elif step.kind == "press" and step.key:
                    res = await browser_tool("press", profile=profile, key=step.key)
                    entry.update(
                        {
                            "status": "passed" if res.success else "failed",
                            "error": res.error,
                        }
                    )
                elif step.kind == "navigate" and step.url:
                    url = self._resolve_url(step.url, values)
                    if is_transient_auth_or_risk_url(url):
                        entry.update(
                            {
                                "status": "skipped",
                                "urlAfter": url,
                                "reason": "transient_auth_or_risk_redirect",
                            }
                        )
                        report["steps"].append(entry)
                        continue
                    target_id = self._step_target_id(step)
                    runtime_target_id = (
                        target_map.get(target_id, target_id) if target_id else ""
                    )
                    if runtime_target_id:
                        switched = await browser_tool(
                            "switch_tab", profile=profile, tab_id=runtime_target_id
                        )
                        entry["switchTab"] = switched.success
                        if switched.success:
                            current_recorded_target = (
                                target_id or current_recorded_target
                            )
                    res = await browser_tool("navigate", profile=profile, url=url)
                    entry.update(
                        {
                            "status": "passed" if res.success else "failed",
                            "urlAfter": url,
                            "error": res.error,
                        }
                    )
                elif step.kind == "scroll_to" and step.value:
                    switched = await self._switch_for_step_target(
                        step,
                        profile=profile,
                        target_map=target_map,
                        current_recorded_target=current_recorded_target,
                    )
                    if switched is not None:
                        entry["switchTab"] = switched.success
                        if switched.success:
                            current_recorded_target = (
                                self._step_target_id(step) or current_recorded_target
                            )
                    x, y = self._parse_scroll_value(step.value)
                    scroll_expr = (
                        f"window.scrollTo({x}, {y});"
                        f" JSON.stringify({{x: window.scrollX, y: window.scrollY}})"
                    )
                    res = await browser_tool(
                        "eval_js", profile=profile, expression=scroll_expr
                    )
                    entry.update(
                        {
                            "status": "passed" if res.success else "failed",
                            "scroll": {"x": x, "y": y},
                            "error": res.error,
                        }
                    )
                else:
                    entry.update({"status": "skipped"})
                report["steps"].append(entry)
                if entry["status"] == "failed":
                    report["failureArtifacts"] = await self._capture_failure_artifacts(
                        recording_id,
                        profile,
                        step.id,
                        reason=str(entry.get("error") or "step failed"),
                    )
                    report["status"] = "failed"
                    break
            else:
                executed = [s for s in report["steps"] if s.get("status") != "skipped"]
                if not executed:
                    raise RuntimeError("Recording has no executable steps")
                verification_failed = await self._run_verification(
                    steps_doc.verification,
                    profile=profile,
                    report=report,
                )
                report["status"] = "failed" if verification_failed else "passed"
            report["endedAt"] = _now()
        except Exception as exc:  # pylint: disable=broad-except
            report["status"] = "failed"
            report["error"] = str(exc)
            report["endedAt"] = _now()
        path = self._write_report(recording_id, report)
        report["reportPath"] = str(path)
        return report

    def _step_target_id(self, step: Any) -> str:
        target = getattr(step, "target", None)
        if isinstance(target, dict):
            value = target.get("targetId")
            return str(value) if value else ""
        return ""

    async def _switch_for_step_target(
        self,
        step: Any,
        *,
        profile: str,
        target_map: dict[str, str],
        current_recorded_target: str,
    ) -> Any | None:
        target_id = self._step_target_id(step)
        if not target_id:
            return None
        runtime_target_id = target_map.get(target_id)
        if not runtime_target_id:
            return None
        # Intentionally switch even when the recorded target appears current:
        # browser focus can drift between CLI calls, user actions, and replay
        # fallback JavaScript. Re-activating the intended tab is cheap and makes
        # multi-tab replay deterministic.
        return await browser_tool(
            "switch_tab", profile=profile, tab_id=runtime_target_id
        )

    async def _run_verification(
        self,
        verification: list[dict[str, Any]],
        *,
        profile: str,
        report: dict[str, Any],
    ) -> bool:
        failed = False
        for item in verification:
            typ = str(item.get("type") or "")
            value = str(item.get("value") or "")
            entry: dict[str, Any] = {"type": typ, "value": value, "status": "running"}
            if typ == "url_contains" and value:
                res = await browser_tool(
                    "wait", profile=profile, url_contains=value, timeout_ms=10000
                )
                entry.update({"status": "passed" if res.success else "failed"})
                if res.error:
                    entry["error"] = res.error
            elif typ == "text_contains" and value:
                res = await browser_tool(
                    "wait", profile=profile, text=value, timeout_ms=10000
                )
                entry.update({"status": "passed" if res.success else "failed"})
                if res.error:
                    entry["error"] = res.error
            elif typ == "selector_exists" and value:
                res = await browser_tool(
                    "wait", profile=profile, selector=value, timeout_ms=10000
                )
                entry.update({"status": "passed" if res.success else "failed"})
                if res.error:
                    entry["error"] = res.error
            elif typ == "title_contains" and value:
                res = await browser_tool(
                    "eval_js",
                    profile=profile,
                    expression="document.title.includes("
                    + json.dumps(value, ensure_ascii=False)
                    + ")",
                )
                passed = res.success and self._truthy_js_content(res.content)
                entry.update({"status": "passed" if passed else "failed"})
                if res.error:
                    entry["error"] = res.error
            elif typ == "element_text_contains" and value and item.get("selector"):
                selector = str(item.get("selector") or "")
                res = await browser_tool(
                    "eval_js",
                    profile=profile,
                    expression=(
                        "(() => { const el = document.querySelector("
                        + json.dumps(selector, ensure_ascii=False)
                        + "); return !!el && (el.innerText || el.textContent || '').includes("
                        + json.dumps(value, ensure_ascii=False)
                        + "); })()"
                    ),
                )
                passed = res.success and self._truthy_js_content(res.content)
                entry.update(
                    {"status": "passed" if passed else "failed", "selector": selector}
                )
                if res.error:
                    entry["error"] = res.error
            elif typ == "input_value_equals" and item.get("selector"):
                selector = str(item.get("selector") or "")
                res = await browser_tool(
                    "eval_js",
                    profile=profile,
                    expression=(
                        "(() => { const el = document.querySelector("
                        + json.dumps(selector, ensure_ascii=False)
                        + "); return !!el && String(el.value ?? '') === "
                        + json.dumps(value, ensure_ascii=False)
                        + "; })()"
                    ),
                )
                passed = res.success and self._truthy_js_content(res.content)
                entry.update(
                    {"status": "passed" if passed else "failed", "selector": selector}
                )
                if res.error:
                    entry["error"] = res.error
            else:
                entry.update(
                    {"status": "skipped", "error": f"Unsupported verification: {typ}"}
                )
            report.setdefault("verification", []).append(entry)
            if entry["status"] == "failed":
                report["error"] = (
                    entry.get("error") or f"Verification failed: {typ}={value}"
                )
                failed = True
                break
        return failed

    async def _capture_failure_artifacts(
        self,
        recording_id: str,
        profile: str,
        step_id: str,
        *,
        reason: str,
        dom_content: str | None = None,
    ) -> dict[str, str]:
        reports_dir = self.store.recording_dir(recording_id) / "replay-reports"
        reports_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        artifact_dir = reports_dir / f"failure_{stamp}_{step_id}"
        artifact_dir.mkdir(parents=True, exist_ok=True)

        artifacts: dict[str, str] = {}
        reason_path = artifact_dir / "reason.txt"
        reason_path.write_text(reason, encoding="utf-8")
        artifacts["reasonPath"] = str(reason_path)

        if dom_content is None:
            dom = await browser_tool("dom_tree", profile=profile, level="structured")
            if dom.success and isinstance(dom.content, str):
                dom_content = dom.content
        if dom_content is not None:
            dom_path = artifact_dir / "dom_snapshot.json"
            dom_path.write_text(dom_content, encoding="utf-8")
            artifacts["domSnapshotPath"] = str(dom_path)

        screenshot_path = artifact_dir / "screenshot.png"
        shot = await browser_tool(
            "screenshot",
            profile=profile,
            full_page=True,
            path=str(screenshot_path),
        )
        if shot.success:
            artifacts["screenshotPath"] = str(shot.content or screenshot_path)
        elif shot.error:
            screenshot_error = artifact_dir / "screenshot_error.txt"
            screenshot_error.write_text(str(shot.error), encoding="utf-8")
            artifacts["screenshotErrorPath"] = str(screenshot_error)
        return artifacts

    async def _fallback_dom_action(
        self,
        step: Any,
        profile: str,
        inputs: dict[str, str],
    ) -> tuple[Any, str] | None:
        target = step.target or {}
        selectors = [
            s
            for s in target.get("selectorCandidates") or []
            if isinstance(s, str) and s.strip()
        ]
        xpath = target.get("xpath")
        bbox = target.get("bbox") if isinstance(target.get("bbox"), dict) else None

        if selectors or xpath:
            text = self._resolve_value(step.value or "", inputs)
            js = self._selector_xpath_js(step.kind, selectors, str(xpath or ""), text)
            res = await browser_tool("eval_js", profile=profile, expression=js)
            if res.success:
                return res, "selector/xpath"

        if step.kind == "click" and bbox:
            x = int(float(bbox.get("x", 0)) + float(bbox.get("width", 0)) / 2)
            y = int(float(bbox.get("y", 0)) + float(bbox.get("height", 0)) / 2)
            if x >= 0 and y >= 0:
                res = await browser_tool("click", profile=profile, x=x, y=y)
                return res, "bbox"
        return None

    def _selector_xpath_js(
        self, kind: str, selectors: list[str], xpath: str, text: str
    ) -> str:
        return (
            """
(() => {
  const selectors = __SELECTORS__;
  const xpath = __XPATH__;
  const kind = __KIND__;
  const text = __TEXT__;
  let el = null;
  for (const selector of selectors) {
    try {
      el = document.querySelector(selector);
      if (el) break;
    } catch (_) {}
  }
  if (!el && xpath) {
    const result = document.evaluate(xpath, document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null);
    el = result.singleNodeValue;
  }
  if (!el) {
    throw new Error('target not found by selector/xpath');
  }
  el.scrollIntoView({block: 'center', inline: 'center'});
  if (kind === 'fill') {
    el.focus();
    el.value = text;
    el.dispatchEvent(new InputEvent('input', {bubbles: true, inputType: 'insertText', data: text}));
    el.dispatchEvent(new Event('change', {bubbles: true}));
    return JSON.stringify({ok: true, action: 'fill'});
  }
  if (kind === 'select') {
    el.focus();
    el.value = text;
    el.dispatchEvent(new Event('input', {bubbles: true}));
    el.dispatchEvent(new Event('change', {bubbles: true}));
    return JSON.stringify({ok: true, action: 'select', value: el.value});
  }
  if (kind === 'set_checked') {
    const desired = text === 'true' || text === '1' || text === 'yes' || text === 'on';
    if ('checked' in el) {
      el.checked = desired;
      el.dispatchEvent(new Event('input', {bubbles: true}));
      el.dispatchEvent(new Event('change', {bubbles: true}));
      return JSON.stringify({ok: true, action: 'set_checked', checked: el.checked});
    }
    const current = el.getAttribute('aria-checked') === 'true';
    if (current !== desired) el.click();
    return JSON.stringify({ok: true, action: 'set_checked', checked: desired});
  }
  el.click();
  return JSON.stringify({ok: true, action: 'click'});
})()
""".replace("__SELECTORS__", json.dumps(selectors, ensure_ascii=False))
            .replace("__XPATH__", json.dumps(xpath, ensure_ascii=False))
            .replace("__KIND__", json.dumps(kind))
            .replace("__TEXT__", json.dumps(text, ensure_ascii=False))
        )

    def _parse_scroll_value(self, value: str) -> tuple[float, float]:
        try:
            x_raw, y_raw = value.split(",", 1)
            return float(x_raw), float(y_raw)
        except (ValueError, TypeError):
            return 0.0, 0.0

    def _resolve_value(self, value: str, inputs: dict[str, str]) -> str:
        if value.startswith("{{") and value.endswith("}}"):
            key = value[2:-2].strip()
            return inputs.get(key, "")
        return value

    def _resolve_checked(self, value: str | None) -> bool:
        return str(value or "").strip().lower() in {"true", "1", "yes", "on", "checked"}

    def _truthy_js_content(self, content: object) -> bool:
        if isinstance(content, bool):
            return content
        if isinstance(content, str):
            return content.strip().lower() in {"true", '"true"', "1"}
        return bool(content)

    def _set_checked_by_ref_js(self, ref: str, desired: bool) -> str:
        return (
            "(() => {"
            "const refs = Array.from(document.querySelectorAll("
            "'input[type="
            '"checkbox"],input[type="radio"],'
            '[role="checkbox"],[role="switch"]'
            "'));"
            "const index = Number(" + json.dumps(str(ref).split("_")[-1]) + ");"
            "const el = refs[index];"
            "if (!el) throw new Error('target not found by ref for set_checked');"
            "const desired = " + ("true" if desired else "false") + ";"
            "if ('checked' in el) { el.checked = desired;"
            " el.dispatchEvent(new Event('input', {bubbles:true}));"
            " el.dispatchEvent(new Event('change', {bubbles:true}));"
            " return JSON.stringify({ok:true, action:'set_checked',"
            " checked:el.checked}); }"
            "const current = el.getAttribute('aria-checked') === 'true';"
            " if (current !== desired) el.click();"
            " return JSON.stringify({ok:true, action:'set_checked',"
            " checked:desired});"
            "})()"
        )

    def _resolve_url(self, url: str, inputs: dict[str, str]) -> str:
        resolved = url
        for key, value in inputs.items():
            resolved = resolved.replace("{{" + key + "}}", value)

        # If a query input is provided, make search-engine result URLs replay
        # the new query value too. This fixes recordings that search Baidu via
        # Enter: the semantic steps are fill -> press -> recorded navigation.
        query = inputs.get("query")
        if query:
            resolved = self._replace_known_search_query(resolved, query)
        return resolved

    def _replace_known_search_query(self, url: str, query: str) -> str:
        try:
            parts = urlsplit(url)
        except ValueError:
            return url
        host = parts.netloc.lower()
        key = ""
        if "baidu." in host:
            key = "wd"
        elif "google." in host or "bing." in host:
            key = "q"
        if not key or f"{key}=" not in parts.query:
            return url
        pairs = []
        replaced = False
        for part in parts.query.split("&"):
            name = part.split("=", 1)[0]
            if name == key:
                pairs.append(f"{key}={quote_plus(query)}")
                replaced = True
            else:
                pairs.append(part)
        if not replaced:
            return url
        return urlunsplit(
            (parts.scheme, parts.netloc, parts.path, "&".join(pairs), parts.fragment)
        )

    def _write_report(self, recording_id: str, report: dict[str, Any]) -> Path:
        rec_dir = self.store.recording_dir(recording_id)
        reports = rec_dir / "replay-reports"
        reports.mkdir(parents=True, exist_ok=True)
        path = reports / (
            "replay_" + datetime.now().strftime("%Y%m%d_%H%M%S") + ".json"
        )
        path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return path
