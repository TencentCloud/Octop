#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI视频剪辑 - 素材分析脚本
功能：自动分析素材目录，识别视频/音频/图片，提取元数据，建立索引
"""

import os
import json
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional

# 配置区域 - 用户可修改
DEFAULT_CONFIG = {
    "input_dir": "",  # 素材输入目录
    "output_dir": "",  # 分析结果输出目录
    "supported_video": [".mp4", ".mov", ".avi", ".mkv", ".flv", ".wmv"],
    "supported_audio": [".mp3", ".wav", ".aac", ".flac", ".ogg"],
    "supported_image": [".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp"],
    "ffmpeg_path": "ffmpeg",  # FFmpeg路径，如已安装可留空
    "whisper_model": "base"  # whisper模型大小: tiny/base/small/medium/large
}

class MediaAnalyzer:
    """素材分析器"""
    
    def __init__(self, config: Dict = None):
        self.config = {**DEFAULT_CONFIG, **(config or {})}
        self.results = []
        
    def scan_directory(self, directory: str) -> List[Path]:
        """扫描目录下的所有媒体文件"""
        media_files = []
        directory = Path(directory)
        
        if not directory.exists():
            raise FileNotFoundError(f"目录不存在: {directory}")
        
        for ext in (self.config["supported_video"] + 
                    self.config["supported_audio"] + 
                    self.config["supported_image"]):
            media_files.extend(directory.rglob(f"*{ext}"))
            media_files.extend(directory.rglob(f"*{ext.upper()}"))
        
        return list(set(media_files))  # 去重
    
    def get_video_info(self, file_path: Path) -> Dict:
        """获取视频文件信息"""
        cmd = [
            self.config["ffmpeg_path"], "-i", str(file_path)
        ]
        
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, 
                stderr=subprocess.PIPE, timeout=30
            )
            output = result.stderr
            
            info = {
                "path": str(file_path),
                "name": file_path.name,
                "type": "video",
                "size": file_path.stat().st_size,
                "duration": self._extract_duration(output),
                "resolution": self._extract_resolution(output),
                "fps": self._extract_fps(output),
                "codec": self._extract_codec(output),
                "audio": self._has_audio(output)
            }
            return info
        except Exception as e:
            return {
                "path": str(file_path),
                "name": file_path.name,
                "type": "video",
                "error": str(e)
            }
    
    def get_image_info(self, file_path: Path) -> Dict:
        """获取图片文件信息"""
        return {
            "path": str(file_path),
            "name": file_path.name,
            "type": "image",
            "size": file_path.stat().st_size
        }
    
    def get_audio_info(self, file_path: Path) -> Dict:
        """获取音频文件信息"""
        return {
            "path": str(file_path),
            "name": file_path.name,
            "type": "audio",
            "size": file_path.stat().st_size
        }
    
    def _extract_duration(self, ffmpeg_output: str) -> Optional[float]:
        """从FFmpeg输出提取时长"""
        import re
        match = re.search(r"Duration: (\d{2}):(\d{2}):(\d{2})\.(\d{2})", ffmpeg_output)
        if match:
            h, m, s, cs = match.groups()
            return int(h) * 3600 + int(m) * 60 + int(s) + int(cs) / 100
        return None
    
    def _extract_resolution(self, ffmpeg_output: str) -> Optional[str]:
        """从FFmpeg输出提取分辨率"""
        import re
        match = re.search(r"(\d{3,4}x\d{3,4})", ffmpeg_output)
        return match.group(1) if match else None
    
    def _extract_fps(self, ffmpeg_output: str) -> Optional[float]:
        """从FFmpeg输出提取帧率"""
        import re
        match = re.search(r"(\d+(?:\.\d+)?)\s*fps", ffmpeg_output)
        return float(match.group(1)) if match else None
    
    def _extract_codec(self, ffmpeg_output: str) -> Optional[str]:
        """从FFmpeg输出提取编码器"""
        import re
        match = re.search(r"Video: (\w+)", ffmpeg_output)
        return match.group(1) if match else None
    
    def _has_audio(self, ffmpeg_output: str) -> bool:
        """检查是否有音频流"""
        return "Audio:" in ffmpeg_output
    
    def analyze(self, input_dir: str, output_dir: str = None) -> Dict:
        """执行素材分析"""
        print(f"[AI剪辑] 开始分析素材目录: {input_dir}")
        
        media_files = self.scan_directory(input_dir)
        print(f"[AI剪辑] 发现 {len(media_files)} 个媒体文件")
        
        results = {
            "analyze_time": datetime.now().isoformat(),
            "input_dir": input_dir,
            "total_files": len(media_files),
            "files": []
        }
        
        for i, file_path in enumerate(media_files, 1):
            print(f"[AI剪辑] 分析文件 {i}/{len(media_files)}: {file_path.name}")
            
            ext = file_path.suffix.lower()
            if ext in self.config["supported_video"]:
                info = self.get_video_info(file_path)
            elif ext in self.config["supported_image"]:
                info = self.get_image_info(file_path)
            else:
                info = self.get_audio_info(file_path)
            
            results["files"].append(info)
            
            # 分类统计
            if "type" in info:
                if info["type"] == "video":
                    results["video_count"] = results.get("video_count", 0) + 1
                elif info["type"] == "image":
                    results["image_count"] = results.get("image_count", 0) + 1
                elif info["type"] == "audio":
                    results["audio_count"] = results.get("audio_count", 0) + 1
        
        # 计算总时长
        total_duration = sum(
            f.get("duration", 0) for f in results["files"] 
            if f.get("type") == "video"
        )
        results["total_duration_seconds"] = total_duration
        results["total_duration_formatted"] = self._format_duration(total_duration)
        
        # 保存结果
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)
            output_file = os.path.join(output_dir, "media_analysis.json")
            with open(output_file, "w", encoding="utf-8") as f:
                json.dump(results, f, ensure_ascii=False, indent=2)
            print(f"[AI剪辑] 分析结果已保存: {output_file}")
        
        self.results = results
        return results
    
    def _format_duration(self, seconds: float) -> str:
        """格式化时长"""
        if seconds is None:
            return "未知"
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        if hours > 0:
            return f"{hours}小时{minutes}分钟{secs}秒"
        elif minutes > 0:
            return f"{minutes}分钟{secs}秒"
        else:
            return f"{secs}秒"
    
    def generate_report(self, results: Dict) -> str:
        """生成分析报告"""
        report = f"""
╔══════════════════════════════════════════════════════════════╗
║                    AI视频剪辑 - 素材分析报告                   ║
╠══════════════════════════════════════════════════════════════╣
║ 分析时间: {results['analyze_time']}
║ 素材目录: {results['input_dir']}
╠══════════════════════════════════════════════════════════════╣
║ 文件统计:
║   - 视频文件: {results.get('video_count', 0)} 个
║   - 图片文件: {results.get('image_count', 0)} 个
║   - 音频文件: {results.get('audio_count', 0)} 个
║   - 总  计: {results['total_files']} 个
║ 总时长: {results['total_duration_formatted']}
╠══════════════════════════════════════════════════════════════╣
║ 文件列表:
"""
        for i, f in enumerate(results["files"], 1):
            if f.get("type") == "video":
                duration = self._format_duration(f.get("duration", 0))
                resolution = f.get("resolution", "未知")
                report += f"║ {i}. [视频] {f['name']} ({resolution}, {duration})\n"
            elif f.get("type") == "image":
                size_kb = f.get("size", 0) // 1024
                report += f"║ {i}. [图片] {f['name']} ({size_kb}KB)\n"
            else:
                report += f"║ {i}. [音频] {f['name']}\n"
        
        report += "╚══════════════════════════════════════════════════════════════╝"
        return report


def main():
    """命令行入口"""
    import argparse
    
    parser = argparse.ArgumentParser(description="AI视频剪辑 - 素材分析")
    parser.add_argument("--input", "-i", required=True, help="素材输入目录")
    parser.add_argument("--output", "-o", help="分析结果输出目录")
    parser.add_argument("--config", "-c", help="配置文件路径")
    
    args = parser.parse_args()
    
    # 加载配置
    config = DEFAULT_CONFIG.copy()
    if args.config and os.path.exists(args.config):
        with open(args.config, "r", encoding="utf-8") as f:
            config.update(json.load(f))
    
    # 执行分析
    analyzer = MediaAnalyzer(config)
    results = analyzer.analyze(args.input, args.output)
    
    # 输出报告
    print(analyzer.generate_report(results))
    
    return results


if __name__ == "__main__":
    main()
