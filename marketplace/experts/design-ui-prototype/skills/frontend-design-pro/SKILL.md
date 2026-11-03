---
name: frontend-design-pro
description: >
  前端设计质量提升 skill。让 AI 生成的 UI/前端代码更专业，避免常见设计反模式。
  参考 impeccable 项目的设计语言规范，提供 audit/polish/critique 等设计审查命令。
  触发词：/audit /polish /critique /colorize /animate /bolder /quieter /distill
  以及：审查UI设计、优化界面、前端设计建议、让设计更好看、检查设计质量
author: antonia-sz
version: 1.0.0
---

# Frontend Design Pro — 前端设计质量提升

灵感来源：[impeccable](https://github.com/pbakaus/impeccable) ⭐ 3k

一套专业的前端设计语言规范，让 AI 输出的 UI 摆脱"千篇一律的模板感"。

---

## 为什么需要这个 skill？

LLM 从相同的通用模板中学习，没有引导就会产生相同的可预测错误：
- Inter 字体 + 紫色渐变
- 卡片套卡片套卡片
- 彩色背景上的灰色文字
- Bounce/弹性动画（显得老气）

这个 skill 用设计规范和反模式清单，主动引导 AI 产出专业设计。

---

## 设计规范（核心原则）

### 字体 (Typography)
- ✅ 选择有个性的字体：Geist, Instrument Serif, DM Sans, Sora
- ✅ 建立字体比例系统（modular scale：1.25 或 1.333）
- ❌ 禁止：Arial, Inter（过于通用）, system-ui（缺乏个性）
- ❌ 禁止：同一页面超过 2 种字体族

### 色彩 (Color & Contrast)
- ✅ 使用 OKLCH 色彩空间定义颜色（感知均匀）
- ✅ 中性色永远带色调（warm gray / cool gray，不要纯灰）
- ✅ 暗色模式：背景用 #0f0f0f，不要纯黑 #000000
- ❌ 禁止：彩色背景上用灰色文字
- ❌ 禁止：纯黑/纯灰（始终带一点色调）

### 空间 (Spatial Design)
- ✅ 建立 4px 或 8px 基础间距系统
- ✅ 用留白创造呼吸感，不要把元素挤在一起
- ✅ 内容宽度限制：正文 65ch，宽容器 1280px
- ❌ 禁止：随意的 padding 数字（13px, 22px）

### 动效 (Motion Design)
- ✅ easing 使用 cubic-bezier(0.16, 1, 0.3, 1)（快入慢出）
- ✅ 微交互时长：100-200ms；页面过渡：300-500ms
- ✅ 尊重 prefers-reduced-motion
- ❌ 禁止：bounce/elastic easing（显得廉价）
- ❌ 禁止：超过 600ms 的动画（太慢）

### 交互 (Interaction Design)
- ✅ Focus 状态必须清晰可见（不要移除 outline）
- ✅ Loading 状态：skeleton 优于 spinner
- ✅ 错误信息：具体 + 可操作（"邮箱格式不对" vs "输入有误"）
- ❌ 禁止：禁用状态没有提示原因

### UX 文案 (UX Writing)
- ✅ 按钮文字：动词开头（"保存更改" 不是 "确认"）
- ✅ 空状态：说明原因 + 提供下一步操作
- ✅ 错误提示：人话，不要技术术语
- ❌ 禁止："请稍候..."（说明在做什么）

---

## 命令列表

在任何 UI/前端相关对话中使用这些命令：

| 命令 | 功能 |
|------|------|
| `/audit [组件名]` | 检查无障碍、性能、响应式问题 |
| `/critique [组件名]` | UX 设计评审：层次、清晰度 |
| `/polish [组件名]` | 发布前最终打磨 |
| `/distill [组件名]` | 化繁为简，去除多余元素 |
| `/colorize [组件名]` | 引入战略性色彩 |
| `/animate [组件名]` | 添加有意义的动效 |
| `/bolder [组件名]` | 让平淡的设计更大胆 |
| `/quieter [组件名]` | 让过于张扬的设计沉稳下来 |
| `/delight [组件名]` | 添加让人会心一笑的细节 |
| `/normalize [组件名]` | 与设计系统规范对齐 |
| `/harden [组件名]` | 增加错误处理、边界情况、国际化 |

---

## 执行规则

当用户发出设计相关请求时：

1. **自动应用设计规范**：生成或修改 UI 代码时，主动遵循上述规范
2. **收到命令时**：
   - `/audit`：检查并列出 3-5 个具体问题（带行号/组件名）
   - `/polish`：输出修改后的完整代码 + 说明改了什么
   - 其他命令：先说明要做什么修改，再输出改后代码
3. **主动提醒反模式**：发现用户代码有反模式时，简短指出
4. **优先给代码**：设计建议要落地到具体 CSS/代码，不停留在概念

---

## 示例

用户说："帮我写一个登录表单"

**自动应用规范后的输出特征：**
- 字体使用 Geist 或 DM Sans（不用 Arial/Inter）
- 输入框 focus 状态用 2px solid oklch(0.6 0.2 250)（带色调的蓝）
- 按钮文字："登录" 而不是 "确认"
- 错误提示："邮箱格式不正确，请检查 @ 符号前后" 而不是 "输入错误"
- Loading 状态用 skeleton，不用 spinner
- spacing 用 8px 倍数（8/16/24/32px）
