# Design to Code（还原设计图）

将设计稿（Figma/Sketch/图片）高保真还原为前端代码。

## What It Does

- 解析设计稿：标注、层级、状态、响应式断点
- 设计 token 对齐（颜色、字号、间距映射到 CSS 变量/Tailwind）
- 实现优先级：布局 → 字体排版 → 视觉 → 交互状态 → 响应式 → 动效
- 还原度自检清单

## How to Use

当用户说「还原设计图」「按设计稿实现」「切图」「设计转代码」或提供 Figma/Sketch 链接、设计图截图时启用，按项目技术栈输出组件化代码。

## Requirements

- 项目使用 Tailwind/SCSS 等现有技术栈
- 语义化 HTML 与合理 ARIA
