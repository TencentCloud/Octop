---
name: insight-song
version: 1.0.1
description: Transform technical insights into Suno-ready songs with lyrics, style tags, and emotional arc
author: Live Neon <hello@liveneon.ai>
homepage: https://github.com/live-neon/skills/tree/main/creative/insight-song
repository: leegitw/insight-song
license: MIT
tags: [creative, songwriting, suno, lyrics, music, synthesis, reflection, learning, technical-writing]
layer: creative
status: active
alias: song
user-invocable: true
emoji: 🎵
---

# insight-song (歌)

Transform technical conversations and insights into songs formatted for Suno.ai.
Creates lyrics with emotional arc that mirrors the technical journey, complete with
style tags and section markers.

**Trigger**: 明示呼出 (explicit invocation) or when deep technical insight emerges

**Core insight**: "Creation forces synthesis. Making a song about a concept reveals
gaps that passive understanding cannot."

## Installation

```bash
openclaw install leegitw/insight-song
```

**Dependencies**: None (standalone creative skill)

**Data handling**: This skill synthesizes content from user-supplied input or the current
conversation context (default). It does NOT read files from the workspace or access project
artifacts directly. Results are returned to the invoking agent, who decides how to use them.

## What This Solves

Technical insights fade with context compression. Songs provide audio reinforcement
that makes concepts memorable and transferable. This skill:

1. **Synthesizes** technical conversations into narrative arc
2. **Transforms** abstract concepts into singable lyrics with visual imagery
3. **Formats** output for direct use with Suno.ai

**The insight**: Technical principles conveyed through metaphor and emotional arc
stick better than documentation alone.

## Usage

```
/song [topic]
```

## Arguments

| Argument | Required | Description |
|----------|----------|-------------|
| topic | No | Topic focus (default: synthesize current conversation) |

## Pre-Requisites

Before creating a song, ensure:

1. **Sufficient conversation depth** — Surface-level summaries don't make good songs
2. **Clear narrative arc** — Problem → Discovery → Solution → Impact
3. **Main work documented** — Save current progress first if mid-task

### Context Understanding Checklist

You must be able to answer:

| Question | What It Means |
|----------|---------------|
| Core insight? | Not "we talked about X" but "we discovered X solves Y" |
| Problem solved? | The pain point, not just the topic |
| Why, not just what? | The reasoning, not just the outcome |
| Substantial depth? | Teaches something new, not standard practice |

### Red Flags (Don't Create)

- Surface-level summary of conversation
- Don't understand why a decision was made
- Insight is just standard practice
- No clear narrative arc
- Vague lyrics that could apply to anything

## Output Format

### Suno.ai Song Format

```markdown
## Song

**Title**: [Song Name]

**Suno.ai Style Tags**:
[300-500 characters describing musical style, mood, instrumentation]

[Verse 1]
[Lyrics conveying the problem/pain]

[Chorus]
[Core message, repeatable, memorable]

[Verse 2]
[Discovery/insight]

[Bridge]
[Technical depth through metaphor]

[Chorus]

[Outro]
[Resolution/call to action]
```

### Song Rules

| Rule | Description |
|------|-------------|
| Tell a story | Beginning, middle, end with clear arc |
| Technical but singable | Don't sacrifice accuracy for rhyme |
| Visual imagery | Designed for audio+visual reinforcement |
| Emotional arc | Matches the technical journey |
| NO literal specifics | Use metaphor and symbol, not file names or metrics |
| NO artist names | Extract essence, not references |

### Example: Good vs Bad Lyrics

**Bad** (too literal):
```
We fixed the bug in handler.go
The timeout was set to 300
```

**Good** (metaphorical):
```
Three in the morning, the logs are all silent
System's on fire but the metrics don't know
Building in darkness, no baseline to measure
Can't debug what you've never seen before
```

## Core Logic

### Step 1: Synthesize Conversation

- Read full conversation context
- Identify key decisions, "aha" moments
- Extract core insight or pattern

### Step 2: Identify Narrative Arc

| Element | Question |
|---------|----------|
| Problem | What was broken/painful? |
| Discovery | What did we learn? |
| Solution | What pattern emerged? |
| Impact | Why does this matter? |

### Step 3: Write Song

**Structure** (flexible):
- Intro: Set the problem/context
- Verse 1: The pain/current state
- Verse 2: The discovery/insight
- Bridge: Technical depth through metaphor
- Chorus: Core message (repeatable, memorable)
- Outro: Resolution/call to action

### Step 4: Format for Suno

- Add title
- Write 300-500 character style tags
- Add section markers: `[Verse 1]`, `[Chorus]`, `[Bridge]`, etc.

## Example

### Input: Bootstrap Observability Insight

**Context**: Discovered reproduce-to-debug problem. Introduced Bootstrap → Learn → Enforce phases.

**Narrative arc**:
- **Problem**: Debugging without reproduction is impossible
- **Discovery**: Greenfield systems don't know what "normal" is
- **Solution**: Bootstrap → Learn → Enforce phases
- **Impact**: Debug with sight instead of in darkness

### Output

**Title**: Bootstrap Before You Break

**Suno.ai Style Tags**:
```
Atmospheric indie folk with building intensity, finger-picked acoustic guitar opening,
gradually adding warm synth pads and driving drums, introspective male vocals with
occasional harmonies, dynamic shifts between quiet verses and powerful choruses,
ethereal reverb on bridge section, cinematic crescendo finale
```

```
[Verse 1]
Three in the morning, the logs are all silent
System's on fire but the metrics don't know
Building in darkness, no baseline to measure
Can't debug what you've never seen before

[Chorus]
Bootstrap before you break
Learn the patterns while you wait
Enforce what the data shows
Now you see where the failure goes

[Verse 2]
Started collecting every signal
Cast the net wide, caught it all
Fourteen days of patient watching
Now we know what normal's called
```

## Integration

- **Layer**: Creative
- **Depends on**: None (standalone)
- **Used by**: side-quests (combo skill)
- **Complements**: visual-concept, ted-talk

## Failure Modes

| Condition | Behavior |
|-----------|----------|
| Insufficient context | Ask clarifying questions first |
| No clear narrative arc | Decline, explain what's missing |
| Surface-level topic | Suggest deeper exploration first |

## Security Considerations

**Input sources:**
- User-supplied context (if provided)
- Current conversation context (default)

**What this skill does NOT do:**
- Read files from the workspace
- Access project artifacts directly
- Send data to external services
- Call external APIs

**Output behavior:**
This skill returns the song directly to the invoking agent. The agent can then display,
save, or pass the result to another skill as needed.

**Provenance note:**
This skill is developed by Live Neon (https://github.com/live-neon/skills) and published
to ClawHub under the `leegitw` account. Both refer to the same maintainer.

## Quality Checklist

- [ ] Can explain core insight in one sentence
- [ ] Understand why, not just what
- [ ] Song tells story with beginning, middle, end
- [ ] Emotional arc matches technical journey
- [ ] No literal specifics (file names, metrics, etc.)
- [ ] Style tags are 300-500 characters
- [ ] Section markers present: [Verse], [Chorus], [Bridge], etc.

## Acceptance Criteria

- [ ] `/song` synthesizes input or conversation into Suno-ready format
- [ ] Output includes title, 300-500 char style tags, sectioned lyrics
- [ ] Lyrics convey technical insight through metaphor
- [ ] Emotional arc matches the technical journey
- [ ] Result returned to invoking agent

---

*Part of the Live Neon Creative Suite.*
