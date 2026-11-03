## Description: <br>
Create and manage Product Requirements Documents (PRDs). Use when: (1) Creating structured task lists with user stories, (2) Specifying features with acceptance criteria, (3) Planning feature implementation for AI agents or human developers. <br>

This skill is ready for commercial/non-commercial use. <br>

## Publisher: <br>
[bjesuiter](https://clawhub.ai/user/bjesuiter) <br>

### License/Terms of Use: <br>


## Use Case: <br>
Developers, product managers, and coding-agent users use this skill to define PRDs as ordered user stories with verifiable acceptance criteria, then track implementation progress through PRD files. <br>

### Deployment Geography for Use: <br>
Global <br>

## Known Risks and Mitigations: <br>
Risk: The skill documentation includes an unattended coding-agent loop that bypasses permissions and can run indefinitely. <br>
Mitigation: Use a reviewed human-in-the-loop workflow or an isolated worktree, and only run unattended permission-bypass loops when deliberately accepting automated file changes and commits. <br>


## Reference(s): <br>
- [Agent Usage Patterns](references/agent-usage.md) <br>
- [Output Patterns and Templates](references/output-patterns.md) <br>
- [Workflow Patterns for PRD Skills](references/workflows.md) <br>
- [ClawHub Skill Page](https://clawhub.ai/bjesuiter/prd) <br>
- [Ralph by snarktank](https://github.com/snarktank/ralph) <br>
- [Claude Code](https://github.com/anthropics/claude-code) <br>
- [Amp Code](https://ampcode.com) <br>
- [Tips for AI Coding with Ralph Wiggum](https://www.aihero.dev/tips-for-ai-coding-with-ralph-wiggum) <br>


## Skill Output: <br>
**Output Type(s):** [Text, Markdown, JSON, Shell commands, Guidance] <br>
**Output Format:** [Markdown guidance with JSON PRD templates and inline shell command examples] <br>
**Output Parameters:** [1D] <br>
**Other Properties Related to Output:** [Produces PRD structure, acceptance-criteria patterns, workflow guidance, and agent execution prompts.] <br>

## Skill Version(s): <br>
2.0.5 (source: server release metadata) <br>

## Ethical Considerations: <br>
Users should evaluate whether this skill is appropriate for their environment, review any generated or modified files before relying on them, and apply their organization's safety, security, and compliance requirements before deployment. <br>
