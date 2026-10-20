---
name: install-skill
description: |
  从 Git 仓库或本地目录安装 Skill 到当前工作区。
  当用户想要以下内容时使用：
    - 向代理添加新 Skill（"安装 X skill"、"添加
      foo skill"、"我想要一个能做 Y 的 skill"）
    - 拉取已安装 Skill 的最新版本（"更新
      X skill"、"刷新我的 skills"）
    - 列出工作区中当前活动的 Skill
    - 移除他们不再需要的 Skill
  在短语如"装一个 X skill"、"安装技能"、"install
  skill"、"update skill"、"list skills"、"remove skill"、"找个能 X
  的 skill"时触发。不要要求用户说出字面 Skill 名称——
  如果他们描述了能力，提出候选 Skill（Git URL
  或本地路径）并在安装前确认。
metadata:
  octop:
    label:
      zh: "安装技能"
      en: "Install Skill"
    summary:
      zh: "从 Git 或本地目录安装、更新、列出或移除技能。"
      en: "Install, update, list, or remove skills from Git or disk."
  harness:
    emoji: "⬇️"
---

# 安装 Skill

一个帮助代理安装、列出、更新和移除工作区中其他 Skill 的 Skill。

Skill 位于 ``{workspace}/skills/<skill-name>/``，并在下一次代理会话中由 deepagents skills 中间件自动发现。随 ``octop-harness`` 内置的 Skill 位于 ``{workspace}/_builtin_skills/``，并且**不得**直接编辑——它们会在每次 ``HarnessAgent.init()`` 调用时被擦除并重新同步。

## 我们支持的来源

| 来源                  | 你需要给代理的内容                              | 示例                                            |
|-------------------------|------------------------------------------------------|----------------------------------------------------|
| Git 仓库（单个 Skill） | 根目录包含 ``SKILL.md`` 的 Git URL           | ``https://github.com/owner/my-skill.git``          |
| Git 仓库（子目录）       | Git URL + 仓库内的相对路径          | ``https://github.com/owner/skills-collection.git`` + ``./searxng`` |
| 本地目录         | 绝对或工作区相对路径               | ``/Users/me/my-drafts/cool-skill``                 |

我们特意不捆绑远程注册表。在 GitHub（或任何 HTTPS 可访问的 Git 服务器）上托管 Skill 就足够了。

## 工作流

### 1. 识别工作区 skills 目录

用户可安装的 Skill 位于 ``{workspace}/skills/``。使用 ``current_time`` 或 ``execute_shell_command pwd`` 来确定路径是否模糊，然后：

```bash
SKILLS_DIR="<workspace>/skills"
mkdir -p "$SKILLS_DIR"
```

如果用户还没有运行 ``HarnessAgent.init()``，建议先运行——它会创建 ``{workspace}/skills/`` 并植入内置 Skill。

### 2. 从 Git 仓库安装（单个 Skill 在根目录）

```bash
cd "$SKILLS_DIR"
git clone --depth 1 <repo-url> <skill-name>
```

然后验证 Skill 格式良好：

```bash
test -f "$SKILLS_DIR/<skill-name>/SKILL.md" || {
  echo "❌ repo 根目录没有 SKILL.md —— 尝试安装子目录"
  rm -rf "$SKILLS_DIR/<skill-name>"
  exit 1
}
```

验证 frontmatter 解析：

```bash
python3 - <<'PY'
import sys, re, pathlib
p = pathlib.Path("$SKILLS_DIR/<skill-name>/SKILL.md")
text = p.read_text(encoding="utf-8")
m = re.match(r"^---\n(.*?)\n---", text, re.DOTALL)
if not m:
    sys.exit("❌ SKILL.md 缺少 YAML frontmatter")
import yaml
fm = yaml.safe_load(m.group(1)) or {}
for k in ("name", "description"):
    if not fm.get(k):
        sys.exit(f"❌ frontmatter 缺少必需字段: {k}")
print(f"✅ {fm['name']}: {fm['description'][:80]}…")
PY
```

（如果 ``yaml`` 没有安装，先 ``pip install pyyaml`` —— 它很可能也是用户想要的通用依赖。）

### 3. 从仓库的子目录安装

当上游仓库包含许多 Skill 时：

```bash
TMPDIR=$(mktemp -d)
git clone --depth 1 <repo-url> "$TMPDIR"
cp -r "$TMPDIR/<subpath>" "$SKILLS_DIR/<skill-name>"
rm -rf "$TMPDIR"
```

运行与步骤 2 相同的 SKILL.md 验证。

### 4. 从本地目录安装

对于用户在本地编写的 Skill：

```bash
cp -r "<source-dir>" "$SKILLS_DIR/<skill-name>"
```

或者，如果他们想要迭代时进行实时链接：

```bash
ln -s "<absolute-source-dir>" "$SKILLS_DIR/<skill-name>"
```

当用户的 _编写_ Skill 并希望编辑被拾取而无需重新安装时，符号链接是正确的选择。

### 5. 列出已安装的 Skill

```bash
for d in "$SKILLS_DIR"/*/; do
  name=$(basename "$d")
  desc=$(awk '/^description:/{sub(/^description: */, ""); print; exit}' "$d/SKILL.md" 2>/dev/null)
  printf "  • %-30s %s\n" "$name" "$desc"
done
```

将此输出逐字显示给用户——每个 Skill 的描述正是他们识别已安装内容所需的。

### 6. 更新 Skill

如果最初是通过 ``git clone`` 安装的：

```bash
cd "$SKILLS_DIR/<skill-name>" && git pull --ff-only
```

否则重新安装：移除目录并再次运行步骤 2/3/4。

### 7. 移除 Skill

先与用户确认（这也会删除用户就地编辑的文件）：

```bash
rm -rf "$SKILLS_DIR/<skill-name>"
```

## 操作原则

- **在变更前确认。** 克隆到工作区可以不经询问完成，但 ``rm -rf`` 和强制覆盖需要用户明确确认。
- **拒绝格式错误的 Skill。** 没有有效 frontmatter 的 Skill 比没有 Skill 更糟——它会拖慢加载器并混淆模型。每次都运行步骤 2 中的 YAML 检查。
- **不要触碰 ``_builtin_skills/``。** 该目录由包拥有；编辑将在下一次 ``HarnessAgent.init()`` 时丢失。内置 Skill 可以通过在 ``skills/`` 中安装同名 Skill 来_遮蔽_——Harness Agent 优先使用用户安装的 Skill 而不是内置的。
- **告诉用户何时重新加载。** 新安装的 Skill 在下次代理会话时被拾取，而不是在对话中途。提及此点以便他们不期望立即生效。

## 常见问题

> "我想要一个用于 X 的 Skill，你能找一个吗？"

通过 web fetcher 或你拥有的任何其他工具搜索 GitHub，提出 1-2 个候选仓库，总结它们的 `SKILL.md` 描述，并让用户在选择前挑选。

> "Skill 来自哪里？"

任何 ``git clone`` 可达的地方——公共 GitHub、内部 GitLab/Gitea、``file://`` 等。设计上没有中央注册表。

> "我可以编辑内置 Skill 吗？"

不要直接编辑 ``_builtin_skills/`` 中的文件——它会在 init 时被覆盖。而是，将它复制到 ``skills/`` 并使用相同的名称；用户安装的副本会遮蔽内置的。
