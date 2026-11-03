#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI视频剪辑 - 音频处理脚本
功能：音频分离、人声增强、背景音乐匹配、音效添加
"""

import os
import json
import subprocess
import random
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional

DEFAULT_CONFIG = {
    "voice_volume": 1.0,
    "bgm_enabled": True,
    "bgm_volume": 0.3,
    "bgm_path": "",  # 背景音乐目录
    "sfx_enabled": True,
    "sfx_path": "",  # 音效目录
    "noise_reduction": True,
    "enhance_voice": True
}

class AudioProcessor:
    def __init__(self, config: Dict = None):
        self.config = {**DEFAULT_CONFIG, **(config or {})}
        self.ffmpeg_path = "ffmpeg"
        
    def separate_audio(self, video_file: str, output_dir: str) -> Dict[str, str]:
        """分离音频"""
        print("[音频] 正在分离音频轨道...")
        
        os.makedirs(output_dir, exist_ok=True)
        base_name = os.path.splitext(os.path.basename(video_file))[0]
        
        # 分离人声/背景音乐（需要spleeter或其他工具）
        voice_file = os.path.join(output_dir, f"{base_name}_voice.wav")
        bgm_file = os.path.join(output_dir, f"{base_name}_bgm.wav")
        
        # 简单分离：复制原音频
        cmd_voice = [self.ffmpeg_path, "-i", video_file, "-vn", "-acodec", "pcm_s16le", "-y", voice_file]
        subprocess.run(cmd_voice, capture_output=True)
        
        return {"voice": voice_file, "bgm": bgm_file}
    
    def enhance_voice(self, voice_file: str, output_dir: str) -> str:
        """增强人声"""
        if not self.config["enhance_voice"]:
            return voice_file
        
        print("[音频] 正在增强人声...")
        
        output_file = os.path.join(output_dir, f"enhanced_voice.wav")
        
        # 使用FFmpeg音频滤镜增强人声
        cmd = [
            self.ffmpeg_path, "-i", voice_file,
            "-af", "loudnorm=I=-16:TP=-1.5:LRA=11",
            "-y", output_file
        ]
        subprocess.run(cmd, capture_output=True)
        
        return output_file if os.path.exists(output_file) else voice_file
    
    def reduce_noise(self, voice_file: str, output_dir: str) -> str:
        """降噪处理"""
        if not self.config["noise_reduction"]:
            return voice_file
        
        print("[音频] 正在降噪处理...")
        
        output_file = os.path.join(output_dir, f"denoised_voice.wav")
        
        cmd = [
            self.ffmpeg_path, "-i", voice_file,
            "-af", "afftdn=nf=-25",
            "-y", output_file
        ]
        subprocess.run(cmd, capture_output=True)
        
        return output_file if os.path.exists(output_file) else voice_file
    
    def select_bgm(self, video_duration: float) -> Optional[str]:
        """选择背景音乐"""
        if not self.config["bgm_enabled"] or not self.config["bgm_path"]:
            return None
        
        print("[音频] 正在选择背景音乐...")
        
        bgm_dir = Path(self.config["bgm_path"])
        if not bgm_dir.exists():
            print("[音频] 背景音乐目录不存在")
            return None
        
        bgm_files = list(bgm_dir.glob("*.mp3")) + list(bgm_dir.glob("*.wav")) + list(bgm_dir.glob("*.aac"))
        
        if not bgm_files:
            print("[音频] 未找到背景音乐文件")
            return None
        
        # 随机选择或根据节奏匹配
        selected_bgm = random.choice(bgm_files)
        print(f"[音频] 已选择背景音乐: {selected_bgm.name}")
        
        return str(selected_bgm)
    
    def adjust_bgm_duration(self, bgm_file: str, target_duration: float, output_dir: str) -> str:
        """调整背景音乐时长"""
        output_file = os.path.join(output_dir, "adjusted_bgm.wav")
        
        cmd = [
            self.ffmpeg_path, "-i", bgm_file,
            "-t", str(target_duration),
            "-y", output_file
        ]
        subprocess.run(cmd, capture_output=True)
        
        return output_file
    
    def add_bgm_to_video(self, video_file: str, bgm_file: str, output_dir: str) -> str:
        """添加背景音乐到视频"""
        if not bgm_file or not os.path.exists(bgm_file):
            return video_file
        
        print("[音频] 正在添加背景音乐...")
        
        os.makedirs(output_dir, exist_ok=True)
        output_file = os.path.join(output_dir, "with_bgm.mp4")
        
        cmd = [
            self.ffmpeg_path, "-i", video_file,
            "-i", bgm_file,
            "-filter_complex",
            f"[0:a]volume={self.config['voice_volume']}[voice];[1:a]volume={self.config['bgm_volume']}[bgm];[voice][bgm]amix=inputs=2:duration=first[aout]",
            "-map", "0:v",
            "-map", "[aout]",
            "-c:v", "copy",
            "-y", output_file
        ]
        subprocess.run(cmd, capture_output=True, timeout=300)
        
        return output_file if os.path.exists(output_file) else video_file
    
    def add_fade_effect(self, audio_file: str, fade_in: float, fade_out: float, output_dir: str) -> str:
        """添加淡入淡出效果"""
        print("[音频] 正在添加淡入淡出效果...")
        
        output_file = os.path.join(output_dir, "fade_audio.wav")
        
        cmd = [
            self.ffmpeg_path, "-i", audio_file,
            "-af", f"afade=t=in:st=0:d={fade_in},afade=t=out:st={self._get_duration(audio_file)-fade_out}:d={fade_out}",
            "-y", output_file
        ]
        subprocess.run(cmd, capture_output=True)
        
        return output_file
    
    def _get_duration(self, audio_file: str) -> float:
        """获取音频时长"""
        cmd = [self.ffmpeg_path, "-i", audio_file, "-f", "null", "-"]
        result = subprocess.run(cmd, capture_output=True, text=True, stderr=subprocess.PIPE)
        
        import re
        match = re.search(r"time=(\d+):(\d+):(\d+)", result.stderr)
        if match:
            return int(match.group(1)) * 3600 + int(match.group(2)) * 60 + int(match.group(3))
        return 10
    
    def process(self, video_file: str, output_dir: str = None, config: Dict = None) -> str:
        """执行音频处理流程"""
        if config:
            self.config.update(config)
        
        if output_dir is None:
            output_dir = os.path.dirname(video_file)
        os.makedirs(output_dir, exist_ok=True)
        
        print(f"[音频] ============================================")
        print(f"[音频] 开始音频处理")
        print(f"[音频] 视频文件: {video_file}")
        print(f"[音频] 背景音乐: {'启用' if self.config['bgm_enabled'] else '禁用'}")
        print(f"[音频] 人声增强: {'启用' if self.config['enhance_voice'] else '禁用'}")
        print(f"[音频] ============================================")
        
        video_duration = self._get_duration(video_file)
        
        # 1. 分离音频
        audio_files = self.separate_audio(video_file, output_dir)
        voice_file = audio_files["voice"]
        
        # 2. 降噪处理
        if self.config["noise_reduction"]:
            voice_file = self.reduce_noise(voice_file, output_dir)
        
        # 3. 增强人声
        if self.config["enhance_voice"]:
            voice_file = self.enhance_voice(voice_file, output_dir)
        
        # 4. 选择背景音乐
        bgm_file = self.select_bgm(video_duration)
        
        if bgm_file:
            bgm_file = self.adjust_bgm_duration(bgm_file, video_duration, output_dir)
            output_file = self.add_bgm_to_video(video_file, bgm_file, output_dir)
        else:
            # 只处理人声
            final_voice = self.add_fade_effect(voice_file, 1.0, 1.0, output_dir)
            # 合并回视频
            output_file = self._merge_audio_to_video(video_file, final_voice, output_dir)
        
        print(f"[音频] ============================================")
        print(f"[音频] 音频处理完成!")
        print(f"[音频] 输出文件: {output_file}")
        print(f"[音频] ============================================")
        
        return output_file
    
    def _merge_audio_to_video(self, video_file: str, audio_file: str, output_dir: str) -> str:
        """将处理后的音频合并回视频"""
        output_file = os.path.join(output_dir, "processed_video.mp4")
        
        cmd = [
            self.ffmpeg_path, "-i", video_file,
            "-i", audio_file,
            "-c:v", "copy",
            "-map", "0:v",
            "-map", "1:a",
            "-y", output_file
        ]
        subprocess.run(cmd, capture_output=True)
        
        return output_file if os.path.exists(output_file) else video_file


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="AI视频剪辑 - 音频处理")
    parser.add_argument("--input", "-i", required=True, help="输入视频文件")
    parser.add_argument("--output", "-o", help="输出目录")
    parser.add_argument("--bgm", "-b", help="背景音乐目录")
    parser.add_argument("--no-bgm", action="store_true", help="禁用背景音乐")
    parser.add_argument("--voice-volume", type=float, default=1.0, help="人声音量")
    parser.add_argument("--bgm-volume", type=float, default=0.3, help="背景音乐音量")
    parser.add_argument("--no-noise-reduction", action="store_true", help="禁用降噪")
    parser.add_argument("--no-enhance", action="store_true", help="禁用人声增强")
    
    args = parser.parse_args()
    
    config = DEFAULT_CONFIG.copy()
    config["bgm_path"] = args.bgm or ""
    config["bgm_enabled"] = not args.no_bgm
    config["voice_volume"] = args.voice_volume
    config["bgm_volume"] = args.bgm_volume
    config["noise_reduction"] = not args.no_noise_reduction
    config["enhance_voice"] = not args.no_enhance
    
    processor = AudioProcessor(config)
    output_file = processor.process(args.input, args.output)
    
    print(f"\n音频处理完成! 输出文件: {output_file}")


if __name__ == "__main__":
    main()
