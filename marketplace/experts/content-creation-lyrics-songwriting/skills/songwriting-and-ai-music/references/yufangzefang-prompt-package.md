# 《遇方则方》— 参考示例：中国风rap完整prompt包

> 此文件用作 songwriting-and-ai-music skill 的完整工作示例。
> 标签：中国风 / 低男声念白rap / 截拳道 / 水哲学 / 单押双押三押

## 创作背景

此曲为响应"中国风rap + 李小龙武术"创作要求的结果。使用 creative-ideation 约束库生成3个方向，选定方向一"Be Water"后，歌词经历两版迭代（自由版→韵脚加强版）。

## 歌曲基本信息

- 歌名：《遇方则方》
- 风格：中国风武侠rap，低男声念白+旋律爆发
- BPM：~75
- 调式：Pentatonic minor, D tonic
- 结构：Intro - Verse1 - Chorus - Verse2 - Chorus - Bridge - Verse3 - Outro

## Style 字段（英文，Suno Custom Mode）

### 精简版（~640字符，直接复制）

```
Chinese martial arts wuxia rap, low male voice spoken-word rap, guqin foundation. Pure Chinese instruments only. NO western instruments. Chinese barrel drum instead of 808. Pentatonic minor, D key, BPM ~75. Opens with a stone chime. Verses are half-whispered with dense internal rhymes. Chorus is a highly melodic sung hook — "遇方则方 遇圆则圆" must be catchy and melodic, sung with Peking opera quaver on held syllables. Bridge has silence, voice only. Outro fades to nothing. Guqin harmonics between lines. Dynamic arc: whisper → tension → melodic hook → silence → fade.
```

### 完整参考版（~543字符，含更详细描述）

```
Chinese martial arts wuxia rap, low male voice spoken-word rap, guqin foundation. Pure Chinese instruments only. NO western instruments. Chinese barrel drum instead of 808. Pentatonic minor, D key, BPM ~75. Opens with a stone chime. Verses are half-whispered, controlled tension with dense internal rhymes and multi-syllable rhyme patterns. Chorus is a highly melodic sung hook — the line "遇方则方 遇圆则圆" must be catchy and song-like, sung with a slight Peking opera quaver on held final syllables, not shouted. Bridge has two beats of silence — voice only. Outro strips to nothing. Guqin harmonics between lines. Dynamic arc: whisper → tension → melodic explosion → silence → fade.
```

## 韵辙分布（中文rap押韵方案参考）

| 段落 | 韵辙 | 示例 |
|------|------|------|
| Intro | 江阳辙 -ang/-iang/-uang | 强/刚/狂/钢/黄/撞/伤 |
| Verse 1 | 言前辙 -an/-ian/-uan | 板/颤/慢/点/路/输/形/钉/穿/瓣/遍/乱/软 |
| Chorus | 江阳辙 -ang/-iang/-uang | 方/圆/钻/路/感/状/挡/淌/江 |
| Verse 2 | 中东辙 -ong/-iong | 周/空/痛/松/碰/用/渗/缝/弓/远/头/留 |
| Bridge | 灰堆 -ei / 一七 -i 交替 | 水/争/胜/装/变/天 |
| Verse 3 | 由求辙 -ou/-iu | 懂/手/空/走/输/处/了/湖/当/窗/人/江 |

## 韵脚密度说明

- **单押：** 每段尾字统一韵辙。如 Verse 1 全部落 -an/ian/uan
- **双押：** 每行末两字押韵。如 Chorus 的「形状/挡/淌/江」- 全部押 -iang/uang
- **三押：** 末三字押韵。如 Chorus 的「渗过去/从缝隙钻」- 全部押 -ian/-i/uan (句中节奏点+尾韵)
- **句中内韵：** 如 Verse1「越练越紧 越紧越僵 越僵越慢」- 紧/僵/慢 三字三韵递进

## 实践经验教训

1. **Style 字段推荐用英文**——中文描述会被 Suno 降级处理，英文效果更好
2. **Style 字段上限 1000 字符**，要在有限空间内集中传达关键信息（乐器、动态弧线、人声特色、hook要求）
3. **Exclude Styles 很重要**——中国风必须排除所有西方乐器/曲风，否则 Suno 默认会混入钢琴和流行鼓点
4. **歌词中的 [Silence] metatag 在 bridge 处效果极佳**，符合中式"留白"美学
5. **双版递进创作**——先出自由版定情绪方向，再出韵脚版注入密度，可以满足不同审美需求

## 来源

- 歌词初稿：自由版
- 韵脚加强版：同上歌词的 v2 版本
- Suno prompt 包：见本文档