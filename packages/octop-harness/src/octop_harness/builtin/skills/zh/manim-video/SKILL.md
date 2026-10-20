---
name: manim-video
description: "Manim CE 动画：3Blue1Brown 数学/算法视频。"
version: 1.0.0
compatibility: linux, macos, windows
metadata:
  octop:
    label:
      zh: "Manim 动画"
      en: "Manim Video"
    summary:
      zh: "用 Manim CE 制作数学与算法讲解动画。"
      en: "Make math and algorithm explainers with Manim CE."
  harness:
    emoji: "🎥"
---

# Manim 视频制作流程#

## Harness-agent tools#

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

## 何时使用#

当用户请求：动画解释、数学动画、概念可视化、算法演练、技术讲解、3Blue1Brown 风格视频，或任何带有几何/数学内容的程序化动画时，使用此技能。使用 Manim Community Edition 创建 3Blue1Brown 风格讲解视频、算法可视化、公式推导、架构图和数据分析故事。

## 创意标准#

这是教育电影。每一帧都在教学。每一个动画都揭示结构。

**在编写任何一行代码之前**，阐明叙事弧。这个误解需要纠正什么？"啊哈时刻"是什么？什么视觉故事让观众从困惑走向理解？用户的提示是一个起点——要用教学野心去诠释它，而不是字面转录。

**几何先于代数。** 先展示形状，再展示公式。视觉记忆比符号记忆编码更快。当观众在公式之前看到几何模式时，公式感觉是应得的。

**首次渲染卓越是不可协商的。** 输出必须在视觉上清晰且美学上连贯，无需修改轮次。如果某些东西看起来杂乱、时机不当，或像"AI 生成的幻灯片"，那就是错误的——在交付之前重新思考创意概念。

**不透明度分层引导注意力。** 永远不要以全亮度显示所有内容。主要元素在 1.0，上下文元素在 0.4，结构元素（坐标轴、网格）在 0.15。大脑按层次处理视觉显著性。

**呼吸空间。** 每个动画之后都需要 `self.wait()`。观众需要时间吸收刚刚出现的内容。永远不要从一个动画匆忙进入下一个。在关键揭示之后的 2 秒暂停永远不会浪费。

**连贯的视觉语言。** 所有场景共享一个调色板、一致的排版尺寸、匹配的动画速度。一个技术正确但每个场景使用随机不同颜色的视频是美学失败。

## 先决条件#

运行 `scripts/setup.sh` 以验证所有依赖项。需要：Python 3.10+、Manim Community Edition v0.20+（`pip install manim`）、LaTeX（`texlive-full` 在 Linux 上，`mactex` 在 macOS 上）和 ffmpeg。参考文档针对 Manim CE v0.20.1 测试。

## 模式#

| 模式 | 输入 | 输出 | 参考 |
|------|-------|--------|-----------|
| **概念讲解** | 主题/概念 | 带有几何直觉的动画解释 | `references/scene-planning.md` |
| **公式推导** | 数学表达式 | 逐步动画证明 | `references/equations.md` |
| **算法可视化** | 算法描述 | 带有数据结构的逐步执行 | `references/graphs-and-data.md` |
| **数据故事** | 数据/指标 | 动画图表、比较、计数器 | `references/graphs-and-data.md` |
| **架构图** | 系统描述 | 带有连接的组件构建 | `references/mobjects.md` |
| **3D 可视化** | 3D 概念 | 旋转表面、参数曲线、空间几何 | `references/camera-and-3d.md` |

## 技术栈#

每个项目一个独立的 Python 脚本。无需浏览器、Node.js 或 GPU。

| 层 | 工具 | 用途 |
|-------|------|---------|
| 核心 | Manim Community Edition | 场景渲染、动画引擎 |
| 数学 | LaTeX (texlive/MiKTeX) | 通过 `MathTex` 渲染公式 |
| 视频 I/O | ffmpeg | 场景拼接、格式转换、音频混合 |
| TTS | ElevenLabs / Qwen3-TTS（可选） | 旁白语音覆盖 |

## 流程#

```
PLAN --> CODE --> RENDER --> STITCH --> AUDIO（可选） --> REVIEW
```

1. **PLAN** — 编写 `plan.md`，包含叙事弧、场景列表、视觉元素、调色板、旁白脚本
2. **CODE** — 编写 `script.py`，每个场景一个类，每个都可独立渲染
3. **RENDER** — `manim -ql script.py Scene1 Scene2 ...` 用于草稿，`-qh` 用于制作
4. **STITCH** — ffmpeg 将场景剪辑拼接成 `final.mp4`
5. **AUDIO**（可选）— 通过 ffmpeg 添加旁白和/或背景音乐。参见 `references/rendering.md`
6. **REVIEW** — 渲染预览静止图像，对照计划验证，调整

## 项目结构#

```
project-name/
  plan.md                # 叙事弧、场景分解
  script.py              # 所有场景在一个文件中
  concat.txt             # ffmpeg 场景列表
  final.mp4              # 拼接输出
  media/                 # Manim 自动生成
    videos/script/480p15/
```

## 创意方向#

### 调色板#

| 调色板 | 背景 | 主要 | 次要 | 强调 | 使用场景 |
|---------|-----------|---------|-----------|--------|----------|
| **经典 3B1B** | `#1C1C1C` | `#58C4DD`（蓝色） | `#83C167`（绿色） | `#FFFF00`（黄色） | 通用数学/CS |
| **温暖学术** | `#2D2B55` | `#FF6B6B` | `#FFD93D` | `#6BCB77` | 亲和力 |
| **霓虹科技** | `#0A0A0A` | `#00F5FF` | `#FF00FF` | `#39FF14` | 系统、架构 |
| **单色** | `#1A1A2E` | `#EAEAEA` | `#888888` | `#FFFFFF` | 极简主义 |

### 动画速度#

| 上下文 | 运行时间 | 之后等待 |
|---------|----------|-------------------|
| 标题/介绍出现 | 1.5秒 | 1.0秒 |
| 关键公式揭示 | 2.0秒 | 2.0秒 |
| 变换/变形 | 1.5秒 | 1.5秒 |
| 支持标签 | 0.8秒 | 0.5秒 |
| 淡出清理 | 0.5秒 | 0.3秒 |
| "啊哈时刻"揭示 | 2.5秒 | 3.0秒 |

### 排版尺度#

| 角色 | 字体大小 | 用法 |
|------|-----------|-------|
| 标题 | 48 | 场景标题、开场文本 |
| 标题 | 36 | 场景内的章节标题 |
| 正文 | 30 | 解释性文本 |
| 标签 | 24 | 注释、坐标轴标签 |
| 说明文字 | 20 | 字幕、小号印刷 |

### 字体#

**对所有文本使用等宽字体。** Manim 的 Pango 渲染器在所有尺寸上都使用比例字体产生错误的字距。参见 `references/visual-design.md` 获取完整建议。

```python
MONO = "Menlo"  # 在文件顶部定义一次

Text("Fourier Series", font_size=48, font=MONO, weight=BOLD)  # 标题
Text("n=1: sin(x)", font_size=20, font=MONO)  # 标签
MathTex(r"\nabla L")  # 数学（使用 LaTeX）
```

最小 `font_size=18` 以确保可读性。

### 每场景变奏#

永远不要对所有场景使用相同的配置。对于每个场景：
- **不同的主色**来自调色板
- **不同的布局**——不要总是居中所有内容
- **不同的动画进入**——在 Write、FadeIn、GrowFromCenter、Create 之间变化
- **不同的视觉权重**——一些场景密集，其他稀疏

## 工作流#

### 步骤 1：计划（plan.md）#

在任何代码之前，编写 `plan.md`。参见 `references/scene-planning.md` 获取完整模板。

### 步骤 2：代码（script.py）#

每个场景一个类。每个场景都可独立渲染。

```python
from manim import *

BG = "#1C1C1C"
PRIMARY = "#58C4DD"
SECONDARY = "#83C167"
ACCENT = "#FFFF00"
MONO = "Menlo"


class Scene1_Introduction(Scene):
    def construct(self):
        self.camera.background_color = BG
        title = Text("Why Does This Work?", font_size=48, color=PRIMARY, weight=BOLD, font=MONO)
        self.add_subcaption("Why does this work?", duration=2)
        self.play(Write(title), run_time=1.5)
        self.wait(1.0)
        self.play(FadeOut(title), run_time=0.5)
```

关键模式：
- **每个动画上的字幕**：`self.add_subcaption("text", duration=N)` 或 `subcaption="text"` 在 `self.play()` 上
- **共享色彩常量**在文件顶部以实现跨场景一致性
- **`self.camera.background_color`** 在每个场景中设置
- **干净退出**——在场景结束时淡出所有 mobject：`self.play(FadeOut(Group(*self.mobjects)))`
### 步骤 3：渲染#

```bash
manim -ql script.py Scene1_Introduction Scene2_CoreConcept  # 草稿
manim -qh script.py Scene1_Introduction Scene2_CoreConcept  # 制作
```

### 步骤 4：拼接#

```bash
cat > concat.txt << 'EOF'
file 'media/videos/script/480p15/Scene1_Introduction.mp4'
file 'media/videos/script/480p15/Scene2_CoreConcept.mp4'
EOF
ffmpeg -y -f concat -safe 0 -i concat.txt -c copy final.mp4
```

### 步骤 5：审查#

```bash
manim -ql --format=png -s script.py Scene2_CoreConcept  # 预览静止图像
```

## 关键实现注意事项#

### LaTeX 的原始字符串#

```python
# 错误：MathTex("\frac{1}{2}")  # 转义问题
# 正确：
MathTex(r"\frac{1}{2}")  # 原始字符串
```

### 边缘文本的 buff >= 0.5#

```python
label.to_edge(DOWN, buff=0.5)  # 永远不要 < 0.5
```

### 在替换文本之前淡出#

```python
self.play(ReplacementTransform(note1, note2))  # 不要在其上 Write(note2)
```

### 永远不要动画化未添加的 Mobject#

```python
self.play(Create(circle))  # 必须先添加
self.play(circle.animate.set_color(RED))  # 然后动画化
```

## 性能目标#

| 质量 | 分辨率 | FPS | 速度 |
|---------|-----------|-----|-------|
| `-ql`（草稿） | 854x480 | 15 | 5-15秒/场景 |
| `-qm`（中等） | 1280x720 | 30 | 15-60秒/场景 |
| `-qh`（制作） | 1920x1080 | 60 | 30-120秒/场景 |

始终在 `-ql` 上迭代。仅对最终输出渲染 `-qh`。

## 参考#

| 文件 | 内容 |
|------|----------|
| `references/animations.md` | 核心动画、速率函数、组合、`.animate` 语法、时序模式 |
| `references/mobjects.md` | 文本、形状、VGroup/Group、定位、样式、自定义 mobject |
| `references/visual-design.md` | 12 个设计原则、不透明度分层、布局模板、调色板 |
| `references/equations.md` | Manim 中的 LaTeX、TransformMatchingTex、推导模式 |
| `references/graphs-and-data.md` | 坐标轴、绘图、BarChart、动画数据、算法可视化 |
| `references/camera-and-3d.md` | MovingCameraScene、ThreeDScene、3D 表面、摄像机控制 |
| `references/scene-planning.md` | 叙事弧、布局模板、场景过渡、计划模板 |
| `references/rendering.md` | CLI 参考、质量预设、ffmpeg、旁白工作流、GIF 导出 |
| `references/troubleshooting.md` | LaTeX 错误、动画错误、常见错误、调试 |
| `references/animation-design-thinking.md` | 何时动画化 vs 显示静态、分解、节奏、旁白同步 |
| `references/updaters-and-trackers.md` | ValueTracker、add_updater、always_redraw、基于时间的更新器、模式 |
| `references/paper-explainer.md` | 将研究论文转化为动画——工作流、模板、域模式 |
| `references/decorations.md` | SurroundingRectangle、Brace、箭头、DashedLine、Angle、注释生命周期 |
| `references/production-quality.md` | 预代码、预渲染、后渲染检查清单、空间布局、颜色、节奏 |

---

## 创意分歧（仅当用户请求实验性/创意/独特输出时使用）#

如果用户要求创意、实验性或非传统的解释方法，请选择策略并在设计动画之前通过它进行推理。

- **SCAMPER** — 当用户想要标准解释的新鲜视角时
- **假设逆转** — 当用户想要挑战某事的典型教学方式时

### SCAMPER 变换#

采用标准数学/技术可视化并变换它：
- **替代**：替换标准视觉隐喻（数字线 → 蜿蜒路径，矩阵 → 城市网格）
- **组合**：合并两种解释方法（代数 + 几何同时）
- **逆转**：向后推导——从结果开始并解构到公理
- **修改**：夸大参数以显示为什么它很重要（10倍学习率，1000倍样本大小）
- **消除**：移除所有符号——通过动画和空间关系纯粹解释

### 假设逆转#

1. 列出关于此主题如何可视化"标准"的内容（从左到右，2D，离散步骤，正式符号）
2. 选择最根本的假设
3. 逆转它（从右到左推导，3D 嵌入 2D 概念，连续变形而不是步骤，零符号）
4. 探索逆转揭示了标准方法隐藏了什么
