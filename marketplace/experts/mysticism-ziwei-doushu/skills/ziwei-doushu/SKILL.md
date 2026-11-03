---
name: ziwei-doushu
description: Professional Ziwei Doushu consultation skill with offline, Beijing-standard calculation rules. Use when the user wants a polished Ziwei report from birth date and time, including life palace structure, twelve palaces, four transformations, major luck cycles, yearly triggers, optional chart images, and a clear split between chart facts and traditional interpretation.
---

# Ziwei Doushu

Generate a **professional Ziwei Doushu reading** with a clear split between:
- chart facts
- traditional interpretation framework
- practical trend summary

This skill is designed to feel more like a **clean analyst-style consultation** than a mystical word dump.

## Recommended Command

```bash
python scripts/ziwei_chart.py \
  --date 1990-10-21 \
  --time 15:30 \
  --gender female \
  --year 2026 \
  --engine dual \
  --template pro \
  --format markdown
```

## Default Standard

- Timezone: `Asia/Shanghai`
- Longitude: `120.0`
- Default engine: `py`
- Optional chart export: `jpg` when supported, otherwise text-only output remains valid

## Deliverables

A strong output should include:
1. Calculation standard (timezone / longitude / unified calculation time)
2. Chart facts
   - 命宫 / 身宫
   - 十二宫
   - 主星组合
   - 三方四正
   - 四化
   - 大限 / 流年触发
3. Interpretation framework
   - what the structure suggests
   - where the reading is robust
   - where timing sensitivity matters
4. Practical summary
   - career
   - relationships
   - money
   - health / energy management
   - current-year focus and risk boundary

## Common Parameters

- `--engine py|js|dual`: primary / fallback / dual-check
- `--template lite|pro|executive`: output density
- `--chart none|svg|jpg`: chart rendering mode
- `--chart-quality 1-100`: JPG quality, default `92`
- `--chart-backend auto|cairosvg`: offline backend
- `--format markdown|json`: final output format

## Output Style Guardrails

- Separate **chart facts** from **traditional interpretation**.
- Present conclusions as trend / structure, not deterministic destiny claims.
- Make method transparency part of the deliverable.
- If dual-engine results differ, surface the discrepancy instead of hiding it.
- If chart export fails, continue with the report.

## Scope Boundary

- Offline only; no network dependency.
- Produce interpretive analysis only; not medical, legal, or financial advice.
- Optional image export should enhance delivery, not gate it.

## References

- `references/mapping.md`
- `references/interpretation-framework.md`
