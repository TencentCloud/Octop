# Contributing to Octop

Thank you for your interest in contributing! Octop is the control-plane application in the [Octop Harness](https://github.com/TencentCloud) ecosystem.

## Getting started

**Prerequisites:** Python 3.12+, Node.js 18+, [uv](https://docs.astral.sh/uv/)

```bash
git clone https://github.com/TencentCloud/Octop.git octop
cd octop
make install          # backend dev dependencies
make install-hooks    # once per clone: pre-commit runs make all + dashboard build
make all              # format-all + backend lint + typecheck + test (ship bar)
```

For frontend work (separate terminal):

```bash
make dev-frontend     # Vite dev server
make lint-frontend
make typecheck-frontend
make check-all        # full stack quality gate
```

## Development workflow

| Command | Description |
|---------|-------------|
| `make install` | Install Python dev dependencies |
| `make install-hooks` | Point git at `.githooks` (pre-commit: `make all` + dashboard build) |
| `make all` | `format-all` + backend lint + typecheck + test |
| `make check-all` | Full stack quality gate |
| `make dev` | Start frontend + backend dev servers |
| `make build` | Build dashboard + Python wheel |
| `make docs-cli` | Regenerate CLI documentation |

## Branching

| Branch | Role |
|--------|------|
| `main` | Production source of truth; GitHub default branch; only release / hotfix merges |
| `develop` | Daily integration; **open feature PRs against `develop`** |
| `release/x.y.z` | Temporary release snapshot; deleted after the version ships |
| `hotfix/*` | Emergency fix from `main`; merge to `main` and back to `develop` |

```
feature/* ──PR──► develop ──► release/x.y.z ──PR──► main ──tag v*──► publish
hotfix/* ──PR──► main (+ tag) and ──PR──► develop
```

**Rules:**

- Never push `develop` directly to `main` — ship only via `release/x.y.z` → `main` (or hotfix → `main`). Do **not** open `develop` → `main` bulk merges; they fork history and break post-release sync.
- Merge `release/x.y.z` → `main` with a **merge commit** (not squash). Squash drops shared ancestry with `develop`.
- Production `v*` tags are created **on `main` after** the release PR merges — not on the release branch before merge.
- After a release, `main` must stay an **ancestor** of `develop`. GitHub Actions runs `sync-main-to-develop.yml` (merge first; on conflict, a `chore/sync-develop-after-*` PR). Do not open legacy `head=main` → `develop` PRs.

## Pull requests

1. Fork (if needed) and create a feature branch from **`develop`**
2. Open the PR with base **`develop`** (not `main`, unless it is a release or hotfix)
3. Add or update tests for behavior changes — CI runs on **Linux and Windows**; follow the cross-platform rules in [AGENTS.md](AGENTS.md) §7 (prefer `tmp_path` / `pathlib`, `fake_bin_path` for mocked binaries, `posix_only` for Unix-only cases)
4. Ensure `make install-hooks` is enabled locally; run `make all` (backend) or `make check-all` (full stack) before submitting — pre-commit enforces the same gate
5. Update `CHANGELOG.md` when user-facing behavior changes; update `docs/` (e.g. `docs/api.md`) when HTTP or product behavior changes
6. Open a PR with a clear description and test plan

See [AGENTS.md](AGENTS.md) for module boundaries and coding conventions.

## Releases

1. Cut `release/x.y.z` from latest `develop` (version bump + CHANGELOG on that branch)
2. Open PR: `release/x.y.z` → `main` and merge when green
3. Tag `v<version>` on **main tip** and push — GitHub Actions builds, publishes to PyPI, and creates the GitHub Release
4. Delete `release/x.y.z`; Actions syncs `main` → `develop` (or opens `chore/sync-develop-after-*` if merge conflicts / branch protection)

Agent-assisted publish: `.cursor/skills/publish` (`/publish <version>`).

### Hotfix

Branch from `main` → PR into `main` (tag if shipping a patch) → PR into `develop`.

---

# 贡献指南

感谢你对 Octop 的关注！Octop 是 [Octop Harness](https://github.com/TencentCloud) 生态中的可自托管 AI 助手平台，支持多用户与多 Agent。

## 环境搭建

**前置条件：** Python 3.12+、Node.js 18+、[uv](https://docs.astral.sh/uv/)

```bash
git clone https://github.com/TencentCloud/Octop.git octop
cd octop
make install
make install-hooks    # 每个 clone 执行一次：提交前跑 make all + 前端 build
make all              # format-all + 后端 lint / typecheck / test
```

前端开发（另开终端）：

```bash
make dev-frontend
make check-all        # 全栈质量门禁
```

## 分支策略

| 分支 | 角色 |
|------|------|
| `main` | 生产真源；GitHub 默认分支；仅合入 release / hotfix |
| `develop` | 日常集成；**特性 PR 请打向 `develop`** |
| `release/x.y.z` | 临时发版分支；发版完成后删除 |
| `hotfix/*` | 从 `main` 紧急修复；合入 `main` 后再合回 `develop` |

**规则：**

- 禁止 `develop` 直推/直 merge 到 `main` — 发版必须走 `release/x.y.z` → `main`（或 hotfix → `main`）。不要开 `develop` → `main` 大包 PR，否则历史分叉、发版后 sync 必冲突。
- `release/x.y.z` → `main` 请用 **merge commit** 合并，不要 squash。
- 生产 `v*` tag 仅在 release PR **合入 `main` 之后**打在 main tip 上。
- 发版后 `main` 必须是 `develop` 的祖先；由 Actions `sync-main-to-develop.yml` 自动 sync（冲突或分支保护时会开 `chore/sync-develop-after-*` PR）。不要再用 `head=main` → `develop` 的老 sync PR。

## 提交流程

1. 从 **`develop`** 创建特性分支
2. PR 的 base 选 **`develop`**（release / hotfix 除外）
3. 补充测试（CI 同时跑 **Linux / Windows**，路径与假二进制遵循 [AGENTS.md](AGENTS.md) §7）
4. 本地执行过 `make install-hooks`；提交前 `make all` 或 `make check-all` 必须绿（hooks 会强制执行）
5. 用户可见变更时更新 `CHANGELOG.md`；HTTP 或产品行为变更时同步更新 `docs/`（如 `docs/api.md`）
6. 提交 Pull Request

模块边界与编码规范见 [AGENTS.md](AGENTS.md)。

## 发版

1. 从最新 `develop` 切 `release/x.y.z`（在该分支 bump 版本与 CHANGELOG）
2. PR：`release/x.y.z` → `main`，合并通过后
3. 在 **main tip** 打并推送 `v<version>`，由 Actions 构建并发布
4. 删除 `release/x.y.z`；Actions 自动 sync `main` → `develop`（冲突或分支保护时会开 `chore/sync-develop-after-*` PR）

Hotfix：从 `main` 拉分支 → 合入 `main`（需发补丁则打 tag）→ 再合入 `develop`。
