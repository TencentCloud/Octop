---
name: publish
description: >-
  Publish the octop-browser Python package: cut a release branch from develop, bump
  version, update CHANGELOG / README, open a PR to main; after merge, Actions
  tag on main (PyPI + GitHub Release) and sync main into develop. Use when the
  user asks to publish, release, bump version, cut a release, or run /publish.
disable-model-invocation: true
---

# Publish

自动化 octop-browser（PyPI: `octop-browser`）的完整发布流程。

**开始时宣告：** "正在使用 publish 技能发布版本 {VERSION}。"

## 配置项

以下配置有默认值，可在项目的 `.cursor/skills/publish/SKILL.md` 或 `.codebuddy/skills/publish/SKILL.md` 中覆盖。

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `CHANGELOG_FILE` | `CHANGELOG.md` | 相对于仓库根目录的路径，文件不存在则跳过 |
| `VERSION_FILE` | `pyproject.toml` | 包含版本号的文件 |
| `VERSION_PATTERN` | `^\s*version\s*=\s*"[^"]+"` | 匹配版本行的正则表达式 |
| `README_FILE` | `README.md` | 发版时同步检查/更新的 README（见步骤 4b） |
| `README_CN_FILE` | `README_CN.md` | 若存在则同样同步；缺失则跳过 |
| `INIT_VERSION_FILE` | `(none — package metadata)` | 含硬编码 `__version__` 时同步；本包通常由 `importlib.metadata` 读取，缺失/元数据驱动则跳过 |
| `TAG_PREFIX` | `v` | Git tag 前缀；工作流监听 `v*` |
| `REMOTE` | `origin` | Git 远程仓库名（推送 release 分支与创建 PR） |
| `INTEGRATION_BRANCH` | `develop` | 日常集成分支；release 必须从最新 tip 切出 |
| `TARGET_BRANCH` | `main` | 合并请求的目标分支（生产真源） |
| `RELEASE_BRANCH_PREFIX` | `release/` | release 分支名前缀 |
| `PYPI_PACKAGE` | `octop-browser` | PyPI 包名（仅用于提示文案） |

## 调用方式

```
/publish 0.1.14
```

目标版本号是唯一必填参数，其余均从配置或自动检测获取。

## 发布流程

> **顺序硬约束：** 先 PR 合入 `main`，再在 **main tip** 打并推送 `v*` tag。  
> **禁止**在 release 分支未合入 `main` 前推送生产 tag。  
> **禁止**在本地直接 `twine upload` / `make publish` — 公开发布由 GitHub Action 负责。  
> **禁止**将 `develop` 直接 push / merge 进 `main`。

### 步骤 1 — 读取配置并确认版本

1. 获取仓库根目录：`git rev-parse --show-toplevel`
2. 记录当前分支为 `{original_branch}`。
3. `git fetch {REMOTE} {INTEGRATION_BRANCH} {TARGET_BRANCH}`
4. 从 `VERSION_FILE` 读取当前版本（在即将基于的 integration tip 上）：
   ```bash
   git show {REMOTE}/{INTEGRATION_BRANCH}:pyproject.toml | grep -E '^\s*version\s*=\s*"[^"]+"'
   ```
5. 检查未提交的更改：
   ```bash
   git status --short
   ```
   若工作树不干净：**中止**并要求用户先提交或 stash。发布不得夹带无关脏文件。
6. 查找最近的 git tag：
   ```bash
   git tag --sort=-creatordate | head -1
   ```
   如果没有 tag，视为首次发布（在步骤 3 中使用从仓库初始到 HEAD 的所有提交）。
7. 展示确认信息：

```
当前版本 (pyproject.toml @ develop): X.Y.Z
目标版本:                           A.B.C
上次发布 tag:                       vX.Y.Z (YYYY-MM-DD)
Release 分支:                       release/A.B.C
集成起点:                           develop
合入目标:                           main
Tag 时机:                           main 合并之后（不会在 release 上先打 tag）
PyPI 包:                            octop-browser

确认发布 X.Y.Z → A.B.C？[y/N]
```

如果用户未输入 `y` 确认，立即中止。

### 步骤 2 — 从 develop 创建 release 分支

```bash
git checkout -B {RELEASE_BRANCH_PREFIX}{version} {REMOTE}/{INTEGRATION_BRANCH}
```

如果本地或远程已存在同名 release 分支，中止：
```
✗ 分支 {RELEASE_BRANCH_PREFIX}{version} 已存在。
请手动删除后再运行 /publish。
```

### 步骤 3 — 分析变更并生成 CHANGELOG 草稿

1. 获取上次 tag 以来的提交（相对当前 release HEAD，即 develop tip）：
   ```bash
   git log {last_tag}..HEAD --oneline
   # 首次发布时：
   git log --oneline
   ```

2. 如果没有找到提交：
   ```
   ⚠ 自上次发布 tag ({last_tag}) 以来没有新提交。
   是否继续？[y/N]
   ```
   用户未确认则中止。

3. 按提交前缀分类，生成 Keep a Changelog 格式的条目。

   **CHANGELOG 内容必须用中文书写。** 将每个提交总结为简洁的中文要点 — 不要逐字翻译提交信息。适当合并相关提交。

   分类规则：
   - 以 `feat:` 或 `feat(` 开头 → **新增**
   - 以 `fix:` 或 `fix(` 开头 → **修复**
   - 以 `refactor:` 或 `perf:` 开头 → **变更**
   - 包含 `!:` 或提交正文含 `BREAKING CHANGE:` → **变更**，加 `**Breaking:**` 前缀
   - 以 `docs:` 开头 → **变更**
   - 以 `chore:`、`test:`、`ci:` 开头 → 忽略（基础设施噪音）
   - 其他所有提交 → **变更**
   - 移除的功能 → **移除**
   - 安全修复 → **安全**

   输出格式：
   ```markdown
   ## [A.B.C] - YYYY-MM-DD

   ### 新增
   - 中文描述新增功能

   ### 修复
   - 中文描述修复内容

   ### 变更
   - 中文描述行为变更

   ### 移除
   - 中文描述移除内容

   ### 安全
   - 中文描述安全修复
   ```
   省略空的分类。日期使用 ISO 8601 格式（当天日期）。日期行与第一个分类之间、各分类之间保留空行。

4. 向用户展示草稿并请求确认：
   ```
   CHANGELOG 草稿：

   {draft}

   添加到 CHANGELOG.md？[y/N/edit]
   ```
   - `y` → 继续
   - `n` → 中止
   - `edit` 或其他反馈 → 询问用户："需要什么修改？" — 等待回复后重新生成，再次展示确认。循环直到 `y` 或 `n`。

5. 如果 `CHANGELOG_FILE` 不存在，跳过此步骤（无需警告）。

### 步骤 4 — 更新文件、提交并推送 release 分支

按顺序执行：

**4a. 更新 CHANGELOG：**

在 `CHANGELOG_FILE` 中找到 `## [Unreleased]` 标题，在其后插入新版本条目（保持 `[Unreleased]` 为空）：

```markdown
## [Unreleased]

## [A.B.C] - YYYY-MM-DD
### 新增
- ...
```

如果 `## [Unreleased]` 标题不存在，在 `# Changelog` 标题行之后插入新条目（若无标题则插入到文件顶部）。

**4b. 升级版本号并同步 README：**

发布版本号必须保持多文件一致。依次处理：

1. `VERSION_FILE`（`pyproject.toml`）— wheel / PyPI 的唯一版本源：
   ```bash
   grep -n '^\s*version\s*=\s*"[^"]+"' pyproject.toml
   # 用 Edit 工具将该行的 "X.Y.Z" 替换为 "A.B.C"
   ```
2. `README_FILE` / `README_CN_FILE`（若存在）：
   - 若存在静态 shields 徽标 `version-X.Y.Z-orange`（或同类），升级为 `version-A.B.C-orange`。
   - 若仅使用动态 `shields.io/pypi/v/octop-browser` 徽标，**无需改徽标**（PyPI 发布后自动更新），但仍须检查 README 中是否有硬编码安装示例版本（如 `pip install octop-browser==X.Y.Z`）并同步。
   - 用户可见的发版说明若写在 README，按需补一行指向 `CHANGELOG.md` 对应版本。
   - 文件不存在则跳过并提示（不中止）。
3. `INIT_VERSION_FILE` — 仅当文件内存在硬编码 `__version__ = "..."` 时升级；若通过 `importlib.metadata` / `_version.py` 读包元数据则跳过。

**4c. 提交：**

```bash
git status --short
```

- 如果有更改：暂存并提交：
  ```bash
  git add -A
  git commit -m "chore: release {version}"
  ```
- 如果工作树已干净：无需提交，跳过。

**4d. 推送 release 分支：**
```bash
git push -u {REMOTE} {RELEASE_BRANCH_PREFIX}{version}
```

推送失败则中止。

### 步骤 5 — 创建合入 main 的 Pull Request（先合，后自动 tag）

使用 `gh` CLI（`--repo` 指向 GitHub 上的本仓）：

```bash
gh pr create \
  --repo TencentCloud/octop-browser \
  --base {TARGET_BRANCH} \
  --head {RELEASE_BRANCH_PREFIX}{version} \
  --title "chore: release {version}" \
  --body "$(cat <<'EOF'
{步骤 3 生成的 CHANGELOG 条目}

## Release checklist
- [ ] CI green
- [ ] Merge this PR into main with a **merge commit** (not squash)
- [ ] After merge, GitHub Action auto-pushes v{version} tag on main tip
- [ ] Release workflow publishes octop-browser to PyPI and syncs main → develop
EOF
)"
```

- 成功时展示 PR URL，并明确告知：
  - 合并前不要手动打 tag；
  - 合并请用 **merge commit**；
  - 合并后会自动发版（自动打 tag → PyPI → sync develop）。
- 若 `gh` 失败：中止（此时尚未发版），提示手动创建 PR：
  `{RELEASE_BRANCH_PREFIX}{version}` → `{TARGET_BRANCH}`

### 步骤 6 — 等待合入后，由 Action 在 main tip 打 tag

1. 询问用户 PR 是否已合并，或轮询：
   ```bash
   gh pr view {pr_url} --json state,mergedAt
   ```
   未合并则等待；无需本地执行打 tag。

2. 合并后：
   - `auto-tag-on-release.yml` 会读取合并后 `main` 的 `pyproject.toml` 版本并推送 `{TAG_PREFIX}{version}`。
   - 随后 dispatch `release.yml`：构建 → PyPI → GitHub Release → `sync-main-to-develop.yml`。
   - 若 tag 已存在，Action 会跳过并输出日志。

3. 提示用户到 Actions 确认：
   - `Auto Tag On Release Merge` 成功；
   - `Release` 随 `v*` tag / dispatch 通过；
   - `Sync Main Into Develop` 在 GitHub Release 发布后把 `main` 同步回 `develop`。

### 步骤 7 — 删除 release 分支；develop 由 Action 同步

1. 删除远程与本地 release 分支：
   ```bash
   git push {REMOTE} --delete {RELEASE_BRANCH_PREFIX}{version}
   git branch -D {RELEASE_BRANCH_PREFIX}{version}
   ```
   删除失败则警告（非致命），提示手动删除。

2. **develop 同步**：GitHub Release 发布成功后，`sync-main-to-develop.yml` 会自动把 `main` 合入 `develop`（保护/冲突时开 `chore/sync-develop-after-*` PR，尽量 merge auto-merge）。
   - 若已快进无差异，Action 会跳过。
   - 技能侧无需再手动创建 sync PR（除非 Action 失败）。

### 步骤 8 — 切回原分支

```bash
git checkout {original_branch}
```

确保流程结束后用户不会停留在 release / 临时检出上。

## 错误处理参考

| 场景 | 行为 |
|------|------|
| `VERSION_FILE` 未找到 | 中止："找不到 VERSION_FILE：{path}" |
| 文件中未匹配到版本号 | 中止："在 {VERSION_FILE} 中找不到匹配 {VERSION_PATTERN} 的版本行" |
| 工作树不干净 | 中止：先清理再发布 |
| 没有 git tag（首次发布） | 使用完整历史；提示"首次发布" |
| 上次 tag 以来无提交 | 警告并询问是否继续 |
| Release 分支已存在 | 中止并给出删除指令 |
| 步骤 4 推送失败 | 中止：文件已在本地更新但未推送 |
| 步骤 5 PR 创建失败 | 中止（尚未打 tag / 未发版） |
| 步骤 6 在未合入时手动打 tag | **禁止** — 硬红线 |
| 步骤 6 tag 已存在 | Action 跳过；提示检查是否已发布 |
| 步骤 6 tag 推送成功但 Action 失败 | 非致命：提示到 Actions Re-run |
| 步骤 7 删分支或 sync 失败 | 警告并给出手动命令 |

## 红线规则

**绝不：**
- 在 release / feature 分支上、于合入 `main` **之前**推送生产 `v*` tag
- 在推送 tag 前直接上传 PyPI（发布由 GitHub Action 负责）
- 将 `develop` 直接 push / merge 进 `main`（必须走 `release/*` PR）
- 直接 push 到受保护的 `main` / `develop`
- 跳过步骤 1 的用户确认
- 跳过步骤 3 的 CHANGELOG 确认
- 在任何步骤失败后继续执行（步骤 7 的清理/同步警告除外）
- 流程结束后让用户留在 release 分支
- 保留已发完的 `release/*` 作为长期分支

**始终：**
- 从最新 `{REMOTE}/{INTEGRATION_BRANCH}` 切 release
- 先合入 `{TARGET_BRANCH}`，再由 Action 在 main tip 打 tag
- 发版时同步更新 CHANGELOG，并检查/更新 README（及 README_CN）
- 发版后删除 `release/*`；`main → develop` 由 `sync-main-to-develop.yml` 自动同步（失败时再手动补）
- 中止前展示完整错误输出
- 插入新版本条目后保持 `[Unreleased]` 为空
- 推送 tag 后提示用户关注 GitHub Actions 的发布结果
