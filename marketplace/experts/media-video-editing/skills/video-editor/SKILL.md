---
name: video-editor
description: Video editing operations using ffmpeg. Use when user needs to: (1) Cut/trim video clips, (2) Merge/join multiple videos, (3) Convert video formats, (4) Extract audio from video, (5) Add subtitles or text overlays, (6) Adjust video speed, (7) Resize/crop video dimensions, (8) Apply filters or effects. Supports common formats like MP4, MOV, AVI, MKV, WebM.
homepage: https://ffmpeg.org
metadata:
  {
    "openclaw":
      {
        "emoji": "🎬",
        "requires": { "bins": ["ffmpeg", "ffprobe"] },
        "install":
          [
            {
              "id": "brew",
              "kind": "brew",
              "formula": "ffmpeg",
              "bins": ["ffmpeg", "ffprobe"],
              "label": "Install ffmpeg (brew)",
            },
          ],
      },
  }
---

# Video Editor (ffmpeg)

Video editing operations for cutting, merging, converting, and processing video files.

## Prerequisites

Requires `ffmpeg` and `ffprobe` installed:

```bash
brew install ffmpeg
```

## Quick Start

### Cut/Trim Video

Extract a segment from a video:

```bash
{baseDir}/scripts/cut.sh /path/to/input.mp4 --start 00:00:10 --end 00:00:30 --out /path/to/output.mp4
```

Or use duration instead of end time:

```bash
{baseDir}/scripts/cut.sh /path/to/input.mp4 --start 00:01:00 --duration 30 --out /path/to/output.mp4
```

### Merge Videos

Concatenate multiple videos (must have same codec/resolution):

```bash
{baseDir}/scripts/merge.sh video1.mp4 video2.mp4 video3.mp4 --out merged.mp4
```

### Convert Format

Convert between video formats:

```bash
{baseDir}/scripts/convert.sh input.mov --format mp4 --out output.mp4
```

### Extract Audio

Extract audio track from video:

```bash
{baseDir}/scripts/extract-audio.sh input.mp4 --out audio.mp3
```

### Add Subtitles

Burn subtitles into video:

```bash
{baseDir}/scripts/add-subtitles.sh input.mp4 subtitles.srt --out output.mp4
```

### Resize Video

Change video resolution:

```bash
{baseDir}/scripts/resize.sh input.mp4 --width 1920 --height 1080 --out output.mp4
```

Or scale proportionally:

```bash
{baseDir}/scripts/resize.sh input.mp4 --scale 720 --out output.mp4
```

### Adjust Speed

Speed up or slow down video:

```bash
{baseDir}/scripts/speed.sh input.mp4 --rate 2.0 --out output.mp4   # 2x faster
{baseDir}/scripts/speed.sh input.mp4 --rate 0.5 --out output.mp4   # 0.5x slower
```

### Crop Video

Crop to specific region:

```bash
{baseDir}/scripts/crop.sh input.mp4 --x 100 --y 100 --width 800 --height 600 --out output.mp4
```

## Common Workflows

### Social Media Clip

Cut a segment and resize for Instagram/TikTok:

```bash
# First cut the segment
{baseDir}/scripts/cut.sh input.mp4 --start 00:00:15 --duration 15 --out clip.mp4

# Then resize to vertical format
{baseDir}/scripts/resize.sh clip.mp4 --width 1080 --height 1920 --out tiktok.mp4
```

### Extract Highlights

Cut multiple segments and merge:

```bash
{baseDir}/scripts/cut.sh input.mp4 --start 00:00:10 --duration 5 --out highlight1.mp4
{baseDir}/scripts/cut.sh input.mp4 --start 00:01:30 --duration 5 --out highlight2.mp4
{baseDir}/scripts/merge.sh highlight1.mp4 highlight2.mp4 --out highlights.mp4
```

### Add Background Music

Replace or mix audio:

```bash
# Replace audio
ffmpeg -i video.mp4 -i music.mp3 -c:v copy -map 0:v:0 -map 1:a:0 -shortest output.mp4

# Mix audio (video audio at 70%, music at 30%)
ffmpeg -i video.mp4 -i music.mp3 -filter_complex "[0:a]volume=0.7[a0];[1:a]volume=0.3[a1];[a0][a1]amix=inputs=2:duration=first" -c:v copy -shortest output.mp4
```

## Tips

- **Quality**: Use `-crf 18` for high quality, `-crf 28` for smaller files (default is 23)
- **Presets**: Use `-preset slow` for better compression, `-preset fast` for quicker encoding
- **Hardware acceleration**: On Apple Silicon, add `-c:v h264_videotoolbox` for faster encoding
- **Copy mode**: Use `-c copy` to avoid re-encoding (much faster, but limited editing)

## Troubleshooting

### Merge fails with "Codec mismatch"

Videos must have the same codec, resolution, and frame rate. Re-encode them first:

```bash
ffmpeg -i input1.mp4 -c:v libx264 -c:a aac -vf "scale=1920:1080" -r 30 temp1.mp4
ffmpeg -i input2.mp4 -c:v libx264 -c:a aac -vf "scale=1920:1080" -r 30 temp2.mp4
{baseDir}/scripts/merge.sh temp1.mp4 temp2.mp4 --out merged.mp4
```

### Subtitles not showing

Ensure subtitle file format matches extension (.srt, .ass, .vtt). Check encoding:

```bash
file -I subtitles.srt  # Should show charset=utf-8
```

Convert if needed:

```bash
iconv -f GBK -t UTF-8 subtitles.srt > subtitles_utf8.srt
```
