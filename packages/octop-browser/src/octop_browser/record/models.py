"""Models for browser record/replay artifacts."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

RecordingStatus = Literal["recording", "stopped", "failed"]
InputPolicy = Literal["none", "mask-sensitive", "mask-all"]
ScreenshotPolicy = Literal["off", "on-error", "on-step-or-error", "every-event"]


class PrivacySettings(BaseModel):
    input_policy: InputPolicy = "mask-sensitive"
    url_query_policy: InputPolicy = "mask-sensitive"
    screenshot_policy: ScreenshotPolicy = "off"


class RecordingTarget(BaseModel):
    target_id: str | None = None
    start_url: str = ""
    end_url: str | None = None
    title: str = ""


class RecordingStats(BaseModel):
    events: int = 0
    steps: int = 0


class RecordingManifest(BaseModel):
    schema_version: str = Field(default="1.0", alias="schemaVersion")
    recording_id: str = Field(alias="recordingId")
    status: RecordingStatus = "recording"
    created_at: str = Field(alias="createdAt")
    ended_at: str | None = Field(default=None, alias="endedAt")
    profile: str = "default"
    target: RecordingTarget = Field(default_factory=RecordingTarget)
    privacy: PrivacySettings = Field(default_factory=PrivacySettings)
    stats: RecordingStats = Field(default_factory=RecordingStats)

    model_config = {"populate_by_name": True}


class TargetDescriptor(BaseModel):
    tag: str = ""
    role: str = ""
    name: str = ""
    accessible_name: str = Field(default="", alias="accessibleName")
    text: str = ""
    label: str = ""
    placeholder: str = ""
    id: str = ""
    name_attr: str = Field(default="", alias="nameAttr")
    type: str = ""
    test_id: str = Field(default="", alias="testId")
    selector_candidates: list[str] = Field(
        default_factory=list, alias="selectorCandidates"
    )
    xpath: str = ""
    bbox: dict[str, int] | None = None
    visible: bool = True
    enabled: bool = True

    model_config = {"populate_by_name": True, "extra": "allow"}


class SemanticStep(BaseModel):
    id: str
    kind: str
    description: str = ""
    url: str | None = None
    target: dict[str, Any] | None = None
    value: str | None = None
    key: str | None = None
    expect: dict[str, Any] | None = None


class StepsDocument(BaseModel):
    schema_version: str = Field(default="1.0", alias="schemaVersion")
    recording_id: str = Field(alias="recordingId")
    start_url: str = Field(default="", alias="startUrl")
    inputs: list[dict[str, Any]] = Field(default_factory=list)
    steps: list[SemanticStep] = Field(default_factory=list)
    verification: list[dict[str, Any]] = Field(default_factory=list)

    model_config = {"populate_by_name": True}
