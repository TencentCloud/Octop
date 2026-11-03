# 内容捕手 (Content Hunter)

短视频平台热门内容抓取机器人 🤖

## 功能特性

- 🔍 **多平台抓取**：小红书、抖音、B站 3大平台
- 📊 **热门内容**：自动抓取各平台热门内容
- 📝 **内容总结**：自动生成内容摘要
- ⏰ **定时汇报**：可配置时间自动生成汇报
- 🔄 **历史存档**：按日期存储，不覆盖历史数据
- ⚙️ **灵活配置**：可自定义抓取数量和汇报时间

## 支持平台

| 平台 | 状态 |
|------|------|
| 小红书 | ✅ |
| 抖音 | ✅ |
| B站 | ✅ |

## 安装

```bash
# 通过 ClawHub 安装
clawhub install content-hunter

# 或克隆仓库
git clone https://github.com/judefluen-coder/content-hunter.git
```

## 使用方法

### 手动触发

```
"帮我刷短视频平台"
"抓取热门内容"
"生成内容汇报"
"每个平台抓取30条"
"下午6点汇报"
```

### 定时任务（推荐）

```bash
# 按需设置抓取频率和汇报时间
openclaw cron add --name "内容捕手-抓取" --cron "*/30 9-20 * * *" --session isolated --message "请执行内容捕手抓取"

# 设置汇报时间
openclaw cron add --name "内容捕手-汇报" --cron "0 18 * * *" --session isolated --message "请执行内容捕手汇报"
```

## 汇报示例

```
📊 2026年3月11日 内容捕手汇报

🔥 热门内容TOP20
【小红书】
1. 标题 → 热度 | 内容总结
...

📈 各平台趋势总结
- 小红书：xxx
- 抖音：xxx
...

🐸 呱呱感悟
xxx
```

## 数据存储

```
~/.openclaw/workspace/content-hunter/
└── task-2026-03-11-2000/
    ├── xiaohongshu.md
    ├── douyin.md
    ├── bilibili.md
    └── summary.md
```

## 依赖

- OpenClaw 浏览器控制服务
- bilibili-youtube-watcher（字幕提取）

## License

MIT
