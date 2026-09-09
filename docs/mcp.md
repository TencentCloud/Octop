# Octop connector-management MCP server

`octop mcp` exposes a local stdio MCP server that lets an authenticated Octop
user manage custom MCP connectors through an MCP-capable agent. It calls the
running Octop HTTP API, so the existing ownership, validation, audit, and agent
reload paths remain authoritative.

## Prerequisites

1. Initialize Octop and start the service with `octop run`.
2. Pin a CLI user with `octop config set-user <username>`, or pass `--user`.
3. Configure the command as a local stdio MCP server in the client.

Example configuration:

```json
{
  "mcpServers": {
    "octop-control": {
      "command": "octop",
      "args": ["mcp", "--user", "alice"]
    }
  }
}
```

To use it from Octop itself, add that stdio entry once in **Connectors ->
Custom MCP**. The bundled `octop-assistant` skill then prefers the resulting
`octop_*` tools when the user asks to manage a connector in chat.

The Octop server must already be running. To target a non-default address:

```json
{
  "command": "octop",
  "args": [
    "mcp",
    "--user",
    "alice",
    "--base-url",
    "http://127.0.0.1:8088"
  ]
}
```

## Tools

| Tool | Purpose |
|---|---|
| `octop_get_status` | Check the service and authenticated management user |
| `octop_list_connectors` | List connector metadata without stored credentials |
| `octop_add_mcp_connector` | Add a Streamable HTTP custom MCP connector |
| `octop_configure_mcp_connector` | Change enabled, default-open, or shared flags |
| `octop_test_mcp_connector` | Probe connectivity and tool discovery |
| `octop_delete_mcp_connector` | Permanently remove a custom MCP connector |

Adding or changing a connector schedules the same agent reload used by the
dashboard. When Octop is managing its own connector list, the active chat may
briefly reconnect after a successful tool call.

## Security

- The stdio command resolves one explicit or CLI-pinned Octop user and mints a
  short-lived local JWT. Requests still pass through the normal HTTP API.
- Listing and mutation results omit stored request headers and credentials.
- The add tool accepts headers because many remote MCP servers require a bearer
  token, but never returns their values.
- Only Streamable HTTP connectors can be created through chat. Arbitrary stdio
  commands must still be configured manually in the dashboard.
- MCP clients should require confirmation before calling the delete tool or
  changing connector sharing.
