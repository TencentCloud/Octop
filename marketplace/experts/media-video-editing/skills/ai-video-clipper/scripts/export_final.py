#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI视频剪辑 - 最终导出脚本
功能：成品导出、格式转换、压缩优化
"""

import os
import json
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Dict, Optional

DEFAULT_CONFIG = {
    "preset": "high",  # high/medium/low/compress
    "format": "mp4",
    "resolution": "",  # 空表示保持原分辨率
    "fps": 0,  # 0表示保持原帧率
    "bitrate": "",
    "crf": 23,
    "storage_path": "",
    "naming": "{date}_{theme}_{duration}",
    "auto_upload": False,  # 是否自动上传到云端
    "sync_to_cloud": False
}

PRESET_CONFIG = {
    "high": {
        "crf": 18,
        "bitrate": "8M",
        "preset": "slow"
    },
    "medium": {
        "crf": 23,
        "bitrate": "5M",
        "preset": "medium"
    },
    "low": {
        "crf": 28,
        "bitrate": "2M",
        "preset": "fast"
    },
    "compress": {
        "crf": 30,
        "bitrate": "1M",
        "preset": "veryfast"
    }
}

class VideoExporter:
    def __init__(self, config: Dict = None):
        self.config = {**DEFAULT_CONFIG, **(config or {})}
        self.ffmpeg_path = "ffmpeg"
        self.ffprobe_path = "ffprobe"
        
    def get_video_info(self, video_file: str) -> Dict:
        """获取视频信息"""
        cmd = [self.ffprobe_path, "-v", "quiet", "-print_format", "json", 
               "-show_format", "-show_streams", video_file]
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True)
            return json.loads(result.stdout)
        except:
            return {}
    
    def calculate_duration(self, video_file: str) -> str:
        """计算视频时长"""
        info = self.get_video_info(video_file)
        
        if "format" in info:
            duration = float(info["format"].get("duration", 0))
            m, s = divmod(int(duration), 60)
            h, m = divmod(m, 60)
            if h > 0:
                return f"{h}h{m}m{s}s"
            return f"{m}m{s}s"
        
        return "unknown"
    
    def get_output_path(self, video_file: str, theme: str = "video") -> str:
        """生成输出文件路径"""
        storage_path = self.config["storage_path"] or os.path.dirname(video_file)
        
        os.makedirs(storage_path, exist_ok=True)
        
        # 解析命名模板
        naming = self.config["naming"]
        date_str = datetime.now().strftime("%Y%m%d")
        duration_str = self.calculate_duration(video_file)
        
        filename = naming.replace("{date}", date_str)
        filename = filename.replace("{theme}", theme)
        filename = filename.replace("{duration}", duration_str)
        
        # 清理文件名
        filename = "".join(c for c in filename if c.isalnum() or c in "._-")
        
        output_file = os.path.join(storage_path, f"{filename}.{self.config['format']}")
        
        # 避免覆盖
        if os.path.exists(output_file):
            output_file = os.path.join(storage_path, f"{filename}_{datetime.now().strftime('%H%M%S')}.{self.config['format']}")
        
        return output_file
    
    def export(self, video_file: str, theme: str = "video", config: Dict = None) -> str:
        """执行导出"""
        if config:
            self.config.update(config)
        
        print(f"[导出] ============================================")
        print(f"[导出] 开始导出视频")
        print(f"[导出] 预设: {self.config['preset']}")
        print(f"[导出] 格式: {self.config['format']}")
        print(f"[导出] ============================================")
        
        # 获取视频信息
        info = self.get_video_info(video_file)
        
        # 获取输出路径
        output_file = self.get_output_path(video_file, theme)
        
        # 获取预设配置
        preset = PRESET_CONFIG.get(self.config["preset"], PRESET_CONFIG["medium"])
        
        # 构建FFmpeg命令
        cmd = [self.ffmpeg_path, "-i", video_file]
        
        # 视频编码参数
        video_filters = []
        
        # 分辨率
        if self.config["resolution"]:
            video_filters.append(f"scale={self.config['resolution']}")
        
        # 帧率
        if self.config["fps"] > 0:
            video_filters.append(f"fps={self.config['fps']}")
        
        if video_filters:
            cmd.extend(["-vf", ",".join(video_filters)])
        
        # 编码器设置
        cmd.extend([
            "-c:v", "libx264",
            "-preset", preset["preset"],
            "-crf", str(preset["crf"])
        ])
        
        if self.config["bitrate"]:
            cmd.extend(["-b:v", self.config["bitrate"]])
        
        # 音频设置
        cmd.extend([
            "-c:a", "aac",
            "-b:a", "128k"
        ])
        
        # 输出文件
        cmd.extend(["-y", output_file])
        
        print(f"[导出] 正在导出...")
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
            
            if result.returncode != 0:
                print(f"[导出] FFmpeg错误: {result.stderr}")
                # 尝试简化导出
                return self._simple_export(video_file, output_file)
            
            # 验证输出文件
            if os.path.exists(output_file):
                file_size = os.path.getsize(output_file) / (1024 * 1024)
                print(f"[导出] ============================================")
                print(f"[导出] 导出成功!")
                print(f"[导出] 文件: {output_file}")
                print(f"[导出] 大小: {file_size:.2f} MB")
                print(f"[导出] ============================================")
                
                # 清理临时文件
                self._cleanup_temp_files(video_file)
                
                return output_file
            else:
                raise Exception("导出失败，输出文件不存在")
                
        except subprocess.TimeoutExpired:
            print("[导出] 错误: 导出超时")
            raise
        except Exception as e:
            print(f"[导出] 错误: {str(e)}")
            raise
    
    def _simple_export(self, video_file: str, output_file: str) -> str:
        """简化导出方案"""
        print("[导出] 使用简化方案导出...")
        
        cmd = [
            self.ffmpeg_path, "-i", video_file,
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "23",
            "-c:a", "aac",
            "-y", output_file
        ]
        
        subprocess.run(cmd, capture_output=True, timeout=600)
        
        return output_file if os.path.exists(output_file) else video_file
    
    def _cleanup_temp_files(self, original_file: str):
        """清理临时文件"""
        temp_extensions = ["_temp.", "_temp_voice.", "_temp_bgm.", "_with_subs."]
        temp_dir = os.path.dirname(original_file)
        
        if not temp_dir:
            return
        
        for f in os.listdir(temp_dir):
            if any(f.endswith(ext.replace(".", "")) for ext in temp_extensions):
                try:
                    os.remove(os.path.join(temp_dir, f))
                except:
                    pass
    
    def convert_format(self, video_file: str, target_format: str, output_dir: str = None) -> str:
        """格式转换"""
        if output_dir is None:
            output_dir = os.path.dirname(video_file)
        
        base_name = os.path.splitext(os.path.basename(video_file))[0]
        output_file = os.path.join(output_dir, f"{base_name}_converted.{target_format}")
        
        print(f"[导出] 正在转换格式: {target_format}")
        
        cmd = [self.ffmpeg_path, "-i", video_file, "-y", output_file]
        
        if target_format == "mp4":
            cmd.extend(["-c:v", "libx264", "-c:a", "aac"])
        elif target_format == "webm":
            cmd.extend(["-c:v", "libvpx-vp9", "-c:a", "libopus"])
        elif target_format == "avi":
            cmd.extend(["-c:v", "libx264", "-c:a", "mp3"])
        
        subprocess.run(cmd, capture_output=True)
        
        return output_file if os.path.exists(output_file) else video_file
    
    def compress_for_mobile(self, video_file: str, output_dir: str = None) -> str:
        """移动端压缩"""
        if output_dir is None:
            output_dir = os.path.dirname(video_file)
        
        output_file = os.path.join(output_dir, "mobile_compressed.mp4")
        
        print("[导出] 正在压缩为移动端优化...")
        
        cmd = [
            self.ffmpeg_path, "-i", video_file,
            "-vf", "scale=1280:-2",
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-crf", "26",
            "-c:a", "aac",
            "-b:a", "96k",
            "-movflags", "+faststart",
            "-y", output_file
        ]
        
        subprocess.run(cmd, capture_output=True)
        
        return output_file if os.path.exists(output_file) else video_file


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="AI视频剪辑 - 导出")
    parser.add_argument("--input", "-i", required=True, help="输入视频文件")
    parser.add_argument("--output", "-o", help="输出目录")
    parser.add_argument("--preset", "-p", default="high", choices=["high", "medium", "low", "compress"], help="导出预设")
    parser.add_argument("--format", "-f", default="mp4", help="输出格式")
    parser.add_argument("--resolution", "-r", help="输出分辨率 (如1920x1080)")
    parser.add_argument("--theme", "-t", default="video", help="视频主题")
    parser.add_argument("--storage", "-s", help="存储路径")
    
    args = parser.parse_args()
    
    config = DEFAULT_CONFIG.copy()
    config["preset"] = args.preset
    config["format"] = args.format
    config["resolution"] = args.resolution or ""
    config["storage_path"] = args.output or args.storage or ""
    
    exporter = VideoExporter(config)
    output_file = exporter.export(args.input, args.theme)
    
    print(f"\n导出完成! 文件: {output_file}")


if __name__ == "__main__":
    main()
