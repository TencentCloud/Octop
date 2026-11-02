# Feast 🍽️

A comprehensive meal planning skill for [OpenClaw](https://openclaw.ai) that transforms weekly cooking into a cultural experience.

## Features

- **Weekly meal planning** with advance preparation
- **Authentic cuisines** — properly researched, not Westernised defaults
- **Intelligent shopping lists** — ingredient overlap, waste reduction, price checking
- **Cultural immersion** — regional history, current events, and context for every dish
- **Curated music** — 1-2 hour playlists with contemporary + classic music from each region (not generic Spotify searches)
- **Smart shopping** — price checking across stores, deal alerts, shopping strategy recommendations
- **Surprise & delight** — shopping is transparent, daily meal reveals with full cultural experience
- **Health-focused** — balanced nutrition, dietary phases, calorie tracking
- **Seasonal awareness** — location-based produce guidance
- **Universal** — works for any user, any region, any household size

## Installation

### Via ClawHub (recommended)

```bash
clawhub install feast
```

### Manual installation

```bash
git clone https://github.com/smadgerano/feast.git ~/.openclaw/skills/feast
```

## Setup

Ask your agent to run through the Feast onboarding process.

This will guide you through making all the dietary and regional decisions needed, and then start planning your culinary experiences.


## Documentation

- [Specification](docs/SPECIFICATION.md) — Full system design
- [SKILL.md](SKILL.md) — Core skill instructions
- [Onboarding](references/onboarding.md) — New user setup guide
- [Theme Research](references/theme-research.md) — How to create cultural experiences
- [Price Checking](references/price-checking.md) — Smart shopping guidance
- [Conversions](references/conversions.md) — Unit conversion reference

## Structure

```
feast/
├── SKILL.md                    # Core skill instructions
├── LICENSE                     # MIT License
├── docs/
│   └── SPECIFICATION.md        # Full specification
├── references/
│   ├── onboarding.md           # User onboarding guide
│   ├── theme-research.md       # How to research cultural themes
│   ├── price-checking.md       # Smart shopping guidance
│   ├── conversions.md          # Unit conversions
│   ├── nutrition.md            # Dietary guidance
│   ├── events.md               # Cultural events calendar
│   ├── cuisines/               # Per-cuisine research guides (grow organically)
│   └── seasonality/            # Regional seasonal produce (grow organically)
├── templates/
│   ├── profile.yaml            # User profile template
│   ├── week.md                 # Weekly plan (self-contained: recipes, themes, music, shopping)
│   └── shopping-list.md        # Standalone shopping list format (reference)
└── scripts/
    └── update-history.py       # History tracking script
```

## User Data

User data lives in the OpenClaw workspace, not the skill:

```
workspace/meals/
├── profile.yaml            # User preferences
├── history.yaml            # Meal history
├── favourites.yaml         # Favourite recipes
├── failures.yaml           # Recipes to avoid
└── weeks/
    └── YYYY-MM-DD.md       # Weekly plans (self-contained)
```

Each weekly plan is fully self-contained — recipes, cultural context, music playlists, and shopping lists are all embedded in a single file.

## Contributing

Issues and pull requests welcome.

## License

MIT — see [LICENSE](LICENSE)
