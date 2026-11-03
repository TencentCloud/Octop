---
name: financial-fraud-index
description: Use when analyzing annual reports, audit reports, financial statements, or suspected accounting manipulation and the agent needs an evidence-grounded fraud-risk assessment from PDFs or extracted report text.
---

# Financial Fraud Index

## Overview

Use this skill to assess fraud or manipulation risk in annual reports and financial statements. The core rule is simple: conclusions must stay tied to evidence, and missing evidence must stay visible.

## When to Use

Use this skill when the task involves:

- annual reports, audit reports, or financial statements;
- fraud-risk, manipulation-risk, or earnings-quality assessment;
- extracting red flags from PDF reports or extracted report text;
- evidence-backed comparison across companies or periods.

Do not use this skill for:

- general investment advice without source documents;
- broad market commentary;
- valuation modeling unrelated to report evidence.

## Workflow

1. Confirm the source set.
   Source type, company name, report year, and whether the input is a PDF, extracted text, or both.
2. Extract the usable facts.
   Focus on headline statements, core financial fields, notes, audit opinion, and governance disclosures.
3. Classify findings into three buckets.
   Confirmed anomalies, weak signals, and missing data.
4. Attach evidence to every confirmed anomaly.
   Prefer page-numbered excerpts. If page numbers are unavailable, say so explicitly.
5. Downgrade certainty when coverage is incomplete.
   If core fields or note evidence are missing, say the conclusion is incomplete or pending review.

## Evidence Rules

- Never invent figures, excerpts, page numbers, ratios, or causal explanations.
- Prefer primary evidence from the report over summary text written by the user.
- Prefer page-numbered excerpts over paraphrases.
- If a signal is based on calculation, show both the source values and the calculation basis.
- If evidence is partial, keep the signal as weak or pending review rather than overstating it.
- If extraction is noisy or unreliable, say that directly.

## Output Structure

Produce output in this order:

1. Report summary
   Company, period, audit opinion, and overall risk view.
2. Confirmed anomalies
   Only signals supported by report evidence.
3. Weak signals
   Suspicious items that do not yet support a firm conclusion.
4. Missing data
   Fields, notes, or evidence gaps that weaken confidence.
5. Evidence excerpts
   Prefer `原文摘录（第X页）: ...` style citations when page numbers exist.
6. Review guidance
   What needs manual checking next.

## Signal Categories

### Confirmed anomalies

Use when the report provides direct support, for example:

- audit opinion issues;
- revenue, profit, and cash-flow contradictions;
- receivable or inventory anomalies supported by values or notes;
- governance issues with explicit disclosure;
- accounting-policy or accounting-estimate changes with cited source text.

### Weak signals

Use when the evidence is suggestive but incomplete, for example:

- ratio deterioration without corroborating note evidence;
- unusual changes lacking note disclosure;
- narrative inconsistencies without numeric backing.

### Missing data

Use when the analysis would normally depend on fields or notes that are absent, unreadable, or unsupported by evidence, for example:

- missing operating cash flow support;
- missing sales cash receipts;
- missing note excerpts for provisions, subsidies, or contingent liabilities;
- missing page anchors for core statement lines.

## Common Mistakes

- Treating every anomaly as a confirmed fraud signal.
- Using narrative statements as evidence when the task requires numeric proof.
- Hiding missing data behind a confident risk rating.
- Giving buy/hold/sell style advice when the evidence base is incomplete.
- Quoting a value without naming where it came from.

## Reference Pattern

Use this concise pattern when reporting:

```text
报告摘要
- 公司/年度:
- 审计意见:
- 总体判断:

明确异常
- 信号名:
  证据:

弱信号
- 信号名:
  原因:

缺失数据
- 字段/附注:
  影响:
```

## Repository Note

This skill is standalone. If a local project already contains a financial-fraud analysis pipeline, use that implementation as a helper, but keep the evidence and output rules above as the controlling standard.
