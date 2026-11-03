---
description: Evaluate installed media codecs on the computer
tags: [media, codecs, audio, video, system, project, gitignored]
---

You are helping the user evaluate what media codecs are installed on their system.

## Process

1. **Check GStreamer plugins**
   - List GStreamer plugins: `gst-inspect-1.0 | grep -i plugin`
   - Check installed GStreamer packages:
     ```bash
     dpkg -l | grep -E "gstreamer.*plugin"
     ```
   - Key packages:
     - `gstreamer1.0-plugins-base` (essential)
     - `gstreamer1.0-plugins-good` (common formats)
     - `gstreamer1.0-plugins-bad` (additional)
     - `gstreamer1.0-plugins-ugly` (patent-encumbered)
     - `gstreamer1.0-libav` (FFmpeg integration)

2. **Check FFmpeg codecs**
   - List FFmpeg codecs: `ffmpeg -codecs 2>/dev/null | head -50`
   - List encoders: `ffmpeg -encoders 2>/dev/null | head -20`
   - List decoders: `ffmpeg -decoders 2>/dev/null | head -20`
   - Check FFmpeg version: `ffmpeg -version`

3. **Check VA-API support (hardware acceleration)**
   - Check VA-API: `vainfo`
   - For AMD: Should show ROCm/RADV support
   - Verify hardware encoding/decoding support

4. **Check for common codec packages**
   ```bash
   dpkg -l | grep -E "libavcodec|libavformat|libavutil|x264|x265|vp9|opus|aac|mp3"
   ```

5. **Test codec support**
   - Video codecs to verify:
     - H.264/AVC (most common)
     - H.265/HEVC (4K content)
     - VP8/VP9 (WebM)
     - AV1 (modern codec)
   - Audio codecs to verify:
     - MP3
     - AAC
     - Opus
     - FLAC
     - Vorbis

6. **Identify missing codecs**
   - Common needs:
     - DVD playback: `libdvd-pkg`
     - Proprietary formats: `ubuntu-restricted-extras`
     - H.265 encoding: `x265`
     - AV1: `libaom3`, `libdav1d-dev`

7. **Suggest installations**

   **For comprehensive codec support:**
   ```bash
   sudo apt install ubuntu-restricted-extras
   sudo apt install ffmpeg
   sudo apt install gstreamer1.0-plugins-{base,good,bad,ugly}
   sudo apt install gstreamer1.0-libav
   sudo apt install gstreamer1.0-vaapi  # Hardware acceleration
   ```

   **For DVD:**
   ```bash
   sudo apt install libdvd-pkg
   sudo dpkg-reconfigure libdvd-pkg
   ```

8. **Check browser codec support**
   - Visit: `https://www.youtube.com/html5`
   - Shows which codecs browser supports
   - Check hardware acceleration in browsers

## Output

Provide a report showing:
- Installed GStreamer plugins
- FFmpeg codec support
- Hardware acceleration status (VA-API)
- Missing common codecs
- Installation recommendations
- Browser codec support status
