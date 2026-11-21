"""Gateway media handling.

Three cohesive concerns, one per submodule:

- :mod:`.ingress` — ``AgentBackedMediaBackend``: the octop-gateway
  ``MediaBackend`` adapter that persists inbound IM attachments.
- :mod:`.backend_files` — binary file I/O + dashboard media preview/URL
  resolution and host-path guards, all through ``agent.backend``.
- :mod:`.tool_media` — enrich tool-result payloads with media for the
  Dashboard WebSocket stream (builds on :mod:`.backend_files`).
"""
