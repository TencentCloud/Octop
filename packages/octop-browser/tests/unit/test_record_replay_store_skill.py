from octop_browser.record.models import (
    RecordingManifest,
    SemanticStep,
    StepsDocument,
)
from octop_browser.record.settings import RecordReplaySettings
from octop_browser.record.skill_generator import SkillGenerator
from octop_browser.record.store import RecordingStore


def test_store_round_trip(tmp_path):
    store = RecordingStore(RecordReplaySettings(base_dir=tmp_path))
    manifest = RecordingManifest(recordingId="rec_x", createdAt="now")
    store.create(manifest)
    store.append_event("rec_x", {"seq": 1, "kind": "click"})
    assert store.read_events("rec_x") == [{"seq": 1, "kind": "click"}]


def test_skill_generator_contains_workflow():
    doc = StepsDocument(
        recordingId="rec_x",
        startUrl="https://example.com",
        inputs=[{"name": "email", "kind": "email", "required": True}],
        steps=[
            SemanticStep(id="step_001", kind="open", url="https://example.com"),
            SemanticStep(
                id="step_002", kind="fill", target={"name": "Email"}, value="{{email}}"
            ),
            SemanticStep(
                id="step_003",
                kind="click",
                target={"name": "Submit"},
                expect={"urlContains": "/done"},
            ),
        ],
        verification=[{"type": "url_contains", "value": "/done"}],
    )
    skill = SkillGenerator(doc, skill_name="submit-example").generate()
    assert "name: submit-example" in skill
    assert "Fill `Email` with `{{email}}`" in skill
    assert "URL contains `/done`" in skill


def test_replay_failure_artifacts_are_referenced_in_report(tmp_path):
    store = RecordingStore(RecordReplaySettings(base_dir=tmp_path))
    manifest = RecordingManifest(recordingId="rec_report", createdAt="now")
    store.create(manifest)
    report_dir = (
        store.recording_dir("rec_report") / "replay-reports" / "failure_x_step_001"
    )
    report_dir.mkdir(parents=True)
    reason = report_dir / "reason.txt"
    dom = report_dir / "dom_snapshot.json"
    shot = report_dir / "screenshot.png"
    reason.write_text("target missing", encoding="utf-8")
    dom.write_text('{"elements": []}', encoding="utf-8")
    shot.write_bytes(b"png")

    assert reason.exists()
    assert dom.exists()
    assert shot.exists()


def test_store_recording_summary_includes_artifact_paths(tmp_path):
    store = RecordingStore(RecordReplaySettings(base_dir=tmp_path))
    manifest = RecordingManifest(recordingId="rec_summary", createdAt="now")
    store.create(manifest)
    store.write_steps(
        "rec_summary",
        StepsDocument(
            recordingId="rec_summary",
            steps=[SemanticStep(id="step_001", kind="open", url="https://example.com")],
        ),
    )
    store.write_skill("rec_summary", "# skill", draft=True)
    report_dir = store.recording_dir("rec_summary") / "replay-reports"
    report = report_dir / "replay_20260629_000000.json"
    report.write_text('{"status":"passed"}', encoding="utf-8")

    summary = store.recording_summary("rec_summary")

    assert summary["recordingId"] == "rec_summary"
    assert summary["eventsPath"].endswith("events.jsonl")
    assert summary["stepsPath"].endswith("steps.json")
    assert summary["skillDraft"].endswith("draft.skill.md")
    assert summary["latestReplayReport"].endswith("replay_20260629_000000.json")
    assert summary["hasSteps"] is True
    assert summary["hasSkillDraft"] is True


def test_skill_generator_documents_select_and_set_checked_steps():
    doc = StepsDocument(
        recordingId="rec_controls",
        startUrl="https://example.com/form",
        inputs=[{"name": "country", "kind": "string", "required": True}],
        steps=[
            SemanticStep(id="step_001", kind="open", url="https://example.com/form"),
            SemanticStep(
                id="step_002",
                kind="select",
                target={"name": "Country"},
                value="{{country}}",
            ),
            SemanticStep(
                id="step_003",
                kind="set_checked",
                target={"name": "Subscribe"},
                value="true",
            ),
        ],
    )

    skill = SkillGenerator(doc, skill_name="controls").generate()

    assert "Select `Country` with `{{country}}`" in skill
    assert "Set `Subscribe` checked to `true`" in skill
