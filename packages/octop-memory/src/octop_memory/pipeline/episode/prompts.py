"""Prompts for the Episode (diary) extractor.

Edit ``EPISODE_EXTRACTOR_VERSION`` whenever the prompt body changes — the
version is persisted on every Episode row so output can be replayed
against new prompt versions later.
"""

from __future__ import annotations

EPISODE_EXTRACTOR_VERSION = "episode/v1"
"""Version tag persisted on every Episode (`extractor_version`)."""

_FEW_SHOT = """\
Few-shot examples (study the format, then process the actual input):

Example 1 — emotional family event
INPUT:
[
  {"event_id": "raw-1", "event_type": "user_message",
   "content": "今天和老婆吵架了，她说我天天加班不顾家，我气炸了",
   "timestamp": "2026-06-20T22:00:00Z"},
  {"event_id": "raw-2", "event_type": "assistant_message",
   "content": "听起来你很委屈，要不要说说？",
   "timestamp": "2026-06-20T22:00:05Z"}
]
OUTPUT:
{
  "episodes": [
    {
      "summary": "用户和老婆吵架，妻子认为他加班太多不顾家，他感到愤怒和委屈",
      "verbatim_quote": "今天和老婆吵架了，她说我天天加班不顾家，我气炸了",
      "quote_event_id": "raw-1",
      "source_refs": ["raw-1"],
      "occurred_at": "2026-06-20T22:00:00Z",
      "emotion": "angry",
      "intensity": 4,
      "people": ["老婆"],
      "topics": ["家庭", "冲突", "工作"]
    }
  ]
}

Example 2 — positive work milestone
INPUT:
[
  {"event_id": "raw-3", "event_type": "user_message",
   "content": "项目终于上线了，老板还表扬了我，今天好开心",
   "timestamp": "2026-06-21T18:00:00Z"}
]
OUTPUT:
{
  "episodes": [
    {
      "summary": "用户负责的项目成功上线，得到老板表扬，心情非常愉快",
      "verbatim_quote": "项目终于上线了，老板还表扬了我，今天好开心",
      "quote_event_id": "raw-3",
      "source_refs": ["raw-3"],
      "occurred_at": "2026-06-21T18:00:00Z",
      "emotion": "happy",
      "intensity": 4,
      "people": ["老板"],
      "topics": ["工作", "成就"]
    }
  ]
}

Example 3 — pure technical question, NOT extracted
INPUT:
[
  {"event_id": "raw-4", "event_type": "user_message",
   "content": "Python 里 dict 怎么按 value 排序？",
   "timestamp": "2026-06-22T10:00:00Z"}
]
OUTPUT:
{"episodes": []}

Example 4 — mixed: pure-fact statement, NOT extracted (atom layer's job)
INPUT:
[
  {"event_id": "raw-5", "event_type": "user_message",
   "content": "我老婆叫小丽，今年28岁",
   "timestamp": "2026-06-23T09:00:00Z"}
]
OUTPUT:
{"episodes": []}
"""


_PROMPT_TEMPLATE = """\
You are an Episode Extractor — you write the user's life-diary entries.

Your job: read a batch of conversation messages and extract first-person
**lived events and feelings** worth remembering as diary entries. Output
Episode JSON only.

Episode = "what happened to the user today and how they felt about it".

You MUST extract:
- Emotional events: arguments, celebrations, anxieties, milestones,
  health concerns, family/work/relationship dynamics
- Personal life events: travel, illness, achievements, setbacks, plans
  the user actually made or did
- Strong opinions / reflections the user voiced about their own life
- The implicit emotion behind the statement when it's clear

You MUST NOT extract:
- Pure technical questions ("how does X work")
- Pure factual statements about other entities ("my wife is named XiaoLi"
  — that's the atom layer's job)
- Tool-related chatter / coding tasks
- Generic small talk about weather, time of day, greetings
- Anything the assistant said (only extract user-experienced events)

Output schema for each episode:
- summary: <=120 char neutral 3rd-person description ("用户...")
- verbatim_quote: <=200 char direct quote from a user_message
- quote_event_id: the event_id that quote came from (must be in the input)
- source_refs: list of event_ids that justify this episode (>=1)
- occurred_at: ISO datetime — default to the quote event's timestamp
- emotion: one of [neutral, happy, sad, angry, anxious, excited,
  frustrated, grateful, tired, reflective]
- intensity: 1..5 (1=mild, 3=clearly felt, 5=overwhelming)
- people: short list of names/relationships mentioned ("老婆", "老板",
  "妈妈", "小李"). Empty list is fine. Pronouns alone don't count.
- topics: short tags like ["家庭"], ["工作"], ["健康"], ["朋友"],
  ["项目"], ["情绪"]. Empty list is fine.

Rules:
- Output JSON only. No prose, no markdown fences.
- HARD LIMIT: at most {max_episodes} episodes. If fewer events warrant
  extraction, output fewer.
- If no episodes warrant extraction, output {{"episodes": []}}.
- One episode = one coherent event. Don't merge two unrelated events
  ("老婆吵架" and "项目上线") into one row.
- Do not include events the assistant brought up; only first-person user
  experiences.

{few_shot}

Now process the actual input. Output JSON only.

INPUT (raw events to extract from):
{events_json}

OUTPUT:
"""


def render_episode_prompt(events_json: str, *, max_episodes: int = 10) -> str:
    return _PROMPT_TEMPLATE.format(
        max_episodes=max_episodes,
        few_shot=_FEW_SHOT,
        events_json=events_json,
    )


__all__ = ["EPISODE_EXTRACTOR_VERSION", "render_episode_prompt"]
