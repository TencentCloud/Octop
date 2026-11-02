# Medical source failover policy

Use this policy after an access path becomes slow, blocked, moved, incomplete, paywalled, or unparseable. The thresholds are operational defaults; honor a stricter product configuration when one exists.

## Failure classification and immediate action

| Signal | Interpretation | Action |
|---|---|---|
| `401`, login wall, subscription wall | Authorization or entitlement required | Do not bypass. Use an authorized session if available; otherwise move to a public official or formal-publisher route. |
| `403`, `412`, CAPTCHA, JavaScript challenge | Current client or route blocked | Do not repeat the same request. Open the route circuit and move to L1-L3. This is not evidence-source disqualification. |
| `429` | Rate limited | Honor `Retry-After`; open the host circuit for the current task and use an approved fallback. |
| `404`, `410` | Stale or retired URL | Search the exact title plus issuer, year/version, document number, or DOI. Check archives and replacement notices. |
| `5xx`, connection reset | Transient server failure | Retry once with bounded backoff, then fail over. |
| Connect/read timeout | Slow or unavailable route | Start one approved fallback; do not wait through repeated long timeouts. |
| HTML shell with no content | Client-rendered or protected content | Try same-owner HTML/API/PDF endpoints, then official republication or formal publication. |
| Broken, scanned, or unparseable PDF | Extraction failure | Try the same-owner HTML, formal journal version, or verified complete copy. OCR does not establish authenticity. |
| Metadata/content mismatch | Possible wrong or altered document | Quarantine the copy and continue searching. Never merge it with the intended document. |

## Per-task retry budget

- Use at most two direct retrieval attempts against the same host for the same document.
- For `403`, `412`, CAPTCHA, login walls, or a clear bot challenge, use one attempt only.
- Do not rotate identities, evade access controls, or use unauthorized credentials.
- A slow primary may trigger one hedged request to a pre-approved fallback after roughly two seconds when latency matters. Cancel unnecessary duplicate work after a valid copy is obtained.

## Host circuit breaker

Maintain circuit state separately from medical authority:

- **Closed:** route is eligible.
- **Open:** suppress ordinary requests after three consecutive transient failures, or immediately after a persistent access-control response for the current client.
- **Half-open:** after the cooldown, send one lightweight probe. Close after two successful probes; reopen on failure.

Suggested cooldowns:

- `429`: use `Retry-After`, otherwise 30 minutes;
- `403`/`412`/CAPTCHA for the current client: 15 minutes;
- repeated timeout/`5xx`: 15 minutes;
- `404`/`410`: URL-level circuit remains open until the registry is updated.

These values control traffic only. Never lower or raise evidence authority based on response speed.

## Access-path state machine

1. **Canonical route:** request the original page or attachment.
2. **Same owner:** try official bulletin/archive, attachment server, mobile page, API, HTML/PDF counterpart, or journal subsite.
3. **Official republication:** try a complete government portal copy, joint issuer, supervising body, or official gazette.
4. **Formal publication:** try the journal publisher or DOI-bound version.
5. **Verified complete copy:** use an authorized database or mirror only after document-identity verification.
6. **Metadata only:** use registry/index/secondary coverage to refine discovery; do not extract precise clinical claims.
7. **Stop:** if no complete verified copy exists, report the limitation.

Do not treat multiple copies of the same document as multiple supporting sources.

## Query reconstruction after a stale URL

Prefer identity-bearing queries over broad topic queries:

```text
"exact title" issuer
"exact title" year DOI
"document number" PDF
"exact title" 更新 OR 更正 OR 撤回 OR 废止
site:approved-domain "distinctive title phrase"
```

Do not let a broad query silently substitute a different guideline, consensus, or edition.

## Cache and provenance

An internal cache may speed retrieval when permitted, but it must store provenance:

- canonical URL and retrieval URL;
- retrieval time and HTTP status;
- content hash, size, page count, and media type when available;
- identity fields and verification grade;
- update/correction/withdrawal check time.

Cached content expires for authority purposes when a newer version or correction is detected. A cache hit does not remove the duty to check currency for time-sensitive or high-risk claims.

## Observability

Track at least:

- canonical success rate by host;
- fallback level used and failover latency;
- circuit-open reason and duration;
- identity-match failures;
- incomplete-copy rejections;
- stale-version discoveries;
- high-risk queries stopped because no verified full text was available.

The safety target is zero false substitutions, not a 100% answer rate.
