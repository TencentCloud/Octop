"""CDP-based browser recorder.

This MVP records a single active page in-process. It is designed so a future
long-lived daemon can own ``RecordSession`` across CLI calls; the storage and
payload formats are daemon-safe already.
"""

from __future__ import annotations

import asyncio
import json
import secrets
from contextlib import suppress
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import aiohttp

from octop_browser.cdp.client import CDPClient
from octop_browser.cdp.launcher import get_page_ws_url, launch_or_attach
from octop_browser.mode import resolve_headless
from octop_browser.profile import Profile, ProfileManager
from octop_browser.record.models import (
    PrivacySettings,
    RecordingManifest,
    RecordingTarget,
)
from octop_browser.record.privacy import redact_event
from octop_browser.record.semantic import SemanticProcessor
from octop_browser.record.settings import RecordReplaySettings
from octop_browser.record.settings import settings as default_settings
from octop_browser.record.skill_generator import SkillGenerator
from octop_browser.record.store import RecordingStore
from octop_browser.settings import OctopSettings
from octop_browser.settings import settings as browser_settings


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _recording_id() -> str:
    return "rec_" + datetime.now().strftime("%Y%m%d_%H%M%S_") + secrets.token_hex(3)


def _target_id_from_ws_url(ws_url: str) -> str:
    marker = "/devtools/page/"
    if marker not in ws_url:
        return ""
    return ws_url.rsplit(marker, 1)[-1].split("?", 1)[0].strip()


class RecordSession:
    def __init__(
        self,
        client: CDPClient,
        store: RecordingStore,
        manifest: RecordingManifest,
        rr_settings: RecordReplaySettings | None = None,
        cdp_host: str | None = None,
        cdp_port: int | None = None,
        initial_target_id: str | None = None,
    ) -> None:
        self.client = client
        self.store = store
        self.manifest = manifest
        self.rr_settings = rr_settings or default_settings
        self.cdp_host = cdp_host
        self.cdp_port = cdp_port
        self.initial_target_id = initial_target_id or ""
        self.binding_name = f"__hbr_emit_{secrets.token_hex(8)}"
        self.nonce = secrets.token_urlsafe(32)
        self.seq = 0
        self.active = False
        self._last_tick = 0
        self._tick_events = 0
        self._clients: dict[str, CDPClient] = {}
        self._client_target_ids: dict[int, str] = {}
        self._baseline_target_ids: set[str] = set()
        self._poll_task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        self.active = True
        existing_targets = (
            await self._target_infos() if self.cdp_host and self.cdp_port else []
        )
        target_id = self.initial_target_id or "initial"
        self._baseline_target_ids = {
            str(t.get("id") or "")
            for t in existing_targets
            if str(t.get("id") or "") != target_id
        }
        await self._install_on_client(self.client, target_id)
        self._clients[target_id] = self.client
        self._client_target_ids[id(self.client)] = target_id
        await self._attach_known_targets()
        if self.cdp_host and self.cdp_port:
            self._poll_task = asyncio.create_task(self._poll_targets())

    async def stop(
        self, *, generate_steps: bool = True, skill_name: str | None = None
    ) -> dict[str, Any]:
        self.active = False
        if self._poll_task is not None:
            self._poll_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._poll_task
            self._poll_task = None
        self.manifest.status = "stopped"
        self.manifest.ended_at = _now()
        self.store.write_manifest(self.manifest)
        result: dict[str, Any] = {
            "recordingId": self.manifest.recording_id,
            "events": self.manifest.stats.events,
        }
        if generate_steps:
            events = self.store.read_events(self.manifest.recording_id)
            steps = SemanticProcessor(self.manifest.recording_id, events).process()
            self.manifest.stats.steps = len(steps.steps)
            self.store.write_manifest(self.manifest)
            steps_path = self.store.write_steps(self.manifest.recording_id, steps)
            skill = SkillGenerator(steps, skill_name=skill_name).generate()
            skill_path = self.store.write_skill(
                self.manifest.recording_id, skill, draft=True
            )
            result.update(
                {
                    "steps": len(steps.steps),
                    "stepsPath": str(steps_path),
                    "skillDraft": str(skill_path),
                }
            )
        return result

    async def close(self) -> None:
        if self._poll_task is not None:
            self._poll_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._poll_task
            self._poll_task = None
        seen: set[int] = set()
        for client in list(self._clients.values()) + [self.client]:
            ident = id(client)
            if ident in seen:
                continue
            seen.add(ident)
            with suppress(Exception):
                await client.close()
        self._clients.clear()

    def _recorder_source(self, target_id: str | None = None) -> str:
        js_path = Path(__file__).parent / "injected" / "recorder.js"
        body = js_path.read_text(encoding="utf-8")
        config = {
            "recordingId": self.manifest.recording_id,
            "bindingName": self.binding_name,
            "nonce": self.nonce,
            "targetId": target_id or "",
        }
        return (
            "globalThis.__HBR_RECORDER_CONFIG__ = " + json.dumps(config) + ";\n" + body
        )

    async def _install_on_client(self, client: CDPClient, target_id: str) -> None:
        await client.enable_domain("Runtime")
        await client.enable_domain("Page")
        await client.enable_domain("DOM")
        with suppress(Exception):
            await client.send("Runtime.addBinding", {"name": self.binding_name})
        source = self._recorder_source(target_id)
        await client.send("Page.addScriptToEvaluateOnNewDocument", {"source": source})
        await client.send(
            "Runtime.evaluate", {"expression": source, "returnByValue": True}
        )
        client.on("Runtime.bindingCalled", self._on_binding_called)
        client.on(
            "Page.frameNavigated",
            lambda params, tid=target_id: self._on_frame_navigated(params, tid),
        )

    async def _target_infos(self) -> list[dict[str, Any]]:
        if not self.cdp_host or not self.cdp_port:
            return []
        url = f"http://{self.cdp_host}:{self.cdp_port}/json"
        async with aiohttp.ClientSession() as http:
            async with http.get(url, timeout=aiohttp.ClientTimeout(total=3)) as resp:
                targets = await resp.json(content_type=None)
        if not isinstance(targets, list):
            return []
        return [t for t in targets if isinstance(t, dict) and t.get("type") == "page"]

    async def _attach_known_targets(self) -> None:
        for target in await self._target_infos():
            target_id = str(target.get("id") or "")
            ws_url = str(target.get("webSocketDebuggerUrl") or "")
            if not target_id or not ws_url or target_id in self._clients:
                continue
            client = CDPClient(timeout=browser_settings.cdp_timeout)
            try:
                await client.connect(ws_url)
                await self._install_on_client(client, target_id)
            except Exception:  # pylint: disable=broad-except
                with suppress(Exception):
                    await client.close()
                continue
            self._clients[target_id] = client
            self._client_target_ids[id(client)] = target_id
            if target_id not in self._baseline_target_ids:
                self._append(
                    {
                        "kind": "page_opened",
                        "targetId": target_id,
                        "url": str(target.get("url") or ""),
                        "title": str(target.get("title") or ""),
                        "initial": target_id == self.initial_target_id,
                    }
                )

    async def _poll_targets(self) -> None:
        while self.active:
            await self._attach_known_targets()
            alive = {str(t.get("id") or "") for t in await self._target_infos()}
            for target_id, client in list(self._clients.items()):
                if target_id != "initial" and target_id not in alive:
                    self._clients.pop(target_id, None)
                    self._client_target_ids.pop(id(client), None)
                    with suppress(Exception):
                        await client.close()
            await asyncio.sleep(0.5)

    def _rate_limit_ok(self) -> bool:
        now = int(asyncio.get_event_loop().time())
        if now != self._last_tick:
            self._last_tick = now
            self._tick_events = 0
        self._tick_events += 1
        return self._tick_events <= self.rr_settings.max_events_per_second

    def _append(self, event: dict[str, Any]) -> None:
        self.seq += 1
        record = {
            "seq": self.seq,
            "recordingId": self.manifest.recording_id,
            "receivedAt": _now(),
            **event,
        }
        record = redact_event(record, self.manifest.privacy)
        self.store.append_event(self.manifest.recording_id, record)
        self.manifest.stats.events += 1
        page = record.get("page")
        if isinstance(page, dict) and isinstance(page.get("url"), str):
            self.manifest.target.end_url = page["url"]
        self.store.write_manifest(self.manifest)

    def _on_binding_called(self, params: dict[str, Any]) -> None:
        if not self.active or params.get("name") != self.binding_name:
            return
        client_target_id = ""
        client = params.get("__client")
        if client is not None:
            client_target_id = self._client_target_ids.get(id(client), "")
        raw = str(params.get("payload", ""))
        if (
            len(raw.encode("utf-8")) > self.rr_settings.max_event_bytes
            or not self._rate_limit_ok()
        ):
            return
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return
        if payload.get("nonce") != self.nonce:
            return
        event = payload.get("event")
        if not isinstance(event, dict):
            return
        if client_target_id and not event.get("targetId"):
            event["targetId"] = client_target_id
            page = event.get("page")
            if isinstance(page, dict) and not page.get("targetId"):
                page["targetId"] = client_target_id
        kind = event.get("kind")
        if not isinstance(kind, str):
            return
        self._append(event)

    def _on_frame_navigated(
        self, params: dict[str, Any], target_id: str | None = None
    ) -> None:
        frame = params.get("frame", {})
        url = frame.get("url")
        if self.active and isinstance(url, str) and url:
            self._append(
                {
                    "kind": "navigation",
                    "targetId": target_id or "",
                    "ts": _now(),
                    "urlAfter": url,
                }
            )


class RecordController:
    def __init__(
        self,
        store: RecordingStore | None = None,
        settings: OctopSettings | None = None,
        profile_manager: ProfileManager | None = None,
    ) -> None:
        """Create a controller.

        Args:
            store: Recording store. Defaults to a store on the standard path.
            settings: Browser settings used to locate/launch Chrome. Defaults
                to the process-wide singleton.
            profile_manager: Profile manager to resolve the CDP port from.
                Defaults to one derived from ``settings``.

        Passing ``settings``/``profile_manager`` is what lets a caller record
        inside a browser it launched itself: without them the controller would
        resolve a port from the ambient environment and attach to — or start —
        a *different* Chrome than the one under test.
        """
        self.store = store or RecordingStore()
        self._settings = settings or browser_settings
        self._profile_manager = profile_manager or ProfileManager(
            settings=self._settings
        )

    async def _attach(self, profile: str) -> tuple[Profile, str]:
        """Resolve the profile and a page-level websocket URL to record."""
        p = self._profile_manager.get_or_create(profile)
        if self._settings.cdp_ws_url:
            return p, self._settings.cdp_ws_url
        await launch_or_attach(
            p, headless=resolve_headless(self._settings.browser_mode)
        )
        return p, await get_page_ws_url(p.cdp_port, profile=p)

    async def doctor(self, profile: str = "default") -> dict[str, Any]:
        p, ws_url = await self._attach(profile)
        return {
            "ok": True,
            "profile": profile,
            "cdpPort": p.cdp_port,
            "pageWsUrl": ws_url,
        }

    async def start_in_process(
        self,
        profile: str = "default",
        privacy: PrivacySettings | None = None,
        name: str | None = None,
    ) -> tuple[RecordSession, dict[str, Any]]:
        p, ws_url = await self._attach(profile)
        client = CDPClient(timeout=self._settings.cdp_timeout)
        await client.connect(ws_url)
        info = await client.send(
            "Runtime.evaluate",
            {
                "expression": "JSON.stringify({url: location.href, title: document.title})",
                "returnByValue": True,
            },
        )
        page_info = json.loads(info.get("result", {}).get("value", "{}"))
        rec_id = _recording_id()
        manifest = RecordingManifest(
            recordingId=rec_id,
            createdAt=_now(),
            profile=profile,
            target=RecordingTarget(
                start_url=str(page_info.get("url", "")),
                title=str(page_info.get("title", "")),
            ),
            privacy=privacy or PrivacySettings(),
        )
        rec_dir = self.store.create(manifest)
        initial_target_id = _target_id_from_ws_url(ws_url)
        session = RecordSession(
            client,
            self.store,
            manifest,
            cdp_host=self._settings.cdp_host if not self._settings.cdp_ws_url else None,
            cdp_port=p.cdp_port if not self._settings.cdp_ws_url else None,
            initial_target_id=initial_target_id,
        )
        await session.start()
        return session, {
            "ok": True,
            "recordingId": rec_id,
            "store": str(rec_dir),
            "startUrl": manifest.target.start_url,
            "name": name or "",
        }

    def generate_steps(self, recording_id: str) -> dict[str, Any]:
        events = self.store.read_events(recording_id)
        steps = SemanticProcessor(recording_id, events).process()
        path = self.store.write_steps(recording_id, steps)
        manifest = self.store.read_manifest(recording_id)
        manifest.stats.steps = len(steps.steps)
        self.store.write_manifest(manifest)
        return {
            "ok": True,
            "recordingId": recording_id,
            "steps": len(steps.steps),
            "stepsPath": str(path),
        }

    def generate_skill(
        self, recording_id: str, skill_name: str | None = None
    ) -> dict[str, Any]:
        steps = self.store.read_steps(recording_id)
        content = SkillGenerator(steps, skill_name=skill_name).generate()
        path = self.store.write_skill(recording_id, content, draft=True)
        return {"ok": True, "recordingId": recording_id, "skillDraft": str(path)}
