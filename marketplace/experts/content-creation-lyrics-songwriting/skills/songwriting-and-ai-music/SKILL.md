---
name: ai-song-creation
description: "Complete AI song creation pipeline — from idea to Suno AI music production. Covers creative ideation, lyric writing, and Suno prompt engineering."
tags: [songwriting, music, suno, lyrics, creative, ideation, ai-music]
platforms: [linux, macos, windows]
triggers:
  - write a song
  - song lyrics
  - music prompt
  - suno prompt
  - parody song
  - idea for a song
  - create music
  - AI music generation
  - I want to make a song
  - generate a track
---

# AI Song Creation — From Idea to Suno

A complete pipeline for creating songs with AI: **Ideation → Lyrics → Production**.

Each phase has a clear input and output. You can enter at any phase — if you already have a concept, skip to Phase 2. If you have lyrics and just need Suno production, skip to Phase 3.

```
Phase 1: Ideation       ──→  Concept Brief
Phase 2: Lyrics         ──→  Completed Lyrics
Phase 3: Suno Production ──→  Suno-ready Prompt Package
```

---

## Phase 1: Ideation — Where Songs Come From

### 1.1 If You Have No Direction

Use a **creative constraint** to generate song concepts. The constraint provides direction without prescribing the answer — it's a frame, not a cage.

**How it works:**
1. Pick a constraint from the library below (random or matched to the vibe you want)
2. Generate 3 concrete song concepts that satisfy it
3. User picks one to develop

#### Constraint Library for Songwriting

**High concept, low effort** — Best for when you want depth without overthinking:
> A deep idea, lazily executed. The concept should be brilliant. The production should be a single session. If it takes longer, you're overthinking it.
> *Examples: A song from the perspective of a forgotten object. A duet between two seasons. A love song addressed to a programming language.*

**Subtract** — Best for minimalist, atmospheric, or meditative songs:
> How much can you remove before it stops being a song? Strip a song to its minimum viable form. Delete until only the essence remains.
> *Examples: A 4-line song that repeats. One verse, no chorus, one instrument. A song made of silence interrupted by three words.*

**Start at the punchline** — Best for witty, narrative, or surprising songs:
> Think of a line that would be a great song title or hook. Work backwards to make it real.
> *Examples: "I taught my coffee machine about mortality." "The GPS said 'recalculating' for the 47th time and I answered."*

**Text is the universal interface** — Best for lyric-forward, story-driven songs:
> What if the song has no genre — just words? A letter set to music. A voicemail. A Wikipedia article sung straight.
> *Examples: A break-up song structured entirely as commit messages. A recipe as a torch song.*

**Blatantly copy something** — Best for learning or getting unstuck:
> Pick a song you admire. Write new lyrics over its structure. The learning is in the gap between your version and theirs.
> *Effectively a parody approach — see Phase 2.6 for the full method.*

**Make something that dies** — Best for melancholic, ephemeral themes:
> A song that fades. A celebration of impermanence. A waltz for things that won't last.
> *Examples: A song that gets quieter with each verse. A summer love song that ends mid-phrase.*

**An idea that comes from a book** — Best when you want thematic weight:
> Read something. Make something inspired by it. A line from the Tao Te Ching. A character's monologue. A chapter title as a chorus.
> *Examples: A song based on a Zen koan. A villanelle built from traces of Borges.*

**The useless tree** — Best for experimental or anti-songs:
> Make something useless. Deliberately, completely, beautifully useless. A song that serves no purpose. That's the purpose.
> *Examples: A song in a key that doesn't exist. A lullaby for a stone. Music only audible to houseplants.*

#### Matching Constraints to Intent

| You want... | Pick from |
|-------------|-----------|
| Depth, philosophical | High concept low effort, An idea from a book |
| Minimalist, atmospheric | Subtract, Make something that dies |
| Witty, surprising | Start at the punchline, Text is the interface |
| Experimental, weird | The useless tree, Make something that dies |
| Getting unstuck | Blatantly copy something, High concept low effort |
| Narrative, story-driven | Text is the interface, Start at the punchline |
| Warm, personal | An idea from a book, Start at the punchline |

#### Output Format

For each concept generated, use this structure:

```
## Concept: [Working Title]

Constraint: [which constraint was used]
> [The constraint in one sentence]

[2-3 sentences: what the song is about, emotional territory, musical direction]

🎤 Vibe: [genre/mood keywords]
📝 Hook idea: [potential title or chorus seed]
🎯 Emotional core: [one line: what feeling drives this song]
```

---

### 1.2 If You Already Have an Idea

Skip the constraint step. Just define the brief:

```
CONCEPT BRIEF
─────────────
Working title:     [placeholder or decided]
Emotional core:    [one sentence — what the song feels about]
Thematic territory:[images, metaphors, world the song lives in]
Musical direction: [genre / instrumentation / mood keywords, if any]
Reference songs:   [optional — songs with similar energy]
```

Output of Phase 1 is always a **Concept Brief** that feeds into Phase 2.

---

## Phase 2: Lyric Writing

### 2.1 Choose a Structure

Common skeletons — mix, modify, or throw out as needed:

```
ABABCB   Verse/Chorus/Verse/Chorus/Bridge/Chorus    (most pop/rock)
AABA     Verse/Verse/Bridge/Verse (refrain-based)    (jazz standards, ballads)
ABAB     Verse/Chorus alternating                    (simple, direct)
AAA      Verse/Verse/Verse (strophic, no chorus)     (folk, storytelling)
```

The six building blocks:
- **Intro** — set the mood, pull the listener in
- **Verse** — the story, the details, the world-building
- **Pre-Chorus** — optional tension ramp before the payoff
- **Chorus** — the emotional core, the part people remember
- **Bridge** — a detour, a shift in perspective or key
- **Outro** — the farewell, can echo or subvert the rest

You don't need all of these. Some great songs are just one section that evolves. Structure serves the emotion, not the other way around.

---

### 2.2 Emotional Arc — the Journey

Map the energy through the song. The most powerful dynamic trick: **contrast**. Whisper before a scream hits harder than just screaming. Sparse before dense. Slow before fast. Low before high. Silence is an instrument.

Quick energy mapping (rough guide, not prescription):

```
Intro:     2-3  | spare, atmospheric
Verse 1:   5-6  | conversational, grounded
Pre-Chorus:7    | tension rising
Chorus:    8-9  | release, peak
Verse 2:   5-6  | pull back, continue story
Chorus:    8-9  | peak again, maybe bigger
Bridge:    varies  | shift — new perspective, key change, stripped back
Final Chorus: 9-10  | biggest, most open
Outro:     2-3  | fade, echo, or surprising close
```

For Chinese-style ballads, map to a five-stage arc:

```
静 (intro) → 起 (rise) → 放 (release) → 转 (shift) → 寂 (fade)
```

---

### 2.3 Rhyme, Meter, and Sound

**Rhyme types** (from tight to loose):

| Type | Example | Use for |
|------|---------|---------|
| Perfect | lean / mean | Climax, hook, emphasis |
| Family | crate / braid | Verse flow |
| Assonance | had / glass (same vowels) | Atmospheric, dreamy |
| Consonance | scene / when (same ending consonants) | Textured, unresolved |
| Near / slant | enough to suggest connection | Bridge, uncertainty |

Mix them. All perfect rhymes can sound like a nursery rhyme. All slant rhymes can sound lazy. The blend is where it lives.

**Internal rhyme** — rhyming within a line, not just at the ends:
```
"We pruned the lies from bleeding trees / Distilled the storm from entropy"
```
"lies/flies", "trees/entropy" create internal echoes.

**Meter** — the rhythm of stressed vs unstressed syllables:
- Matching syllable counts between parallel lines helps singability
- The STRESSED syllables matter more than total count
- Say it out loud. If you stumble, the meter needs work.
- Intentionally breaking meter can create emphasis or surprise

---

### 2.4 Writing the Hook

The hook is the line people remember, hum, repeat. Usually the title or core phrase. Works best when melody + lyric + emotion all align.

**Hook strategies:**
- Place it at the first or last line of the chorus — where it lands hardest
- Make it short enough to fit on a T-shirt
- It should work alone, without the verses, and still make sense
- Test it: say the hook out of context. Does it still hit?

---

### 2.5 Drafting the Lyrics

**Show, don't tell (usually):**
- "I was sad" = flat
- "Your hoodie's still on the hook by the door" = alive
- But sometimes "I give my life" said plainly IS the power

**Prosody** — lyrics and music supporting each other:
- Stable feelings (resolution, peace) → settled melodies, perfect rhymes, resolved chords
- Unstable feelings (longing, doubt) → wandering melodies, near-rhymes, unresolved chords
- Verse melody typically sits lower, chorus goes higher
- But flip this if it serves the song

**Avoid** (unless you're doing it on purpose):
- Cliches on autopilot ("heart of gold" without earning it)
- Forcing word order to hit a rhyme ("Yoda-speak")
- Same energy in every section (flat dynamics)
- Treating your first draft as sacred — revision is creation

---

### 2.6 Parody / Adaptation

When rewriting an existing song with new lyrics:

**The skeleton:** Map the original's structure first.
1. Count syllables per line
2. Mark the rhyme scheme (ABAB, AABB, etc.)
3. Identify which syllables are STRESSED
4. Note where held/sustained notes fall

**Fitting new words:**
- Match stressed syllables to the same beats as the original
- Total syllable count can flex by 1-2 unstressed syllables
- On long held notes, try to match the VOWEL SOUND of the original (if original holds "LOOOVE" with an "oo" vowel, "FOOOD" fits better than "LIFE")
- Monosyllabic swaps in key spots keep rhythm intact (Crime → Code, Snake → Noose)
- Sing your new words over the original — if you stumble, revise

**Concept:**
- Pick a concept strong enough to sustain the whole song
- Start from the title / hook and build outward
- Generate lots of raw material (puns, phrases, images) FIRST, then fit the best ones into the structure
- If you need a specific line somewhere, reverse-engineer the rhyme scheme backward to set it up

**Keep some originals:** Leaving a few original lines or structures intact adds recognizability and lets the audience feel the connection.

---

**Output of Phase 2:** Completed lyrics, with section markers and a rough emotional arc annotated.

---

## Phase 3: Suno Production

### 3.1 Build the Style Prompt

Use Custom Mode in Suno (separate Style + Lyrics fields). Always prefer Custom Mode for serious work — it gives you control over the dynamic arc.

**Style field formula:**

```
Genre + Mood + Era + Instruments + Vocal Style + Production + Dynamics
```

**Good vs bad:**

```
BAD:  "sad rock song"
GOOD: "Cinematic orchestral spy thriller, 1960s Cold War era, smoky
       sultry female vocalist, big band jazz, brass section with
       trumpets and french horns, sweeping strings, minor key,
       vintage analog warmth"
```

**Describe the journey, not just the genre:**

```
"Begins as a haunting whisper over sparse piano. Gradually layers
in muted brass. Builds through the chorus with full orchestra.
Second verse erupts with raw belting intensity. Outro strips back
to a lone piano and a fragile whisper fading to silence."
```

**Style field tips:**
- Suno V4.5+ supports up to 1,000 chars in Style field — use them
- NO artist names or trademarks. Describe the sound instead.
  "1960s Cold War spy thriller brass" not "James Bond style"
  "90s grunge" not "Nirvana-style"
- Specify BPM and key when you have a preference
- Use Exclude Styles field for what you DON'T want
- Unexpected genre combos can be gold: "bossa nova trap", "Appalachian gothic", "chiptune jazz"
- Build a vocal PERSONA, not just a gender:
  "A weathered torch singer with a smoky alto, slight rasp, who starts vulnerable and builds to devastating power"

---

### 3.2 Add Metatags to Lyrics

Place tags in `[brackets]` inside the lyrics field to guide Suno's performance.

**Structural:**
`[Intro]` `[Verse 1]` `[Verse 2]` `[Pre-Chorus]` `[Chorus]` `[Post-Chorus]`
`[Hook]` `[Bridge]` `[Interlude]` `[Instrumental]` `[Instrumental Break]`
`[Guitar Solo]` `[Breakdown]` `[Build-up]` `[Outro]` `[Silence]` `[End]`

**Vocal performance:**
`[Whispered]` `[Spoken Word]` `[Belted]` `[Falsetto]` `[Powerful]`
`[Soulful]` `[Raspy]` `[Breathy]` `[Smooth]` `[Gritty]`
`[Staccato]` `[Legato]` `[Vibrato]` `[Melismatic]`
`[Harmonies]` `[Choir]` `[Harmonized Chorus]`

**Dynamics:**
`[High Energy]` `[Low Energy]` `[Building Energy]` `[Explosive]`
`[Emotional Climax]` `[Gradual swell]` `[Orchestral swell]`
`[Quiet arrangement]` `[Falling tension]` `[Slow Down]`

**Gender:**
`[Female Vocals]` `[Male Vocals]`

**Atmosphere:**
`[Melancholic]` `[Euphoric]` `[Nostalgic]` `[Aggressive]`
`[Dreamy]` `[Intimate]` `[Dark Atmosphere]`

**SFX:**
`[Vinyl Crackle]` `[Rain]` `[Applause]` `[Static]` `[Thunder]`

**Best practices:**
- Put tags in BOTH style field AND lyrics for reinforcement
- Keep to 5-8 tags per section max — too many confuses the AI
- Don't contradict yourself (`[Calm]` + `[Aggressive]` in same section)
- Without structural tags, Suno defaults to flat verse/chorus repetition with no emotional arc

---

### 3.3 Duet / Vocal Assignment

Suno supports multiple voices in a single track, controlled entirely through metatags and style field description.

**Style field:** Describe both voices with distinct personas, NOT just "male and female":

```
Male-female duet — two voices in dialogue.
Male voice: earthly, searching, vulnerable, restrained at first,
  grows to raw desperate questioning.
Female voice: otherworldly, steady, knowing, serene power —
  starts warm and intimate, builds to devastating emotional peak.
```

**Lyrics field:** Assign every section with a voice tag:

```
[Male Vocals — intimate, almost a whisper]
... male lines ...

[Female Vocals enters — warm, steady, knowing]
... female lines ...

[Both voices, building, intertwining]
... shared lines ...
```

**Call-and-response** works best for separation:
- Verse 3 is the ideal spot — one line male, next line female
- Suno produces the most convincing duet separation here
- Keep individual lines short (1-2 lines per voice max)

**Shared climax** (bridge / outro):
- Use `[Both together]` or `[Harmony enters]` for the final emotional peak
- The outro works well as a question-and-answer structure

**Key insight:** Give each voice a CHARACTER, not just a gender. "Questioner vs answerer" is a stronger separation than "man vs woman". Suno uses the character description to differentiate performance and delivery.

---

### 3.4 Generation & Iteration

**Workflow:**
1. Build the complete prompt package (Style + Lyrics with metatags)
2. Generate 3-5 variations minimum — treat them like recording takes
3. Listen and pick the best section as your base
4. Use Suno's Extend or Continue to build on promising sections
5. If something great happens by accident, keep it
6. Style can drift in extensions — restate genre / mood when extending

**Expect:** ~3-5 generations per 1 good result. Revision is normal.

---

## Chinese & East Asian Styles

Suno defaults to Western pop/rock instrumentation. Chinese-style songs need active guidance to avoid Western instrument bleed.

### Instrument Vocabulary (for Style field)

| Instrument | Description | Use for |
|------------|-------------|---------|
| guqin (古琴) | Seven-string zither, resonant, sparse | Solos, arpeggios, single-note lines |
| erhu (二胡) | Two-string fiddle, mournful, expressive | Subtle texture beneath voice, bridge swells |
| dizi (笛子) | Bamboo flute, bright or melancholic | Melodic fills, intro/outro phrases |
| pipa (琵琶) | Plucked lute, percussive and fluid | Rhythmic patterns, dramatic accents |
| Chinese percussion | 鼓 (drum), 磬 (stone chime), 锣 (gong) | Key moments — a single hit, not a beat |
| zheng (古筝) | Plucked zither, flowing arpeggios | Accompaniment, transitional sections |

### Anti-Western-Instrument Rules

Always include in Style field when going pure Chinese:

```
No western instruments. No piano. No guitar. No bass. No percussion.
```

Or more targeted:
```
Pure Chinese timbre. No piano. No guitar.
```

Suno tends to default to piano in ballads — explicitly exclude it.

### Style Field Language: Use English Even for Chinese Songs

Suno's Style field is trained primarily on English data. Chinese descriptions get approximate treatment — detailed performance instructions (dynamic arcs, instrument textures) are significantly degraded or ignored.

**Best practice:**
- Write the Style field in English for Chinese-style songs. Suno handles terms like `guqin`, `pentatonic minor`, `Chinese percussion` correctly.
- Use Chinese in parentheses for instrument names where the English term is less known (e.g. `qing (stone chime)`, `guqin (ancient Chinese zither)`).
- Keep the Exclude Styles field in English.
- The Lyrics field stays in the song's language (Chinese for Chinese-style songs).

### Pentatonic Scale Guidance

| Desired mood | Include in Style field |
|--------------|----------------------|
| General Chinese folk | `pentatonic scale` |
| Darker, contemplative | `pentatonic minor, D or E tonic` |
| Brighter, narrative | `pentatonic, Chinese folk scale` |

### Vocal Personas for Chinese Styles

| Style | Style Prompt Pattern |
|-------|---------------------|
| Dramatic female | "A female voice with theatrical presence — starts intimate and controlled, builds to soaring, devastating power at the chorus. Spoken word verses, belted emotional climax." |
| Low male spoken-word | "A low male voice, intimate and weathered, spoken-word delivery, never rushed — every word placed like a stone on a board." |
| Ethereal female | "An ethereal female voice, floating, breathy, like wind through bamboo. Never forced. Soft and distant." |
| Opera-inflected | "Traditional opera inflection, vibrato on sustained notes, dramatic pitch slides. Vocal leaps between registers." |

### Dynamic Arc for Chinese Ballads

Map the Western "whisper to roar" arc to Chinese-specific framing:

```
Intimate (静) → Rising (起) → Powerful (放) → Shift (转) → Fade (寂)
```

- **Verse 1:** 静 — controlled, intimate, almost a whisper
- **Verse 2:** 起 — slight rise in intensity, instrument enters
- **Chorus:** 放 — emotional release, belted (controlled power, not Western belting)
- **Bridge:** 转 — shift, harmony enters, perspective changes
- **Outro:** 寂 — stripped back, single instrument, fading

Use `[Silence]` as a structural element — Chinese aesthetics value emptiness (留白). A 2-3 second silence before the final line can be devastating.

### Chinese Rap: Rhyme Patterns

Chinese rap differs from English in rhyme mechanics. The 十三辙 (13 rhyme categories) system maps Chinese finals into natural rhyme groups.

**Single rhyme (单押):** All end-of-line characters share the same 辙.
```
他们说——要强 要刚 要狂
拳头要像烙铁 身体要像钢
```
(Jiangyang 辙: -ang/-iang/-uang)

**Double rhyme (双押):** Last two syllables rhyme.
```
遇方则方 遇圆则圆 — 形状/挡/淌/江上 — 全部押 -iang/-uang
```

**Triple rhyme (三押):** Three-syllable phrase rhyme.
```
打不破的 就绕过去渗过去 从缝隙钻
```
Multi-syllable rhyme across the breath.

**Internal rhyme (句中内韵):** Rhyme points inside the line creates density.
```
越练越紧 越紧越僵 越僵越慢
```
Three two-character segments, each with its own end-rhyme.

**Common 十三辙 for rap:**
Jiangyang (-ang), Yanqian (-an), Zhongdong (-ong/-iong), Youqiu (-ou/-iu), Hui dui (-ei/-ui), Yiqi (-i/-ü), Yaotiao (-ao/-iao), Fahua (-a/-ia/-ua), Renchen (-en/-in/-un), Gusu (-u), Suobo (-o/-e/-uo), Niexie (-e/-ie/-üe), Huailai (-ai/-uai)

**Structure tip:** Each verse section should commit to one 辙 for end-rhymes. Switching between sections creates contrast (e.g., Verse 1 in Yanqian — tight/pressed → Chorus in Jiangyang — open/explosive).

---

## Phonetic Tricks for AI Vocalists

AI vocalists don't read — they pronounce. Help them:

**Phonetic respelling:**
- Spell words as they SOUND: "through" → "thru"
- Proper nouns are the highest failure rate — test early
- "Nous" → "Noose" (forces correct pronunciation)
- Hyphenate to guide syllables: "Re-search", "bio-engineering"

**Delivery control:**
- ALL CAPS = louder, more intense
- Vowel extension: "lo-o-o-ove" = sustained / melisma
- Ellipses: "I... need... you" = dramatic pauses
- Hyphenated stretch: "ne-e-ed" = emotional stretch

**Always:**
- Spell out numbers: "24/7" → "twenty four seven"
- Space acronyms: "AI" → "A I" or "A-I"
- Test proper nouns / unusual words in a short 30-second clip first
- Once generated, pronunciation is baked in — fix in lyrics BEFORE

---

## Best Practices & Common Pitfalls

### Do
- Describe the dynamic ARC in the Style field — it's more important than listing genres
- Build a vocal persona, not just a gender label
- Use structural metatags on every section — without them Suno flattens the arc
- Preserve confirmed lyrics once the writer signs off; revise only style/metatags
- Keep some original lines intact in a parody — recognizability adds emotional weight
- Test unusual words or proper nouns in a short clip before full generation

### Don't
- Expect every generation to be good. 3-5 per 1 usable result is normal.
- Contradict your metatags (`[Calm]` + `[Aggressive]` in the same section)
- Use artist names in Style field — describe the sound instead
- Reverse-engineer lyrics to fit a genre; write the words and find the genre that serves them
- Be precious about rules. If a line breaks meter but hits harder, keep it. Craft serves art, not the other way around.

### If Something Goes Wrong
- Style drifted in an extension → restate genre/mood when extending
- Pronunciation wrong → fix the spelling in lyrics, re-generate
- Too much western instrument bleed (Chinese song) → add explicit exclusion in Style field
- Flat performance with no dynamics → add more performance metatags and describe the journey in Style
- Voices in a duet sound too similar → give each a stronger character description

---

## Templates & Quick Reference

### Style Prompt Template

```
[Genre blend], [era/style reference — no artist names]
[Vocal persona description — character, not just gender]
[Instruments — what to include]
[Explicit exclusions — what NOT to include]
[Key, BPM if known]
[Dynamic journey — emotion arc through sections]
```

### Complete Prompt Package Structure

```
═══════════════════════════════════════
SONG: [Title]
═══════════════════════════════════════

━━━ STYLE FIELD ━━━
[Paste style prompt here — English, even for Chinese songs]

━━━ LYRICS (with metatags) ━━━
[Paste lyrics with [bracketed] section and performance tags]
```

### Structure Quick Reference

| Section | Emotional function | Energy | Typical length |
|---------|-------------------|--------|----------------|
| Intro | Set mood, pull in | 2-3 | 2-4 lines |
| Verse | Story, details, world-building | 5-6 | 4-8 lines |
| Pre-Chorus | Tension ramp | 7 | 2-4 lines |
| Chorus | Emotional core, hook | 8-9 | 4-8 lines |
| Bridge | Shift, detour, new perspective | varies | 4-8 lines |
| Outro | Farewell, fade | 2-3 | 2-4 lines |

### Parody Adaptation Checklist

- [ ] Syllable count per line mapped
- [ ] Rhyme scheme identified (ABAB, AABB, etc.)
- [ ] Stressed syllables marked
- [ ] Held notes / vowel sounds noted
- [ ] Monosyllabic key-word swaps identified (cleanest swaps)
- [ ] Sung over original — no stumbles

### Chinese Style Field Checklist

- [ ] `pentatonic scale` or `pentatonic minor` included
- [ ] `No western instruments. No piano.` explicitly stated (if pure Chinese)
- [ ] Guqin / erhu / dizi / pipa specified
- [ ] Dynamic arc mapped to 静→起→放→转→寂
- [ ] Exclude Styles field filled
- [ ] `[Silence]` considered as structural element

---

## Customizing This Skill for Your Style

This skill is intentionally generic. To make it your own:

1. **Default genres** — replace the example Style prompts with ones matching your preferred sound
2. **Your vocal personas** — add your go-to character descriptions for your voice type
3. **Lyric habits** — note your preferred rhyme density, favorite 辙, structural tendencies
4. **Proven prompts** — save successful Style prompts as templates for reuse
5. **Iteration workflow** — adjust the generation count / revision pattern to what works for you

The skill is modular by design. Each phase (Ideation → Lyrics → Production) can be used independently. Over time, you'll develop your own shortcuts and favorites — the skill provides the pipeline, you fill in the personal touch.