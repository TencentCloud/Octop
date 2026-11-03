---
name: feast
description: |
  Comprehensive meal planning system with cultural themes, authentic recipes, intelligent shopping, and surprise reveals. Use when:
  - Planning weekly meals or menus
  - Generating shopping lists
  - Asking for recipe ideas or cooking help
  - Reviewing past meals or planning ahead
  - Onboarding a new user to the meal system
  - Looking for cuisine inspiration or cultural food events
  - Tracking dietary goals or nutrition
  - Managing favourites, failures, or meal history
---

# Feast

A meal planning skill that transforms weekly cooking into a cultural experience.

## Quick Start

1. **New user?** Run onboarding: "Let's set up Feast" or "Onboard me for meal planning"
2. **Returning user?** Check status: "What's the meal plan status?"
3. **Planning day?** Start planning: "Let's plan next week's meals"
4. **Cooking day?** Get reveal: "What's for dinner?"

## Core Files

User data lives in their workspace:

```
workspace/meals/
├── profile.yaml          # User preferences (created during onboarding)
├── history.yaml          # What they've eaten
├── favourites.yaml       # Loved recipes
├── failures.yaml         # Never again
└── weeks/
    └── YYYY-MM-DD.md     # Each week's plan (self-contained)
```

**Note:** Weekly plans are fully self-contained — each day's recipe, theme research, music playlist, and cultural context is embedded directly in the week file. There are no separate recipe or theme files.

## Weekly Cadence

Default schedule (user-configurable):

| Day | Activity | Trigger |
|-----|----------|---------|
| Thursday | Research & draft | "Let's plan next week" |
| Friday | Confirm plan | "Confirm the meal plan" |
| Saturday | Shopping list | "Generate shopping list" |
| Sunday | Shopping | User shops |
| Week | Daily reveals | "What's for dinner?" |
| End of week | Review | "Review this week's meals" |

## Notifications

Feast sends reminders at key moments: planning day, confirmation, shopping list, daily reveals, and week review. These are delivered via cron jobs that spawn isolated agents to send notifications.

### Notification Channels

Users configure their preferred channel in `profile.yaml` under `schedule.notifications.channel`:

| Channel | Delivery Method |
|---------|-----------------|
| `auto` | Delivers to the current session or first available channel |
| `telegram` | Sends via Telegram (requires Telegram channel configured in OpenClaw) |
| `discord` | Sends via Discord (requires Discord channel configured in OpenClaw) |
| `signal` | Sends via Signal (requires Signal channel configured in OpenClaw) |
| `webchat` | Outputs to the chat session |

### Push Notifications (Optional)

For notifications to mobile devices independent of chat channels, users can enable push notifications:

```yaml
schedule:
  notifications:
    push:
      enabled: true
      method: "pushbullet"    # or "ntfy"
```

**Supported methods:**

- **Pushbullet** — Requires the `pushbullet-notify` skill installed separately with API key configured
- **ntfy** — Uses ntfy.sh (or self-hosted); configure topic in profile

Push notifications are sent *in addition to* the primary channel, not instead of it. If push delivery fails, the notification still goes to the primary channel.

### Timing

Notifications are delivered via OpenClaw's cron system with `wakeMode: "next-heartbeat"`. This means notifications arrive within the heartbeat interval (typically up to 1 hour) after the scheduled time. For most meal planning purposes, this slight delay is acceptable.

### Managing Notifications

Users can adjust their notification preferences anytime:

- "Change my Feast notifications to Telegram"
- "Turn off morning hints"
- "Enable Pushbullet notifications"

When updating, remove old cron jobs using stored IDs and create new ones with updated settings.

## Workflows

### Onboarding

Read [references/onboarding.md](references/onboarding.md) for the full flow.

Essential questions:
1. Location (for seasonality, units, stores)
2. Household size & portion needs
3. Week structure (start day, cooking days, cheat day)
4. Dietary requirements & phase
5. Equipment & cooking confidence
6. Preferences (cuisines, spice, budget)

Save to `workspace/meals/profile.yaml`.

### Planning (Thursday)

1. Check user profile
2. Review history (avoid recent repeats)
3. Check upcoming cultural events (see [references/events.md](references/events.md))
4. Check seasonality for location
5. Select 6-7 meals with:
   - Cuisine variety
   - Ingredient overlap
   - Balanced nutrition
   - Mix of quick/involved
6. **For each meal, research and embed:**
   - **The Place:** Identify specific region of origin (drill down to province, city, or area). Research regional context, history, current events. Write an evocative description.
   - **The Dish:** Research authentic recipe from native sources (search in original language). Include origin story, cultural significance, full ingredients and method.
   - **The Soundtrack:** Curate a 1-2 hour playlist with contemporary hits + classic/traditional from the region (see [references/theme-research.md](references/theme-research.md)). Include full tracklist with links.
   - **Setting the Scene:** How to serve, what to drink, atmosphere tips.
7. Draft plan to `workspace/meals/weeks/YYYY-MM-DD.md` (all content embedded in this single file)
8. Present summary (themes only, not full reveals)

### Confirmation (Friday)

1. Present draft plan with themes
2. Allow amendments
3. Mark as confirmed
4. Set up daily reveal reminders

### Shopping List (Saturday)

1. Generate from confirmed plan
2. Optimise:
   - Group by category
   - Combine overlapping ingredients
   - Check pack sizes vs needs
   - Flag seasonal items
3. **Price check key ingredients** (see [references/price-checking.md](references/price-checking.md)):
   - Identify top 3-5 most expensive items (usually proteins, specialty ingredients)
   - Check prices across user's available stores
   - Note current deals, multi-buy offers, loyalty card prices
   - Add price recommendations to the shopping list
   - Suggest shopping strategy (single store or split if savings are significant)
4. Present for review with price guidance
5. Allow amendments
6. Mark as approved

### Daily Reveal

1. Check it's a cooking day
2. Reveal:
   - Full recipe (in user's units)
   - **Theme dossier highlights:**
     - The place: Regional context, history, and character
     - What's happening there now (current news/events from planning time)
     - The dish: Origin story, cultural significance, how it's eaten locally
   - **Curated playlist:**
     - Contemporary hits from the region (what people there listen to now)
     - Classic/traditional music from the region
     - Full tracklist with links (Spotify/YouTube)
     - The vibe and journey the playlist creates
   - Setting the scene: Serving suggestions, drinks pairings, atmosphere tips
3. Optional morning hint for anticipation

### Review (End of Week)

1. For each meal: rating (1-5), notes
2. Update history
3. Identify favourites → add to favourites
4. Identify failures → add to failures
5. Capture improvements for system
6. Save review to week file

## Recipe Regionalisation

All recipes stored in standardised internal units. On output, convert to user's preferred units:

- Temperature: Celsius / Fahrenheit / Gas Mark
- Weight: Metric (g/kg) / Imperial (oz/lb)
- Volume: Metric (ml/L) / Cups

See [references/conversions.md](references/conversions.md).

## Authenticity Guidelines

When researching cuisines:
1. Search in the original language where possible
2. Look for recipes from native sources, not just English food blogs
3. **Identify the specific region of origin** — not just "Thai food" but "Northern Thai, Chiang Mai style"
4. **Research music that's actually from the region:**
   - Find contemporary hits (what's charting there now)
   - Find classic/traditional music (legendary artists from the region)
   - Build a curated 1-2 hour playlist — not generic Spotify searches
   - See [references/theme-research.md](references/theme-research.md) for guidance
5. **Research the region itself** — history, current events, social context, what it's famous for
6. Note cultural context and any associated events
7. Respect dietary traditions (e.g., no pork in Middle Eastern themes)
8. **Embed everything in the week plan** — recipes, themes, music, and context all go in the single week file

See [references/cuisines/](references/cuisines/) for per-cuisine guides.

## Templates

- [templates/profile.yaml](templates/profile.yaml) — User profile
- [templates/week.md](templates/week.md) — Weekly plan with embedded recipes, themes, music, and shopping list
- [templates/shopping-list.md](templates/shopping-list.md) — Standalone shopping list format (for reference; usually embedded in week)

## References

- [references/onboarding.md](references/onboarding.md) — User onboarding guide
- [references/theme-research.md](references/theme-research.md) — How to research cultural themes and curate music
- [references/price-checking.md](references/price-checking.md) — Smart shopping and price comparison guidance
- [references/events.md](references/events.md) — Cultural events calendar for themed planning
- [references/nutrition.md](references/nutrition.md) — Dietary phases and balanced meal guidance
- [references/conversions.md](references/conversions.md) — Unit conversion tables
- [references/cuisines/](references/cuisines/) — Per-cuisine research guides
- [references/seasonality/](references/seasonality/) — Regional seasonal produce

## Scripts

### History Tracking

After a meal is revealed and cooked, update history:

```bash
python scripts/update-history.py \
    --meals-dir ~/.openclaw/workspace/meals \
    --date 2026-02-03 \
    --name "Thai Green Curry" \
    --cuisine "Thai" \
    --region "Central Thailand" \
    --week-file "2026-02-02.md" \
    --rating 4 \
    --notes "Great, maybe more chilli next time"
```

This updates `history.yaml` and recalculates statistics automatically.

When doing the daily reveal, after the user confirms they've cooked and optionally rated the meal, run this script to keep history current.

## Health & Nutrition

- Track calories per meal if user has a target
- Ensure weekly variety across food groups
- Respect dietary phases (weight loss = deficit, etc.)
- Flag any nutritional concerns

See [references/nutrition.md](references/nutrition.md).

## Seasonal Awareness

Check seasonality for user's location before suggesting ingredients. Seasonal produce is:
- Better quality
- Often cheaper
- More environmentally responsible

Not every ingredient needs to be in season, but prefer seasonal when possible.

See [references/seasonality/](references/seasonality/) for regional guides.
