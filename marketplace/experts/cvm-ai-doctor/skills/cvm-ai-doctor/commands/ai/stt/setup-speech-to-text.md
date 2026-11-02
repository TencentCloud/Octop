---
description: Check installed STT apps and suggest installations including local Whisper
tags: [ai, stt, whisper, speech-recognition, audio, project, gitignored]
---

You are helping the user set up speech-to-text applications including local Whisper.

## Process

1. **Check currently installed STT apps**
   - System packages: `dpkg -l | grep -E "whisper|speech|voice"`
   - Python packages: `pip list | grep -E "whisper|speech|vosk"`
   - Check `~/programs/ai-ml/` for installed apps

2. **Suggest STT installation candidates**

   **Whisper (OpenAI) - Recommended:**
   - Best quality, local inference
   - Multiple model sizes available
   - Multilingual support

   **Other options:**
   - Vosk - Lightweight, offline
   - Coqui STT - Mozilla's solution
   - SpeechNote - Simple GUI
   - Subtitle Edit - Video subtitling
   - Subtld - Automatic subtitles

3. **Install Whisper (local)**

   **Method 1: Using pip (simple)**
   ```bash
   pip install openai-whisper
   ```

   **Method 2: Using conda (recommended)**
   ```bash
   conda create -n whisper python=3.11 -y
   conda activate whisper
   pip install openai-whisper
   ```

   **Install dependencies:**
   ```bash
   # For audio processing
   sudo apt install ffmpeg
   pip install setuptools-rust
   ```

4. **Install faster-whisper (optimized)**
   ```bash
   pip install faster-whisper
   ```
   - Uses CTranslate2 for faster inference
   - Lower VRAM usage

5. **Install WhisperX (advanced)**
   ```bash
   pip install whisperx
   ```
   - Includes alignment and diarization
   - Better timestamps

6. **Download Whisper models**
   - Models are downloaded automatically on first use
   - Sizes: tiny, base, small, medium, large
   - Suggest based on VRAM:
     - < 4GB: tiny or base
     - 4-8GB: small or medium
     - 8GB+: large

7. **Test installation**
   ```bash
   whisper audio.mp3 --model base --language en
   ```

8. **Install GUI options**

   **Whisper Desktop:**
   - Check if available as AppImage or Flatpak

   **Subtitle Edit:**
   ```bash
   sudo apt install subtitleeditor
   ```

   **Custom GUI:**
   - Suggest installing gradio-based Whisper UIs

9. **Create helper script**
   - Offer to create `~/scripts/transcribe.sh`:
     ```bash
     #!/bin/bash
     whisper "$1" --model medium --language en --output_format txt
     ```

10. **Suggest workflows**
   - Real-time transcription
   - Batch processing
   - Video subtitling
   - Meeting transcription

## Output

Provide a summary showing:
- Currently installed STT applications
- Whisper installation status and model sizes
- GPU acceleration status
- Suggested models based on hardware
- Example commands for transcription
- GUI options available
- Helper scripts created
