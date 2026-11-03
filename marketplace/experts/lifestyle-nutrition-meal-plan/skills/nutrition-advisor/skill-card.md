## Description: <br>
科学营养顾问 helps users estimate food calories, calculate BMR/TDEE and macronutrient targets, plan meals, and track nutrition, hydration, habits, menstrual-cycle context, and related wellness patterns. <br>

This skill is ready for commercial/non-commercial use. <br>

## Publisher: <br>
[yamyeed](https://clawhub.ai/user/yamyeed) <br>

### License/Terms of Use: <br>
MIT-0 <br>


## Use Case: <br>
External users use this skill for general wellness-oriented nutrition support: calorie lookup, meal planning, macro targets, diet logs, hydration tracking, menstrual-cycle nutrition context, and scenario-specific eating suggestions. It is not a substitute for medical or professional nutrition care. <br>

### Deployment Geography for Use: <br>
Global <br>

## Known Risks and Mitigations: <br>
Risk: The skill can store body metrics, cycle information, allergies, meals, hydration, and habit data locally under ~/nutrition-data. <br>
Mitigation: Install only if comfortable with this local storage, avoid entering unnecessary sensitive data, and review or delete the local files if you stop using the skill. <br>
Risk: Nutrition calculations and meal suggestions may be incorrect or unsuitable for medical conditions, pregnancy, eating disorders, allergies, or other high-risk contexts. <br>
Mitigation: Treat outputs as general wellness guidance and consult qualified healthcare or nutrition professionals for medical or high-risk nutrition decisions. <br>


## Reference(s): <br>
- [ClawHub skill page](https://clawhub.ai/yamyeed/skills/nutrition-advisor) <br>
- [ClawHub publisher profile](https://clawhub.ai/user/yamyeed) <br>


## Skill Output: <br>
**Output Type(s):** [text, markdown, configuration, guidance] <br>
**Output Format:** [Markdown guidance with tables, calculations, JSON examples, and local file path references] <br>
**Output Parameters:** [1D] <br>
**Other Properties Related to Output:** [May optionally read and write local JSON profile and log files under ~/nutrition-data when the user asks to save, update, or track nutrition data.] <br>

## Skill Version(s): <br>
4.2.2 (source: server release metadata; artifact SKILL.md reports 4.2.0 and artifact _meta.json reports 4.2.1) <br>

## Ethical Considerations: <br>
Users should evaluate whether this skill is appropriate for their environment, review any generated or modified files before relying on them, and apply their organization's safety, security, and compliance requirements before deployment. <br>
