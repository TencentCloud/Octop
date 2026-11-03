# Post-Production — Assembly, Color, Sound

## Edit Assembly

### Timeline Organization
```
Scene 01/
├── 01_01_wide_take3.mp4       ← Selected take
├── 01_02_medium_take1.mp4
├── 01_03_closeup_take2.mp4
└── 01_alt_wide_take1.mp4      ← Backup option
```

### Assembly Order
1. **Rough cut:** All scenes in script order, selected takes
2. **Fine cut:** Trim heads/tails, adjust pacing
3. **Picture lock:** No more shot changes after this
4. **Polish:** Color, sound, VFX

### Pacing Guidelines

| Scene Type | Cut Rhythm | Shot Duration |
|------------|------------|---------------|
| Action | Fast cuts | 1-3 seconds |
| Dialogue | Match speech | 3-8 seconds |
| Tension building | Slowing down | 5-15 seconds |
| Emotional | Breathing room | 8-20 seconds |
| Establishing | Set the space | 4-10 seconds |

## Continuity Checking

Before each shot, verify against previous:
- Character position (where did they end?)
- Eyeline direction (who are they looking at?)
- Prop placement (was the cup in their hand?)
- Wardrobe (jacket on or off?)
- Lighting direction (where's the sun/source?)

### Frame Extraction for QA
```bash
# Extract frame from end of previous shot
ffmpeg -sseof -1 -i prev.mp4 -vframes 1 prev_end.jpg

# Extract frame from start of next shot
ffmpeg -i next.mp4 -vframes 1 next_start.jpg

# Compare side by side
montage prev_end.jpg next_start.jpg -geometry +2+2 compare.jpg
```

## Color Grading

### Match Shots in a Scene
1. Pick the "hero" shot (best color)
2. Extract still from hero
3. Generate LUT or describe the look
4. Apply to all shots in scene

### Common Color Workflows
```bash
# Apply LUT
ffmpeg -i input.mp4 -vf lut3d="cinematic.cube" output.mp4

# Adjust brightness/contrast
ffmpeg -i input.mp4 -vf "eq=brightness=0.1:contrast=1.2" output.mp4

# Desaturate
ffmpeg -i input.mp4 -vf "hue=s=0.7" output.mp4
```

### Style Consistency Check
Every shot in a scene should have:
- Same color temperature
- Same contrast ratio
- Same saturation level
- Matching shadows/highlights

## Sound Design

### Audio Layers
1. **Dialogue** — If AI-generated or VO
2. **Foley** — Footsteps, cloth, props
3. **Ambience** — Room tone, environment
4. **SFX** — Specific sound events
5. **Music** — Score, songs

### Sync Points
Dialogue should match lip movement (if using lip sync tools).
Sound effects should hit on visual impact.

### Audio Workflow
```bash
# Extract audio from video
ffmpeg -i video.mp4 -vn -c:a pcm_s16le audio.wav

# Replace audio track
ffmpeg -i video.mp4 -i new_audio.mp3 -c:v copy -map 0:v -map 1:a output.mp4

# Mix multiple audio tracks
ffmpeg -i video.mp4 -i music.mp3 -i sfx.wav \
  -filter_complex "[1:a][2:a]amix=inputs=2[a]" \
  -map 0:v -map "[a]" output.mp4
```

## Subtitles & Captions

### Generate from Dialogue
If you have a dialogue script, create SRT:
```
1
00:00:01,000 --> 00:00:03,500
I never thought it would end like this.

2
00:00:04,000 --> 00:00:06,000
Neither did I.
```

### Burn Subtitles
```bash
ffmpeg -i video.mp4 -vf "subtitles=captions.srt" output.mp4
```

## Export Formats

| Platform | Resolution | Codec | Notes |
|----------|------------|-------|-------|
| YouTube | 1080p/4K | H.264/H.265 | High bitrate |
| Festival | ProRes/DNxHD | Original quality | No compression |
| Social | 1080p | H.264 | Optimized file size |
| Archive | ProRes 422 | Master quality | For future edits |
