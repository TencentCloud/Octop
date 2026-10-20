---
name: findmy
description: "通过 macOS 上的 FindMy.app 追踪 Apple 设备/AirTag。"
version: 1.0.0
author: Octop
license: MIT
compatibility: macos only
metadata:
  octop:
    label:
      zh: "查找设备"
      en: "Find My"
    summary:
      zh: "在 macOS 上追踪 Apple 设备与 AirTag。"
      en: "Track Apple devices and AirTags from Find My on macOS."
  harness:
    emoji: "📍"
    tags: [FindMy, AirTag, location, tracking, macOS, Apple]
---

# Find My（Apple）

## Harness-agent 工具

本技能从 Octop 移植。使用以下 harness/deepagents 工具：

| 概念 | 工具 |
|---------|------|
| Shell | `execute` |
| 读/写/编辑文件 | `read_file`, `write_file`, `edit_file` |
| 查找文件/搜索内容 | `glob`, `grep` |
| 获取 URL | `web_fetch` |
| 浏览器自动化 | `browser_use` |
| 子代理工作 | `task` |
| 记忆 | `memory_store`, `memory_recall`, `memory_search` |

内置技能文件位于 `/_builtin_skills/<name>/`。用户安装的技能位于 `/skills/<name>/`。

通过 macOS 上的 FindMy.app 追踪 Apple 设备和 AirTag。由于 Apple 没有为 FindMy 提供 CLI，本技能使用 AppleScript 打开应用并截图读取设备位置。

## 先决条件

- **macOS** 带 Find My 应用并已登录 iCloud
- 设备/AirTag 已在 Find My 中注册
- 终端的屏幕录制权限（系统设置 → 隐私 → 屏幕录制）
- **可选但推荐**：安装 `peekaboo` 以获得更好的 UI 自动化：
  `brew install steipete/tap/peekaboo`

## 何时使用

- 用户询问"我的 [设备/猫/钥匙/包] 在哪里？"
- 追踪 AirTag 位置
- 检查设备位置（iPhone、iPad、Mac、AirPods）
- 随时间监控宠物或物品移动（AirTag 巡逻路线）

## 方法 1：AppleScript + 截图（基本）

### 打开 FindMy 并导航

```bash
# 打开 Find My 应用
osascript -e 'tell application "FindMy" to activate'

# 等待加载
sleep 3

# 截取 Find My 窗口的截图
screencapture -w -o /tmp/findmy.png
```

然后使用 `read_file` 读取截图路径（需要配置多模态模型）：

```
read_file("/tmp/findmy.png")
```

在回复中描述图像内容中的设备和位置。

### 切换标签页

```bash
# 切换到设备标签
osascript -e '
tell application "System Events"
    tell process "FindMy"
        click button "Devices" of toolbar 1 of window 1
    end tell
end tell'

# 切换到物品标签（AirTag）
osascript -e '
tell application "System Events"
    tell process "FindMy"
        click button "Items" of toolbar 1 of window 1
    end tell
end tell'
```

## 方法 2：Peekaboo UI 自动化（推荐）

如果已安装 `peekaboo`，使用它进行更可靠的 UI 交互：

```bash
# 打开 Find My
osascript -e 'tell application "FindMy" to activate'
sleep 3

# 捕获并注释 UI
peekaboo see --app "FindMy" --annotate --path /tmp/findmy-ui.png

# 通过元素 ID 点击特定设备/物品
peekaboo click --on B3 --app "FindMy"

# 捕获详细视图
peekaboo image --app "FindMy" --path /tmp/findmy-detail.png
```

然后使用视觉分析：

```
read_file(image_url="/tmp/findmy-detail.png", question="此设备/物品显示的位置是什么？如果可见，包括地址和坐标。")
```

## 工作流：随时间追踪 AirTag 位置

对于监控 AirTag（例如，追踪猫的巡逻路线）：

```bash
# 1. 打开 FindMy 到物品标签
osascript -e 'tell application "FindMy" to activate'
sleep 3

# 2. 点击 AirTag 物品（保持页面打开——AirTag 仅在页面打开时更新）

# 3. 定期捕获位置
while true; do
    screencapture -w -o /tmp/findmy-$(date +%H%M%S).png
    sleep 300  # 每 5 分钟
done
```

使用视觉分析每个截图以提取坐标，然后编译路线。

## 限制

- FindMy **没有 CLI 或 API**——必须使用 UI 自动化
- AirTag 仅在 FindMy 页面主动显示时更新位置
- 位置准确性取决于 FindMy 网络中附近的 Apple 设备
- 截图需要屏幕录制权限
- AppleScript UI 自动化可能在不同 macOS 版本间中断

## 规则

1. 追踪 AirTag 时保持 FindMy 应用在前台（最小化时更新停止）
2. 使用 `read_file` 读取截图内容——不要尝试解析像素
3. 对于持续追踪，使用 cronjob 定期捕获并记录位置
4. 尊重隐私——只追踪用户拥有的设备/物品
