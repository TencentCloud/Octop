# Personas

Each agent has an optional MBTI persona (`persona_mbti` column on the
`agents` row). The persona profile is rendered into the agent's
`SOUL.md` (via `octop.infra.agents.persona.render_persona_template` /
`PersonaLoader`) at boot. If the user also sets a `system_prompt` on the
agent row, it is **appended** to the persona — the persona file is the
backbone, the user prompt is the trim.

If `persona_mbti` is `NULL` or the empty string, octop falls back to
the built-in `_DEFAULT_PERSONA_TEMPLATE` (warm, direct, competent tone).

## Where the 16 codes live

Persona content is now data, not files:

| Resource | Location |
|----------|----------|
| 16 `MBTIProfile` records | [`src/octop/infra/agents/persona/mbti_profiles.py`](../src/octop/infra/agents/persona/mbti_profiles.py) |
| Public API (`get_profile`, `get_all_profiles`, `MBTIProfile`, …) | same module (also re-exported from `octop.infra.agents.persona`) |
| SOUL.md / persona rendering | [`src/octop/infra/agents/persona/loader.py`](../src/octop/infra/agents/persona/loader.py) |
| Persisted agent field | `agents.persona_mbti` (string, e.g. `"INTJ"`) |

The legacy `src/octop/infra/agents/personas/*.md` directory is gone —
persona content is now structured dataclasses with explicit
`summary_zh` / `summary_en` / `behavior_*` fields, so it can be
localized without shipping 16 separate Markdown files.

## The 16 codes

Source: `mbti_profiles._PROFILES` (exposed via
`get_all_profiles()`).

| Code | English name | One-liner |
|------|--------------|-----------|
| `INTJ` | The Architect | Imaginative strategist with a plan for everything. |
| `INTP` | The Logician | Innovative inventor with an unquenchable thirst for knowledge. |
| `ENTJ` | The Commander | Bold, decisive, efficiency-obsessed; expects results. |
| `ENTP` | The Debater | Inventive and quick-witted; loves contrary hypotheses. |
| `INFJ` | The Advocate | Insightful and quietly purposeful; empathetic but focused. |
| `INFP` | The Mediator | Idealistic and deeply curious; values authenticity. |
| `ENFJ` | The Protagonist | Warm, articulate, people-oriented; coaches others toward their best. |
| `ENFP` | The Campaigner | Enthusiastic, imaginative, generative; infectious brainstormer. |
| `ISTJ` | The Logistician | Dependable, thorough, detail-oriented; tracks every commitment. |
| `ISFJ` | The Defender | Quietly dedicated; remembers context; consistent. |
| `ESTJ` | The Executive | Organized, direct, standards-driven; documents decisions. |
| `ESFJ` | The Consul | Sociable, empathetic, harmony-seeking. |
| `ISTP` | The Virtuoso | Hands-on; prefers concrete experiments; fixes things efficiently. |
| `ISFP` | The Adventurer | Gentle, open-minded, supportive; explores without rushing. |
| `ESTP` | The Entrepreneur | Action-oriented; cuts to what works right now; pragmatic. |
| `ESFP` | The Entertainer | Expressive, spontaneous, engaging; resourceful improviser. |
| `_default` | Default | Tone: warm, direct, competent. Prefer concrete answers over hedging. |

## What each profile carries

Every `MBTIProfile` dataclass exposes:

| Field | Use |
|-------|-----|
| `code` | Stable identifier persisted on `agents.persona_mbti` |
| `name_zh` / `name_en` | Display name (locale-aware) |
| `nickname_zh` | Internet-meme nickname (zh only) |
| `summary_zh` / `summary_en` | One-line elevator pitch |
| `descriptors_zh` / `descriptors_en` | Comma-separated keyword tags |
| `dimensions: MBTIDimensions` | Four-axis `(pole, percentage)` tuples (`ei` / `sn` / `tf` / `jp`) |
| `behavior: MBTIBehaviorMapping` | Six behaviour strings (answer_style, casual_chat, conflict, creativity, emotion, planning) in both locales |
| `color` | UI accent colour (hex) |
| `symbol` | Decorative Unicode glyph |

## Template variables

The SOUL.md template rendered by `PersonaLoader.load(code)` always
exposes three placeholders:

| Variable | Source |
|----------|--------|
| `{agent_name}` | `agents.name` |
| `{user_display}` | `users.display_name` (falls back to `users.username`) |
| `{custom}` | `agents.system_prompt` (free-form trim appended verbatim) |

The rendered text is what eventually lands in the LangGraph state as
the system message. It is the only knob that distinguishes one
persona-equipped agent from another at the prompt level.

## Selecting a persona

```bash
# create an agent with the INTJ persona
curl -X POST http://127.0.0.1:8088/api/agents \
  -H "Authorization: Bearer $TOK" \
  -H "Content-Type: application/json" \
  -d '{
        "name": "architect",
        "persona_mbti": "INTJ",
        "default_model": "openai:gpt-4o"
      }'

# list available codes
curl http://127.0.0.1:8088/api/mbti/codes -H "Authorization: Bearer $TOK"

# inspect the full profile (dimensions, behaviour, UI metadata)
curl http://127.0.0.1:8088/api/mbti/codes/INTJ -H "Authorization: Bearer $TOK"

# rendered template (the legacy /api/personas/{code} shim still works)
curl http://127.0.0.1:8088/api/mbti/preview/INTJ -H "Authorization: Bearer $TOK"

# apply a persona and reload the agent runtime
curl -X PUT http://127.0.0.1:8088/api/agents/architect/mbti \
  -H "Authorization: Bearer $TOK" \
  -H "Content-Type: application/json" \
  -d '{ "code": "INTJ" }'
```

The CLI exposes the same path via `octop agent create --persona-mbti INTJ`.

## Customising

Editing `mbti_profiles.py` and restarting the server is the supported
path today. There is no admin endpoint for persona content — by
design: persona drift across users would make agent behaviour
irreproducible. Per-agent trimming is the official extension point
(`system_prompt` / `config.persona`); see AGENTS.md §7 for the
backend I/O rules around the resulting `SOUL.md` file.
