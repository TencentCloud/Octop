"""nong_gateway：把 IM 通道（元宝 / Kimi）接到可插拔的头脑（pi / cli）。

原身是 yuanbao-bridge-py 的 ybb_core.py（589 项自检护着的业务层），2026-09-15 搬进
harness-gateway 自维护分支与 kimi 通道合成一处；octop 宿主路径已按决定删除。

- core.py：桥本体（闸序、群管、群记录、宿主接缝、角色/沙箱、出站媒体…）
- credentials.py：通道凭据收集（config.json 的 credentials[] / 单套 appKey+appSecret）
- hosts.py：宿主适配器（pi RPC / 任意 CLI），与 kimi-claw-py 同源
"""

from __future__ import annotations

__all__ = ["core", "credentials", "hosts"]
