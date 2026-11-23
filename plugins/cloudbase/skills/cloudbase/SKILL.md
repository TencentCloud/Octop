---
name: cloudbase
description: Tencent CloudBase backend platform — database, auth, storage, cloud functions and hosting. Use when the user wants a backend for a web app, mini program, or AI agent, or needs to deploy/manage CloudBase resources.
version: 0.1.0
license: MIT
---

# CloudBase

CloudBase (腾讯云开发) is a managed backend: document database, PostgreSQL/MySQL, auth
(including WeChat mini program login), object storage, cloud functions, static hosting and
container hosting. It is what many Chinese AI coding products use as the "backend box" behind
vibe-coding tools.

## When to use this skill

- The user wants to build something full-stack and asks where the backend/database lives.
- The user has a mini program, H5 or web app and needs auth, storage or a deploy target.
- The user asks to deploy, inspect or debug CloudBase resources.

Do not use it for generic cloud questions unrelated to CloudBase.

## Connecting the tools

The platform is driven through an MCP server. Two modes:

- **Remote (recommended, no local install):** Streamable HTTP at
  `https://tcb-api.cloud.tencent.com/mcp/v1` (international: `https://tcb-api.tencentcloud.com/mcp/v1`).
  The client walks OAuth 2.1 on its own — dynamic client registration, browser login,
  environment picker, token exchange. The user never pastes a SecretId.
- **Local:** `npx -y @cloudbase/cloudbase-mcp@latest` when the environment has no outbound
  access to the hosted endpoint.

In Octop, add the remote server as an MCP connector rather than asking the user for keys.

## How to work

1. Read the environment id before doing anything destructive; never guess one.
2. Prefer reading current state (list environments, describe collections) over assuming.
3. Confirm before any delete/destroy operation — those are not recoverable.
4. Keep credentials out of files and out of the conversation.

## Out of scope

This skill does not fetch remote documentation at runtime. If a referenced page is needed,
tell the user which URL to open instead of pulling markdown into the conversation.
