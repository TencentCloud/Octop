# Feast — Specification

**Version:** 1.0.1  
**Status:** Released  
**Created:** 2026-02-01  

---

## Overview

Feast is a comprehensive meal planning skill for OpenClaw that transforms weekly cooking from a chore into a cultural experience. It handles the entire journey from planning through shopping to cooking, with authentic regional themes, intelligent shopping optimisation, and an element of surprise and delight.

### Core Principles

1. **Advance Planning** — Plans are researched and confirmed days ahead, not improvised
2. **Authenticity** — Cuisines, recipes, and music are properly researched, not Westernised defaults
3. **Surprise & Delight** — Shopping is transparent, but the meal reveal happens on the day
4. **Intelligence** — Ingredient overlap, waste reduction, pack-size optimisation across weeks
5. **Health First** — Balanced nutrition adapted to dietary phases and goals
6. **Seasonal Awareness** — Location-aware seasonality for responsible food choices
7. **Cultural Context** — Themes tied to real events, history, and contemporary culture
8. **Solid Foundations** — Data structures that enable future features (reviews, trends, analytics)
9. **Universal** — Works for any user, any region, any household size
10. **Immersive Experience** — Each meal is a journey: regional history, curated music, cultural context
11. **Accessible** — Smart price checking to help users shop well on any budget

---

## User Onboarding

New users go through onboarding to establish their profile. This captures:

### Required
- **Location** — Country/region (for seasonality, units, stores)
- **Household size** — Number of portions per meal
- **Week structure** — Which day the week starts, how many cooking days
- **Dietary requirements** — Restrictions, allergies, preferences

### Optional (with sensible defaults)
- **Dietary phase** — Weight loss, maintenance, bulking, etc.
- **Budget** — Strict limit or "be sensible"
- **Cheat day** — Fixed day, flexible, or none
- **Available stores** — For shopping list optimisation
- **Cuisine preferences** — Favourites, dislikes, exploration level
- **Spice tolerance** — None to extreme
- **Equipment** — What they have (oven, air fryer, slow cooker, etc.)
- **Cooking confidence** — Beginner to advanced

### Special Cases
- **OMAD (One Meal A Day)** — Portion multiplier (e.g., 2x portions as single meal)
- **Batch cooking** — Cook once, eat twice
- **Multi-week planning** — For pack optimisation

---

## Weekly Cadence

The default cadence (user-configurable):

| Day | Activity |
|-----|----------|
| Thursday | Research themes, draft plan based on upcoming events, seasons, history |
| Friday | Present plan for confirmation, allow amendments |
| Friday | Shopping list generated, reviewed, finalised |
| Saturday/Sunday | Shopping day (flexible) |
| Week begins | Cooking starts, daily reveals |

### Daily Reveal

On each cooking day:
- Afternoon: Reveal the full experience
- Optional brief morning hint for mystery/anticipation
- **The Place:** Regional context, history, what's happening there now
- **The Dish:** Origin story, cultural significance, how it's eaten locally
- **The Soundtrack:** Curated playlist with contemporary + classic music from the region
- **Setting the Scene:** Serving suggestions, drinks pairings, atmosphere tips
- Recipe presented in user's regional format

---

## Data Structures

### File Formats

**User Profile** — YAML (`profile.yaml`)  
**Weekly Plans** — Markdown with YAML frontmatter (`weeks/YYYY-MM-DD.md`) — self-contained  
**History/Favourites/Failures** — YAML (machine-only)

Weekly plans are **fully self-contained** — each day's recipe, cultural context, music playlist, and shopping list is embedded directly in the week file. There are no separate recipe or theme files.

The markdown+frontmatter approach provides:
- Human-readable content (markdown body)
- Machine-readable metadata for tracking (YAML frontmatter)
- Single file per week (simpler management, no linking complexity)

### User Profile (`profile.yaml`)

```yaml
version: 1
user:
  name: string
  location:
    country: string (ISO 3166-1)
    region: string (optional, for local seasonality)
    timezone: string
  
  household:
    portions: integer (base portions per meal)
    portionMultiplier: float (e.g., 2.0 for OMAD double portions)
  
  schedule:
    weekStart: string (sunday|monday)
    cookingDays: integer (1-7)
    cheatDay: string|null (day name or null for none)
    cheatDayFlexible: boolean
  
  dietary:
    phase: string (maintenance|weight_loss|weight_gain|custom)
    restrictions: string[] (allergies, intolerances)
    preferences: string[] (vegetarian-leaning, low-carb, etc.)
    calorieTarget: integer|null (daily kcal or null for untracked)
  
  cooking:
    confidence: string (beginner|intermediate|advanced)
    equipment: string[] (oven, hob, air_fryer, slow_cooker, etc.)
    timeAvailable: string (quick|moderate|leisurely)
    spiceTolerance: string (none|mild|medium|hot|extreme)
  
  preferences:
    budget: string (strict|moderate|flexible)
    stores: string[] (available stores)
    cuisinesFavourite: string[]
    cuisinesAvoid: string[]
    explorationLevel: string (comfortable|adventurous|very_adventurous)
  
  units:
    temperature: string (celsius|fahrenheit|gas_mark)
    weight: string (metric|imperial)
    volume: string (metric|cups)
```

### Weekly Plan (`week-YYYY-MM-DD.md`)

Weekly plans are self-contained — all recipes, cultural context, music, and shopping are embedded.

```yaml
version: 1
weekOf: date
status: string (draft|confirmed|active|complete)
createdAt: datetime
confirmedAt: datetime|null

profile:
  # Snapshot of relevant user profile at time of planning
  portions: integer
  portionMultiplier: float
  calorieTarget: integer|null

weekTheme:
  name: string|null (e.g., "Mediterranean Summer")
  event: string|null
  description: string|null

days:
  - date: date
    type: string (cooking|cheat|skip)
    revealed: boolean
    
    # THE PLACE — Regional context (embedded)
    place:
      country: string
      region: string (specific region)
      city: string|null
      description: string (evocative, 2-3 paragraphs)
      currentContext: string (news, events from planning time)
      famousFor: string
    
    # THE DISH — Full recipe (embedded)
    dish:
      name: string
      cuisine: string
      story: string (origin, evolution)
      culturalSignificance: string
      modernContext: string
      prepTime: integer (minutes)
      cookTime: integer (minutes)
      difficulty: string (easy|medium|hard)
      equipment: string[]
      nutrition:
        caloriesPerServing: integer|null
        protein: integer|null
        carbs: integer|null
        fat: integer|null
        fibre: integer|null
      ingredients:
        - name: string
          amount: string
          unit: string
          category: string
          notes: string|null
      method:
        - step: integer
          instruction: string
          tips: string|null
      tips: string[]
      source:
        url: string|null
        adapted: boolean
        notes: string|null
    
    # THE SOUNDTRACK — Curated music (embedded)
    music:
      philosophy: string (why these tracks)
      duration: string
      contemporary:
        - artist: string
          track: string
          year: integer|null
          notes: string|null
      classic:
        - artist: string
          track: string
          era: string
          notes: string|null
      playlist:
        - artist: string
          track: string
      spotifyLink: string|null
      youtubeLink: string|null
      fallbackSearch: string|null
    
    # SETTING THE SCENE (embedded)
    atmosphere:
      serving: string
      drinks: string[]
      ambience: string|null
    
    # Research metadata
    research:
      confidenceLevel: string (high|medium|low)
      sources: string[]
      compiled: datetime
    
    # Tracking
    cooked: boolean
    rating: integer|null (1-5)
    notes: string|null

shopping:
  status: string (pending|approved|purchased)
  generatedAt: datetime|null
  priceCheck:
    performed: boolean
    checkedOn: date|null
    strategy: string|null
    primaryStore: string|null
    potentialSavings: float|null
  keyDeals: Deal[]
  items:
    proteins: Item[]
    vegetables: Item[]
    # ... other categories
  storecupboard: string[]
  estimatedCost: float|null
  actualCost: float|null

review:
  completed: boolean
  overallRating: integer|null
  highlights: string[]
  improvements: string[]
  addToFavourites: string[]
  neverAgain: string[]
  musicDiscoveries: string[]
```

### Shopping List (`shopping-list.yaml`)

```yaml
version: 1
weekOf: date
generatedAt: datetime
status: string (draft|approved|purchased)

items:
  - name: string
    amount: float
    unit: string
    category: string
    usedIn: string[] (recipe names)
    seasonal: boolean
    estimatedPrice: float|null
    store: string|null (if store-specific)
    notes: string|null
    checked: boolean

byCategory:
  # Grouped view for shopping convenience
  proteins: Item[]
  vegetables: Item[]
  dairy: Item[]
  carbs: Item[]
  spices: Item[]
  other: Item[]

totals:
  estimatedCost: float|null
  itemCount: integer
```

### History (`history.yaml`)

Tracks what's been cooked for avoiding recent repeats and building statistics.

```yaml
version: 1
lastUpdated: datetime

meals:
  - date: date
    name: string (dish name)
    cuisine: string
    region: string|null
    weekFile: string (reference to week file, e.g., "2026-02-02.md")
    rating: integer|null
    notes: string|null
    tags: string[]

statistics:
  totalMealsCooked: integer
  cuisineBreakdown: { cuisine: count }
  averageRating: float
  topRatedMeals: string[]
  recentCuisines: string[] (last 4 weeks)
```

### Favourites & Failures

Track dishes to repeat or avoid. References are by name (not ID, since recipes are embedded in week files).

```yaml
# favourites.yaml
version: 1
meals:
  - name: string (dish name)
    cuisine: string
    region: string|null
    addedAt: datetime
    timesCooked: integer
    lastCooked: date
    weekFile: string|null (original week file for reference)
    notes: string|null

# failures.yaml  
version: 1
meals:
  - name: string (dish name)
    cuisine: string
    reason: string
    date: date
    avoidUntil: date|null (null = permanent)
```

---

## Theme Research & Cultural Immersion

Every meal in Feast is more than just food — it's a window into a place. The theme research process ensures each meal feels like a genuine cultural experience.

### Regional Specificity

Don't stop at country level. Drill down:
- **Bad:** "Thai food"
- **Good:** "Northern Thai, Chiang Mai style"

The more specific the origin, the richer the experience.

### What Gets Researched

For each meal, research and embed the following directly into the week plan:

1. **The Place**
   - Brief history of the region (evocative, not encyclopedic)
   - What's happening there now (current events, seasonal context)
   - What the region is famous for beyond food
   - Social and cultural context

2. **The Dish**
   - Origin story (where it came from, how it evolved)
   - Cultural significance (when eaten, by whom, what it means)
   - Modern context (street food? home cooking? celebration?)

3. **The Soundtrack** (1-2 hours, curated)
   - Contemporary hits (what people there listen to NOW)
   - Classic/traditional (timeless sounds from the region)
   - Ordered tracklist with an arc (cooking → eating → wind-down)
   - Links to Spotify/YouTube

4. **Setting the Scene**
   - How the dish would be served locally
   - Drinks pairings
   - Atmosphere suggestions

All of this content is embedded directly in the weekly plan file — there are no separate theme or recipe files.

### Music Curation Guidelines

**DO NOT** just search "[Cuisine] playlist" on Spotify. Those are generic compilations for Western audiences.

Instead:
- Search local charts and streaming data for contemporary hits
- Research legendary artists from the specific region
- Look for local genres (not just international pop)
- Mix contemporary and classic
- Build a journey with an arc
- Aim for 1-2 hours total

See [references/theme-research.md](../references/theme-research.md) for detailed research guidance.

---

## Price Checking & Smart Shopping

Feast helps users shop smart by checking prices across their available stores.

### When to Check

**Always check:**
- Proteins (most expensive items)
- Specialty ingredients
- Items over £5 (or regional equivalent)
- Bulk items where savings multiply

**Skip checking:**
- Storecupboard staples (minimal variation)
- Very cheap items (not worth the time)
- Quality-critical items where cheapest isn't best

### The Process

1. **Flag target ingredients** (top 3-5 most expensive)
2. **Check prices** across user's listed stores
3. **Note deals** (multi-buy, loyalty cards, temporary offers)
4. **Recommend strategy:**
   - Single store (convenience)
   - Split (if savings significant)
   - Deal-driven (if specific offers worth chasing)

### Shopping List Output

Price guidance integrated into the shopping list:
- Key deals highlighted
- Store recommendations per item or category
- Quality notes where cheapest isn't best
- Disclaimer about price accuracy

See [references/price-checking.md](../references/price-checking.md) for detailed guidance.

---

## Conversion Reference

Baked-in conversions for recipe regionalisation:

### Volume
| US | UK | Metric |
|----|-----|--------|
| 1 cup | - | 240ml |
| 1 tbsp | 1 tbsp (15ml) | 15ml |
| 1 tsp | 1 tsp (5ml) | 5ml |
| 1 fl oz | 1 fl oz (28ml) | 30ml |

Note: US tbsp = 14.8ml, UK tbsp = 15ml, AU tbsp = 20ml

### Weight
| Imperial | Metric |
|----------|--------|
| 1 oz | 28g |
| 1 lb | 454g |

### Temperature
| Gas Mark | °C | °F | Description |
|----------|-----|-----|-------------|
| 1 | 140 | 275 | Very low |
| 2 | 150 | 300 | Low |
| 3 | 160 | 325 | Moderately low |
| 4 | 180 | 350 | Moderate |
| 5 | 190 | 375 | Moderately hot |
| 6 | 200 | 400 | Hot |
| 7 | 220 | 425 | Hot |
| 8 | 230 | 450 | Very hot |
| 9 | 240 | 475 | Very hot |

---

## Notification System

Feast uses OpenClaw's cron system to send reminders at key moments in the weekly cadence.

### Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Cron Job Fires                          │
│                           │                                 │
│                           ▼                                 │
│              ┌─────────────────────────┐                    │
│              │   agentTurn payload     │                    │
│              │   (isolated session)    │                    │
│              └───────────┬─────────────┘                    │
│                          │                                  │
│                          ▼                                  │
│              ┌─────────────────────────┐                    │
│              │  Read profile.yaml      │                    │
│              │  → notifications config │                    │
│              └───────────┬─────────────┘                    │
│                          │                                  │
│            ┌─────────────┼─────────────┐                    │
│            ▼             ▼             ▼                    │
│     ┌──────────┐  ┌──────────┐  ┌──────────┐               │
│     │ Channel  │  │ Channel  │  │  Push    │               │
│     │(telegram)│  │(webchat) │  │(optional)│               │
│     └──────────┘  └──────────┘  └──────────┘               │
└─────────────────────────────────────────────────────────────┘
```

### Why agentTurn, Not systemEvent

Cron jobs use `agentTurn` payloads instead of `systemEvent` because:

1. **systemEvent** only injects text into the chat session — users won't see it unless actively watching
2. **agentTurn** spawns an isolated agent that can use tools to deliver notifications via the user's preferred channel

### Supported Channels

| Channel | Method | Requirement |
|---------|--------|-------------|
| `auto` | Detect from session context | None |
| `telegram` | OpenClaw message tool | Telegram configured |
| `discord` | OpenClaw message tool | Discord configured |
| `signal` | OpenClaw message tool | Signal configured |
| `webchat` | Session output | None |

### Push Notifications (Optional)

For mobile push independent of chat:

| Method | Implementation | Requirement |
|--------|---------------|-------------|
| Pushbullet | External skill | pushbullet-notify skill installed |
| ntfy | HTTP POST to ntfy.sh | Topic configured in profile |

Push notifications supplement the primary channel; they don't replace it.

### Timing Behaviour

Cron jobs use `wakeMode: "next-heartbeat"`, meaning:
- Jobs execute on the next heartbeat after their scheduled time
- With default 1-hour heartbeat, notifications may arrive up to 1 hour late
- Acceptable for meal planning; not suitable for time-critical alerts

### Profile Schema (notifications section)

```yaml
schedule:
  notifications:
    channel: string           # auto, telegram, discord, signal, webchat
    push:
      enabled: boolean
      method: string|null     # pushbullet, ntfy, or null
      ntfy:
        topic: string|null
        server: string        # default: https://ntfy.sh
    quietHoursStart: string   # HH:MM format
    quietHoursEnd: string     # HH:MM format
```

---

## Technical Requirements

- **Importable** — Works when installed on any OpenClaw instance
- **Stateless skill** — All user data lives in workspace, not skill
- **Version controlled** — Git, semantic versioning
- **Well documented** — Onboarding, workflows, schemas all documented
- **Tested** — Scripts tested, templates validated

