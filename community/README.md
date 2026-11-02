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
community/
├── experts/    # one directory per expert; skills live in skills/<name>/
└── plugins/    # one directory per plugin (plugin.yaml + main.py)
```

There was no separate on-disk skill-market catalog. Each skill is the
`skills/<name>/SKILL.md` package inside its expert.
