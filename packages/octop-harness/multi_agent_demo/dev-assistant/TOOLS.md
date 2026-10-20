# TOOLS.md - 工具配置与说明

---
summary: "工具使用规则与配置速查表"
read_when:
  - 手动引导工作区
---

## 工具使用规则

Skills 定义工具的用法。用之前翻它的 `SKILL.md`。本地设备配置（摄像头、SSH、语音偏好等）记在 `MEMORY.md`「工具设置」里。身份档案在 `IDENTITY.md`，用户档案在 `USER.md`。

### 网页信息获取策略

**先判断页面类型，再选工具——不要一上来就开浏览器。**

| 类型 | 判断依据 | 典型场景 | 工具策略 |
|------|---------|---------|---------|
| **静态内容** | 无 JS 渲染依赖；无登录态；内容直接在 HTML 里 | 新闻文章、RSS、开放 API、GitHub README、静态文档、Wikipedia | `execute_shell_command` + `curl` 优先；失败或内容残缺再升级到 `browser_use` |
| **动态渲染** | 依赖 JS 执行才能呈现（SPA）；有反爬检测；需要登录态 | 知乎、微博、各大电商详情页、内网管理系统、需要鉴权的后台 | 直接 `browser_use`（Playwright/stealth），跳过 curl |

**选型决策树：**

1. URL 明显是 API（含 `/api/`、`.json`、`.xml`、`.rss`）→ **curl**
2. 目标是已知动态站（知乎 / 微博 / 淘宝 / B 站 / 飞书文档 / 内网系统）→ **直接 browser**
3. 普通网页但不确定 → curl 先试；返回体 `<body>` 里只有少量文字或全是 `<script>` 标签 → 切换 browser
4. 需要点击、滚动、填表、登录 → **只能 browser**

**curl 降级条件（出现以下任一即切换 browser）：**
- HTTP 403 / 429 / 5xx
- 返回体 `<body>` 少于 200 字符
- 内容明显是 JS 占位（`<div id="app"></div>` 之类）
- 需要 Cookie / Session 才能看到真实内容

---

### 向用户展示文件

展示文件、图片、音频或视频时，使用 `file_preview` 工具（详见系统策略）。`desktop_screenshot` 等其他返回媒体的工具同理——调用工具即可，不要把返回的 URL 嵌入回复。

---

## 工具配置速查表

> 在此记录工具的特定配置、注意事项和凭证信息。

### 凭证存放位置

所有凭证存放在 `.credentials/` 目录下（已加入 .gitignore）。




