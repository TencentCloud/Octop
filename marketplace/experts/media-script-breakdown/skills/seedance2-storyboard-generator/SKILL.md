---
name: seedance2-storyboard-generator
description: Professional AI video script and storyboard generator for Seedance 2.0 platform. Use when user asks to: (1) Convert articles/stories into video scripts, (2) Generate Seedance 2.0 storyboard prompts, (3) Plan multi-episode AI video series, (4) Create character/scene/prop generation prompts for image models like Nana Banana Pro. Input can be full novels, articles, or brief story outlines. Output includes four-act script structure, episode breakdown, asset generation prompts, and Seedance 2.0 formatted storyboard scripts.
slug: seedance2-storyboard-generator
displayName: seedance2-storyboard-generator
version: 1.0.0
summary: Professional AI video script and storyboard generator for Seedance 2.0 platform. Use when user asks to: (1) Convert arti
---

# Seedance Storyboard Generator

Expert AI script and storyboard generation system for creating professional AI video series on Seedance 2.0 platform.

## Workflow

Follow this sequential process to convert source material into production-ready video scripts:

### 1. Analyze Input

**Determine input type:**
- **Full text**: Complete novel/article requiring adaptation and episode segmentation
- **Outline**: Brief story concept requiring full script development

**Extract core elements:**
- Protagonist(s) and key characters
- Central conflict and narrative arc
- Setting/world-building elements
- Key plot points and emotional beats

Ask clarifying questions if input is ambiguous or incomplete.

### 2. Confirm Production Parameters

**Essential questions to ask:**

1. **Visual Style**: What visual style? (写实/动画/水墨/科幻/复古/电影感/其他)
2. **Duration**: Total runtime? (Standard: 20 episodes × 15s each ≈ 5 minutes)
3. **Target Platform**: Aspect ratio? (16:9横屏 / 9:16竖屏 / 2.35:1电影宽屏)
4. **Tone**: Overall emotional tone? (史诗/温馨/悬疑/欢快/忧伤等)

Document these parameters for consistent application throughout.

### 3. Generate Four-Act Script Structure

**Structure:**
- **Act 1 (起)**: Episodes 1-5 - Introduction and inciting incident
- **Act 2 (承)**: Episodes 6-10 - Rising action and complications
- **Act 3 (转)**: Episodes 11-15 - Climax and confrontation
- **Act 4 (合)**: Episodes 16-20 - Resolution and conclusion

**For each episode include:**
- Episode number and title
- Duration (standard: 15 seconds)
- Emotional tone/mood
- Key plot points
- Beginning/ending frame description (for continuity)

**Output format:** Markdown document with clear section headers.

### 4. Create Asset Generation Plan

**Categorize and number all visual assets:**

| Category | Prefix | Example | Description |
|----------|--------|---------|-------------|
| Characters | C01-C99 | C01 叶青云·正面全身 | Multiple angles per character |
| Scenes | S01-S99 | S01 青锋山废墟 | Key locations |
| Props | P01-P99 | P01 青锋剑 | Important objects |

**Asset generation prompt format:**
```
### [编号] — [名称]

[Style prefix], [detailed visual description in English], [technical specs]

**Style Prefix Examples:**
- Chinese ink wash painting style mixed with anime cel-shading
- Cinematic photorealistic style with dramatic lighting
- 3D Pixar-style animation rendering
- Sci-fi cyberpunk aesthetic with neon lighting

**Character differentiation:** Use distinct color schemes and visual markers for each character to ensure recognition in the chosen art style.
```

**Output format:** Organized list with unique IDs, suitable for copy-pasting into image generators.

### 5. Generate Seedance 2.0 Storyboard Scripts

**For each episode, produce:**

**a. Asset Upload List**
```
图片1: C01 (角色参考)
图片2: S03 (场景参考)
图片3: P01 (道具参考)
```

**b. Seedance Prompt (Time-axis format)**
```
[风格描述]，[画幅比例]，[整体氛围]

0-3s画面：[镜头运动]，[场景建立]，[主体引入]
3-6s画面：[镜头运动]，[情节发展]，[动作描述]
6-9s画面：[镜头运动]，[高潮/冲突]，[情绪爆发]
9-12s画面：[镜头运动]，[转折/过渡]
12-15s画面：[镜头运动]，[结尾/落版]

【声音】[配乐风格] + [音效] + [对白/旁白]

【参考】@图片1 [用途]，@图片2 [用途]...
```

**c. Ending Frame Description**
- Document the final frame content for next episode continuity

**Camera movement keywords:** 推镜头/拉镜头/摇镜头/移镜头/跟镜头/环绕镜头/升降镜头/希区柯克变焦/一镜到底/手持晃动

**For episode chaining (Ep 2+):** Start prompt with `将@视频1延长15s` and upload previous episode as video reference.

## Output Files

Generate these deliverable files:

1. **[Title]_剧本.md** - Complete four-act script with episode breakdown
2. **[Title]_素材清单.md** - All character/scene/prop generation prompts
3. **[Title]_E[XX]_分镜.md** - Individual episode storyboard scripts (or combined)

## Quality Assurance

**Before finalizing:**
- Verify all asset references (@图片X) have corresponding IDs in asset list
- Check episode-to episode continuity (ending frame → opening frame)
- Ensure time-axis coverage spans complete 15 seconds
- Validate that camera movements are feasible and logically sequenced

## Reference Material

For detailed Seedance 2.0 prompt patterns, templates, and best practices, see [references/seedance-manual.md](references/seedance-manual.md).

Key reference sections:
- Templates 1-16 for different video types (叙事/产品/角色/风景/战争/等)
- Camera movement quick reference
- Atmosphere keyword library
- Multimodal reference syntax (@图片X, @视频X, @音频X)

## Common Pitfalls to Avoid

1. **Sensitive words**: Seedance may reject content with certain terms. Avoid common triggers or use alternative phrasing.
2. **Over-complex prompts**: Long prompts (300+ words) may have inconsistent instruction following. Prefer clarity over verbosity.
3. **Missing continuity**: Always document ending frames and verify next episode starts with matching scene.
4. **Inconsistent style**: Apply same visual style prefix to all asset generation prompts.
