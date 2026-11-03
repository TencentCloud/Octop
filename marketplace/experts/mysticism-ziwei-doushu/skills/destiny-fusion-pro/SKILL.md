---
name: destiny-fusion-pro
description: Premium destiny consultation skill combining Ziwei Doushu and Bazi in one offline workflow. Use when the user wants a flagship, consultation-style report from birth date and time with unified calculation rules, dual-system cross-checking, optional chart images, and polished markdown or JSON deliverables for yearly outlook, decade luck cycles, relationships, career, wealth, and risk themes.
---

# Destiny Fusion Pro

Generate a **consultation-grade destiny report** by combining **Ziwei Doushu + Bazi** under one consistent calculation standard.

Core appeal:
- One input, two systems, one unified report
- Offline-first and reproducible
- Text report is the primary deliverable; chart image is optional enhancement
- Suitable for both human-readable consultation and structured automation output

## Recommended Command

```bash
python scripts/fortune_fusion.py \
  --date 1990-10-21 \
  --time 15:30 \
  --gender female \
  --year 2026 \
  --from-year 2026 \
  --years 10 \
  --template pro \
  --format markdown
```

## Default Standard

- Timezone: `Asia/Shanghai`
- Longitude: `120.0` (Beijing standard)
- Ziwei engine: `py`
- Report priority: text-first; chart export may be attempted when enabled

## Deliverables

A strong output should include:
1. Calculation standard (timezone, longitude, unified calculation time)
2. Ziwei full-plate facts (命宫 / 身宫 / 十二宫 / annual transformations)
3. Bazi facts (四柱 / 日主 / 十神 / 藏干 / 大运 / 流年)
4. Cross-system synthesis
   - personality baseline
   - career / money / relationship / health themes
   - current-cycle opportunity and risk boundaries
5. Caution notes about time ambiguity or interpretation limits

## Common Parameters

- `--engine py|js|dual`: primary / fallback / dual-engine cross-check
- `--template lite|pro|executive`: lighter / standard / premium consulting density
- `--chart none|svg|jpg`: chart export mode
- `--chart-quality 1-100`: JPG quality, default `92`
- `--chart-backend auto|cairosvg`: offline image backend
- `--format markdown|json`: final output format

## Output Style Guardrails

- Write **fact first, interpretation second, advice last**.
- Prefer trend language and probability language; avoid absolute prophecy.
- Make cross-system consistency visible: note where Ziwei and Bazi reinforce each other vs diverge.
- If chart rendering fails, continue with the text report instead of failing the whole workflow.
- If birth time is near a boundary, explicitly recommend dual-plate comparison.

## Scope Boundary

- Fully offline; use no web search or headless browser.
- Produce analysis only; not medical, legal, or investment advice.
- Optional chart export should never block the report.

## References

- `references/ziwei-methodology.md`
- `references/positioning.md`
