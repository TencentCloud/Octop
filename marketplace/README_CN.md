# 社区目录

[English](./README.md)

`feature/remote-plugin-and-expert-market` 从安装包里拿掉的专家、技能和插件。
安装包仍只带空白的 `default` 专家。产品里的专家、技能、插件从远程市场安装。

这里是原先随仓库分发的目录，放在仓库根目录，方便之后和社区一起改。
Octop 启动时不会扫描这里，也不会打进 wheel 或 Docker 镜像。

```text
marketplace/
├── experts/    # 每个专家一个目录；技能在 skills/<name>/
└── plugins/    # 每个插件一个目录（plugin.yaml + main.py）
```

技能市场没有单独的本地目录。每份技能都是所属专家里的
`skills/<name>/SKILL.md`。

`experts/<技能集 slug>` 是从 SkillHub 专家市场拉下来的 54 个专家，
追加在原先的内置专家旁边。其中 4 个技能包在 SkillHub 下载接口返回 404，
按详情里的作者从 ClawHub 取回：`competitive-intelligence-market-research`、
`content-writer`、`academic-researcher`、`jackyshen-design-workshop-outline`。
