<p align="center">
  <img src="assets/images/banner.jpeg" alt="Octop Memory — a little octopus keeping memories safe" width="880" />
</p>

<p align="center">
  <strong>Help your agent remember what matters.</strong><br />
  Keep preferences, carry context across sessions, and bring your memory to the next agent.
</p>

<p align="center">
  <a href="pyproject.toml"><img alt="Python 3.12+" src="https://img.shields.io/badge/Python-3.12%2B-3776AB?logo=python&amp;logoColor=white" /></a>
  <a href="LICENSE"><img alt="License: MIT" src="https://img.shields.io/badge/License-MIT-E85D75" /></a>
  <a href="pyproject.toml"><img alt="Core dependencies: 0" src="https://img.shields.io/badge/Core_dependencies-0-E85D75" /></a>
  <a href="#optional-dependencies"><img alt="Storage: SQLite and PostgreSQL" src="https://img.shields.io/badge/Storage-SQLite_%7C_PostgreSQL-4169E1" /></a>
  <a href="CONTRIBUTING.md"><img alt="Code style: Ruff" src="https://img.shields.io/badge/Code_style-Ruff-261230?logo=ruff&amp;logoColor=white" /></a>
</p>

<p align="center">
  <a href="#highlights">Highlights</a> ·
  <a href="#quick-start">Quick start</a> ·
  <a href="#external-agent-adapters">Integrations</a> ·
  <a href="#cli">CLI</a> ·
  <a href="#code-architecture">Architecture</a> ·
  <a href="CONTRIBUTING.md">Contributing</a>
</p>

<p align="center">
  <b>English</b> · <a href="README_CN.md">中文</a>
</p>

---

**Octop Memory** is a persistent, portable memory system for LLM agents. Give a personal assistant lasting preferences,
keep decisions and project context available across conversations, or move accumulated memory between supported hosts.
Start locally with SQLite, then add PostgreSQL or model-assisted extraction as needed.

It powers memory in the **Octop ecosystem** and also works independently as a Python library, CLI, or JSON-RPC bridge.
**OpenClaw** and **Hermes** adapters connect their host hooks and tools to the same memory runtime.
Your host manages agent execution and model scheduling; Octop Memory handles capture, extraction, recall, storage, and migration.

> **Memory worth keeping. Context worth bringing along.** Save it, recall it, and carry it between supported agents.

<a id="highlights"></a>

## ✨ Highlights

| | What stands out | What you get |
|---|---|---|
| 🪶 | **Start small, add what you need** | Zero core dependencies: Python's standard library + SQLite/FTS5. Manual storage and lexical recall work without a model. |
| 🧠 | **Turn conversations into lasting memory** | Model-assisted extraction and promotion turn raw events into facts with evidence references; entity pages and episodes organize the context. |
| 🔍 | **Recall that fits the prompt** | Full-text search, ranking, deduplication, and token budgets select context for the current query. |
| 🧳 | **Bring your memory along** | Export/import and portable `.hmpkg` packages move memory between supported hosts, including OpenClaw and Hermes. |
| 🔌 | **Connect to your agent** | Python `MemoryService`, a JSON-RPC bridge, and dedicated host plugins share the same runtime. |
| 💾 | **Choose your storage** | SQLite for a local start; PostgreSQL for server deployments. |
| 🌳 | **Keep facts organized** | Canonical `AtomCard` facts, entity pages, and a `root → branch → leaf` tree make memory easier to navigate; namespaces separate stores within a backend. |
| 🔖 | **Resume conversations** | Optional LangGraph checkpoints preserve execution state alongside long-term memory, with SQLite and PostgreSQL support. |

**Python 3.12+** is required. Automated extraction, promotion checks, and page regeneration use an injected `LLMClient`;
installing the package alone does not configure a model. See the [integration guide](docs/integrations.md) for host setup.
Existing installations should read the [rename migration guide](docs/integrations.md#更名与已有安装迁移) before upgrading.

## Quick start

```bash
pip install octop-memory
```

```python
from octop_memory import Memory, MemoryService

memory = Memory(
    namespace="demo",
    backend_config={"db_path": "./demo.sqlite"},
)
memory.store("User prefers Python for backend services", topic="preferences")

# Basic fact search returns MemoryNode leaf projections.
for node in memory.recall("Python"):
    print(node.content)

# Prompt recall adds source selection, ranking, deduplication, and budgeting.
result = MemoryService(memory).recall("Python")
print(result.rendered)
```

This creates a local database. Use terms present in the stored text for a minimal FTS example. `Memory.search()` searches archived conversation messages; it is a separate API from fact recall.

### Optional dependencies

| Install | Purpose |
|---|---|
| `pip install "octop-memory[cli]"` | CLI and OpenClaw setup commands |
| `pip install "octop-memory[postgres]"` | PostgreSQL memory backend |
| `pip install "octop-memory[langgraph]"` | SQLite LangGraph checkpointer |
| `pip install "octop-memory[langgraph-postgres]"` | PostgreSQL LangGraph checkpointer |

Vector search interfaces and Chroma/Qdrant adapters exist in the code, but current tests use fake/mock implementations; real Chroma/Qdrant integration remains unverified. Vector search is not enabled by default and is not yet presented as a fully supported installation option. Using it requires initializing an index and injecting `vector_index` and `embedding_provider` into `Memory`; installing dependencies alone does not enable it. The database backend remains `sqlite` or `postgres`.

```python
memory = Memory(
    namespace="demo",
    backend="postgres",
    backend_config={"dsn": "postgresql://user:pass@localhost/octop_memory"},
)
```

Use deployment configuration for real credentials. SQLite isolates memory with table prefixes; PostgreSQL uses namespace-first keys in the shared `octop_memory` schema.

Within one process, PostgreSQL instances with the same connection settings share a business pool (up to 8 connections) and a checkpoint/maintenance pool (up to 4), independent of agent count. Each pool allows at most 64 queued requests with a 30-second checkout timeout; saturation raises an explicit error. Idle pools can shrink to zero, and closing one instance leaves other instances usable. Budget separately for multiple processes, different connection settings, and the host's own database connections.

## CLI

Install `[cli]`. Global options precede subcommands; use an explicit database and namespace when following examples.

```bash
octop-memory --db ./demo.sqlite --namespace demo memory store --content "User prefers Python"
octop-memory --db ./demo.sqlite --namespace demo recall "Python"
octop-memory --db ./demo.sqlite --namespace demo memory tree
octop-memory --help
```

| Commands | Purpose |
|---|---|
| `raw`, `candidate`, `atom`, `entity`, `page` | Inspect and manage memory layers |
| `episode`, `digest`, `journal` | Event summaries and decision records |
| `memory`, `recall`, `thread` | Tree operations, prompt recall, thread state |
| `export`, `import`, `migrate`, `portable` | Backup and migration |
| `db`, `gc`, `consolidate` | Storage maintenance and lifecycle operations |
| `config`, `openclaw`, `backfill` | Configuration, integration, historical extraction |

Run `<command> --help` for arguments. `db slim FILE` previews SQLite checkpoint deduplication; `--apply --offline` creates a backup and performs it without deleting history. Read [checkpoint compatibility and maintenance](CONTRIBUTING.md#checkpoint-维护) before migration or reader downgrade.

The dashboard is available from a source checkout with `[dashboard]` dependencies; its modules are currently excluded from the wheel. Installing `octop-memory[dashboard]` from PyPI alone does not provide the dashboard command.

## External agent adapters

`plugins/<host>/` maps external agent hooks, tools, and configuration to the shared Python runtime.
OpenClaw and Hermes adapters are available today. Other agents can integrate through the Python API or JSON-RPC,
with an adapter implementing their host contract.

| Integration | Use case | Entry point |
|---|---|---|
| In-process Python | Custom agents / Python applications | `MemoryService.capture_turn()` / `recall()` / `search()` / `get()` / `extract()` |
| JSON-RPC bridge | Cross-language or separate processes | stdio `octopmemory-bridge` |
| Host plugin | Agent-specific lifecycle and tool interfaces | `plugins/<host>/`; OpenClaw and Hermes currently implemented |

See the [integration guide](docs/integrations.md) for installation, configuration, profiles, troubleshooting, and adapter boundaries.

Move memory with `octop-memory portable list-sources / pack / adopt / doctor`. Exported `.hmpkg` files contain memory data; keep them out of source control.

## Code architecture

```text
src/octop_memory/
├── core.py / types.py     # Public Memory API and data structures
├── service.py            # MemoryService: Python host entry point
├── application/          # MemoryRuntime, config, host files, path projection
├── pipeline/             # Extraction, promotion, recall, pages, episodes, lifecycle
├── storage/              # SQLite / PostgreSQL, checkpoints, vector indexes
├── ports/                # External capability interfaces, including LLM clients
├── domain/               # Shared alias and time rules
├── adapters/             # JSON-RPC bridge, CLI, source-only dashboard
└── operations/           # Import/export, migration, portable packages
plugins/                  # External agent adapters, organized by host
examples/                 # Public API example
tests/ / evals/           # Behavior tests / synthetic recall evaluation
docs/agent/               # Harness project map, decisions, and handoff
```

Adapters call inward through application and pipeline/core/storage layers. `MemoryService` and `Bridge`
share `MemoryRuntime`; pipeline/storage do not depend on adapters, and backend-specific SQL stays in storage.
The source dashboard's direct SQLite access is an existing exception.

### Host call flow

```text
Python host → MemoryService ─────────┐
Hermes → in-process Bridge ──────────┤
OpenClaw → JSON-RPC bridge ───────────┴→ MemoryRuntime → pipelines → Memory
CLI → application / operations ────────────────────────────────────┘
                                                     ├→ SQLite / PostgreSQL
                                                     └→ optional vector index
```

Hermes currently calls `Bridge` in-process; OpenClaw uses a bridge subprocess. `MemoryService.recall()` also calls the recall pipeline directly. Facts live in `AtomCard`; tree leaves reference atoms and project their content. The tree is an organization view, not an additional copy or independent recall source.

### Long-term memory flow

```text
RawEvent ──extraction──→ Candidate ──promotion──→ AtomCard ──dirty / regeneration──→ EntityPage
    └──episode extraction──→ Episode                └──atom_id reference──→ tree leaf
```

Candidates do not all require human approval. Promotion checks value, evidence, entity resolution,
duplicates, and conflicts; it can promote, merge, or drop candidates automatically, leaving review/conflict
cases for user action. Pages are marked dirty and regenerated when triggered by runtime/CLI/host,
rather than immediately after every write. Episode extraction is a parallel path from raw events.
Manual `Memory.store()` needs no model and directly creates RawEvent/Candidate/AtomCard plus a leaf reference.

Prompt recall routes `atom` and `raw` by default, adds `page_headline` when an entity is resolved, and adds `vector` when configured. With the default raw fallback policy, durable hits suppress raw; passing the current session/thread excludes its raw events from prompt injection.

Synthetic runtime failures are excluded from automatic capture, extraction and raw prompt fallback. octop-harness / Octop raise model errors into checkpoint task failures and display diagnostics separately; automatic team failure notifications are excluded from capture. Hosts that still create synthetic replies must mark them with `payload.octop_runtime_error=true`; online filtering uses structured provenance only. Agents decide when to call `memory_save`; approvals and manual saves are protected by their provenance, without intent or troubleshooting-value keyword lists. Automatic capture keeps its length policy with no intent-keyword exception; explicit saves bypass that capture policy. Original diagnostics remain inspectable by ID. `operations.retention.audit_runtime_errors(memory)` previews eligible records by default; even `apply=True` retires only automatic atoms whose evidence is entirely marked as runtime failures. The fixed legacy retry envelope only nominates `review_atom_ids` / `review_candidate_ids`; missing and mixed evidence stays unchanged for human review.

`MemoryService.reconcile_manual_documents({"USER.md": text, "MEMORY.md": text})` gives owner-edited documents priority. Bridge exposes the same operation and `manual_document_review_status`. Proven conflicts softly retire the old atom and create a replacement review candidate with original evidence and a journal trail; acceptance makes the replacement a confirmed fact. Duplicate atoms remain stored; pass the actual session snapshot as `recall(..., manual_context=documents)` to suppress repeated context. An optional `manual_documents_provider` checks current files after saves/automatic promotions, without refreshing chat snapshots. Each call checks up to 100 new facts and accepts at most 100,000 document characters. Partial checks are resumable; unavailable/uncertain/invalid semantic checks are explicit and never force retirement. Full documents are comparison metadata, not indexed atoms. See ADR-042.

Start with [CONTRIBUTING.md](CONTRIBUTING.md); the [project map](docs/agent/PROJECT_MAP.md) covers architecture and data flow. AI contributors use [AGENTS.md](AGENTS.md), with task clarification and handoff in [HANDOFF.md](docs/agent/HANDOFF.md).

## Development

```bash
make install          # uv sync --group dev
make install-hooks    # required once per clone
make all              # format + lint + strict mypy + tests
uv build              # Python wheel + source distribution
```

Run PostgreSQL behavior tests against a real test server with `TEST_POSTGRES_DSN`; skipped PG cases do not prove compatibility. OpenClaw has its own `npm ci`, `npm test`, and `npm run build` under `plugins/openclaw/octopmemory/`.

The repository retains tests, CI, examples, and plugins; the Python sdist contains the sources needed to rebuild the wheel. Development and release procedures live in [CONTRIBUTING.md](CONTRIBUTING.md).

## License

[MIT](LICENSE). Report vulnerabilities through the channels in [SECURITY.md](SECURITY.md).
