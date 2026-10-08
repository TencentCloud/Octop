---
name: publish
description: >-
  Publish the Octop Python package: cut a release branch from develop, bump
  version, update CHANGELOG, open a PR to main; after merge, Actions tag on
  main (PyPI / Docker Hub + GHCR) and sync main into develop. Use when the user asks
  to publish, release, bump version, cut a release, or run /publish.
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
| `README_GLOB` | `README*.md` | 含 shields.io 版本徽标的 README（含多语言变体，如 `README.md`、`README_CN.md`）；全部同步升级 |
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

**4b. 升级版本号（把旧号 X.Y.Z 全部换成当前号 A.B.C）：**

表示「当前发布版本」的钉死号必须一致，**不得只改 `pyproject.toml`**。
把旧版本 `X.Y.Z` 换成目标版本 `A.B.C`。缺文件则提示并继续（不中止）。

必改清单（按顺序，用 Edit 工具精确替换，勿用会误伤 CHANGELOG 历史条目的全局 replace）：

1. `VERSION_FILE`（`pyproject.toml`）— wheel / PyPI 的唯一版本源：
   ```bash
   grep -n '^\s*version\s*=\s*"[^"]+"' pyproject.toml
   # "X.Y.Z" → "A.B.C"
   ```
2. 所有匹配 `README_GLOB` 且含 shields.io 版本徽标的 README（含多语言）：
   ```bash
   grep -l 'shields.io/badge/version-' README.md README_*.md 2>/dev/null
   grep -n 'shields.io/badge/version-' {file}
   # `version-X.Y.Z-orange` → `version-A.B.C-orange`
   ```
   当前仓库至少包括 `README.md` 与 `README_CN.md`。全部未命中则提示并继续。
3. `INIT_VERSION_FILE`（`src/octop/__init__.py`）— 运行时常量 `__version__`：
   ```bash
   grep -n '__version__' src/octop/__init__.py
   # `__version__ = "X.Y.Z"` → `"A.B.C"`
   ```
4. 飞牛 FnOS 两个 manifest 的 `version=`（`scripts/build-fpk.sh` 打包时会再注入，但仓库源文件必须先改）：
   ```bash
   grep -n '^version=' fnos/docker/manifest fnos/native/manifest
   # `version=X.Y.Z` → `version=A.B.C`（两个文件都要改）
   ```
5. 飞牛 Docker compose 镜像标签（与本包版本相同，供 FPK 拉取 GHCR）：
   ```bash
   grep -n 'ghcr.io/tencentcloud/octop:' fnos/docker/app/docker/docker-compose.yaml
   # `ghcr.io/tencentcloud/octop:X.Y.Z` → `:A.B.C`
   # 不得改成 `:latest`（测试禁止 latest）
   ```
6. `uv.lock` 里可编辑包 `octop` 的版本（漏改会导致 lock 与 pyproject 不一致）：
   ```bash
   grep -n -A2 'name = "octop"' uv.lock | head -5
   # 将该包的 `version = "X.Y.Z"` 改为 `"A.B.C"`
   # 或在改完 pyproject.toml 后执行 `uv lock`，只接受 octop 版本行变化
   ```

**扫尾（必做）：** 全库搜索旧号，把漏网的「当前版本钉死」一并改掉：

```bash
git grep -n --fixed-strings "X.Y.Z"
```

对每一处命中：

| 类型 | 处理 |
|------|------|
| 当前版本钉死（compose / badge / manifest / lock / `__version__` / 文档里「当前版本」） | 换成 `A.B.C` |
| 测试里断言「等于当前发布号」的硬编码 | 改成读 `_pyproject_version()`（或同步为 `A.B.C`） |
| `CHANGELOG.md` 已发布章节（`## [X.Y.Z]` 及正文） | **保留**，不要改历史 |
| 测试夹具里拿旧号做比较（如 `1.0.2b4` vs `1.0.2b5`、解析示例） | **保留** |
| workflow / 注释里的示例旧号（如 `0.9.28`） | **保留**（不是当前钉死） |

提交前再扫必改清单，必须已经没有旧号：

```bash
git grep -n --fixed-strings "X.Y.Z" -- \
  pyproject.toml src/octop/__init__.py \
  README.md README_CN.md \
  fnos/docker/manifest fnos/native/manifest \
  fnos/docker/app/docker/docker-compose.yaml \
  uv.lock
```

任一文件仍命中旧号：**补改后再提交**，不得带着半套版本号推 release。

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
- [ ] After merge, GitHub Action auto-pushes v{version} tag on main tip
EOF
)"
```

- 成功时展示 PR URL，并明确告知：
  - 合并前不要手动打 tag；
  - 合并后会自动发版（自动打 tag）。
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
   - 若 tag 已存在，Action 会跳过并输出日志。

3. 提示用户到 Actions 确认：
   - `Auto Tag On Release Merge` 成功；
   - `Release` 与 `Docker Publish` 随 `v*` tag 触发并通过；
   - `Sync Main Into Develop` 在 GitHub Release 发布后把 `main` 同步回 `develop`。

### 步骤 7 — 删除 release 分支；develop 由 Action 同步

1. 删除远程与本地 release 分支：
   ```bash
   git push {REMOTE} --delete {RELEASE_BRANCH_PREFIX}{version}
   git branch -D {RELEASE_BRANCH_PREFIX}{version}
   ```
   删除失败则警告（非致命），提示手动删除。

2. **develop 同步**：GitHub Release 发布成功后，`sync-main-to-develop.yml` 会自动开 `main → develop` PR，并在无冲突时用 **merge commit** 合入。
   - 若已快进无差异，Action 会跳过。
   - 若有冲突或分支保护拦截，Action 留下 PR 并告警，需人工处理。
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
- 先合入 `{TARGET_BRANCH}`，再由 Action 在 main tip 打 tag
- 发版后删除 `release/*`；`main → develop` 由 `sync-main-to-develop.yml` 自动同步（失败时再手动补）
- 中止前展示完整错误输出
- 插入新版本条目后保持 `[Unreleased]` 为空
- 把旧版本号 `X.Y.Z` 换成 `A.B.C`：`pyproject.toml`、`__version__`、多语言 README 徽标、`fnos/*/manifest`、`fnos/docker/app/docker/docker-compose.yaml` 镜像标签、`uv.lock` 的 octop 包版本；提交前 `git grep` 必改清单确认无旧号
- 勿改 CHANGELOG 历史章节、测试夹具里的旧版本比较、workflow 示例号
- 推送 tag 后提示用户关注 GitHub Actions 的发布结果
