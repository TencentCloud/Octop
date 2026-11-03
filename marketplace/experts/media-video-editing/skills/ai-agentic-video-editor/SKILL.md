---
name: ai_agentic_video_editor
description: AI agentic video editor: send a prompt, the autonomous editor plans, uses internal tools, exports, and returns the result.
version: 1.0.0
metadata:
  openclaw:
    requires:
      env:
        - ADSCENE_API_URL
        - ADSCENE_API_KEY
      bins:
        - curl
        - jq
    primaryEnv: ADSCENE_API_KEY
    envVars:
      - name: ADSCENE_API_URL
        required: true
        description: Base URL for the Levea API, for example https://api.livecore.ai. Do not use the studio URL or the /api/v1/misc/editor route.
      - name: ADSCENE_API_KEY
        required: true
        description: OpenClaw API key generated from the Studio app at https://studio.livecore.ai/.
    skillKey: openclaw_ai_video_editor
    homepage: https://github.com/brajendrak00068/openclaw-ai-video-editor#readme
---

# Levea Agentic Video Editor for OpenClaw

A full agentic video editing surface. Send a prompt and get a planned, verified, executed edit. The autonomous editor chooses its own internal tools, applies safety gates, exports when needed, and returns the final scene/video result.

Use this skill when the user asks for OpenClaw video editing, AI video editing, natural-language video edits, viral clips, TikTok videos, Instagram Reels, YouTube Shorts, auto captions, subtitles, chroma key, green screen removal, background removal, B-roll, motion tracking, motion graphics, multi-cam editing, smart jump cuts, silence cleanup, audio cleanup, voiceover, music generation, object blur / hide, face blur, privacy redaction, beat sync, brand kits, thumbnails, style presets, vertical video, safe-zone repair, final delivery checks, export presets, multi-platform export, or MP4 export.

> **Beta**: This skill is in beta and outputs can be wrong. Before executing any mutating edit on user content, describe the planned edit and request explicit confirmation from the user. For destructive or irreversible workflows, pass `requirePlanApproval: true` so the editor halts after planning and the user can approve before execution.

## Endpoint

`POST {ADSCENE_API_URL}/api/v1/misc/openclaw/v1/execute`

Auth: `Authorization: Bearer {ADSCENE_API_KEY}`

Create an account and generate the OpenClaw API key in Studio: `https://studio.livecore.ai/`.
Use `https://api.livecore.ai` for `ADSCENE_API_URL`; Studio is only for signup, login, and key management.

Accepts either single-shot JSON (default) or SSE (`Accept: text/event-stream` or `?stream=true`).

Request body:

```json
{
  "tool": "autonomous_edit",
  "params": { ... },
  "project_id": "optional-project-id",
  "scene": { /* optional client scene; server-side committed scene wins if newer */ }
}
```

## How you use it

Every edit goes through one tool: **`autonomous_edit`**. Pass a natural-language description in `params.prompt`. The agent classifies the intent, decomposes into atomic steps, plans, executes through safety gates, and verifies the result. There are no other tools the caller needs to learn.

```bash
curl -sS -X POST "$ADSCENE_API_URL/api/v1/misc/openclaw/v1/execute" \
  -H "Authorization: Bearer $ADSCENE_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "tool": "autonomous_edit",
    "params": {
      "prompt": "Make this a TikTok-ready viral clip: vertical reframe, add bold captions, remove silences, and apply motion tracking to the speaker."
    },
    "project_id": "my-project"
  }'
```

Behind a single `autonomous_edit` call the agent can compose any of:

**Read / inspect**
- Inspect the timeline structure, layer properties, and current scene state
- Run computer-vision analysis on frames (object/face/scene detection)
- Query the transcript with keyword, semantic, or timestamp-window search
- Pull video intelligence (narrative peaks, speaker diarization, sentiment, pacing)
- Search the asset gallery (videos, images, audio) by type, duration, name
- Poll async job status; introspect property schemas

**Structural editing**
- Insert / update / replace / delete layers (video, audio, image, text, shape, solid, adjustment, group, light, vfx, visualizer, lottie)
- Trim, split, retime layers (slow-mo 0.5×, fast-forward 2×, freeze-frame)
- Smart jump cuts, filler-word cuts, silence cleanup, low-energy segment removal
- Reposition on the timeline, sequence layers, snap to transcript
- Multi-cam sync and angle switching by pacing, speaker priority, or shot size
- Heal timeline gaps, normalize audio, reconcile durations (pre-export safety pass)
- Multi-step undo / redo

**Visual editing**
- Color grading (brightness, contrast, saturation, hue, lift/gamma/gain, RGB curves)
- Procedural VFX shaders: smoke, dust, fire, explosion, lightning, snow, glitch, scanlines, grain, glassmorphism, bokeh, lava, telomere/corrosion, portal
- Chroma key (green / blue screen) with similarity, smoothness, spill controls; luma / alpha / depth masks
- Geometric clip shapes (circle, dome, star, hexagon, …)
- Crop (absolute or edge-based), 3D rotation + perspective
- Glow, shadow, inner shadow, gradient fills, text gradients
- Vertical reframe (9:16) and vertical-reframe montage
- Split screen (top/bottom, left/right, picture-in-picture)
- Branding overlays and brand kits (logo / watermark / colors / fonts / voice) from gallery, project brand settings, or AI-generated
- Motion / face tracking with dynamic zoom-follow
- Object hide / object blur, selective face blur, privacy redaction, safe-zone repair

**Captions & text**
- Auto-generate captions from transcript
- Style captions with built-in templates or an AI director that picks/generates a custom template at runtime
- Motion graphics: kinetic captions, lower thirds, stat callouts, charts, comparison overlays, concept-icon Lottie layers
- Curved text paths (circle, wave, custom SVG)
- Per-word entrance / exit animations (typewriter, slide, fade, scale, rotate, bounce, flip, swing, elastic, blur, glitch, wave, plus matching exits)
- Lottie animation playback control

**Audio**
- Clean audio: remove silences, breaths, filler words; word-level mute or cut
- Profanity cleanup: mute, bleep, or cut flagged words
- Auto-ducking on speech detection (sidechain music vs voice)
- Mix / normalize / denoise / EQ (bass boost, vocal clarity, warm, bright)
- Sync external master audio to video (offset, mute camera audio)
- Beat / kick-drum-synced cuts (provide `beat_times` or `bpm`)
- Add SFX, generate music (mood / genre / BPM), generate voiceover (TTS or cloned voice)
- Render waveform visualizers (bars, wave, circular)

**Async generation**
- AI video / B-roll — duration + aspect ratio
- AI images — single or batch at timestamps
- AI music — prompt + duration + mood + genre + BPM
- AI voiceover — TTS or cloned voice library
- Auto-thumbnail extraction or AI-generated thumbnail variants
- Face blur (all faces or background-only)
- Image edit (generative instruction-based)

**High-level kits** (each is a single canonical action that orchestrates many underlying edits)
- `APPLY_VIRAL_KIT` — vertical reframe + captions + silence removal + motion tracking + emphasis
- `APPLY_CINEMATIC_DIRECTOR` — energy analysis + dynamic zooms + cinematic color grade + mood-based camera moves
- `APPLY_EMPHASIS_SYSTEM` — keyword detection + scaling / glow / pulse coordinated with captions
- `OPTIMIZE_PACING` — filler-word + silence + low-energy segment removal for retention

**Export**
- `EXPORT_VIDEO` — render to MP4 (resolution / codec / quality tier)
- `EXPORT_PRESET` — platform / codec / aspect-ratio presets with safe-zone repair
- `FINAL_DELIVERY_CHECK` — verify safe zones, timeline integrity, captions, media, and export readiness
- `GENERATE_VIRAL_CLIPS` — auto-segment short-form clips packaged as ZIP
- `GENERATE_MULTI_PLATFORM` — TikTok + Reels + Shorts + YouTube + Instagram aspect ratios in one pass

## Auto-export follow-up

After any **mutating** `autonomous_edit` call, if the scene was actually changed and the agent did not already queue an export, the route fires one automatically as a second run. The final response carries `videoUrl` (when ready) or `jobId` (for polling). Read-only and conversational `autonomous_edit` calls do NOT trigger auto-export.

## Optional input parameters (parity with the in-product editor)

Pass any of these inside `params` (or at the top level of the body) to drive advanced features:

- `prompt` — required on every call (the natural-language edit description)
- `workingMemory` — durable working-memory snapshot. Re-send to resume after `awaiting_approval`
- `requirePlanApproval` — `true` makes the agent stop after planning and emit `awaiting_approval`; resume with the same workingMemory + an approval prompt (`"yes"`, `"approve"`, `"do it"`, …)
- `attachedImages` — array of base64 screenshots / reference images
- `flaggedIssues` — array of strings describing specific problems the user wants fixed
- `captionTemplatePreset`, `captionTemplateMode` — style preset routing for caption generation
- `brandId`, `projectBrandId` — optional brand-kit selection for colors, fonts, logo, grade bias, and voice
- `core_only` (also accepted via `?core_only=true`) — return a minimal scene shape (rendering-only, no debug fields)
- `assets` — additional asset descriptors to make available to the agent

## Response shapes

### JSON (default)

```json
{
  "type": "success" | "partial_success",
  "tool": "<tool-name>",
  "success": true,
  "status": "completed" | "failed" | "awaiting_approval",
  "scene": { /* updated scene */ },
  "reply": "Human-readable summary of what changed",
  "videoUrl": "https://.../output.mp4",
  "jobId": "1234567",
  "viral_clips": [ /* clip metadata if generated */ ],
  "zip_url": "https://.../clips.zip",
  "activeTasks": [ /* queued background jobs */ ],
  "pendingAsyncJobs": [ /* in-flight job status */ ],
  "workflowStepsDetailed": [ /* every executed step */ ],
  "workflowSummary": { "title": "...", "summary": "..." },
  "verificationPassed": true,
  "verificationIssues": [],
  "committedToProjectScene": true,
  "processingTime": 12.3,
  "message": "Same as reply",
  "workingMemory": { /* return this in the next call to resume approval-paused runs */ }
}
```

Failure response (HTTP 4xx/5xx):

```json
{ "success": false, "error": "...", "code": "MISSING_PROMPT" | "EXECUTION_ERROR" }
```

### SSE (`Accept: text/event-stream` or `?stream=true`)

The same event stream the in-product editor uses. Notable event types:
- `heartbeat` — every 15s, keeps the connection alive
- `status` — phase transitions (`request_received`, `runtime_start`, …)
- `mode_select` — `{ mode: "qa" | "action" }`
- `thinking`, `tool_call`, `tool_result` — per-step reasoning visibility
- `background_job_completed` — async job finished (B-roll, viral clips, …)
- `workflow_completed` — main brain loop done, verification may continue
- `success` / `partial_success` — final terminal payload (same shape as JSON above)
- `error` — terminal failure

## Async job lifecycle

Generation actions (`generate_*`, `EXPORT_VIDEO`) return immediately with a `jobId` in `activeTasks` / `pendingAsyncJobs`. Poll status with:

```
GET {ADSCENE_API_URL}/api/v1/misc/openclaw/v1/jobs/{jobId}
Authorization: Bearer {ADSCENE_API_KEY}
```

Response:
```json
{
  "success": true,
  "jobId": "1234567",
  "status": "queued" | "processing" | "completed" | "failed",
  "progress": 0.74,
  "message": "Rendering frame 142 of 192",
  "result": { /* artifact URLs / clip metadata on completion */ },
  "error": null,
  "createdAt": "...",
  "updatedAt": "..."
}
```

To pull async-generated content into the timeline once jobs settle, the agent uses `APPLY_PENDING` internally — `autonomous_edit` callers don't need to manage this, but direct callers can issue an `autonomous_edit` prompt like `"apply any pending generated content"` to harvest.

## Plan approval flow

If you pass `requirePlanApproval: true`, the agent stops after planning and the response carries `status: "awaiting_approval"` + a populated `workingMemory`. To proceed, call again with:

```json
{
  "tool": "autonomous_edit",
  "params": {
    "prompt": "yes",
    "workingMemory": { /* the workingMemory from the previous response */ }
  }
}
```

Accepted approval phrases: `yes`, `y`, `approve`, `approved`, `go`, `proceed`, `go ahead`, `do it`, `confirm`.

## Safety, verification, and limits

Every run flows through three deterministic gates (`ActionPermissionGate`, `ArchitectureControlPlane`, `EditorSafetyPolicy`). Destructive actions (`CLEAR`, mass deletes) require explicit confirmation params. Verification runs after execution and may trigger up to 2 repair loops; failures surface in `verificationPassed: false` + `verificationIssues[]`. Concurrent identical requests for the same `(user, project, prompt, scene fingerprint)` are deduplicated server-side.

Rate-limited per API key. Processing times vary: read-only ~1–3s, structural edits ~3–10s, async generation 30s–5min per artifact, viral-clip / multi-platform exports several minutes.

## Supported formats

- **Video in**: MP4, MOV, WebM (HTTP/HTTPS URLs, YouTube URLs, gallery IDs)
- **Image in**: JPG, PNG, WebP
- **Audio in**: MP3, WAV, M4A, AAC (or extracted from video)
- **Output**: MP4 (export), ZIP (viral clips / multi-platform bundles)
- **Max video length**: up to ~3 hours per asset (plan-dependent); sync edits and async generation both supported
- **Recommended resolution**: 1080p or 4K; canvas is configurable per project

## Example: end-to-end viral-clip generation

```bash
# 1) Kick off the viral-clip pipeline (auto-export follow-up queues rendering)
curl -sS -X POST "$ADSCENE_API_URL/api/v1/misc/openclaw/v1/execute" \
  -H "Authorization: Bearer $ADSCENE_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "tool": "autonomous_edit",
    "params": {
      "prompt": "Generate 5 viral clips, 15-30 seconds each, focused on the most engaging moments. Add bold captions, vertical reframe, remove silences."
    },
    "project_id": "my-project"
  }' | tee /tmp/result.json | jq -r '.jobId // .activeTasks[0].intent.job_id'

# 2) Poll job status until done
JOB_ID=$(jq -r '.jobId // .activeTasks[0].intent.job_id' /tmp/result.json)
while true; do
  STATUS=$(curl -sS "$ADSCENE_API_URL/api/v1/misc/openclaw/v1/jobs/$JOB_ID" \
    -H "Authorization: Bearer $ADSCENE_API_KEY" | jq -r '.status')
  echo "Status: $STATUS"
  [ "$STATUS" = "completed" ] || [ "$STATUS" = "failed" ] && break
  sleep 5
done

# 3) Fetch the final artifact URL(s)
curl -sS "$ADSCENE_API_URL/api/v1/misc/openclaw/v1/jobs/$JOB_ID" \
  -H "Authorization: Bearer $ADSCENE_API_KEY" | jq '.result'
```
