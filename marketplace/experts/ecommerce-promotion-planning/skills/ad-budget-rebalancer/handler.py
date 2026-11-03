#!/usr/bin/env python3
import sys
from typing import Any, Dict, List, Union

CHANNEL_RULES = {
    'Meta Ads': ['meta', 'facebook', 'instagram', 'fb'],
    'Google Ads': ['google', 'youtube', 'gdn'],
    'Amazon Sponsored': ['amazon', 'ams', 'sponsored'],
    'TikTok Ads': ['tiktok', 'douyin'],
    'Xiaohongshu': ['xiaohongshu', 'rednote', 'xhs', 'xiaohongshu ads'],
}

CAMPAIGN_RULES = {
    'Awareness': ['awareness', 'reach', 'branding', 'awareness', 'video', 'upper funnel'],
    'Consideration': ['consideration', 'traffic', 'engagement', 'mid funnel', 'video views'],
    'Conversion': ['conversion', 'sales', 'dra', 'direct response', 'lower funnel', 'purchase'],
    'Retargeting': ['retarget', 'remarketing', 'rlsa', 'custom audience', 'past visitor'],
}

BudgetInput = Union[str, Dict[str, Any]]


def _score_rules(text: str, rules: Dict[str, List[str]]) -> Dict[str, int]:
    return {name: sum(1 for kw in kws if kw in text) for name, kws in rules.items()}


def _join(items: List[str]) -> str:
    return ', '.join(items) if items else 'Not specified'


class AdBudgetRebalancer:
    def __init__(self, user_input: BudgetInput):
        self.raw = user_input
        self.text = self._normalize_input(user_input)
        self.lower = self.text.lower()
        self.channels = self._detect_channels()
        self.campaign_types = self._detect_campaign_types()
        self.concern = self._detect_concern()

    def _normalize_input(self, user_input: BudgetInput) -> str:
        if isinstance(user_input, dict):
            chunks: List[str] = []
            for key in ['budget', 'channels', 'campaign_types', 'performance', 'concern', 'notes']:
                value = user_input.get(key)
                if not value:
                    continue
                if isinstance(value, list):
                    value = ', '.join(str(v) for v in value)
                chunks.append(f'{key}: {value}')
            return ' | '.join(chunks)
        return str(user_input or '').strip()

    def _detect_channels(self) -> List[str]:
        matched = [name for name, kws in CHANNEL_RULES.items() if any(kw in self.lower for kw in kws)]
        return matched or ['Meta Ads', 'Google Ads']

    def _detect_campaign_types(self) -> List[str]:
        matched = [name for name, kws in CAMPAIGN_RULES.items() if any(kw in self.lower for kw in kws)]
        return matched or ['Awareness', 'Conversion']

    def _detect_concern(self) -> str:
        if any(kw in self.lower for kw in ['drop', 'decline', 'down', 'worse', 'worsening']):
            return 'Performance Decline'
        if any(kw in self.lower for kw in ['rebalance', 'reallocate', 'shift', 'redistribute']):
            return 'Budget Reallocation'
        if any(kw in self.lower for kw in ['review', 'monthly', 'quarterly', 'audit']):
            return 'Periodic Review'
        return 'Budget Diagnosis'

    def _channel_scorecard(self) -> List[Dict[str, str]]:
        default_roas = {'Meta Ads': 2.0, 'Google Ads': 3.0, 'Amazon Sponsored': 4.0, 'TikTok Ads': 1.5, 'Xiaohongshu': 1.2}
        default_cpm = {'Meta Ads': 12, 'Google Ads': 8, 'Amazon Sponsored': 15, 'TikTok Ads': 6, 'Xiaohongshu': 20}
        rows = []
        for ch in self.channels:
            roas = default_roas.get(ch, 2.0)
            cpm = default_cpm.get(ch, 10)
            efficiency = '🟢 Strong' if roas >= 3 else '🟡 Moderate' if roas >= 1.5 else '🔴 Weak'
            recommendation = (
                'Scale +15–25% if ROAS is above platform average'
                if roas >= 3 else
                'Test new creative and audience before scaling'
                if roas >= 1.5 else
                'Diagnose creative, landing page, or audience mismatch before increasing spend'
            )
            rows.append({
                'channel': ch,
                'roas': f'{roas}x',
                'cpm': f'${cpm}',
                'efficiency': efficiency,
                'recommendation': recommendation,
            })
        return rows

    def _campaign_breakdown(self) -> List[Dict[str, str]]:
        awareness = '🟡 Moderate' if 'Awareness' in self.campaign_types else '⚪ Low'
        consideration = '🟡 Moderate' if 'Consideration' in self.campaign_types else '⚪ Low'
        conversion = '🟢 High' if 'Conversion' in self.campaign_types else '⚪ Low'
        retargeting = '🟡 Moderate' if 'Retargeting' in self.campaign_types else '⚪ Low'
        return [
            {'type': 'Awareness', 'recommended_pct': '20–30%', 'current': awareness, 'note': 'Brand building and top-of-funnel reach'},
            {'type': 'Consideration', 'recommended_pct': '20–30%', 'current': consideration, 'note': 'Mid-funnel engagement and traffic'},
            {'type': 'Conversion', 'recommended_pct': '35–50%', 'current': conversion, 'note': 'Direct response and sales'},
            {'type': 'Retargeting', 'recommended_pct': '15–20%', 'current': retargeting, 'note': 'Past visitors and cart abandoners'},
        ]

    def _rebalance_recommendations(self) -> List[str]:
        recs = [
            'Identify the top 2 channels by ROAS and increase each by 15–20% from lower-performing channels.',
            'Shift 10–15% of Awareness spend to Retargeting if new customer acquisition cost is rising.',
            'Test a new creative variant in the weakest channel before reducing budget further.',
            'Set a 7-day ROAS review checkpoint after any reallocation to confirm direction.',
        ]
        if self.concern == 'Performance Decline':
            recs.insert(0, 'Pause the declining channel for 48 hours, diagnose creative fatigue vs. audience exhaustion.')
            recs.insert(1, 'Cross-check whether landing page conversion has changed, which would explain ROAS decline.')
        return recs

    def _creative_notes(self) -> List[str]:
        return [
            'Meta: Video creative with captions outperforms static by 20–40% in feed environments.',
            'Google: RSA (Responsive Search Ads) with 8–10 headlines and 4 descriptions outperform expanded text ads.',
            'Amazon: A+ content and lifestyle images boost Sponsored Brand conversion by 5–15%.',
            'TikTok: Native, unpolished UGC-style content outperforms brand-produced video in feed.',
            'Xiaohongshu: High-quality image + conversational copy with specific use-case scenarios drives engagement.',
        ]

    def render(self) -> str:
        lines: List[str] = []
        lines.append('# Ad Budget Rebalancing Brief')
        lines.append('')
        lines.append(f'**Review mode:** {self.concern}')
        lines.append(f'**Channels in scope:** {_join(self.channels)}')
        lines.append(f'**Campaign types:** {_join(self.campaign_types)}')
        lines.append('**Method note:** This is a heuristic budget brief. No live ad platform, campaign manager, or analytics API was accessed.')
        lines.append('')
        lines.append('## Budget Health Summary')
        lines.append('- Start by confirming total monthly spend, channel mix percentages, and overall ROAS or MER.')
        lines.append('- Treat ROAS targets as channel-specific: Amazon at 3x+ is different from TikTok at 1.5x.')
        lines.append('- If overall ROAS is declining but individual channels look healthy, investigate audience overlap or attribution conflict.')
        lines.append('')
        lines.append('## Channel Efficiency Scorecard')
        lines.append('| Channel | Est. ROAS | Est. CPM | Efficiency | Recommendation |')
        lines.append('|---|---|---|---|---|')
        for row in self._channel_scorecard():
            lines.append(f'| {row["channel"]} | {row["roas"]} | {row["cpm"]} | {row["efficiency"]} | {row["recommendation"]} |')
        lines.append('')
        lines.append('## Campaign Type Mix')
        lines.append('| Type | Recommended % | Your Mix | Note |')
        lines.append('|---|---|---|---|---|')
        for row in self._campaign_breakdown():
            lines.append(f'| {row["type"]} | {row["recommended_pct"]} | {row["current"]} | {row["note"]} |')
        lines.append('')
        lines.append('## Rebalancing Recommendations')
        for idx, rec in enumerate(self._rebalance_recommendations(), 1):
            lines.append(f'{idx}. {rec}')
        lines.append('')
        lines.append('## Creative & Landing-Page Considerations')
        for note in self._creative_notes():
            lines.append(f'- {note}')
        lines.append('')
        lines.append('## Next Review Checkpoint')
        lines.append('- Run a 7-day performance review after any budget reallocation.')
        lines.append('- Set a monthly cadence for budget rebalancing even when performance is stable.')
        lines.append('- Escalate to a full audit if ROAS drops more than 20% in any channel without clear creative or audience explanation.')
        return '\n'.join(lines)


def handle(user_input: BudgetInput) -> str:
    return AdBudgetRebalancer(user_input).render()


if __name__ == '__main__':
    payload = sys.argv[1] if len(sys.argv) > 1 else sys.stdin.read()
    print(handle(payload))
