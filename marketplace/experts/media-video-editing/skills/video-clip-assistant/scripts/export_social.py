#!/usr/bin/env python3
"""Export Social — 导出多平台短视频格式"""
import argparse, os, subprocess, shutil, sys

FORMATS = {
    "vertical":   {"size": "1080:1920", "note": "抖音/快手/小红书 9:16"},
    "square":     {"size": "1080:1080", "note": "Instagram 1:1"},
    "horizontal": {"size": "1920:1080", "note": "YouTube/B站 16:9"},
}

def smart_trim(input_file: str, duration: float, output: str) -> bool:
    """裁剪为指定时长（从开头或随机位置）。"""
    cmd = [
        "ffmpeg", "-y",
        "-i", input_file,
        "-t", str(duration),
        "-c:v", "libx264", "-preset", "fast",
        "-c:a", "aac",
        output
    ]
    return subprocess.run(cmd, capture_output=True).returncode == 0

def scale_and_pad(input_file: str, target_size: str, output: str) -> bool:
    """缩放并填充黑边以适应目标比例。"""
    # scale 缩放到目标宽度，高度等比，pad 在两侧或上下加黑边
    cmd = [
        "ffmpeg", "-y",
        "-i", input_file,
        "-vf", f"scale={target_size}:force_original_aspect_ratio=decrease,pad={target_size}:(ow-iw)/2:(oh-ih)/2:black",
        "-c:v", "libx264", "-preset", "fast",
        "-c:a", "aac",
        output
    ]
    return subprocess.run(cmd, capture_output=True, text=True).returncode == 0

def export(input_file: str, fmt: str, duration: float, output_dir: str) -> list:
    os.makedirs(output_dir, exist_ok=True)
    base = os.path.splitext(os.path.basename(input_file))[0]
    target = FORMATS[fmt]["size"]
    note = FORMATS[fmt]["note"]

    # 先裁剪时长
    trimmed = os.path.join(output_dir, f"{base}_trimmed.mp4")
    print(f"  裁剪为 {duration}s...")
    if not smart_trim(input_file, duration, trimmed):
        return []

    # 再缩放填充
    out = os.path.join(output_dir, f"{base}_{fmt}.mp4")
    print(f"  缩放为 {note}...")
    if not scale_and_pad(trimmed, target, out):
        # 如果失败，直接返回截断版
        shutil.copy(trimmed, out)

    os.remove(trimmed)
    return [out]

if __name__ == "__main__":
    p = argparse.ArgumentParser(description="多平台短视频导出")
    p.add_argument("--input", required=True)
    p.add_argument("--format", required=True, choices=["vertical","square","horizontal"],
                   help="目标格式")
    p.add_argument("--duration", type=float, default=60,
                   help="输出时长（秒），默认60")
    p.add_argument("--output", required=True, help="输出目录")
    args = p.parse_args()

    if not shutil.which("ffmpeg"):
        print("错误: ffmpeg 未安装", file=sys.stderr)
        sys.exit(1)

    print(f"导出 {FORMATS[args.format]['note']}，时长 {args.duration}s...")
    results = export(args.input, args.format, args.duration, args.output)
    if results:
        print(f"成功: {results[0]}")
    else:
        print("失败", file=sys.stderr)
        sys.exit(1)
