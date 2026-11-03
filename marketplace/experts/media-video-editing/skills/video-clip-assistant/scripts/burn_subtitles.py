#!/usr/bin/env python3
"""Burn Subtitles — SRT字幕烧录到视频"""
import argparse, os, subprocess, shutil, sys

def burn_subtitles(input_file: str, srt_file: str, output: str,
                   font: str = "Arial", size: int = 24, color: str = "white") -> bool:
    """使用 FFmpeg 将 SRT 字幕烧录到视频。"""
    if not os.path.exists(srt_file):
        print(f"错误: 字幕文件不存在: {srt_file}", file=sys.stderr)
        return False

    # 检查字幕编码
    try:
        with open(srt_file, "r", encoding="utf-8") as f:
            f.read()
    except UnicodeDecodeError:
        # 尝试 GBK
        tmp = srt_file + ".utf8.srt"
        with open(srt_file, "r", encoding="gbk", errors="ignore") as src:
            content = src.read()
        with open(tmp, "w", encoding="utf-8") as dst:
            dst.write(content)
        srt_file = tmp

    # 使用 FFmpeg subtitles filter
    filter_str = (
        f"subtitles='{srt_file}':force_style="
        f"'FontName={font},FontSize={size},PrimaryColour=&H{color}&'"
    )
    cmd = [
        "ffmpeg", "-y",
        "-i", input_file,
        "-vf", filter_str,
        "-c:v", "libx264", "-preset", "fast",
        "-c:a", "aac",
        output
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0 and "Unable to parse option" in result.stderr:
        # fallback: 简化滤镜
        cmd = [
            "ffmpeg", "-y",
            "-i", input_file,
            "-vf", f"subtitles='{srt_file}'",
            "-c:v", "libx264", "-preset", "fast",
            "-c:a", "aac",
            output
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
    return result.returncode == 0

if __name__ == "__main__":
    p = argparse.ArgumentParser(description="烧录字幕到视频")
    p.add_argument("--input", required=True, help="输入视频")
    p.add_argument("--srt", required=True, help="SRT字幕文件")
    p.add_argument("--output", required=True, help="输出视频")
    p.add_argument("--font", default="Arial", help="字体")
    p.add_argument("--size", type=int, default=24, help="字号")
    p.add_argument("--color", default="white", help="颜色(white/yellow/cyan)")
    args = p.parse_args()

    import shutil as _sh
    if not _sh.which("ffmpeg"):
        print("错误: ffmpeg 未安装", file=sys.stderr)
        sys.exit(1)

    ok = burn_subtitles(args.input, args.srt, args.output,
                         args.font, args.size, args.color)
    print(f"结果: {'成功' if ok else '失败'}")
    if not ok:
        print("错误信息:", file=sys.stderr)
        sys.exit(1)
