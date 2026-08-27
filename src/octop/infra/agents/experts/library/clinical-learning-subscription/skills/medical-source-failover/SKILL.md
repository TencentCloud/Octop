---
name: medical-source-failover
description: Route retrieval of Chinese medical guidelines, consensus statements, regulatory documents, drug information, safety notices, standards, and public-health materials through authoritative originals and verified fallback copies. Use when a canonical medical source is blocked, slow, unavailable, moved, paywalled, or difficult to parse, or when designing and auditing domestic medical-source fallback rules. Do not treat secondary summaries or reposts as independent clinical evidence.
---

# Medical Source Failover

Retrieve the intended medical document reliably without laundering a secondary source into primary evidence.

## Non-negotiable invariant

**Degrade the access path, never the document identity or evidentiary standard.**

- Keep authority, document quality, access health, and retrieval priority as separate judgments.
- A domain's reputation does not grade every item published on it.
- A repost that reproduces the same document is an access carrier, not independent corroboration.
- A summary, interpretation, search snippet, news item, or social post may help discover an original; it must not support a precise recommendation, dose, contraindication, or evidence grade.

## Load the relevant references

- For any domestic medical retrieval, read [references/domestic-source-registry.md](references/domestic-source-registry.md) before selecting sources. It defines authoritative scope, discovery-only sources, fallback relationships, and how to extend the registry.
- When a page is blocked, slow, moved, paywalled, incomplete, or unparseable, read [references/failover-policy.md](references/failover-policy.md) before retrying or switching hosts.
- Before using a repost, mirror, alternate PDF, cached copy, or database full text, read [references/document-identity.md](references/document-identity.md) and verify that it is the same document and version.

## Workflow

1. Classify the requested fact before searching:
   - regulation or legal status;
   - approved drug indication, contraindication, dosage, or label;
   - pharmacovigilance or adverse-reaction notice;
   - reimbursement or payment scope;
   - public-health policy, surveillance, or prevention;
   - national or industry standard;
   - clinical guideline or consensus;
   - effectiveness, diagnosis, prognosis, or harm evidence;
   - teaching or explanatory material.
2. Define the intended document identity from all available fields: normalized title, issuing/developing organization, year/version, document number or DOI, publication venue, and date.
3. Use the registry to choose a source authoritative for that fact type. Do not choose solely by generic tier or domain.
4. Attempt the canonical route within the retry budget. Classify access failures; do not repeatedly hammer a protected host.
5. Follow the failover ladder. Prefer alternate endpoints of the same publisher, official republications, and formal journal versions before verified third-party copies.
6. Verify document identity and version before extracting content from any fallback. Reject mismatches and incomplete copies.
7. Check for a newer version, correction, update, retraction, or withdrawal before relying on the text.
8. Extract only claims supported by the retrieved document. For recommendations, preserve population, intervention, conditions, recommendation strength, evidence certainty, and exceptions when reported.
9. Cite the original issuer or formal publication. If a fallback carried the text, disclose the fallback separately instead of presenting it as a second source.

## Latency-first fast failover

For an ordinary `clinical-q-and-a` request, keep the same identity standard but use the smallest path:

- Enter this skill only after the selected canonical route actually fails; do not preload failover references during a successful direct fetch.
- `401`/`403`/`412`/CAPTCHA/login/paywall: do not retry the address. Move immediately to the best known L1-L3 route.
- Timeout/`5xx`: at most one retry or one approved fallback, not both repeatedly. When latency matters, start one hedged fallback after roughly two seconds and cancel the losing request after a valid copy arrives.
- Try only one fallback carrier for the same document in the fast path. If it is incomplete or identity cannot be established, return a bounded “正文未核验” result instead of exploring the whole ladder.
- Do not retrieve a second guideline merely to compensate for an access failure. The target remains the same document unless `source-verify` explicitly chooses a new normative document.

## Failover ladder

- **L0 — Canonical original:** issuing body or formal publisher page and complete attachment.
- **L1 — Same-owner alternate:** the same body's attachment host, mobile page, bulletin, archive, API, HTML/PDF counterpart, or journal subsite.
- **L2 — Official republication:** a complete copy on another government body, joint issuer, government portal, or official gazette.
- **L3 — Formal publication:** the guideline's journal HTML/PDF or DOI-bound publisher version.
- **L4 — Verified complete copy:** an authorized bibliographic database or complete copy with strong identity verification. Attribute claims to the original document.
- **L5 — Metadata only:** registry entry, index, abstract, news item, or interpretation. Use only to continue discovery or report that full text was not verified.

Do not skip identity verification between L2-L4. L5 cannot support document-level clinical claims.

## Safe stopping rules

Stop precise extraction and state what remains unverified when any of these applies:

- year/version, issuer, or unique identifier conflicts;
- only a summary, snippet, partial screenshot, or truncated copy is available;
- tables, footnotes, recommendation conditions, appendices, or safety qualifications are missing;
- a possible correction, replacement, withdrawal, or newer version cannot be resolved;
- a high-risk drug or procedure claim cannot be located in a complete authoritative document.

When stopping, provide the verified metadata and a bounded statement such as “full text not verified; no precise recommendation or dosage extracted.” Do not fill gaps from memory.

## Response record

For material medical claims, retain or report:

- document title, issuer/developer, year/version, document number or DOI;
- document type and the fact type it is authoritative for;
- canonical URL and the URL actually used to retrieve the text;
- fallback level and identity-verification result;
- publication/update status and last verification date;
- exact recommendation, section, table, or page locator when available;
- unresolved uncertainty or conflict.
