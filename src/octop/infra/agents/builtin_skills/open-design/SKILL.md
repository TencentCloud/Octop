---
name: open-design
description: Use when the user selects the OpenDesign connector to create or refine websites, prototypes, slides or visual artifacts. 用户选择 OpenDesign 连接器生成或修改设计时使用。
metadata:
  octop:
    emoji: "🎨"
    label:
      zh: "OpenDesign 设计"
      en: "OpenDesign Design"
    summary:
      zh: "通过已选择的 OpenDesign 连接器确认需求、生成设计并交付预览。"
      en: "Confirm a brief, generate designs and deliver previews through the selected connector."
---

# OpenDesign

Use only the OpenDesign connector selected for this conversation. All tool names
are prefixed by its server name. Do not install software, run CLI authentication,
or substitute shell commands when the connector is unavailable; direct the user
to the connector settings.

1. For a new artifact, call collect_brief with the request language and answers
   already supplied. Present its questions using the host's question tool or
   ordinary conversation. Ask only for missing design decisions. Use defaults
   without asking only when the user requested that behavior.
2. Call confirm_brief with the returned internal draft ID, nonce and actual user
   answers. Never display those internal values. If the draft expired or the MCP
   process restarted, recollect with the known answers; do not invent confirmation.
3. Discover available skills, plugins and agents when needed. Use list_resources
   and read_resource for design-system or skill context. Do not guess identifiers.
4. Create or choose a project. Pass its project ID explicitly to every project
   operation. The user's currently open OpenDesign project may be unrelated.
5. Submit start_run with the confirmed brief. Keep its requestId and runId. A
   transport retry must reuse the same requestId and parameters. A requested
   design revision is a new action in the same project, with a new requestId.
6. Query get_run or the host task_status tool. For a request to wait, use
   task_status(wait=true): the host polls every 30 seconds for at most 60 seconds.
   Avoid tight loops or shell sleeps. If still running, report its state and
   retain its identity for the next message. Do not start another run or
   overwrite files to bypass a pending run.
7. On success, show the preview link and the generator's explanation. If no
   preview exists, report what the generator returned without claiming an artifact
   exists. On failure, explain the returned actionable cause. Refresh get_run if
   a preview link stopped working after an OpenDesign restart.
8. Fetch source with get_artifact only when needed. Respect truncation and page
   through get_file when necessary. Direct edits with write_file require the
   user's editing intent; do not silently replace OpenDesign generation.
9. Cancel with cancel_run only when the user asks to cancel generation. Stopping
   an Octop reply does not mean canceling the upstream task.

Model credentials and the generation runtime are configured in OpenDesign.
This connector does not promise binary export, file synchronization or automatic
completion notifications. Deliver preview links and source on demand.
