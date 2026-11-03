## Description: <br>
Access Whoop wearable health data (sleep, recovery, strain, HRV, workouts) and generate interactive charts. <br>

This skill is ready for commercial/non-commercial use. <br>

## Publisher: <br>
[rodrigouroz](https://clawhub.ai/user/rodrigouroz) <br>

### License/Terms of Use: <br>


## Use Case: <br>
People who use Whoop can let an agent retrieve their sleep, recovery, strain, HRV, workout, profile, and body-measurement data to summarize trends and create visual health charts. The skill is useful for personal wellness analysis, but its outputs should not be treated as medical advice. <br>

### Deployment Geography for Use: <br>
Global <br>

## Known Risks and Mitigations: <br>
Risk: The skill requests broad read access to sensitive Whoop health, profile, and body-measurement data. <br>
Mitigation: Grant access only when this scope is acceptable, review the requested OAuth scopes before authorizing, and revoke access when the analysis is no longer needed. <br>
Risk: OAuth tokens, terminal output, and generated HTML charts can expose private health or credential material. <br>
Mitigation: Treat generated data and charts as private, avoid printing tokens unless necessary, protect ~/.clawdbot/whoop-tokens.json, and delete or revoke tokens after use. <br>
Risk: Health interpretations can be incomplete or misleading if treated as diagnosis. <br>
Mitigation: Use the results as wellness context only, include the skill's medical-advice disclaimer, and consult a qualified clinician for medical concerns or persistent red flags. <br>


## Reference(s): <br>
- [Whoop API Reference](references/api.md) <br>
- [Health Data Analysis Guide](references/health_analysis.md) <br>
- [Whoop Developer Dashboard](https://developer-dashboard.whoop.com) <br>


## Skill Output: <br>
**Output Type(s):** [guidance, shell commands, configuration, JSON, files] <br>
**Output Format:** [Markdown guidance with shell commands; scripts return JSON and generated HTML charts.] <br>
**Output Parameters:** [1D] <br>
**Other Properties Related to Output:** [Requires user-provided Whoop OAuth credentials and stores refreshable tokens locally.] <br>

## Skill Version(s): <br>
1.1.0 (source: server release metadata) <br>

## Ethical Considerations: <br>
Users should evaluate whether this skill is appropriate for their environment, review any generated or modified files before relying on them, and apply their organization's safety, security, and compliance requirements before deployment. <br>
