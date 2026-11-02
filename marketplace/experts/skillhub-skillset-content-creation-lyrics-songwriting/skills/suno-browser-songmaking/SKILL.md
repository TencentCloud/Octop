---
name: suno-browser-songmaking
description: Browser-based song creation with Suno (suno.ai), including gathering a song brief, generating lyrics, setting Persona/Custom mode, and producing new tracks. Use when the user asks to make a new song with Suno or to automate Suno in a browser session.
---

# Suno Browser Songmaking

## Overview
Create a new song in Suno via browser automation: collect a brief, generate lyrics, set Persona/Custom mode, and produce/review tracks.

## Workflow

### 1) Get a song brief
Collect or confirm:
- Theme/story
- Genre + reference artists
- Mood/energy
- Tempo/length
- Vocal type (female/male/duet) and era (alt‑metal, synth‑pop, etc.)
- Any do‑not‑include constraints

If missing, propose 2–3 options and ask for a quick pick.

### 2) Generate lyrics
Use a sub‑agent for lyrics if requested. Provide:
- Title
- Lyrics (structured verse/chorus/bridge)
- Style tags

### 3) Open Suno in browser
Prefer Chrome relay if the user is already logged in. Otherwise use the isolated OpenClaw browser and ask for login if needed.

### 4) Create in Suno
- Switch to **Custom** mode.
- Set **Persona** to the requested persona (e.g., “Kara Codex”).
- Paste lyrics and style tags.
- Generate and wait for completion.

### 5) Review + iterate
Listen/preview, capture the best output, and iterate once if needed (tweak lyrics, style tags, or mood).

### 6) Deliver
Provide the Suno link(s) and any download/share artifacts available.

## References
- See `references/suno-workflow.md` for UI-specific steps and browser notes.
