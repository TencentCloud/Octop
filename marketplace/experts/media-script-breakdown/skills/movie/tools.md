# Tools — Video Generation APIs & CLIs

## Video Generation Models

| Model | Best For | Duration | Resolution | Notes |
|-------|----------|----------|------------|-------|
| **Seedance 2.0** | Motion, dance, action | 10s | 2K | Fast, 90% usable output |
| **Sora 2** | Cinematic, narrative | 60s | 1080p | Best physics understanding |
| **Kling 3.0** | Long clips, lip sync | 10s | 1080p | Good character consistency |
| **Veo 3.1** | Broadcast quality, 24fps | 8s | 4K | Cinematic aesthetics |
| **Runway Gen-4.5** | Style transfer, control | 10s | 1080p | Best motion brush |
| **Hailuo** | Value/cost efficiency | 6s | 1080p | Budget option |
| **Wan 2.6 / LTX-2** | Open source, local | 4s | 720p | Self-hosted option |

## Tool Selection Rules

**Action/motion sequences** → Seedance 2.0
**Dialogue scenes** → Kling 3.0 (lip sync)
**Establishing shots** → Sora 2 or Veo 3.1
**Style-heavy artistic** → Runway Gen-4.5
**Quick iterations** → Hailuo (budget)
**Privacy/offline** → Wan 2.6 locally

## FFmpeg Essentials

```bash
# Concatenate clips (create list.txt first)
ffmpeg -f concat -safe 0 -i list.txt -c copy output.mp4

# Extract frame for reference
ffmpeg -i clip.mp4 -ss 00:00:02 -vframes 1 ref.jpg

# Match duration exactly
ffmpeg -i input.mp4 -t 00:00:05 -c copy output.mp4

# Aspect ratio for social
ffmpeg -i input.mp4 -vf "crop=ih*9/16:ih,scale=1080:1920" vertical.mp4

# Color grade with LUT
ffmpeg -i input.mp4 -vf lut3d="style.cube" graded.mp4

# Add audio track
ffmpeg -i video.mp4 -i audio.mp3 -c:v copy -map 0:v -map 1:a final.mp4
```

## Image Generation (Storyboards)

**Midjourney** — Best for cinematic frames, character design
**DALL-E 3** — Good for concept art, quick iteration
**Flux** — Open source, consistent style

## Audio

**Suno / Udio** — AI music generation
**ElevenLabs** — Voice/dialogue generation
**Whisper** — Transcription for subtitle generation

## Frame Analysis

For continuity checking, extract frames:
```bash
ffmpeg -i scene.mp4 -vf "fps=1" frames/frame_%04d.jpg
```

Then analyze each frame for:
- Character appearance consistency
- Lighting direction
- Color palette adherence
- Prop/costume continuity
