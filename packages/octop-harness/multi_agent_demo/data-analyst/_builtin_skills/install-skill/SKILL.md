---
name: install-skill
description: |
  Install a Skill into the current workspace from a Git repository or
  local directory. Use this whenever the user wants to:
    - Add a new Skill to the agent ("install the X skill", "add the
      foo skill", "I want a skill that does Y, find one")
    - Pull the latest version of an already-installed Skill ("update
      the X skill", "refresh my skills")
    - List Skills currently active in the workspace
    - Remove a Skill they no longer need
  Trigger on phrases like "装一个 X skill", "安装技能", "install
  skill", "update skill", "list skills", "remove skill", "找个能 X
  的 skill". Do not require the user to say the literal Skill name —
  if they describe a capability, propose a candidate Skill (Git URL
  or local path) and confirm before installing.
---

# Install Skill

A Skill that helps the agent install, list, update, and remove other
Skills in the workspace.

Skills live under ``{workspace}/skills/<skill-name>/`` and are
auto-discovered by the deepagents skills middleware on the next agent
session. Built-in Skills shipped with ``octop-harness`` live
under ``{workspace}/_builtin_skills/`` and **must not** be edited
directly — they are wiped and re-synced from the package on every
``HarnessAgent.init()`` call.

## Sources we support

| Source                  | What you give the agent                              | Example                                            |
|-------------------------|------------------------------------------------------|----------------------------------------------------|
| Git repo (single Skill) | A Git URL whose root contains ``SKILL.md``           | ``https://github.com/owner/my-skill.git``          |
| Git repo (subdir)       | A Git URL + a relative path inside the repo          | ``https://github.com/owner/skills-collection.git`` + ``./searxng`` |
| Local directory         | An absolute or workspace-relative path               | ``/Users/me/my-drafts/cool-skill``                 |

We deliberately don't bundle a remote registry. Hosting Skills on
GitHub (or any HTTPS-accessible Git server) is enough.

## Workflow

### 1. Identify the workspace skills directory

The user's installable Skills live at ``{workspace}/skills/``. Use
``current_time`` or ``execute_shell_command pwd`` to get oriented if
the path is ambiguous, then:

```bash
SKILLS_DIR="<workspace>/skills"
mkdir -p "$SKILLS_DIR"
```

If the user hasn't run ``HarnessAgent.init()`` yet, suggest doing so
first — it creates ``{workspace}/skills/`` and seeds the built-in
Skills.

### 2. Install from a Git repo (single Skill at the root)

```bash
cd "$SKILLS_DIR"
git clone --depth 1 <repo-url> <skill-name>
```

Then verify the Skill is well-formed:

```bash
test -f "$SKILLS_DIR/<skill-name>/SKILL.md" || {
  echo "❌ no SKILL.md at the repo root — try installing a subdir instead"
  rm -rf "$SKILLS_DIR/<skill-name>"
  exit 1
}
```

Validate the frontmatter parses:

```bash
python3 - <<'PY'
import sys, re, pathlib
p = pathlib.Path("$SKILLS_DIR/<skill-name>/SKILL.md")
text = p.read_text(encoding="utf-8")
m = re.match(r"^---\n(.*?)\n---", text, re.DOTALL)
if not m:
    sys.exit("❌ SKILL.md is missing YAML frontmatter")
import yaml
fm = yaml.safe_load(m.group(1)) or {}
for k in ("name", "description"):
    if not fm.get(k):
        sys.exit(f"❌ frontmatter is missing required field: {k}")
print(f"✅ {fm['name']}: {fm['description'][:80]}…")
PY
```

(If ``yaml`` isn't installed, ``pip install pyyaml`` first — it's a
common dependency the user is likely to want anyway.)

### 3. Install from a subdirectory of a repo

When the upstream repo holds many Skills:

```bash
TMPDIR=$(mktemp -d)
git clone --depth 1 <repo-url> "$TMPDIR"
cp -r "$TMPDIR/<subpath>" "$SKILLS_DIR/<skill-name>"
rm -rf "$TMPDIR"
```

Run the same SKILL.md validation as in step 2.

### 4. Install from a local directory

For Skills the user is authoring locally:

```bash
cp -r "<source-dir>" "$SKILLS_DIR/<skill-name>"
```

Or, if they want a live link while iterating:

```bash
ln -s "<absolute-source-dir>" "$SKILLS_DIR/<skill-name>"
```

A symlink is the right call when the user is _writing_ the Skill and
wants edits to be picked up without reinstall.

### 5. List installed Skills

```bash
for d in "$SKILLS_DIR"/*/; do
  name=$(basename "$d")
  desc=$(awk '/^description:/{sub(/^description: */, ""); print; exit}' "$d/SKILL.md" 2>/dev/null)
  printf "  • %-30s %s\n" "$name" "$desc"
done
```

Show this output to the user verbatim — the per-Skill description is
exactly what they need to recognise what's installed.

### 6. Update a Skill

If the original was installed via ``git clone``:

```bash
cd "$SKILLS_DIR/<skill-name>" && git pull --ff-only
```

Otherwise re-install: remove the directory and run step 2/3/4 again.

### 7. Remove a Skill

Confirm with the user first (this deletes user-modified files too if
they edited the Skill in place):

```bash
rm -rf "$SKILLS_DIR/<skill-name>"
```

## Operating principles

- **Confirm before mutating.** Cloning into the workspace is fine to
  do without asking, but ``rm -rf`` and forced overwrites need
  explicit user confirmation.
- **Reject malformed Skills.** A Skill without valid frontmatter is
  worse than no Skill — it bloats the loader and confuses the model.
  Run the YAML check from step 2 every time.
- **Don't touch ``_builtin_skills/``.** That directory is owned by
  the package; edits will be lost on the next ``HarnessAgent.init()``.
  Built-in Skills can be _shadowed_ by installing a Skill of the same
  name into ``skills/`` — Harness Agent prefers user-installed Skills
  over built-ins.
- **Tell the user when to reload.** Newly installed Skills are picked
  up on the next agent session, not mid-conversation. Mention this so
  they don't expect immediate effect.

## Common questions

> "I want a Skill for X, can you find one?"

Search GitHub via the web fetcher or any other tool you have, propose
1–2 candidate repos, summarise their `SKILL.md` description, and let
the user pick before installing.

> "Where do Skills come from?"

Anywhere reachable by ``git clone`` — public GitHub, internal
GitLab/Gitea, ``file://``, etc. There's no central registry by
design.

> "Can I edit a built-in Skill?"

Don't edit the file in ``_builtin_skills/`` directly — it's
overwritten on init. Instead, copy it into ``skills/`` with the same
name; the user-installed copy shadows the built-in.
