---
name: architecture-diagram
description: "暗色主题的 SVG 架构/云/基础设施图表，输出为 HTML。"
version: 1.0.0
author: Cocoon AI (hello@cocoon-ai.com), ported by Octop
license: MIT
dependencies: []
compatibility: linux, macos, windows
metadata:
  octop:
    label:
      zh: "架构图"
      en: "Architecture Diagram"
    summary:
      zh: "生成暗色主题的 SVG 架构与基础设施图。"
      en: "Generate dark-themed SVG architecture and infra diagrams."
  harness:
    emoji: "📐"
    tags: [architecture, diagrams, SVG, HTML, visualization, infrastructure, cloud]
    related_skills: [concept-diagrams, excalidraw]
---

# 架构图技能

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

生成专业的暗色主题技术架构图，输出为带内联 SVG 图形的独立 HTML 文件。无需外部工具、API 密钥或渲染库——只需编写 HTML 文件并在浏览器中打开。

## 适用范围

**最适合：**
- 软件系统架构（前端/后端/数据库层）
- 云基础设施（VPC、区域、子网、托管服务）
- 微服务/服务网格拓扑
- 数据库 + API 映射、部署图
- 任何适合暗色、网格背景美学的生产技术主题

**优先查找其他地方：**
- 物理、化学、数学、生物或其他科学主题
- 物理对象（车辆、硬件、解剖、横截面）
- 平面图、叙事旅程、教育/教科书式视觉
- 手绘白板草图（考虑 `excalidraw`）
- 动画解说（考虑动画技能）

如果有更适合该主题的专门技能，优先使用它。如果没有合适的，此技能也可作为通用 SVG 图表后备——输出只会带有下面描述的暗色技术美学。

基于 [Cocoon AI's architecture-diagram-generator](https://github.com/Cocoon-AI/architecture-diagram-generator) (MIT)。

## 工作流

1. 用户描述他们的系统架构（组件、连接、技术）
2. 按照下面的设计系统生成 HTML 文件
3. 使用 `write_file` 保存为 `.html` 文件（例如 `~/architecture-diagram.html`）
4. 用户在任意浏览器中打开——离线工作，无依赖

### 输出位置

将图表保存到用户指定的路径，或默认到当前工作目录：
```
./[project-name]-architecture.html
```

### 预览

保存后，建议用户打开它：
```bash
# macOS
open ./my-architecture.html
# Linux
xdg-open ./my-architecture.html
```

## 设计系统与视觉语言

### 调色板（语义映射）

使用特定的 `rgba` 填充和十六进制描边来对组件进行分类：

| 组件类型 | 填充 (rgba) | 描边 (Hex) |
| :--- | :--- | :--- |
| **前端** | `rgba(8, 51, 68, 0.4)` | `#22d3ee` (cyan-400) |
| **后端** | `rgba(6, 78, 59, 0.4)` | `#34d399` (emerald-400) |
| **数据库** | `rgba(76, 29, 149, 0.4)` | `#a78bfa` (violet-400) |
| **AWS/云** | `rgba(120, 53, 15, 0.3)` | `#fbbf24` (amber-400) |
| **安全** | `rgba(136, 19, 55, 0.4)` | `#fb7185` (rose-400) |
| **消息总线** | `rgba(251, 146, 60, 0.3)` | `#fb923c` (orange-400) |
| **外部** | `rgba(30, 41, 59, 0.5)` | `#94a3b8` (slate-400) |

### 排版与背景

- **字体：** JetBrains Mono（等宽字体），从 Google Fonts 加载
- **大小：** 12px（名称）、9px（子标签）、8px（注释）、7px（微小标签）
- **背景：** Slate-950 (`#020617`)，带微妙的 40px 网格图案

```svg
<!-- 背景网格图案 -->
<pattern id="grid" width="40" height="40" patternUnits="userSpaceOnUse">
  <path d="M 40 0 L 0 0 0 40" fill="none" stroke="#1e293b" stroke-width="0.5"/>
</pattern>
```

## 技术实现细节

### 组件渲染

组件是圆角矩形（`rx="6"`），带 1.5px 描边。为了防止箭头透过半透明填充显示，使用**双矩形遮罩技术**：
1. 绘制不透明的背景矩形 (`#0f172a`)
2. 在上面绘制样式化的半透明矩形

### 连接规则

- **Z 顺序：** 在 SVG 中*尽早*绘制箭头（在网格之后），以便它们渲染在组件框后面
- **箭头头部：** 通过 SVG 标记定义
- **安全流：** 使用玫瑰色 (`#fb7185`) 的虚线
- **边界：**
  - *安全组：* 虚线 (`4,4`)，玫瑰色
  - *区域：* 大虚线 (`8,4`)，琥珀色， `rx="12"`

### 间距与布局逻辑

- **标准高度：** 60px（服务）；80-120px（大型组件）
- **垂直间隙：** 组件之间最小 40px
- **消息总线：** 必须放置在服务*之间的间隙*中，不要与它们重叠
- **图例放置：** **关键。** 必须放在所有边界框之外。计算所有边界的最低 Y 坐标，并将图例放置在其下方至少 20px 处。

## 文档结构

生成的 HTML 文件遵循四部分布局：
1. **头部：** 带脉冲点指示器和副标题的标题
2. **主 SVG：** 图表包含在圆角边框卡片中
3. **摘要卡片：** 图表下方三张卡片的网格，用于高级细节
4. **页脚：** 最少元数据

### 信息卡模式
```html
<div class="card">
  <div class="card-header">
    <div class="card-dot cyan"></div>
    <h3>Title</h3>
  </div>
  <ul>
    <li>• Item one</li>
    <li>• Item two</li>
  </ul>
</div>
```

## 输出要求

- **单文件：** 一个自包含的 `.html` 文件
- **无外部依赖：** 所有 CSS 和 SVG 必须内联（Google Fonts 除外）
- **无 JavaScript：** 对任何动画使用纯 CSS（如脉冲点）
- **兼容性：** 必须在任何现代 Web 浏览器中正确渲染

## 模板参考

加载完整 HTML 模板以获取确切的结构、CSS 和 SVG 组件示例：

```
read_file("/_builtin_skills/architecture-diagram/templates/template.html")
```

模板包含每种组件类型（前端、后端、数据库、云、安全）、箭头样式（标准、虚线、曲线）、安全组、区域边界和图例的工作示例——在生成图表时将其作为你的结构参考。
