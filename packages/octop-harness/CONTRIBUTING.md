# Contributing to octop-harness

Thank you for your interest in contributing! This guide applies to the [Octop Harness](https://github.com/TencentCloud) ecosystem.

## Getting started

**Prerequisites:** Python 3.12+, [uv](https://docs.astral.sh/uv/)

```bash
git clone https://github.com/TencentCloud/octop-harness.git
cd octop-harness
make install        # install dev dependencies
make all            # lint + typecheck + test (CI ship bar)
```

## Development workflow

| Command | Description |
|---------|-------------|
| `make install` | Install dev dependencies |
| `make all` | Lint + typecheck + test (required before PR) |
| `make lint` | Ruff check + format check |
| `make format` | Auto-fix and format code |
| `make typecheck` | mypy strict |
| `make test` | pytest with coverage |
| `make build` | Build wheel + sdist |

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
- Never push directly to `main` or `develop` — always open a PR (enforce via GitHub branch protection).
- Merge `release/x.y.z` → `main` with a **merge commit** (not squash). Squash drops shared ancestry with `develop`.
- Production `v*` tags are created **on `main` after** the release PR merges — not on the release branch before merge.
- After a release, `main` must stay an **ancestor** of `develop`. GitHub Actions runs `sync-main-to-develop.yml` (merge first; on conflict, a `chore/sync-develop-after-*` PR). Do not open legacy `head=main` → `develop` PRs.

### GitHub branch protection (required settings)

Configure in the GitHub repo **Settings → Branches** for both `main` and `develop`:

- Require a pull request before merging
- Block force pushes and deletions
- Do **not** allow direct pushes to the branch
- Require status checks to pass (CI)
- For `main`: prefer disallowing squash merges for release PRs, or always choose **Create a merge commit** when merging `release/*`



## Pull requests

1. Fork (if needed) and create a feature branch from **`develop`**
2. Open the PR with base **`develop`** (not `main`, unless it is a release or hotfix)
3. Add or update tests for behavior changes
4. Run `make all` locally — CI must pass
5. Update `CHANGELOG.md` under **Unreleased** when user-facing behavior changes
6. Open a PR with a clear description and test plan


## Code style

- **Ruff** for linting and formatting (`line-length = 120`)
- **mypy** strict mode for type checking
- Prefer focused PRs — one logical change per PR
- See [AGENTS.md](AGENTS.md) for module boundaries

## Releases

1. Cut `release/x.y.z` from latest `develop` (version bump + CHANGELOG + README sync on that branch)
2. Open PR: `release/x.y.z` → `main` and merge when green (**merge commit**)
3. GitHub Action `Auto Tag On Release Merge` reads `pyproject.toml` on **main tip**, pushes `v<version>`, and dispatches `Release`
4. `Release` builds, publishes `octop-harness` to PyPI (trusted publishing), creates the GitHub Release, then dispatches `Sync Main Into Develop`
5. Delete `release/x.y.z`; Actions syncs `main` → `develop` (or opens `chore/sync-develop-after-*` if merge conflicts / branch protection)

Agent-assisted publish: `.cursor/skills/publish` / `.codebuddy/skills/publish` (`/publish <version>`).

Manual fallback: push a `v<version>` tag on main tip yourself (must match `[project].version`).

### Hotfix

Branch from `main` → PR into `main` (tag via the same auto-tag path if shipping a patch) → PR into `develop`.


---

# 贡献指南

感谢你对 octop-harness 的关注！本指南适用于 [Octop Harness](https://github.com/TencentCloud) 生态。

## 环境搭建

**前置条件：** Python 3.12+、[uv](https://docs.astral.sh/uv/)

```bash
git clone https://github.com/TencentCloud/octop-harness.git
cd octop-harness
make install
make all            # 提交 PR 前必须通过
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
- 禁止直接 push 到 `main` / `develop` — 一律走 PR（请在 GitHub 开启分支保护）。
- `release/x.y.z` → `main` 请用 **merge commit** 合并，不要 squash。
- 生产 `v*` tag 仅在 release PR **合入 `main` 之后**打在 main tip 上。
- 发版后 `main` 必须是 `develop` 的祖先；由 Actions `sync-main-to-develop.yml` 自动 sync（冲突或分支保护时会开 `chore/sync-develop-after-*` PR）。不要再用 `head=main` → `develop` 的老 sync PR。

### GitHub 分支保护（必配）

在仓库 **Settings → Branches** 为 `main` 与 `develop` 配置：

- 要求 PR 才能合并
- 禁止 force push / 删除分支
- 禁止直接 push
- 要求 CI status check 通过
- 合入 `release/*` → `main` 时使用 **Create a merge commit**



## 提交流程

1. 从 **`develop`** 创建特性分支
2. PR 的 base 选 **`develop`**（release / hotfix 除外）
3. 为行为变更补充测试
4. 本地运行 `make all`
5. 用户可见变更请更新 `CHANGELOG.md` 的 **Unreleased**
6. 提交 Pull Request


## 代码规范

- Ruff lint + format（`line-length = 120`）
- mypy strict 类型检查
- 每个 PR 聚焦单一逻辑变更
- 模块边界见 [AGENTS.md](AGENTS.md)

## 发版

1. 从最新 `develop` 切 `release/x.y.z`（在该分支 bump 版本、CHANGELOG，并同步 README 等）
2. PR：`release/x.y.z` → `main`，合并通过后（使用 **merge commit**）
3. Action `Auto Tag On Release Merge` 读取 main tip 的 `pyproject.toml`，推送 `v<version>` 并触发 `Release`
4. `Release` 构建、发布 `octop-harness` 到 PyPI、创建 GitHub Release，再触发 `Sync Main Into Develop`
5. 删除 `release/x.y.z`；Actions 自动 sync `main` → `develop`（冲突或分支保护时会开 `chore/sync-develop-after-*` PR）

Agent 辅助发布：`.cursor/skills/publish` / `.codebuddy/skills/publish`（`/publish <version>`）。

手动兜底：在 main tip 自行推送与 `[project].version` 一致的 `v<version>` 标签。

### Hotfix

从 `main` 拉分支 → 合入 `main`（需发补丁则打 tag）→ 再合入 `develop`。

