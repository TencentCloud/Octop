#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI视频剪辑 - 字幕生成脚本
功能：使用Whisper自动识别语音生成字幕，支持中英双语
"""

import os
import json
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional

try:
    import whisper
    WHISPER_AVAILABLE = True
except ImportError:
    WHISPER_AVAILABLE = False

DEFAULT_CONFIG = {
    "model": "base",  # tiny/base/small/medium/large
    "language": "zh",  # 中文: zh, 英文: en, 自动: None
    "subtitle_style": {
        "font": "Arial",
        "font_size": 36,
        "color": "white",
        "bg_color": "black@0.5",
        "position": "bottom_center"
    },
    "output_format": "srt"  # srt/vtt
}

class SubtitleGenerator:
    def __init__(self, config: Dict = None):
        self.config = {**DEFAULT_CONFIG, **(config or {})}
        self.ffmpeg_path = "ffmpeg"
        self.ffprobe_path = "ffprobe"
        
    def extract_audio(self, video_file: str, output_dir: str) -> str:
        """从视频提取音频"""
        audio_file = os.path.join(output_dir, "temp_audio.wav")
        cmd = [
            self.ffmpeg_path, "-i", video_file,
            "-vn", "-acodec", "pcm_s16le",
            "-ar", "16000", "-ac", "1",
            "-y", audio_file
        ]
        subprocess.run(cmd, capture_output=True)
        return audio_file
    
    def transcribe(self, audio_file: str) -> List[Dict]:
        """使用Whisper进行语音识别"""
        if not WHISPER_AVAILABLE:
            print("[字幕] 警告: Whisper未安装，使用模拟数据")
            return self._mock_transcribe(audio_file)
        
        print(f"[字幕] 正在加载 Whisper {self.config['model']} 模型...")
        model = whisper.load_model(self.config["model"])
        
        print("[字幕] 正在进行语音识别...")
        result = model.transcribe(
            audio_file, 
            language=self.config.get("language"),
            verbose=False
        )
        
        segments = []
        for segment in result["segments"]:
            segments.append({
                "start": segment["start"],
                "end": segment["end"],
                "text": segment["text"].strip()
            })
        
        return segments
    
    def _mock_transcribe(self, audio_file: str) -> List[Dict]:
        """模拟语音识别结果（Whisper未安装时使用）"""
        print("[字幕] 使用模拟字幕数据...")
        return [
            {"start": 0.0, "end": 3.5, "text": "这是第一句台词"},
            {"start": 4.0, "end": 7.5, "text": "这是第二句台词"},
            {"start": 8.0, "end": 12.0, "text": "这里是精彩片段"}
        ]
    
    def generate_srt(self, segments: List[Dict], output_file: str) -> str:
        """生成SRT字幕文件"""
        with open(output_file, "w", encoding="utf-8") as f:
            for i, seg in enumerate(segments, 1):
                start_time = self._format_srt_time(seg["start"])
                end_time = self._format_srt_time(seg["end"])
                f.write(f"{i}\n")
                f.write(f"{start_time} --> {end_time}\n")
                f.write(f"{seg['text']}\n\n")
        
        print(f"[字幕] SRT字幕已生成: {output_file}")
        return output_file
    
    def generate_vtt(self, segments: List[Dict], output_file: str) -> str:
        """生成VTT字幕文件"""
        with open(output_file, "w", encoding="utf-8") as f:
            f.write("WEBVTT\n\n")
            for i, seg in enumerate(segments, 1):
                start_time = self._format_vtt_time(seg["start"])
                end_time = self._format_vtt_time(seg["end"])
                f.write(f"{i}\n")
                f.write(f"{start_time} --> {end_time}\n")
                f.write(f"{seg['text']}\n\n")
        
        print(f"[字幕] VTT字幕已生成: {output_file}")
        return output_file
    
    def burn_subtitles(self, video_file: str, subtitle_file: str, output_file: str) -> str:
        """将字幕烧录到视频"""
        print("[字幕] 正在烧录字幕到视频...")
        
        style = self.config["subtitle_style"]
        
        # 构建字幕样式
        font_size = style.get("font_size", 36)
        color = style.get("color", "white")
        position = style.get("position", "bottom_center")
        
        # 字幕位置映射
        position_map = {
            "top_center": "x=(w-text_w)/2:y=50",
            "bottom_center": f"x=(w-text_w)/2:y=h-text_h-{font_size}",
            "center": "x=(w-text_w)/2:y=(h-text_h)/2"
        }
        
        force_style = f"FontSize={font_size},PrimaryColour=&HFFFFFF&,Outline=2,BorderStyle=3"
        if position in position_map:
            force_style += f",Alignment=5" if position == "bottom_center" else ""
        
        cmd = [
            self.ffmpeg_path, "-i", video_file,
            "-vf", f"subtitles='{subtitle_file}':force_style='{force_style}'",
            "-c:a", "copy",
            "-y", output_file
        ]
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                print(f"[字幕] 烧录失败，尝试备用方案...")
                return self._burn_subtitles_fallback(video_file, subtitle_file, output_file)
            
            print(f"[字幕] 字幕烧录完成: {output_file}")
            return output_file
        except Exception as e:
            print(f"[字幕] 错误: {str(e)}")
            return video_file
    
    def _burn_subtitles_fallback(self, video_file: str, subtitle_file: str, output_file: str) -> str:
        """备用字幕烧录方案"""
        cmd = [
            self.ffmpeg_path, "-i", video_file,
            "-i", subtitle_file,
            "-c:v", "libx264", "-preset", "fast",
            "-c:a", "copy",
            "-c:s", "mov_text",
            "-metadata:s:s:0", "language=chi",
            "-y", output_file
        ]
        
        subprocess.run(cmd, capture_output=True)
        return output_file if os.path.exists(output_file) else video_file
    
    def _format_srt_time(self, seconds: float) -> str:
        """格式化SRT时间"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        millisecs = int((seconds % 1) * 1000)
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{millisecs:03d}"
    
    def _format_vtt_time(self, seconds: float) -> str:
        """格式化VTT时间"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        millisecs = int((seconds % 1) * 1000)
        return f"{hours:02d}:{minutes:02d}:{secs:02d}.{millisecs:03d}"
    
    def generate(self, video_file: str, output_dir: str = None) -> str:
        """执行字幕生成流程"""
        if output_dir is None:
            output_dir = os.path.dirname(video_file)
        os.makedirs(output_dir, exist_ok=True)
        
        print(f"[字幕] ============================================")
        print(f"[字幕] 开始生成字幕")
        print(f"[字幕] 视频文件: {video_file}")
        print(f"[字幕] 模型: {self.config['model']}")
        print(f"[字幕] ============================================")
        
        # 1. 提取音频
        audio_file = self.extract_audio(video_file, output_dir)
        
        # 2. 语音识别
        segments = self.transcribe(audio_file)
        
        if not segments:
            print("[字幕] 警告: 未能识别到语音内容")
            return video_file
        
        print(f"[字幕] 识别到 {len(segments)} 条字幕")
        
        # 3. 生成字幕文件
        base_name = os.path.splitext(os.path.basename(video_file))[0]
        subtitle_file = os.path.join(output_dir, f"{base_name}.{self.config['output_format']}")
        
        if self.config["output_format"] == "srt":
            self.generate_srt(segments, subtitle_file)
        else:
            self.generate_vtt(segments, subtitle_file)
        
        # 4. 烧录字幕
        output_file = os.path.join(output_dir, f"{base_name}_with_subs.{self.config['output_format']}")
        final_file = self.burn_subtitles(video_file, subtitle_file, output_file)
        
        # 清理临时文件
        if os.path.exists(audio_file):
            try:
                os.remove(audio_file)
            except:
                pass
        
        print(f"[字幕] ============================================")
        print(f"[字幕] 字幕生成完成!")
        print(f"[字幕] 输出文件: {final_file}")
        print(f"[字幕] ============================================")
        
        return final_file


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="AI视频剪辑 - 字幕生成")
    parser.add_argument("--input", "-i", required=True, help="输入视频文件")
    parser.add_argument("--output", "-o", help="输出目录")
    parser.add_argument("--model", "-m", default="base", choices=["tiny", "base", "small", "medium", "large"], help="Whisper模型")
    parser.add_argument("--language", "-l", default="zh", help="语言 (zh/en/auto)")
    parser.add_argument("--format", "-f", default="srt", choices=["srt", "vtt"], help="字幕格式")
    parser.add_argument("--burn", "-b", action="store_true", help="是否烧录字幕到视频")
    
    args = parser.parse_args()
    
    config = DEFAULT_CONFIG.copy()
    config["model"] = args.model
    config["language"] = args.language if args.language != "auto" else None
    config["output_format"] = args.format
    
    generator = SubtitleGenerator(config)
    output_file = generator.generate(args.input, args.output)
    
    if args.burn:
        print(f"\n字幕已烧录到视频: {output_file}")
    else:
        print(f"\n字幕文件已生成: {output_file.replace('_with_subs.srt', '.srt')}")


if __name__ == "__main__":
    main()
