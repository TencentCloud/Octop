# Pre-Production — Script to Shot List

## Script Breakdown Process

### 1. Parse the Script
Extract from screenplay:
- **Sluglines** → Scene locations, time of day
- **Action lines** → Visual descriptions, blocking
- **Dialogue** → Who speaks, duration estimates
- **Parentheticals** → Emotional beats, delivery

### 2. Generate Shot List

For each scene, define:
```
Scene 3 - INT. APARTMENT - NIGHT
├── Shot 3.1: Wide establishing (3s)
│   └── Framing: Full room, Sarah enters frame left
├── Shot 3.2: Medium two-shot (5s)
│   └── Framing: Sarah and Tom at table
├── Shot 3.3: Close-up Sarah (4s)
│   └── Framing: Face, catch the realization
└── Shot 3.4: Insert - phone screen (2s)
```

### 3. Time of Day Logic

| Script Says | Lighting Keywords |
|-------------|-------------------|
| MORNING | Golden hour, soft warm light, long shadows |
| DAY | Neutral daylight, even illumination |
| AFTERNOON | Warm amber tones, lower sun angle |
| EVENING | Blue hour, mixed warm/cool |
| NIGHT | Practical lights, high contrast, pools of light |

## Storyboard Generation

For each key shot, generate a reference frame:
1. Describe framing in detail
2. Include character positions
3. Specify lighting direction
4. Note any camera movement start/end frames

Storyboard prompt template:
```
[SHOT TYPE] of [SUBJECT], [LIGHTING], [STYLE KEYWORDS].
Camera: [MOVEMENT]. Mood: [EMOTION].
```

## Character Sheets

Before generating any footage:

1. **Generate front/side/back views** of each main character
2. **Document fixed attributes:**
   - Hair color/style
   - Clothing per scene
   - Distinguishing features
   - Height relative to others
3. **Save as reference** in `characters/[name]/`

## Style Bible Creation

From reference films/images, extract:

```markdown
## Visual Style
- **Color palette:** Teal and orange, desaturated midtones
- **Lighting:** High contrast, motivated sources
- **Grain:** 35mm film texture, 15% intensity
- **Movement:** Slow, deliberate, no handheld

## Reference Films
- Blade Runner 2049 (lighting)
- Her (color palette)
- Children of Men (long takes)
```

## Scene Complexity Estimation

| Scene Type | Shots Needed | Iteration Budget |
|------------|--------------|------------------|
| Dialogue (2 people) | 8-12 | 3x per shot |
| Action sequence | 15-25 | 5x per shot |
| Establishing/mood | 2-4 | 2x per shot |
| Montage | 6-10 | 3x per shot |

A 90-minute film ≈ 50-70 scenes ≈ 400-800 shots ≈ 1500+ generations
