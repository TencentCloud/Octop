---
name: Movie
description: Create films with AI video generation by managing scripts, prompts, consistency, and production workflows from concept to final cut.
---

## Core Workflow

Every film follows: Script → Breakdown → Generation → Assembly → Polish.

Before generating ANY video, establish:
1. **Style bible** — Visual language, color palette, lighting, grain
2. **Character sheets** — Reference images from multiple angles
3. **Shot list** — Scene-by-scene with framing, duration, transitions

## Project Structure

```
~/movies/<project>/
├── script.md           # Source screenplay or treatment
├── style-bible.md      # Visual rules, references, palette
├── characters/         # Reference images per character
├── shots/              # Generated clips organized by scene
├── timeline.md         # Edit assembly order
└── status.md           # What's done, what needs work
```

## Generation Checklist

Before each shot generation:
- [ ] Character reference images attached
- [ ] Style keywords locked (from style-bible)
- [ ] Previous shot reviewed for continuity
- [ ] Tool selected based on shot type (see `tools.md`)

After generation:
- [ ] Check character consistency vs reference
- [ ] Check lighting/color matches scene
- [ ] Log prompt + result in shots folder
- [ ] Flag continuity issues for re-generation

## Quick Reference

| Need | Load |
|------|------|
| Breaking down scripts into shots | `preproduction.md` |
| Writing effective prompts by tool | `generation.md` |
| Editing, color matching, sound | `postproduction.md` |
| Which API/tool for which shot | `tools.md` |
| Commercial: versions, formats, localization | `commercial.md` |
| Experimental: audio-sync, style morphing | `experimental.md` |

## Critical Rules

1. **Consistency over speed** — Better to re-generate than break character continuity
2. **Log everything** — Every prompt, every iteration, what worked/failed
3. **Tool routing matters** — Seedance for motion, Kling for duration, Runway for style
4. **Start rough** — Animatics first, polish approved shots only
5. **Project scope** — 2-hour film = hundreds of shots. Plan iterations.
