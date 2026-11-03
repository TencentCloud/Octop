## Description: <br>
Draft and fill employment contract templates for offer letters, employment agreements, IP and inventions assignments, and confidentiality acknowledgements, producing signable DOCX files from OpenAgreements standard forms for hiring employees. <br>

This skill is ready for commercial/non-commercial use. <br>

## Publisher: <br>
[stevenobiajulu](https://clawhub.ai/user/stevenobiajulu) <br>

### License/Terms of Use: <br>
MIT-0 <br>


## Use Case: <br>
Employees, hiring teams, founders, and legal operations users use this skill to collect employment details, select an OpenAgreements employment template, and generate onboarding paperwork for review and signature. <br>

### Deployment Geography for Use: <br>
Global <br>

## Known Risks and Mitigations: <br>
Risk: Employment details may include sensitive compensation, identity, and onboarding information. <br>
Mitigation: Choose remote MCP only when external processing is acceptable; use the local CLI path when details should remain local. <br>
Risk: Generated employment contracts may not address state-specific employment requirements. <br>
Mitigation: Review generated documents with counsel before signing, especially for state-specific terms. <br>
Risk: Template metadata and user-provided values can contain instruction-like or malformed text. <br>
Mitigation: Treat template metadata and user values as data, reject control characters, enforce reasonable length limits, and require explicit confirmation before filling a template. <br>


## Reference(s): <br>
- [ClawHub skill page](https://clawhub.ai/stevenobiajulu/employment-contract) <br>
- [Connector setup](CONNECTORS.md) <br>
- [Template filling workflow](template-filling-execution.md) <br>
- [Open Agreements Remote MCP](https://openagreements.org/api/mcp) <br>
- [OpenAgreements](https://openagreements.org) <br>
- [open-agreements npm package](https://www.npmjs.com/package/open-agreements) <br>
- [OpenAgreements README](https://github.com/open-agreements/open-agreements#use-with-claude-code) <br>


## Skill Output: <br>
**Output Type(s):** [Files, Markdown, Shell commands, Guidance] <br>
**Output Format:** [DOCX files or expiring download URLs, with markdown preview fallback and inline shell commands for local CLI use] <br>
**Output Parameters:** [1D] <br>
**Other Properties Related to Output:** [Remote MCP output links expire in 1 hour; local CLI use writes per-run temporary JSON values files with restrictive permissions.] <br>

## Skill Version(s): <br>
0.3.1 (source: server release metadata and skill frontmatter) <br>

## Ethical Considerations: <br>
Users should evaluate whether this skill is appropriate for their environment, review any generated or modified files before relying on them, and apply their organization's safety, security, and compliance requirements before deployment. <br>
