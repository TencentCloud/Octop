#!/usr/bin/env python3
import sys
from typing import Any, Dict, List, Union

PLATFORM_RULES = {
    'Amazon': ['amazon', 'seller central', 'vendor central'],
    'TikTok Shop': ['tiktok', 'tik tok', 'douyin'],
    'JD': ['jd', 'jingdong', 'jd.com'],
    'Taobao': ['taobao', '1688'],
    'Shopify': ['shopify', 'storefront'],
    'Xiaohongshu': ['xiaohongshu', 'rednote', 'xhs'],
    'General': ['general', 'all platform', 'multi-platform'],
}

PROMO_RULES = {
    'Lightning Deal': {
        'platform': 'Amazon',
        'duration': '4–6 hours',
        'discount': '15–50% off',
        'eligibility': 'Professional seller, 3+ reviews, inventory depth, category eligibility',
        'submission': '3–4 weeks before event',
        'rejection_reasons': ['Insufficient review count', 'Inventory too thin', 'Category not eligible', 'Pricing below floor'],
    },
    'Best Deal': {
        'platform': 'Amazon',
        'duration': '1–2 weeks',
        'discount': '10–30% off',
        'eligibility': 'Professional seller, 1+ review, Buy Box eligibility',
        'submission': '2–3 weeks before event',
        'rejection_reasons': ['Buy Box lost', 'Account health below threshold', 'Inventory inconsistency'],
    },
    'Coupon': {
        'platform': 'Amazon',
        'duration': '1–90 days',
        'discount': '5–50% off',
        'eligibility': 'Any seller with inventory',
        'submission': '1–2 weeks before launch',
        'rejection_reasons': ['Overlapping with other promotions', 'Pricing below 50% of recent price'],
    },
    'Prime Day': {
        'platform': 'Amazon',
        'duration': '48 hours',
        'discount': '20–40% off recommended',
        'eligibility': 'Prime-eligible, strong review profile, inventory for 2x expected volume',
        'submission': 'Invitations sent 6–8 weeks before; by-invitation only',
        'rejection_reasons': ['No invitation', 'Account health issue', 'Inventory risk'],
    },
    'TikTok Shop Promo Zone': {
        'platform': 'TikTok Shop',
        'duration': '4–24 hours',
        'discount': '10–30% off + creator佣金补贴',
        'eligibility': 'Store rating 4.0+, live-f直播资格, sufficient inventory',
        'submission': '1–2 weeks before via seller center',
        'rejection_reasons': ['Low store rating', 'Insufficient inventory', 'Category restriction', 'Price too low'],
    },
    'JD 618': {
        'platform': 'JD',
        'duration': 'Mid-June (typically June 1–18)',
        'discount': 'Platform-defined, typically 15–30% off',
        'eligibility': 'JD store, category participation, inventory commitment, margin deposit',
        'submission': 'April–May (pre-registration)',
        'rejection_reasons': ['Margin deposit insufficient', 'Category not in event', 'Inventory plan rejected'],
    },
    'Taobao Crowd-Collapse (聚划算)': {
        'platform': 'Taobao',
        'duration': '24–72 hours',
        'discount': '20–50% off',
        'eligibility': 'Gold seller status, 4.8+ DSR, category eligibility',
        'submission': '3–5 days before via Taobao Seller Center',
        'rejection_reasons': ['DSR below threshold', 'Low seller rank', 'Category not eligible'],
    },
    '11.11 / Black Friday': {
        'platform': 'Multi',
        'duration': 'Nov 11 (CN) / Black Fri–Cyber Mon (Western)',
        'discount': 'Platform-specific, typically 20–50% off',
        'eligibility': 'Varies by platform; generally high review count, inventory depth, account health',
        'submission': '6–8 weeks before',
        'rejection_reasons': ['Account health', 'Inventory commitment', 'Margin constraints'],
    },
}

EnrollmentInput = Union[str, Dict[str, Any]]


def _score_rules(text: str, rules: Dict[str, List[str]]) -> Dict[str, int]:
    return {name: sum(1 for kw in kws if kw in text) for name, kws in rules.items()}


def _join(items: List[str]) -> str:
    return ', '.join(items) if items else 'Not specified'


class PromotionEnrollmentAssistant:
    def __init__(self, user_input: EnrollmentInput):
        self.raw = user_input
        self.text = self._normalize_input(user_input)
        self.lower = self.text.lower()
        self.platform = self._detect_platform()
        self.promo_type = self._detect_promo_type()
        self.promo_info = PROMO_RULES.get(self.promo_type, None)

    def _normalize_input(self, user_input: EnrollmentInput) -> str:
        if isinstance(user_input, dict):
            chunks: List[str] = []
            for key in ['platform', 'promo_type', 'sku', 'category', 'window', 'notes']:
                value = user_input.get(key)
                if not value:
                    continue
                if isinstance(value, list):
                    value = ', '.join(str(v) for v in value)
                chunks.append(f'{key}: {value}')
            return ' | '.join(chunks)
        return str(user_input or '').strip()

    def _detect_platform(self) -> str:
        scores = _score_rules(self.lower, PLATFORM_RULES)
        best = max(scores, key=scores.get)
        return best if scores[best] > 0 else 'Amazon'

    def _detect_promo_type(self) -> str:
        known_promos = list(PROMO_RULES.keys())
        matched = [p for p in known_promos if p.lower().replace(' ', '') in self.lower.replace(' ', '')]
        if matched:
            return matched[0]
        for name in ['Lightning Deal', 'Best Deal', 'Coupon', 'TikTok Shop Promo Zone', 'JD 618', 'Taobao Crowd-Collapse (聚划算)', '11.11 / Black Friday', 'Prime Day']:
            if name.lower().split(' ')[0] in self.lower:
                return name
        return 'Lightning Deal'

    def _eligibility_checklist(self) -> List[str]:
        if not self.promo_info:
            return ['- Promotion type not recognized; confirm eligibility directly with platform seller support.']
        info = self.promo_info
        return [
            f'- **Platform:** {info["platform"]}',
            f'- **Duration:** {info["duration"]}',
            f'- **Typical discount:** {info["discount"]}',
            f'- **Eligibility:** {info["eligibility"]}',
        ]

    def _rejection_mitigation(self) -> List[str]:
        if not self.promo_info:
            return []
        return [f'- **{r}** — mitigation: review inventory, pricing history, and account health metrics before resubmission.'
                for r in self.promo_info['rejection_reasons']]

    def _timeline(self) -> List[str]:
        if not self.promo_info:
            return ['- Submit 2–4 weeks before the target deal window.']
        submission = self.promo_info.get('submission', '2–4 weeks before')
        return [
            f'- **Pre-registration:** {submission}',
            '- **Submission:** Via platform seller center (not third-party tools)',
            '- **Review period:** 3–10 business days depending on platform',
            '- **Approval / Rejection notice:** 1 week before deal goes live',
            '- **Inventory lock:** Typically required 48–72 hours before deal starts',
        ]

    def render(self) -> str:
        lines: List[str] = []
        lines.append('# Promotion Enrollment Brief')
        lines.append('')
        lines.append(f'**Platform:** {self.platform}')
        lines.append(f'**Promotion type:** {self.promo_type}')
        lines.append('**Method note:** This is a heuristic enrollment brief. No live seller portal or promotion API was accessed.')
        lines.append('')
        if self.promo_info:
            lines.append('## How It Works')
            lines.append(f'- **Platform:** {self.promo_info["platform"]}')
            lines.append(f'- **Duration:** {self.promo_info["duration"]}')
            lines.append(f'- **Typical discount range:** {self.promo_info["discount"]}')
            lines.append('')
        lines.append('## Eligibility Assessment')
        for item in self._eligibility_checklist():
            lines.append(item)
        lines.append('')
        lines.append('## Enrollment Timeline')
        for item in self._timeline():
            lines.append(item)
        lines.append('')
        lines.append('## Required Checklist')
        checks = [
            'Confirm product category eligibility on the target platform',
            'Verify review count or rating meets platform minimum',
            'Check inventory depth: plan for 2–3x expected deal volume',
            'Confirm pricing floor and discount margin will protect gross margin',
            'Review account health metrics (ODR, late shipment rate) 30 days before submission',
            'Prepare deal-related creative assets (badges, ad copy) in advance',
        ]
        for check in checks:
            lines.append(f'- [ ] {check}')
        lines.append('')
        lines.append('## Common Rejection Reasons & Mitigation')
        for item in self._rejection_mitigation():
            lines.append(item)
        lines.append('')
        lines.append('## Platform-Specific Tips')
        tips = {
            'Amazon': [
                '- Lightning Deal submission requires a referral fee for each deal submission.',
                '- Best Deal can run alongside Lightning Deal if the discount differential is justified.',
                '- Prime Day is by invitation only; build the relationship through consistent deal performance.',
            ],
            'TikTok Shop': [
                '- TikTok creator佣金补贴 can amplify deal economics — coordinate with at least 2–3 creators pre-deal.',
                '- Live streaming during the promo zone significantly lifts conversion.',
                '- Ensure your store rating is 4.0+ before applying.',
            ],
            'JD': [
                '- JD requires a margin deposit upfront for 618 participation — plan cash flow accordingly.',
                '- Coordinate JD logistics (入仓) timing carefully; late warehouse entry disqualifies the deal.',
            ],
            'Taobao': [
                '- Gold seller status (金冠) is a hard prerequisite for 聚划算.',
                '- DSR decline in the 30 days before application can trigger automatic rejection.',
            ],
            'General': [
                '- Always cross-check submission deadlines against the official platform event calendar.',
                '- Maintain a buffer between your discount and the platform floor.',
            ],
        }
        platform_tips = tips.get(self.platform, tips['General'])
        for tip in platform_tips:
            lines.append(f'- {tip}')
        return '\n'.join(lines)


def handle(user_input: EnrollmentInput) -> str:
    return PromotionEnrollmentAssistant(user_input).render()


if __name__ == '__main__':
    payload = sys.argv[1] if len(sys.argv) > 1 else sys.stdin.read()
    print(handle(payload))
