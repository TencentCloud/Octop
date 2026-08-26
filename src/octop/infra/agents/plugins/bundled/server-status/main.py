"""服务器状态 — 采集本机 OS / CPU / 内存 / 磁盘快照，供聊天 UI 渲染。"""

from __future__ import annotations

import json
import os
import platform
import socket
import time
from datetime import UTC, datetime
from typing import Any

import psutil
from harness_agent.plugins import PluginContext


def _bytes_human(n: int | float) -> str:
    value = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB", "PB"):
        if abs(value) < 1024.0:
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024.0
    return f"{value:.1f} EB"


def _pct(used: float | int, total: float | int) -> float:
    if not total:
        return 0.0
    return round(100.0 * float(used) / float(total), 1)


def _uptime_human(seconds: float) -> str:
    secs = max(0, int(seconds))
    days, rem = divmod(secs, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, _ = divmod(rem, 60)
    parts: list[str] = []
    if days:
        parts.append(f"{days} 天")
    if hours or days:
        parts.append(f"{hours} 小时")
    parts.append(f"{minutes} 分钟")
    return " ".join(parts)


def _collect() -> dict[str, Any]:
    # First call primes counters; second samples ~0.2s utilization.
    psutil.cpu_percent(interval=None)
    cpu_percent = float(psutil.cpu_percent(interval=0.2))
    cpu_count_logical = psutil.cpu_count(logical=True) or 0
    cpu_count_physical = psutil.cpu_count(logical=False) or cpu_count_logical
    freq = psutil.cpu_freq()

    vm = psutil.virtual_memory()
    swap = psutil.swap_memory()

    disk_path = os.path.abspath(os.sep)
    try:
        disk = psutil.disk_usage(disk_path)
    except Exception:
        disk_path = "/"
        disk = psutil.disk_usage(disk_path)

    boot_ts = float(psutil.boot_time())
    now = time.time()
    uname = platform.uname()

    load_avg: list[float] | None
    try:
        load_avg = [round(x, 2) for x in os.getloadavg()]
    except (AttributeError, OSError):
        load_avg = None

    return {
        "hostname": socket.gethostname(),
        "os": {
            "system": uname.system or platform.system(),
            "release": uname.release or platform.release(),
            "version": uname.version or platform.version(),
            "machine": uname.machine or platform.machine(),
            "pretty": f"{platform.system()} {platform.release()}",
        },
        "kernel": uname.release or platform.release(),
        "python": platform.python_version(),
        "cpu": {
            "percent": cpu_percent,
            "logical": cpu_count_logical,
            "physical": cpu_count_physical,
            "freq_mhz": round(freq.current, 0) if freq is not None else None,
        },
        "memory": {
            "total": int(vm.total),
            "used": int(vm.used),
            "available": int(vm.available),
            "percent": float(vm.percent),
            "total_h": _bytes_human(vm.total),
            "used_h": _bytes_human(vm.used),
            "available_h": _bytes_human(vm.available),
        },
        "swap": {
            "total": int(swap.total),
            "used": int(swap.used),
            "percent": float(swap.percent),
            "total_h": _bytes_human(swap.total),
            "used_h": _bytes_human(swap.used),
        },
        "disk": {
            "path": disk_path,
            "total": int(disk.total),
            "used": int(disk.used),
            "free": int(disk.free),
            "percent": _pct(disk.used, disk.total),
            "total_h": _bytes_human(disk.total),
            "used_h": _bytes_human(disk.used),
            "free_h": _bytes_human(disk.free),
        },
        "load_avg": load_avg,
        "boot_time": datetime.fromtimestamp(boot_ts, tz=UTC).isoformat(),
        "uptime_sec": int(now - boot_ts),
        "uptime_h": _uptime_human(now - boot_ts),
        "collected_at": datetime.now(tz=UTC).isoformat(),
    }


def _text_summary(data: dict[str, Any]) -> str:
    os_info = data["os"]
    cpu = data["cpu"]
    mem = data["memory"]
    disk = data["disk"]
    return (
        f"主机 {data['hostname']} · {os_info['pretty']} ({os_info['machine']})\n"
        f"内核 {data['kernel']} · 运行 {data['uptime_h']}\n"
        f"CPU {cpu['percent']:.0f}%（{cpu['logical']} 逻辑核）· "
        f"内存 {mem['percent']:.0f}%（{mem['used_h']} / {mem['total_h']}）· "
        f"磁盘 {disk['percent']:.0f}%（{disk['used_h']} / {disk['total_h']}）"
    )


async def get_server_status() -> str:
    """采集当前服务器操作系统、内核与 CPU/内存/磁盘负载，并在聊天中渲染状态卡片。"""
    data = _collect()
    payload = {
        "octop_ui": {"renderer": "server_status", "version": 1},
        "data": data,
        "text": _text_summary(data),
    }
    return json.dumps(payload, ensure_ascii=False)


def setup(ctx: PluginContext) -> None:
    ctx.tool(
        "get_server_status",
        get_server_status,
        description=(
            "查询当前 Octop 所在服务器的基本信息与资源负载："
            "操作系统、内核版本、主机名、运行时长，以及 CPU / 内存 / 磁盘使用率。"
            "在聊天中渲染可视化状态卡片。无需参数；需要最新数据时再次调用即可。"
        ),
    )
