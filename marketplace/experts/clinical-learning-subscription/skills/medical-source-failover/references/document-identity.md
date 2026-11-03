# Document identity and fallback verification

Read this before using a repost, alternate PDF, database copy, cached copy, or mirror as the text carrier for a medical document.

## Identity record

Build a record with as many fields as the document type supports:

```text
normalized_title
document_type
issuing_body
developing_body
publication_venue
publication_date
year_or_edition
document_number
doi
approval_number_or_standard_number
language
page_count
canonical_url
retrieval_url
content_hash
correction_or_withdrawal_status
last_verified_at
```

Normalize whitespace, full-width punctuation, and harmless typography only. Do not normalize away edition numbers, population qualifiers, disease stage, part numbers, or words such as “草案”, “试行”, “解读”, “患者版”, and “更新版”.

## Verification grades

### Exact

- Binary hash matches a previously verified original; or
- the same official attachment is reached through a different official URL.

The fallback is an equivalent access path.

### Strong

Require all applicable hard identifiers to match:

- title;
- issuer/developer;
- year/edition;
- document number, DOI, approval number, or standard number.

Also compare structure: page count, section order, tables, recommendation numbering, references, and first/last pages. A formal journal version may have different pagination from an issuer PDF, but DOI, title, version, authorship, and substantive recommendation structure must align.

### Insufficient

Any of the following makes identity insufficient for precise extraction:

- missing or conflicting edition;
- a shortened title that could refer to several documents;
- only an abstract, slide deck, screenshot, summary, or article about the document;
- missing tables, appendices, footnotes, recommendation grades, or safety qualifications;
- no unique identifier and no independent authoritative metadata record;
- unexplained textual differences between copies.

Insufficient copies remain discovery aids only.

## Version and status checks

Before relying on a clinical or regulatory document, search the exact title and identifier with:

- `更新`, `新版`, `修订`;
- `更正`, `勘误`;
- `撤回`, `撤销`, `废止`, `替代`;
- the issuing organization's current document list.

Keep drafts, registrations, public-comment versions, final versions, interpretations, patient versions, and professional versions as distinct identities.

## High-risk extraction rule

For dosage, contraindications, pregnancy/pediatric use, severe adverse reactions, invasive procedures, emergency care, or legal/regulatory status:

- require a complete authoritative original or a complete fallback with Exact/Strong identity;
- locate the claim in a named section, recommendation, table, label field, or page;
- preserve formulation, route, population, conditions, exceptions, and units;
- do not reconstruct missing text from a secondary summary or memory;
- stop if the source is incomplete or the version cannot be resolved.

For approved drug information, match the relevant generic name, formulation, strength, route, approval holder/manufacturer where material, approval number, and label version. CDE technical guidance does not substitute for the approved label; reimbursement restrictions do not rewrite the label.

## Citation and disclosure

Attribute the claim to the original issuer or formal publication. Record the access carrier separately:

```text
Source: <original document title>, <issuer>, <year/version>, <document number or DOI>.
Text retrieved from: <official republication or verified carrier URL>.
Verification: <Exact|Strong>; checked <date>.
```

Do not count the original and its repost as two independent sources. Do not cite a discovery page as though it authored the recommendation.
