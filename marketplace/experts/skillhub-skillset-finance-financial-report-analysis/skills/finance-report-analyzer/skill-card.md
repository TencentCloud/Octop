## Description: <br>
Analyze financial data from uploaded Excel/PDF files and generate interactive reports with sparkline trend charts. <br>

This skill is ready for commercial/non-commercial use. <br>

## Publisher: <br>
[qiujiahong](https://clawhub.ai/user/qiujiahong) <br>

### License/Terms of Use: <br>
MIT <br>


## Use Case: <br>
Finance, operations, or analyst users can use this skill to turn financial spreadsheets, PDFs, local files, pasted data, or Feishu-hosted files into formatted company analysis reports. It is useful when a user needs trend charts, financial metric summaries, risk analysis, or HTML/PDF/DOCX/Markdown report output from company financial data. <br>

### Deployment Geography for Use: <br>
Global <br>

## Known Risks and Mitigations: <br>
Risk: The skill uses Feishu app credentials and can transmit financial files or generated reports through Feishu. <br>
Mitigation: Use only approved Feishu workspaces, confirm recipients and file destinations before sending, and avoid confidential financial data unless the destination is authorized. <br>
Risk: The security review notes runtime package installation without enough safeguards. <br>
Mitigation: Preinstall and pin required dependencies in a controlled environment before running the skill. <br>
Risk: PDF conversion depends on external tools such as wkhtmltopdf or Chromium. <br>
Mitigation: Run document conversion in a sandboxed environment and review generated reports before distribution. <br>


## Reference(s): <br>
- [ClawHub Skill Page](https://clawhub.ai/qiujiahong/finance-report-analyzer) <br>
- [Financial Metrics Reference](references/metrics.md) <br>
- [Feishu Authentication API](https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal) <br>
- [Feishu File Upload API](https://open.feishu.cn/open-apis/im/v1/files) <br>


## Skill Output: <br>
**Output Type(s):** [text, markdown, code, shell commands, configuration, files] <br>
**Output Format:** [HTML report with optional PDF, DOCX, and Markdown files] <br>
**Output Parameters:** [1D] <br>
**Other Properties Related to Output:** [Reports may include inline SVG sparklines, forecast markers, financial metric tables, section-level analysis, and generated risk/opportunity commentary.] <br>

## Skill Version(s): <br>
1.2.0 (source: server release metadata) <br>

## Ethical Considerations: <br>
Users should evaluate whether this skill is appropriate for their environment, review any generated or modified files before relying on them, and apply their organization's safety, security, and compliance requirements before deployment. <br>
