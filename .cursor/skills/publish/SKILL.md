---
name: publish
description: >-
  Publish the Octop Python package: create a release branch, bump version,
  update CHANGELOG, push tag (triggers GitHub Actions for PyPI / Docker Hub),
  and open a PR to main. Use when the user asks to publish, release, bump
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
| `TAG_PREFIX` | ``（空） | Git tag 前缀，设为 `v` 则生成 `v0.1.14` 风格标签 |
| `REMOTE` | `origin` | Git 远程仓库名 |
| `TARGET_BRANCH` | `main` | 合并请求的目标分支 |
| `RELEASE_BRANCH_PREFIX` | `release/` | release 分支名前缀 |

## 调用方式

```
/publish 0.1.14
```

目标版本号是唯一必填参数，其余均从配置或自动检测获取。

## 发布流程

### 步骤 1 — 读取配置并确认版本

1. 获取仓库根目录：`git rev-parse --show-toplevel`
2. 从 `VERSION_FILE` 读取当前版本：
   ```bash
   grep -E '^\s*version\s*=\s*"[^"]+"' pyproject.toml
   ```
3. 检查未提交的更改：
   ```bash
   git status --short
   ```
   如果存在未提交的更改，它们将被包含在步骤 4 的发布提交中。这是有意为之 — 所有待处理的工作随版本一起发布。
4. 查找最近的 git tag：
   ```bash
   git tag --sort=-creatordate | head -1
   ```
   如果没有 tag，视为首次发布（在步骤 3 中使用从仓库初始到 HEAD 的所有提交）。
5. 展示确认信息：

```
当前版本 (pyproject.toml): X.Y.Z
目标版本:                   A.B.C
上次发布 tag:               X.Y.Z (YYYY-MM-DD)
Release 分支:               release/A.B.C
目标分支 (PR):              main

确认发布 X.Y.Z → A.B.C？[y/N]
```

如果用户未输入 `y` 确认，立即中止。

### 步骤 2 — 创建 release 分支

从当前 HEAD 创建并切换到新的 release 分支：

```bash
git checkout -b {RELEASE_BRANCH_PREFIX}{version}
```

如果分支已存在，中止：
```
✗ 分支 {RELEASE_BRANCH_PREFIX}{version} 已存在。
请手动删除：git branch -D {RELEASE_BRANCH_PREFIX}{version}
然后重新运行 /publish。
```

### 步骤 3 — 分析变更并生成 CHANGELOG 草稿

1. 获取上次 tag 以来的提交：
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

检查工作树状态：
```bash
git status --short
```

- 如果有更改（已暂存或未暂存）：暂存所有文件并提交：
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

### 步骤 5 — 打 tag 并推送（触发 GitHub Action 发布）

推送 tag 到远程后，**GitHub Actions 会自动完成发布**，本步骤**不再直接上传 PyPI**：

- `release.yml` 的 `build` job 执行 `make build`（重建前端 + 生成 `README.pypi.md` + 打 wheel），随后 `publish` job 用 `PYPI_API_TOKEN` secret 上传 PyPI；
- `docker-publish.yml` 构建并推送镜像到 Docker Hub；
- `github-release` job 用 CHANGELOG 生成 GitHub Release。

```bash
git tag {TAG_PREFIX}{version}
git push {REMOTE} {TAG_PREFIX}{version}
```

如果 `git tag` 因 tag 已存在而失败：
```
✗ Tag {TAG_PREFIX}{version} 已存在。
请手动删除：git tag -d {TAG_PREFIX}{version}
然后重新运行 /publish 从此步骤重试。
```
中止。

推送成功后，提示用户到仓库 Actions 页面确认 `Release` 与 `Docker Publish` 两个工作流均通过（失败可在对应 run 上 Re-run jobs，无需重新打 tag）。

### 步骤 6 — 创建合并请求（GitHub）

使用 `gh` CLI 从 release 分支创建到 `TARGET_BRANCH` 的 Pull Request：

```bash
gh pr create \
  --base {TARGET_BRANCH} \
  --head {RELEASE_BRANCH_PREFIX}{version} \
  --title "chore: release {version}" \
  --body "$(cat <<'EOF'
{步骤 3 生成的 CHANGELOG 条目}
EOF
)"
```

- 若 `gh` 未登录或命令失败，展示警告（非致命 — tag 已推送，发布将由 GitHub Action 完成），并提示手动创建 PR：
  ```
  ⚠ tag 已推送、发布将由 GitHub Action 完成，但 Pull Request 创建失败（可能 gh 未登录）。
  请手动创建 PR：{RELEASE_BRANCH_PREFIX}{version} → {TARGET_BRANCH}
  ```
- 成功时展示 PR URL：
  ```
  ✓ 已推送 tag {TAG_PREFIX}{version} 到 {REMOTE}（PyPI / Docker 由 GitHub Action 自动发布）
  ✓ 已创建 Pull Request：{RELEASE_BRANCH_PREFIX}{version} → {TARGET_BRANCH}
    链接：{pr_url}
  ```

### 步骤 7 — 切回原分支

返回创建 release 分支之前所在的分支：

```bash
git checkout {original_branch}
```

确保流程结束后用户不会停留在 release 分支上。

## 错误处理参考

| 场景 | 行为 |
|------|------|
| `VERSION_FILE` 未找到 | 中止："找不到 VERSION_FILE：{path}" |
| 文件中未匹配到版本号 | 中止："在 {VERSION_FILE} 中找不到匹配 {VERSION_PATTERN} 的版本行" |
| 没有 git tag（首次发布） | 使用从仓库初始到 HEAD 的所有提交；提示"首次发布 — 使用完整 git 历史" |
| 上次 tag 以来无提交 | 警告并询问是否继续 |
| Release 分支已存在 | 中止并给出删除指令 |
| 步骤 4 推送失败 | 中止：文件已在本地更新但未推送 |
| 步骤 5 tag 已存在 | 中止并给出删除指令 |
| 步骤 5 tag 推送成功但 GitHub Action 发布失败 | 非致命：提示用户到 Actions 页面查看失败日志并 Re-run 对应 job（无需重新打 tag） |
| 步骤 6 PR 创建失败 | 仅警告（tag 已推送，发布将由 GitHub Action 完成） |

## 红线规则

**绝不：**
- 在推送 tag 前直接上传 PyPI（发布由 GitHub Action 负责）
- 跳过步骤 1 的用户确认
- 跳过步骤 3 的 CHANGELOG 确认
- 在任何步骤失败后继续执行（步骤 6 PR 失败除外）
- 流程结束后让用户留在 release 分支

**始终：**
- 任何失败立即中止（步骤 6 PR 失败除外）
- 中止前展示完整错误输出
- 插入新版本条目后保持 `[Unreleased]` 为空
- 流程结束时切回原分支
- 推送 tag 后提示用户关注 GitHub Actions 的发布结果
