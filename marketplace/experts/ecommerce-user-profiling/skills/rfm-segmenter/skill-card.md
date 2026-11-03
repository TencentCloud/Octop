## Description: <br>
Segment your customer base using Recency, Frequency, and Monetary value scoring to identify Champions, Loyal Customers, At-Risk buyers, and Churned segments - then generate targeted retention and reactivation campaigns for each group. <br>

This skill is ready for commercial/non-commercial use. <br>

## Publisher: <br>
[leooooooow](https://clawhub.ai/user/leooooooow) <br>

### License/Terms of Use: <br>
MIT-0 <br>


## Use Case: <br>
Marketing and ecommerce teams use this skill to turn customer order data into RFM segments, identify retention and reactivation opportunities, and plan segment-specific campaigns. <br>

### Deployment Geography for Use: <br>
Global <br>

## Known Risks and Mitigations: <br>
Risk: Campaign recommendations may include SMS, phone, email, or advertising outreach that is subject to consent, opt-out, do-not-call, and privacy rules. <br>
Mitigation: Use only approved customer data, confirm required consent before outreach, honor opt-outs and unsubscribe requests, screen do-not-call restrictions, and verify applicable GDPR, CCPA, TCPA, and CAN-SPAM obligations before launching campaigns. <br>
Risk: Incorrect or stale order data can produce misleading segment assignments and poor campaign targeting. <br>
Mitigation: Validate the data source, subtract refunds, remove test and internal orders, merge duplicate customer records, exclude cancelled orders, and review segment sizes before sending campaigns. <br>


## Reference(s): <br>
- [ClawHub skill page](https://clawhub.ai/leooooooow/rfm-segmenter) <br>
- [Output Template](artifact/output-template.md) <br>
- [Segment Action Playbook](artifact/segment-action-playbook.md) <br>
- [Scoring Methodology Guide](artifact/scoring-methodology.md) <br>
- [Quality Checklist](artifact/checklist.md) <br>


## Skill Output: <br>
**Output Type(s):** [text, markdown, guidance] <br>
**Output Format:** [Markdown report guidance with RFM scoring tables, segment summaries, campaign matrices, and checklists.] <br>
**Output Parameters:** [1D] <br>
**Other Properties Related to Output:** [Uses customer-level order data, including customer identifier, order date, and net order value, to guide segmentation and campaign planning.] <br>

## Skill Version(s): <br>
1.1.0 (source: server release metadata) <br>

## Ethical Considerations: <br>
Users should evaluate whether this skill is appropriate for their environment, review any generated or modified files before relying on them, and apply their organization's safety, security, and compliance requirements before deployment. <br>
