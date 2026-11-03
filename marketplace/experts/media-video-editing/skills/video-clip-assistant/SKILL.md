---
name: video-clip-assistant
description: 视频自动剪辑助手。基于 FFmpeg 自动提取精彩片段、生成字幕、裁剪时长、制作短视视频，支持多平台导出。当用户需要：自动剪辑视频、提取关键词片段、生成字幕并烧录、导出短视频、提取视频精华、生成视频摘要时使用此技能。
---

# Video Clip Assistant

视频自动剪辑助手。基于 FFmpeg，提供视频剪切、字幕生成、短视频导出等功能。

## 核心能力

1. **时间轴剪切** — 按时间戳提取片段
2. **关键词切片** — 基于 ASR 字幕找到关键词对应片段
3. **字幕烧录** — SRT 字幕压制到视频
4. **短视视频导出** — 裁剪为 9:16/1:1/16:9 多比例
5. **精华提取** — 自动从长视频提取高光片段

## 快速开始

### 按时间剪切

```bash
python3 scripts/cut_video.py --input video.mp4 --start 10 --duration 30 --output clip.mp4
```

### 提取多段

```bash
python3 scripts/cut_video.py --input video.mp4 --segments "0-30,60-90,120-150" --output ./clips/
```

### 烧录字幕

```bash
python3 scripts/burn_subtitles.py --input video.mp4 --srt subs.srt --output subtitled.mp4
```

### 导出短视频

```bash
python3 scripts/export_social.py --input video.mp4 --format vertical --duration 60 --output shorts/
```

## 脚本说明

### scripts/cut_video.py

按时间轴剪切视频。

```bash
python3 scripts/cut_video.py \
  --input <视频文件> \
  --start <秒> \
  --duration <秒> \
  [--segments "0-30,60-90"] \
  --output <输出>
```

### scripts/burn_subtitles.py

将 SRT 字幕烧录到视频。

```bash
python3 scripts/burn_subtitles.py \
  --input <视频> \
  --srt <字幕文件> \
  --output <输出>
```

**支持字幕位置、字体大小、颜色自定义。**

### scripts/export_social.py

导出为多平台适配格式。

```bash
python3 scripts/export_social.py \
  --input <视频> \
  --format <vertical|square|horizontal> \
  --duration <秒> \
  --output <输出目录>
```

| 格式 | 比例 | 用途 |
|------|------|------|
| vertical | 9:16 | 抖音/快手/小红书 |
| square | 1:1 | Instagram |
| horizontal | 16:9 | YouTube/B站 |

### scripts/extract_highlights.py

从长视频自动提取精华片段。

```bash
python3 scripts/extract_highlights.py \
  --input <视频> \
  --num-clips <片段数> \
  --min-duration <最小秒数> \
  --output <输出目录>
```

**使用场景检测算法定位精彩切换点。**

### scripts/generate_subtitles.py

生成 SRT 字幕文件（需要 ASR 服务）。

```bash
python3 scripts/generate_subtitles.py \
  --input <视频> \
  --provider <whisper|funclip> \
  --output <字幕.srt>
```

## 典型工作流

### 工作流1：从会议录像提取3个精华片段

```bash
# 1. 剪切3个片段
python3 scripts/cut_video.py \
  --input meeting.mp4 \
  --segments "300-360,720-780,1200-1260" \
  --output ./clips/

# 2. 分别导出为抖音格式
for f in ./clips/*.mp4; do
  python3 scripts/export_social.py \
    --input "$f" \
    --format vertical \
    --output ./shorts/
done
```

### 工作流2：给视频加上字幕

```bash
# 1. 生成字幕
python3 scripts/generate_subtitles.py \
  --input video.mp4 \
  --provider whisper \
  --output video.srt

# 2. 烧录字幕
python3 scripts/burn_subtitles.py \
  --input video.mp4 \
  --srt video.srt \
  --output subtitled.mp4
```

### 工作流3：一键生成多个短视频

```bash
python3 scripts/export_social.py \
  --input long_video.mp4 \
  --format vertical \
  --duration 60 \
  --output ./shorts/
```

## 环境要求

- **必须**：FFmpeg（`ffmpeg` / `ffprobe`）
- **可选**：FunClip（阿里开源 ASR 视频剪辑）
- **可选**：Whisper（本地或 API 模式）

## 安装参考

```bash
# 安装 FunClip（推荐）
pip install funclip

# 安装 Whisper
pip install openai-whisper

# FFmpeg（已有）
which ffmpeg  # 应返回路径
```
