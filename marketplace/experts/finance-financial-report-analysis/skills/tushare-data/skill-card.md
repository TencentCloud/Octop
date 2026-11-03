## Description: <br>
面向中文自然语言的 Tushare 数据研究技能，用于把股票、基金、财务、估值、资金流、公告新闻、板块概念与宏观数据等研究请求转成可执行的数据获取、清洗、对比、筛选、导出与简要分析流程。 <br>

This skill is ready for commercial/non-commercial use. <br>

## Publisher: <br>
[lidayan](https://clawhub.ai/user/lidayan) <br>

### License/Terms of Use: <br>
MIT-0 <br>


## Use Case: <br>
Developers, analysts, and external users use this skill to turn Chinese natural-language financial research requests into Tushare data retrieval, comparison, export, and concise research-summary workflows. <br>

### Deployment Geography for Use: <br>
Global <br>

## Known Risks and Mitigations: <br>
Risk: The skill uses Tushare network access and may use a sensitive TUSHARE_TOKEN. <br>
Mitigation: Install only in environments where Tushare network access is acceptable, keep the token scoped and protected, and confirm data requests before running live retrieval or export workflows. <br>
Risk: The skill documents self-selected portfolio APIs that can save, modify, or delete watchlists. <br>
Mitigation: Require explicit user confirmation before any watchlist-changing action and keep default workflows focused on read-only research and data export. <br>
Risk: Financial research summaries could be mistaken for investment advice. <br>
Mitigation: Frame outputs as data research, include data scope and limitations, and avoid direct buy, sell, automated trading, or investment-adviser recommendations. <br>


## Reference(s): <br>
- [ClawHub skill page](https://clawhub.ai/lidayan/skills/tushare-data) <br>
- [Tushare API interface reference](references/数据接口.md) <br>
- [Tushare registration and token setup](https://tushare.pro/register) <br>


## Skill Output: <br>
**Output Type(s):** [text, markdown, code, shell commands, configuration, guidance] <br>
**Output Format:** [Markdown with tables, file paths, and optional Python or shell code blocks] <br>
**Output Parameters:** [1D] <br>
**Other Properties Related to Output:** [May produce CSV or Parquet exports and concise research summaries when requested.] <br>

## Skill Version(s): <br>
1.1.19 (source: ClawHub release evidence; artifact frontmatter reports 1.1.16) <br>

## Ethical Considerations: <br>
Users should evaluate whether this skill is appropriate for their environment, review any generated or modified files before relying on them, and apply their organization's safety, security, and compliance requirements before deployment. <br>
