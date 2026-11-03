# FFmpeg 命令参考

## 基础命令

### 查看视频信息
```bash
ffprobe -v quiet -print_format json -show_format -show_streams input.mp4
```

### 格式转换
```bash
ffmpeg -i input.avi output.mp4
```

### 提取音频
```bash
ffmpeg -i input.mp4 -vn -acodec pcm_s16le output.wav
```

## 视频剪辑

### 按时间截取
```bash
ffmpeg -i input.mp4 -ss 00:00:10 -t 00:00:30 -c copy output.mp4
```

### 合并多个视频
```bash
# 创建 concat.txt
file 'input1.mp4'
file 'input2.mp4'

# 执行合并
ffmpeg -f concat -safe 0 -i concat.txt -c copy output.mp4
```

### 调整播放速度
```bash
# 2倍速
ffmpeg -i input.mp4 -filter:v "setpts=0.5*PTS" -af "atempo=2.0" output.mp4

# 0.5倍速（慢动作）
ffmpeg -i input.mp4 -filter:v "setpts=2.0*PTS" -af "atempo=0.5" output.mp4
```

## 转场效果

### 淡入淡出
```bash
# 视频淡入淡出
ffmpeg -i input.mp4 -vf "fade=t=in:st=0:d=2,fade=t=out:st=58:d=2" output.mp4

# 音频淡入淡出
ffmpeg -i input.mp4 -af "afade=t=in:st=0:d=2,afade=t=out:st=58:d=2" output.mp4
```

### 叠化（交叉淡化）
```bash
ffmpeg -i input1.mp4 -i input2.mp4 -filter_complex "xfade=transition=dissolve:duration=1:offset=5" output.mp4
```

## 滤镜效果

### 缩放分辨率
```bash
ffmpeg -i input.mp4 -vf "scale=1920:1080" output.mp4
```

### 调整帧率
```bash
ffmpeg -i input.mp4 -vf "fps=30" output.mp4
```

### 画面调整
```bash
# 亮度、对比度、饱和度
ffmpeg -i input.mp4 -vf "eq=brightness=0.1:contrast=1.2:saturation=1.3" output.mp4

# 锐化
ffmpeg -i input.mp4 -vf "unsharp=5:5:0.8:3:3:0.4" output.mp4
```

### 暗角效果
```bash
ffmpeg -i input.mp4 -vf "vignette=angle=0.5" output.mp4
```

### 模糊效果
```bash
ffmpeg -i input.mp4 -vf "boxblur=2:1" output.mp4
```

### 颜色调整
```bash
# 冷色调
ffmpeg -i input.mp4 -vf "colortemperature=s:8000K" output.mp4

# 暖色调
ffmpeg -i input.mp4 -vf "colortemperature=t:6500K" output.mp4
```

## 字幕处理

### 烧录字幕
```bash
ffmpeg -i input.mp4 -vf "subtitles='subtitle.srt':force_style='FontSize=24,PrimaryColour=&HFFFFFF&'" output.mp4
```

### 嵌入字幕流
```bash
ffmpeg -i input.mp4 -i subtitle.srt -c:s mov_text -c:v copy -c:a copy output.mp4
```

## 音频处理

### 调整音量
```bash
ffmpeg -i input.mp4 -af "volume=1.5" output.mp4
```

### 混音
```bash
ffmpeg -i video.mp4 -i bgm.mp3 -filter_complex "[0:a]volume=1.0[voice];[1:a]volume=0.3[bgm];[voice][bgm]amix=inputs=2:duration=first[aout]" -map 0:v -map "[aout]" output.mp4
```

### 降噪
```bash
ffmpeg -i input.mp4 -af "afftdn=nf=-25" output.mp4
```

### 音量标准化
```bash
ffmpeg -i input.mp4 -af "loudnorm=I=-16:TP=-1.5:LRA=11" output.mp4
```

## 编码参数

### H.264 编码预设
```bash
# 快速编码
ffmpeg -i input.mp4 -c:v libx264 -preset ultrafast -crf 23 output.mp4

# 慢速编码（更高质量）
ffmpeg -i input.mp4 -c:v libx264 -preset veryslow -crf 18 output.mp4
```

### CRF 值参考
| CRF | 质量 | 适用场景 |
|-----|------|----------|
| 18-20 | 近乎无损 | 存档 |
| 23 | 默认 | 通用 |
| 26-28 | 较低质量 | 流媒体 |
| 28+ | 低质量 | 移动端 |

### 比特率控制
```bash
# 固定比特率
ffmpeg -i input.mp4 -b:v 5M -maxrate 6M -bufsize 10M output.mp4

# 使用 CRF
ffmpeg -i input.mp4 -crf 23 -preset medium output.mp4
```

## 常用输出格式

### MP4 (H.264 + AAC)
```bash
ffmpeg -i input -c:v libx264 -preset medium -crf 23 -c:a aac -b:a 128k output.mp4
```

### WebM (VP9 + Opus)
```bash
ffmpeg -i input -c:v libvpx-vp9 -crf 30 -b:v 0 -c:a libopus -b:a 128k output.webm
```

### MOV (ProRes)
```bash
ffmpeg -i input -c:v prores_ks -profile:v 3 -c:a pcm_s16le output.mov
```

## 高级技巧

### 截取帧作为封面
```bash
ffmpeg -i input.mp4 -ss 00:00:05 -vframes 1 -q:v 2 thumbnail.jpg
```

### 添加水印
```bash
ffmpeg -i input.mp4 -i watermark.png -filter_complex "overlay=10:10" output.mp4
```

### 画中画
```bash
ffmpeg -i main.mp4 -i pip.mp4 -filter_complex "[1:v]scale=320:180[pip];[0:v][pip]overlay=W-w-10:H-h-10" output.mp4
```

### 反转视频
```bash
ffmpeg -i input.mp4 -vf "reverse" -af "areverse" output.mp4
```

### 静帧输出
```bash
ffmpeg -i input.mp4 -vf "select='eq(n\,100)'" -vframes 1 output.jpg
```

## 性能优化

### 多线程编码
```bash
ffmpeg -i input.mp4 -threads 8 -c:v libx264 -preset medium output.mp4
```

### GPU 加速 (NVENC)
```bash
ffmpeg -i input.mp4 -c:v h264_nvenc -preset p7 -cq 23 output.mp4
```

### 跳过不需要的处理
```bash
# 直接复制（不重新编码）
ffmpeg -i input.mp4 -c copy -c:s mov_text output.mp4
```
