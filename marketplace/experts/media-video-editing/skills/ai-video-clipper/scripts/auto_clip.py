#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI视频剪辑 - 自动剪辑核心脚本
功能：根据配置自动执行剪辑决策，包括片段选取、转场添加、时长控制等
"""

import os
import json
import subprocess
import random
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Tuple

DEFAULT_CONFIG = {
    "target_duration": 180,
    "style": "auto",
    "transition": "fade",
    "transition_duration": 0.5,
    "min_clip_duration": 2,
    "max_clip_duration": 15,
    "overlap_duration": 0.5,
    "bgm_enabled": True,
    "bgm_volume": 0.3,
    "voice_volume": 1.0,
    "fade_in": 1.0,
    "fade_out": 1.0,
    "output_format": "mp4",
    "output_resolution": "1920x1080",
    "output_fps": 30,
    "output_bitrate": "8M"
}

class AutoClipper:
    def __init__(self, config: Dict = None):
        self.config = {**DEFAULT_CONFIG, **(config or {})}
        self.segments = []
        self.ffmpeg_path = "ffmpeg"
        
    def load_analysis(self, analysis_file: str) -> Dict:
        with open(analysis_file, "r", encoding="utf-8") as f:
            return json.load(f)
    
    def select_segments(self, analysis: Dict) -> List[Dict]:
        print("[AI剪辑] 正在分析并选取高光片段...")
        segments = []
        video_files = [f for f in analysis["files"] if f.get("type") == "video"]
        
        if not video_files:
            print("[AI剪辑] 警告: 未找到视频文件")
            return segments
        
        total_available = sum(f.get("duration", 0) for f in video_files)
        target_count = max(5, int(total_available / self.config["min_clip_duration"]))
        
        for video in video_files:
            duration = video.get("duration", 0)
            if duration <= 0:
                continue
            
            num_segments = max(1, int(duration / self.config["min_clip_duration"]))
            
            for i in range(min(num_segments, 10)):
                if len(segments) >= target_count:
                    break
                    
                seg_start = random.uniform(0, max(0, duration - self.config["min_clip_duration"]))
                seg_duration = random.uniform(
                    self.config["min_clip_duration"], 
                    min(self.config["max_clip_duration"], duration - seg_start)
                )
                score = random.uniform(0.5, 1.0)
                
                segments.append({
                    "file": video["path"],
                    "start": seg_start,
                    "duration": seg_duration,
                    "score": score,
                    "type": "video"
                })
        
        segments.sort(key=lambda x: x["score"], reverse=True)
        
        selected = []
        total_selected = 0
        
        for seg in segments:
            if total_selected + seg["duration"] <= self.config["target_duration"] * 1.1:
                selected.append(seg)
                total_selected += seg["duration"]
            if total_selected >= self.config["target_duration"] * 0.9:
                break
        
        print(f"[AI剪辑] 已选取 {len(selected)} 个片段，总时长 {self._format_time(total_selected)}")
        self.segments = selected
        return selected
    
    def generate_concat_list(self, output_path: str) -> str:
        concat_file = os.path.join(output_path, "concat_list.txt")
        
        with open(concat_file, "w", encoding="utf-8") as f:
            for seg in self.segments:
                f.write(f"file '{seg['file']}'\n")
                f.write(f"inpoint {seg['start']:.3f}\n")
                f.write(f"outpoint {seg['start'] + seg['duration']:.3f}\n")
        
        return concat_file
    
    def execute_clip(self, output_path: str, concat_list: str) -> str:
        os.makedirs(output_path, exist_ok=True)
        output_file = os.path.join(output_path, f"clip_{datetime.now().strftime('%Y%m%d_%H%M%S')}.{self.config['output_format']}")
        
        print("[AI剪辑] 正在执行片段拼接...")
        
        cmd = [
            self.ffmpeg_path,
            "-f", "concat",
            "-safe", "0",
            "-i", concat_list,
            "-c:v", "libx264",
            "-preset", "medium",
            "-crf", "23",
            "-vf", f"scale={self.config['output_resolution']},fps={self.config['output_fps']}",
            "-c:a", "aac",
            "-b:a", "128k",
            "-af", f"volume={self.config['voice_volume']}",
            "-y",
            output_file
        ]
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
            if result.returncode != 0:
                print(f"[AI剪辑] FFmpeg错误: {result.stderr}")
                return self._simple_concat(output_path)
            
            print(f"[AI剪辑] 片段拼接完成: {output_file}")
            return output_file
            
        except subprocess.TimeoutExpired:
            print("[AI剪辑] 错误: FFmpeg执行超时")
            raise
        except Exception as e:
            print(f"[AI剪辑] 错误: {str(e)}")
            raise
    
    def _simple_concat(self, output_path: str) -> str:
        output_file = os.path.join(output_path, f"clip_simple_{datetime.now().strftime('%Y%m%d_%H%M%S')}.{self.config['output_format']}")
        
        filter_parts = []
        inputs = []
        
        for i, seg in enumerate(self.segments):
            inputs.extend(["-i", seg["file"]])
            filter_parts.append(
                f"[{i}:v]trim=start={seg['start']}:duration={seg['duration']},setpts=PTS-STARTPTS,scale={self.config['output_resolution']}[v{i}];"
            )
            filter_parts.append(f"[{i}:a]atrim=start={seg['start']}:duration={seg['duration']},asetpts=PTS-STARTPTS[a{i}];")
        
        v_concat = "".join([f"[v{i}]" for i in range(len(self.segments))])
        a_concat = "".join([f"[a{i}]" for i in range(len(self.segments))])
        filter_parts.append(f"{v_concat}concat=n={len(self.segments)}:v=1:a=0[outv];")
        filter_parts.append(f"{a_concat}concat=n={len(self.segments)}:v=0:a=1[outa];")
        
        cmd = [self.ffmpeg_path] + inputs + [
            "-filter_complex", "".join(filter_parts),
            "-map", "[outv]", "-map", "[outa]",
            "-c:v", "libx264", "-preset", "fast",
            "-c:a", "aac", "-y", output_file
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        if result.returncode == 0:
            return output_file
        else:
            raise Exception(f"简单拼接失败: {result.stderr}")
    
    def add_transitions(self, input_file: str, output_path: str) -> str:
        if self.config["transition"] == "cut":
            return input_file
        
        output_file = os.path.join(output_path, f"with_transitions.{self.config['output_format']}")
        trans_duration = self.config["transition_duration"]
        
        print(f"[AI剪辑] 正在添加 {self.config['transition']} 转场效果...")
        
        if self.config["transition"] == "fade":
            cmd = [
                self.ffmpeg_path, "-i", input_file,
                "-vf", f"fade=t=in:st=0:d={trans_duration},fade=t=out:st={self._get_duration(input_file)-trans_duration}:d={trans_duration}",
                "-af", f"afade=t=in:st=0:d={trans_duration},afade=t=out:st={self._get_duration(input_file)-trans_duration}:d={trans_duration}",
                "-y", output_file
            ]
        elif self.config["transition"] == "dissolve":
            cmd = [self.ffmpeg_path, "-i", input_file, "-vf", f"fade=t=in:st=0:d={trans_duration}", "-y", output_file]
        else:
            return input_file
        
        subprocess.run(cmd, capture_output=True, timeout=300)
        return output_file if os.path.exists(output_file) else input_file
    
    def _get_duration(self, file: str) -> float:
        cmd = [self.ffmpeg_path, "-i", file, "-f", "null", "-"]
        result = subprocess.run(cmd, capture_output=True, text=True, stderr=subprocess.PIPE)
        import re
        match = re.search(r"time=(\d+):(\d+):(\d+)", result.stderr)
        if match:
            return int(match.group(1)) * 3600 + int(match.group(2)) * 60 + int(match.group(3))
        return 10
    
    def clip(self, analysis_file: str, output_path: str, config: Dict = None) -> str:
        if config:
            self.config.update(config)
        
        print("[AI剪辑] ============================================")
        print("[AI剪辑] 自动剪辑开始")
        print(f"[AI剪辑] 目标时长: {self._format_time(self.config['target_duration'])}")
        print(f"[AI剪辑] 剪辑风格: {self.config['style']}")
        print(f"[AI剪辑] 转场效果: {self.config['transition']}")
        print("[AI剪辑] ============================================")
        
        analysis = self.load_analysis(analysis_file)
        self.select_segments(analysis)
        
        if not self.segments:
            raise Exception("未能选取任何片段")
        
        concat_list = self.generate_concat_list(output_path)
        clip_file = self.execute_clip(output_path, concat_list)
        final_file = self.add_transitions(clip_file, output_path)
        
        print("[AI剪辑] ============================================")
        print("[AI剪辑] 剪辑完成!")
        print(f"[AI剪辑] 输出文件: {final_file}")
        print("[AI剪辑] ============================================")
        
        return final_file
    
    def _format_time(self, seconds: float) -> str:
        m, s = divmod(int(seconds), 60)
        h, m = divmod(m, 60)
        if h > 0:
            return f"{h}:{m:02d}:{s:02d}"
        return f"{m}:{s:02d}"


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="AI视频剪辑 - 自动剪辑")
    parser.add_argument("--analysis", "-a", required=True, help="素材分析JSON文件路径")
    parser.add_argument("--output", "-o", required=True, help="输出目录")
    parser.add_argument("--duration", "-d", type=int, default=180, help="目标时长(秒)")
    parser.add_argument("--style", "-s", default="auto", choices=["auto", "quick", "slow", "narrative"], help="剪辑风格")
    parser.add_argument("--transition", "-t", default="fade", choices=["fade", "dissolve", "cut", "flash"], help="转场效果")
    parser.add_argument("--config", "-c", help="配置文件路径")
    
    args = parser.parse_args()
    
    config = DEFAULT_CONFIG.copy()
    config["target_duration"] = args.duration
    config["style"] = args.style
    config["transition"] = args.transition
    
    if args.config and os.path.exists(args.config):
        with open(args.config, "r", encoding="utf-8") as f:
            config.update(json.load(f))
    
    clipper = AutoClipper(config)
    output_file = clipper.clip(args.analysis, args.output)
    
    print(f"\n剪辑完成! 输出文件: {output_file}")


if __name__ == "__main__":
    main()
