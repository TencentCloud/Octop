# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.0.3] - 2026-10-16

### 新增

- 提供带插件所有权的动态通道注册、更新和注销。宿主可通过 `register_channel_kind()` 在运行时注册自定义通道，重复注册保持首次结果。
- Telegram 支持按会话范围激活（群聊 `always` / `mention` / `mention_or_reply`、会话白名单），以及原生交互投递（回复引用、话题隔离、流式模式、回调按钮）。

### 修复

- Telegram 入站图片在落盘前识别实际格式，并保留 JPEG 的 MIME。
- Telegram 隔离并限制 update 与消息去重缓存；相册任务槽在激活后才占用，被动成员数量有上限；显式 429 重试能恢复嵌套上传句柄，无法恢复的重试直接拒绝。会排队 Agent 工作的短回调保持 Stop 可响应。
- `ERROR` 作为失败终态，不再等待后续完成事件；各通道显式关闭处理器执行清理，清理超过 5 秒取消并记录诊断。Telegram 预览流停止时同时关闭宿主 processor，避免错误回合跳过清理。
- 通道收到错误事件后结束本轮，避免后续完成事件将失败误标为成功；小艺任务同步发送 `failed` 状态，并保留错误展示。
- QQ 私聊流式回复在工具调用前已有正文发出或正在发送时，保留该段正文作为固定前缀，避免工具调用后的回答随流式更新反复追加。

## [1.0.2] - 2026-10-14

### 修复

- 微信思考状态改由 `sendtyping` 控制，正文发出前关闭，不再把「思考中」插到答案后面。思考灯失败且超过约 4 秒还没有正文时，才先发一条「⏳ 思考中...」。要灯和关灯的请求最多等 3 秒，避免卡住正文。
- 微信普通回复和主动推送超过约 2000 字时按换行切开再发，避免客户端显示不全。发送失败只记录返回码和字数，不记录发送票和正文。
- QQ 私聊不再把未完成的中间帧刷成空白气泡，整段回复落在同一个气泡里。

## [1.0.1] - 2026-10-09

### 新增

- Telegram：新增 `allowed_user_ids` 用户白名单（私聊与群聊均生效）。留空保持现有行为（任何人都能使用 Bot）；配置后只有列表中的 Telegram 用户 ID 能触发 Agent，其他消息在拉取媒体、调用 Agent 之前即被丢弃。

## [1.0.0] - 2026-09-24

### 新增

- 首个 1.0.0 正式版本发布到 PyPI。

### 变更

- 对齐 Octop：引入 `develop` 集成分支策略；禁止直推 `main`/`develop`；发版后由 `sync-main-to-develop.yml` 同步；新增 `/publish` skill（发版同步 CHANGELOG / README）。


