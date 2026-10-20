# Expert template library (read-only bundled content)

This directory holds **static expert templates** shipped with agentbuddy: manifests,
markdown persona files, and optional skill scripts. It is **not** runtime Python
code — treat it as data.

- **Scanner code:** `catalog.py` (parent directory)
- **Do not** refactor or lint-fix files here unless updating a template itself
- Large skill script trees (e.g. `office-automation/`) are intentional bundle assets
