# 第三方来源与改编说明

本 Octop 专家中的工作流设计改编自 **Anthropic Knowledge Work Plugins** 的 `operations` 插件，版本为 **1.3.0**。上游 Git 仓库：

https://github.com/anthropics/knowledge-work-plugins

固定上游提交：`02ffa99ff00ce4d3046ccebabb8357cb39f3ab06`

上游来源文件与本地改编位置：

| 上游来源 | Octop 改编技能 |
| --- | --- |
| `operations/skills/process-doc/SKILL.md` | `skills/bo-process-doc/SKILL.md` |
| `operations/skills/runbook/SKILL.md` | `skills/bo-runbook/SKILL.md` |
| `operations/skills/process-optimization/SKILL.md` | `skills/bo-process-optimization/SKILL.md` |
| `operations/skills/risk-assessment/SKILL.md` | `skills/bo-risk-assessment/SKILL.md` |
| `operations/skills/vendor-review/SKILL.md` | `skills/bo-vendor-review/SKILL.md` |
| `operations/skills/status-report/SKILL.md` | `skills/bo-status-report/SKILL.md` |

**改编内容：** 根据 Octop 专家的结构独立重写和调整了相关指引，替换 Claude/Cowork 专用命令、连接器占位内容和产物假设；加入跨行业表述、证据跟踪、可选工具不可用时的替代做法、写入与权限保护，并为技能名称添加前缀以避免冲突。另行编写了 Octop 专家的双语清单、身份说明和工作约定。

Anthropic 上游项目采用 Apache License 2.0（Apache-2.0）许可；相关版权及署名归原作者所有。许可文本见 `LICENSE-APACHE-2.0`。上游内容经过修改；这些改编内容**并非** Anthropic 或 Claude 官方提供的 Octop 集成。上游商标不表示对本项目的认可或背书。

已核验上述固定提交的完整 Git tree：`operations` 无独立 LICENSE，适用仓库根 LICENSE；根目录及 `operations` 下均无另立 NOTICE。随包 `LICENSE-APACHE-2.0` 保留该提交根 LICENSE 的完整原文字节，SHA-256 为 `a6946284993aeec75c7d75906064b66210c46051e562077efb30eb6dcfe72e26`。六份改编技能各自载有修改声明并链接至本说明。
