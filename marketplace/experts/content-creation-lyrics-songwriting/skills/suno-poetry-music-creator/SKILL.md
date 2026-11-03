---
name: suno-poetry-music-creator
description: Enhanced Suno song creator with reference song analysis and intelligent lyric optimization. Analyzes user's reference songs to extract style, mood, and structure patterns. Iteratively optimizes lyrics based on Suno generation feedback. Creates AI-generated songs with Suno that match user's musical preferences. Use when user wants to create AI-generated songs, optimize lyrics, analyze reference tracks, or create Chinese classical style songs with proper rhyme and tonal patterns.
---

# Suno Song Creator Enhanced 🎵✨

Transform creative themes into AI-generated songs with Suno, now with reference song analysis and intelligent lyric optimization.

## When to Use

- User wants to create a song similar to a reference track
- User says "make a song like [artist/song]..."
- User wants to optimize lyrics after Suno generation
- User needs help matching a specific musical style
- User wants to turn poetry into a song with specific genre constraints
- User wants to create Chinese classical style songs with proper rhyme and tonal patterns

## Quick Start

```
User: "创作一首关于春天的歌，风格像周杰伦的《青花瓷》"
→ 分析参考歌曲 → 生成歌词 → 优化 → 输出 Suno 风格标签
```

## Complete Workflow

### Phase 1: Discovery
1. Understand theme/concept
2. Ask for reference song (optional but recommended)
3. Determine target mood and style
4. Identify cultural/linguistic context

### Phase 2: Research & Analysis

**IF reference provided:**
→ Analyze reference song characteristics (see [references/lyric-examples.md] for analysis framework)
→ Extract style DNA → Map to Suno tags

**ELSE:**
→ Use default style selection
→ Research poetry for theme

**IF Chinese classical style:**
→ Consult [references/chinese-rhyme.md] for rhyme scheme
→ Apply tonal patterns and couplet techniques

### Phase 3: Creation - First Draft
1. Generate initial lyrics with proper structure
2. Create style tags based on analysis
3. Present complete package to user

### Phase 4: Poetic Elevation ⬆️
Transform first draft into poetic version:
- Apply personification and metaphor
- Enhance sensory details (sound, touch, smell)
- Create dynamic imagery
- Elevate personal emotions to universal themes
- Add musical arrangement guidance

See [references/lyric-examples.md] for detailed examples.

### Phase 5: Optimization (if needed)
**IF user wants changes:**
→ Identify specific issues
→ Apply optimization rules
→ Generate improved version
→ Repeat up to 3 times

## Reference Song Analysis 🎧

When user provides a reference song/artist:

**Step 1: Extract Reference Information**
```
Artist: [Artist Name]
Song: [Song Title]
Genre: [Inferred Genre]
Era: [Time Period]
Mood: [Emotional Tone]
```

**Step 2: Analyze Musical Characteristics**
Use web search to find:
- Song structure (Verse-Chorus pattern, Bridge placement)
- Instrumentation and arrangement style
- Vocal style and range
- Tempo and rhythm characteristics
- Lyrical themes and imagery patterns

**Step 3: Extract Style DNA**
```yaml
Reference Analysis:
  genre: [Primary Genre]
  sub_genre: [Sub-style]
  tempo: [BPM range or descriptor]
  mood: [Emotional profile]
  instrumentation: [Key instruments]
  vocal_style: [Vocal characteristics]
  lyrical_density: [Wordy/Minimal/Average]
  rhyme_scheme: [Rhyme pattern]
  chorus_hook: [Hook style]
```

**Step 4: Map to Suno Style Tags**
```
[Genre], [Sub-genre], [Mood], [Instrumentation], [Vocal Style]
```

## Lyric Optimization Loop 🔄

When Suno generation doesn't meet expectations:

**Step 1: Analyze Feedback**
Identify issues:
- ❌ Lyrics too long/short for melody
- ❌ Words don't flow well with music
- ❌ Emotion not matching style
- ❌ Pronunciation issues
- ❌ Need more/less repetition
- ❌ Lacks poetic depth or imagery
- ❌ Too plain or cliché

**Step 2: Apply Optimization Rules**

**Rule 1: Poetic Elevation** ⬆️
Transform plain descriptions into poetic imagery:
```
Before: 春风拂柳绿枝芽
After:  春风借柳 织几抹新芽
```
Techniques: Personification, sensory details, dynamic action
See [references/lyric-examples.md] for complete examples.

**Rule 2: Length Adjustment**
- Target: 4-8 syllables per line for most genres
- Break long lines or combine short ones

**Rule 3: Flow Improvement**
- Eliminate tongue twisters
- Soften hard consonants at line ends
- Add alliteration or assonance

**Rule 4: Emotional Alignment**
- Match word intensity to music energy
- High energy → Strong, active verbs
- Soft music → Gentle, flowing imagery

**Rule 5: Repetition Strategy**
- Chorus: 60-70% repeated phrases
- Verse: 20-30% internal repetition
- Bridge: Fresh content, minimal repetition

**Rule 6: Emotional Depth Enhancement** 💫
```
Before: 莫道离别苦 / 且将思念藏
After:  莫叹离别苦 / 岁月暗流藏
```
Techniques: Personal→Universal, metaphorical depth, philosophical undertones

## Chinese Classical Style Guide

For Chinese classical style songs:

1. **Consult [references/chinese-rhyme.md]** for 《中华新韵》14韵部
2. **Choose one rhyme category** and stick to it throughout the song
3. **Apply tonal patterns** - alternate between level (平) and oblique (仄) tones
4. **Use couplet techniques** - parallel structure in adjacent lines

**Example couplet:**
```
春风拂柳 / 细雨润物  (春风对细雨，拂柳对润物)
流水无情 / 青山有意  (流水对青山，无情对有意)
```

## Style Tag Library

### By Genre
```
Pop: Pop, Catchy, Radio-friendly, Modern
Rock: Rock, Electric Guitar, Energetic, Driving
Jazz: Jazz, Smooth, Saxophone, Sophisticated
Classical: Classical, Orchestral, Cinematic, Epic
Electronic: Electronic, Synth, EDM, Upbeat
Folk: Folk, Acoustic, Storytelling, Intimate
R&B: R&B, Soulful, Groove, Smooth
Hip-Hop: Hip-Hop, Rap, Beats, Urban
Chinese Classical: Chinese Classical, Folk, Erhu, Guzheng, Female Vocal, Melancholic, Cinematic
```

### By Mood
```
Happy: Upbeat, Cheerful, Bright, Positive
Sad: Melancholic, Somber, Emotional, Tearful
Energetic: High Energy, Intense, Powerful, Driving
Calm: Peaceful, Relaxing, Gentle, Serene
Romantic: Love, Passionate, Tender, Intimate
Dark: Moody, Brooding, Mysterious, Intense
```

## Best Practices

1. **Always ask for reference** - Even vague references help ("like 80s synth-pop" or "similar to Adele's ballads")

2. **Iterate based on feedback** - Don't expect perfection on first try

3. **Match style to content** - Sad lyrics need appropriate musical backing

4. **Keep Suno's limitations in mind**:
   - ~120-150 words maximum for best results
   - Shorter phrases work better
   - Clear enunciation helps
   - Repetition is your friend for hooks

5. **Cultural sensitivity** - When adapting classical poetry, respect the original meaning while making it singable

6. **Poetic Elevation is key** - First drafts are often plain; always look for opportunities to elevate

7. **Learn from feedback** - When users share improved versions, analyze what changed and why

## Integration with Tools

- **web_search**: Research reference songs and artists
- **browser**: Suno automation and reference listening
- **gemini**: Poetry research and lyric generation
- **image**: Analyze album artwork for style cues (if provided)

## Safety & Ethics

- Respect artist copyrights - analyze style, don't copy lyrics
- Inform users about Suno's terms of service
- Credit original poets when adapting classical works
- Be mindful of cultural appropriation when using traditional styles
