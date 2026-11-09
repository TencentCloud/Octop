/**
 * 纯文本工具：召回关键词抽取、结果合并、注入正文渲染。
 * 这个文件不 import 任何 Harness 包，所以 `node --test` 能直接跑。
 */

/** 中文停用词：只用于召回关键词抽取，宁缺勿滥。 */
const STOPWORDS = new Set([
  '请问', '帮我', '帮忙', '一下', '看看', '看下', '检查', '这个', '那个', '这些', '那些',
  '我们', '你们', '他们', '什么', '怎么', '为什么', '哪个', '哪些', '是否', '可以', '能否',
  '需要', '想要', '现在', '然后', '还有', '以及', '或者', '如果', '因为', '所以', '但是',
  '就是', '这种', '那种', '一个', '一些', '已经', '进行', '相关', '问题', '情况', '内容',
])

/** 中文停用词切分：先按停用词切断再取片段，避免把「哪几个/涉及」这类词当关键词。 */
const CJK_STOP_PATTERN = [...STOPWORDS]
  .sort((a, b) => b.length - a.length)
  .map((word) => word.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'))
  .join('|')
const CJK_STOP_RE = new RegExp(CJK_STOP_PATTERN, 'g')

/** 把中文长句切成候选实体词：去停用词、按非中文断开、保留 2-8 字片段。 */
export function cjkChunks(text) {
  return String(text || '')
    .replace(CJK_STOP_RE, ' ')
    .split(/[^\u4e00-\u9fa5]+/)
    .map((chunk) => chunk.trim())
    .filter((chunk) => chunk.length >= 2 && chunk.length <= 8)
}

/** 从一段文本里抽取召回关键词（ASCII 标识符/数字优先，其次中文实体片段）。 */
export function tokensFromPrompt(text) {
  const source = String(text || '')
  const ascii = source.match(/[A-Za-z0-9_]+(?:[-./:][A-Za-z0-9_]+)*/g) || []
  const tokens = []
  const push = (value) => {
    const token = String(value || '').trim()
    if (token.length < 2 || STOPWORDS.has(token)) return
    if (!tokens.includes(token)) tokens.push(token)
  }
  // ASCII 标识符（含 8503、rc.5、fh_stepwise_hotel_tokens、x7mm65）通常是最强信号
  for (const token of ascii) if (/[0-9]|[._/-]/.test(token)) push(token)
  for (const token of cjkChunks(source)) push(token)
  for (const token of ascii) push(token)
  return tokens
}

/** 合并多路查询结果：按 path 去重，命中次数多的优先，最后按配置截断。 */
export function mergeHits(results, maxHits) {
  const merged = new Map()
  for (const hits of results) {
    for (const hit of hits || []) {
      const key = hit?.path || hit?.source_id
      if (!key) continue
      const existing = merged.get(key)
      if (existing) existing.score += 1
      else merged.set(key, { hit, score: 1 })
    }
  }
  return [...merged.values()]
    .sort((a, b) => b.score - a.score)
    .slice(0, Math.max(1, maxHits))
    .map((entry) => entry.hit)
}

/** 渲染注入正文：带层/时间/片段，末尾给 memory_get 的用法。 */
export function renderHits(hits, maxChars) {
  const lines = [
    '[octop memory] 与本轮相关的共享记忆（来自团队记忆库，按相关度排序）：',
  ]
  let used = lines[0].length
  for (const hit of hits) {
    const when = String(hit.occurred_at || '').slice(0, 19).replace('T', ' ')
    const layer = hit.layer || hit.role_hint || 'memory'
    const snippet = String(hit.snippet || '').replace(/\s+/g, ' ').trim()
    if (!snippet) continue
    const line = `- [${layer}${when ? ` @ ${when}` : ''}] ${snippet}`
    if (used + line.length > maxChars) break
    lines.push(line)
    used += line.length + 1
  }
  if (lines.length === 1) return ''
  lines.push(
    `（需要原文/证据用 memory_get(path=…)；与本次工作无关则忽略。）`,
  )
  return lines.join('\n')
}

export { STOPWORDS }

/** Harness 自动注入的易变上下文：子会话 prompt、系统提示、运行时长文。上报/召回前剥掉。 */
const VOLATILE_CUT_MARKERS = [
  '\nCurrent runtime context.',
  '\n<system-reminder>',
  '\nYour parent agent id is',
  '\nYou are a delegated subagent:',
  '\nCurrent DeepSeek Harness implementation checkout:',
]

/**
 * 去掉 Harness 注入的运行时长文，只保留人/agent 真正写的内容。
 * @param {string} text 原始消息文本
 * @returns {string} 清洗后的文本（可能为空）
 */
export function stripHarnessContext(text) {
  let out = String(text || '')
  out = out.replace(/<system-reminder>[\s\S]*?<\/system-reminder>/g, '')
  let cut = out.length
  for (const marker of VOLATILE_CUT_MARKERS) {
    const at = out.indexOf(marker)
    if (at >= 0 && at < cut) cut = at
  }
  return out.slice(0, cut).replace(/[ \t]+/g, ' ').replace(/\n{3,}/g, '\n\n').trim()
}
