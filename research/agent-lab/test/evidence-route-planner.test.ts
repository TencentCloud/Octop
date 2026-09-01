import assert from 'node:assert/strict'
import { mkdtemp, writeFile } from 'node:fs/promises'
import os from 'node:os'
import path from 'node:path'
import test from 'node:test'

import { createUserMessage } from '../src/core/messages.js'
import { compileEvidenceBundle } from '../src/memory/evidence-bundle.js'
import { planEvidenceRoute } from '../src/memory/evidence-route-planner.js'
import { createMemoryAgent } from '../src/memory/runtime.js'
import { FileMemoryStore } from '../src/memory/store.js'

function source(ref: string, observedAt = '2026-07-01T00:00:00.000Z') {
  return { type: 'conversation' as const, ref, observed_at: observedAt }
}

test('evidence bundle removes advice-intent noise and expands phone battery aliases', async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), 'battery-alias-'))
  const store = new FileMemoryStore(root)
  await store.initialize()
  await store.create({
    kind: 'episodic',
    title: 'Travel charging accessories',
    summary: 'The user owns a portable power bank and wireless charging pad.',
    content: 'user: I bought a portable power bank and a wireless charging pad for travel.',
    source: source('charging-session'),
  })

  const bundle = await compileEvidenceBundle(
    store,
    "I've been having trouble with the battery life on my phone lately. Any tips?",
  )

  assert.deepEqual(bundle.query_facets, ['battery', 'life', 'phone'])
  assert.equal(bundle.covered_facets.includes('battery'), true)
  assert.equal(bundle.covered_facets.includes('phone'), true)
  assert.equal(bundle.source_clusters[0]?.source_ref, 'charging-session')
})

test('evidence planner composes temporal and aggregation operations without a gold label', async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), 'evidence-planner-'))
  const store = new FileMemoryStore(root)
  await store.initialize()
  await store.create({
    kind: 'episodic',
    title: 'March flights',
    summary: 'The user flew United four times in March.',
    content: 'user: I flew with United Airlines four times in March.',
    source: source('march-flights'),
  })
  await store.create({
    kind: 'episodic',
    title: 'April flights',
    summary: 'The user flew American Airlines in April.',
    content: 'user: I flew with American Airlines twice in April.',
    source: source('april-flights'),
  })

  const plan = await planEvidenceRoute(
    store,
    'Which airline did I fly with the most in March and April?',
    '2026-07-15',
  )

  assert.equal(plan.route, 'fork_reader')
  assert.equal(plan.profiles.includes('timeline'), true)
  assert.equal(plan.profiles.includes('aggregate'), true)
  assert.equal(plan.profiles.includes('cross_session_linking'), true)
  assert.equal(plan.operations.includes('aggregate_requested_relation'), true)
  assert.equal('question_type' in plan, false)
})

test('evidence preview detects complementary cross-session evidence for a simple-looking question', async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), 'evidence-preview-'))
  const store = new FileMemoryStore(root)
  await store.initialize()
  await store.create({
    kind: 'episodic',
    title: 'Poster presentation',
    summary: 'The user presented a thesis research poster at their first conference.',
    content: 'user: I presented a poster on my thesis research at my first research conference.',
    source: source('poster-session'),
  })
  await store.create({
    kind: 'episodic',
    title: 'Conference location',
    summary: 'The first research conference was at Harvard University.',
    content: 'user: I attended my first research conference at Harvard University.',
    source: source('university-session'),
  })

  const plan = await planEvidenceRoute(
    store,
    'At which university did I present a poster on my thesis research?',
  )

  assert.equal(plan.preview.source_cluster_count >= 2, true)
  assert.equal(plan.preview.complementary_sources, true)
  assert.equal(plan.profiles.includes('cross_session_linking'), true)
})

test('evidence planner recognizes implicit personalized-advice wording', async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), 'preference-planner-'))
  const store = new FileMemoryStore(root)
  await store.initialize()
  await store.create({
    kind: 'episodic',
    title: 'High school memories',
    summary: 'The user enjoyed debate and economics in high school.',
    content: 'user: I loved debate team and AP economics in high school.',
    source: source('high-school-session'),
  })

  const questions = [
    'Do you think it would be a good idea to attend my high school reunion?',
    'My bike performs better during Sunday group rides. Could there be a reason for this?',
    'I am deciding whether to buy a NAS now or wait. What do you think?',
  ]
  for (const [index, question] of questions.entries()) {
    const plan = await planEvidenceRoute(store, question)
    assert.equal(plan.profiles.includes('preference_profile'), true, question)
    if (index < 2) assert.equal(plan.profiles.includes('state_resolution'), false, question)
  }
})

test('evidence preview routes competing sourced values through state resolution', async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), 'state-preview-'))
  const store = new FileMemoryStore(root)
  await store.initialize()
  await store.create({
    kind: 'episodic',
    title: 'Earlier support group count',
    summary: 'The user attended three bereavement support group sessions.',
    content: 'user: I attended three sessions. assistant: You attended 3 bereavement support group sessions.',
    source: source('support-group-old', '2026-06-01T00:00:00.000Z'),
  })
  await store.create({
    kind: 'episodic',
    title: 'Updated support group count',
    summary: 'The user attended five bereavement support group sessions.',
    content: 'user: I attended 5 sessions of the bereavement support group.',
    source: source('support-group-new', '2026-07-01T00:00:00.000Z'),
  })

  const plan = await planEvidenceRoute(store, 'How many bereavement support group sessions did I attend?')

  assert.equal(plan.preview.state_conflict.detected, true)
  assert.equal(plan.preview.state_conflict.value_kinds.includes('number'), true)
  assert.equal(plan.profiles.includes('state_resolution'), true)
  assert.equal(plan.operations.includes('order_competing_states'), true)
})

test('planner mode keeps raw memory tools out of the parent answer phase', async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), 'planner-orchestrator-'))
  const configPath = path.join(root, 'memory-agent.config.json')
  await writeFile(configPath, JSON.stringify({
    memoryRoot: './data',
    context: { maxItems: 4, maxChars: 4_000, minScore: 0.01 },
    compression: { maxChars: 8_000, preserveRecentChars: 2_000, summaryMaxChars: 1_000 },
  }), 'utf8')
  const agent = await createMemoryAgent(configPath)
  const memory = await agent.store.create({
    kind: 'episodic',
    title: 'Current shampoo',
    summary: 'The user currently uses Trader Joes shampoo.',
    content: 'user: I currently use shampoo from Trader Joes.',
    source: source('shampoo-session'),
  })

  let parentToolNames: string[] | null = null
  const model = {
    async next(messages: readonly import('../src/core/messages.js').Message[], context: import('../src/core/agent-loop.js').ModelContext) {
      const isChild = messages.some(message =>
        message.role === 'system' && message.content.includes('Evidence Reader Subagent'))
      if (isChild) {
        return { role: 'assistant' as const, content: JSON.stringify({
          schema_version: '1.0',
          answerability: 'answerable',
          query_kind: 'state_latest',
          sourced_facts: [{
            fact: 'The user currently uses Trader Joes shampoo.',
            source_memory_id: memory.id,
            source_ref: 'shampoo-session',
            evidence_quote: 'I currently use shampoo from Trader Joes.',
            confidence: 1,
          }],
          entity_ledger: [],
          event_ledger: [],
          pending_action_ledger: [],
          timeline: [],
          conflicts: [],
          exclusions: [],
          missing_information: [],
        }) }
      }
      parentToolNames = context.tools.map(tool => tool.name)
      return { role: 'assistant' as const, content: 'Trader Joes.' }
    },
  }

  const result = await agent.run(
    model,
    [createUserMessage('Question date: 2026-07-15\nQuestion: What brand of shampoo do I currently use?')],
    3,
    undefined,
    { evidencePlanner: true, orchestratorOnly: true, finalAnswerWithoutTools: true },
  )

  assert.deepEqual(parentToolNames, [])
  assert.equal(result.output, 'Trader Joes.')
  const routed = result.events.find(event =>
    event.type === 'tool_call_start' && event.toolName === 'ForkEvidenceReader')
  assert.equal(routed?.type, 'tool_call_start')
  if (routed?.type === 'tool_call_start') {
    assert.equal((routed.input.profiles as string[]).includes('state_resolution'), true)
    assert.equal('question_type' in routed.input, false)
  }
})
