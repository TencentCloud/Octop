---
name: wechat-publisher-personal
description: Personal Multi-Platform Publisher — 一文多发工具，将 Markdown 文章同时发布到内容运营平台和社交内容平台。微信端通过 wenyan-cli + 自建服务器代理，社交内容平台端通过浏览器自动化。
metadata:
  {
    "openclaw":
      {
        "emoji": "✍️",
        "requires": { "bins": ["node", "npx", "python3"] },
        "primaryEnv": "WECHAT_APP_ID",
      },
    "octop":
      {
        "emoji": "✍️",
        "label": { "zh": "一文多发", "en": "Multi-Platform Publisher" },
        "summary":
          {
            "zh": "把一篇 Markdown 同步发布到内容运营平台与社交平台。",
            "en": "Publish one Markdown article to content and social platforms.",
          },
      },
  }
---

# 个人版一文多发工具 — 内容运营平台 + 社交内容平台

写一篇 Markdown，同时发布到**内容运营平台**和**社交内容平台**。微信端通过 wenyan-cli 渲染精美排版，社交内容平台端自动适配短文案 + 图片格式。无需依赖第三方 SaaS 平台，数据完全自主可控。

> 集成 [ClawHub hi-yu/xhs](https://clawhub.ai/hi-yu/xhs) v1.2.5 社交内容平台 Skill 能力

## 支持平台

| 平台 | 发布方式 | 内容格式 |
|------|----------|----------|
| 📱 **内容运营平台** | wenyan-cli + 微信 API → 草稿箱 | 长文章 + 精美排版 |
| 📕 **社交内容平台 (RedNote)** | Playwright 浏览器自动化 → 直接发布 | 短笔记 + 图片 + 话题标签 |

## Agent 人格标识

本 Skill 遵循 [SoulHub](https://github.com/Yourdaylight/soulhub) Agent 规范，包含完整的人格身份定义：

| 文件 | 说明 |
|------|------|
| [`manifest.yaml`](./manifest.yaml) | Agent 元数据（名称、分类、标签、版本） |
| [`IDENTITY.md`](./IDENTITY.md) | 身份定义 — 我是谁、我的专长、工作方式 |
| [`SOUL.md`](./SOUL.md) | 灵魂规范 — 核心原则、行为边界、语气风格 |

> **核心人格**: ✍️ 一文多发助手 — 独立自主的内容发行人，一篇 Markdown 同时覆盖微信和社交内容平台。极简高效、数据自主、一键搞定。

## 与 agent-publisher 的区别

| 特性 | agent-publisher (SaaS版) | wechat-publisher-personal (个人版) |
|------|--------------------------|----------------------------------|
| 部署方式 | 使用共享后端服务 | 用户自己的服务器 |
| 数据存储 | 存在后端数据库 | 本地文件 + 微信平台 |
| 用户管理 | 多用户、邮箱注册 | 单用户、直接使用 |
| AI 生成 | 内置 AI Agent 生成内容 | 用户自己写内容或由 AI 辅助编写 |
| 依赖 | Python + 后端 API | Node.js (wenyan-cli) + Python 辅助脚本 |
| IP 白名单 | 使用共享服务器 IP | 用户自己服务器的公网 IP |

## Prerequisites

### 内容运营平台（必需）

1. **Node.js** >= 18（用于运行 wenyan-cli）
2. **Python** >= 3.10（用于辅助脚本）
3. **一台有固定公网 IP 的服务器**（用作微信 API IP 白名单代理）
4. **内容运营平台** 的 AppID 和 AppSecret

### 社交内容平台（可选，启用一文多发）

5. **Python playwright** — `pip install playwright && playwright install chromium`
6. **社交内容平台账号** — 通过扫码登录
7. **AI 封面生成（可选）** — 配置 `GEMINI_API_KEY` / `IMG_API_KEY` / `HUNYUAN_API_KEY` 之一

## 快速开始

### Step 1: 安装 wenyan-cli

```bash
npm install -g @wenyan-md/cli
```

验证安装：
```bash
wenyan --help
```

### Step 2: 配置内容运营平台凭证

设置环境变量（推荐写入 `~/.bashrc` 或 `~/.zshrc`）：

```bash
export WECHAT_APP_ID="your_wechat_app_id"
export WECHAT_APP_SECRET="your_wechat_app_secret"
```

### Step 3: 获取 AppID 和 AppSecret

如果用户还没有内容运营平台凭证：

1. 登录 [微信开发者平台](https://developers.weixin.qq.com/console/product/mp)
2. 进入 "我的业务与服务" → "公众号" → "基础信息"
3. 复制 **AppID**
4. 点击 AppSecret 旁的 "重置" 生成新密钥（⚠️ 仅显示一次，立即保存！）

### Step 4: 配置 IP 白名单

有两种模式，根据用户情况选择：

#### 模式 A: 本地模式（有固定公网 IP）

如果你的本地网络有固定公网 IP：
1. 获取你的公网 IP：`curl ifconfig.me`
2. 在微信开发者平台 → "API IP白名单" → 点击 "编辑" → 添加你的 IP

#### 模式 B: Server 模式（推荐，无固定 IP 时使用）

在你的云服务器上部署 wenyan server 作为代理：

```bash
python3 {baseDir}/scripts/wechat_publish.py setup-server --host your_server_ip
```

这会指导你：
1. 在服务器上安装 wenyan-cli 并启动 `wenyan serve`
2. 将服务器公网 IP 加入微信白名单
3. 配置本地 CLI 连接服务器

然后设置 server 环境变量：
```bash
export WENYAN_SERVER="http://your_server_ip:7788"
export WENYAN_API_KEY="your_api_key"
```

### Step 5: 发布第一篇文章

准备一个 Markdown 文件，顶部包含 frontmatter：

```markdown
---
title: 我的第一篇文章
cover: ./cover.jpg
author: 你的名字
---

# 正文内容

这是正文...
```

然后发布：

```bash
python3 {baseDir}/scripts/wechat_publish.py publish article.md
```

---

## All Commands

### 📦 一文多发（推荐）

**一条命令同时发布到微信 + 社交内容平台：**

```bash
python3 {baseDir}/scripts/wechat_publish.py multi-publish article.md
```

**社交内容平台使用草稿模式（推荐首次使用）：**

```bash
python3 {baseDir}/scripts/wechat_publish.py multi-publish article.md --xhs-draft
```

**批量一文多发：**

```bash
python3 {baseDir}/scripts/wechat_publish.py multi-publish article1.md article2.md
```

---

### 📱 内容运营平台

#### 发布文章

**直接发布 Markdown 到内容运营平台草稿箱：**

```bash
python3 {baseDir}/scripts/wechat_publish.py publish article.md
```

**指定主题发布：**

```bash
python3 {baseDir}/scripts/wechat_publish.py publish article.md --theme github
```

**通过 Server 模式发布（本地无固定 IP 时）：**

```bash
python3 {baseDir}/scripts/wechat_publish.py publish article.md --server http://your_server:7788 --api-key your_key
```

**批量发布多篇文章：**

```bash
python3 {baseDir}/scripts/wechat_publish.py publish article1.md article2.md article3.md
```

### 渲染预览

**渲染 Markdown 为 HTML（不发布，仅预览）：**

```bash
python3 {baseDir}/scripts/wechat_publish.py render article.md
```

**渲染并保存到文件：**

```bash
python3 {baseDir}/scripts/wechat_publish.py render article.md --output article.html
```

### 主题管理

**列出所有可用主题：**

```bash
python3 {baseDir}/scripts/wechat_publish.py themes
```

**预览某个主题效果：**

```bash
python3 {baseDir}/scripts/wechat_publish.py render article.md --theme elegant --output preview.html
```

### Server 管理

**检查 server 连接状态：**

```bash
python3 {baseDir}/scripts/wechat_publish.py server-status
```

**部署/配置 wenyan server（交互式引导）：**

```bash
python3 {baseDir}/scripts/wechat_publish.py setup-server --host your_server_ip
```

### 配置检查

**检查当前环境配置是否正确：**

```bash
python3 {baseDir}/scripts/wechat_publish.py check
```

输出：wenyan-cli 安装状态、环境变量、IP 白名单建议、server 连接等。

---

## 社交内容平台命令

### 登录社交内容平台

**首次使用需要扫码登录：**

```bash
python3 {baseDir}/scripts/xhs_publish.py login
```

浏览器会自动打开，使用社交内容平台 APP 扫描二维码即可。Cookie 会自动保存，后续无需重复登录。

### 发布到社交内容平台

**将 Markdown 文件发布为社交内容平台笔记：**

```bash
python3 {baseDir}/scripts/xhs_publish.py publish article.md
```

**草稿模式（填写内容但不自动点击发布）：**

```bash
python3 {baseDir}/scripts/xhs_publish.py publish article.md --draft
```

**无头模式（后台运行）：**

```bash
python3 {baseDir}/scripts/xhs_publish.py publish article.md --headless
```

### 预览社交内容平台适配效果

**查看 Markdown 转换为社交内容平台格式后的效果：**

```bash
python3 {baseDir}/scripts/xhs_publish.py adapt article.md
```

这会显示：标题裁剪（≤20字）、正文转换、图片提取、话题标签等。

### 检查社交内容平台环境

```bash
python3 {baseDir}/scripts/xhs_publish.py check
```

---

## 一文多发命令

### 同时发布到微信 + 社交内容平台

**一条命令，Markdown 同时发布到两个平台：**

```bash
# 先发内容运营平台
python3 {baseDir}/scripts/wechat_publish.py publish article.md

# 再发社交内容平台
python3 {baseDir}/scripts/xhs_publish.py publish article.md
```

> 💡 **内容自动适配**：微信端保持完整长文排版，社交内容平台端自动转换为短笔记 + 图片 + 话题标签格式。同一篇 Markdown，两个平台各自呈现最佳形态。

---

## Environment Variables

### 内容运营平台

| Variable | Description | Default |
|----------|-------------|---------|
| `WECHAT_APP_ID` | 内容运营平台 AppID | — (必填) |
| `WECHAT_APP_SECRET` | 内容运营平台 AppSecret | — (必填) |
| `WENYAN_SERVER` | wenyan server URL（Server 模式） | — (可选) |
| `WENYAN_API_KEY` | wenyan server API Key（Server 模式） | — (可选) |
| `WENYAN_THEME` | 默认渲染主题 | `github` |

### 社交内容平台

| Variable | Description | Default |
|----------|-------------|---------|
| `XHS_COOKIE_FILE` | 社交内容平台 Cookie 文件路径 | `~/.xhs-cookies.json` |
| `GEMINI_API_KEY` | Gemini API Key（AI 封面生成） | — (可选) |
| `IMG_API_KEY` | 图片生成 API Key（AI 封面生成） | — (可选) |
| `HUNYUAN_API_KEY` | 腾讯混元 API Key（AI 封面生成） | — (可选) |

## Typical Workflow

### 首次使用

1. **安装 wenyan-cli** → `npm install -g @wenyan-md/cli`
2. **安装 playwright** → `pip install playwright && playwright install chromium`
3. **环境检查** → `wechat_publish.py check` + `xhs_publish.py check`
4. **配置微信白名单** → 本地模式或 `setup-server` Server 模式
5. **登录社交内容平台** → `xhs_publish.py login`（扫码登录）
6. **写文章** → 用 Markdown 编写，添加 frontmatter（title、cover、tags）
7. **预览** → `wechat_publish.py render` + `xhs_publish.py adapt`（分别查看两端效果）
8. **一文多发** → `wechat_publish.py publish` + `xhs_publish.py publish`
9. **登录公众号后台** → 检查草稿箱，点击发布
10. **发布后校验** → 在 [搜狗微信搜索](https://weixin.sogou.com/) 搜索文章标题，确认文章已被收录

### 日常使用（一文多发）

1. **写 Markdown** → 任意编辑器
2. **发布微信** → `wechat_publish.py publish article.md`
3. **发布社交内容平台** → `xhs_publish.py publish article.md`
4. **去公众号后台发布** → 检查、发布
5. **发布后校验** → 去 [搜狗微信搜索](https://weixin.sogou.com/) 搜索文章标题，确认可被搜到

### AI 辅助写作 + 一文多发

1. **让 AI 生成 Markdown 内容** → 包含 frontmatter（title、cover、tags）
2. **预览两端效果** → `render` 看微信排版 + `adapt` 看社交内容平台适配
3. **修改调整** → 可让 AI 继续修改
4. **一键多发** → 先 `wechat_publish.py publish`，再 `xhs_publish.py publish`
5. **发布后校验** → 用户确认在公众号后台发布后，去 [搜狗微信搜索](https://weixin.sogou.com/) 搜索验证

---

## Markdown 文件格式

每篇文章的 Markdown 文件顶部必须包含 frontmatter：

```yaml
---
title: 文章标题（必填）
cover: 封面图路径或URL（可选，推荐）
author: 作者名（可选）
source_url: 原文链接（可选）
tags: 标签1, 标签2, 标签3（可选，用于社交内容平台话题标签）
---
```

### 社交内容平台内容适配规则

Markdown 发布到社交内容平台时会自动适配：

| 项目 | 内容运营平台 | 社交内容平台 |
|------|-----------|--------|
| 标题 | 完整标题 | 截取前 20 字 |
| 正文 | HTML 精美排版 | 纯文本，emoji 标注段落 |
| 图片 | 嵌入文章内 | 作为笔记图片上传 |
| 代码块 | 语法高亮 | `💻 代码片段:` 文本化 |
| 链接 | 保留超链接 | 仅保留链接文字 |
| 标签 | 不使用 | frontmatter `tags` → `#话题` |
| 长度 | 无限制 | ≤1800 字，超长自动截断 |

### 图片支持

- 本地图片：`![alt](./images/photo.jpg)` — 自动上传到微信图床
- 网络图片：`![alt](https://example.com/photo.jpg)` — 自动下载并上传
- 封面图：在 frontmatter 的 `cover` 字段指定

---

## 发布后校验

当用户告知草稿已在公众号后台正式发布后，需要进行最后一步校验：

1. 打开 [搜狗微信搜索](https://weixin.sogou.com/)
2. 搜索文章标题或公众号名称
3. 确认文章能被搜索到

> **注意**：文章从发布到被搜狗收录通常需要一段时间（几小时到一天不等）。如果刚发布就搜不到，可以稍后再试。

这一步是整个发布流程的**最终校验**，确保文章不仅进入了草稿箱、在公众号后台发布成功，还能被外部搜索引擎正常索引和检索。

## Notes

### 内容运营平台
- wenyan-cli 会自动将文章中的图片上传到微信素材库
- 发布后文章进入**草稿箱**，需要登录公众号后台手动发布
- 封面图建议尺寸：900x383 或 2.35:1 比例
- 如果使用 Server 模式，只需在服务器上配置 IP 白名单，本地 IP 随意变动
- 支持数学公式（LaTeX）、代码高亮、链接自动转脚注等

### 社交内容平台
- 社交内容平台笔记**必须包含至少一张图片**，建议在 frontmatter 中设置 `cover` 字段
- 封面图建议尺寸：1080x1440（3:4 竖屏）或 1080x1080（正方形）
- 正文会自动从 Markdown 转换为社交内容平台友好的纯文本格式
- 标题限制 20 字以内，超长会自动截取
- 正文建议 1800 字以内，超长会自动截断并附加公众号引导语
- Cookie 有效期通常为 7-30 天，过期需要重新 `login` 扫码
- frontmatter 中的 `tags` 字段会自动转为社交内容平台 `#话题标签`
- 建议使用 `--draft` 模式先预览，确认无误后再正式发布
