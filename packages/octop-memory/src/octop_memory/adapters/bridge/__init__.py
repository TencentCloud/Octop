"""OpenClaw/Hermes memory bridge protocol.

This subpackage hosts the Python side of the octopmemory ↔ OpenClaw
plugin bridge. The TS plugin shell (``plugins/openclaw/octopmemory/``)
spawns ``octopmemory-bridge`` as a subprocess and talks to it over
stdin/stdout using a tiny JSON-RPC 2.0 dialect.

Design:

- **D51-C** (path projection, 2026-06-04 locked):
  ``path_projection`` projects SQLite-backed atoms / pages / raw events
  onto a *virtual* file tree (``atom/<id>.md`` etc.) so OpenClaw's
  file-shaped ``memory_get(path, from, lines)`` API works against our
  storage. Real files (``MEMORY.md``, ``memory/YYYY-MM-DD.md``) are
  ALSO indexed via ``host_files`` so the host's compaction
  silent turn is preserved verbatim.

- **D52-C** (auto-capture, 2026-06-04 locked):
  ``handlers.capture`` is the entry point for the TS ``agent_end``
  hook; it validates and filters a batch, then writes it synchronously
  through ``Memory.add_raw_batch``.

The bridge is intentionally minimal: no auth, no encryption — it runs
as a child process of OpenClaw on the same machine as the user.
It does not expose a TCP/HTTP or remote multi-tenant transport.
"""

from __future__ import annotations

__all__ = [
    "PROTOCOL_VERSION",
]

PROTOCOL_VERSION = "1.0"
"""Wire protocol version. Bumped only on breaking changes to the JSON-RPC
method names or payload schemas. The TS client checks this on
``handshake`` and refuses to start on mismatch."""
