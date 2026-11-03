---
source: |
  来源：Tailwind CSS / 行业最佳实践
  URL: https://www.tailwindcss.cn/
date: 2026-04-25
---

# H5 移动端最佳实践

> 来源：Tailwind CSS 文档 + 行业最佳实践（2026）
> https://www.tailwindcss.cn/docs/installation
> https://www.tailwindcss.cn/docs/browser-support

## 1. Tailwind CDN 快速原型

CDN 方式适合 H5 快速原型，引入即可使用：

```html
<script src="https://cdn.tailwindcss.com"></script>
```

生产环境建议使用 CLI 构建版。

## 2. H5 移动端关键设置

### viewport 元标签（必需）
```html
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
```

### 微信 H5 适配
- 设计宽度：750px（iPhone 6/7/8 逻辑像素）
- 使用 `flex` 布局配合 `justify-between`
- 微信浏览器：X5 内核，部分 CSS 特性有差异
- 触摸目标最小 44x44px

### 基础重置
```css
* { box-sizing: border-box; }
body { margin: 0; padding: 0; -webkit-tap-highlight-color: transparent; }
```

## 3. 响应式断点

Tailwind 移动优先断点：

| 断点前缀 | 最小宽度 | 典型设备 |
|---------|---------|---------|
| 无前缀 | 0px | 手机 |
| sm: | 640px | 大手机/小平板 |
| md: | 768px | 平板 |
| lg: | 1024px | 笔记本 |
| xl: | 1280px | 桌面 |

## 4. H5 常用工具类

### Flexbox 布局
```html
<!-- 水平居中 -->
<div class="flex justify-center items-center">
<!-- 垂直居中 -->
<div class="flex items-center justify-center">
<!-- 两端对齐 -->
<div class="flex justify-between">
```

### 间距
```html
<!-- 移动端常用间距 -->
<div class="px-4 py-3 gap-2">
<div class="m-4 space-y-3">
```

### 文字
```html
<!-- 移动端字体 -->
<div class="text-base leading-relaxed">
<div class="text-sm text-gray-500">
```

### 圆角和阴影
```html
<!-- 卡片圆角 -->
<div class="rounded-xl shadow-lg">
<!-- 按钮圆角 -->
<button class="rounded-full px-6 py-2">
```

## 5. 浏览器兼容性

- 支持：Chrome、Firefox、Edge、Safari（最新稳定版）
- 不支持：IE11
- 中国市场需注意：微信 X5 内核、UC 浏览器、百度浏览器
- 建议使用 Autoprefixer 处理厂商前缀

## 6. 生产构建

```bash
# CLI 构建
npm install -D tailwindcss
npx tailwindcss init
# 配置 tailwind.config.js
npx tailwindcss -o output.css --watch
```

## 7. 移动端性能

- 图片使用 `srcset` 响应式
- 动画使用 `transform` 和 `opacity`（GPU 加速）
- 使用 `will-change` 提示浏览器优化
- 避免重排，批量 DOM 操作
- 使用 CSS `content-visibility` 优化长列表

## 8. 微信 H5 注意事项

1. 微信支付需要公众号配置
2. 分享功能需要微信 JSSDK
3. 长按识别二维码需要单独处理
4. 音频/视频自动播放受限，需用户触发
5. 输入框 focus 时页面适配问题
