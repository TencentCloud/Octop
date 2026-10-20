"""Persistent recording store."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from octop_browser.record.models import RecordingManifest, StepsDocument
from octop_browser.record.settings import RecordReplaySettings
from octop_browser.record.settings import settings as default_settings


class RecordingStore:
    def __init__(self, cfg: RecordReplaySettings | None = None) -> None:
        self.cfg = cfg or default_settings
        self.base_dir = self.cfg.base_dir
        self.recordings_dir = self.base_dir / "recordings"

    def ensure_base(self) -> None:
        self.recordings_dir.mkdir(parents=True, exist_ok=True)
        try:
            self.base_dir.chmod(0o700)
            self.recordings_dir.chmod(0o700)
        except OSError:
            pass

    def recording_dir(self, recording_id: str) -> Path:
        return self.recordings_dir / recording_id

    def manifest_path(self, recording_id: str) -> Path:
        return self.recording_dir(recording_id) / "manifest.json"

    def events_path(self, recording_id: str) -> Path:
        return self.recording_dir(recording_id) / "events.jsonl"

    def steps_path(self, recording_id: str) -> Path:
        return self.recording_dir(recording_id) / "steps.json"

    def skill_path(self, recording_id: str, draft: bool = True) -> Path:
        return self.recording_dir(recording_id) / (
            "draft.skill.md" if draft else "final.skill.md"
        )

    def create(self, manifest: RecordingManifest) -> Path:
        self.ensure_base()
        rec_dir = self.recording_dir(manifest.recording_id)
        rec_dir.mkdir(parents=True, exist_ok=False)
        for sub in ("screenshots", "snapshots", "replay-reports"):
            (rec_dir / sub).mkdir(exist_ok=True)
        try:
            rec_dir.chmod(0o700)
        except OSError:
            pass
        self.write_manifest(manifest)
        events = self.events_path(manifest.recording_id)
        events.touch(exist_ok=False)
        try:
            events.chmod(0o600)
        except OSError:
            pass
        return rec_dir

    def write_manifest(self, manifest: RecordingManifest) -> None:
        path = self.manifest_path(manifest.recording_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(
            json.dumps(
                manifest.model_dump(mode="json", by_alias=True),
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        tmp.replace(path)

    def read_manifest(self, recording_id: str) -> RecordingManifest:
        data = json.loads(self.manifest_path(recording_id).read_text(encoding="utf-8"))
        return RecordingManifest.model_validate(data)

    def append_event(self, recording_id: str, event: dict[str, Any]) -> None:
        line = json.dumps(event, ensure_ascii=False, separators=(",", ":"))
        with self.events_path(recording_id).open("a", encoding="utf-8") as f:
            f.write(line + "\n")
            f.flush()

    def read_events(self, recording_id: str) -> list[dict[str, Any]]:
        path = self.events_path(recording_id)
        events: list[dict[str, Any]] = []
        if not path.exists():
            return events
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            events.append(json.loads(line))
        return events

    def write_steps(self, recording_id: str, steps: StepsDocument) -> Path:
        path = self.steps_path(recording_id)
        path.write_text(
            json.dumps(
                steps.model_dump(mode="json", by_alias=True),
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        return path

    def read_steps(self, recording_id: str) -> StepsDocument:
        return StepsDocument.model_validate_json(
            self.steps_path(recording_id).read_text(encoding="utf-8")
        )

    def write_skill(self, recording_id: str, content: str, draft: bool = True) -> Path:
        path = self.skill_path(recording_id, draft=draft)
        path.write_text(content, encoding="utf-8")
        return path

    def list_recordings(self) -> list[RecordingManifest]:
        self.ensure_base()
        manifests: list[RecordingManifest] = []
        for path in sorted(self.recordings_dir.glob("*/manifest.json")):
            try:
                manifests.append(
                    RecordingManifest.model_validate_json(
                        path.read_text(encoding="utf-8")
                    )
                )
            except Exception:  # pylint: disable=broad-except
                continue
        return manifests

    def recording_summary(self, recording_id: str) -> dict[str, Any]:
        manifest = self.read_manifest(recording_id)
        rec_dir = self.recording_dir(recording_id)
        steps = self.steps_path(recording_id)
        draft = self.skill_path(recording_id, draft=True)
        final = self.skill_path(recording_id, draft=False)
        reports = sorted((rec_dir / "replay-reports").glob("replay_*.json"))
        latest_report = reports[-1] if reports else None
        return {
            "recordingId": recording_id,
            "status": manifest.status,
            "profile": manifest.profile,
            "createdAt": manifest.created_at,
            "endedAt": manifest.ended_at,
            "startUrl": manifest.target.start_url,
            "endUrl": manifest.target.end_url,
            "events": manifest.stats.events,
            "steps": manifest.stats.steps,
            "recordingDir": str(rec_dir),
            "manifestPath": str(self.manifest_path(recording_id)),
            "eventsPath": str(self.events_path(recording_id)),
            "stepsPath": str(steps) if steps.exists() else "",
            "skillDraft": str(draft) if draft.exists() else "",
            "skillFinal": str(final) if final.exists() else "",
            "latestReplayReport": str(latest_report) if latest_report else "",
            "hasSteps": steps.exists(),
            "hasSkillDraft": draft.exists(),
        }
