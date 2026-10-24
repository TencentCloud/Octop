# Cron/IM 工具前过程文本泄漏：Windows 交接

交接日期：2026-10-24（Asia/Shanghai）。

## 接手任务与代码位置

在 Windows 原生 Python 环境验证本次 cron Agent 文本投递修复，然后完成微信/iLink 真机验收并回报结果。先阅读 `AGENTS.md`、`CONTRIBUTING.md`。本次仅涉及 cron 过程文本泄漏，不修改模型供应商、记忆、数据库 schema 或媒体发送逻辑。

- fork：`https://github.com/henryZhouLikeStudy/Octop.git`
- 分支：`hotfix/cron-preamble-leak`
- 修复基线：`dd9dce470844c25d59effb50615bb3c667ea25cd`（上游和 fork 的 `main`）。
- 具体修复提交号以云端交接消息及远端分支为准；先记录 `git rev-parse HEAD`。
- 此分支独立于 `hotfix/2351-generated-media`，**不包含 #2351 的媒体补丁**。不要修改或覆盖 #2351 分支/PR。若目标部署已经应用媒体修复，保留原部署，先独立验证本分支；需要同时部署时，在用户指定的集成分支保留两项修复，再重新验收，不能用本分支直接覆盖含媒体补丁的部署。
- 不需要下载 ZIP 或再次应用旧补丁；不要修改 `site-packages`，未经用户要求不发布版本或改动生产部署。

在一个未被占用的目录中克隆；若复用已有仓库，先确认 origin、当前分支和工作区状态，保留用户的本地改动，不做强制重置。

```powershell
$ErrorActionPreference = 'Stop'
function Assert-NativeSuccess([string]$Step) {
    if ($LASTEXITCODE -ne 0) { throw "$Step 失败，退出码 $LASTEXITCODE" }
}

git clone --branch hotfix/cron-preamble-leak --single-branch https://github.com/henryZhouLikeStudy/Octop.git C:\src\Octop-cron-preamble
Assert-NativeSuccess '克隆修复分支'
Set-Location C:\src\Octop-cron-preamble
git branch --show-current
git rev-parse HEAD
git status --short
```

刚克隆的工作区应干净。保留 `Assert-NativeSuccess`，后续重要的原生命令也检查真实退出码；仅设置 `$ErrorActionPreference` 不能保证旧版 PowerShell 遇到原生命令失败时终止。

## 问题与修复

原行为：cron 的 `_deliver_agent()` 将整轮 `token`/`delta` 直接拼接，例如把“先查时间”的英文过程说明与后续中文摘要一起传给 `Gateway.push_session_text()`。同一原始 token 流还会进入历史跟踪器，形成“过程说明 + 最终答案”的额外匿名 AI 历史消息。

修复在 `response_mode.py` 新增 `withhold_pretool_stream_chunks()`，只接入 cron Agent 路径：

1. 按当前 AI 文本段暂存 `token`/`delta`，按 index/call id 汇总分片工具名称，并用 ToolMessage 的完整名称补全。
2. 在整批工具结果与下一段模型文本的边界判断：存在普通或未知工具就丢弃此前过程文本；仅调用 `ask_agent` 的批次保留主持人分派话术。
3. 多轮工具分别判断；已确认保留的团队分派话术不会被后续普通工具调用误删。按工具调用 ID 过滤重放结果的判定影响，但不修改原始 chunk。
4. `error`/`hitl_required` 丢弃未确认文本并关闭生产流；cron 遇到错误或等待审批时不推送部分结果。
5. history tracker 和 usage tracker 接收过滤后的流。usage、reasoning、state 等控制 chunk 原样传递，不修改 checkpoint 的原始 AIMessage 或 tool_calls。

此修复没有按语言、英文正则或固定句式删除文字。无工具的英文最终答案正常保留。`task_type=text` 不进入过滤器，普通 Dashboard/QQ/Telegram/微信交互包装器没有改动。

| 文件 | 改动 |
| --- | --- |
| `src/octop/infra/gateway/process/response_mode.py` | raw chunk 过滤与生产流关闭 |
| `src/octop/infra/cron/delivery.py` | cron 接入；过滤后才跟踪历史/用量；终止事件不投递部分回复 |
| `tests/unit/gateway/test_response_mode.py` | 多工具、分片、并行、重放、终止、控制 chunk 等回归测试 |
| `tests/unit/cron/test_cron_delivery.py` | 实际投递参数、SQLite 历史、用量、text cron、异常/审批测试 |
| `CHANGELOG.md` | Unreleased 修复说明 |
| `docs/handoffs/cron-preamble-windows.md` | 本文 |

原来的 `test_agent_failure_projects_the_prompt` 仍验证失败时保存用户 prompt，但现在不再把尚未确认的过程文本存成匿名最终答案。原始带工具调用的 checkpoint 消息仍可保留；验收重点是没有新增拼接的匿名 AI 消息，而非删除模型自己的历史。

## 云端验证记录

- 新增 34 个参数化回归用例；与修复直接相关的两个测试文件和 composer context 测试：**64 passed**。
- 完整 `make all PYTEST_JOBS=4`：Ruff、格式检查、mypy（597 个源文件）通过；完整非在线测试 **5064 passed、22 skipped、4 failed**，命令退出码为 2。失败仍是下表 4 项既有问题，没有新增失败，不能称为全量门禁全绿。
- 本次交接提交保留原 pre-commit hook，通过 `PYTEST_ADDOPTS="tests/unit/cron tests/unit/gateway tests/unit/history"` 将本地 testmon 检查限定为相关模块；hook 仍执行格式处理、Ruff、mypy 和 Dashboard 构建。局部提交检查不替代上面的完整门禁。
- 尚未进行 Windows 原生部署、真实 cron 调度或微信/iLink 真机验收。云端投递使用 mock 的 Gateway，SQLite 历史测试使用真实临时数据库。

本环境此前确认有 4 项既有失败，若完整门禁仍出现它们，需要分别记录：

| 测试 | 已知原因 |
| --- | --- |
| `tests/unit/bridge/test_peer_auth.py::test_normalize_accepts_https_host` | `demo.octop.chat` 的未 mock DNS 解析失败 |
| `tests/integration/test_bridge_api.py::test_bridge_probe_returns_expert_list` | 同上，返回 502 |
| `tests/integration/test_bridge_api.py::test_bridge_probe_peer_rejection_stays_logged_in` | 同上，在认证判断前失败 |
| `tests/unit/test_fnos_native_stop.py::test_free_octop_ports_kills_orphan_child` | 云容器不提供 `/proc/<pid>/task/<pid>/children` |

Linux bwrap 集成测试需要支持的外层执行权限；不要关闭应用沙箱。Windows 上应由原有 Linux/POSIX 标记决定跳过，不要手工屏蔽本次修复相关用例。发现额外失败时逐项诊断，不能一概称为“基线问题”。

## Windows 原生环境与自动测试

使用 Python 3.12、uv、Node 20/npm 10，具体版本约束见 `mise.toml`。不能只在 WSL 通过后声称 Windows 验证完成。云端使用 Python 3.12.14、uv 0.12.23、Node 20.20.2/npm 10.9.9。不要复制云端虚拟环境或 Linux 编译器设置。

```powershell
uv sync --frozen --python 3.12
Assert-NativeSuccess '安装 Python 依赖'
Push-Location dashboard
npm ci
Assert-NativeSuccess '安装前端依赖'
npm run build
Assert-NativeSuccess '构建 Dashboard'
Pop-Location

uv run --frozen python -c "import sys; import octop.infra.cron.delivery as d; import octop.infra.gateway.process.response_mode as r; print(sys.executable); print(d.__file__); print(r.__file__); print(hasattr(r, 'withhold_pretool_stream_chunks'))"
Assert-NativeSuccess '核对实际加载的修复源码'

uv run --frozen pytest tests/unit/gateway/test_response_mode.py tests/unit/cron/test_cron_delivery.py tests/unit/cron/test_cron_composer_context.py -q
Assert-NativeSuccess '定向回归'
uv run --frozen pytest tests/unit/cron tests/unit/gateway tests/unit/history -q
Assert-NativeSuccess '相关模块测试'
```

`delivery.__file__` 与 `response_mode.__file__` 必须来自当前源码克隆，不能是旧全局安装或桌面内置运行时。版本号仍为 1.0.2，不能用版本号代替修复提交号。

在配置好 Git Bash/GNU make 的环境中，按官方要求运行 `make install-hooks`、`make all PYTEST_JOBS=4`；运行后检查是否产生无关格式变更。若暂时没有 GNU make，可以先在 PowerShell 继续以下检查，明确报告 `make all` 未运行：

```powershell
uv run --frozen ruff check src tests
Assert-NativeSuccess 'Ruff'
uv run --frozen ruff format --check src tests
Assert-NativeSuccess '格式检查'
uv run --frozen mypy src/octop
Assert-NativeSuccess 'mypy'
uv run --frozen pytest -n 4 -m 'not live' --junitxml=cron-preamble-windows-results.xml
Assert-NativeSuccess '完整非在线测试'
```

保留退出码、通过/失败/跳过统计。验证 XML 是本地产物，不要误提交。不能修改断言、全量 skip 或绕过测试来声称通过。

## 测试部署与微信验收

使用独立测试数据、测试账号和测试 cron；不要迁移或覆盖现有 `~/.octop`。若目标是 Windows 服务、wheel 或 EXE，先识别实际运行时与启动方式，确认修复安装到该运行时；源码启动通过不代表桌面 EXE 已更新。

在仓库根目录开 PowerShell，选择空闲测试端口：

```powershell
$env:OCTOP_HOME = Join-Path $env:LOCALAPPDATA 'Octop\cron-preamble-test'
$env:OCTOP_DATABASE_DRIVER = 'sqlite'
uv run --frozen octop run --host 127.0.0.1 --port 18089
```

另开终端检查：

```powershell
$h = Invoke-RestMethod 'http://127.0.0.1:18089/api/health'
if (-not $h.ok -or -not $h.db) { throw '服务或数据库未就绪' }
$p = Invoke-WebRequest 'http://127.0.0.1:18089/' -UseBasicParsing
if ($p.StatusCode -ne 200) { throw 'Dashboard 未就绪' }
```

通过正常初始化向导配置测试模型、Agent 和微信/iLink Bot。保留初始化口令保护；不要把 `~/octop-login.txt`、API Key、微信 token、完整记忆正文或含凭据的启动日志放进报告。使用独立 Bot；复用已有 Bot 时先与用户协调停用旧轮询实例，避免双实例竞争。

| 必验场景 | 预期结果 |
| --- | --- |
| 实际调度的 `task_type=agent` cron | 明确要求先调用 `current_time`/`ls` 等普通工具，再输出中文短摘要；微信只收到最终摘要，不出现工具前计划 |
| 两轮普通工具 | 每轮工具前的过程说明都不出现；最终正文完整、不重复投递 |
| `ask_agent` 团队主持人 | 必要的“分派给谁”话术保留，最终答案正常；混入普通工具时，对应普通工具批次的过程说明丢弃 |
| `task_type=text` | 预置提醒原文逐字保留，即使文字看起来像英文过程说明 |
| 无工具 Agent 任务 | 最终答案完整保留，包括真正的英文答案 |
| 历史投影 | 只读检查本次 thread，不再新增匿名的“计划 + 答案”AI 消息；原始带 tool_calls 的 AIMessage 可保留 |
| 错误/HITL | 不发送未完成文字；调度错误可在运行记录中观察到。自动测试另覆盖生产流关闭 |
| 普通交互回归 | 普通微信、Dashboard 原有交互保持正常；不要将 cron 的过滤器扩展到所有 UI 流 |
| 重启 | 只停止本次启动的测试服务；以同一配置重启后重新执行一条测试 cron，仍然正确 |

首次可手动触发测试 cron 来缩短反馈，但最终至少验证一次真实调度路径。不要把普通聊天测试或 `task_type=text` 成功当作 Agent cron 已验收。查看记录时只读，不修改用户 checkpoint 或数据库 schema。保留脱敏截图/录屏、运行时间和必要的日志证据。

## 回报与后续操作

报告需包含：基线与实际修复提交号、Windows/工具链版本、实际加载路径和部署形式；每条检查命令的退出码及统计；上表逐项通过/失败/未运行；真实调度与微信结果的脱敏截图；已有失败与本次新增问题的区分。

若缺少账号、模型、Bot 或测试窗口，明确写“自动测试已验证，真实 cron/微信端到端验收未完成”，不要声称已完成生产部署。需要用户提供的值通过安全设置提供，不在聊天或提交中收集凭据。

后续如需补修，继续在此独立分支或用户指定的集成分支工作。未经用户要求不修改 #2351 分支、不创建生产 tag、不直接推送 `main`。本次分支交付不等于已经创建 Issue/PR、合入上游或发布。
