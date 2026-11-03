#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI视频剪辑 - 全自动剪辑流程
功能：整合所有模块，实现从素材到成片的全流程自动化
"""

import os
import json
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional

# 导入各模块
from analyze_media import MediaAnalyzer
from auto_clip import AutoClipper
from add_subtitles import SubtitleGenerator
from audio_process import AudioProcessor
from add_effects import EffectsProcessor
from export_final import VideoExporter

DEFAULT_CONFIG = {
    # 素材配置
    "input_dir": "",
    "theme": "auto",
    
    # 输出配置
    "output_dir": "",
    "storage_path": "",
    
    # 剪辑配置
    "target_duration": 180,
    "style": "auto",
    "transition": "fade",
    
    # 音频配置
    "bgm_enabled": True,
    "bgm_path": "",
    "bgm_volume": 0.3,
    "voice_volume": 1.0,
    "noise_reduction": True,
    "enhance_voice": True,
    
    # 字幕配置
    "subtitle_enabled": True,
    "subtitle_language": "zh",
    "subtitle_burn": True,
    
    # 特效配置
    "filter": "auto",
    "effects": [],
    
    # 导出配置
    "export_preset": "high",
    "export_format": "mp4",
    "export_resolution": "",
    
    # 高级配置
    "auto_cleanup": True,
    "generate_preview": False
}

class VideoPipeline:
    """全自动视频剪辑流程"""
    
    def __init__(self, config: Dict = None):
        self.config = {**DEFAULT_CONFIG, **(config or {})}
        self.workspace = None
        self.analysis_file = None
        self.current_file = None
        
        # 初始化各模块
        self.media_analyzer = MediaAnalyzer()
        self.clipper = AutoClipper()
        self.subtitle_generator = SubtitleGenerator()
        self.audio_processor = AudioProcessor()
        self.effects_processor = EffectsProcessor()
        self.exporter = VideoExporter()
        
    def setup_workspace(self) -> str:
        """创建工作空间"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        workspace_name = f"clip_{timestamp}"
        
        self.workspace = os.path.join(
            self.config["output_dir"] or os.path.expanduser("~"),
            "AI视频剪辑",
            workspace_name
        )
        
        os.makedirs(self.workspace, exist_ok=True)
        os.makedirs(os.path.join(self.workspace, "素材分析"), exist_ok=True)
        os.makedirs(os.path.join(self.workspace, "中间文件"), exist_ok=True)
        os.makedirs(os.path.join(self.workspace, "成品"), exist_ok=True)
        
        print(f"[流程] 工作空间: {self.workspace}")
        return self.workspace
    
    def step_analyze(self) -> Dict:
        """Step 1: 素材分析"""
        print(f"\n{'='*50}")
        print(f"[流程 Step 1/6] 素材分析")
        print(f"{'='*50}")
        
        input_dir = self.config["input_dir"]
        if not input_dir or not os.path.exists(input_dir):
            raise FileNotFoundError(f"素材目录不存在: {input_dir}")
        
        analysis_dir = os.path.join(self.workspace, "素材分析")
        results = self.media_analyzer.analyze(input_dir, analysis_dir)
        
        self.analysis_file = os.path.join(analysis_dir, "media_analysis.json")
        self.current_file = None
        
        print(f"[流程] 分析完成: {results['total_files']} 个文件, {results.get('total_duration_formatted', '未知')} 总时长")
        
        return results
    
    def step_clip(self) -> str:
        """Step 2: 自动剪辑"""
        print(f"\n{'='*50}")
        print(f"[流程 Step 2/6] 自动剪辑")
        print(f"{'='*50}")
        
        if not self.analysis_file:
            raise RuntimeError("请先执行素材分析")
        
        clip_dir = os.path.join(self.workspace, "中间文件")
        
        clip_config = {
            "target_duration": self.config["target_duration"],
            "style": self.config["style"],
            "transition": self.config["transition"],
            "voice_volume": self.config["voice_volume"]
        }
        
        self.clipper.config.update(clip_config)
        self.current_file = self.clipper.clip(self.analysis_file, clip_dir)
        
        print(f"[流程] 剪辑完成: {self.current_file}")
        return self.current_file
    
    def step_audio(self) -> str:
        """Step 3: 音频处理"""
        print(f"\n{'='*50}")
        print(f"[流程 Step 3/6] 音频处理")
        print(f"{'='*50}")
        
        if not self.current_file:
            raise RuntimeError("请先执行剪辑")
        
        audio_dir = os.path.join(self.workspace, "中间文件")
        
        audio_config = {
            "bgm_enabled": self.config["bgm_enabled"],
            "bgm_path": self.config["bgm_path"],
            "bgm_volume": self.config["bgm_volume"],
            "voice_volume": self.config["voice_volume"],
            "noise_reduction": self.config["noise_reduction"],
            "enhance_voice": self.config["enhance_voice"]
        }
        
        self.audio_processor.config.update(audio_config)
        self.current_file = self.audio_processor.process(self.current_file, audio_dir)
        
        print(f"[流程] 音频处理完成: {self.current_file}")
        return self.current_file
    
    def step_subtitle(self) -> str:
        """Step 4: 字幕生成"""
        print(f"\n{'='*50}")
        print(f"[流程 Step 4/6] 字幕生成")
        print(f"{'='*50}")
        
        if not self.current_file:
            raise RuntimeError("请先执行剪辑")
        
        if not self.config["subtitle_enabled"]:
            print("[流程] 字幕功能已禁用，跳过")
            return self.current_file
        
        subtitle_dir = os.path.join(self.workspace, "中间文件")
        
        subtitle_config = {
            "language": self.config["subtitle_language"]
        }
        
        self.subtitle_generator.config.update(subtitle_config)
        self.current_file = self.subtitle_generator.generate(self.current_file, subtitle_dir)
        
        print(f"[流程] 字幕生成完成: {self.current_file}")
        return self.current_file
    
    def step_effects(self) -> str:
        """Step 5: 特效处理"""
        print(f"\n{'='*50}")
        print(f"[流程 Step 5/6] 特效处理")
        print(f"{'='*50}")
        
        if not self.current_file:
            raise RuntimeError("请先执行剪辑")
        
        effects_dir = os.path.join(self.workspace, "中间文件")
        
        effects_config = {
            "filter": self.config["filter"],
            "effects": self.config["effects"]
        }
        
        self.effects_processor.config.update(effects_config)
        self.current_file = self.effects_processor.process(self.current_file, effects_dir)
        
        print(f"[流程] 特效处理完成: {self.current_file}")
        return self.current_file
    
    def step_export(self) -> str:
        """Step 6: 成品导出"""
        print(f"\n{'='*50}")
        print(f"[流程 Step 6/6] 成品导出")
        print(f"{'='*50}")
        
        if not self.current_file:
            raise RuntimeError("请先执行剪辑")
        
        export_dir = os.path.join(self.workspace, "成品")
        storage_path = self.config["storage_path"] or export_dir
        
        export_config = {
            "preset": self.config["export_preset"],
            "format": self.config["export_format"],
            "resolution": self.config["export_resolution"],
            "storage_path": storage_path,
            "naming": "{date}_{theme}_{duration}"
        }
        
        self.exporter.config.update(export_config)
        final_file = self.exporter.export(
            self.current_file, 
            theme=self.config["theme"] or "video"
        )
        
        print(f"[流程] 成品导出完成: {final_file}")
        return final_file
    
    def cleanup(self):
        """清理临时文件"""
        if not self.config["auto_cleanup"]:
            return
        
        print("[流程] 正在清理临时文件...")
        
        temp_dir = os.path.join(self.workspace, "中间文件")
        if os.path.exists(temp_dir):
            for f in os.listdir(temp_dir):
                try:
                    os.remove(os.path.join(temp_dir, f))
                except:
                    pass
    
    def run(self) -> str:
        """执行完整流程"""
        print(f"\n{'#'*60}")
        print(f"#")
        print(f"#   AI视频剪辑 - 全自动剪辑流程")
        print(f"#")
        print(f"{'#'*60}")
        print(f"\n开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"配置信息:")
        print(f"  - 素材目录: {self.config['input_dir']}")
        print(f"  - 目标时长: {self.config['target_duration']}秒")
        print(f"  - 剪辑风格: {self.config['style']}")
        print(f"  - 背景音乐: {'启用' if self.config['bgm_enabled'] else '禁用'}")
        print(f"  - 字幕生成: {'启用' if self.config['subtitle_enabled'] else '禁用'}")
        print(f"  - 滤镜预设: {self.config['filter']}")
        
        try:
            # 1. 创建工作空间
            self.setup_workspace()
            
            # 2. 执行各步骤
            self.step_analyze()
            self.step_clip()
            self.step_audio()
            self.step_subtitle()
            self.step_effects()
            final_file = self.step_export()
            
            # 3. 清理
            self.cleanup()
            
            print(f"\n{'#'*60}")
            print(f"#")
            print(f"#   剪辑完成!")
            print(f"#")
            print(f"#   成品文件: {final_file}")
            print(f"#")
            print(f"{'#'*60}")
            print(f"\n完成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            
            return final_file
            
        except Exception as e:
            print(f"\n[流程] 错误: {str(e)}")
            raise


def main():
    """命令行入口"""
    import argparse
    
    parser = argparse.ArgumentParser(description="AI视频剪辑 - 全自动流程")
    parser.add_argument("--input", "-i", required=True, help="素材目录")
    parser.add_argument("--output", "-o", help="输出目录")
    parser.add_argument("--duration", "-d", type=int, default=180, help="目标时长(秒)")
    parser.add_argument("--style", "-s", default="auto", choices=["auto", "quick", "slow", "narrative"], help="剪辑风格")
    parser.add_argument("--transition", "-t", default="fade", choices=["fade", "dissolve", "cut", "flash"], help="转场效果")
    parser.add_argument("--bgm", help="背景音乐目录")
    parser.add_argument("--no-bgm", action="store_true", help="禁用背景音乐")
    parser.add_argument("--no-subtitle", action="store_true", help="禁用字幕")
    parser.add_argument("--filter", "-f", default="auto", help="滤镜预设")
    parser.add_argument("--preset", "-p", default="high", choices=["high", "medium", "low"], help="导出预设")
    parser.add_argument("--config", "-c", help="配置文件路径")
    
    args = parser.parse_args()
    
    # 加载配置
    config = DEFAULT_CONFIG.copy()
    config["input_dir"] = args.input
    config["output_dir"] = args.output or os.path.dirname(args.input)
    config["target_duration"] = args.duration
    config["style"] = args.style
    config["transition"] = args.transition
    config["bgm_enabled"] = not args.no_bgm
    config["bgm_path"] = args.bgm or ""
    config["subtitle_enabled"] = not args.no_subtitle
    config["filter"] = args.filter
    config["export_preset"] = args.preset
    
    if args.config and os.path.exists(args.config):
        with open(args.config, "r", encoding="utf-8") as f:
            config.update(json.load(f))
    
    # 执行流程
    pipeline = VideoPipeline(config)
    output_file = pipeline.run()
    
    print(f"\n最终成品: {output_file}")


if __name__ == "__main__":
    main()
