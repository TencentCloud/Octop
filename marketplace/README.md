# Community catalog

[中文版](./README_CN.md)

Experts, their skills, and plugins removed from the install tree on
`feature/remote-plugin-and-expert-market`. The wheel still ships only the
blank `default` expert. Product installs come from the remote expert,
skill, and plugin markets.

This tree is the previous in-repo catalog, kept at the repository root so
it can be maintained with the community. Octop does not scan it at startup
and does not pack it into the wheel or the Docker image.

```text
marketplace/
├── experts/    # one directory per expert; skills live in skills/<name>/
└── plugins/    # one directory per plugin (plugin.yaml + main.py)
```

There was no separate on-disk skill-market catalog. Each skill is the
`skills/<name>/SKILL.md` package inside its expert.

`experts/<skillset-slug>` is the 54-expert SkillHub market catalog,
appended beside the former built-in experts. Four skill packages 404 on
SkillHub's download API and were fetched from ClawHub using the owner in
the SkillHub detail: `competitive-intelligence-market-research`,
`content-writer`, `academic-researcher`, and
`jackyshen-design-workshop-outline`.
