## Description: <br>
Draft and fill NDA templates, including mutual NDAs, one-way NDAs, and confidentiality agreements, producing signable DOCX files from Common Paper and Bonterms standard forms. <br>

This skill is ready for commercial/non-commercial use. <br>

## Publisher: <br>
[stevenobiajulu](https://clawhub.ai/user/stevenobiajulu) <br>

### License/Terms of Use: <br>
MIT-0 <br>


## Use Case: <br>
External users, developers, and business teams use this skill to choose a standard NDA template, collect required agreement fields, and generate a signable DOCX or markdown preview for review. <br>

### Deployment Geography for Use: <br>
Global <br>

## Known Risks and Mitigations: <br>
Risk: Remote MCP rendering can transmit confidential NDA field values to the hosted Open Agreements service. <br>
Mitigation: Tell the user what data will be sent, obtain explicit consent, and offer the local CLI path for highly sensitive agreements. <br>
Risk: The local CLI path constructs shell commands from user-provided values, including an output filename. <br>
Mitigation: Enforce the documented DOCX filename pattern, reject shell metacharacters and control characters, write values to a chmod 600 mktemp file, and clean it up after use. <br>
Risk: Generated NDAs may be legally insufficient or inappropriate for a specific transaction. <br>
Mitigation: Review the generated DOCX with counsel before signing, especially for non-standard agreements or edits outside template fields. <br>


## Reference(s): <br>
- [ClawHub skill page](https://clawhub.ai/stevenobiajulu/nda) <br>
- [Open Agreements](https://openagreements.org) <br>
- [Open Agreements Remote MCP](https://openagreements.org/api/mcp) <br>
- [open-agreements npm package](https://www.npmjs.com/package/open-agreements) <br>
- [Open Agreements local CLI README](https://github.com/open-agreements/open-agreements#use-with-claude-code) <br>


## Skill Output: <br>
**Output Type(s):** [Guidance, Shell commands, Configuration, Files, Markdown] <br>
**Output Format:** [Markdown guidance with inline shell commands; DOCX files or markdown previews when executed by an agent] <br>
**Output Parameters:** [1D] <br>
**Other Properties Related to Output:** [Remote MCP returns a time-limited download URL; local CLI writes a DOCX file and should use a secure temporary JSON values file.] <br>

## Skill Version(s): <br>
0.2.3 (source: server evidence and frontmatter) <br>

## Ethical Considerations: <br>
Users should evaluate whether this skill is appropriate for their environment, review any generated or modified files before relying on them, and apply their organization's safety, security, and compliance requirements before deployment. <br>
