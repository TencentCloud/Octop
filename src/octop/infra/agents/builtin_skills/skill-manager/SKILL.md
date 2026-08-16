---
name: skill-manager
description: 必须用于通过对话管理当前专家实例的 Skill，包括查找、检查、安装、导入、更新、编辑、列出、恢复或删除。支持 skillhub.cn/skills/... 页面 URL、SkillHub CLI、本地及上传文件、SKILL.md、ZIP/TAR、Git/GitHub 和普通下载 URL；也用于把 PDF、Markdown、文档、代码、图片等任意资料整理成新 Skill。Must use for conversational Skill management from files, URLs, Git repositories, archives, or SkillHub.
---

# Skill Manager

只管理当前实例的 `{{OCTOP_WORKSPACE}}/skills/`。当前实例工作区固定为 `{{OCTOP_WORKSPACE}}`；上传文件通常位于其中的 `inbound/`。不要用 `pwd`、`$HOME`、`~/.harness-agent/workspace`、记忆文件或搜索结果重新猜测工作区。不要改其他实例、全局 Skill 目录或 `_builtin_skills/`。

## 操作入口

使用内置脚本完成检查、下载、安全解包、安装、列出和删除：

```bash
python "{{OCTOP_WORKSPACE}}/_builtin_skills/skill-manager/scripts/manage_skills.py" <command>
```

```bash
# 列出已安装技能
... list

# 检查来源，不写入 skills/
... inspect "<file-directory-url-or-skillhub:slug>"

# 安装；仓库或压缩包内的多个 Skill 可一次安装
... install "<source>" [--subpath "path/in/repo"] [--name "slug"]

# 仅在用户明确同意替换后覆盖
... install "<source>" --force

# SkillHub 搜索；结果可用 skillhub:<slug> 检查或安装
... skillhub-search "<query>" --limit 10

# 仅在用户明确同意删除后执行；实际移动到 skills/.trash/
... remove "<slug>" --yes

# 从回收站恢复
... restore "<trash-name>"
```

## 来源处理

1. **现成 Skill、目录或 ZIP/TAR**：先 `inspect`；检查通过且用户已要求安装时执行 `install`。
2. **Git/GitHub URL**：可直接处理仓库、GitHub `tree` 子目录和指向 `SKILL.md` 的 `blob` URL。复杂仓库使用 `git+<url>` 和 `--subpath`。
3. **SkillHub 页面 URL**：`https://skillhub.cn/skills/<namespace>/<slug>` 可直接传给 `inspect` 或 `install`；脚本会解析 namespace 和 slug。不要自行安装/升级 CLI，不要直接运行 `skillhub install`。
4. **普通 HTTP(S) URL**：脚本处理直接文件和压缩包。若 URL 是其他介绍网页，先用现有网页工具读取并找到公开仓库、下载地址或 `SKILL.md`，再交给脚本。不得绕过登录、付费墙或访问控制。
5. **SkillHub 搜索**：用户只描述能力时，先搜索并给出 1–3 个候选的 slug、名称、用途和来源，让用户选择；用户已点名具体 Skill 时，可直接检查并安装。
6. **任意非 Skill 文件**：普通资料不会因复制而自动成为 Skill。先读取和理解材料，再使用内置 `skill-creator` 工作流，将可复用知识、步骤和必要资源整理为合法 Skill，写入 `{{OCTOP_WORKSPACE}}/skills/<slug>/`，然后执行 `inspect` 校验。

## 变更规则

- 新安装请求本身即表示同意新增；目标已存在时停止并说明冲突，只有获得明确同意才使用 `--force`。
- 编辑现有 Skill 前先读取其 `SKILL.md` 和相关资源，只改该 Skill 目录；修改后重新 `inspect`。
- 删除前点名目标并取得明确确认。使用 `remove --yes`，不要直接 `rm -rf`。需要恢复时使用 `restore`。
- 安装后报告 slug 和最终路径。新安装、更新或删除的 Skill 通常从下一次新会话开始完整生效。

## 安全边界

- 脚本限制下载及解包体积、文件数，拒绝路径穿越和符号链接，并通过暂存目录安装。
- 不执行、导入或 source 下载包中的代码。安装表示部署 Skill 内容，不代表第三方代码已通过安全审计。
- 不在输出中回显 URL 凭据；私有来源只使用环境中已有的 Git 或 SkillHub 凭据。
- 若当前实例没有 Shell 执行能力，仍可用文件工具处理简单文本 Skill，但必须说明 URL 下载、安全解包和 SkillHub CLI 无法完成，不能假装成功。
