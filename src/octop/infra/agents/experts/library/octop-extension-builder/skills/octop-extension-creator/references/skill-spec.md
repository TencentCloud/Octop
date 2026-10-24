# Octop Skill 规范

Skill 根目录必须包含 `SKILL.md`。

`SKILL.md` 必须以 YAML frontmatter 开始：

```markdown
---
name: example-skill
description: Explain the capability and the requests that should activate it.
---
```

名称使用小写字母、数字和连字符。
description 要说明能力和触发条件。

在 `SKILL.md` 中保存核心判断和工作流。
把较长的模式、协议和示例放入 `references/`。
把重复且需要确定性执行的逻辑放入 `scripts/`。
把输出模板放入 `assets/`。

不要复制通用知识。
不要加入无用目录。
不要声明超出用户需求的权限。
不要把安装动作当作已获得的授权。
所有文本文件必须以换行符结尾。
