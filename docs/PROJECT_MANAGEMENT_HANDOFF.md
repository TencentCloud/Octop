# Octop 项目管理能力开发 — 换机交接文档

> 目的：在一台**全新的电脑**上读完本文即可继续开发，无需回溯任何历史对话。
> 生成时间：2026-09-27 · 分支 `feature/projects-p0` · 基线 `upstream/develop`

---

## 0. 先读这一节（30 秒）

你接手的是一份**已经在 fork 上、已有 13 个提交、可运行、门禁全绿**的工作，不是从零开始。

新机器上你要做的三件事：

1. 按 **§2** 装环境（约 30–45 分钟，其中 PostgreSQL 与 `npm ci` 最慢）。
2. 按 **§2.7** 跑自检，确认 `make all` 绿。
3. 按 **§5** 继续做未完成的 M1 收尾任务（T3.2 / T3.3 / T3.4 / T3.5 / S0 / T2.6）。

**最需要你先知道的三件事**（否则一定踩坑）：

| # | 事实 | 后果 |
|---|---|---|
| 1 | 分支基线是 **`develop`**，不是 `main` | `main` 依赖闭源的 `orcakit-harness-agent`，装不上、跑不起来 |
| 2 | 迁移号 **018 已被上游永久占用** | 你下一个迁移号必须从 **020** 开始，用 018 会让整个数据库无法启动 |
| 3 | **绝对不要并发跑两个 `make all`** | 它会对全树执行 `ruff format`，并发会互相覆盖文件，并产生假测试失败（本次开发真实发生过） |

---

## 1. 仓库与远端

| 项 | 值 |
|---|---|
| 工作仓库根（旧机） | `D:\nancc\octop\Octop-develop` |
| 工作区根（旧机） | `D:\nancc\octop`（**注意：不是仓库根，两者不同**） |
| 当前分支 | `feature/projects-p0` |
| 远端 `origin` | `git@github.com:yzzgchina/Octop.git`（你的 fork，**推送目标**） |
| 远端 `upstream` | `https://github.com/TencentCloud/Octop.git`（**只读**，push 已用 `pushurl DISABLED` 关掉） |
| 上游基线 | `upstream/develop` |

### 1.1 上游同步纪律

```powershell
git fetch upstream
git rev-list --left-right --count upstream/develop...HEAD   # 输出「落后 领先」
```

规则：

- **只从 `develop` 分支开发**（AGENTS.md §10）。`release/*` 发布后会删除，不要基于它开发。
- **不要合并 `release/1.0.2b3`**。它只是 `develop` + 一个改版本号的提交（CHANGELOG/README/pyproject/`__init__.py`），**零代码差异**，合并它是纯粹的噪音。
- 上游若前进了，rebase 到 `upstream/develop`，然后**重点检查迁移号冲突**（见 §7.3）。

### 1.2 推送与网络

- 推送走 SSH：`git push origin feature/projects-p0`，已注册 deploy key，无需密码。
- 旧机器上 `github.com` 的 HTTPS 被 **SNI 阻断**，HTTPS 需要代理 `http://127.0.0.1:65532`。新机器如果 SSH 通就用 SSH，不要配 HTTPS 代理。
- 若先 rebase 过，推送需要 `git push --force-with-lease origin feature/projects-p0`。

> ⚠️ 安全提醒：早期对话中出现过一个 GitHub 密码（明文粘贴）。它从未被使用，但**请务必到 GitHub 设置里轮换该密码**，并确认账号已开启 SSH/PAT 而非密码认证。

---

## 2. 新机器环境搭建

### 2.1 必备工具

| 工具 | 版本（旧机实测） | 说明 |
|---|---|---|
| **uv** | 最新 | 管理 Python 3.12 虚拟环境与依赖，**不要用系统 pip** |
| **Python** | 3.12 | 由 uv 自动下载，无需手装 |
| **Node.js** | 22.23.2 | 前端构建 |
| **git** | 任意近期版本 | |
| **make** | ezwinports.make | Windows 上没有自带 make，用 `winget install ezwinports.make` |
| **PostgreSQL** | 17 | M2 设计上控制面与记忆都要 PG；测试也需要 |

CPU 建议 ≥ 8 核：测试用 `-n auto`（xdist），旧机 14 worker。

### 2.2 克隆

```powershell
cd D:\nancc            # 或你的工作目录
git clone -b feature/projects-p0 git@github.com:yzzgchina/Octop.git Octop-develop
cd Octop-develop
git remote add upstream https://github.com/TencentCloud/Octop.git
git config core.autocrlf false      # ★ 必做，见 §7.1
```

如果只 clone 了 `develop`：

```powershell
git fetch origin feature/projects-p0
git checkout feature/projects-p0
```

### 2.3 `dev-env.ps1`（★ 必须重建）

旧机上的 `D:\nancc\octop\dev-env.ps1` **不在仓库里**（它是本地文件），新机器要重新创建。**每条需要 git/uv/make/node 的命令前都要先 dot-source 它**：

```powershell
. D:\nancc\octop\dev-env.ps1
```

它的作用（缺一样都会失败）：

1. 把 `C:\Program Files\Git\usr\bin` 加到 PATH 最前 —— **Makefile 需要一个 Unix shell**，否则报 `process_begin: CreateProcess(NULL, pwd, ...) failed`。
2. 设 `PYTHONUTF8=1` —— **中文 Windows 必做**，否则 `tests/unit/db` 会有 18 个 `UnicodeDecodeError: 'gbk' ... 0x92`。建议同时永久写进用户环境变量。
3. 设 `OCTOP_TEST_DATABASE_URL=postgresql://octop:octop_dev_pw@127.0.0.1:5432/octop` —— 让 `-m postgresql` 的测试真正跑起来而不是 skip。
4. 打印一段自检（git/make/uv/node/psql/pg_dump 是否找得到、PG 是否在监听、当前分支与 dirty 数）。

> ★★ **写这个文件时必须存成「UTF-8 带 BOM」**。PowerShell 5.1 会把无 BOM 的 `.ps1` 按 GBK 读，文件里的中文注释会让脚本直接解析失败。写入方式：
> ```powershell
> [System.IO.File]::WriteAllText('D:\nancc\octop\dev-env.ps1', $content, (New-Object System.Text.UTF8Encoding($true)))
> ```
> 注意这里是 `$true`（**带** BOM）。同样的坑在 `~/.ssh/config` 上反向踩过：那个文件必须**不带** BOM，否则 OpenSSH 报 `no argument after keyword "\357\277\277"`。

### 2.4 PostgreSQL

二选一：

**A. Docker（旧机用的这个）**

```powershell
docker run -d --name octop-pg --restart unless-stopped `
  -e POSTGRES_USER=octop -e POSTGRES_PASSWORD=octop_dev_pw -e POSTGRES_DB=octop `
  -p 5432:5432 postgres:17
```

**B. 本地安装**：EDB 的 Windows 二进制包解压即用，旧机放在 `D:\nancc\tools\pgsql`。

连接串：`postgresql://octop:octop_dev_pw@127.0.0.1:5432/octop`

### 2.5 安装依赖

```powershell
cd D:\nancc\octop\Octop-develop
. ..\dev-env.ps1
make install            # uv sync，建 .venv
make install-hooks      # 装 pre-commit（见 §7.8，它很慢）
cd dashboard; npm ci    # ★ 必须，否则 make all 会在 prettier 阶段失败
```

> `npm ci` 约 1066 个包，旧机装了挺久。**不装的话 `make all` 会在 `format-frontend` 阶段报 prettier 找不到。**

### 2.6 前端构建（本地起服务才需要）

```powershell
cd dashboard; npm run build     # 产物进 src/octop/dashboard/
```

> `dashboard/` 是**源码**，`src/octop/dashboard/` 是**构建产物**（已被前端流程覆盖写入）。**永远不要手改 `src/octop/dashboard/` 里的文件**，改了会在下次构建时被冲掉。

### 2.7 首次自检（必跑）

```powershell
. D:\nancc\octop\dev-env.ps1
cd D:\nancc\octop\Octop-develop
make all                       # 约 4–8 分钟，无输出则在跑，别以为卡死
```

期望：`format-all` / `lint` / `typecheck` / `test` 四段全过，测试在 3900+ passed 量级。

若只想验证前端类型：

```powershell
cd dashboard; npx tsc -b
```

---

## 3. 当前进度

### 3.1 已提交并推送的基线（`feature/projects-p0`，相对 `upstream/develop` 领先 13 个提交）

| 提交 | 内容 |
|---|---|
| `7858e1b5` | 项目域迁移（`019_projects.{sql,pg.sql}`，10 张表） |
| `3d7c3b79` | repo 层：`repos/projects.py`、`repos/project_tasks.py` |
| `2f07aaa6` | `ProjectService`：KB 生命周期 + 项目状态机 + §4.6 权限矩阵 |
| `c3ac257c` | 任务 CRUD + 任务状态机 + `timeline_events` |
| `9ef2b70d` | HTTP router + app 挂载 + 10 个项目错误码 |
| `23bc3a66` | 前端：项目列表 / 详情 / 成员管理 |
| `a8f808a8` | 修复：知识库能力不可用时仍可创建项目（`kb_id=NULL`） |
| `c7b57690` | 迁移重编号 018 → **019** |
| `b8868d50` | 看板页（状态列 + 拖拽 + 过滤） |
| `95642443` | 派单 T2.5 + 任务路由跨项目守护修复 + 枚举值 4xx |
| `cec85936` | 讨论线 T3.1（`ProjectCommentRepo` + `ProjectDiscussion`） |
| `5e37f25d` | 权限集成测试（AC-13 / AC-16） |
| `271f63ca` | 交接文档（`docs/PROJECT_MANAGEMENT_HANDOFF.md`） |

**当前 HEAD = `271f63ca`**，与 `origin/feature/projects-p0` 完全一致（0/0），相对 `upstream/develop` **领先 13 个提交、落后 0**。

**规模**：相对 `upstream/develop`，50 个文件、约 +6611 / −277 行。

### 3.2 本次交接批次（T2.5 派单 + T3.1 讨论线 + 权限测试 + 路由修复）

本批次在原本的 9 个提交之上新增，**涵盖**：

| 能力 | 主要文件 |
|---|---|
| **派单 T2.5** | `infra/projects/dispatch.py`（`split_acceptance` / `build_dispatch_prompt` / `require_dispatchable` / `_TeamRoomBridge` / `run_dispatch_turn`） |
| **cron 复用改造** | `infra/cron/delivery.py`：私有 `_build_agent_request` 提取为模块级 `build_agent_turn_request` + 新增 `run_agent_turn`（**是提取，不是重写**） |
| **讨论线 T3.1** | `infra/projects/discussion.py`（`ProjectDiscussion`）、`repos/project_content.py`（`ProjectCommentRepo`） |
| **权限集成测试** | `tests/integration/test_projects_api.py`（AC-13 / AC-16，10 用例） |
| **路由守护修复** | `infra/projects/service.py::_require_task(project_id, task_id)` |
| 测试 | `test_project_dispatch.py`、`test_project_discussion.py`、`test_project_route_guards.py` |

> **本批次权威门禁**（交付前最后一次 `make all`）：
> `All checks passed!`（ruff check）· `1096 files already formatted` · `Success: no issues found in 538 source files`（mypy strict）· 测试 **3897 passed / 1 failed / 111 skipped**。
> 那 1 个失败是 `tests/unit/gateway/test_versioned_history.py::test_process_exit_after_commit_keeps_last_fragment`，**单独重跑 `1 passed in 25.84s`** —— 高负载下的 flaky，与项目域无关（另一个代理在低负载下单跑 `make all` 得到 3898 passed / 0 failed，exit 0）。

### 3.4 ★ 本批次明确「未验证」的部分（新机器上优先补）

派单（T2.5）的**代码路径全部通过单测，但真实 LLM 回合从未执行过**。当时的机器上**没有配置 LLM provider**，所以 `agent_manager.stream(...)` 全程走的是 `_StubAgentManager`。以下四点没有被证明：

| # | 未验证项 | 影响 |
|---|---|---|
| 1 | 真实 agent 回合从未跑过（无 provider、无已配置专家） | 派单能否真的驱动一次专家执行，未知 |
| 2 | **步骤 ④ 团队房间端到端**：团队宿主是否真的起回合、其 `ask_agent(async)` 是否真的开房间并把成员发言扇回来 | 只断言了 `stamp_host_runtime` 被调用，**行为未证** |
| 3 | `run_agent_turn` 的 HITL / 空回复 `RuntimeError` 分支，项目路径未覆盖（cron 路径有既有测试） | 只覆盖了通用回合失败 |
| 4 | 无 HTTP 冒烟测试：`:8088` 上跑的是**改动前**的代码，从未用新代码重启过 | 路由存在性有 `route.matches()` 证明，但没有真实请求 |

> 这四点写在 `dispatch.py` 的模块 docstring 和 `test_project_dispatch.py` 的文件 docstring 里，不是口头约定。
> **新机器上如果配好 provider，第一件事就是跑 `_tools/verify_dispatch_e2e.py` 把这四点补上。**

### 3.5 已知遗留缺陷 + 已知既有测试 flake（★ 避免新机器上重复排查）

**遗留缺陷（与本批次刚修的问题同族，刻意未修，需要你先决策）**

1. **建任务时 `parent_id` / `thread_id` 仍会返回 500。**
   `POST /projects/{id}/tasks` 若 `parent_id` 指向**别的项目**的任务、或 `thread_id` 不存在，`repos/project_tasks.py` 里 `_assert_parent_ok` / `_assert_thread_exists` 抛出的 `ValueError` 会直接冒到 `app.py:95` 的兜底处理器，变成 **HTTP 500**，而不是 4xx。
   这与本批次刚修的「非法枚举值 → 500」是**同一族问题**。当时未修的原因是**没有语义完全贴合的 `PROJECT_*` 错误码** —— 这是需要你拍板的语义决策，不是纯技术活。
   建议方向：`parent_id` 跨项目或不存在 → `PROJECT_TASK_NOT_FOUND`(404)；`thread_id` 不存在 → 复用 404 或新增一个码。

**已知既有测试 flake（★ 全部与项目域无关，不要追）**

本机高负载时（`-n auto`，14 worker）会出现下列失败，**全部单跑通过，且没有一个是项目域引起的**：

| 失败用例 | 真实原因 |
|---|---|
| `tests/unit/gateway/test_versioned_history.py::test_process_exit_after_commit_keeps_last_fragment` | 子进程 helper 在 14 路负载下 `subprocess.TimeoutExpired(20s)`；单跑 `1 passed in 25.84s` |
| `tests/unit/cli/test_chats_cmd.py::test_chats_list_uses_offline_db` 与 `::test_chats_update_sends_title` | **同 worker 测试污染**：`::test_chats_list_requires_agent` 会把 `octop.cli.support.ctx.require_agent` monkeypatch 成桩（回显 `error: --agent is required`）。xdist 把它与这两个用例分到同一 worker 就串味。**只跑 `tests/unit/cli -n auto` 也能复现**（`1 failed, 92 passed, 9 skipped`），是**既有 bug**，与项目管理代码无关 |
| `tests/unit/auth/test_captcha_verify.py::test_mocked_success_passes`、`tests/integration/test_captcha_api.py::test_strong_login_mocked_ok_token_returns_jwt` | 高负载 flake，单跑通过 |
| `tests/integration/test_postgresql_control_plane.py::test_pg_knowledge_base_max_documents_schema_and_crud` | **测试库并行竞争**：另一个 worker 的 `_reset_public_schema` 把共享 `OCTOP_TEST_DATABASE_URL` 库里的表 DROP 了，报 `psycopg UndefinedTable`。单跑 `1 passed in 3.16s` |

> **分块跑全量的结果**（与 `make test` 收集到同一批 4009 项）：
>
> - `uv run pytest tests/unit -n auto -m "not live" -q` → **3 failed, 3336 passed, 101 skipped**（连跑两轮结果一致）
> - `uv run pytest tests/integration -n auto -m "not live" -q` → **1 failed, 558 passed, 10 skipped**
> - 3440 + 569 = 4009
>
> **所有失败都是上表这几条环境 flake，没有任何一条与项目域相关。** 另：之前怀疑的 `test_sse_catchup_refreshes_same_seq_tool_after_history` 在多轮运行中**从未真的失败过**。

### 3.3 已验证项（来自开发期间的真实运行）

| 检查 | 结果 |
|---|---|
| `uv run pytest tests/unit/projects tests/unit/api tests/unit/cron tests/unit/db -q` | **698 passed, 11 skipped** |
| `uv run pytest tests/unit/projects -q` | **102 passed** |
| `uv run pytest tests/integration/test_projects_api.py -q` | **10 passed** |
| `uv run ruff check src tests` | **All checks passed!** |
| `uv run ruff format --check src tests` | **1096 files already formatted** |
| `uv run mypy src/octop`（strict） | **Success: no issues found in 538 source files** |
| `make all` | 见 §3.1 各提交提交信息（3852 passed / 111 skipped 量级） |

---

## 4. 已完成能力对照验收标准

| AC | 内容 | 状态 | 证据 / 位置 |
|---|---|---|---|
| **AC-03** | 任务独立讨论线，发言不污染其他任务 | ✅ 完成 | `tests/unit/projects/test_project_discussion.py`（两任务各 3 条互不串线 + 计数 + 项目级行不落入任务行） |
| **AC-04** | 每条评论有作者 + 时间；专家产出落入任务讨论线 | ✅ 完成 | 同上（`author_type`/`author_id`/`created_at`/`updated_at`；agent 行 `source='agent'`） |
| **AC-09** | 派工消息含任务标题 / 描述 / 验收标准 | ⚠️ 代码完成，端到端未验 | `dispatch.py::build_dispatch_prompt` + `split_acceptance`；需对真实运行实例跑一次 |
| **AC-13** | 非成员访问项目数据一律拒绝 | ✅ 完成 | `tests/integration/test_projects_api.py`（非成员对 5 类资源 × 4 方法全 403） |
| **AC-16** | 项目 A 的共享专家不可被项目 B 未授权访问 | ✅ 完成 | 同上 |
| AC-05 / AC-06 | 打标入池 / 撤销留痕 | ⬜ 未做 | 属 T3.2 |
| AC-07 | 未确认节点无「生成任务」路径 | ⬜ 未做 | 属 T3.2（API 半边）+ T3.3（UI 半边） |
| AC-08 | 草案 → Owner 确认 → 生成 N 个任务，可追溯 | ⬜ 未做 | 属 T3.2 + T3.3 |
| AC-10 | 任务转 done 时产出入项目 KB，可跳回 | ⬜ 未做 | 属 T3.4 |
| AC-12 | 任务时间线完整有序（不含记忆变更事件） | ⬜ 未做 | 属 T3.5 |
| AC-14 | 搜产出关键句 30s 内命中 | ⬜ 未做 | 人工验收，属 T3.4 之后 |

---

## 5. 未完成的工作 + 下一步

### 5.1 剩余 M1 任务（这是你的下一步）

| 任务 | 内容 | 依赖 | 关键产出 |
|---|---|---|---|
| **T3.2** | 需求节点池 + 打标 + Leader 草案落库 | — | `infra/projects/nodes.py`、`repos/project_nodes.py` |
| **T3.3a** | Owner 确认闸门（领域层） | T3.2 | `infra/projects/approval.py` |
| **T3.3b** | 需求池前端页 + 路由/i18n 登记 | T3.3a、S0、T2.6 | `pages/Projects/Detail/RequirementPool.tsx` |
| **T3.4** | 资料归档进项目 KB | — | 扩展 `infra/projects/service.py` |
| **T3.5** | 时间线回放接口 | — | 扩展 `infra/projects/service.py` |
| **S0** | 聊天列表改造（T0.1–T0.4） | — | `api/routers/chat/sessions.py`、`pages/Chat/components/SessionList.tsx`、`hooks/useSessionInbox.ts` |
| **T2.6** | 会话列表项目分组 +「项目会话」标签 | S0 | 扩展 `useSessionInbox` |
| **收口** | 把上述能力挂成 HTTP 端点 + i18n + ACL 门禁 | T3.2/T3.3a/T3.4/T3.5 | `api/routers/projects.py` |

> **注意 T2.6 曾被我误判为「现在就能做」**。它的前置是 **S0**（会话列表改造），而 S0 一直没做。所以 S0 必须先做，T2.6 才能开始。

### 5.2 并行化的正确姿势（重要，别再踩坑）

这批任务的**共享热点只有一个**：`src/octop/api/routers/projects.py`。除此之外还有两个单点：

- `src/octop/infra/projects/service.py` —— T3.4 与 T3.5 都要改它，**必须串行或同一人做**。
- `dashboard/src/locales/{en,zh}.json` —— S0、T2.6、T3.3b 都要改它，**必须串行**。

推荐 DAG（这是我在本机上设计并被任务板校验过的版本）：

```
T3.2 需求节点 ──┬─→ T3.3a Owner闸门 ──┬─→ 收口（路由/i18n/ACL）──┐
T3.4+T3.5 归档/时间线 ────────────────┘                          ├─→ 评审
S0 聊天列表 ──→ T2.6 项目分组 ──────────→ T3.3b 需求池前端页 ─────┘
```

**分工原则**：

1. 一个文件只能有一个写者。`api/routers/projects.py` 交给单独一人（集成者）收口。
2. `service.py` 交给单独一人（T3.4+T3.5 一起做）。
3. `dashboard/src/locales/*.json` 按 S0 → T2.6 → T3.3b 顺序串行。
4. **禁止成员并发跑 `make all`**（全树 `ruff format`）。成员只跑自己范围内的 scoped 测试，全量门禁由你统一跑。

### 5.3 已归档的团队计划

开发后期我建过一个 AgentTeams 团队（`octop-m1-closeout`，6 成员 / 8 任务）来并行做 §5.1，**已按你的要求停止并归档**，未启动任何工作。成员与任务定义见上表和 §5.2 的 DAG，可直接重建。

重建时的两个已知约束：

- 任务板**强制 inScope 互斥**（比"建议"更强）。`dashboard/src/locales/*.json` 的冲突就是因此被挡下并促成了 T3.3 拆成 a/b 两半。
- 成员**必须显式指定模型**：默认继承会话模型别名会失败（provider 上不存在），实测可用值为 `deepseek-flash` / `deepseek-v4-pro`。建议实现者用前者、评审者用后者。

---

## 6. 架构与约定速查

### 6.1 六项已锁定决策

| # | 决策 |
|---|---|
| D1 | fork 基于 **`develop`** 分支 |
| D2 | 项目记忆用 **A 方案**：一个项目一个命名空间 |
| D3 | 记忆后端用 **PostgreSQL** |
| D4 | 控制面用 **PostgreSQL** |
| D5 | 跨团队交互**按项目隔离**（项目作用域） |
| D6 | 团队工具：知识库 1 行解锁；connectors/ACP 走新的「项目房间宿主」角色 |

### 6.2 分层

```
src/octop/api/routers/projects.py     HTTP 层（Pydantic 模型、错误码映射）
src/octop/infra/projects/             领域层
    service.py        ProjectService：权限矩阵、项目/任务状态机、KB 生命周期
    dispatch.py       派单：prompt 构造 + TeamRoom 桥
    discussion.py     ProjectDiscussion：讨论线（权限全部委托 ProjectService）
src/octop/infra/db/repos/             SQL 层（仅 SQL，无业务规则）
    projects.py / project_tasks.py / project_content.py
src/octop/infra/db/migrations/        019_projects.{sql,pg.sql}
dashboard/src/pages/Projects/         前端页面（源码）
```

### 6.3 关键约定

**资源表**（★ 全项目统一）：

```sql
id          INTEGER PRIMARY KEY,     -- 内部代理键
{entity}_id TEXT UNIQUE NOT NULL     -- 对外 id，外键与调用方都用它
```

子表用**字符串 id** 作外键。`users` 表是唯一例外。

**迁移**：

- 一对文件：`NNN_x.sql`（SQLite）+ `NNN_x.pg.sql`（PostgreSQL）。
- 末尾必须有 `UPDATE _schema_version SET version = N;`。
- SQLite 走 `migrate.py` 里显式的 `if version == N:` 分支；PG 直接执行 `.pg.sql` 文件。
- `run_migrations` 末尾会跑幂等的 `_ensure_*` 修复函数。

**权限**：`infra/projects/service.py` 是唯一权威。`PROJECT_READ / WRITE / CONFIRM / MANAGE_MEMBERS / ARCHIVE` 五级，角色→级别查 `_ROLE_LEVELS`。所有新能力都必须 `assert_project_role`，**不要另造一套判断**。

> 平台管理员但**非项目成员**也返回 403（计划 §4.6「非成员一律 403」，AC-13）。粗粒度的 `projects` 权限键只控制"能不能进这个功能"。

**时间戳**：一律 unix **秒**（INTEGER）。前端显示必须用 `formatServerDateTime(..., timeZone)` + `useServerTimezone()`，**禁止裸 `toLocaleString()`**（铁律 #13）。

**i18n**：后端 `src/octop/i18n/{en,zh}.json` 用 `{x}` 占位符；dashboard `dashboard/src/locales/{en,zh}.json` 用 `{{x}}`。**两种风格不同，且必须两个语言都补齐。**

**错误码**：`src/octop/infra/errors.py`。项目域已有 10 个：

`PROJECT_NOT_FOUND`(404)、`PROJECT_FORBIDDEN`(403)、`PROJECT_ROLE_FORBIDDEN`(403)、`PROJECT_MEMBER_INVALID`(400)、`PROJECT_STATUS_INVALID`(409)、`PROJECT_TASK_NOT_FOUND`(404)、`PROJECT_TASK_STATUS_INVALID`(409)、`PROJECT_NODE_NOT_FOUND`(404)、`PROJECT_NODE_NOT_CONFIRMED`(409)、`PROJECT_KB_BIND_FAILED`(500)。

**任务状态机**：

```
todo     → doing, blocked, cancelled
doing    → todo, review, done, blocked, cancelled
review   → doing, done, blocked, cancelled
blocked  → todo, doing, cancelled
done     → doing
cancelled→ （终态）
```

### 6.4 数据库层两个硬坑

1. **PG 代理没有 `cursor.lastrowid`**（`_PgConnectionProxy` 不实现）→ 必须用 `insert_returning_id`。
2. **`?` 占位符会被自动改写成 `%s`** —— 所以写 SQL 时统一用 `?`，两种数据库都吃。

---

## 7. 铁律与已知陷阱（★ 都是真实踩过的）

### 7.1 Git 换行符

系统 gitconfig 里 `autocrlf=true`，会让工作区变 CRLF 而 blob 是 LF，`git status` 显示几千个"假改动"。

```powershell
git config core.autocrlf false
```

两个反直觉的坑：

- `git checkout -- .` **不会**重写工作区文件。
- `git status` 会撒谎（旧机上报了 2462 个，实际只有 9 个）。修复用 `git read-tree HEAD`。
- **PowerShell 的 `>` 重定向会把 LF 转成 CRLF**，用它检查换行符会得出错误结论。要比对字节请用 `[System.IO.File]::ReadAllBytes` 或 Python 二进制管道。

### 7.2 PowerShell 5.1 的坑

- **没有 `pwsh`**，就是 5.1。
- **不支持 `&&` 和三目 `? :`**。多语句用 `;`。
- `(...)` 只能放单个表达式；**多语句必须用 `$(...)`**，否则报 `MissingEndParenthesisInExpression`。
- `Select-String` **没有 `-Recurse`**。
- `.ps1` 含中文必须存成 **UTF-8 带 BOM**（见 §2.3）。
- **`Invoke-RestMethod` 返回的 JSON 数组在管道里是「一个对象」** —— 用 `Where-Object { $_.title -like ... }` 过滤会枚举成真值数组，从而匹配到全部。旧机上因此误删过 6 个任务。**调用 API 请优先用 Python 脚本，不要用 PowerShell 管道过滤。**
- `Get-Content`/`Select-String` 读 UTF-8 中文在 5.1 下会显示乱码，但**只是显示问题**，不影响判断（不要据此以为文件坏了）。

### 7.3 迁移号 018 已被永久占用

上游 `release/1.0.2b3` 里带了 `018_user_role.{sql,pg.sql}`（`version = 18`）。我们的项目域原本也是 018，**两套 018 共存**会让 `_discover()` 抛 `RuntimeError`，**每一次数据库操作都失败**。

已重编号为 **019**。你下一个迁移号是 **020**。

> ★ 最危险的一点：两处 `if version == 18:` 分别位于 `_apply_sqlite_migration` 和 `run_migrations` **两个不同函数**里，所以 **git 自动合并时不会有冲突提示** —— 它会静默合并，然后第一个分支遮蔽第二个。rebase 后**必须**检查这个，不能只看有没有冲突。

### 7.4 中文 Windows + Python

不设 `PYTHONUTF8=1` 会有 18 个 `UnicodeDecodeError: 'gbk'` 失败。建议永久写进用户环境变量。

### 7.5 Makefile 需要 Unix shell

报 `process_begin: CreateProcess(NULL, pwd, ...) failed` 就是这个原因。把 `C:\Program Files\Git\usr\bin` 加到 PATH 最前（`dev-env.ps1` 已处理）。

### 7.6 pytest 导入冲突（曾静默吞掉 32 个测试）

`tests/unit/` 下**大部分子目录没有 `__init__.py`**（只有 `tests/integration`、`tests/support`、`tests/unit`、`tests/unit/cli` 有）。同名测试文件会撞 `import file mismatch`。

真实案例：`tests/unit/projects/test_service.py` 撞上 `tests/unit/infra/setup/test_service.py` —— **32 个新测试完全不运行**，而 `make all` 还显示 "3762 passed"。已改名为 `test_project_service.py`。

**新增测试文件时务必确认它真的在跑**（看用例数，不要只看 "passed"）。

### 7.7 并发跑门禁 = 自毁

`make all` 内部会执行 `ruff format src tests`，**它会写全树**。两个进程同时跑会互相覆盖文件。

本次开发真实后果：

- 3 个并发 `make all` + 多个 pytest 同时运行；
- 产生**假失败**：AC-13 用例报 422（实际是文件被写到一半的快照）、xdist collection race、execnet 通道被关闭；
- 一个 `make all` 跑了 19 分钟还没结束。

**纪律：同一时刻只允许一个全量门禁。** 多人/多代理协作时，成员只跑 scoped 测试。

> 另注：**pytest-xdist 会自动重启被杀的 worker**。所以"杀掉所有 pytest 进程"不但没用，还会让它无限重试（本次实测 90 秒内重生 92 个进程）。别用杀进程的方式"暂停"测试。

### 7.8 pre-commit 很慢

pre-commit 钩子里的 testmon 是**串行**跑的，约 **20 分钟**。工作流：

```powershell
make all                              # 手动全量门禁（xdist，约 4–8 分钟）
$env:SKIP_PRECOMMIT='1'
git commit -F <消息文件>
```

提交信息用文件传入，且文件要写成**无 BOM 的 UTF-8**：

```powershell
[System.IO.File]::WriteAllText('msg.txt', $msg, (New-Object System.Text.UTF8Encoding($false)))
```

### 7.9 门禁范围

`make all` = `format-all lint typecheck test`。**`lint` 只有 ruff**；dashboard 的 eslint 在单独的 `lint-all` 里。所以**前端类型检查要自己跑**：

```powershell
cd dashboard; npx tsc -b
```

### 7.10 全新安装下项目 KB 是关的

`knowledge_bases_enabled` 默认 **false**（要配 embedding 模型）。所以：**新建项目时 `kb_id` 可能是 NULL**。

`create_project` 采用 **best-effort** 策略：KB 可用就绑定（带补偿删除），不可用就建项目 + `kb_id=NULL` + 记日志。

> **开放问题（需要你决策）**：项目是否**必须**有知识库？
> 计划 T2.1 ①③ 读起来像"必需"，但 T3.4 的注记「归档只在 `kb_id IS NOT NULL` 时执行」隐含可空。当前实现是可空。
> 若要改成必需 —— 代价是**全新安装未配 embedding 前无法创建任何项目**。改 `create_project` 一处即可。

### 7.11 看板没有拖拽库

`dashboard` **不依赖任何拖拽库**。已有实现用原生 HTML5 DnD，参考 `pages/KnowledgeBases/index.tsx`、`WorkspaceDrawer.tsx`、以及本次的 `pages/Projects/Detail/Board.tsx`。

### 7.12 ★ 长任务会被作业运行器掐断（「95% 处神秘失败」的真相）

本机全量 `make all` 约 **17–19 分钟**。**作业运行器会在超时后掐掉长作业**，日志里的标志是：

```
Windows Job runner exited with exit code 4294967295 before proving its managed range empty
```

**症状**：pytest 跑到 **95%–98%** 时进程被杀，**永远不打印 `short test summary info`**。你只会看到一大片点和一个孤零零的 `F`，**却拿不到失败用例名**。

> 本次开发中反复出现的「神秘失败在 95%」就是这个原因，**不是代码问题，也不是并发问题**。

应对方式：

- **不要**试图从被截断的日志里找失败名，找不到的。
- 改为**分块跑**：
  ```powershell
  uv run pytest tests/unit -n auto -m "not live" -q
  uv run pytest tests/integration -n auto -m "not live" -q
  ```
- 或把完整输出重定向到**仓库外**的文件（`Out-File` 到 `D:\nancc\octop\`），因为缓冲输出在进程被杀时会全部丢失。

---

## 8. 常用命令速查

```powershell
# 每条命令前都要先 source
. D:\nancc\octop\dev-env.ps1
cd D:\nancc\octop\Octop-develop

make install            # uv sync
make install-hooks      # 装 pre-commit
make all                # 全量门禁
make lint-all           # 含 dashboard eslint

uv run pytest tests/unit/projects -q                  # 项目域
uv run pytest tests/unit/api -q                       # API 层
uv run pytest tests/unit/cron -q                      # ★ 改了 cron/delivery.py 必跑
uv run pytest tests/integration/test_projects_api.py -q
uv run pytest -m postgresql -q                        # 需 DSN
uv run pytest -n auto -m "not live" -q                # 全量

uv run ruff check src tests
uv run ruff format --check src tests
uv run mypy src/octop

cd dashboard; npx tsc -b                 # 前端类型（★ make all 不覆盖）
cd dashboard; npx eslint src/...         # 前端 lint
cd dashboard; npm run build              # 构建进 src/octop/dashboard/

# 本地起服务
uv run octop run --host 127.0.0.1 --port 8088 --log-level info
```

**旧机运行实例**：<http://127.0.0.1:8088> · 账号 `admin` / `octopadmin2026` · SQLite 控制面 `~/.octop/octop.db` · schema version **19**。

**演示数据**：`56JXDW` 演示项目 Alpha（active，4 任务，1 成员）、`MK3R2R` 演示项目 Alpha（draft）。运行时已配好 provider **DeepSeek**，专家 `7VDPXH`、`AD5N8X`、团队 `6FJJ66 测试`。

### 8.1 本机辅助脚本（`D:\nancc\octop\_tools\`，**不在仓库里，需要重建或从旧机拷**）

| 脚本 | 用途 |
|---|---|
| `verify_migration_numbering.py` | 13 项迁移号自检（重复号、水位、上游 wiring 是否还在） |
| `verify_pg_018.py` / `verify_pg_repos.py` / `verify_pg_timeline.py` | 对真实 PG 跑迁移/repo/时间线验证 |
| `verify_dispatch_e2e.py` | 派单端到端（6 段） |
| `check_local_deploy.py` / `final_check.py` / `seed_demo_project.py` | 本地部署自检 / 造演示数据 |
| `dump_schema.py` | 导出实际 schema |
| `fix_eol.py` | 换行符归一 |
| `renumber_018_to_019.py` 等 | 本次迁移重编号用的一次性脚本 |

---

## 9. 待你决策的开放问题

1. **项目是否必须有知识库？** —— 见 §7.10。当前是可空（best-effort）。
2. **讨论线是否需要支持「改评论 / 删评论」？** —— T3.1 按卡片只实现了 create/list/count。若需要，在同样 4 个文件内即可加。
3. **评论的 `thread_id` 是否要校验存在性？** —— 当前只存不校验（卡片把软外键要求限定在 `task_id`）。若要，同上去加。
4. **写评论是否要在 `timeline_events` 留痕？** —— 当前不留；讨论线自身即记录。
5. **非成员可区分 404 与 403**（项目不存在 vs 无权限），因而能枚举项目 id。当前**刻意保留**，未改状态码。若要收敛，需要统一返回 403。

---

## 10. 文档索引（都在 `D:\nancc\octop\`，不在仓库里）

| 文件 | 内容 |
|---|---|
| **`Octop-换机开发交接文档.md`** | **本文档** |
| `Octop-总计划与落地开发计划.md` | ★ 主计划 v2.2（含附录 H 执行实况）。任务卡、验收表、§4.3 讨论线双层模型、§4.4 Leader 草案、§4.5 Owner 闸门、§4.6 权限矩阵 |
| `Octop-需求文档-v1.0-正文提取.md` | 需求正文提取 |
| `Octop-项目管理与跨团队协作-可行性分析.md` | 可行性分析（A→C 记忆路径、项目作用域可见性） |
| `Octop-改造开发方案.md` | 改造方案 |
| `Octop-develop更新日志整理.md` | 上游 develop 更新日志整理 |
| `Octop-计划审查报告.md` | 计划审查报告（32 项发现） |
| `dev-env.ps1` | ★ 环境脚本（需带 BOM 重建，见 §2.3） |
| `start-octop.ps1` | `-Build` 构建前端 + 自检 + 起服务 |

---

## 附：一句话状态

**项目域地基、任务/成员/看板、派单、讨论线、权限矩阵都已落地并推送；剩余是需求节点池、Owner 闸门、资料归档、时间线回放、聊天列表改造这几块 M1 收尾。**
