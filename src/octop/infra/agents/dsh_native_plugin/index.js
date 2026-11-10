/**
 * octop-memory-native — DSH 原生「记忆共享」插件（替代 Claude Code hook 桥接）。
 *
 * 两个接缝都在进程内，不拉起子进程、不依赖 hook 方言：
 *   · 召回：`agent/pre-step`（waterfall）在每轮第一个 step 前查一轮 octop memory，
 *     有命中就作为一条带 source 的 user message 注入本轮（`createUserMessage`），
 *     与 `time-context` 的做法一致。
 *   · 上报：监听 `session/event` 的 `turn/end`（durable、post-commit），把该轮的
 *     user/assistant 文本增量 POST 给 `memory_capture`；按 turn 去重，失败只告警。
 *
 * 设计取舍见 README.md；所有网络失败都必须静默降级，绝不阻塞会话。
 */

import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { randomUUID } from 'node:crypto'
import z from '@deepseek-ai/schemastery'
import { mergeHits, renderHits, stripHarnessContext, tokensFromPrompt } from './lib/text.js'

/**
 * 与 dsh-llm 的 createUserMessage 等价的最小实现：`{...input, role:'user', id}`。
 *
 * 不 import `@deepseek-ai/dsh-llm`：该包不在 profile 的 node_modules 里，只能靠 host 的
 * 私有解析映射加载（插件若是 symlink/位于 bundles 目录就会 ERR_MODULE_NOT_FOUND）。
 * 留 `@deepseek-ai/schemastery` 一个依赖即可——它在 profile node_modules 里能正常解析。
 */
function createUserMessage(input) {
  return Object.freeze({ ...input, role: 'user', id: randomUUID() })
}

/** 加载探针：确认模块真的被 host 进程 import（排查插件 inactive 用）。 */
function probe(line) {
  try {
    fs.appendFileSync('/tmp/octop-memory-native.log', `${new Date().toISOString()} ${line}\n`)
  } catch {
    // 探针失败不影响插件
  }
}

probe(`module-load pid=${process.pid}`)

/** Loader 诊断用的插件名。 */
export const name = 'octop-memory-native'

/** 无必需 Service：只用事件接缝，profile 里缺任何可选服务都不影响激活。 */
export const inject = []

/**
 * Config 保持扁平：schemastery 的嵌套对象在旧版 Loader 上有兼容风险，
 * 而这些都是运维可调参数，扁平更好写 patch。
 */
export const Config = z.object({
  // ── 连接 ────────────────────────────────────────────────────────────────
  endpoint: z.string().default(''),
  token: z.string().default(''),
  tokenHeader: z.string().default('Authorization'),
  /** token 为空时回退读这个文件（octop 安装器写的 hooks config.json）。 */
  configFallbackPath: z.string().default('~/.dsh/hooks/config.json'),
  // ── 召回 ────────────────────────────────────────────────────────────────
  recallEnabled: z.boolean().default(true),
  recallMaxHits: z.number().default(4),
  recallMaxChars: z.number().default(1200),
  recallTimeoutMs: z.number().default(4000),
  /** 关键词扇出：每个 token 单独查一次，再合并去重（服务端是短语匹配，整句必 0 命中）。 */
  recallMaxQueries: z.number().default(4),
  recallCorpus: z.string().default('all'),
  recallMinPromptChars: z.number().default(4),
  recallDedupeTtlMs: z.number().default(300000),
  // ── 上报 ────────────────────────────────────────────────────────────────
  captureEnabled: z.boolean().default(true),
  captureTimeoutMs: z.number().default(15000),
  captureMaxChars: z.number().default(8000),
  /** session_id 前缀，与旧 hook 保持一致，避免同会话在服务端变成两条记录。 */
  sessionPrefix: z.string().default('dsh:'),
  source: z.string().default('dsh:octop-memory-native'),
})

const DAY_MS = 24 * 60 * 60 * 1000

export { mergeHits, renderHits, tokensFromPrompt } from './lib/text.js'

/** 一条 message 里所有 text block 拼接。 */
function textOf(content) {
  if (!Array.isArray(content)) return ''
  return content
    .filter((block) => block && block.type === 'text' && typeof block.text === 'string')
    .map((block) => block.text)
    .join('\n')
    .trim()
}

/** 读 fallback 配置文件（hooks 安装器写的那种），失败返回空对象。 */
function readFallbackConfig(filePath) {
  try {
    const expanded = filePath.startsWith('~') ? path.join(os.homedir(), filePath.slice(1)) : filePath
    return JSON.parse(fs.readFileSync(expanded, 'utf8'))
  } catch {
    return {}
  }
}

/** 有效连接配置：显式 Config 优先，缺的字段回退 hooks config.json。 */
export function resolveConnection(config) {
  const fallback = readFallbackConfig(config.configFallbackPath || '')
  const endpoint = (config.endpoint || fallback.url || '').trim()
  const token = (config.token || fallback.token || '').trim()
  const tokenHeader = (config.tokenHeader || fallback.tokenHeader || 'Authorization').trim()
  const client = (config.client || fallback.client || 'dsh').trim()
  return { endpoint, token, tokenHeader, client }
}

function baseHeaders(connection) {
  const headers = {
    'Content-Type': 'application/json',
    Accept: 'application/json, text/event-stream',
  }
  if (connection && connection.client) headers['X-Octop-Client'] = connection.client
  return headers
}

/**
 * token 属于用户：``Authorization``（默认）写成 ``Bearer <token>``，其它头名原样写入。
 * token 在服务端已绑定一个专家，所以客户端不再发送任何身份头（用户或专家）。
 */
function authHeaders(connection) {
  const headers = baseHeaders(connection)
  if (!connection.token) return headers
  const header = connection.tokenHeader || 'Authorization'
  headers[header] = header.toLowerCase() === 'authorization' ? `Bearer ${connection.token}` : connection.token
  return headers
}

/** 一次 JSON-RPC 调用；永不抛错，返回 `{ ok, detail, error, status }`。 */
export async function rpc(connection, method, params, timeoutMs, signal) {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(new Error('octop-memory-native: timeout')), Math.max(1000, timeoutMs))
  const signals = signal ? [controller.signal, signal] : [controller.signal]
  try {
    const response = await fetch(connection.endpoint, {
      method: 'POST',
      headers: authHeaders(connection),
      body: JSON.stringify({ jsonrpc: '2.0', id: 1, method, params }),
      signal: signals.length > 1 ? AbortSignal.any(signals) : signals[0],
    })
    const text = await response.text()
    let payload = text
    for (const line of text.split('\n')) {
      if (line.startsWith('data: ')) {
        payload = line.slice(6)
        break
      }
    }
    let parsed = {}
    try {
      parsed = JSON.parse(payload.slice(payload.indexOf('{'), payload.lastIndexOf('}') + 1))
    } catch {
      // 保留原始 body 供诊断
    }
    return {
      ok: response.ok,
      status: response.status,
      detail: parsed?.result?.structuredContent ?? parsed?.result ?? {},
      error: parsed?.error?.message ?? '',
    }
  } catch (error) {
    return { ok: false, status: 0, detail: {}, error: String(error?.message || error) }
  } finally {
    clearTimeout(timer)
  }
}

/** 单次 memory_search，返回 hits 数组（失败返回空数组）。 */
async function searchOnce(connection, config, query, signal) {
  const result = await rpc(
    connection,
    'tools/call',
    { name: 'memory_search', arguments: { query, corpus: config.recallCorpus, max_results: config.recallMaxHits } },
    config.recallTimeoutMs,
    signal,
  )
  if (!result.ok) return []
  return Array.isArray(result.detail?.hits) ? result.detail.hits : []
}

/** 关键词扇出召回：多路单 token 查询 + 整句兜底，合并去重。 */
export async function recall(connection, config, prompt, signal) {
  const queries = tokensFromPrompt(prompt).slice(0, Math.max(1, config.recallMaxQueries))
  if (!queries.length) {
    const fallback = String(prompt || '').trim().slice(0, 30)
    if (!fallback) return []
    const hits = await searchOnce(connection, config, fallback, signal)
    return mergeHits([hits], config.recallMaxHits)
  }
  const results = await Promise.all(queries.map((query) => searchOnce(connection, config, query, signal)))
  return mergeHits(results, config.recallMaxHits)
}

/**
 * 从 session 事件里取出某一轮的对话文本（用于上报）。
 * user 侧跳过本插件注入的 context，assistant 侧只要 text block。
 */
export function collectTurn(session, turn, injectedKind) {
  const userParts = []
  const assistantParts = []
  for (let seq = session.seq - 1; seq >= 0; seq -= 1) {
    let event
    try {
      event = session.eventAt(seq)
    } catch {
      continue
    }
    if (!event) continue
    if (event.type === 'turn/start' && event.data?.turn === turn) break
    if (event.type === 'user/message') {
      if (event.data?.source?.kind === injectedKind) continue
      const text = stripHarnessContext(textOf(event.data?.content))
      if (text) userParts.push(text)
    } else if (event.type === 'assistant/message' && event.data?.turn === turn) {
      const text = textOf(event.data?.message?.content)
      if (text) assistantParts.push(text)
    }
  }
  return { user: userParts.reverse(), assistant: assistantParts.reverse() }
}

/** 上报一轮对话：memory_capture（text 模式，user/assistant 分字段）。 */
async function captureTurn(connection, config, session, turn, logger) {
  const { user, assistant } = collectTurn(session, turn, name)
  if (!user.length && !assistant.length) return false
  const content = user.join('\n\n').slice(0, config.captureMaxChars)
  const args = { content, source: config.source, session_id: `${config.sessionPrefix}${session.id}` }
  const assistantText = assistant.join('\n\n').slice(0, config.captureMaxChars)
  if (assistantText) args.assistant = assistantText
  const result = await rpc(connection, 'tools/call', { name: 'memory_capture', arguments: args }, config.captureTimeoutMs)
  if (!result.ok) {
    logger?.warn?.(`octop-memory-native: capture turn ${turn} failed http=${result.status} ${result.detail?.error || result.error || ''}`)
    return false
  }
  return true
}

/** 插件入口。 */
export function apply(ctx, config) {
  const state = new Map() // sessionId -> { lastTurn, lastPrompt, lastRecallAt, lastHits:Set<string> }
  const logger = ctx.logger
  probe(`apply pid=${process.pid}`)

  const note = (line) => {
    try {
      logger?.info?.(`octop-memory-native: ${line}`)
    } catch {
      // 日志永远不能影响主流程
    }
  }

  const connection = () => resolveConnection(config)
  const configured = () => {
    const conn = connection()
    return Boolean(conn.endpoint && conn.token)
  }

  // ── 召回：每个 agent 的 pre-step ─────────────────────────────────────────
  const registerAgent = (agent) => {
    if (!agent?.ctx) return
    agent.ctx.effect(() => {
      const off = agent.ctx.on(
        'agent/pre-step',
        async ({ agent: current, messages, turn, step, signal }, next) => {
          const decision = await next()
          try {
            if (!config.recallEnabled || !decision || decision.kind !== 'enter') return decision
            if (step !== 1 || signal?.aborted) return decision
            const proposed = (messages || []).filter((message) => message?.source?.kind === 'user')
            const prompt = proposed
              .map((message) => stripHarnessContext(textOf(message.content)))
              .filter(Boolean)
              .join('\n')
              .trim()
            if (prompt.length < config.recallMinPromptChars) return decision

            const sessionId = current?.session?.id || ''
            const entry = state.get(sessionId) || { lastPrompt: '', lastRecallAt: 0, lastHits: new Set() }
            state.set(sessionId, entry)
            if (entry.lastPrompt === prompt && Date.now() - entry.lastRecallAt < config.recallDedupeTtlMs) {
              return decision
            }
            entry.lastPrompt = prompt
            entry.lastRecallAt = Date.now()
            if (!configured()) return decision

            const hits = await recall(connection(), config, prompt, signal)
            if (!hits.length) return decision
            const text = renderHits(hits, config.recallMaxChars)
            if (!text) return decision
            const fresh = hits.filter((hit) => !entry.lastHits.has(hit.path || hit.source_id))
            for (const hit of hits) entry.lastHits.add(hit.path || hit.source_id)
            if (entry.lastHits.size > 64) entry.lastHits = new Set([...entry.lastHits].slice(-32))
            // 同一批命中重复出现（TTL 内已被注入过）就不再注入，避免噪声
            if (!fresh.length) return decision
            note(`recall turn=${turn} hits=${hits.length} fresh=${fresh.length}`)
            return {
              ...decision,
              messages: [
                ...decision.messages,
                createUserMessage({
                  content: [{ type: 'text', text }],
                  source: { kind: name, form: 'snapshot', sections: [{ name, text }] },
                }),
              ],
            }
          } catch (error) {
            logger?.warn?.(`octop-memory-native: recall failed ${String(error?.message || error)}`)
            return decision
          }
        },
        { prepend: true },
      )
      return () => off?.()
    }, 'octop-memory-native: recall listener')
  }

  ctx.on('agent/created', ({ agent }) => {
    try {
      registerAgent(agent)
    } catch (error) {
      logger?.warn?.(`octop-memory-native: register agent failed ${String(error?.message || error)}`)
    }
  })

  // HMR/热装时已存在的 agent 也要覆盖
  try {
    for (const agent of ctx.get('agents')?.list?.() || []) registerAgent(agent)
  } catch {
    // 没有 agents 服务时忽略
  }

  // ── 上报：turn/end（durable、post-commit）────────────────────────────────
  ctx.on('session/event', (session, event) => {
    try {
      if (!config.captureEnabled || event?.type !== 'turn/end') return
      const turn = event.data?.turn
      if (typeof turn !== 'number' || !configured()) return
      const sessionId = session?.id || ''
      const entry = state.get(sessionId) || { lastTurn: 0, lastPrompt: '', lastRecallAt: 0, lastHits: new Set() }
      state.set(sessionId, entry)
      if (entry.lastTurn >= turn) return
      entry.lastTurn = turn
      void captureTurn(connection(), config, session, turn, logger).catch((error) => {
        logger?.warn?.(`octop-memory-native: capture failed ${String(error?.message || error)}`)
      })
    } catch (error) {
      logger?.warn?.(`octop-memory-native: capture dispatch failed ${String(error?.message || error)}`)
    }
  })

  // 清理会话级缓存，避免长跑进程里无限增长
  ctx.on('session/disposed', (session) => {
    try {
      state.delete(session?.id)
    } catch {
      // ignore
    }
  })

  note(`loaded endpoint=${config.endpoint || '(fallback)'} recall=${config.recallEnabled} capture=${config.captureEnabled}`)
  // 「装了但没配」和「根本没加载」看起来都是"记忆不生效"，但排查方向完全不同：前者要重跑
  // octop 安装器 / 补 profile patch 的 config，后者要查 loader。这里明确喊一次。
  if (!configured()) {
    logger?.warn?.(
      'octop-memory-native: loaded but NOT configured (endpoint / token missing) — recall and capture stay inactive. Run the octop memory setup installer or fill the `octop-memory-native` config block in the profile cordis.patch.yml.',
    )
  }
}
