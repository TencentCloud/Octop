<div align="center">
  <img src="assets/images/banner.jpeg" alt="Octop Harness" width="600" />
  <h1>Octop Harness</h1>
</div>

<p align="center">
  <strong>A production-grade agent runtime engineered from the Harness Engineering philosophy.</strong>
</p>

<p align="center">
  <a href="https://www.python.org/downloads/"><img alt="Python 3.12+" src="https://img.shields.io/badge/python-3.12%2B-blue?logo=python&logoColor=white" /></a>
  <a href="https://github.com/TencentCloud/octop-harness/blob/main/LICENSE"><img alt="License: MIT" src="https://img.shields.io/badge/license-MIT-green" /></a>
  <a href="https://pypi.org/project/octop-harness/"><img src="https://img.shields.io/pypi/v/octop-harness" alt="PyPI" /></a>
  <a href="https://github.com/astral-sh/ruff"><img alt="Code Style: Ruff" src="https://img.shields.io/badge/code%20style-ruff-000000?logo=ruff&logoColor=white" /></a>
  <a href="https://github.com/TencentCloud/octop-harness"><img alt="GitHub stars" src="https://img.shields.io/github/stars/TencentCloud/octop-harness?style=social" /></a>
</p>

<p align="center">
  <a href="#what-is-octop-harness">What is Octop Harness?</a> ·
  <a href="#why-octop-harness">Why Octop Harness?</a> ·
  <a href="#how-to-use">How to Use</a> ·
  <a href="#documentation">Documentation</a>
</p>

<p align="center">
  <b>English</b> · <a href="README_CN.md">中文</a>
</p>

---

**octop-harness** is a production-grade agent runtime built on the harness engineering theory. At its core it is a thin, battle-tested **encapsulation and engineering layer around [deepagents](https://github.com/langchain-ai/deepagents)** — we take the elegant `create_deep_agent` primitive from deepagents and package it with everything you need to run agents in production: multi-provider model routing, persistent memory, browser/search tools, a multi-agent registry, pluggable storage backends, and a terminal CLI.

> 💜 **A tribute to deepagents.** octop-harness stands on the shoulders of [deepagents](https://github.com/langchain-ai/deepagents) (by the LangChain team). Our `HarnessAgent` ultimately delegates to `deepagents.create_deep_agent`, and everything else — model routing, backends, tiered memory, the agent registry, CLI, and ACP — is the engineering we added on top. deepagents gives us the agentic foundation; Harness gives it a home for production.

## What is Octop Harness?

| | Feature | Description |
|---|---------|-------------|
| 🧩 | **Built on deepagents** | A faithful, production-focused facade over `deepagents.create_deep_agent` — kudos to the deepagents project |
| 🔀 | **Model routing** | `ChatModelFactory` with OpenAI, Anthropic, AWS Bedrock, and 17 editable provider presets |
| 🧠 | **Persistent memory** | [octop-memory](https://github.com/TencentCloud/octop-memory) middleware with tiered L0→L3 distillation |
| 🛠️ | **Rich toolset** | Browser automation, web search, file ops, sub-agents, and MCP tools out of the box |
| 🗂️ | **Multi-agent registry** | `AgentManager` runs many isolated agents in one process |
| 💾 | **Pluggable backends** | Local disk, S3, COS, or PostgreSQL as the agent workspace |
| 🔌 | **ACP integration** | A stdio ACP server so IDE / terminal AIs can drive your agent |
| 🔒 | **Safety built-in** | Tool guardrails, filesystem permissions, and PII redaction |
| 💬 | **Teams** | Peer inbox; `peer_invoke_mode` selects sync / async / both |
| ⌨️ | **Terminal CLI** | Interactive chat, provider/skill config, and agent management |

## Why Octop Harness?

octop-harness is a library (not an app) that turns deepagents into a deployable runtime. A single `HarnessAgentManager` owns a registry of agents; each agent wires together a model, a set of tools/skills, a memory backend, and a LangGraph checkpoint — all assembled through the `harness` layering discipline (L0 I/O helpers → L1 workspace facade → L2 business logic → L3 assembly).

> Harness Agent's design goal: let you build a production-grade agent from deepagents in a few lines of code, while keeping model choice, memory, storage, and safety swappable without rewriting your agent.

### Core Technology

| Layer | Technology |
|-------|-----------|
| **Language** | Python 3.12+ |
| **Agent core** | [deepagents](https://github.com/langchain-ai/deepagents) (`create_deep_agent`) |
| **Graph runtime** | LangGraph + SQLite checkpoint |
| **Model routing** | `ChatModelFactory` (OpenAI / Anthropic / Bedrock + 17 presets) |
| **Memory** | [octop-memory](https://github.com/TencentCloud/octop-memory) middleware |
| **Browser / search** | [octop-browser](https://github.com/TencentCloud/octop-browser) + web search |
| **Workspaces** | `BackendWorkspace`: local / S3 / COS / PostgreSQL |
| **ACP** | agent-client-protocol |
| **Build / quality** | hatchling · ruff · mypy · pytest |

### Features

#### Agent runtime
- `HarnessAgentManager` — a registry that creates, lists, and streams many agents in one process.
- `HarnessAgent` — exposes `call`, `stream`, `stream_events`, `aget_history`, `aappend_messages`, and `cancel`.
- Checkpointing via LangGraph `AsyncSqliteSaver` (or a octop-memory saver) for resumable chats.

#### Model routing & providers
- `ChatModelFactory` resolves a model name to the right client.
- First-class providers: **OpenAI** (incl. OpenAI-compatible via `base_url`), **Anthropic**, and **AWS Bedrock** (optional `[bedrock]` extra).
- 17 user-editable provider presets, including Hunyuan, Kimi, GLM, DeepSeek, MiniMax, and Moonshot.

#### Memory (tiered)
- `MEMORY.md` (strong memory) and `USER.md` (profile) are user-maintained, including
  onboarding. Their full contents are snapshotted
  once per session and reused from the checkpoint, even when structured memory
  is disabled. Manual edits apply to new sessions. Agent file
  tools cannot edit them. Hosts can expose manual editors.
- Workspace context loading, session snapshots, prompt formatting and cache
  breakpoints use deepagents' native `MemoryMiddleware`. Memory rules live in
  workspace `AGENTS.md`; the existing filesystem guard enforces both documents'
  file-tool write protection. Template updates do not overwrite existing user
  documents; update legacy auto-writing rules in `AGENTS.md` / `USER.md` when migrating.
- Ordinary saves and automatic promotions check current owner documents through
  `BackendWorkspace`, without refreshing the chat snapshot. Proven conflicts
  retire the old atom and create a replacement review candidate, retaining evidence.
  `memory_save` reports conflicts or incomplete checks. Duplicates remain stored
  and are suppressed against matching session context. Uncertain checks leave facts
  active. File-tool guards complement the host's shell/OS permissions.
- Remember requests use `memory_save(content, topic)` to persist directly through
  octop-memory; `memory_search` / `memory_get` retrieve additional history.
- Eligible conversation content is captured as **L0 raw events**, then distilled asynchronously into **L2 atoms** (`AtomCard`s) and **L3 entity pages**. Runtime failures are excluded; normal troubleshooting knowledge and explicit remember requests remain eligible.
- Model failures raise after retries; retry eligibility follows LangChain's defaults, with the existing retry budget and backoff settings. Callers must handle exceptions from `call()` / streaming. Checkpoints retain failed tasks without adding a synthetic assistant reply. Hosts display errors separately; automatic team failure notifications use `configurable.octop_memory_capture_exclude=true` to keep diagnostics out of memory.
- Powered by the octop-memory middleware; memory travels with the workspace.
- Recall is frozen once per user turn and appended to the model-facing user message,
  keeping the system prompt stable. Checkpoints preserve recall snapshots for exact
  replay while chat history and capture retain the original user text.

Memory extraction can be configured independently of main chat:
`memory_extract_max_tokens` sets the candidate/episode output budget (default
2048), while `memory_aux_light_timeout_s` / `memory_aux_heavy_timeout_s` set
per-request timeouts (30–3600 seconds). `memory_aux_max_retries` defaults to 2
extra attempts per model and accepts 0–10; `memory_aux_retry_backoff_s` defaults
to 1 second and doubles up to 60 seconds. Only transport/transient HTTP failures
are retried. SDK retries are disabled on separate cached model instances, so
main-chat retry settings are unaffected. `ChatModelFactory.get_chat_model(ref,
max_retries=0)` exposes that isolated construction path.

`memory_aux_thinking="auto"` or `"off"` disables thinking for known Qwen3/QwQ
chat-template models; unsupported models keep their defaults. `"on"` keeps the
model default. `memory_aux_extra_body` can supply vendor-specific settings such
as `reasoning_effort`; these apply only to the first selected OpenAI-compatible
model, never to fallback models. Fallback options are rebuilt for each target,
and output budgets respect the target model's configured output limit. Retries,
model fallback, and multiple extraction stages can extend total extraction time
beyond a single request timeout.

#### Host-owned memory restore

Hosts can use `MemoryMiddleware.pause_background(timeout=120)` as a context manager after pausing graph admission. It drains capture, extraction and maintenance workers for that middleware only, skips new background submissions while paused, and resumes admission on exit or timeout. Keep it held while closing and recreating the memory runtime; other experts remain independent.

#### Tools & skills
- Built-in tools: browser (octop-browser), web search, files, ``ask_user_question`` for
  respond-only human decisions, optional provider-neutral image/video generation, sub-agents,
  and MCP tools. Set ``ask_user_enabled=False`` for unattended agents.
- Skills come from the deepagents skills middleware; manage them per agent via the CLI.
- Optional ``system_files_path`` (e.g. ``.octop``) keeps skills, sessions, ``.env``,
  and sqlite under a workspace subdir while persona markdown stays at the root.

Enable provider-neutral `generate_image` and `generate_video` tools with Volcengine Ark:

```python
from octop_harness import HarnessAgentConfig, MediaGenerationConfig

config = HarnessAgentConfig(
    # ...providers/default_model...
    media_generation=MediaGenerationConfig(api_key_env="ARK_API_KEY"),
)
```

Generated files are stored under `generated/images/` and `generated/videos/` in the agent workspace. The tools
are deferred by default and become visible through the configured tool-search strategy only when needed.
Expected provider failures return a structured, model-visible error envelope with retry guidance instead of
terminating the agent stream.

For separate image and video routes, configure named providers. Built-in adapters cover Volcengine Ark
(Seedream/Seedance), Alibaba Cloud Model Studio (Wan), and MiniMax (image-01/H3):

```python
from octop_harness import HarnessAgentConfig, MediaGenerationConfig, MediaProviderConfig

config = HarnessAgentConfig(
    # ...providers/default_model...
    media_generation=MediaGenerationConfig(
        providers=[
            MediaProviderConfig(
                id="ark-images",
                provider="volcengine",
                api_key_env="ARK_API_KEY",
                video_enabled=False,
            ),
            MediaProviderConfig(
                id="minimax-videos",
                provider="minimax",
                api_key_env="MINIMAX_API_KEY",
                image_enabled=False,
            ),
        ],
        default_image_provider="ark-images",
        default_video_provider="minimax-videos",
    ),
)
```

Advanced hosts can inject a `MediaManager` into `build_media_generation_tools` and register a constrained
custom adapter without adding arbitrary protocol or authentication fields to declarative configuration.

#### Multi-agent & collaboration
- Multiple isolated agents per process via `AgentManager` + `registry`.
- **Teams** peer inbox for agent-to-agent messaging. ``peer_invoke_mode``
  selects the ``ask_agent`` surface (``sync`` / ``async`` / ``both``);
  request-scoped overrides may tighten it but cannot add background dispatch.
- **ACP** stdio server so external IDE / terminal AIs can invoke your agent.

#### Safety
- `SecurityPolicy` with tool guardrails, filesystem permissions (`FilesystemPermission`), and PII redaction middleware.
- PII detection covers provider API keys, mainland China mobile numbers (common 13-19 prefixes, optional `+86` / `0086`), and 18-character resident IDs with a known province code, 1900-2099 date, and checksum. Existing `pii_strategy` and `pii_surfaces` apply; legacy 15-digit IDs and other countries' numbers are out of scope.

#### CLI
`octop-harness` provides: `init`, `chat`, `agent`, `config` (e.g. `config provider add`), `skill`, and `update`.

## How to Use

### Prerequisites
- **Python 3.12+**
- A model provider API key (OpenAI / Anthropic / Bedrock / compatible)

### 1. Install

```bash
# Core SDK — agent runtime, model routing, tools, skills, backends
pip install octop-harness

# With the terminal CLI — interactive chat, config, skill management
pip install octop-harness[cli]

# Multiple extras — comma-separated inside one pair of brackets (quote for the shell):
pip install 'octop-harness[object-storage,desktop]'
pip install 'octop-harness[cli,all]'
```

Optional dependency extras (install only what you need; missing extras fail at use-time with an install hint):

| Extra | What it adds |
|-------|----------------|
| `cli` | Terminal CLI (`octop-harness`) |
| `bedrock` | AWS Bedrock provider |
| `object-storage` | Tencent COS + Alibaba OSS + Huawei OBS SDKs |
| `desktop` | Desktop screenshot / input (`mss`, `pynput`, `pillow`) |
| `web-search-all` | All web-search backends (Tavily / Brave / Google) |
| `remote-backends` | Postgres workspace backend (`psycopg`). S3 uses the bundled boto3 backend. |
| `observability` | Langfuse |
| `acp` | ACP agent runner |
| `all` | All library feature extras above (**excludes** `cli`; use `[cli,all]` for both) |

### 2. Initialize & configure

```bash
octop-harness init
octop-harness config provider add   # choose a provider and paste your key
```

### 3. Chat

```bash
octop-harness chat
```

### Programmatic use

```python
from octop_harness import HarnessAgentManager, HarnessAgentConfig, ProviderConfig, ChatRequest

manager = HarnessAgentManager()
agent: HarnessAgentConfig = manager.create_agent(
    name="assistant",
    provider=ProviderConfig(name="openai", api_key="sk-..."),
    model="gpt-4o",
)
request = ChatRequest(message="Summarize the Harness theory in one paragraph.")
async for chunk in agent.stream(request):
    print(chunk.delta, end="")
```

### Progressive tool loading

Large, low-frequency tool sets can be hidden until the model needs them. The
default `client` mode registers an ordinary `tool_search` function, so it works
with any Chat Completions-compatible model that supports function calling. A
deferred tool remains visible by its real name and short description, while its
parameter schema is replaced by a lightweight reference. A search result is
appended to the conversation, the matched full schemas replace their references
on the next model step, and the loaded set persists for the thread. The selected
tool is still called by its real name through the normal DeepAgents ToolNode,
security guard, and interrupt policy.

```python
from octop_harness import HarnessAgentConfig, ProviderConfig

provider = ProviderConfig(
    id="openai",
    base_url="https://openai-compatible.example/v1",
    api_key="sk-...",
    protocol="openai",
)

config = HarnessAgentConfig(
    providers=[provider],
    default_model="openai/your-function-calling-model",
    tools=[generate_image, generate_video, generate_3d_asset],
    deferred_tools=frozenset(
        {"generate_image", "generate_video", "generate_3d_asset"},
    ),
    defer_mcp_tools=True,
    tool_search_mode="client",  # default; no Responses API required
)
```

Set `tool_search_mode="native"` to use OpenAI Responses hosted `tool_search`
or Anthropic hosted `defer_loading` / `tool_reference`. Native mode additionally
requires `ModelConfig.native_tool_search=True`; unsupported routed models use
the configured `tool_search_fallback`. Set the mode to `eager` to disable
progressive loading.

For OpenAI-compatible providers, each model can set `api_mode` to
`"chat_completions"` (default) or `"responses"`. The choice is explicit for
official and compatible endpoints alike. Native OpenAI tool search requires
Responses. Models using Responses may also opt in to
`api_fallback="chat_completions"`. The fallback is disabled by default and is
used only for clear unsupported-endpoint/model errors, before any streamed
output. It does not apply to native tool search or other Responses-only request
features, and never masks authentication, rate-limit, timeout, or server errors.

## Documentation

- [What is Octop Harness?](#what-is-octop-harness)
- [Why Octop Harness?](#why-octop-harness)
- [How to Use](#how-to-use)
- **Reference**
  - [CLI reference](#cli-reference)
  - [Project layout](#project-layout)
  - [Development](#development)
- **Project Info**
  - [Contributing](#contributing)
  - [Related projects](#related-projects)
  - [License](#license)

### CLI reference

| Command | Description |
|---------|-------------|
| `octop-harness init` | Bootstrap a workspace and config |
| `octop-harness chat` | Interactive chat with an agent |
| `octop-harness agent` | Create, list, and manage agents |
| `octop-harness config` | Provider / model configuration (`config provider add`) |
| `octop-harness skill` | Enable / disable per-agent skills |
| `octop-harness update` | Check for and install updates |

### Project layout

```
src/octop_harness/
  agent.py          facade over deepagents.create_deep_agent
  manager.py        AgentManager — multi-agent registry
  config/           configs, provider & model presets
  llm/factory.py    ChatModelFactory — model routing
  backends/         BackendWorkspace — local / S3 / COS / Postgres
  builtin/          tools + skills + seed files
  middleware/       model_router, skill_filter, tool_guard, memory, pii, ...
  memory/           MemoryRuntime (octop-memory wrapper)
  protocols/        langgraph / openai / mcp streaming
  acp/             ACP stdio server
  teams/           peer inbox
  cli/             terminal CLI
```

### Development

**Prerequisites:** Python 3.12+, [uv](https://docs.astral.sh/uv/)

```bash
make install          # pip install -e ".[cli,dev]"
make all              # lint + typecheck + test
```

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Run `make all` before submitting
4. Open a Pull Request against `main`

Module boundaries and coding conventions: [AGENTS.md](AGENTS.md).

See [CONTRIBUTING.md](CONTRIBUTING.md) for branching, PR, and release details (`release/*` → `main` auto-publishes to PyPI).

## 🔗 Related projects

| Project | Description |
|---------|-------------|
| [deepagents](https://github.com/langchain-ai/deepagents) | The agentic foundation Harness Agent wraps — ❤️ tribute |
| [octop-memory](https://github.com/TencentCloud/octop-memory) | Memory system behind the tiered recall |
| [octop-browser](https://github.com/TencentCloud/octop-browser) | CDP browser automation used by the agent |
| [octop-gateway](https://github.com/TencentCloud/octop-gateway) | Multi-platform IM channel bridge |
| [Octop](https://github.com/TencentCloud/Octop) | The self-hosted assistant that composes the Harness stack |

## 📄 License

This project is licensed under the [MIT License](LICENSE).

## ✨ Contributors

Thanks to all contributors:

<a href="https://github.com/TencentCloud/octop-harness/graphs/contributors">
  <img src="https://contrib.rocks/image?repo=TencentCloud/octop-harness" />
</a>

### Channel plugins

A `kind: channel` manifest may register a channel class with
`ctx.channel("acme", AcmeChannel, label="Acme IM", fields=[...])`.
The class must inherit the hosts gateway `BaseChannel`; factories are not
accepted. Harness stores metadata without importing the gateway. The host
registers implementations before constructing persisted channels. Plugin IDs
own their kinds: updates replace the same plugin, and conflicting owners are
rejected. Hosts must stop affected live instances before replacing or removing
registrations. Installing this library alone does not add channels to a host
that has not implemented the bridge.
