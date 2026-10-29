# Agent deletion lifecycle evidence

The PNG is a headless-browser capture of a local HTML verification report rendered
from actual completed test logs. It is not a product UI screenshot, a hosted CI
result, or an assertion that a human has reviewed the code.

Baseline: upstream develop `44c22434b090cb78d3a4a2d6fad786e7bbc95863`.
The four baseline failures exercise real SQLite and the real Harness registry and
graph compiler. Event barriers control compilation or storage cleanup; they do not
replace runtime creation/removal or database effects.

- Baseline regression: **4 failed, 2 passed in 2.30s**. Raw-log SHA-256: `8b481a9a76061db474ba3497b0623c44e8e22512865bb2ba33116ac50ea3aec5`.
- Final related suite: **144 passed, 1 skipped in 7.32s**. Raw-log SHA-256: `33f9b9f8f434fda9cd61597d001c108c67a0499ac8a2352dbe69e917cc8b0fac`.
- Full make all: **5311 passed, 34 skipped, 9 warnings in 279.84s (0:04:39)**. Raw-log SHA-256: `b7139ab8ab985eeb1e4741ab115c2a8906d2cc0146e3180f7b6ad84397f5ad86`.

Independent AI re-review passed all seven new lifecycle regressions and the
original separate team-creation reproduction after its finding was fixed.

The first sandboxed full run had 6 failures and 15 setup errors from prohibited
loopback binding/DNS. The final make-all run used those normal test capabilities;
no tests were excluded, assertions changed, or CI waivers added to address that.
The normal commit hook and dashboard build are recorded separately in the PR body.

No native Windows, live model/provider, operator database, cross-process fencing,
or cancelled detached compilation/cleanup-thread guarantee is claimed.
