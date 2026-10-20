---
name: skill-creator
description: |
  Author or improve a Skill (an executable, reusable capability with a
  ``SKILL.md`` plus optional ``scripts/``, ``references/``, and assets).
  Trigger this skill whenever the user wants to:
    - Capture a workflow they keep repeating into a fresh Skill
    - Polish an existing Skill's prompt, description, or examples
    - Tighten when-to-trigger wording so the model invokes the Skill more
      reliably
    - Discuss the Skill format, frontmatter, or how progressive
      disclosure works
  Do not wait for the user to say "skill-creator" verbatim — phrases
  like "turn this into a skill", "let's make a reusable thing for this",
  "improve my skill", or "tweak the description for this skill" should
  all reach this skill.
---

# Skill Creator

A meta-skill for designing new Skills and iterating on existing ones.
Skills are how you teach a Harness Agent a reusable capability — they
plug into the workspace's ``skills/`` directory and the agent loads
them on demand.

This is a **library-grade** version of the original Anthropic
``skill-creator`` recipe. It keeps the core authoring loop (intent →
draft → test → iterate) and drops the Anthropic-private tooling
(``claude -p``, ``eval-viewer``, ``run_loop.py``, Cowork-specific
behaviour). When you want quantitative benchmarking, plug those tools
in yourself — the Skill format and authoring loop don't depend on them.

## High-level loop

1. Capture intent. Ask the user what the Skill should enable, when it
   should trigger, and what the output looks like.
2. Draft ``SKILL.md`` with frontmatter and a short body.
3. Run a couple of realistic test prompts against the agent _with_ the
   Skill loaded, eyeball the results.
4. Edit the Skill (mostly the description and the body) based on what
   you observed.
5. Repeat 3–4 until you and the user are happy.
6. Optionally, sharpen the description for triggering accuracy (the
   description is the primary mechanism the model uses to decide
   whether to consult a Skill).

## Anatomy of a Skill

```
my-skill/
├── SKILL.md          (required — frontmatter + body)
├── scripts/          (optional — executable code the Skill calls)
├── references/       (optional — long docs the Skill points the model at on demand)
└── assets/           (optional — templates, icons, fonts used in outputs)
```

`SKILL.md` is a Markdown file with **YAML frontmatter** at the top:

```markdown
---
name: my-skill
description: One paragraph explaining what the skill does AND when to use it.
---

# Body

Imperative-voice instructions. Keep this under ~500 lines. Reference
files in `references/` when the model needs deep dives.
```

### Three-level loading (progressive disclosure)

The agent loads Skill content on demand:

| Level | What gets loaded                | When                                |
|-------|---------------------------------|-------------------------------------|
| 1     | Frontmatter (name + description) | Always — kept short (~100 words)    |
| 2     | The body of `SKILL.md`           | When the Skill triggers (<500 LOC)  |
| 3     | Files in `references/`, `scripts/` | When the body refs them explicitly |

This is why **the description is the most important field**: it's what
the model sees at every turn, and it's what decides whether the rest of
the Skill ever loads.

## Writing the description

Two failure modes to avoid:

1. **Under-triggering** — model doesn't load the Skill when it should.
   Fix: state the trigger contexts explicitly. _"Use this when the user
   asks about X, Y, Z, or any task involving foo, even if they don't
   mention the word 'skill'."_
2. **Over-triggering** — model loads the Skill on unrelated requests.
   Fix: state the negative scope. _"Do not use this for non-tabular
   data; for raw text use the text-reader skill."_

A well-shaped description has roughly this structure:

> Verb-led summary of what the Skill does. Trigger phrases / contexts /
> file types. Where it _doesn't_ apply (only if there's a near-neighbour
> Skill that competes).

## Writing the body

- **Imperative voice.** "Read the file" beats "you should read the
  file".
- **Explain why.** Tell the model what each step accomplishes; that
  generalises better than rigid MUSTs.
- **Show, don't lecture.** A two-line example is worth a paragraph of
  exposition.
- **Reference files clearly.** When you point at `references/foo.md`,
  say _what_ the model will find there and _when_ it should bother
  reading it.

If the Skill supports multiple variants (cloud providers, file formats,
domains), keep `SKILL.md` as a thin selector and put one reference file
per variant:

```
cloud-deploy/
├── SKILL.md         (workflow + selector)
└── references/
    ├── aws.md
    ├── gcp.md
    └── azure.md
```

The model only reads the variant it needs.

## Scripts pattern

When several test runs all reinvent the same helper script, that's a
strong signal to bundle it:

```
my-skill/
├── SKILL.md
└── scripts/
    └── do_the_thing.py
```

Reference it from the body:

> Run `python scripts/do_the_thing.py <args>` to <do the thing>. The
> script handles <edge cases> so the agent doesn't have to re-derive
> them every call.

## Authoring loop (concrete)

### Step 1: Interview

Ask the user (in their own words):

- What the Skill should _enable_ — what new behaviour does the agent
  need.
- When it should fire — concrete user phrases / file types /
  scenarios.
- What success looks like — a sample output, a passing assertion,
  "looks right by eye".
- Edge cases worth handling vs. punting on.

If the conversation history already contains the workflow ("turn this
into a skill"), pull what you can from it and only ask about the gaps.

### Step 2: Draft

Write a minimal `SKILL.md`. Resist over-engineering on the first pass.
Body under 200 lines is plenty for most Skills.

### Step 3: Pick test prompts

2–3 realistic prompts the user might actually send. Save them next to
the skill, e.g. in `evals/prompts.json`:

```json
{
  "skill_name": "my-skill",
  "prompts": [
    "User-style request 1",
    "User-style request 2"
  ]
}
```

### Step 4: Run them

In a fresh agent session with the Skill loaded:

```python
from octop_harness import HarnessAgent, HarnessAgentConfig

config = HarnessAgentConfig(
    name="skill-test",
    root_dir="./skill-test-workspace",
    providers={...},
    default_model="...",
)
agent = HarnessAgent(config)
result = agent.invoke("<one of the test prompts>")
```

Skills under `{workspace}/skills/<my-skill>/` are auto-loaded by the
deepagents skills middleware. Eyeball the run, capture what's wrong.

### Step 5: Iterate

Common changes after the first run:

- Description didn't trigger → make it pushier and list more contexts.
- Body told the model to go down the wrong path → reorder steps or
  delete the misleading sentence.
- The model rebuilt a script in flight → bundle the script and point
  at it.

Edit, rerun the test prompts, repeat. Two or three iterations is
usually enough.

### Step 6 (optional): Quantitative benchmarking

If the Skill has objectively checkable outputs (a generated CSV, a
filled form, a deterministic function), write a small harness that
runs each prompt N times and asserts on the output. Track pass rate
across iterations. Subjective Skills (writing style, design quality)
are not worth this — stick with human review.

When you do automate it, plug your favourite eval framework in here.
This Skill deliberately doesn't bundle one.

## Description optimisation pass

Once the Skill behaves well, take one focused pass on the description:

1. Write 8–10 prompts that _should_ trigger the Skill and 8–10 that
   shouldn't (especially near-misses with overlapping vocabulary —
   those are the hard ones).
2. For each prompt, ask the agent: "Given the user said '<prompt>',
   would you load the Skill described as `<description>`?" — score the
   model's answer against the ground truth.
3. Tweak the description until both rates are high. Pushier wording
   helps with under-triggering; explicit "do not use this for X" lines
   help with over-triggering.

You can do this entirely with `agent.invoke(...)` — no special tooling
required.

## Common pitfalls

- **Frontmatter missing or malformed.** If `name:` or `description:`
  is missing, the Skill won't load. Validate by parsing with any YAML
  parser before saving.
- **`SKILL.md` over 500 lines.** The model gets lost. Split the long
  parts into `references/<topic>.md` and have the body point at them.
- **Description is too generic** ("Helps with files."). The model
  can't decide when to use it; either it triggers everywhere or
  nowhere.
- **Prescriptive MUSTs without rationale.** They generalise poorly.
  Replace with the reasoning behind the rule.
- **Bundling a script that can be one-liner shell.** Don't pre-empt
  the agent's judgement; only bundle when you observe repeated
  reinvention across runs.

## Checklist before "done"

- `SKILL.md` parses as Markdown with valid YAML frontmatter.
- `name` + `description` present and concrete.
- Body under 500 lines.
- 2–3 test prompts pass by human review.
- Description triggers the Skill on representative phrasings.
- Files in `references/` and `scripts/` are referenced from the body
  with a one-line "read this when…" hint.

When all six are true, ship it.
