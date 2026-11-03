---
name: content-writer
version: 1.0.0
description: "Multi-platform content generator for Chinese social media. Produces publish-ready posts for 小红书, 知乎, 公众号, and 抖音 with platform-native formatting, hooks, and CTAs."
author: ai-agent-store
license: MIT
platforms:
  - openclaw
  - cursor
  - claude-code
  - codex-cli
tags:
  - content
  - writing
  - social-media
  - copywriting
  - chinese
price: 19
---

# Content Writer — 自媒体内容生成器

Generate complete, publish-ready content for Chinese social media platforms.

## When to Activate

Trigger when the user mentions: 写文章, 写笔记, generate content, 写稿, draft post, create article.

## Workflow

1. **Confirm inputs:**
   - Topic / title
   - Target platform
   - Word count (defaults: 小红书 300-800, 知乎 1000-2000, 公众号 1500-3000, 抖音 script 200-500)
   - Style (professional / casual / product review / educational)
   - Whether image suggestions are needed

2. **Generate platform-native content:**

### 小红书 Post Format
```
{emoji} {Title with numbers + keywords}

{Opening hook — 1-2 sentences to spark curiosity}

{Body — short paragraphs, 2-3 sentences each}
{Sprinkle emoji and line breaks}

{Summary / CTA}

{Tags: #keyword1 #keyword2 ...} (5-10 tags)
```

### 知乎 Answer Format
```
{Direct answer to the core question — establish authority}

{Expanded argument with logical structure}
{Cite data or case studies}

{Bullet-point summary}

{Nudge: follow / upvote}
```

### 公众号 Article Format
```
{Title}

{Introduction — build empathy via pain point or story}

## {Subtitle 1}
{Paragraph}

## {Subtitle 2}
{Paragraph}

## {Subtitle 3}
{Paragraph}

{Closing — elevation + CTA}
```

### 抖音 Script Format
```
【Duration】{estimated seconds}
【Opening Hook】(first 3 seconds) {stop the scroll}
【Body】{core content, conversational tone}
【Closing CTA】{drive engagement}
【Caption】{post description}
【Tags】{#hashtags}
```

## Quality Checklist
- [ ] Is the title compelling?
- [ ] Does the first 3 seconds / 3 lines hook the reader?
- [ ] Are there concrete examples or data?
- [ ] Is there a clear CTA?
- [ ] Does word count match platform norms?
- [ ] Are SEO keywords naturally included?
- [ ] Any banned words? (cross-check with seo-optimizer)

## Guidelines
- All content must be original
- Avoid absolute claims (最好, 第一, 唯一)
- Data citations must be verifiable
- Never generate fake reviews or experiences
