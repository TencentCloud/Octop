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
5. Update `CHANGELOG.md` when user-facing behavior changes
6. Open a PR with a clear description and test plan

See [AGENTS.md](AGENTS.md) for module boundaries and coding conventions.

## Pull Request submission guidelines

To ensure code quality and collaboration efficiency, please observe the following principles when opening a Pull Request.

### ✅ PR essentials

#### 1. 📸 Provide visual proof (screenshots / recordings)

Always attach screenshots, whether in the PR description or a comment.

- Let reviewers **see the "human"** — prove the code was manually reviewed and crafted with care.
- UI changes must include interface screenshots.
- Bug fixes are best shown with before/after comparison images.
- Complex interaction flows may use a GIF / video demo.

> 💡 Screenshots are not only proof that "it was tested" but also a communication tool that helps reviewers quickly understand intent.

#### 2. 🧪 Complete test cases & passing CI

**Every PR must include test cases, and they must be complete.**

- ✅ New feature → add the corresponding unit / integration tests.
- ✅ Bug fix → add a regression test to prevent recurrence.
- ✅ Adequate coverage → core logic is well covered.
- ✅ **All CI workflows must pass** → don't expect reviewers to fix failing CI for you.

> ⚠️ Run `npm test` / `pytest` / `go test` locally before pushing to remote.

#### 3. 🔄 Collaborating with AI: confirm shared understanding

When using AI-assisted coding, **make sure both sides understand the same thing**.

1. After describing requirements clearly, **ask the AI to repeat them** to confirm understanding.
2. For complex logic, ask the AI to explain its implementation plan.
3. After code is generated, **proactively ask**:
   - "Does this implementation satisfy all requirement points?"
   - "Are there any missed scenarios?"
   - "Is there a simpler implementation?"

> 🤖 AI is not a one-shot tool; multiple rounds of dialogue are needed to calibrate understanding. Spend 2 minutes confirming rather than 2 hours redoing.

#### 4. 🎯 Code quality: minimal changes & iterative refinement

**Hold to the minimal-change principle.**

- One PR **solves only one problem**.
- Don't do unrelated refactors (open a separate PR).
- Clear structure, accurate naming, concise logic.

**Three questions to ask after AI generates code:**

1. Is there still room to optimize this code? (performance, readability, edge cases)
2. Are all errors / exceptions handled properly?
3. Is there redundant code or unused variables / imports?

> 📝 Good code isn't written once; it's asked into being.

### 📋 Quick checklist (copy into PR description template)

```markdown
## PR Checklist

- [ ] 📸 UI screenshots / feature demo provided
- [ ] 🧪 Test cases added and passing
- [ ] ✅ All CI workflows passing
- [ ] 🤖 Requirements aligned with AI
- [ ] 🎯 Follows minimal-change principle, clear structure
- [ ] 📝 Optimization suggestions asked and addressed
```

### 🤔 Why these rules?

| Rule | Problem solved |
|------|----------------|
| Attach screenshots | Avoid repeated "was it tested?" questions; build trust |
| Tests + CI | Prevent regression, reduce review burden |
| AI alignment | Reduce "this isn't what I wanted" rework |
| Minimal change + questions | Maintain code maintainability, reject filler code |

> **Remember: a PR is communication, not a handoff. Make reviewers' lives easy, and your own PR merges faster.**

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
5. 用户可见变更时更新 `CHANGELOG.md`
6. 提交 Pull Request

模块边界与编码规范见 [AGENTS.md](AGENTS.md)。

## Pull Request 提交规范

为了保证代码质量和协作效率，提交 Pull Request 时请务必遵守以下原则：

### ✅ PR 必备清单

#### 1. 📸 提供视觉证明（截图/录屏）

**必须贴截图**，无论放在 PR 描述中还是评论里。

- 让 reviewer **看到"人"** —— 证明这段代码是经过人工检查、用心完成的
- UI 变更必须有界面截图
- 功能修复最好有修复前后的对比图
- 复杂的交互流程可用 GIF/视频演示

> 💡 截图不仅是为了证明"测过了"，更是沟通工具，帮助 reviewer 快速理解改动意图。

#### 2. 🧪 测试用例完整 & CI 通过

**所有 PR 必须包含测试用例，且测试用例必须完整。**

要求：

- ✅ 新增功能 → 新增对应的单元测试/集成测试
- ✅ Bug 修复 → 添加回归测试，防止问题再次发生
- ✅ 覆盖率达标 → 核心逻辑测试覆盖充分
- ✅ **所有 CI Workflow 必须通过** → 不要期望 reviewer 去帮你 fix 失败的 CI

> ⚠️ 提交前先在本地运行 `npm test` / `pytest` / `go test` 等，确认无误后再推送到远程。

#### 3. 🔄 与 AI 协作：确认理解一致

使用 AI 辅助编码时，**务必确认双方理解一致**。

做法：

1. 明确需求描述后，**让 AI 重复一遍需求**，确认理解无误
2. 对于复杂逻辑，让 AI 解释其实现方案
3. 生成代码后，**主动追问**：
   - "这个实现是否满足所有需求点？"
   - "是否有遗漏的场景？"
   - "有没有更简洁的实现方式？"

> 🤖 AI 不是一次性工具，需要多轮对话来校准理解。宁可多花 2 分钟确认，也不要花 2 小时返工。

#### 4. 🎯 代码质量：最小修改 & 追问优化

**坚守最小修改原则。**

- 一个 PR **只解决一个问题**
- 不要做无关的重构（可以另开 PR）
- 结构清晰，命名准确，逻辑简洁

**AI 生成代码后，必问的 3 个问题：**

1. 这段代码是否还有优化空间？（性能、可读性、边界处理）
2. 是否所有错误/异常都被妥善处理？
3. 是否有冗余代码或未使用的变量/导入？

> 📝 好的代码不是一次写出来的，是问出来的。

### 📋 Quick Checklist (复制到 PR 描述模板)

```markdown
## PR Checklist

- [ ] 📸 已提供 UI 截图/功能演示
- [ ] 🧪 测试用例已添加并通过
- [ ] ✅ CI Workflow 全部通过
- [ ] 🤖 已与 AI 对齐需求理解
- [ ] 🎯 遵循最小修改原则，代码结构清晰
- [ ] 📝 已询问并处理代码优化建议
```

### 🤔 为什么要有这些规范？

| 规范 | 解决的问题 |
|------|-----------|
| 贴截图 | 避免"测试过吗？"的反复询问，建立 trust |
| 测试+CI | 防止 regression，降低 review 负担 |
| AI 对齐 | 减少"这不是我要的"的返工 |
| 最小修改+追问 | 保证代码可维护性，拒绝凑数代码 |

> **记住：PR 是沟通，不是交接。让 reviewer 轻松，就是让自己更快合入。**

## 发版

1. 从最新 `develop` 切 `release/x.y.z`（在该分支 bump 版本与 CHANGELOG）
2. PR：`release/x.y.z` → `main`，合并通过后
3. 在 **main tip** 打并推送 `v<version>`，由 Actions 构建并发布
4. 删除 `release/x.y.z`；Actions 自动 sync `main` → `develop`（冲突或分支保护时会开 `chore/sync-develop-after-*` PR）

Hotfix：从 `main` 拉分支 → 合入 `main`（需发补丁则打 tag）→ 再合入 `develop`。
