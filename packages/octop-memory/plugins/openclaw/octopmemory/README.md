# OctopMemory for OpenClaw

OpenClaw memory plugin backed by the Python `octop-memory` runtime.

```bash
uv tool install 'octop-memory[cli]'
openclaw plugins install @octop-memory/openclaw
octop-memory openclaw setup
openclaw gateway restart
octop-memory openclaw doctor
```

Requires Python 3.12+ with SQLite FTS5 and a host version compatible with `package.json`.
Installation, configuration, profiles, troubleshooting and adapter development share one
[OpenClaw / Hermes guide](https://github.com/TencentCloud/octop-memory/blob/main/docs/integrations.md#openclaw).
