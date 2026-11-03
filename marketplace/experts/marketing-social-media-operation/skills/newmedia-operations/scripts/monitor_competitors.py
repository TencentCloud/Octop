"""
竞品账号实时监测工具
用法：python monitor_competitors.py --accounts accounts.json --check_interval 24h
"""

import argparse
import json
import os
import sys
import time
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

# 所有爬虫脚本与本脚本同处 scripts/ 目录
SCRIPTS_DIR = Path(__file__).parent
SKILL_ROOT = SCRIPTS_DIR.parent

# 监测状态存储文件
MONITOR_STATE_FILE = SKILL_ROOT / "data" / "monitor_state.json"


def load_state() -> dict:
    """加载上次监测状态"""
    if MONITOR_STATE_FILE.exists():
        with open(MONITOR_STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"accounts": {}, "last_check": {}, "alerts": []}


def save_state(state: dict):
    """保存监测状态"""
    MONITOR_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(MONITOR_STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def fetch_account_latest(account: dict, platform: str) -> list:
    """抓取账号最新内容，调用同目录爬虫脚本"""
    script_map = {
        "douyin": SCRIPTS_DIR / "fetch_douyin.py",
        "xiaohongshu": SCRIPTS_DIR / "fetch_xiaohongshu.py",
        "wechat_video": SCRIPTS_DIR / "fetch_wechat_video.py",
    }

    script = script_map.get(platform)
    if not script or not script.exists():
        print(f"⚠️  {platform} 平台爬虫脚本未找到，跳过")
        return []

    try:
        result = subprocess.run(
            [sys.executable, str(script),
             "--account_id", account.get("id", ""),
             "--type", "recent",
             "--limit", "20",
             "--json"],
            capture_output=True, text=True, timeout=60
        )
        if result.returncode == 0:
            return json.loads(result.stdout)
    except (subprocess.TimeoutExpired, json.JSONDecodeError, Exception) as e:
        print(f"⚠️  抓取 {account.get('name')} 失败: {e}")

    return []


def detect_new_content(account_id: str, current_content: list, state: dict) -> list:
    """检测新增内容"""
    previous_ids = set(state.get("accounts", {}).get(account_id, {}).get("content_ids", []))
    current_ids = {item.get("id") for item in current_content if item.get("id")}

    new_ids = current_ids - previous_ids
    new_items = [item for item in current_content if item.get("id") in new_ids]

    return new_items


def detect_viral_content(content_list: list, threshold: int = 100000) -> list:
    """检测爆款内容（播放量超过阈值）"""
    return [
        item for item in content_list
        if item.get("play_count", 0) >= threshold
    ]


def analyze_new_comments(account: dict, platform: str, content_id: str) -> dict:
    """分析新内容的评论，提取需求和痛点"""
    script = SCRIPTS_DIR / "extract_demands.py"
    if not script.exists():
        return {}

    try:
        result = subprocess.run(
            [sys.executable, str(script),
             "--platform", platform,
             "--content_id", content_id,
             "--json"],
            capture_output=True, text=True, timeout=60
        )
        if result.returncode == 0:
            return json.loads(result.stdout)
    except Exception:
        pass

    return {}


def generate_alert(account: dict, alert_type: str, data: dict) -> dict:
    """生成监测警报"""
    return {
        "timestamp": datetime.now().isoformat(),
        "account_name": account.get("name"),
        "account_id": account.get("id"),
        "platform": account.get("platform"),
        "alert_type": alert_type,  # new_content / viral_detected / demand_spike
        "data": data
    }


def format_alert_message(alert: dict) -> str:
    """格式化警报消息"""
    timestamp = alert["timestamp"][:16].replace("T", " ")

    if alert["alert_type"] == "new_content":
        items = alert["data"].get("items", [])
        msg = [f"📢 [{timestamp}] 竞品更新提醒"]
        msg.append(f"账号：{alert['account_name']} ({alert['platform']})")
        msg.append(f"新增内容：{len(items)} 条")
        for item in items[:3]:
            msg.append(f"  • {item.get('title', '无标题')} | 播放: {item.get('play_count', 0):,}")

    elif alert["alert_type"] == "viral_detected":
        item = alert["data"]
        msg = [f"🔥 [{timestamp}] 爆款内容提醒"]
        msg.append(f"账号：{alert['account_name']} ({alert['platform']})")
        msg.append(f"标题：{item.get('title', '无标题')}")
        msg.append(f"播放量：{item.get('play_count', 0):,}")
        msg.append(f"链接：{item.get('url', 'N/A')}")

    else:
        msg = [f"📊 [{timestamp}] 监测警报: {alert['alert_type']}"]
        msg.append(f"账号：{alert['account_name']} ({alert['platform']})")

    return "\n".join(msg)


def run_monitor_once(accounts: list, viral_threshold: int, state: dict) -> tuple[dict, list]:
    """执行一次监测"""
    alerts = []

    for account in accounts:
        platform = account.get("platform", "douyin")
        account_id = account.get("id")
        account_name = account.get("name", account_id)

        print(f"正在检测: {account_name} ({platform})...")

        current_content = fetch_account_latest(account, platform)

        if not current_content:
            print(f"  → 未获取到内容，跳过")
            continue

        # 检测新增内容
        new_items = detect_new_content(account_id, current_content, state)
        if new_items:
            alert = generate_alert(account, "new_content", {"items": new_items})
            alerts.append(alert)
            print(f"  → 发现 {len(new_items)} 条新内容")

        # 检测爆款
        viral_items = detect_viral_content(current_content, viral_threshold)
        for item in viral_items:
            item_id = item.get("id")
            # 避免重复报警
            prev_viral = state.get("accounts", {}).get(account_id, {}).get("viral_ids", [])
            if item_id not in prev_viral:
                alert = generate_alert(account, "viral_detected", item)
                alerts.append(alert)
                print(f"  → 爆款: {item.get('title', '')} ({item.get('play_count', 0):,} 播放)")

        # 更新状态
        if account_id not in state["accounts"]:
            state["accounts"][account_id] = {}

        state["accounts"][account_id].update({
            "content_ids": [item.get("id") for item in current_content],
            "viral_ids": [item.get("id") for item in viral_items],
            "last_check": datetime.now().isoformat(),
            "last_count": len(current_content)
        })

    state["last_check"]["timestamp"] = datetime.now().isoformat()
    state["alerts"].extend(alerts)

    # 只保留最近100条警报
    state["alerts"] = state["alerts"][-100:]

    return state, alerts


def main():
    parser = argparse.ArgumentParser(description="竞品账号实时监测工具")
    parser.add_argument("--accounts", type=str, required=True,
                        help="账号配置文件路径（JSON格式）")
    parser.add_argument("--check_interval", type=str, default="24h",
                        help="检测间隔，如 1h / 6h / 24h")
    parser.add_argument("--alert_threshold", type=int, default=100000,
                        help="爆款播放量阈值")
    parser.add_argument("--once", action="store_true",
                        help="只执行一次检测")
    parser.add_argument("--report", action="store_true",
                        help="输出监测报告")

    args = parser.parse_args()

    # 解析时间间隔
    interval_map = {"h": 3600, "m": 60, "d": 86400}
    interval_str = args.check_interval.lower()
    interval_seconds = int(interval_str[:-1]) * interval_map.get(interval_str[-1], 3600)

    # 加载账号配置
    with open(args.accounts, "r", encoding="utf-8") as f:
        accounts = json.load(f)

    if isinstance(accounts, dict):
        accounts = accounts.get("accounts", [])

    print(f"加载了 {len(accounts)} 个监测账号")
    print(f"检测间隔: {args.check_interval}")
    print(f"爆款阈值: {args.alert_threshold:,} 播放")
    print("-" * 40)

    state = load_state()

    if args.report:
        # 输出已有警报报告
        print(f"\n=== 监测报告 ===")
        recent_alerts = state.get("alerts", [])[-20:]
        for alert in recent_alerts:
            print(format_alert_message(alert))
            print()
        return

    while True:
        print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 开始检测...")
        state, new_alerts = run_monitor_once(accounts, args.alert_threshold, state)
        save_state(state)

        if new_alerts:
            print(f"\n{'='*40}")
            print(f"发现 {len(new_alerts)} 条警报：")
            for alert in new_alerts:
                print(format_alert_message(alert))
                print()
        else:
            print("未发现新动态")

        if args.once:
            break

        print(f"\n下次检测时间: {(datetime.now() + timedelta(seconds=interval_seconds)).strftime('%Y-%m-%d %H:%M:%S')}")
        time.sleep(interval_seconds)


if __name__ == "__main__":
    main()
