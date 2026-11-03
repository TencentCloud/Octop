# Commercial Production — Ads, Corporate, Branded Content

## Brand Consistency

### Brand Kit Setup
Before any generation, document:
```markdown
## Brand: [Client Name]

### Colors
- Primary: #HEX
- Secondary: #HEX
- Accent: #HEX

### Typography
- Headlines: [Font Name]
- Body: [Font Name]

### Logo
- Clear space: [X]px minimum
- Position: [standard placement]
- Animation: [approved animation style]

### Visual Style
- Photography style: [description]
- Lighting: [warm/cool/neutral]
- Mood: [professional/playful/bold]
```

### Style Lock
Save approved visual parameters as reusable preset:
- Color grading LUT
- Motion graphics tempo
- Transition style
- Text animation patterns

## Version Generation

### A/B Testing Workflow
Generate matched pairs varying ONE element:
1. Same video, different CTA
2. Same video, different opening hook
3. Same video, different end card

### Batch Variations
From one approved concept:
```
Base concept: Product hero shot with tagline
├── Version A: "Save 20%" CTA
├── Version B: "Limited Time" CTA
├── Version C: "Shop Now" CTA
└── Version D: No CTA (awareness)
```

### Duration Cuts
From one master:
- :06 (bumper)
- :15 (pre-roll)
- :30 (standard)
- :60 (full story)

Each cut needs different pacing, not just trimming.

## Multi-Format Export

### Platform Specifications

| Platform | Aspect | Resolution | Max Duration |
|----------|--------|------------|--------------|
| YouTube | 16:9 | 1920x1080 | No limit |
| TikTok/Reels | 9:16 | 1080x1920 | 60s-3min |
| Instagram Feed | 1:1 | 1080x1080 | 60s |
| Instagram Story | 9:16 | 1080x1920 | 15s per card |
| LinkedIn | 16:9 | 1920x1080 | 10min |
| CTV/OTT | 16:9 | 1920x1080+ | 15-30s |

### Smart Reframing
When converting 16:9 to 9:16:
- Identify key subject
- Crop to follow subject
- May need to regenerate for optimal framing

```bash
# Center crop to vertical
ffmpeg -i horizontal.mp4 -vf "crop=ih*9/16:ih,scale=1080:1920" vertical.mp4

# With subject tracking (if available)
# Use AI reframe tools or manual keyframing
```

## Localization

### Text Overlays
Maintain separate text layers:
```
base_video.mp4 (no text)
├── english_supers.mp4
├── spanish_supers.mp4
├── french_supers.mp4
└── german_supers.mp4
```

### Voiceover Workflow
1. Export video with M&E (music and effects) only
2. Record VO in target language
3. Combine: `ffmpeg -i video_me.mp4 -i vo_spanish.mp3 -map 0:v -map 1:a output.mp4`

### Cultural Adaptation Flags
Before international rollout, check:
- Hand gestures (meanings vary)
- Color associations
- Text direction (RTL languages)
- Local regulations (alcohol, gambling, etc.)

## Client Approval Workflow

### Animatic Stage
1. Generate rough frames (fast, cheap)
2. Present for concept approval
3. Get sign-off before full generation

### Revision Tracking
```
project/
├── v1_concept/
├── v2_client_feedback/
├── v3_final_approved/
└── changes.md (log of all revisions)
```

### Checkpoint Gates
- [ ] Concept approved
- [ ] Storyboard approved
- [ ] Animatic approved
- [ ] First cut approved
- [ ] Final cut approved
- [ ] Deliverables approved

## Legal Considerations

- No AI-generated people resembling real individuals without consent
- Clear rights to music/sound
- Brand guidelines compliance verified
- Disclosure of AI usage if required by platform/region
