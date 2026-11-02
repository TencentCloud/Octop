---
name: promotion-enrollment-assistant
description: Navigate Amazon Lightning Deal, Best Deal, Coupon, Shoppable Holiday; TikTok Shop Promo Zone; Shopify Discount Rules; Taobao Crowd-Collapse; JD 618; and other platform promotion mechanisms. Use when operators need to compare promotion types, assess eligibility, plan enrollment timelines, or avoid common enrollment mistakes without live platform API access.
---

# Promotion Enrollment Assistant

## Overview

Use this skill to turn rough promotion intent into an operator-ready enrollment plan. It maps promotion types across major ecommerce platforms, checks eligibility heuristics, generates enrollment timelines, and surfaces common pitfalls before submission.

This MVP is heuristic. It does **not** access live seller portals, promotion APIs, or enrollment dashboards. It relies on the user's provided product context, platform, and promotion type.

## Trigger

Use this skill when the user wants to:
- compare promotion types across Amazon, TikTok Shop, JD, Taobao, or Shopify
- assess whether a SKU or category is likely eligible for a specific deal type
- plan an enrollment timeline with submission windows and approval lead times
- avoid common rejection reasons for Lightning Deal, Coupon, Best Deal, or similar mechanisms
- prepare a promotion enrollment checklist for a specific platform and campaign window

### Example prompts

- "Help me enroll in Amazon Lightning Deal for our skincare SKU this Prime Day"
- "What promotion types should we use on TikTok Shop for a mid-season flash sale?"
- "Create an enrollment timeline for our JD 618 campaign"
- "How do we avoid Amazon promotion rejection for our Home category?"

## Workflow

1. Capture the platform, promotion type, target SKU or category, and campaign window.
2. Map eligibility heuristics for the specific promotion type.
3. Build the enrollment checklist and timeline.
4. Surface common rejection patterns and how to avoid them.
5. Return a markdown enrollment brief.

## Inputs

The user can provide any mix of:
- platform: Amazon, TikTok Shop, JD, Taobao, Shopify, Xiaohongshu, or general
- promotion type: Lightning Deal, Best Deal, Coupon, Crowd-Collapse, Flash Sale, Bundle Deal, 618, 11.11, Prime Day, Black Friday
- SKU or category context: product type, price range, rating, fulfillment method
- campaign window: specific dates, seasonal event, or general timing
- historical context: prior enrollment rejections, approval rates, or deal performance

## Outputs

Return a markdown brief with:
- promotion type summary and how it works
- eligibility assessment for the given SKU or category
- enrollment timeline (submission deadline → review → approval → go-live)
- checklist: required materials, pricing constraints, inventory requirements
- common rejection reasons and mitigation steps
- platform-specific notes and tips

## Safety

- No live seller portal or enrollment API access.
- Eligibility assessment is directional; final approval depends on platform review.
- Do not claim guaranteed enrollment or specific deal placement.
- Pricing and margin decisions remain with the operator.

## Best-fit Scenarios

- sellers enrolling in platform deals for the first time or expanding to new platforms
- operators managing multiple promotion types across channels
- brands preparing for major shopping festivals (618, 11.11, Prime Day, Black Friday)

## Not Ideal For

- real-time enrollment status tracking or automated submission
- enterprise-grade promotion management with complex legal or compliance requirements
- platforms or deal types not covered in the built-in playbook library

## Acceptance Criteria

- Return markdown text.
- Include eligibility assessment, enrollment timeline, and rejection-mitigation steps.
- Cover at least one specific promotion type with actionable checklist items.
- Make eligibility assumptions explicit.
- Keep the brief practical for platform sellers and ecommerce operators.
