---
name: publish
description: >-
  Publish the Octop Python package: cut a release branch from develop, bump
  version, update CHANGELOG, open a PR to main, wait for merge, then tag on
  main (triggers GitHub Actions for PyPI / Docker Hub), delete the release
  branch, and sync develop. Use when the user asks to publish, release, bump
  version, cut a release, or run /publish.
disable-model-invocation: true
---

# Publish

自动化 Octop Python 包的完整发布流程。

**开始时宣告：** "正在使用 publish 技能发布版本 {VERSION}。"

## 配置项

以下配置有默认值，可在项目的 `.cursor/skills/publish/SKILL.md` 中覆盖。

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `CHANGELOG_FILE` | `CHANGELOG.md` | 相对于仓库根目录的路径，文件不存在则跳过 |
| `VERSION_FILE` | `pyproject.toml` | 包含版本号的文件 |
| `VERSION_PATTERN` | `^\s*version\s*=\s*"[^"]+"` | 匹配版本行的正则表达式 |
| `README_FILE` | `README.md` | 含 shields.io 版本徽标的文件（badge 版本号同步升级） |
| `INIT_VERSION_FILE` | `src/octop/__init__.py` | 含运行时常量 `__version__` 的文件（缺失则跳过并提示） |
| `TAG_PREFIX` | `v` | Git tag 前缀；工作流监听 `v*`，生成 `v0.1.14` 风格标签 |
| `REMOTE` | `origin` | Git 远程仓库名 |
| `INTEGRATION_BRANCH` | `develop` | 日常集成分支；release 必须从最新 tip 切出 |
| `TARGET_BRANCH` | `main` | 合并请求的目标分支（生产真源） |
| `RELEASE_BRANCH_PREFIX` | `release/` | release 分支名前缀 |

## 调用方式

```
/publish 0.1.14
```

目标版本号是唯一必填参数，其余均从配置或自动检测获取。

## 发布流程

> **顺序硬约束：** 先 PR 合入 `main`，再在 **main tip** 打并推送 `v*` tag。  
> **禁止**在 release 分支未合入 `main` 前推送生产 tag。

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

**4b. 升级版本号（同步所有版本来源）：**

发布版本号必须保持多文件一致。依次升级以下位置：

1. `VERSION_FILE`（`pyproject.toml`）— wheel / PyPI 的唯一版本源：
   ```bash
   grep -n '^\s*version\s*=\s*"[^"]+"' pyproject.toml
   # 用 Edit 工具将该行的 "X.Y.Z" 替换为 "A.B.C"
   ```
2. `README_FILE`（`README.md`）— shields.io 版本徽标：
   ```bash
   grep -n 'shields.io/badge/version-' README.md
   # 用 Edit 工具将 `version-X.Y.Z-orange` 替换为 `version-A.B.C-orange`
   ```
   文件不存在则跳过并提示（不中止）。
3. `INIT_VERSION_FILE`（`src/octop/__init__.py`）— 运行时常量 `__version__`：
   ```bash
   grep -n '__version__' src/octop/__init__.py
   # 用 Edit 工具将 `__version__ = "X.Y.Z"` 替换为 `"A.B.C"`
   ```
   文件不存在则跳过并提示（不中止）。

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

### 步骤 5 — 创建合入 main 的 Pull Request（先合，后 tag）

使用 `gh` CLI：

```bash
gh pr create \
  --base {TARGET_BRANCH} \
  --head {RELEASE_BRANCH_PREFIX}{version} \
  --title "chore: release {version}" \
  --body "$(cat <<'EOF'
{步骤 3 生成的 CHANGELOG 条目}

## Release checklist
- [ ] CI green
- [ ] Merge this PR into main
- [ ] Then tag v{version} on main tip (publish skill step 6)
EOF
)"
```

- 成功时展示 PR URL，并明确告知：**在 PR 合并前不要打 tag。**
- 若 `gh` 失败：中止（此时尚未发版），提示手动创建 PR：
  `{RELEASE_BRANCH_PREFIX}{version}` → `{TARGET_BRANCH}`

### 步骤 6 — 等待合入后，在 main tip 打 tag

1. 询问用户 PR 是否已合并，或轮询：
   ```bash
   gh pr view {pr_url} --json state,mergedAt
   ```
   未合并则**不要**打 tag；可暂停并提示用户合并后再说「继续」。

2. 合并后：
   ```bash
   git fetch {REMOTE} {TARGET_BRANCH}
   git checkout {TARGET_BRANCH}
   git pull {REMOTE} {TARGET_BRANCH}
   ```
   确认 `pyproject.toml` 版本已是目标版本（合入结果在 main 上）。

3. 打 tag 并推送（触发 GitHub Action）：

   - `release.yml`：`build` → PyPI `publish` → `github-release`
   - `docker-publish.yml`：推送 Docker Hub

   ```bash
   git tag {TAG_PREFIX}{version}
   git push {REMOTE} {TAG_PREFIX}{version}
   ```

   若 tag 已存在：中止并给出删除指令（仅在确认该 tag 未用于错误发布时）。

4. 提示用户到 Actions 确认 `Release` 与 `Docker Publish` 通过。

### 步骤 7 — 删除 release 分支并同步 develop

1. 删除远程与本地 release 分支：
   ```bash
   git push {REMOTE} --delete {RELEASE_BRANCH_PREFIX}{version}
   git branch -D {RELEASE_BRANCH_PREFIX}{version}
   ```
   删除失败则警告（非致命），提示手动删除。

2. 若 `main` 与 `develop` 有差异（merge commit 或仅在 main 上的修复），创建同步 PR：
   ```bash
   gh pr create \
     --base {INTEGRATION_BRANCH} \
     --head {TARGET_BRANCH} \
     --title "chore: sync main into develop after {version}" \
     --body "Post-release sync so develop contains the shipped main tip."
   ```
   若已快进无差异，跳过并说明。

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
| 步骤 6 在未合入时打 tag | **禁止** — 硬红线 |
| 步骤 6 tag 已存在 | 中止并给出删除指令 |
| 步骤 6 tag 推送成功但 Action 失败 | 非致命：提示到 Actions Re-run |
| 步骤 7 删分支或 sync PR 失败 | 警告并给出手动命令 |

## 红线规则

**绝不：**
- 在 release / feature 分支上、于合入 `main` **之前**推送生产 `v*` tag
- 在推送 tag 前直接上传 PyPI（发布由 GitHub Action 负责）
- 将 `develop` 直接 push / merge 进 `main`（必须走 PR）
- 跳过步骤 1 的用户确认
- 跳过步骤 3 的 CHANGELOG 确认
- 在任何步骤失败后继续执行（步骤 7 的清理/同步警告除外）
- 流程结束后让用户留在 release 分支
- 保留已发完的 `release/*` 作为长期分支

**始终：**
- 从最新 `{REMOTE}/{INTEGRATION_BRANCH}` 切 release
- 先合入 `{TARGET_BRANCH}`，再在 main tip 打 tag
- 发版后删除 `release/*`，并在需要时同步回 `develop`
- 中止前展示完整错误输出
- 插入新版本条目后保持 `[Unreleased]` 为空
- 推送 tag 后提示用户关注 GitHub Actions 的发布结果
