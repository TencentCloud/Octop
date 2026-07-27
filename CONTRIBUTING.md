# Contributing to Octop

Thank you for your interest in contributing! Octop is the control-plane application in the [Octop Harness](https://github.com/TencentCloud) ecosystem.

## Getting started

**Prerequisites:** Python 3.11+, Node.js 18+, [uv](https://docs.astral.sh/uv/)

```bash
git clone https://github.com/TencentCloud/Octop.git octop
cd octop
make install          # backend dev dependencies
make all              # backend lint + typecheck + test (CI ship bar)
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
| `make all` | Backend lint + typecheck + test |
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

**Rules:** never push `develop` directly to `main` (PR only). Production `v*` tags are created **on `main` after** the release PR merges — not on the release branch before merge.

## Pull requests

1. Fork (if needed) and create a feature branch from **`develop`**
2. Open the PR with base **`develop`** (not `main`, unless it is a release or hotfix)
3. Add or update tests for behavior changes
4. Run `make all` (backend) or `make check-all` (full stack) before submitting
5. Update `CHANGELOG.md` when user-facing behavior changes
6. Open a PR with a clear description and test plan

See [AGENTS.md](AGENTS.md) for module boundaries and coding conventions.

## Releases

1. Cut `release/x.y.z` from latest `develop` (version bump + CHANGELOG on that branch)
2. Open PR: `release/x.y.z` → `main` and merge when green
3. Tag `v<version>` on **main tip** and push — GitHub Actions builds, publishes to PyPI, and creates the GitHub Release
4. Delete `release/x.y.z`; if needed, open PR `main` → `develop` to sync

Agent-assisted publish: `.cursor/skills/publish` (`/publish <version>`).

### Hotfix

Branch from `main` → PR into `main` (tag if shipping a patch) → PR into `develop`.

---

# 贡献指南

感谢你对 Octop 的关注！Octop 是 [Octop Harness](https://github.com/TencentCloud) 生态中的可自托管 AI 助手平台，支持多用户与多 Agent。

## 环境搭建

**前置条件：** Python 3.11+、Node.js 18+、[uv](https://docs.astral.sh/uv/)

```bash
git clone https://github.com/TencentCloud/Octop.git octop
cd octop
make install
make all              # 后端质量门禁
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

**规则：** 禁止将 `develop` 直接推送到 `main`（必须走 PR）。生产 `v*` tag 仅在 release PR **合入 `main` 之后**打在 main tip 上。

## 提交流程

1. 从 **`develop`** 创建特性分支
2. PR 的 base 选 **`develop`**（release / hotfix 除外）
3. 补充测试，运行 `make all` 或 `make check-all`
4. 用户可见变更时更新 `CHANGELOG.md`
5. 提交 Pull Request

模块边界与编码规范见 [AGENTS.md](AGENTS.md)。

## 发版

1. 从最新 `develop` 切 `release/x.y.z`（在该分支 bump 版本与 CHANGELOG）
2. PR：`release/x.y.z` → `main`，合并通过后
3. 在 **main tip** 打并推送 `v<version>`，由 Actions 构建并发布
4. 删除 `release/x.y.z`；必要时再开 `main` → `develop` 同步 PR

Hotfix：从 `main` 拉分支 → 合入 `main`（需发补丁则打 tag）→ 再合入 `develop`。
