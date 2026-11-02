# Experimental Video — Artistic, Abstract, Music-Driven

## Audio-Visual Synthesis

### Beat-Reactive Generation
Analyze audio and sync visuals to:
- **Transients** — Hard cuts on drum hits
- **Bass** — Scale/pulse effects, color shifts
- **Melody** — Movement direction, subject changes
- **Dynamics** — Intensity of effects

### Workflow
1. Extract audio waveform/spectrum
2. Mark beat timestamps
3. Generate clips timed to sections
4. Cut on beat for final edit

```bash
# Extract audio for analysis
ffmpeg -i music.mp3 -af "showwaves=s=1920x200:mode=line" waveform.mp4

# Cut video on specific timestamps
ffmpeg -i input.mp4 -ss 00:00:02.350 -t 00:00:01.200 beat_cut.mp4
```

### Musical Structure Awareness
Map visual intensity to song structure:
| Section | Visual Treatment |
|---------|-----------------|
| Intro | Slow build, establishing |
| Verse | Moderate energy, narrative |
| Pre-chorus | Rising tension |
| Chorus | Peak energy, maximum motion |
| Bridge | Contrast, calm or shift |
| Drop | Explosive, all elements |
| Outro | Fade, resolve |

## Style Manipulation

### Continuous Style Interpolation
Morph between styles over time:
```
00:00 - Van Gogh impressionist
00:10 - Transition begins
00:15 - Kandinsky abstract
00:25 - Transition begins
00:30 - Cyberpunk neon
```

Use keyframes with style keywords, generate transitions.

### Texture Blending
Combine incompatible materials:
- "flesh merging with marble, liquid chrome veins, static interference"
- "water surface with circuit board patterns, bioluminescent"
- "silk fabric dissolving into smoke, firefly particles"

### Glitch Aesthetics
Intentional digital artifacts:
- **Datamosh** — Frame blending artifacts
- **Pixel sorting** — Organized chaos
- **Compression artifacts** — Block noise
- **Chromatic aberration** — RGB split
- **Scan lines** — CRT/VHS effects

```bash
# VHS effect
ffmpeg -i input.mp4 -vf "noise=alls=20:allf=t+u,chromashift=cbh=3:crh=-3" vhs.mp4

# Add scan lines
ffmpeg -i input.mp4 -vf "drawgrid=w=0:h=2:c=black@0.1" scanlines.mp4
```

## Conceptual & Non-Linear

### Semantic Morphing
Transform concepts visually:
```
Frame 1: "isolation" — single figure, vast empty space
Frame 2: "connection" — figures approaching, warmth
Frame 3: "dissolution" — figures merging, boundaries blur
```

Generate each as still or clip, transition between.

### Dream Logic Transitions
Instead of physical continuity:
- Match emotion, not location
- Visual rhymes (shape A to shape B)
- Symbolic links (blood red → rose petal → sunset)
- Time non-linearity (future echoes, past ghosts)

### Visual Poetry Mode
Interpret text as metaphor:
```
Text: "The weight of unspoken words"
Visual: Figure with letters falling like rain, crushing flowers
NOT: Person with speech bubble
```

## Generative Approaches

### Infinite Loops
Create seamless, endless content:
- Zoom fractals
- Infinite hallway/tunnel
- Repeating pattern evolution

```bash
# Create seamless loop (last frame = first frame)
ffmpeg -i input.mp4 -filter_complex "[0]reverse[r];[0][r]concat" loop.mp4
```

### Emergent Patterns
Define rules, let system generate:
- "Particles attracted to red, repelled by blue"
- "Shapes grow toward light, decay in shadow"
- "Motion follows music frequency bands"

### Controlled Randomness
Add chaos with boundaries:
```
Base: Fixed composition
Chaos layer: Random particle movement (intensity: 30%)
Result: Organic feel, still coherent
```

## Temporal Manipulation

### Time Sculpting
- **Loops within loops** — Nested repetition
- **Reverse causality** — Effect before cause
- **Temporal echoes** — Ghosts of past/future frames
- **Speed ramping** — Extreme slow-mo to fast-forward

### Multi-Timeline Compositing
Layer different time streams:
```
Layer 1: Present action, normal speed
Layer 2: Memory fragments, slow, desaturated
Layer 3: Future flashes, fast, high contrast
Composite: All visible simultaneously
```

## Synesthetic Mapping

### Sound to Color
| Frequency | Color |
|-----------|-------|
| Sub-bass (<60Hz) | Deep purple/black |
| Bass (60-250Hz) | Red/orange |
| Low-mid (250-500Hz) | Orange/yellow |
| Mid (500-2kHz) | Green/cyan |
| High-mid (2-4kHz) | Blue |
| High (>4kHz) | White/silver |

### Sound to Texture
| Sound Character | Texture |
|-----------------|---------|
| Smooth sine | Liquid, glass |
| Harsh distortion | Fracture, static |
| Reverb/space | Fog, particles |
| Staccato | Sharp edges, fragments |
