# Domestic medical source registry

This registry routes fact types to candidate authorities and fallback paths. It is not a universal evidence ranking and it does not guarantee current accessibility. Recheck ownership, document status, and access health at use time.

## National government and regulatory sources

| Source | Canonical domains | Authoritative scope | Preferred fallbacks and cautions |
|---|---|---|---|
| Chinese Government | `gov.cn`, `app.www.gov.cn` | State Council policy and official republications of ministry documents | Strong fallback for a complete ministry republication. Preserve the original issuing body and attachments. |
| National Health Commission | `nhc.gov.cn` | National health policy, normative documents, clinical/technical specifications issued by NHC, health standards, official bulletins | Try attachment URLs, policy/regulation lists, NHC Gazette, then complete `gov.cn` republication. Some routes may reject automated clients. |
| National Disease Control and Prevention Administration | `ndcpa.gov.cn` | Disease-control regulation, policy, notices, technical documents | Use China CDC for technical/public-health material when it is the issuing or implementing body; do not substitute unrelated popular education. |
| Chinese Center for Disease Control and Prevention | `chinacdc.cn` | National surveillance reports, public-health technical guidance, prevention and control information | For binding policy, trace back to NHC/NDCPA or the named issuer. |
| National Medical Products Administration | `nmpa.gov.cn`, `zwfw.nmpa.gov.cn` | Drug/device approvals, regulatory notices, recalls, safety communications, legal status | Try NMPA service portal, direct attachments, `gov.cn`, CDE/CMDE only within their delegated scope. Automated access may be restricted. |
| Center for Drug Evaluation, NMPA | `cde.org.cn` | Drug-review technical guidelines, review notices, registration-development information | Not a substitute for a final NMPA approval decision or approved product label. |
| Center for Medical Device Evaluation, NMPA | `cmde.org.cn` | Medical-device review principles and technical review guidance | Not general clinical-effectiveness evidence; trace regulatory status to NMPA. |
| National ADR monitoring systems | `adrs.org.cn` and NMPA public notices | Adverse-reaction/event reporting systems and official pharmacovigilance material | Login/reporting portals are not public evidence databases. Prefer public NMPA/monitoring-center reports and bulletins for citation. |
| National Healthcare Security Administration | `nhsa.gov.cn` | National reimbursement catalogues, payment restrictions, medical-service pricing/payment policy | Payment scope is not an approved indication and not a clinical recommendation. Check provincial policy when the question is local. |
| National standards and market regulation | `openstd.samr.gov.cn`, `samr.gov.cn` | Current national standards, standard status, market-regulation notices | Distinguish mandatory `GB`, recommended `GB/T`, and guidance `GB/Z`; check current/replaced/withdrawn status. |
| National Administration of Traditional Chinese Medicine | `natcm.gov.cn` | National TCM policy, standards, technical and administrative documents within its remit | Do not elevate educational or news content to clinical evidence. |

## Professional societies and formal publication sources

| Source | Canonical domains | Appropriate use | Fallback notes |
|---|---|---|---|
| Chinese Medical Association | `cma.org.cn` and verified `*.cma.org.cn` branch sites | Society identity, branch notices, guideline/consensus release information | Prefer the complete formal journal article when the society page contains only news or excerpts. Branch ownership must be verified. |
| CMA Publishing House / MedNexus | `medjournals.cn`, `cs.medjournals.cn` | Formal Chinese Medical Association journal articles, guidelines, consensus statements, corrections, DOI metadata | Route at article level. The platform also contains editorials, original studies, reviews, cases, videos, and news; domain alone does not confer a grade. |
| CMA journal sites / Yiigle | `yiigle.com`, verified `*.yiigle.com`, official attachment endpoints | Formal journal HTML/PDF and issue metadata | Verify title, DOI, year/version, journal, and completeness across old/new platform URLs. |
| Chinese Preventive Medicine Association | `cpma.org.cn` | Public-health society documents, standards, professional guidance, branch information | Prefer a complete formal publication; separate society news and popular education from technical documents. |
| Chinese Society of Clinical Oncology | `csco.org.cn` | CSCO guideline identity and oncology guideline information | Access and edition availability may vary; verify annual edition and use an authorized complete version. Do not infer text from launch news. |
| Other national specialty societies | Official society domain plus formal publisher | Specialty guidelines and consensus statements within the society's remit | Add only after ownership verification and sample-document checks. “National” in a name is not enough. |

## Discovery, indexing, and bibliographic services

| Source | Typical domains | Allowed role | Restrictions |
|---|---|---|---|
| PREPARE guideline registry | `guidelines-registry.cn` | Discover registration metadata, developing organizations, status, and possible publication links | Registration is not endorsement of final quality. Distinguish planned, draft, public-comment, and final documents. |
| SinoMed | `sinomed.ac.cn` | Chinese biomedical bibliographic discovery | Full-text availability and route stability vary. Verify against the formal publisher. |
| CNKI | `cnki.net` | Bibliographic discovery and authorized full-text access | Paywall/entitlement may apply. Cite the original journal item and DOI, not the search result page. |
| Wanfang Data | `wanfangdata.com.cn` and verified service domains | Bibliographic discovery and authorized full-text access | Same-document verification is required before using hosted full text as a carrier. |
| Guideline aggregators | `guide.medlive.cn`, `medlive.cn`, `medsci.cn`, relevant `dxy.cn` public pages | Discover titles, dates, organizations, translations, and original links | Secondary content only unless it supplies a complete verified formal document. Never use an interpretation for precise recommendation text. |

## Local and institutional sources

- Provincial health commissions, CDCs, medical-insurance bureaus, and drug regulators are authoritative for their own local policy, surveillance, and implementation rules. They do not override a national rule outside delegated scope.
- National clinical research centers, universities, and hospitals can be authoritative for documents they actually issue, local protocols, or copies they formally host. A hospital repost is not automatically an official national republication.
- Official journal and society WeChat posts may aid discovery, but use the linked formal document whenever possible. Screenshots and posts without stable complete text remain metadata only.

## Source expansion protocol

Do not add a domain merely because one useful page was found. For each candidate, record:

1. legal or organizational owner and how ownership was verified;
2. authoritative scope and explicitly excluded uses;
3. canonical domain and known same-owner subdomains/attachment hosts;
4. at least three representative documents, including one current item;
5. document identifiers exposed: DOI, document number, approval number, standard number, journal metadata;
6. access behavior: static/server-rendered, JavaScript-only, login, paywall, anti-bot, redirect, PDF/HTML support;
7. official fallback relationships and whether copies are complete;
8. correction, withdrawal, replacement, and archive mechanisms;
9. last health and ownership verification time.

Promote a source to an authoritative route only for its verified scope. Keep access-health observations in operational telemetry rather than treating “stable” as a permanent property.

## Candidate acceptance tests

Before adding or promoting a source:

- retrieve three sample documents by exact identity;
- verify the issuer and domain ownership;
- confirm that title, version, identifier, attachments, and correction links are preserved;
- simulate one blocked canonical URL and demonstrate a valid fallback;
- demonstrate that a secondary summary is rejected for a precise clinical claim;
- demonstrate that an older edition is not silently substituted;
- record the result and verification date.
