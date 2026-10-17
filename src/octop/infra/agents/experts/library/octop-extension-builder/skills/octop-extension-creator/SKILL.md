---
name: octop-extension-creator
description: Create or revise an Octop Skill, Plugin, or hybrid extension from a user requirement. Use for new Octop capabilities, reusable workflows, custom tools, external API integrations, and Plugin packaging. Do not use for installing an existing Skill or Plugin.
metadata:
  octop:
    emoji: "🧱"
    label:
      zh: "Octop 扩展创建"
      en: "Octop Extension Creator"
    summary:
      zh: "创建并校验 Octop Skill、Plugin 或组合扩展。"
      en: "Create and validate Octop Skills, Plugins, or hybrid extensions."
---

# Octop Extension Creator

先选择产物类型。

- 只需要知识、规则或工作流时，创建 `skill`。
- 需要新工具、API、UI 或 Python 运行时代码时，创建 `plugin`。
- 工具还需要专门的调用规则时，创建 `hybrid`。

创建 Skill 时，读取 [Skill 规范](references/skill-spec.md)。
创建 Plugin 或 hybrid 时，读取 [Plugin 规范](references/plugin-spec.md)。
涉及网络、凭据、依赖或外部写操作时，再读取 [安全规范](references/security.md)。

## 工作流

1. 调用 `octop_extension_scaffold`。
2. 只编辑返回的 `source_root`。
3. 替换所有 `[REPLACE_ME]` 内容。
4. 让工具函数参数直接匹配用户要求的工具参数。不要擅自包装 JSON。
5. 调用 `octop_extension_validate`。
6. 修复全部 errors。warnings 必须向用户说明。
7. 使用最新 revision 调用 `octop_extension_package`。
8. 报告 ZIP 路径、SHA-256、私人目录条目和“未安装”状态。

不要修改 `project.json`。
不要执行生成的 Plugin。
不要把打包说成安装。
打包成功后，Skill 会进入用户的“我的创建”目录。Plugin 会进入用户可见的插件市场。
不要在文件中写入真实密钥。
