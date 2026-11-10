# octop-memory-native

DSH（DeepSeek Harness）原生「记忆共享」插件：**每轮开始前自动召回 octop 共享记忆并注入上下文，轮末把本轮的对话增量上报回 octop**，全程在 DSH 进程内完成。

它是「记忆共享模式」的 hooks 实现（`~/.dsh/hooks/dsh/*.mjs` + Claude Code hook 桥）的替代品：hooks 方案要背 5 个外部依赖（外部 Node 子进程、会话沙箱写权限、`--use-system-ca`、hook 方言映射、以及和 harness 版本锁死的 hook 桥包），任意一个变化都会让它**静默失效**。本插件只用 harness 的一等公民接缝。

## 为什么更稳

| | hooks 方案 | 本插件 |
|---|---|---|
| 执行位置 | 外部 shell 子进程（Claude Code hook 方言） | 进程内 Cordis 插件 |
| 版本耦合 | 依赖 `@deepseek-ai/dsh-hooks-claude-code` 精确版本，harness 升级即被闸门 deny | 无 `@deepseek-ai/*` 依赖声明，不进版本闸门 |
| 抓取/写日志 | 受会话沙箱限制，`~/.dsh/hooks` 不可写时静默降级到 `$TMPDIR` | 用 `ctx.logger`，失败可见 |
| CA/代理 | 需要 `NODE_OPTIONS=--use-system-ca` | host 进程已由 dsh-mcp 做进程级 CA 合并 |
| 召回质量 | 整句当 query，服务端短语匹配 → 0 命中 | 关键词扇出（多路单 token 查询 + 合并去重） |
| 状态 | 外部 json offset 文件 | 进程内按 session 去重 + turn 幂等 |

## 接缝

- **召回**：`agent/pre-step`（waterfall，per-agent ctx）。每轮第一个 step、拿到新 user message 后，用关键词扇出查 `memory_search`，命中则以 `createUserMessage({ source: { kind: 'octop-memory-native', form: 'snapshot', sections } })` 注入本轮。做法与内置的 `time-context` 插件同构。
- **上报**：`session/event` 的 `turn/end`（durable、post-commit）。收集该轮 user/assistant 文本，POST `memory_capture`（text 模式，user/assistant 分字段），按 turn 去重、按 session 幂等。
  上报/召回前都会先剥掉 Harness 自动注入的运行时长文（`Current runtime context…`、`<system-reminder>…`、子会话 delegate 前言），避免把技能清单/工作目录等噪声写进记忆、也避免它们污染召回关键词。
- 没有新事件类型、不写 session 日志，因此不影响 fork / resume / replay。

## 认证

认证是**用户级 token**：token 随 `Authorization: Bearer <token>` 发送（`tokenHeader` 可改名，非 `Authorization` 的头名按原样写入）。token 在服务端已经绑定一个专家，所以客户端**不需要也不发送任何身份头**（用户标识或专家标识都不传）。

## 配置

行 id：`octop-memory-native`。可在 profile 的 `cordis.patch.yml` 用同 id 覆盖（octop 的 DSH 安装器会自动写）：

```yaml
- id: octop-memory-native
  config:
    endpoint: https://<your-octop-host>/mcp/memory/
    token: omcp_xxxxxxxx
    tokenHeader: Authorization
```

`token` 留空时会回退读 `~/.dsh/hooks/config.json`（octop 安装器写的那个），方便从 hooks 方案平滑迁移。

主要开关：`recallEnabled` / `captureEnabled` / `recallMaxHits` / `recallMaxChars` / `recallTimeoutMs` / `recallMaxQueries` / `recallCorpus` / `recallDedupeTtlMs` / `captureMaxChars` / `captureTimeoutMs` / `sessionPrefix` / `source`。

## 安装

本目录就是插件源码（`src/octop/infra/agents/dsh_native_plugin/`），包名是 `octop-memory-native`。

```bash
# 1) 装成 profile 的 bundle（本地目录用 link:）
dsh plugin --profile desktop add link:/path/to/octop/src/octop/infra/agents/dsh_native_plugin

# 2) 把 bundle 名加进该 profile package.json 的 dsh.profile.bundles，然后重启 DSH
```

octop 的 DSH 安装器会自动完成上面两步并写入 config。

## 验证

1. 新会话问一句命中历史记忆的话 → 本轮 request 里能看到 `[octop memory] …` 注入块（`source.kind = octop-memory-native`）；
2. 轮末在 octop 记忆库（`memory_search` / `memory_raws`）能看到本轮 `session_id = dsh:<sessionId>` 的记录；
3. 插件日志（host 日志）：`octop-memory-native: recall turn=… hits=… fresh=…`；
4. **「装了却没生效」先分清是哪一类**：加载探针 `/tmp/octop-memory-native.log` 在每次模块 import / `apply()` 时写一行 pid。
   - 日志里**没有**当前 DSH 进程的 pid → 插件没被 loader 导入（查 profile `dsh.profile.bundles`、`cordis.patch.yml` 里有没有 `disabled: true`、版本闸门）；
   - 有 pid 但 host 日志出现 `loaded but NOT configured` → 加载正常、配置缺失（重跑 octop 的 DSH 安装器，或补 profile patch 里的 config 块）。

## 回滚

从 profile 的 `dsh.profile.bundles` 移除 `octop-memory-native`（或 `dsh plugin --profile desktop remove octop-memory-native`）并重启即可；hooks 方案可随时切回。
