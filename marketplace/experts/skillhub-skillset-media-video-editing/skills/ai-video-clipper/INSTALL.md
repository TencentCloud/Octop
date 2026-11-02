# AI视频剪辑Skill安装指南

## 环境要求

- Python 3.8+
- FFmpeg
- (可选) Whisper

## 安装步骤

### 1. 安装Python依赖

```bash
pip install whisper openai-whisper moviepy Pillow numpy
```

或使用requirements.txt:

```bash
pip install -r requirements.txt
```

### 2. 安装FFmpeg

#### Windows
1. 下载 FFmpeg: https://ffmpeg.org/download.html
2. 解压到指定目录 (如 C:\ffmpeg)
3. 将 bin 目录添加到系统 PATH
4. 验证安装: `ffmpeg -version`

#### macOS
```bash
brew install ffmpeg
```

#### Linux
```bash
sudo apt install ffmpeg
```

### 3. 安装Whisper (可选，用于字幕生成)

```bash
pip install openai-whisper
```

或只安装模型:
```bash
pip install whisper
python -c "import whisper; whisper.load_model('base')"
```

### 4. 验证安装

```bash
python scripts/analyze_media.py -i "测试目录" -o "测试输出"
```

## 配置说明

编辑 `references/default_config.yaml` 或创建 `config.json`:

```json
{
  "input_dir": "D:\\电影素材",
  "output_dir": "D:\\AI视频剪辑",
  "target_duration": 180,
  "style": "auto",
  "transition": "fade",
  "bgm_enabled": true,
  "bgm_path": "D:\\AI视频剪辑\\背景音乐",
  "subtitle_enabled": true,
  "filter": "auto",
  "export_preset": "high"
}
```

## 快速测试

```bash
# 测试素材分析
python scripts/analyze_media.py -i "D:\\测试素材" -o "D:\\测试输出"

# 测试剪辑流程
python scripts/full_pipeline.py -i "D:\\测试素材" -o "D:\\测试输出" -d 30
```

## 常见问题

### FFmpeg not found
确保FFmpeg已添加到系统PATH，或在配置中指定路径:
```python
config["ffmpeg_path"] = "C:\\ffmpeg\\bin\\ffmpeg.exe"
```

### Whisper模型下载失败
手动下载模型:
```python
import whisper
model = whisper.load_model("base")
```

### 内存不足
减小剪辑片段数量或使用更低分辨率:
```bash
--target_duration 60
--export_resolution 1280x720
```

## 技术支持

如有问题，请检查:
1. Python版本 (3.8+)
2. FFmpeg是否正确安装
3. 素材路径是否正确
4. 输出目录是否有写入权限
