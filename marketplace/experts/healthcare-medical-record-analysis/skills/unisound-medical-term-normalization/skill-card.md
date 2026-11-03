## Description: <br>
Normalizes colloquial medical record text into standardized clinical documentation with regulated terminology, stricter wording, normalized data formats, and preserved record structure. <br>

This skill is ready for commercial/non-commercial use. <br>

## Publisher: <br>
[unisound-llm](https://clawhub.ai/user/unisound-llm) <br>

### License/Terms of Use: <br>
MIT-0 <br>


## Use Case: <br>
Clinical operations teams, medical documentation reviewers, and developers can use this skill to convert de-identified colloquial medical notes into standardized record text for documentation cleanup, quality review, archiving, reimbursement workflows, or downstream analytics. A licensed clinician should review outputs before clinical use. <br>

### Deployment Geography for Use: <br>
Global <br>

## Known Risks and Mitigations: <br>
Risk: Medical record text may contain sensitive personal or health information and is sent to a remote model endpoint. <br>
Mitigation: Use only de-identified records and remove names, IDs, phone numbers, addresses, and other identifiers before running the skill. <br>
Risk: Prepared input or normalized output can be written to disk when optional save or output flags are used. <br>
Mitigation: Avoid --save-prepared and output-file flags unless local persistence is intended and storage controls are in place. <br>
Risk: Normalized medical text may be incorrect, incomplete, or unsuitable for direct clinical use. <br>
Mitigation: Require review by a licensed clinician before relying on the output for clinical documentation or decision-making. <br>


## Reference(s): <br>
- [ClawHub skill page](https://clawhub.ai/unisound-llm/skills/unisound-medical-term-normalization) <br>
- [Publisher profile](https://clawhub.ai/user/unisound-llm) <br>


## Skill Output: <br>
**Output Type(s):** [text, markdown, JSON, files, shell commands, guidance] <br>
**Output Format:** [UTF-8 standardized medical record text, with optional text or JSON file output] <br>
**Output Parameters:** [1D] <br>
**Other Properties Related to Output:** [Accepts PDF, DOC, DOCX, XLS, XLSX, CSV, TXT, or JSON input; JSON may include records, record, text, content, or prompt fields.] <br>

## Skill Version(s): <br>
1.0.2 (source: server release metadata) <br>

## Ethical Considerations: <br>
Users should evaluate whether this skill is appropriate for their environment, review any generated or modified files before relying on them, and apply their organization's safety, security, and compliance requirements before deployment. <br>
