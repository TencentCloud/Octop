# AGENTS.md

Working handbook for AI coding agents in the `octop-harness` repository.

> This file is **how to change this repo**. `src/octop_harness/builtin/md_files/AGENTS.md` (shipped in the library and copied into end-user workspaces) is **how to use the agent this library creates**. They are not the same document — do not mix them.

## 1. Collaboration principles

> Favor caution over speed; trivial tasks may relax these rules. These principles complement [§12 Change workflow](#12-change-workflow) and [§13 Communication](#13-communication).

### Think before writing

- Read first: the docstring of the file you will change, neighboring implementations, and related specs.
- State assumptions up front; ask when unsure — do not guess. When several interpretations exist, list them and let the user choose — do not pick one silently.
- Suggest simpler approaches when they exist; push back when appropriate.
- Stop when blocked; name exactly what is unclear.

### Simplicity first

- Write the minimum code that solves the problem; no unrequested features, abstractions, or config knobs.
- Do not add defensive error handling for scenarios that cannot realistically happen.
- Trim the diff when it grows unnecessarily large.

### Surgical edits

- Touch only lines directly related to the task; do not opportunistically "clean up" nearby code, comments, or formatting.
- Do not refactor working code or unify style just because it differs from yours.
- Unrelated dead code: mention it, do not delete it proactively.
- Remove orphan imports, variables, and functions **you** introduced.

### Verifiable outcomes

| Task | Plan | Verify |
|------|------|--------|
| Bug fix | Write a failing test that reproduces → fix → run the suite | New test fails before the fix; `make test` passes after |
| New public API | Export from `__all__` in `__init__.py` → implement + docstring + tests + mention in README | `make all` green |
| Behavior change | Add/change tests first → then change the implementation | Targeted `pytest`, then `make all` |
| Refactor | `make test` before → refactor → `make test` after | Zero behavior change unless requested |

**Ship bar: `make all` green** (format + lint + typecheck + test — exactly what the pre-commit hook runs). For multi-step work, sketch a short plan:

```
1. Read resolve_path in backends/workspace.py → verify: understand root_dir vs workspace_dir
2. Implement xxx → verify: pytest tests/test_backends_utils.py -k xxx
3. Run the full gate → verify: make all
```

## 2. What this is

`octop-harness` is a published Python library (`pip install octop-harness`). It is a moderate wrapper around [LangChain Deep Agents](https://docs.langchain.com/oss/python/deepagents/) so users can create production-grade agents with very little code.

**It is a library, not an application.** Anything that looks like application-layer functionality (cron, MBTI onboarding, vector-memory persistence, HTTP server, user login, UI) does not belong here — those belong in hosts such as `Octop`. `octop-harness` provides the agent runtime; `octop-gateway` (the IM bridge) and Octop (the self-hosted platform) assemble applications on top of it.

## 3. Tech stack

| Layer | Technology |
|-------|------------|
| Language | Python 3.12+; every source file has `from __future__ import annotations` |
| Agent runtime | `deepagents>=0.7.16,<0.8` + `langchain` / `langchain-core` / `langgraph` |
| Config objects | `dataclasses` (`HarnessAgentConfig` / `ProviderConfig` / `ModelConfig`) with `to_dict` / `from_dict` |
| Optional extras | `cli` (click + rich + prompt-toolkit), `bedrock`, `remote-backends`, `docker`, `opensandbox`, `observability` (langfuse), `acp`, `desktop` (mss + pynput + pillow), `web-search-all`, `object-storage`, `all` |
| Ecosystem | `octop-memory`, `octop-browser`, `langchain-mcp-adapters` + `mcp` |
| Packaging | hatchling; local development with `uv` (`uv sync --group dev`) |
| Quality gates | ruff (lint + format, line length 120), `mypy --strict`, pytest + pytest-asyncio |

## 4. Package layout

```
src/octop_harness/
├── __init__.py             # Public exports + type stubs + lazy load of HarnessAgent / Workspace
├── _version.py             # Resolve [project].version from pyproject.toml via importlib.metadata
├── agent.py                # HarnessAgent (construct + invoke/stream + init())
├── manager.py              # HarnessAgentManager + multi-agent orchestration + team subsystem
├── registry.py             # In-memory agent registry (AgentEntry + storage CRUD)
├── request.py              # ChatRequest (messages/thread_id/user/source/...)
├── config/                 # HarnessAgentConfig + ProviderConfig + ModelConfig + env parsing
├── init.py                 # init_workspace + InitResult (workspace seeding)
├── backends/               # Backend string / dict → BackendProtocol instance
│   ├── workspace.py        # BackendWorkspace: L1 agent-storage facade
│   └── utils.py            # Path rules + backend I/O helpers + materialize_storage_path
├── llm/                    # ChatModelFactory (ProviderConfig → BaseChatModel) + model routing
├── middleware/             # SessionLogger / PII / memory / media offload, etc.
├── memory/                 # MemoryRuntime (octop-memory adapter)
├── media/                  # Vendor-agnostic media generation (BaseMediaProvider + builtins)
├── plugins/                # Plugin system (manifest / loader / registry / tools / context)
├── providers/              # provider_template.json (presets) + load_provider_templates()
├── protocols/              # Chat protocol registry (discover / resolve implementations)
├── security/               # Policy models (FilesystemPolicy / HitlPolicy / SSRF) + tool_guard
├── skills/                 # Skill catalog and metadata helpers
├── slash/                  # Runtime slash commands (stop / skills / model)
├── subagents/              # Workspace subagent loading and catalog
├── teams/                  # Optional inbox-driven agent-to-agent collaboration
├── acp/                    # ACP (Agent Client Protocol) external-agent integration
├── observability/          # Optional observability (langfuse) + runtime logging
├── context_usage.py        # Context-window usage estimate / persistence
├── compaction.py           # Forced session compaction (SummarizationMiddleware offload + summary)
├── messages.py / usage.py  # Message parsing / token-usage normalization
├── runtime_env.py          # Process env + global keys + workspace .env merge
├── mcp.py                  # MCP server config merge + tool loading
├── cli/                    # Optional CLI (main / commands / agents / config / providers / repl / ui)
└── builtin/
    ├── _sync.py            # Sync builtin/skills/* into workspace/_builtin_skills/
    ├── templates.py        # Pure read layer for packaged builtin/ resources
    ├── md_files/           # User workspace templates (en/ zh/)
    ├── agents/             # Built-in workspace subagent defs (en/ zh/, YAML frontmatter + system_prompt)
    ├── skills/             # Built-in skills (en/ zh/, synced at startup)
    └── tools/              # Built-in tools (current_time / web_fetch / send_file / screenshot / web_search/*)

tests/                      # pytest, one-to-one with src modules
examples/                   # End-to-end runnable demos (numbered)
multi_agent_demo/           # Multi-agent example configs
```

**Change-mapping cheat sheet:**

| To change… | Look at… |
|------------|----------|
| Public API (constructor / fields) | `agent.py` / `config/` / `request.py` |
| Multi-agent register / route / cancel | `manager.py` / `registry.py` |
| New built-in tool | `builtin/tools/*.py` + `builtin/tools/__init__.py` |
| New built-in skill | `builtin/skills/{en,zh}/<name>/SKILL.md` |
| New backend | `backends/__init__.py` (register) + `backends/<name>.py` (implement) |
| Paths / backend storage | `backends/utils.py` / `backends/workspace.py` |
| Config serialization | `config/` |
| Startup behavior | `HarnessAgent.__init__` assembly in `agent.py` |
| Provider preset list | `providers/provider_template.json` |
| CLI subcommands | `cli/commands/*_cmd.py` + `cli/main.py` |

## 5. Module boundaries

### Layers (bottom-up; reverse imports are forbidden)

| Layer | Module | Owns |
|-------|--------|------|
| L0 | `backends/utils.py` | Low-level I/O helpers (`backend_write_force`, etc.); `materialize_storage_path` escape hatch |
| L1 | `backends/workspace.py` (`BackendWorkspace`) | The **only** I/O facade for **agent-visible / agent-used workspace content** inside harness |
| L2 | `middleware/*`, `builtin/tools/*`, `init.py`, `builtin/_sync.py` | Business / seed logic; L1 content goes only through `BackendWorkspace`; runtime persistence may hit local FS / DB as an explicit exception |
| L3 | `agent.py` | Assembly; `config` parses path fragments and does not do I/O itself |

### Which path to use

| Caller | Entry | Notes |
|--------|-------|-------|
| Internal L1 content (init, bootstrap, skills, media, bound send_file, catalogs, …) | `agent.workspace` / `BackendWorkspace` | **Required** |
| LLM tools (`read_file` / `write_file`) | `agent.backend` | deepagents protocol; interpreted by the backend's `virtual_mode` / `root_dir` |
| Local runtime persistence (memory DB, `sessions/` JSONL, `checkpoints.sqlite`) | `Path` / `open()` / DB drivers, default under `workspace_dir` | Explicit exception: real OS fds, locks, append, or rotation — not via `BackendWorkspace` |
| Runtime diagnostic logs (`octop_harness.*`) | `Path` / logging handlers, default `~/.octop-harness/logs` | App-level `HarnessAgentManager(log_dir=…)` / `setup_logging`; shared across agents with `[agent=…]` |
| CLI global config (`~/.octop-harness/`) | Local FS | Not part of the agent workspace |

"Agent content" here means templates, bootstrap, skills, media, send-file materialize targets, and other workspace content used by the agent / LLM. Those reads and writes go through `BackendWorkspace` only — never direct `Path` / `open()`. Do not bypass `BackendWorkspace` for L1 content with `Path(workspace_dir).read_text()` / `open()`. This ban does **not** extend to the local runtime-persistence rows in the table above.

## 6. Run commands

```bash
# Full gate (required before commit; also what the pre-commit hook runs)
make all                    # = format + lint + typecheck + test

# Individual targets
make format                 # ruff check --fix + ruff format (rewrites files)
make lint                   # ruff check + ruff format --check
make typecheck              # mypy --strict
make test                   # pytest (with coverage)

# Direct venv (when make is inconvenient)
.venv/bin/python -m ruff check . && .venv/bin/python -m ruff format --check .
.venv/bin/python -m mypy --strict src
.venv/bin/python -m pytest -q

# Environment
make install-hooks          # once per clone: enable .githooks pre-commit
make install                # uv sync --group dev (alias: make install-dev)
uv sync --all-extras        # all optional extras (same as pip install 'octop-harness[cli,all]')

# Packaging
make build                  # wheel + sdist into dist/
make version                # print current version

# Run an example
.venv/bin/python examples/06_init_and_md_files.py
```

**Single-test debug:** `pytest tests/test_init.py::TestInitWorkspace::test_idempotent_second_call_skips -xvs`

**Git hooks (required for local commits):** after cloning, run **`make install-hooks`** once. That sets `core.hooksPath=.githooks`, so every `git commit` first runs **`make all`** (`format` rewrites files, then lint / typecheck / test). Staged files rewritten by format are re-added automatically, so the commit contains the formatted content. Bypass only in emergencies: `SKIP_PRECOMMIT=1 git commit …` or `git commit --no-verify` — **do not** skip the hook to land a red suite.

## 7. Key conventions

### Library vs application

- **May add:** thin wrappers on deepagents, public APIs, optional backends / tools / skills, serialization.
- **Must not add:** HTTP server, local database, cron daemon, vector-memory persistence, UI, login / user management. Those are application concerns.

### Default-value philosophy

- **Zero-deps first:** core `pip install octop-harness` ships no optional packages; heavy deps (`mss`, `langchain-tavily`, …) go through `[extras]`.
- **Fail-soft for UX, not for checks:** fail-soft applies to startup / call-time user experience, not mypy / lint. Missing backend extras should error clearly and tell the user what to install; tests and type checks stay strict.
- **User edits are sacred:** `init()` does not overwrite existing files by default; `overwrite=True` force-refreshes. Wipe-and-replace of `builtin/skills` runs only when the version stamp differs.

### Naming

- Tool functions / modules / files / packages: `snake_case`; no hyphens.
- Skill directories: `kebab-case` (`skill-creator/`, `web-search/`) — de facto Anthropic-ecosystem standard; enumerate with `importlib.resources.files(...).iterdir()` (`Traversable` does not require a valid Python package name).
- Classes: `PascalCase` (`HarnessAgent`, `InitResult`).

### Agent workspace and `BackendWorkspace`

#### `root_dir` vs `workspace_dir` (different axes; do not conflate)

| | `root_dir` | `workspace_dir` |
|---|---|---|
| **What it is** | Mount argument when building a local backend (`filesystem` / `local_shell`) | The agent's **recommended working directory** (host absolute path, or an agent-facing rootfs path) |
| **Who uses it** | Only `resolve_backend` / deepagents backend construction | `HarnessAgentConfig`, harness assembly, `BackendWorkspace` |
| **Visible to agent / LLM?** | **No** — not a tool-API concept | Workspace semantics; relative paths are relative to it |
| **Typical role** | Where virtual `/` maps on disk | Default base for SOUL/skills/seed files and some runtime persistence |

**Do not** treat them as "two peer trees" or as "the agent choosing between root and workspace". The agent only sees path conventions; `root_dir` is a backend-assembly detail.

Factory behavior, briefly:

- If the spec does **not** pin `root_dir`, fill it from `workspace_dir` → virtual `/` aligns with the workspace (common, recommended).
- The default spec pins `root_dir="/"` + `virtual_mode=True` → the backend sees the whole machine; `workspace_dir` remains the recommended workspace (and at host-root the factory wraps a composite so deepagents offload lands in the workspace).
- `workspace_dir` may be a host absolute path or an agent-facing rootfs path (e.g. `/.octop/workspaces/<id>`). The latter is mapped by harness onto `{root_dir}/…` before local persistence, and is valid on Windows too (no drive letter). With aligned config, workspace content corresponds to virtual-FS paths from `/` (e.g. `/SOUL.md` → `{workspace_dir}/SOUL.md`).

#### `virtual_mode=True` (default) and `root_dir` is not host `/`

deepagents filesystem tools then map `/foo` to `{root_dir}/foo` (implementation detail; the agent entry is still a rootfs path, and harness does **not** concatenate `root_dir` at the tool entry).

**`BubbledLocalShellBackend` (Linux + bwrap + non-host `root_dir` + `virtual_mode` only)**

- The factory picks this only when those conditions hold; otherwise `HarnessLocalShellBackend` (dotenv refresh, conservative trusted-virtual-path mapping).
- Directory jail applies only to `execute`: bind `root_dir` to `/` inside the jail.
- In-workspace path limits are owned by deepagents / the jail; command strings stay agent-facing and are not rewritten.
- Jail cwd aligns to the virtual `workspace_dir` (falls back to `/` if the workspace is not under `root_dir`).

**No jail (macOS / no bwrap / host root)**

- `execute` runs with the host workspace as cwd.
- When not host-root and `virtual_mode=True`, trusted virtual absolute paths in command tokens and env map to `{root_dir}/…`: existing host paths win; otherwise only workspace-internal paths or paths with an existing virtual-tree ancestor. URLs, real `/usr` / `/tmp`, and host absolute paths stay unchanged.
- `root_dir` prefixes in execute output are restored to agent-facing `/…`.
- Reading artifacts uses **multi-layer failback** on the `BackendWorkspace` read side:
  - **Absolute paths:** try the `{root_dir}` mapping (`backend._resolve_path`) first; if missing, the original host path.
  - **Relative paths:** try `{root_dir}/{rel}`, then `{workspace_dir}/{rel}`.
- Bound `materialize_local` / `exists` / `aexists` / `read_text` / `aread_text` / `download_bytes` / `send_file` all use this failback.

```text
model: write_file("/gen/run.py") + execute("python /gen/run.py")
        │                              │
        ▼                              ▼
  deepagents → {root}/gen/run.py    bwrap: /gen/... inside the jail
                                    no jail: trusted virtual paths map to {root}/gen/...
model/harness then read artifacts:
  BackendWorkspace.materialize_local("/gen/out.pptx")
    → {root}/gen/out.pptx first, then original /gen/out.pptx
      (and relative paths: root → workspace)
```

#### `BackendWorkspace.resolve_path` cheat sheet

| Input | Result |
|-------|--------|
| Does not start with `/` | `{workspace_dir}/{fragment}` |
| Starts with `/` | Under `virtual_mode`, mapped via `backend._resolve_path` onto `root_dir`; otherwise left as-is |
| `~/…` | Host path after `expanduser()` |

Relative paths that escape `workspace_dir` (e.g. `../x`) → `PermissionError`.
`skill_paths()` / `memory_paths()` go through `_backend_storage_key` (agent-facing virtual key under `virtual_mode`, **not** concatenated with `root_dir`) for deepagents Skills/Memory middleware `backend.ls` and system-prompt injection; host I/O / materialize still uses `resolve_path`.

```python
ws = agent.workspace
ws.write_text("AGENTS.md", text, force=True)
agent.init_workspace()
```

### Strict lazy imports

- Optional SDKs (`mss`, `langchain_tavily`, `qcloud_cos`, …) are imported **only at call time**, never at module top level.
- Exempt `PLC0415` with ruff per-file-ignore; do not use inline `# noqa` (it conflicts with per-file-ignore and triggers `RUF100`).
- Follow the existing comment pattern in `[tool.ruff.lint.per-file-ignores]` in `pyproject.toml`.

## 8. Common pitfalls

- **`HarnessAgentConfig` is a frozen dataclass:** adding a field means updating `to_dict` / `from_dict` as well (including `_unserializable_fields` and `_xxx_to_jsonable` helpers). `providers` is now `list[ProviderConfig]`, serialized as a JSON array not an object; `ProviderConfig` has an `id` field that must be passed at construction.
- **`ProviderConfig` requires `id`:** `id` is the first positional argument (required, no default). Hand-written `ProviderConfig(base_url=..., api_key=...)` must add `id=`; JSON deserialization goes through `from_dict` (old dict format is backward-compatible).
- **mypy strict does not allow implicit `Any` returns:** third-party SDK calls that return `Any` need an explicit `cast` or `assert isinstance(...)`, or you get `no-any-return`.
- **mypy for optional packages such as `mss`:** add `ignore_missing_imports = true` under `[[tool.mypy.overrides]]`. Do **not** use `# type: ignore[import-not-found]` (it becomes `unused-ignore` once the extra is installed).
- **deepagents skills / memory paths:** `skill_paths()` / `memory_paths()` go to deepagents via `_backend_storage_key` (`virtual_mode` → virtual `/…` key; do not concatenate host `root_dir`). `resolve_path` is only for host I/O / materialize (see [§7](#agent-workspace-and-backendworkspace)).
- **L1 agent storage:** agent-visible / agent-used workspace content goes through `agent.workspace` (`BackendWorkspace`); memory DB, logs, JSONL transcripts, and checkpoint SQLite are local runtime persistence and use local FS / DB drivers directly. Do not treat `root_dir` as a second workspace.
- **shell / virtual_mode:** non-host-root + `virtual_mode` + Linux + bwrap → factory picks `BubbledLocalShellBackend` to jail `execute`; otherwise `HarnessLocalShellBackend` conservatively maps trusted virtual command/env paths and uses the workspace as cwd. Reads still have `BackendWorkspace` root→original / root→workspace failback (see [§7](#agent-workspace-and-backendworkspace)).
- **Do not import `mss` at module top level:** import inside the function, or `import octop_harness.builtin.tools` breaks for `pip install octop-harness` without `[desktop]`.
- **`init.py` must not `from octop_harness import __version__`:** that causes a circular import. Use `from octop_harness._version import __version__` (the single source of the version is `[project].version` in `pyproject.toml`).
- **`HarnessAgentManager` is the recommended entry:** `manager.create_agent(config)` eagerly builds and caches `HarnessAgent`; `manager.stream(agent_id, request)` reuses the cached instance. Direct `HarnessAgent(config)` is still supported for backend-only work (`agent.backend`, `agent.init_workspace()`), but **all LLM chat goes through the manager**.
- **`HarnessAgentManager` is a single-process in-memory registry:** do not share one instance across processes; cross-process coordination is left to the MQ extension point (the interface is already reserved).
- **CLI uses `CliAgentManager`, not the library `HarnessAgentManager` directly:** `cli/agents/manager.py` `CliAgentManager` owns file persistence and reaches the underlying manager via `.runtime`.
- **Provider presets live in JSON, not Python:** `providers/provider_template.json` is the single source of truth; `cli/providers/registry.py` `_build_registry()` reads that JSON. Do not hard-code new providers in Python.

## 9. Test conventions

- **Test files mirror `src/` modules:** `src/octop_harness/init.py` ↔ `tests/test_init.py`; subpackages have matching directories (`tests/cli/`, `tests/config/`, `tests/protocols/`, `tests/slash/`, `tests/observability/`).
- **Mock third-party SDKs; no network:** all web-search / S3 / COS tests use mock clients; only `examples/` may use a real network.
- **Assert behavior, not implementation:** `test_idempotent_second_call_skips` checks the `templates_skipped` list, not internal branches in `_sync.py`.
- **Regex matches use raw strings:** `pytest.raises(RuntimeError, match=r"env var.*missing")`, otherwise `RUF043`.
- **Cross-platform:** CI runs on Linux, but code must land on Windows / macOS. Guard POSIX-only behavior (bwrap, `chmod`, `/proc`) with `pytest.mark.skipif`; prefer `tmp_path` / `pathlib.Path` equality over hardcoded `/`-prefix strings. See `tests/test_bwrap_shell*.py` and `tests/test_docker_sandbox.py`.
- **Before a PR:** full suite green, mypy 0 issues, ruff clean — CI runs the same.

## 10. Do not

Boundary rules are in [§5](#5-module-boundaries). Additionally:

- Do not bypass `BackendWorkspace` with `Path` / `open()` for L1 agent content (local runtime-persistence exceptions: [§5 Which path to use](#which-path-to-use)).
- Do not import optional SDKs at module top level; do not use inline `# noqa: PLC0415`.
- Do not add application-layer features: HTTP server, cron daemon, UI, login / user management, vector-memory persistence.
- Do not commit real credentials: `.env` / `.gitignore` already cover this; `pyproject.toml` must not contain API keys either.
- Do not hard-code real credentials in README / docstrings / tests: use `"sk-xxx"` placeholders. If a user pastes a secret, do not echo the full string into a commit message / log, and tell them to revoke it.
- Do not disable PII Middleware for a demo unless the demo's point is turning PII off.
- Do not duplicate manager / config domain logic in `cli/*_cmd.py`.
- Do not `git commit` / `git push` unless the user explicitly asks.

## 11. Where to look

| Question | Location |
|----------|----------|
| How do I construct / call an agent? | `agent.py`, `manager.py`, `tests/test_agent.py` |
| Multi-agent register and routing | `manager.py`, `registry.py` |
| Workspace init (seed files / skills) | `init.py`, `builtin/templates.py`, `builtin/_sync.py` |
| Backend resolution and path rules | `backends/__init__.py`, `backends/utils.py`, `backends/workspace.py` |
| Shell / sandbox behavior | local shell backend implementations, `tests/test_bwrap_shell*.py`, `tests/test_docker_sandbox.py` |
| Provider presets / model factory | `providers/provider_template.json`, `llm/` |
| Middleware (PII / memory / media offload) | `middleware/` |
| Built-in tools | `builtin/tools/` |
| Plugin system | `plugins/` |
| teams / subagents / ACP | `teams/`, `subagents/`, `acp/` |
| Config fields and env parsing | `config/` |
| CLI behavior | `cli/main.py`, `cli/commands/*_cmd.py` |
| Release flow and hooks | [§12](#12-change-workflow); `CONTRIBUTING.md` |

External references:

- [LangChain Deep Agents docs](https://docs.langchain.com/oss/python/deepagents/)
- [LangGraph middleware guide](https://docs.langchain.com/oss/python/langchain/middleware)

## 12. Change workflow

1. **Read first:** docstring of the file you will change, neighboring implementations, related specs.
2. **Hooks:** if this clone has not run `make install-hooks` yet, do it first (see [§6](#6-run-commands)). The hook must stay green before commits.
3. **Small steps:** split into multiple commits when you can; one commit, one motive.
4. **Keep docstring and tests in sync:** if a signature / behavior changes, update docstring + tests together.
5. **New public APIs must:** be in `__all__` of `__init__.py`, have a docstring, be covered by tests, and be mentioned at least once in the README.
6. **Quality gate:** `make all` must be green — that is also what pre-commit runs; do not commit if the hook fails. If a rule truly needs an exemption, add a per-file-ignore and comment **why**.
7. **CHANGELOG:** user-visible public behavior gets a line under `## [Unreleased]` in `CHANGELOG.md`.
8. **Wrap up:** remove orphan symbols this change introduced; do not commit or push unless asked.

### Branching & release

```
feature/* ──PR──► develop ──► release/x.y.z ──PR──► main ──tag v*──► publish
hotfix/* ──PR──► main (+ tag) and ──PR──► develop
```

| Branch | Role |
|--------|------|
| `main` | Production source of truth; **default branch**; only release / hotfix merges; **only `v*` tags on `main` are production** |
| `develop` | Daily integration; **base for feature PRs** |
| `release/x.y.z` | Temporary freeze (version bump / CHANGELOG / README sync); **delete after ship** |
| `hotfix/*` | Emergency fix from `main`; merge to `main` and back to `develop` |

**Rules**

- Never push `develop` directly onto `main` — ship via `release/*` → `main` (or hotfix → `main`) only. Do **not** bulk-merge `develop` → `main`; it forks history and breaks post-release sync.
- Never push directly to `main` or `develop` — always open a PR (GitHub branch protection).
- Merge `release/*` → `main` with a **merge commit** (not squash) so `main` stays reconcilable with `develop`.
- Release sequence: cut `release/*` from latest `develop` → PR into `main` → **tag `v*` on main tip only after merge** → delete `release/*` → Actions syncs `main` → `develop` (`sync-main-to-develop.yml`; opens `chore/sync-develop-after-*` on conflict / branch protection).
- Keep **`main` an ancestor of `develop`** after every release. Do not use legacy `head=main` → `develop` sync PRs.
- Do **not** push a production tag from a release/feature branch before it is on `main`.
- Hotfix: branch from `main`, PR to `main` (and tag if shipping), then PR into `develop`.
- Day-to-day feature work: branch from `develop`, open PR **into `develop`** (not `main`).
- Human detail: `CONTRIBUTING.md`. Agent publish flow: `.cursor/skills/publish` / `.codebuddy/skills/publish`.


## 13. Communication

- Default to **Chinese** when talking to the user; cite code as `` `path:line` ``.
- Lead with the conclusion, then the detail; write complete sentences, not telegraphic fragments.
- Before saying "done", include the verification command and its result (or say why it was not run).
- Mention out-of-scope issues briefly; do not expand scope unilaterally.
- **Do not say "done" until the quality gate is green:** if `make all` is not fully green, do not call the work finished.

---

_This file is a living document — keep it in sync when structure, conventions, or workflow change._
