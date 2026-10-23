# Agent 内容文件 Backend 严格化改造方案

> 目标：政务伙伴服务端对 agent workspace **内容文件**的读写，一律经 `agent.backend`（或 `resolve_harness_backend`），不再用 `Path(...).write_text` / `read_text` 直连磁盘。  
> 记忆相关路径除外。不新增统一 I/O 抽象层。

---

## 1. 背景与问题

当前部分代码在 agent 已配置远程 backend（S3/COS 等）时，仍向本地 `~/.agentbuddy/agents/<agent_id>/` 读写内容文件，导致：

- 用户配置了 backend，agent 工具读的是远程存储；
- 政务伙伴服务端 seed / 写 SOUL / 同步插件 skills 等仍写本地；
- Dashboard 部分读路径优先本地，展示与真实存储不一致。

默认未配置 backend 时，harness 使用 `filesystem` + `virtual_mode`，`root_dir` 由 `workspace_dir`（即 `~/.agentbuddy/agents/<id>/`）在创建 backend 时挂载。此时直连磁盘与经 backend 写入**同一物理文件**，但远程 backend 场景下必须统一走 backend。

---

## 2. 核心原则

### 2.1 只换 IO 通道，不换路径

改造前后**操作的是同一个文件**，路径字符串**保持项目既有写法**，政务伙伴不做路径改写。

```python
# 以前
workspace_dir = paths.ensure_agent_workspace(agent_id)
(workspace_dir / "SOUL.md").write_text(text, encoding="utf-8")

# 以后 — path 字符串不变，只换 IO
soul_path = str(workspace_dir / "SOUL.md")
backend = await agent_registry.resolve_harness_backend(agent_id)
await backend.aupload_files([(soul_path, text.encode("utf-8"))])
```

- **禁止**在政务伙伴层把 `~/.agentbuddy/agents/<id>/SOUL.md`「转换」为 `/SOUL.md`、`SOUL.md` 等另一套命名。
- 专家模板、skills、seed 等：backend 参数中的 path 与原先 `disk_path = workspace_dir / rel` 的字符串形式一致。

### 2.2 Backend 获取方式

| 场景 | 用法 |
|------|------|
| Agent 已运行 | `agent.backend` |
| 启动前 / 未运行 | `await agent_registry.resolve_harness_backend(agent_id)` |

`resolve_harness_backend` 内部已调用 `resolve_backend(spec, workspace_dir=str(workspace))`，`root_dir` 在**创建 backend 时**挂载，日常读写只传业务路径。

### 2.3 不新增 `workspace_io` 模块

直接调用 backend 协议即可：

- 读：`aread(path)`、`als(path)`、`adownload_files([path])`
- 写：`aupload_files([(path, bytes)])`
- 搜：`aglob` / `agrep`

现有薄 helper（如 `api/common/workspace.py` 的 `coerce_read_content`、`gateway/backend_files.backend_download_bytes`）可复用，不包装成新层。

### 2.4 `workspace_dir` 的保留用途

`~/.agentbuddy/agents/<id>/` 仍作为 harness 的 `workspace_dir`，用于：

- 构造 backend 时的 `root_dir` 挂载（默认 filesystem）；
- checkpoint、sessions JSONL、octop-memory SQLite 等**本地产物**（不由 backend 协议管理）；
- 终端 PTY 的 cwd（见 §6 例外）。

**内容文件**（md、skills 等）不再由政务伙伴对该目录做 `read_text` / `write_text`。

---

## 3. 范围

### 3.1 纳入改造（须走 backend）

| 类型 | 典型路径（示例，以实际 `workspace_dir` 拼接为准） |
|------|--------------------------------------------------|
| 引导模板 | `{workspace_dir}/AGENTS.md`、`BOOTSTRAP.md`、… |
| Persona | `{workspace_dir}/SOUL.md` |
| Skills | `{workspace_dir}/skills/<name>/SKILL.md` |
| 专家模板 | `{workspace_dir}/` 下各相对路径 |
| 工作区配置 md | `{workspace_dir}/USER.md`、`HEARTBEAT.md` 等 |
| Dashboard workspace API | 已走 backend，保持 |
| 上下文用量估算 | 读 `AGENTS.md`、`USER.md`、`SOUL.md` 等（见 §3.2） |
| Bootstrap 状态 | 检查 `BOOTSTRAP.md`、`.bootstrapped` |
| 系统备份中的 workspace 内容 | 改走 `export_workspace_zip(backend)` |

### 3.2 记忆豁免（本期不强制改）

| 类型 | 说明 |
|------|------|
| `MEMORY.md` | 长期记忆 |
| `daily/YYYY-MM-DD.md` | 日记忆；读已走 backend，删除暂可保留本地 `unlink` |
| `sessions/*.jsonl` | 对话历史兜底 |
| octop-memory / checkpoint | 绑定 `workspace_dir`，非 backend 内容文件 |

### 3.3 不在范围

- Expert library 内 skill 脚本（agent 运行时经 harness 工具执行）
- `~/.agentbuddy/plugins/` 安装、`~/.agentbuddy/security/` tool guard
- Expert catalog  bundled 源码读取

---

## 4. 待改造清单

### 4.1 写路径（优先级最高）

| 位置 | 现状 | 改造 |
|------|------|------|
| `infra/agents/manager.py` `_seed_workspace` | `init_workspace(ws_dir)` 写本地 | `init_workspace(tmp_dir)` → 收集文件 → `backend.aupload_files`，path 为 `str(workspace_dir / rel)` |
| `infra/agents/persona/` (SOUL / persona render) | `Path.write_text` | 改为 async，参数含 `backend`；`aupload_files([(str(workspace_dir / "SOUL.md"), ...)])` |
| `infra/agents/manager.py` `_start_agent` | 调 `write_soul_md(workspace_dir=...)` | 先 `resolve_harness_backend`，再写 SOUL |
| `infra/agents/plugins/manager.py` `sync_skills_to_workspace` | `shutil.copytree` 到本地 | 重命名为 `sync_skills_to_backend`；遍历插件目录 → `aupload_files`，path 为 `str(workspace_dir / "skills" / name / ...)` |
| `infra/agents/manager.py` `_apply_expert_template` | 本地 `write_text` + 可选 `aupload_files` | **删除本地写**；path 用 `str(ws / rel_path.lstrip("/"))`，与原先 `disk_path` 一致 |
| `infra/agents/manager.py` `_ensure_skills_dir` | 本地 `mkdir` | 删除（由 upload 隐式建目录） |
| `infra/utils/browser_media.py` | 截图写本地 `outbound/screenshots` | 截图后 `aupload_files` 到同逻辑路径，或短期标注仅本地 backend |

### 4.2 读路径

| 位置 | 现状 | 改造 |
|------|------|------|
| `infra/agents/context_breakdown.py` | `_read_workspace_text(workspace_dir, name)` | 改为 `backend.aread(str(workspace_dir / name))`；`MEMORY.md` 可保留记忆豁免策略 |
| `infra/agents/manager.py` `_bootstrap_pending` | 读本地 `BOOTSTRAP.md`、`.bootstrapped` | 改为 async，经 `backend.aread` / `exists` 判断 |
| `api/routers/agents.py` / `experts.py` | 调 `_bootstrap_pending(workspace)` | 传入 backend |
| `api/routers/chat/serialize.py` | sessions 本地优先 | **记忆豁免**：维持或文档化；非记忆逻辑不读本地内容文件 |

### 4.3 Gateway 与备份

| 位置 | 现状 | 改造 |
|------|------|------|
| `infra/gateway/backend_files.py` | 预览失败时 `Path.read_bytes` 兜底 | 去掉对 agent workspace staging 的静默 fallback；host 临时文件仍可先 upload 再读 backend |
| `infra/backup/system_archive.py` | tar 打包本地 `agent_workspace` | 每 agent 使用 `export_workspace_zip(backend)` |
| `infra/backup/workspace_archive.py` | replace 模式 `_clear_local_workspace` | 远程 replace 需列 backend 文件后覆盖；或文档警告 + 后续支持 delete |

### 4.4 已合规（仅需对齐 path 约定时检查）

- `api/routers/workspace.py`
- `api/routers/skills.py`
- `api/routers/agent_files.py`（daily 读）
- `infra/gateway/media.py` `AgentBackedMediaBackend`

若上述模块中 path 使用 `/skills/...` 等与磁盘路径不一致的写法，与产品约定对齐：**统一为 `str(workspace_dir / ...)` 形式**（与本次原则一致）。

---

## 5. 启动时序（改造后）

```
create(agent)
  ├─ DB insert
  ├─ backend = resolve_harness_backend(agent_id)
  ├─ _seed_workspace(agent_id)     # tmp → aupload_files，path 带 workspace_dir 前缀
  ├─ write_soul_md(backend, ...)   # 若需要
  ├─ create_agent(..., init_workspace=False)
  └─ _apply_expert_template(...)   # 仅 aupload_files
```

- 全程不对内容文件 `Path.write_text`。
- `init_workspace=False`：避免 harness 再次写本地造成双轨；seed 由政务伙伴经 backend 完成。

---

## 6. 明确例外

| 场景 | 处理 |
|------|------|
| **终端** `api/routers/terminal.py` | PTY cwd 仍为 `workspace_dir`；远程 backend 时 UI 禁用或提示「仅本地 backend」 |
| **记忆删除** `agent_files.delete_daily_memory` | 暂保留本地 `unlink`；待 backend 支持 delete 后统一 |
| **sessions JSONL** | 记忆豁免 |
| **默认 filesystem** | `root_dir` = `workspace_dir` 时，`aupload_files` 与原先 `write_text` 落同一文件，默认用户无感 |

---

## 7. 兼容与迁移

### 7.1 已有 agent + 远程 backend + 本地有文件、远程为空

在 `_start_agent` 或一次性 CLI 中做幂等迁移：

1. `resolve_harness_backend(agent_id)`
2. 若 backend 根目录 listing 为空且本地 `workspace_dir` 有内容文件
3. 将本地文件（排除记忆豁免目录）`aupload_files` 到 backend，path 仍为 `str(workspace_dir / rel)`

### 7.2 默认 filesystem 用户

无迁移步骤；仅 IO 通道变化，物理路径不变。

---

## 8. PR 拆分

| PR | 内容 | 风险 |
|----|------|------|
| **PR-1** | 写路径：seed、soul、plugins、expert template；删本地双写 | 中 |
| **PR-2** | 读路径：context_breakdown、bootstrap_pending | 低 |
| **PR-3** | gateway 去 fallback、system backup 走 backend | 中 |
| **PR-4** | 远程 backend 迁移逻辑 + 测试 | 低 |

每 PR 独立 `make all`；合并前对默认 filesystem 做冒烟（创建 agent、读 SOUL、skills 列表）。

---

## 9. 测试计划

| 类型 | 内容 |
|------|------|
| 单元 | `FakeBackend` 记录 `aupload_files` 的 path 与 bytes；创建 agent 后断言 path 为 `workspace_dir` 下的绝对路径形式 |
| 单元 | `_apply_expert_template` 不再调用 `Path.write_text` |
| 单元 | `bootstrap_pending` 经 backend 判断 |
| 集成 | 默认 filesystem：创建专家 agent 后 `GET workspace/file` 与磁盘一致 |
| 集成 | Mock 远程 backend：`aupload_files` 收到文件后，本地 staging 无对应内容文件（记忆/ checkpoint 目录除外） |

---

## 10. 完成标准

- [ ] `infra/agents/manager.py`、`persona.py`、`plugins/manager.py` 中无对内容文件的 `write_text` / `copytree`（记忆豁免路径除外）
- [ ] `context_breakdown`、`bootstrap_pending` 经 backend 读
- [ ] `gateway/backend_files` 无 agent workspace 本地 fallback
- [ ] `system_archive` 备份含 backend 内容
- [ ] `make all` 绿；涉及 dashboard 时 `cd dashboard && npx tsc -b`
- [ ] 代码审查：新增 agent 内容文件 IO 必须出现 `backend.aread` / `aupload_files` 等，不得 `ensure_agent_workspace(...) / "xxx").write_text`

---

## 11. 参考

- Backend 解析：`infra/agents/manager.py` → `resolve_harness_backend`
- Harness 挂载：`octop_harness.backends.resolve_backend(spec, workspace_dir=...)`
- 已合规示例：`api/routers/workspace.py`、`api/routers/skills.py`
- 路径布局：`infra/utils/paths.py` → `agent_workspace` / `ensure_agent_workspace`

---

## 12. 局部 root_dir 与 execute jail（补充）

当 agent backend 为本地 `local_shell`，且同时满足 **Linux + `virtual_mode=True` + `root_dir` 非主机 `/` + 宿主机有 `bwrap`** 时，harness 在 **构造 backend 之前** 路由到 `BubbledLocalShellBackend`，将 `execute`（含 Skill 脚本）包进 bubblewrap：工作根绑到 `/`，与文件工具虚拟路径对齐。其余情况（宿主根、非 Linux、无 bwrap、`filesystem`）走普通 `HarnessLocalShellBackend`：无目录狱，但在 **octop-harness >= 1.0** 且 `virtual_mode` + 非宿主 `root_dir` 时，仍会把 `execute` 命令里的虚拟绝对路径改写到该 `root_dir` 下再在宿主机执行。

`scripts/install.sh`（及 desktop Linux 安装脚本）会在 **Linux** 上尽力安装 `bubblewrap`；保存局部 `root_dir` 时仪表盘也会调用 `POST /api/filesystem/ensure-bwrap` 做同样的尽力安装。macOS / 无 bwrap 时无目录狱，文件工具仍靠 deepagents `virtual_mode`；`BackendWorkspace` 读/物化路径 failback 不变：绝对路径先 virtual 映到 `root_dir` 再原始宿主机路径；相对路径先 `{root_dir}/{rel}` 再 `{workspace_dir}/{rel}`。Dashboard path I/O: use ``dashboard/src/utils/workspaceIoPath.ts`` for download/file API paths
(host absolute stays ``file://…``). Dock tab identity may still ``canonicalizeDockFilePath``;
do not collapse host abs before calling BackendWorkspace.

---

## 13. Docker sandbox backend

需要把 agent 的文件系统工具与 `execute` 隔离到 Docker 容器时，配置 harness `type: "docker"`（需 `octop-harness[docker]`，本机 Docker daemon 可用）。

宿主 ``workspace_dir`` 在**创建专家时**写入 ``config_json.workspace_dir``（默认
``{AGENTBUDDY_HOME}/agents/<agent_id>/``；创建时可覆盖）。**所有 backend 类型**共用这
一路径作为 harness ``HarnessAgentConfig.workspace_dir``：

| Backend | 专家可见内容 | 宿主 ``workspace_dir`` |
|---------|--------------|------------------------|
| ``local_shell`` / ``filesystem`` | 通常对齐该目录（或 ``root_dir``） | sessions / memory / checkpoints |
| ``docker`` | 容器内**同名绝对路径**（不 bind-mount） | 同上 |
| 对象存储等 | 远端对象；本地物化/缓存按 backend | 同上 |

自动压缩与 `/compact` 把被挤出的原文写到
``{artifacts_root}/conversation_history/{session_id}.md``。本地
``local_shell`` / ``filesystem`` 经 harness ``MountedCompositeBackend`` 把
``artifacts_root`` 收到工作区（政务伙伴：``.octop/conversation_history/``）。
``docker`` / ``opensandbox`` / COS 等**没有**这层 wrap：offload 可能落到
容器内 ``/conversation_history/``。自动压缩在写失败时仍继续摘要
（``file_path=None``）；``/compact`` 写失败则整次失败，不改对话状态。

Harness 侧只认调用方传入的 ``workspace_dir``；Docker 默认把它镜像成容器内工作区根。

### 直接写在 agent `config_json.backend`

```json
{
  "backend": {
    "type": "docker",
    "image": "python:3.12-slim",
    "sandbox_scope": "agent",
    "sandbox_prefix": "octop_sandbox",
    "allow_network": false,
    "memory": "512m"
  }
}
```

字段：

| 字段 | 说明 |
|------|------|
| `sandbox_scope` | `agent`（默认）/ `user` / `fixed` |
| `sandbox_prefix` | 容器名前缀；政务伙伴默认注入 `octop_sandbox`；库默认 `sandbox` |
| `sandbox_id` | `fixed` 必填 |
| `username` | `user` 用；缺省时政务伙伴注入专家所有者用户名 |
| `previewable` | 仅影响 Admin「我的存储」浏览按钮；默认仅 `fixed` 为 true。专家工作区始终可预览 |
| `volumes` | 用户自行配置的挂载，原样透传；**不**自动 named volume |

容器命名：

- `agent` → `{prefix}_agent_{agentId}`（如 `octop_sandbox_agent_ZE6GR2`）
- `user` → `{prefix}_{username}`（同用户多专家共用一沙箱）
- `fixed` → `sandbox_id`

生命周期：没有则创建；`close` / 删除专家**不**删容器；显式 `destroy()` 才 stop+remove（容器内文件一并删除）。

### 或经 storage_backends（`kind=docker`）+ named 引用

- `bucket` 或 `config_json.image`：镜像名（必填）
- Admin 表单可配 `sandbox_scope` / `sandbox_prefix` / `sandbox_id` / `username`，写入 `config_json`
- 其余可选：`allow_network`、`memory`、`cpus`、`pids_limit`、`command_timeout`、`volumes` 等

```json
{ "type": "named", "name": "my-docker-sandbox" }
```

行为要点：

- **同名路径、两处落盘（不自动挂载）**：
  - 专家 ``workspace_dir``（创建时写入配置/库；政务伙伴默认 ``{AGENTBUDDY_HOME}/agents/<id>/``）：宿主上放 sessions / memory / checkpoints
  - 容器内同一绝对路径：专家可见工作区（由传入的 ``workspace_dir`` 决定；可用 ``workspace_path`` 覆盖；皆无时回退 ``/workspace``）
- **沙箱 FS**：`ls` / `read` / `write` / `execute` 都在容器内，经 Docker Python SDK 完成
- **专家工作区**（专家页文件树 / SOUL.md 等）始终可预览；走 agent backend API（Docker 时即该专家对应容器内同名路径）
- **Admin 存储浏览**（`/admin/backend`）：`previewable` 控制；Docker 默认仅 `fixed` 可浏览；`agent`/`user` 按钮置灰，仍可用「探测」验证连通性（test 沙箱）
- 默认 `allow_network=false`；需要 pip/curl 时显式打开
- 启动前会确认镜像在本地；缺失则尝试 pull
- Admin 启用 Docker 存储后端或点「测试可用性」时会自动拉取镜像
- storage backend 浏览 API 支持 docker kind（`previewable` 时）；探测走 test id 沙箱
- Admin「支持类型」页的 Docker 卡片可配置沙箱镜像；打开配置抽屉后可探测本机 Docker，并提供一键安装 / 复制脚本 / 安装提示词

### 13.1 镜像升级与容器换代（沙箱管理）

容器创建后，harness 按**名字复用**已存在的容器：改配置里的 `image` 或
`allow_network` 对运行中的容器**不生效**。镜像 / 网络的变更生效流程
（台账 + 漂移检测 + 一键重建，详见 `docs/sandbox-image-management.md`）：

1. 改配置：`image` 指向新 tag（永远用新 tag，禁止同名覆盖 / `latest`）；
   `allow_network` 开关联网；
2. 重建容器：「管理 → 存储 → 沙箱容器」面板（或 `octop sandbox recreate <container>`）
   一键执行：备份容器工作区到宿主 `{AGENTBUDDY_HOME}/sandbox-backups/<container>/<时间戳>/`
   → 校验期望镜像存在 → 删除容器；下次对话自动按新配置重建；
   关联专家有进行中对话时拒绝（409 `SANDBOX_IN_USE`）；
3. 验证：沙箱面板的镜像列 / 网络列显示 `DRIFT` / `NETWORK-DRIFT`，重建后恢复 `OK`。

数据边界：sessions / memory / checkpoints 在宿主 `workspace_dir`，换代不受影响；
容器可写层里的工作区内容文件由备份兜底；容器内 pip/npm 安装的依赖随容器删除
（这正是换代 / 收回网络权限的目的之一）。

### 13.2 技能依赖与镜像白名单（分层镜像）

沙箱默认离线（`allow_network=false`），技能只能用镜像里已有的依赖。harness 内置技能
（`octop_harness/builtin/skills/{en,zh}/`，24 个）按依赖分四档：

| 档 | 技能 | 处理 |
|---|---|---|
| 零依赖（13 个） | plan、skill-creator、docker-management、memory-management、systematic-debugging、using-workspace、watchers、architecture-diagram、install-skill、apple-notes/reminders/findmy/imessage（macOS 本机技能，docker 沙箱不适用） | 无需处理 |
| 轻依赖 | ocr-and-documents（pymupdf4llm）、powerpoint（markitdown/Pillow/pptxgenjs）、ascii-art（pyfiglet/cowsay）、mcporter、llm-wiki（obsidian-headless） | **基础镜像白名单已含**（SKILL_PIP_PKGS / SKILL_NPM_PKGS / apt cowsay，`docker/Dockerfile.sandbox`）；llm-wiki 需联网，离线不适用 |
| 中依赖 | ascii-video（numpy✅/scipy 可选/Pillow✅） | numpy/Pillow 已进白名单；scipy 仅音频模式需要，未烤 |
| 重依赖 | jupyter-live-kernel（jupyterlab 全家桶）、manim-video（manim + texlive-full） | **分层镜像变体**，不进基础镜像 |

**分层镜像变体**（重依赖按需构建、按专家分配，backend 的 `image` 字段选择）：

```
docker build -f docker/Dockerfile.sandbox -t agentbuddy-sandbox:<ver> .                # 基础
docker build -f docker/Dockerfile.sandbox --target variant-jupyter \
  -t agentbuddy-sandbox:<ver>-jupyter .                                                # jupyter 全家桶
docker build -f docker/Dockerfile.sandbox --target variant-manim \
  -t agentbuddy-sandbox:<ver>-manim .                                                  # manim + texlive-full
```

- 基础镜像是默认构建输出（不传 `--target`）；变体阶段显式 `--target` 选择；
- 变体选择 = 存储管理界面建多个 docker 后端行（各自 `config_json.image` 指向不同 tag），
  专家创建时分配；或 agent 内联 `config.backend.image`；改 image 后需 recreate 生效（§13.1）；
- 永远新 tag、禁止同名覆盖（`docs/sandbox-image-management.md` §5.2 纪律）。

**技能禁用（裁剪）**：粒度 = 每 agent 的 `config_json.skills_disabled`（slug 列表）：

- CLI：`octop skills disable <技能名> --agent <agent_id>`（逐 agent）；
- 界面/API：技能列表 enabled 开关（`persist_skills_disabled` 热同步，无需重建容器）；
- 无跨 agent 的全局开关：新建专家时不勾选 + 已有的用 CLI/API 逐个 disable；
  （2026-10-23 定案：**不做部署级 `skills_disabled_default`**，维持现状靠管理纪律。）
- **禁用而非删源码**（定案）：harness 内置技能不删，升级 resync 回来也无妨；禁用可逆、按部署环境定制。
  政务环境建议禁用：apple-notes / apple-reminders / findmy / imessage（macOS 本机 API，
  docker 沙箱永远跑不了）、nano-pdf（需 LLM API key，离线不可用）、marker-pdf（PyTorch ~5GB，
  有 pymupdf 轻路径兜底）、llm-wiki（需联网）。
