## Description: <br>
Kaiji Fitness Coach helps agents provide fitness coaching guidance for workout planning, exercise teaching, training-data analysis, nutrition basics, and progression planning using a referenced exercise database. <br>

This skill is ready for commercial/non-commercial use. <br>

## Publisher: <br>
[kaiji-z](https://clawhub.ai/user/kaiji-z) <br>

### License/Terms of Use: <br>
MIT-0 <br>


## Use Case: <br>
External users and agents use this skill to collect relevant fitness context, generate or adjust workout plans, explain exercises, review training reports, and provide general fitness nutrition guidance. It is intended for normal fitness coaching support, not medical diagnosis or individualized clinical advice. <br>

### Deployment Geography for Use: <br>
Global <br>

## Known Risks and Mitigations: <br>
Risk: The skill may ask users for body metrics, injuries, goals, and training history to personalize fitness guidance. <br>
Mitigation: Collect only fitness details needed for the current request, and treat outputs as general coaching guidance rather than medical advice. <br>
Risk: The local database setup downloads an exercise database and --force can replace the local database folder. <br>
Mitigation: Run setup only from the installed skill directory and use --force only when intentionally replacing that exercise database. <br>


## Reference(s): <br>
- [ClawHub skill page](https://clawhub.ai/kaiji-z/kaiji-fitness-coach) <br>
- [free-exercise-db](https://gitee.com/kaiji1126/free-exercise-db) <br>
- [Exercise database schema](references/exercise-db-schema.md) <br>
- [Plan generator reference](references/plan-generator.md) <br>
- [Exercise teaching reference](references/exercise-teaching.md) <br>
- [Nutrition advisor reference](references/nutrition-advisor.md) <br>


## Skill Output: <br>
**Output Type(s):** [text, markdown, JSON, shell commands, guidance] <br>
**Output Format:** [Markdown guidance, Markdown tables, JSON workout plans, and shell command snippets] <br>
**Output Parameters:** [1D] <br>
**Other Properties Related to Output:** [Workout-plan JSON should use database exercise names and the target-muscle schema described by the skill references.] <br>

## Skill Version(s): <br>
2.1.0 (source: server release evidence) <br>

## Ethical Considerations: <br>
Users should evaluate whether this skill is appropriate for their environment, review any generated or modified files before relying on them, and apply their organization's safety, security, and compliance requirements before deployment. <br>
