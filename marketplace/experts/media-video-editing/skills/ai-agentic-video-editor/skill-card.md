## Description: <br>
AI agentic video editor: send a prompt, the autonomous editor plans, uses internal tools, exports, and returns the result. <br>

This skill is ready for commercial/non-commercial use. <br>

## Publisher: <br>
[brajendrak00068](https://clawhub.ai/user/brajendrak00068) <br>

### License/Terms of Use: <br>
MIT-0 <br>


## Use Case: <br>
External users and developers use this skill to request natural-language video edits, preview planned changes, manage asynchronous editing jobs, and export finished MP4 or ZIP video deliverables through the Levea/Livecore service. <br>

### Deployment Geography for Use: <br>
Global <br>

## Known Risks and Mitigations: <br>
Risk: The skill sends video prompts, project or scene data, asset URLs, and related media metadata to the Levea/Livecore cloud service. <br>
Mitigation: Install and use it only when that data sharing is acceptable, and avoid submitting sensitive media unless the service handling is approved for that content. <br>
Risk: Mutating edits, auto-export behavior, or approval prompts can result in real changes to user media workflows. <br>
Mitigation: Use plan approval for risky or destructive edits, require explicit confirmation before execution, and preview all exports before publishing or sharing. <br>


## Reference(s): <br>
- [ClawHub Skill Listing](https://clawhub.ai/brajendrak00068/ai-agentic-video-editor) <br>
- [Publisher Profile](https://clawhub.ai/user/brajendrak00068) <br>
- [OpenClaw AI Video Editor README](https://github.com/brajendrak00068/openclaw-ai-video-editor#readme) <br>
- [Levea MCP Server](https://www.npmjs.com/package/levea-mcp-server) <br>
- [Livecore API](https://api.livecore.ai) <br>
- [Livecore Studio](https://studio.livecore.ai) <br>


## Skill Output: <br>
**Output Type(s):** [guidance, shell commands, configuration, API calls, JSON, markdown] <br>
**Output Format:** [Markdown guidance with shell commands and JSON request or response examples.] <br>
**Output Parameters:** [1D] <br>
**Other Properties Related to Output:** [May produce video export URLs, async job IDs, project or scene data, and ZIP package links from the remote editing service.] <br>

## Skill Version(s): <br>
1.0.21 (source: ClawHub release metadata) <br>

## Ethical Considerations: <br>
Users should evaluate whether this skill is appropriate for their environment, review any generated or modified files before relying on them, and apply their organization's safety, security, and compliance requirements before deployment. <br>
