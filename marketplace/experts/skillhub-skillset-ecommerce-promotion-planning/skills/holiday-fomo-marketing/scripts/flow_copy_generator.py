#!/usr/bin/env python3
"""
Abandoned Checkout Flow Copy Generator for holiday campaigns.

Generates multi-step email/SMS recovery flows with holiday-specific
urgency copy based on product, holiday, and shipping cut-off date.

Usage:
    python3 flow_copy_generator.py --product "custom engraved ring" --holiday "Valentine's Day" --cutoff "Feb 8"
    python3 flow_copy_generator.py --product "Christmas ornament set" --holiday "Christmas" --cutoff "Dec 15" --brand "Sparkle & Co"
"""

import argparse
from datetime import datetime


FLOW_STEPS = [
    {
        "step": 1,
        "timing": "+30 minutes",
        "channel": "Email",
        "focus": "Hard deadline — shipping cut-off urgency",
        "subject_template": "⏳ Your cart is waiting — order now for guaranteed {holiday} delivery",
        "body_template": (
            "Hi there,\n\n"
            "You left something special in your cart: **{product}**.\n\n"
            "Here's the thing — to guarantee delivery by {holiday}, "
            "you need to order before **{cutoff}**. That's coming up fast.\n\n"
            "👉 **[Complete My Order →]**\n\n"
            "Don't let the perfect {holiday_adj} gift slip away.\n\n"
            "{brand_sign}"
        ),
    },
    {
        "step": 2,
        "timing": "+2 hours",
        "channel": "SMS",
        "focus": "Scarcity — low stock / high demand",
        "body_template": (
            "⚡ Your {product} is selling fast — only a few left in stock. "
            "Complete your order now for guaranteed {holiday} delivery (cutoff: {cutoff}). "
            "Tap here → [link]"
        ),
    },
    {
        "step": 3,
        "timing": "+12 hours",
        "channel": "Email",
        "focus": "Social proof + FOMO",
        "subject_template": "Everyone's loving this {product} — still want yours?",
        "body_template": (
            "Hi there,\n\n"
            "Since you left your cart, **hundreds of shoppers** have been browsing "
            "the same {product}. It's one of our most popular {holiday} picks.\n\n"
            "⭐ *\"Absolutely stunning — my partner loved it!\"* — Recent buyer\n\n"
            "**Shipping cut-off for {holiday}: {cutoff}.**\n\n"
            "👉 **[Complete My Order →]**\n\n"
            "{brand_sign}"
        ),
    },
    {
        "step": 4,
        "timing": "+24 hours",
        "channel": "SMS",
        "focus": "Final nudge — last chance",
        "body_template": (
            "⏰ Last chance! Your {product} is still in your cart but the "
            "{holiday} shipping cutoff ({cutoff}) is almost here. "
            "Order now or it won't arrive in time → [link]"
        ),
    },
]

HOLIDAY_ADJECTIVES = {
    "valentine's day": "Valentine's",
    "valentines day": "Valentine's",
    "christmas": "Christmas",
    "mother's day": "Mother's Day",
    "mothers day": "Mother's Day",
    "father's day": "Father's Day",
    "bfcm": "holiday",
    "black friday": "holiday",
    "cyber monday": "holiday",
}


def get_holiday_adj(holiday: str) -> str:
    return HOLIDAY_ADJECTIVES.get(holiday.lower(), holiday)


def generate_flow(product: str, holiday: str, cutoff: str, brand: str = "") -> str:
    holiday_adj = get_holiday_adj(holiday)
    brand_sign = f"— {brand}" if brand else "— Your friends at the store"

    lines = [
        f"# Abandoned Checkout Recovery Flow",
        f"**Product:** {product}",
        f"**Holiday:** {holiday}",
        f"**Shipping Cut-off:** {cutoff}",
        "",
        "---",
        "",
    ]

    for step in FLOW_STEPS:
        lines.append(f"## Step {step['step']}: {step['channel']} ({step['timing']})")
        lines.append(f"**Focus:** {step['focus']}")
        lines.append("")

        if "subject_template" in step:
            subject = step["subject_template"].format(
                product=product, holiday=holiday, cutoff=cutoff,
                holiday_adj=holiday_adj,
            )
            lines.append(f"**Subject line:** {subject}")
            lines.append("")

        body = step["body_template"].format(
            product=product, holiday=holiday, cutoff=cutoff,
            holiday_adj=holiday_adj, brand_sign=brand_sign,
        )
        lines.append("**Copy:**")
        lines.append("")
        lines.append("```")
        lines.append(body)
        lines.append("```")
        lines.append("")
        lines.append("---")
        lines.append("")

    lines.extend([
        "## Implementation Notes",
        "",
        "- **Do not stack discounts** on top of sale pricing in recovery flows — it trains abandonment.",
        "- **One-click CTA**: Link directly to checkout with cart pre-loaded.",
        "- **Suppress after purchase**: Remove from flow immediately after conversion.",
        f"- **Hard stop**: Disable all steps after {cutoff} if the cut-off has passed.",
        "",
    ])

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Generate holiday abandoned checkout recovery flow copy"
    )
    parser.add_argument("--product", required=True, help="Product description")
    parser.add_argument("--holiday", required=True, help="Holiday or event name")
    parser.add_argument("--cutoff", required=True, help="Shipping cut-off date")
    parser.add_argument("--brand", default="", help="Brand name (optional)")
    parser.add_argument("--out", default=None, help="Output file (default: stdout)")
    args = parser.parse_args()

    result = generate_flow(args.product, args.holiday, args.cutoff, args.brand)

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(result)
        print(f"Flow written to {args.out}")
    else:
        print(result)


if __name__ == "__main__":
    main()
