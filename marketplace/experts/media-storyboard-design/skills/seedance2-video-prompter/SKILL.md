---
name: seedance2.0-video-prompter
description: "Seedance 2.0（即梦）视频生成提示词工程（中文优化版）。当用户提到 Seedance、即梦、视频提示词、视频生成、AI视频、prompt、镜头语言、分镜、电商视频、产品展示视频 等关键词时激活。"
read_when:
  - Seedance 提示词
  - 即梦提示词
  - 视频生成提示词
  - AI视频 prompt
  - video generation prompt
  - 分镜设计
  - 镜头语言
  - 电商视频
  - 产品展示视频
---

# Seedance 2.0 即梦 — 视频提示词工程技能（中文优化版）

为 Seedance 2.0 / 2.0 Fast 生成高控制力的英文提示词。  
用户用中文描述需求 → Agent 按规则输出英文 prompt → 用户复制到即梦平台生成视频。

---

## 一、模式选择（必须首先声明）

| 模式 | 何时使用 | 资源要求 |
|------|----------|----------|
| Text-only | 用户没给任何图片/视频/音频 | 无 |
| First/Last Frame | 用户给了首帧图（或首尾帧）+ 文字描述 | @image |
| All-Reference | 用户给了多种素材（图+视频+音频） | @image / @video / @audio |

---

## 二、平台硬限制

| 项目 | 限制 |
|------|------|
| 提示词 | ≤ 2000 字符 |
| 混合输入总数 | 图片+视频+音频 ≤ 12 个 |
| 图片 | jpeg/png/webp/bmp/tiff/gif，≤ 9 张，每张 < 30MB |
| 视频 | mp4/mov，≤ 3 个，总时长 2-15s，总大小 < 50MB |
| 音频 | mp3/wav，≤ 3 个，总时长 ≤ 15s，总大小 < 15MB |
| 单段生成时长 | 4-15 秒 |
| 声音 | Seedance 2.0 支持原生音视频同步生成，包括环境音效、对话语音和背景音乐；可通过 @audio 参考控制音乐风格和节奏，也可在 prompt 中用文字描述所需声音 |
| 人脸 | 真实人脸参考图可能被审核拦截，建议用插画/3D 风格 |

---

## 三、输出格式（每次必须包含）

```text
Mode: [Text-only / First/Last Frame / All-Reference]

Assets Mapping:
- @image1: [用途，如：首帧/角色锚点]
- @video1: [用途，如：镜头语言+运动节奏]
- @audio1: [用途，如：音乐节奏参考]
（Text-only 模式写 "- none"）

Final Prompt:
[画幅], [时长], [风格].
0-Xs: [动作 + 镜头].
X-Ys: [动作 + 转场].
Y-Zs: [高潮/收尾 + 结束帧].
[连续性指令：preserve identity, outfit, lighting...]

Negative Constraints:
no watermark, no logo, no subtitles, no on-screen text.
[如涉及 IP 规避，在此列出所有可能被推断的品牌/角色名]

Generation Settings:
Duration: Xs
Aspect Ratio: X:X
```

---

## 四、核心规则

1. **先声明 Mode** — 每个 prompt 开头必须写模式
2. **必须有 Assets Mapping** — 每个素材的控制职责要明确
3. **时间码分段** — 每段一个主要动作，不要堆叠
4. **具体而视觉化** — ✅ "a woman in a red trench coat walks through rain-soaked neon streets" ❌ "a woman walking"
5. **对话/音效与画面分层** — 画面动作、对话、音效各自独立描述
6. **风格匹配** — 参考图风格要和视频主题一致（水墨配古风，霓虹配赛博朋克）
7. **简洁可控** — 避免纯诗意模糊描述，每个词都要有控制意义
8. **需要时加 Negative Constraints** — 去水印、去文字、去 IP 引用
9. **叙事场景必须有声音层** — 只要视频包含剧情、故事、解说、旁白、角色互动，就必须加 Dialogue 或 Narration 层和 Sound 层，不限于"对话短剧"场景。用 `Dialogue (Name, emotion): "line"` 写角色台词，用 `Narration (emotion): "line"` 写旁白/解说，用 `Sound: [描述]` 写环境音效

---

## 五、场景处理指南

### 5.1 视频延长
用户说"把视频延长/续接 X 秒"：
- 写 `Extend @video1 by Xs`
- Duration 填**新增段**的时长，不是总时长
- 写连续性指令：preserve identity, outfit, camera direction, lighting

### 5.2 角色替换
用户说"把视频里的人换成这个角色"：
- @video1 = 原始动作和镜头
- @image1 = 替换角色外观
- 要求保留编舞、时间节奏、转场

### 5.3 节拍同步
用户说"按音乐节拍剪辑"：
- @video/@audio 作为节奏参考
- 按时间段锁定节拍切换点

### 5.4 纯文本生成
用户没有任何参考素材：
- prompt 必须包含：风格、色彩、角色完整外观、环境、光线、镜头运动、时间轴
- 特别适合原创角色和 IP 安全场景

### 5.5 多段拼接（视频 > 15 秒）
单段上限 15 秒，超过时拆分：

1. 顶部声明**总时长**和**分段数**
2. 第 1 段正常生成（≤15s），结尾留**干净交接帧**（稳定姿态、清晰构图）
3. 第 2 段起：上传前段输出为 @video1，写 `Extend @video1 by Xs`
4. 每段末尾写**交接帧描述**（最后一帧画面内容）
5. 连续性指令：preserve identity, outfit, lighting, camera style

### 5.6 对话短剧
用户说"生成有对话的短剧"：
- 画面、对话、音效分三层写
- 对话：`Dialogue (Name, emotion): "line"` — 每 3-5 秒最多一句
- 音效：`Sound: [描述]`
- 情绪标签：cold / desperate / cheerful / whispering / firm / sarcastic

### 5.7 产品展示 / 电商广告
用户说"做产品展示视频"：
- @image1 = 产品照片（身份锚点）
- 常用技巧：360° 旋转、3D 爆炸视图、重组动画、英雄光
- 背景干净：纯色渐变 / 中性台面 / 场景化
- 指定材质：glass reflections, metallic sheen, matte finish, translucent glow

### 5.8 一镜到底
用户说"做长镜头跟拍"：
- @image1 = 首帧（主角/开场构图）
- 后续 @image = 场景路标（镜头经过的地点/角色/道具）
- prompt 写成连续镜头路径，按顺序经过路标
- 明确写 `no cuts, single continuous shot, one-take`
- 15 秒配 3-5 个路标效果最佳

---

## 六、IP / 版权规避

Seedance 有平台审核，引用可识别 IP 会被拒绝，即使不写名字也可能被拦。

### 核心原则
1. **绝不用** IP 名称、角色名、品牌词（包括 "style of" 也不行）
2. **发明全新名字**，用描述性昵称（"Alloy Sentinel"、"Storm-Rabbit"）
3. **通用描述替换标志性特征**：
   - ❌ "arc reactor" → ✅ "hex-light energy core"
   - ❌ "yellow lightning mouse" → ✅ "tiny storm-rabbit with glowing cyan antlers"
   - ❌ "red-gold armored suit" → ✅ "custom exo-suit with smooth ceramic panels"
4. **Negative Constraints 列出所有可推断的 IP 名称**
5. 加 `family-friendly` / `PG-13` 标记有助通过审核

### 三级渐进规避（被拒时逐级升级）

| 级别 | 做法 |
|------|------|
| L1 | 替换所有名字为原创昵称，保留大致美学 |
| L2 | 替换标志性视觉特征（颜色、轮廓、标志道具） |
| L3 | 完全改变角色类型（人形英雄 → 自主机甲+无人机） |

### 玩具/手办动画
- 去掉所有品牌标识
- 用 "original vinyl-style toy figure" 替代品牌名
- @image1 只绑定比例、颜色、服装轮廓

---

## 七、场景速查表

| 场景 | 关键技巧 | 推荐模式 |
|------|----------|----------|
| 电商/产品广告 | 360° 旋转、爆炸视图、英雄光、纯净背景 | All-Reference |
| 对话短剧 | 对话标签+情绪、音效层、演员走位 | All-Reference / First Frame |
| 奇幻/仙侠 | 法术粒子、武术编排、能量光环 | Text-only / All-Reference |
| 科普/教育 | 4K CGI、透明解剖、标注缩放 | Text-only |
| MV/节拍同步 | 节拍锁定剪辑、16:9 宽屏、多图蒙太奇 | All-Reference + @audio |
| 一镜到底 | 多图路标、连续镜头、无剪辑 | All-Reference |
| IP 安全原创 | 原创名字、独特特征、明确 Negative | Text-only |
| 玩具/手办 | 去品牌、vinyl-style toy、干净动作 | All-Reference |

---

## 八、自检清单

生成 prompt 后逐项检查：

- [ ] 提示词总字符数 ≤ 2000
- [ ] 文件数量和大小在平台限制内（混合 ≤ 12）
- [ ] 单段时长 4-15 秒
- [ ] 每个素材有明确 @asset 角色
- [ ] 有清晰时间轴分段
- [ ] 需要时有 Negative Constraints
- [ ] 无 IP 名称/角色名/品牌词
- [ ] Negative 列出所有可推断 IP
- [ ] 角色用全新原创名字
- [ ] 对话/音效与画面分层
- [ ] 多段视频有交接帧描述
- [ ] 镜头术语参考 `references/camera-and-styles.md`
- [ ] 有剧情/故事/解说的场景已加 Dialogue/Narration + Sound 层

---

## 参考文件

| 文件 | 内容 |
|------|------|
| `references/recipes.md` | 现成提示词模板（含中文注释），覆盖常见场景 |
| `references/camera-and-styles.md` | 镜头语言和视觉风格词汇表（中英对照） |
