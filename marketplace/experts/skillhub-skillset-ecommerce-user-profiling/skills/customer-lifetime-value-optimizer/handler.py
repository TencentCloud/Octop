#!/usr/bin/env python3
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Sequence


def _load_skill_meta() -> Dict[str, str]:
    skill_path = Path(__file__).with_name("SKILL.md")
    text = skill_path.read_text(encoding="utf-8")
    frontmatter = ""
    body = text
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) == 3:
            frontmatter = parts[1]
            body = parts[2]

    data: Dict[str, str] = {}
    for line in frontmatter.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        data[key.strip()] = value.strip().strip("\"'")

    title = data.get("name", Path(__file__).resolve().parent.name.replace("-", " ").title())
    for line in body.splitlines():
        if line.startswith("# "):
            title = line[2:].strip()
            break

    return {
        "name": data.get("name", title),
        "title": title,
        "description": data.get("description", title),
    }


def _normalize_inputs(inputs: Any) -> str:
    if inputs is None:
        return ""
    if isinstance(inputs, str):
        return inputs.strip()
    if isinstance(inputs, dict):
        parts: List[str] = []
        for key, value in inputs.items():
            if value in (None, "", [], {}, ()):  # type: ignore[comparison-overlap]
                continue
            if isinstance(value, (list, tuple, set)):
                rendered = ", ".join(str(item) for item in value)
            else:
                rendered = str(value)
            parts.append(f"{key}: {rendered}")
        return " | ".join(parts)
    if isinstance(inputs, (list, tuple, set)):
        return " | ".join(str(item) for item in inputs)
    try:
        return json.dumps(inputs, ensure_ascii=False, sort_keys=True)
    except TypeError:
        return str(inputs)


def _detect_many(text: str, rules: Dict[str, Sequence[str]], default: List[str], limit: int = 4) -> List[str]:
    lower = text.lower()
    found = [label for label, keywords in rules.items() if any(keyword in lower for keyword in keywords)]
    ordered: List[str] = []
    for item in found + default:
        if item not in ordered:
            ordered.append(item)
    return ordered[:limit]


def _detect_one(text: str, rules: Dict[str, Sequence[str]], default: str) -> str:
    lower = text.lower()
    for label, keywords in rules.items():
        if any(keyword in lower for keyword in keywords):
            return label
    return default


def _join(items: Sequence[str]) -> str:
    return ", ".join(items) if items else "Not specified"


SEGMENT_RULES = {
    "High-potential new customers": ["new customer", "new buyer", "first order", "first-time", "新客", "首购"],
    "High-value loyal customers": ["vip", "loyal", "repeat", "member", "high value", "老客", "会员"],
    "Price-sensitive customers": ["discount", "coupon", "deal seeker", "price sensitive", "促销", "价格敏感"],
    "Dormant customers": ["dormant", "lapsed", "inactive", "sleeping", "winback", "沉睡客", "流失"],
    "Return-risk customers": ["return", "refund", "exchange", "complaint", "退货", "退款"],
}

LEVER_RULES = {
    "Lift repeat rate": ["repeat", "frequency", "reorder", "refill", "repurchase", "复购"],
    "Raise AOV": ["aov", "average order", "bundle", "upsell", "cross sell", "加价购", "连带"],
    "Protect gross margin": ["margin", "profit", "gross margin", "折扣", "discount abuse", "毛利"],
    "Reduce churn": ["churn", "lapsed", "dormant", "inactive", "drop-off", "流失", "召回"],
    "Improve first-order experience": ["first order", "welcome", "onboarding", "首购", "首次体验", "post-purchase"],
}

CONTEXT_RULES = {
    "Low-frequency / high-ticket": ["high ticket", "big ticket", "low frequency", "furniture", "appliance", "大件"],
    "Consumables / repeatable": ["consumable", "subscription", "refill", "repeat", "supplement", "复购"],
    "Discount-led acquisition": ["discount", "coupon", "deal", "promotion only", "低价流量", "价格战"],
}

SEGMENT_LIBRARY = {
    "High-potential new customers": {
        "pattern": "First-order intent exists, but the second-order path is not yet protected.",
        "issue": "The business may be paying acquisition cost without converting it into durable behavior.",
        "move": "Use a tighter welcome-to-second-order path with one clear reason to come back quickly.",
        "touchpoint": "Welcome flow, post-purchase education, and a timed second-order reminder.",
        "offer": "Keep incentives narrow and tied to next-best products or replenishment logic.",
        "metric": "30-day repeat rate and second-order contribution margin.",
    },
    "High-value loyal customers": {
        "pattern": "These customers already compound value through repeat behavior, trust, or membership depth.",
        "issue": "Generic campaigns can under-serve them or train them to wait for unnecessary discounts.",
        "move": "Protect them with differentiated value, early access, or curated higher-margin bundles.",
        "touchpoint": "VIP CRM, loyalty tiers, priority launches, and service recovery priority.",
        "offer": "Use exclusivity, premium bundles, or convenience benefits before defaulting to deep discounts.",
        "metric": "90-day gross profit contribution, repeat frequency, and premium mix.",
    },
    "Price-sensitive customers": {
        "pattern": "They respond to offers, but their margin quality can collapse if every touch is price-led.",
        "issue": "Revenue may look healthy while net value is thin or unstable.",
        "move": "Shift from blanket discounts to threshold mechanics, bundles, or product selection control.",
        "touchpoint": "Promo segmentation, threshold offers, and margin-protected assortment selection.",
        "offer": "Prefer bundle logic, add-on logic, or category fences instead of storewide discounting.",
        "metric": "Offer redemption quality, AOV, and contribution margin after discount.",
    },
    "Dormant customers": {
        "pattern": "Past purchase intent exists, but relevance or timing has faded.",
        "issue": "Winback costs rise fast if the team waits too long or uses the same message for everyone.",
        "move": "Use reason-based reactivation with tailored hooks such as refill timing, newness, or solved pain points.",
        "touchpoint": "Winback journeys, segmented reminders, and category-specific comeback offers.",
        "offer": "Use the lightest offer that reopens attention, then graduate customers into a healthier repeat path.",
        "metric": "Reactivation rate, 60-day retained value, and margin after winback spend.",
    },
    "Return-risk customers": {
        "pattern": "Top-line spend can look attractive while refunds or dissatisfaction erase the real value.",
        "issue": "The business may over-invest in segments that produce noisy or low-net revenue.",
        "move": "Fix expectation setting, product matching, and onboarding before scaling lifecycle pressure.",
        "touchpoint": "Pre-purchase education, FAQ clarity, order follow-up, and support escalation rules.",
        "offer": "Prioritize trust-building and expectation alignment over harder promotional pushes.",
        "metric": "Net revenue after returns, return rate, and complaint rate.",
    },
}

LEVER_LIBRARY = {
    "Lift repeat rate": "Tighten the time-to-second-order path and give the best-fit segments a clear reason to return before attention decays.",
    "Raise AOV": "Use bundles, attach logic, or premium alternatives so extra revenue also improves order quality.",
    "Protect gross margin": "Separate growth that looks good on revenue from growth that still creates durable profit after incentives and service cost.",
    "Reduce churn": "Intervene earlier around dormancy and post-purchase drop-off instead of waiting for full customer loss.",
    "Improve first-order experience": "Use onboarding, expectation setting, and early service touchpoints so more first orders become repeat behavior.",
}


class CustomerLifetimeValueOptimizer:
    def __init__(self, user_input: Any):
        self.raw = user_input
        self.text = _normalize_inputs(user_input)
        self.lower = self.text.lower()
        self.segments = _detect_many(
            self.text,
            SEGMENT_RULES,
            ["High-potential new customers", "High-value loyal customers", "Dormant customers"],
            limit=4,
        )
        self.primary_lever = _detect_one(self.text, LEVER_RULES, "Lift repeat rate")
        self.levers = _detect_many(
            self.text,
            LEVER_RULES,
            ["Lift repeat rate", "Raise AOV", "Reduce churn"],
            limit=4,
        )
        self.context = _detect_one(self.text, CONTEXT_RULES, "General ecommerce lifecycle")

    def _segment_rows(self) -> List[str]:
        rows: List[str] = []
        for segment in self.segments:
            details = SEGMENT_LIBRARY[segment]
            rows.append(
                f"| {segment} | {details['pattern']} | {details['issue']} | {details['move']} |"
            )
        return rows

    def _action_packages(self) -> List[str]:
        blocks: List[str] = []
        for segment in self.segments[:3]:
            details = SEGMENT_LIBRARY[segment]
            blocks.append(f"### {segment}")
            blocks.append(f"- Goal: {details['move']}")
            blocks.append(f"- Touchpoints: {details['touchpoint']}")
            blocks.append(f"- Offer or content logic: {details['offer']}")
            blocks.append(f"- Success metric: {details['metric']}")
            blocks.append("")
        return blocks

    def _measurement_notes(self) -> List[str]:
        notes = [
            "Treat this as an operator-facing LTV action brief, not a finance-grade discounted cash flow model.",
            "Separate revenue lift from gross margin impact and return-adjusted value before scaling any segment play.",
            "Coupon, loyalty, and CRM activation should remain human-approved.",
        ]
        if self.context == "Low-frequency / high-ticket":
            notes.append("Because the business context looks low-frequency or high-ticket, favor trust, timing, and service quality over forced repeat-rate logic.")
        if self.context == "Discount-led acquisition":
            notes.append("Because discount sensitivity appears material, audit incentive quality before mistaking promo response for durable LTV improvement.")
        if "Return-risk customers" not in self.segments:
            notes.append("If return or refund behavior is meaningful, add a separate net-value lens before treating top-line spend as real lifetime value.")
        return notes

    def render(self) -> str:
        meta = _load_skill_meta()
        lines: List[str] = []
        lines.append("# LTV Optimization Plan")
        lines.append("")
        lines.append(f"**Skill description:** {meta['description']}")
        lines.append(f"**Primary growth angle:** {self.primary_lever}")
        lines.append(f"**Segments referenced:** {_join(self.segments)}")
        lines.append(f"**Operating context:** {self.context}")
        lines.append(f"**Input snapshot:** {self.text or 'No structured customer data was provided, so this plan uses default ecommerce lifecycle assumptions.'}")
        lines.append("")
        lines.append("## Segment Diagnosis")
        lines.append("| Segment | Current value pattern | Main issue | Best next move |")
        lines.append("|---|---|---|---|")
        lines.extend(self._segment_rows())
        lines.append("")
        lines.append("## Lever Ranking")
        for idx, lever in enumerate(self.levers, 1):
            lines.append(f"{idx}. **{lever}:** {LEVER_LIBRARY[lever]}")
        lines.append("")
        lines.append("## Action Packages")
        lines.extend(self._action_packages())
        lines.append("## Measurement and Limits")
        for note in self._measurement_notes():
            lines.append(f"- {note}")
        return "\n".join(lines)


def handle(user_input: Any) -> str:
    return CustomerLifetimeValueOptimizer(user_input).render()


if __name__ == "__main__":
    payload = sys.argv[1] if len(sys.argv) > 1 else sys.stdin.read()
    print(handle(payload))
