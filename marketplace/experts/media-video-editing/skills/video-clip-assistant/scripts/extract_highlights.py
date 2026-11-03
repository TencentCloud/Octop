#!/usr/bin/env python3
"""Extract Highlights — 视频精华片段提取"""
import argparse, os, subprocess, shutil, sys, json
from datetime import datetime

def get_video_info(input_file: str) -> dict:
    """使用 ffprobe 获取视频信息。"""
    cmd = [
        "ffprobe", "-v", "quiet", "-print_format", "json",
        "-show_format", "-show_streams", input_file
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        return {}
    try:
        data = json.loads(result.stdout)
        duration = float(data.get("format", {}).get("duration", 0))
        width = height = 0
        for s in data.get("streams", []):
            if s.get("codec_type") == "video":
                width = s.get("width", 0)
                height = s.get("height", 0)
                break
        return {"duration": duration, "width": width, "height": height}
    except:
        return {}

def detect_scenes(input_file: str, threshold: float = 30.0) -> list:
    """使用 FFmpeg scene detection 检测场景切换点。"""
    cmd = [
        "ffmpeg", "-y", "-i", input_file,
        "-vf", f"select='gt(scene,{1/threshold})',showinfo",
        "-f", "null", "-"
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    scenes = []
    for line in result.stderr.splitlines():
        if "pts_time" in line:
            try:
                ts = line.split("pts_time:")[1].split()[0]
                scenes.append(float(ts))
            except:
                pass
    return scenes

def extract_clip(input_file: str, start: float, duration: float, output: str) -> bool:
    cmd = [
        "ffmpeg", "-y", "-ss", str(start), "-i", input_file,
        "-t", str(duration), "-c:v", "libx264", "-preset", "fast",
        "-c:a", "aac", "-avoid_negative_ts", "make_zero", output
    ]
    return subprocess.run(cmd, capture_output=True).returncode == 0

def extract_highlights(input_file: str, num_clips: int, min_duration: float,
                       output_dir: str) -> list:
    os.makedirs(output_dir, exist_ok=True)
    info = get_video_info(input_file)
    duration = info.get("duration", 0)
    print(f"视频时长: {duration:.1f}s, 分辨率: {info.get('width',0)}x{info.get('height',0)}")
    print("检测场景切换点...")
    scenes = detect_scenes(input_file)
    print(f"发现 {len(scenes)} 个场景切换点")

    if not scenes:
        # 无场景检测结果：均匀分段
        scenes = [i * duration / (num_clips + 1) for i in range(1, num_clips + 1)]

    # 过滤距离太近的
    filtered = []
    last = -999
    for s in scenes:
        if s - last >= min_duration:
            filtered.append(s)
            last = s

    # 取前 num_clips 个
    clips = filtered[:num_clips]
    base = os.path.splitext(os.path.basename(input_file))[0]
    results = []
    for i, start in enumerate(clips):
        out = os.path.join(output_dir, f"{base}_highlight{i+1}.mp4")
        ok = extract_clip(input_file, start, min_duration, out)
        results.append((out, start, ok))
        print(f"  片段{i+1}: {start:.1f}s -> {out} [{'OK' if ok else 'FAIL'}]")
    return results

if __name__ == "__main__":
    p = argparse.ArgumentParser(description="视频精华片段提取")
    p.add_argument("--input", required=True)
    p.add_argument("--num-clips", type=int, default=3, help="提取片段数量")
    p.add_argument("--min-duration", type=float, default=30, help="每个片段最小秒数")
    p.add_argument("--output", required=True, help="输出目录")
    p.add_argument("--threshold", type=float, default=30.0, help="场景检测灵敏度(越高越灵敏)")
    args = p.parse_args()

    if not shutil.which("ffmpeg"):
        print("错误: ffmpeg 未安装", file=sys.stderr)
        sys.exit(1)

    print(f"从 {args.input} 提取 {args.num_clips} 个精华片段...")
    results = extract_highlights(args.input, args.num_clips,
                                  args.min_duration, args.output)
    ok = sum(1 for r in results if r[2])
    print(f"\n完成: {ok}/{len(results)} 成功")
