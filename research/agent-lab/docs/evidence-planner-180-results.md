# Evidence Planner 180-Episode Results

## Protocol

- Dataset: `longmemeval_s_cleaned.json`
- Fixed seed: `evidence-planner-v1`
- Selection: six question types, 30 episodes per type, 180 total
- Runtime input: conversation history, timestamps, question, and question date
- Runtime exclusions: no `question_type`, no `_abs` suffix check, no gold tags, no reference answer
- Parent role: orchestration and one tool-free answer turn only
- Reader role: all raw `MemorySearch`, `MemoryRead`, and evidence-bundle access
- Model: `glm-5.2`
- Reader output budget: 4096 tokens

The subset is a fixed regression set sampled from the same 500 episodes used in
earlier experiments. It is not an unseen publication test set.

## Leakage Audit

| Check | Result |
|---|---:|
| Episodes generated | 180 / 180 |
| Unique episode IDs | 180 / 180 |
| Generation errors | 0 |
| Reader calls | 180 / 180 |
| Parent raw-memory tool violations | 0 |
| Runtime gold-label availability | false |
| Gold-like keys in Reader tool inputs | 0 |
| Parent model turns | exactly 1 per episode |

## Scores

The primary robust score uses two complete independent judge passes and a third
vote only for the 17 disagreements. The two complete passes scored 142/180
(`78.9%`) and 143/180 (`79.4%`). Majority voting scored 149/180 (`82.8%`).

| Type | Planner majority | Blind matched subset | Oracle matched subset |
|---|---:|---:|---:|
| single-session-user | 29 / 30 | 30 / 30 | 29 / 30 |
| single-session-assistant | 29 / 30 | 20 / 30 | 30 / 30 |
| single-session-preference | 19 / 30 | 17 / 30 | 28 / 30 |
| temporal-reasoning | 24 / 30 | 9 / 30 | 30 / 30 |
| multi-session | 25 / 30 | 10 / 30 | 27 / 30 |
| knowledge-update | 23 / 30 | 24 / 30 | 29 / 30 |
| **Overall** | **149 / 180 (82.8%)** | **110 / 180 (61.1%)** | **173 / 180 (96.1%)** |

The matched Blind and Oracle values come from earlier model runs on the same
episode IDs, so they are strong regression references rather than a controlled
same-run causal A/B.

## Reader Health

- Valid structured reports: 166/180 (`92.2%`)
- Invalid structured reports: 14/180 (`7.8%`)
- Majority SR with valid reports: 145/166 (`87.3%`)
- Majority SR with invalid reports: 4/14 (`28.6%`)

Invalid or truncated Reader reports account for 10 of the 31 majority-vote
failures. Report validity remains a high-value reliability gate.

## Routing Findings

- All 30 temporal questions received the `timeline` profile.
- All 30 multi-session questions received `cross_session_linking`; 29 also
  received `aggregate`.
- All 30 assistant questions received `assistant_recall` and preferred
  assistant evidence.
- Only 26/30 preference questions received `preference_profile`. All four
  missed preference routes failed.
- Only 13/30 knowledge-update questions received `state_resolution`, showing
  that question wording alone does not expose many state transitions.
- `cross_session_linking` fired on 160/180 episodes. The preview currently has
  high recall but weak selectivity.

## Conclusions

1. Moving raw memory reading out of the parent loop is effective. It eliminated
   repeated parent retrieval and raised matched-subset SR from 61.1% to 82.8%.
2. The largest gains are multi-session, temporal, and prior-assistant recall.
3. Routing is necessary but not sufficient. Preference synthesis and state
   update interpretation remain weak even when the Reader is called.
4. The next implementation should add preference-specific final synthesis,
   detect evidence-level state conflicts in the preview, and reduce invalid
   reports with stricter bounded output or staged ledger compilation.
5. A fresh unseen gate is still required before treating the gain as a general
   benchmark improvement.

## Artifacts

- `eval/subsets/longmemeval-six-types-30.json`
- `work/eval-runs/agent-lab-planner-six-types180-v1/final/generation-summary.json`
- `work/eval-runs/agent-lab-planner-six-types180-v1/final/qa-agent-lab.jsonl`
- `work/eval-runs/agent-lab-planner-six-types180-v1/final/qa-judge-glm52.jsonl`
- `work/eval-runs/agent-lab-planner-six-types180-v1/final/qa-judge-glm52-run2.jsonl`
- `work/eval-runs/agent-lab-planner-six-types180-v1/final/qa-judge-glm52-majority.jsonl`
