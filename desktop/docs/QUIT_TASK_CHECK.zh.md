# 退出前任务检查：实现方案

> 对应 `DESKTOP_ARCHITECTURE.zh.md` §3.4 第 1 条中尚未实现的部分。
> 清理链路（停中继 → 停 Python → 退出、信号路径）已经完成，本文只解决
> **「退出前问后端有没有在跑的任务，有就弹原生确认框」**。

## 1. 问题

现在用户按 Cmd+Q / 点关闭 / 托盘退出时，壳只做一件事：请求 Sidecar 停机并等宽限期，
然后退出。如果有人正在跑一个 Agent 任务或一条长命令，这次退出会**静默地打断它**，
而且没有任何提示。

理想行为：退出前问一次「现在忙不忙」，忙就弹一个原生确认框，用户可以选择留下。

## 2. 为什么这一条一直没做

不是壳侧偷懒，而是**没有可信的输入**。核实过的事实：

| 位置 | 现状 |
|---|---|
| `src/octop/api/routers/terminal.py:244` | `_sessions: dict[tuple[str, str], _PtySession]`，全局存活 PTY。**唯一现成的「在跑」集合** |
| `src/octop/infra/gateway/process/processor.py:655 / :959` | `GlobalProcessor.__call__`（IM 频道）与 `iter_turn_chunks`（Dashboard / Bridge / cron）是两个独立的 turn 入口，**都没有在跑注册表** |
| `src/octop/api/routers/chat/ws.py:249` | turn 是 `channel_manager.enqueue(...)` 投递的，**WS 断开不会取消 turn**；所以「WS 连着」既不是必要条件也不是充分条件 |
| `src/octop/api/routers/health.py` | `/api/health` 的 `agents_running` 是**已加载的 agent 数**，不是在执行的任务数——不能拿来当忙碌信号 |
| `src/octop/infra/cron/manager.py` | 有 `run_now` / `_run_user_job`，但同样没有「本次执行进行中」的可读状态 |

所以这一条的前置条件是**后端先有一个明确的活动注册表**。用壳侧代理指标（代理里的在飞请求
数、中继里打开的 WS 数）糊一版是不行的：空闲终端会话也算「WS 连着」，结果就是每次退出都弹
框，用户第一次就会学会无脑点「继续退出」，等于没有这个功能。

## 3. 设计

三块：后端注册表 → 后端只读接口 → 壳侧询问。分三个可独立合并的 PR。

### 3.1 后端：进程内活动注册表

新增 `src/octop/infra/runtime_activity.py`。纯内存、无持久化、无 IO，进程重启即清零。

```python
class ActivityKind(StrEnum):
    AGENT_TURN = "agent_turn"
    TERMINAL = "terminal"

@asynccontextmanager
async def track(kind, *, agent_id: str | None = None, thread_id: str | None = None): ...

def snapshot() -> list[dict[str, object]]   # JSON 安全，按 started_at 升序
def counts() -> dict[str, int]
```

要点：

- **数据结构**：`dict[str, _Activity]`，key 用 `f"{kind}:{agent_id}:{thread_id}"`，
  值只放 `kind / agent_id / thread_id / started_at`。**不放文本、放不放 prompt、不放路径**。
- **入口与出口对称**：`async with track(...)` 包住整个 generator，`try/finally` 保证异常、
  取消（`GeneratorExit` / `aclose()`）都会减一。注册表只做引用计数式增删，不持有任务句柄，
  不改变任何调度行为。
- **插桩点只有两个**（两者互不嵌套，一个 turn 只会走其中一个）：
  1. `GlobalProcessor.iter_turn_chunks`（`processor.py:959`）——Dashboard WS、Bridge、cron；
  2. `GlobalProcessor.__call__`（`processor.py:655`）——IM 频道（钉钉/飞书/…）。
- **终端不插桩**：`terminal._sessions` 已经是真相，接口生成时读 `len(_sessions)` 即可。
  但注意语义——它是「活着的 PTY 会话」，不是「正在执行命令」，文案不能写成「正在执行」。
- 单测：进入/退出、异常退出、`aclose()` 退出、嵌套不同 key、`counts()` 聚合。

### 3.2 后端：只读接口

新增 `src/octop/api/routers/runtime_activity.py`，挂载为 `GET /api/runtime/activity`。

**路径选择**：`/api/desktop/*` 已被「远程桌面」功能占用
（`app.py:298` 的 `_RouterMount(desktop.router, "/api", ["desktop"])`，内容是 install /
settings / status / stream / uninstall），不能借用；`/api/runtime` 目前空闲，语义也正好。

响应：

```json
{
  "busy": true,
  "checked_at": "2026-10-28T03:12:44.120Z",
  "counts": { "agent_turn": 1, "terminal": 2 },
  "items": [
    { "kind": "agent_turn", "agent_id": "agt_...", "thread_id": "thr_...",
      "started_at": "2026-10-28T03:12:02.001Z", "age_seconds": 42 }
  ]
}
```

- `items` 最多 20 条（`truncated: true` 表示还有更多），只需要「有几件事、多久了」。
- **明确不返回**：对话内容、prompt、模型名、工作区路径、任何凭据。
- `busy = bool(items)`；`terminal` 的条目不带 `thread_id`。

**鉴权**：`GET /api/runtime/activity` 加进 `src/octop/api/deps.py:41` 的
`_JWT_EXEMPT_EXACT`（和 `/api/auth/device/token` 并列），理由写在注释里；路由内部调用
`_require_desktop_loopback(request)` 做真正的把关——它要求 `desktop_shell_enabled()`
（`OCTOP_DESKTOP_SHELL=1`，只有壳拉起的 Sidecar 才有）且对端是 loopback。

> `_require_desktop_loopback` 现在是 `auth_device.py:71` 的私有函数，实施时把它提到
> `src/octop/api/common/desktop.py`，两处共用；不要复制一份。

这不是「新增一个无鉴权接口」：壳自己不发 JWT，它能证明的身份就是「我是这个 Sidecar 的壳」
+「我从本机来」，和设备凭据续期完全同一套信任边界。而且这个接口只读、只回计数。

测试：非桌面壳 → 403；非 loopback 对端 → 403；无 JWT 也能拿到（证明 exempt 生效）；
返回体字段白名单（断言不含 prompt/text/path 之类字段）。

### 3.3 壳侧：quit guard

新增 `desktop/src/main/quit-guard.ts`（纯决策逻辑 + 一次查询，便于单测），在
`desktop/src/main/index.ts` 的 `before-quit` 里接上。

```ts
export type QuitReason = "user" | "update" | "signal";

export interface QuitGuardDecision {
  ask: boolean;          // 是否弹确认框
  counts: Record<string, number>;
  total: number;
}

export async function inspectBeforeQuit(options: {
  reason: QuitReason;
  backendPort: number;
  fetchImpl: typeof fetch;
  timeoutMs?: number;
}): Promise<QuitGuardDecision>;
```

决策矩阵：

| 情况 | 行为 |
|---|---|
| `reason !== "user"`（更新安装 / 信号） | 不查询、不弹框，直接走停机 |
| `backendPort === 0`（Sidecar 未就绪或已死） | 不查询，直接退出 |
| 查询成功且 `busy === false` | 静默退出 |
| 查询成功且 `busy === true` | 弹原生确认框 |
| 查询超过 800ms / 网络错误 / 4xx / 5xx | **视为未知，直接退出**并记日志 |

「查询失败就放行」是刻意的：退出不能被一次查询卡住。宁可少弹一次框，也不要让用户点不动。

确认框（`dialog.showMessageBox`，`noLink: true`）：

- message：`还有 3 个任务正在运行`
- detail：按类型分行，例如 `对话 1 个 · 终端会话 2 个`，外加一句`退出会中断它们。`
- buttons：`["再等等", "仍然退出"]`，`defaultId: 1`、`cancelId: 0`
  ——默认落在「继续退出」上，因为这是用户已经发起的动作；但 Esc 走「再等等」。
- 选「再等等」→ `event.preventDefault()`，`quitting` 复位，应用留在原地（不关闭窗口）。

需要注意的实现细节：

- **更新流程必须跳过**：`runShellUpdate` 成功后是 `app.quit()`（`main/index.ts` 里那处），
  这条 quit 是安装器要接管，绝不能弹框。加一个模块级 `quitReason`，更新成功后置为
  `"update"` 再 quit。
- **防重入**：Cmd+Q 连点会并发进 `before-quit`。用一个 `guardInFlight` promise 复用同一次
  查询；`quitting` 标志继续负责「已经在停机中」。
- **信号路径不弹框**（`shutdownFromSignal` 里没有 UI，也没有窗口），保持现在直接停机的行为。
- **查询方式**：主进程内 `net.fetch(\`http://127.0.0.1:${backendPort}/api/runtime/activity\`)`，
  不走 `octop://` 协议代理（那是渲染层的入口，主进程直连更短也更明确）。
- `apiAdmissionClosed`（更新中）时视同 `backendPort === 0`，直接退出。
- 现有 `before-quit` 已经在做「先关 WS 中继 → 停 Sidecar → `app.quit()`」；guard 只是插在
  它前面的一次异步判断，停机顺序不变。

### 3.4 时序

```text
用户 Cmd+Q
  └─ before-quit (reason = user)
       ├─ backendPort == 0 ────────────────► 停机 → 退出
       └─ GET /api/runtime/activity (≤800ms)
            ├─ 超时/错误 ─────────────────► 停机 → 退出（记日志）
            ├─ busy = false ───────────────► 停机 → 退出
            └─ busy = true ──► 原生确认框
                                 ├─ 再等等 ──► preventDefault，应用继续跑
                                 └─ 仍然退出 ─► 停机 → 退出
```

## 4. 实施步骤

| PR | 内容 | 验收 |
|---|---|---|
| 1 | `infra/runtime_activity.py` + 两处插桩 + 单测 | 跑一个 turn 时 `snapshot()` 有且只有一条；turn 结束/取消/异常后归零 |
| 2 | `api/routers/runtime_activity.py` + `deps.py` exempt + `common/desktop.py` 提取 + 测试 | 非壳 403、非 loopback 403、字段白名单 |
| 3 | `main/quit-guard.ts` + `index.ts` 接线 + 决策矩阵单测 | 矩阵 6 种情况全绿 |
| 4 | 文档：§3.4 去掉「未实现」、README 补一段、本文标记为已落地 | — |

PR 1/2 可以合并成一个；PR 3 依赖 1/2 的接口先合入（本地联调不影响）。

## 5. 测试与验收

单测（壳侧，`node --test`）：

- 6 种决策矩阵；
- 「再等等」后再次 Cmd+Q 会重新查询一次（不复用上次结果）；
- `reason = "update"` 时不会发起任何请求（用 spy 断言 0 次调用）。

手工验收：

1. 终端页开一个 `sleep 300`，Cmd+Q → 弹框显示「终端会话 1 个」；
2. 选「再等等」，确认窗口还在、终端还在跑；
3. 再 Cmd+Q，选「仍然退出」→ 中继和 Python 都退出，无孤儿进程（`ps` 确认）；
4. 空闲状态 Cmd+Q → 不弹框直接退出；
5. 设置页触发一次「检查更新 → 立即升级」→ 全程不弹框。

## 6. 风险与取舍

- **误报**：注册表只统计「真在执行的 turn / 活着的 PTY」，不用连接数，所以不会因为页面开着
  就报忙碌。但 PTY 会被算作忙碌——这是有意的，一条正在跑的命令被打断比多点一次框更糟。
- **漏报**：注册表是我们自己插桩的，将来若新增一条不经过 `GlobalProcessor` 的执行路径
  （例如直接在某个路由里跑长任务），它不会被统计。插桩点必须写进 §3.4，评审新执行路径时
  对照检查。
- **退出变慢**：最坏多 800ms。只发生在用户主动退出且 Sidecar 活着时。
- **回滚**：三个 PR 互相独立，壳侧可以单独 revert 回到「不问直接退」，后端接口留着无害。

## 7. 未决问题

1. **HITL 等待中的 turn 算不算在跑？** 建议算——它在等用户输入，退出同样会丢。
2. **cron 的自动任务算不算？** 建议算（它就是一次 turn），但对「用户能不能打断」的文案要区分：
   自动任务被打断会在下次触发时重来，可以只计数不单列。
3. **是否要提供「退出前等我这个任务跑完」的选项？** 本期不做：需要停机与任务生命周期耦合，
   而 §3.4 的目标只是「别静默打断」。
