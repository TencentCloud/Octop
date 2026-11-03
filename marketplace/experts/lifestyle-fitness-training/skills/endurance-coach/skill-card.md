## Description: <br>
Create personalized triathlon, marathon, and ultra-endurance training plans. Use when athletes ask for training plans, workout schedules, race preparation, or coaching advice. Can sync with Strava to analyze training history, or work from manually provided fitness data. Generates periodized plans with sport-specific workouts, zones, and race-day strategies. <br>

This skill is ready for commercial/non-commercial use. <br>

## Publisher: <br>
[shiv19](https://clawhub.ai/user/shiv19) <br>

### License/Terms of Use: <br>


## Use Case: <br>
External athletes and coaches use this skill to assess endurance training history, validate constraints and goals, and produce personalized triathlon, marathon, and ultra-endurance training plans. It supports Strava-backed analysis or manually supplied fitness data, then guides zone setup, load management, periodization, workouts, race-day execution, and post-workout review. <br>

### Deployment Geography for Use: <br>
Global <br>

## Known Risks and Mitigations: <br>
Risk: The skill can store sensitive training, health, schedule, and coaching-context information in persistent local files. <br>
Mitigation: Review the local ~/.endurance-coach context and database before and after use, and delete stored context or database files when retention is not desired. <br>
Risk: The skill may use an external endurance-coach npm CLI and optionally authorize Strava access. <br>
Mitigation: Install and run the CLI only from a trusted environment, review requested Strava authorization, and avoid syncing accounts unless the athlete accepts that data flow. <br>
Risk: The security summary notes hidden coach notes and limited user-facing consent or review controls. <br>
Mitigation: Tell the athlete when coaching memory or interview notes are being saved, provide an opportunity to review summaries, and remove notes that should not be retained. <br>


## Reference(s): <br>
- [ClawHub Skill Page](https://clawhub.ai/shiv19/endurance-coach) <br>
- [Athlete Assessment Guide](artifact/reference/assessment.md) <br>
- [Training Load Management](artifact/reference/load-management.md) <br>
- [Periodization & Progressive Overload](artifact/reference/periodization.md) <br>
- [Athlete Assessment Commands](artifact/reference/queries.md) <br>
- [Race Execution & Nutrition Strategy](artifact/reference/race-day.md) <br>
- [Database Schema Reference](artifact/reference/schema.md) <br>
- [Workout Templates Reference](artifact/reference/templates.md) <br>
- [Workout Library](artifact/reference/workouts.md) <br>
- [Training Zones & Field Testing](artifact/reference/zones.md) <br>


## Skill Output: <br>
**Output Type(s):** [Text, Markdown, Code, Shell commands, Configuration, Guidance, Files] <br>
**Output Format:** [Markdown guidance with inline shell commands, compact YAML v2.0 plan data, and generated HTML when rendered through the endurance-coach CLI.] <br>
**Output Parameters:** [1D] <br>
**Other Properties Related to Output:** [May create or update local athlete context, training database, workout interview, trigger, and rendered plan files under ~/.endurance-coach or user-selected plan paths.] <br>

## Skill Version(s): <br>
1.4.0 (source: server release metadata) <br>

## Ethical Considerations: <br>
Users should evaluate whether this skill is appropriate for their environment, review any generated or modified files before relying on them, and apply their organization's safety, security, and compliance requirements before deployment. <br>
