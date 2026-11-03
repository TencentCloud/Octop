## Description: <br>
Syncs daily Garmin Connect health and fitness data into local Markdown files, including sleep, activity, heart rate, stress, body battery, HRV, SpO2, and weight data. <br>

This skill is ready for commercial/non-commercial use. <br>

## Publisher: <br>
[freakyflow](https://clawhub.ai/user/freakyflow) <br>

### License/Terms of Use: <br>


## Use Case: <br>
External users use this skill to sync Garmin Connect health and fitness data into local Markdown files so an agent can reference recent personal metrics in conversation. <br>

### Deployment Geography for Use: <br>
Global <br>

## Known Risks and Mitigations: <br>
Risk: The skill uses an unofficial Garmin login flow and may require weakening account security by disabling two-factor authentication. <br>
Mitigation: Install only if that tradeoff is acceptable, and avoid using it with an important Garmin account unless the account-takeover risk is understood. <br>
Risk: Long-lived Garmin tokens are stored locally and can grant access to the user's Garmin account. <br>
Mitigation: Keep ~/.garminconnect private, encrypted where possible, and out of cloud sync, backups shared with others, and public repositories. <br>
Risk: Synced Markdown files contain personal health and fitness data in plaintext. <br>
Mitigation: Store the health output directory in a private location, restrict file access, and exclude it from public repositories or shared folders. <br>


## Reference(s): <br>
- [ClawHub release page](https://clawhub.ai/freakyflow/garmin-pulse) <br>
- [Publisher profile](https://clawhub.ai/user/freakyflow) <br>
- [uv documentation](https://docs.astral.sh/uv/) <br>
- [Garmin Connect](https://connect.garmin.com) <br>
- [python-garminconnect](https://github.com/cyberjunky/python-garminconnect) <br>
- [cloudscraper](https://github.com/VeNoMouS/cloudscraper) <br>


## Skill Output: <br>
**Output Type(s):** [Markdown, Shell commands, Guidance] <br>
**Output Format:** [Markdown files and inline shell commands] <br>
**Output Parameters:** [1D] <br>
**Other Properties Related to Output:** [Writes one health/YYYY-MM-DD.md file per synced day and uses cached Garmin tokens after setup.] <br>

## Skill Version(s): <br>
1.3.1 (source: server release metadata and SKILL.md frontmatter) <br>

## Ethical Considerations: <br>
Users should evaluate whether this skill is appropriate for their environment, review any generated or modified files before relying on them, and apply their organization's safety, security, and compliance requirements before deployment. <br>
