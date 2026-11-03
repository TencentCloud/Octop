# Generation — Prompt Engineering for Video

## Prompt Structure

Every generation prompt needs:

```
[SHOT TYPE] [SUBJECT/ACTION] [ENVIRONMENT].
[LIGHTING]. [CAMERA MOVEMENT].
[STYLE KEYWORDS]. [DURATION].
```

Example:
```
Medium shot of a woman in a red coat walking through rain.
Neon reflections on wet pavement, night city.
Slow tracking shot following from behind.
Cinematic, 35mm film grain, moody, Blade Runner style. 5 seconds.
```

## Shot Type Keywords

| Type | Keywords | When to Use |
|------|----------|-------------|
| Extreme wide | aerial, drone, landscape, establishing | Opening scenes, location setup |
| Wide | full body, environment visible | Group shots, blocking |
| Medium | waist up, two-shot | Dialogue, interactions |
| Close-up | face, head and shoulders | Emotion, reaction |
| Extreme close-up | eyes, hands, detail | Tension, emphasis |
| Over-the-shoulder | OTS, conversation | Dialogue alternating |
| POV | first person, subjective | Immersion, action |

## Camera Movement Keywords

- **Static** — locked off, tripod, no movement
- **Pan** — horizontal sweep, follow action
- **Tilt** — vertical movement, reveal
- **Dolly/Track** — lateral movement, parallel to subject
- **Push in** — move toward subject, intensify
- **Pull out** — move away, reveal context
- **Crane** — vertical + horizontal, epic
- **Handheld** — organic shake, documentary feel
- **Steadicam** — smooth follow, walk-and-talk

## Character Consistency Techniques

### Reference Image Anchoring
Always include character reference in the prompt or as image input:
- Front-facing headshot
- Full body reference
- Costume for this scene

### Consistency Keywords
```
same character as reference, consistent appearance,
matching [hair color], wearing [costume description],
[distinguishing feature] visible
```

### When Characters Break
If a character looks different:
1. Regenerate with stronger reference emphasis
2. Try different seed/variation
3. Use image-to-video with a correct still as input
4. Accept and fix with face-swap as last resort

## Style Consistency

Lock these in your style bible and repeat in EVERY prompt:
- Color palette keywords
- Film stock reference (35mm, 16mm, digital)
- Era/decade aesthetic
- Specific director/film references
- Grain/texture level

## Tool-Specific Syntax

### Seedance 2.0
- Excels with action verbs
- Specify motion intensity: "gentle sway" vs "explosive movement"
- Works well with dance/choreography descriptions

### Kling 3.0
- Strong lip sync capability
- Include dialogue in prompt for better mouth movement
- Good with cultural/regional styles

### Runway Gen-4
- Motion brush: specify areas of movement
- Style reference: upload reference image
- Camera control: explicit movement paths

### Sora
- Natural language descriptions work best
- Can handle longer, more complex prompts
- Physics-aware: describe weight, momentum

## Iteration Workflow

1. **First pass:** Generate with full prompt, assess overall
2. **Refine:** Adjust specific failing elements
3. **Polish:** Fine-tune timing, framing
4. **Variations:** Generate 3-5 options of final
5. **Select:** Choose best, log what worked

## Common Failures & Fixes

| Problem | Likely Cause | Fix |
|---------|--------------|-----|
| Wrong character | Missing/weak reference | Add image reference, strengthen description |
| Lighting doesn't match | Style drift | Repeat lighting keywords more prominently |
| Motion too fast/slow | Duration mismatch | Adjust duration, describe pace explicitly |
| Unwanted elements | Ambiguous prompt | Be more specific, add negative keywords |
| Style inconsistent | Varied prompts | Create prompt template, copy exactly |
