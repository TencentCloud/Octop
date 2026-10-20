---
name: findmy
description: "Track Apple devices/AirTags via FindMy.app on macOS."
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

# Find My (Apple)

## Harness-agent tools

This skill was ported from Octop. Use these harness/deepagents tools:

| Concept | Tool |
|---------|------|
| Shell | `execute` |
| Read / write / edit files | `read_file`, `write_file`, `edit_file` |
| Find files / search content | `glob`, `grep` |
| Fetch URLs | `web_fetch` |
| Browser automation | `browser_use` |
| Subagent work | `task` |
| Memory | `memory_store`, `memory_recall`, `memory_search` |

Builtin skill files live under `/_builtin_skills/<name>/`. User-installed skills live under `/skills/<name>/`.

Track Apple devices and AirTags via the FindMy.app on macOS. Since Apple doesn't
provide a CLI for FindMy, this skill uses AppleScript to open the app and
screen capture to read device locations.

## Prerequisites

- **macOS** with Find My app and iCloud signed in
- Devices/AirTags already registered in Find My
- Screen Recording permission for terminal (System Settings → Privacy → Screen Recording)
- **Optional but recommended**: Install `peekaboo` for better UI automation:
  `brew install steipete/tap/peekaboo`

## When to Use

- User asks "where is my [device/cat/keys/bag]?"
- Tracking AirTag locations
- Checking device locations (iPhone, iPad, Mac, AirPods)
- Monitoring pet or item movement over time (AirTag patrol routes)

## Method 1: AppleScript + Screenshot (Basic)

### Open FindMy and Navigate

```bash
# Open Find My app
osascript -e 'tell application "FindMy" to activate'

# Wait for it to load
sleep 3

# Take a screenshot of the Find My window
screencapture -w -o /tmp/findmy.png
```

Then use `read_file` on the screenshot path (requires a multimodal model configured):

```
read_file("/tmp/findmy.png")
```

Describe devices and locations from the image content in your reply.

### Switch Between Tabs

```bash
# Switch to Devices tab
osascript -e '
tell application "System Events"
    tell process "FindMy"
        click button "Devices" of toolbar 1 of window 1
    end tell
end tell'

# Switch to Items tab (AirTags)
osascript -e '
tell application "System Events"
    tell process "FindMy"
        click button "Items" of toolbar 1 of window 1
    end tell
end tell'
```

## Method 2: Peekaboo UI Automation (Recommended)

If `peekaboo` is installed, use it for more reliable UI interaction:

```bash
# Open Find My
osascript -e 'tell application "FindMy" to activate'
sleep 3

# Capture and annotate the UI
peekaboo see --app "FindMy" --annotate --path /tmp/findmy-ui.png

# Click on a specific device/item by element ID
peekaboo click --on B3 --app "FindMy"

# Capture the detail view
peekaboo image --app "FindMy" --path /tmp/findmy-detail.png
```

Then analyze with vision:
```
read_file(image_url="/tmp/findmy-detail.png", question="What is the location shown for this device/item? Include address and coordinates if visible.")
```

## Workflow: Track AirTag Location Over Time

For monitoring an AirTag (e.g., tracking a cat's patrol route):

```bash
# 1. Open FindMy to Items tab
osascript -e 'tell application "FindMy" to activate'
sleep 3

# 2. Click on the AirTag item (stay on page — AirTag only updates when page is open)

# 3. Periodically capture location
while true; do
    screencapture -w -o /tmp/findmy-$(date +%H%M%S).png
    sleep 300  # Every 5 minutes
done
```

Analyze each screenshot with vision to extract coordinates, then compile a route.

## Limitations

- FindMy has **no CLI or API** — must use UI automation
- AirTags only update location while the FindMy page is actively displayed
- Location accuracy depends on nearby Apple devices in the FindMy network
- Screen Recording permission required for screenshots
- AppleScript UI automation may break across macOS versions

## Rules

1. Keep FindMy app in the foreground when tracking AirTags (updates stop when minimized)
2. Use `read_file` to read screenshot content — don't try to parse pixels
3. For ongoing tracking, use a cronjob to periodically capture and log locations
4. Respect privacy — only track devices/items the user owns
