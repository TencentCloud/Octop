---
AIGC:
    ContentProducer: Minimax Agent AI
    ContentPropagator: Minimax Agent AI
    Label: AIGC
    ProduceID: 8e25991f61069ffc6cc28e33d38ed17d
    PropagateID: 8e25991f61069ffc6cc28e33d38ed17d
    ReservedCode1: 3045022100919684f66b4830d8aa8c13fe3fe5eb1df44b8f82535e81a8214fe833c13fb3030220513585ce8a8da7911923f5ae98a203077163299bbb12b98e5c7056c1d5bfb2c1
    ReservedCode2: 304402201fe77b09dacbda84d317c5ebe24ab6bf489a9b72ac8983032a81bd4109d167b702205907c1cb18f5336b47848f966b850e6aab4a1c233cec8979f9f3d95361aa8cf6
description: 从产品需求到可交互原型的完整工作流。当用户表达产品想法（如'我想做一个...'、'帮我设计...'）时触发。支持：1) 零提问直出PRD 2) 平台选择确认 3) 生成Awwwards级别的高保真HTML/Tailwind原型（移动端/PC端）。端到端产品设计流程。
name: PRD to Prototype
---

# PRD to Prototype — 从想法到可交互原型

## Overview

本技能将用户的模糊产品想法，通过两步强制流程，转化为完整的PRD文档和高保真可交互HTML原型。全程零提问、直接执行，最终交付可在浏览器中预览的原型页面。

---

## ⚠️ 核心铁律（违反必究）

1. **禁止提问**：无论用户输入的需求多么简短或模糊，**绝对禁止**在生成PRD之前询问任何问题。
2. **直接脑补**：必须立即基于行业标准和合理假设，自动补全所有细节，直接产出包含完整交互流程的PRD。
3. **强制两步流程**：必须先生成PRD，再生成原型。绝不跳过PRD直接做原型。

---

## Workflow（强制流程）

### 🟢 第一阶段：直出PRD与交互流程

**触发条件：** 用户表达任何产品想法、需求、痛点或创意（例如："我想做一个商城"）。

**执行步骤：**

1. **零延迟响应**：不进行任何澄清对话，直接开始生成PRD。
2. **生成完整PRD文档**，写入 `/workspace/docs/prd.md`，内容必须包含：
   - 产品概述与目标用户
   - 核心功能列表与优先级
   - 完整的用户交互路径（User Flows）
   - 页面清单与页面间跳转关系
   - 非功能性需求（性能、安全等合理假设）
3. **PRD生成后，立即在同一条消息中展示 GenUI 确认表单**（模板见下方）。

**GenUI 确认表单模板（必须严格一致）：**

```markdown
✅ **PRD与交互流程已生成**：`/workspace/docs/prd.md`

-----------------------------------------------------------------------
📋 **GenUI Project Confirmation**
-----------------------------------------------------------------------
请审核方案，并选择下一步操作：

[ 🚀 确认并生成移动端 App 原型 ]   (回复: "确认移动端")
[ 💻 确认并生成 PC 端 Web 原型 ]   (回复: "确认PC端")
[ 🛠️ 修改需求文档 ]               (回复: "修改: <您的意见>")
[ ❌ 拒绝并重写 ]                 (回复: "重写")
-----------------------------------------------------------------------
```

### 🔵 第二阶段：原型设计与生成

**触发条件：** 用户在确认表单中做出选择（回复 "确认移动端" 或 "确认PC端"）。

**执行步骤：**

1. 读取 `/workspace/docs/prd.md` 中的PRD内容。
2. 根据用户选择的目标平台（Mobile / PC），按照下方【设计系统】和【构建策略】生成原型。
3. 创建原型文件到 `/workspace/prototype/` 目录。
4. 部署原型（如有 deploy 工具可用）。
5. **双重交付**：返回可访问的原型预览链接 + PRD文档路径。

### 用户反馈处理

- **用户点确认**（选平台）→ 立即进入第二阶段。
- **用户改需求**（回复 "修改: ..."）→ 根据意见快速修改PRD → **再次展示** GenUI 确认表单。
- **用户重写**（回复 "重写"）→ 重新生成PRD → **再次展示** GenUI 确认表单。

---

## 设计系统（Design System）

### 色彩 (Color Palette)

- 避免使用高饱和度的纯色（如 `#0000FF`）。
- **PC端**：偏向 B端 SaaS 风格（清爽、大留白）或极客暗黑模式。
- **移动端**：偏向 iOS 18 风格（大圆角、毛玻璃、沉浸式）。
- **配色建议**：使用 Zinc/Slate 中性色系作为骨架，品牌色仅用于 CTA（行动号召）按钮。

### 排版 (Typography)

- 字体栈：`-apple-system, BlinkMacSystemFont, "SF Pro Text", "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif`
- 字号：建立清晰的层次（H1 vs Body），使用 `rem` 单位。
- 行高：正文行高至少 `1.6`。

### 质感 (Texture & Depth)

- **投影**：使用多层柔和阴影（`box-shadow`），避免生硬的黑边。
- **圆角**：现代 UI 标配大圆角（`rounded-xl`, `rounded-2xl`）。
- **模糊**：背景模糊（`backdrop-filter: blur(20px)`）用于侧边栏或弹窗。

### 审美标准

- **拒绝**：默认蓝色/系统蓝、粗糙的阴影、拥挤的布局、低像素图片、Arial/宋体默认字体。
- **必须**：使用高级灰/黑白/品牌色、大留白、毛玻璃效果、流畅动效、高清真实图片、系统级字体栈。
- **标准**：设计必须对标 Awwwards、Dribbble 热门作品和 Apple 设计规范。看起来像 2025 年的产品，而非 2010 年的 Bootstrap 模板。

---

## 平台构建策略

### 📱 移动端 (Mobile) — "沉浸式体验"

- **容器模拟**：在 `index.html` 中必须使用 CSS 绘制一个逼真的 iPhone 16 外框（带灵动岛/刘海）。
- **布局**：
  - 顶部：状态栏（时间/电量）+ 导航栏（大标题/透明背景）。
  - 底部：悬浮或磨砂质感的 TabBar。
  - 内容：卡片式布局，左右留边，内容不贴边。
- **交互**：按钮点击要有缩放反馈（`active:scale-95`）。

### 💻 PC端 (Desktop) — "生产力美学"

- **布局**：
  - 经典的 Sidebar + Header + Content 布局，或顶部大导航布局。
  - 最大宽度限制（`max-w-7xl`），居中显示，避免在大屏上内容过于拉伸。
- **交互**：
  - Hover 效果必不可少（颜色加深、轻微上浮）。
  - Tooltip 提示。
  - 表格行 Hover 高亮。

---

## 资源生成规范

### 图片 (Unsplash)

- **严禁**使用占位符（如 `via.placeholder.com`）。
- 必须使用 Unsplash Source 或类似服务获取**高质量、无水印**图片。
- 根据产品类型选择关键词（e.g., "minimalist office", "abstract technology", "modern portrait"）。
- URL 示例：`https://images.unsplash.com/photo-1497366216548-37526070297c?auto=format&fit=crop&w=800&q=80`（确保图片链接稳定有效）。

### 图标 (Icons)

- 使用 **FontAwesome 6 (CDN)** 或 **Heroicons (SVG)**。
- 图标要与文字垂直居中对齐，大小适中。

---

## 技术栈与代码规范

### 技术栈（强制）

- 输出纯 **HTML5 + Tailwind CSS (CDN) + Vanilla JS**。
- **严禁**依赖需要编译的框架（如 React/Vue）。

### HTML 模板结构

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>产品名称</title>
    <!-- 引入 Tailwind -->
    <script src="https://cdn.tailwindcss.com"></script>
    <!-- 引入 FontAwesome -->
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <!-- 配置 Tailwind 主题 (可选) -->
    <script>
      tailwind.config = {
        theme: {
          extend: {
            colors: {
              brand: '#0f172a', // 自定义品牌色
            }
          }
        }
      }
    </script>
    <style>
        /* 自定义微调样式，如滚动条隐藏、毛玻璃兼容性 */
        body { font-family: -apple-system, system-ui, sans-serif; }
    </style>
</head>
<body class="bg-gray-50 text-gray-900 antialiased">
    <!-- 内容区域 -->
</body>
</html>
```

### 语言统一

- 界面所有文案、数据、按钮必须为**简体中文**（除非用户指定外语）。
- 严禁残留 Lorem Ipsum 或英文标题。

---

## 文件与输出规范

### 目录结构

```
/workspace/
├── docs/
│   └── prd.md              # PRD文档
└── prototype/
    ├── index.html           # 入口页面
    └── pages/
        ├── page1.html       # 子页面
        ├── page2.html       # 子页面
        └── ...
```

### 关键要求

- `index.html` 必须能够预览所有页面：
  - 移动端：用 iframe 手机壳展示。
  - PC端：直接作为首页。
- 所有图片必须真实加载（Unsplash），所有链接必须可点击（跳转或空锚点）。

---

## 原型生成执行步骤

1. **分析 PRD**：确定核心页面（首页、列表、详情）。
2. **定义视觉风格**：根据平台和产品类型确定配色、排版、质感。
3. **生成资源**：选择合适的 Unsplash 图片关键词。
4. **编写代码**：
   - 创建 `/workspace/prototype/index.html`（入口）。
   - 创建 `/workspace/prototype/pages/*.html`（子页面）。
5. **检查细节**：
   - 检查所有文案是否为中文。
   - 检查图片是否加载成功。
   - 检查布局是否错位。
6. **部署**：如有 deploy 工具可用，调用部署。

---

## 质量自检 (Pre-flight Check)

- [ ] **审美**：这看起来像是一个 2025 年的产品吗？还是像 2010 年的 Bootstrap 模板？（必须是前者）
- [ ] **中文**：是否有残留的 Lorem Ipsum 或英文标题？
- [ ] **图片**：是否有裂图？图片风格是否统一？
- [ ] **完整性**：所有链接可点击？所有页面可访问？
- [ ] **响应速度**：CDN 链接是否可访问？（Tailwind CDN 通常没问题）
- [ ] **交互**：按钮、hover、动效是否正常工作？

---

## Common Mistakes to Avoid

1. **在生成PRD前询问用户问题** — 绝对禁止，必须零提问直接生成。
2. **跳过PRD直接生成原型** — 必须严格遵守两步流程。
3. **使用占位符图片** — 必须使用 Unsplash 真实图片。
4. **使用需要编译的框架** — 只允许纯 HTML + Tailwind CDN + Vanilla JS。
5. **残留英文文案** — 所有界面内容必须为简体中文。
6. **使用默认系统蓝或高饱和纯色** — 必须使用高级配色方案。
7. **忘记展示 GenUI 确认表单** — PRD生成后必须立即展示。
8. **PRD中缺少交互流程** — 必须包含完整的 User Flows。
