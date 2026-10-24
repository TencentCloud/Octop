# Octop Plugin 规范

Plugin 根目录必须包含 `plugin.yaml` 和入口 Python 文件。

最小 manifest：

```yaml
id: example-plugin
version: 0.1.0
name: Example Plugin
description: Explain the capability.
kind: tool
entry: main.py
requires: []
```

`id` 必须和项目 slug 相同。
入口必须使用相对路径。
第一版优先使用空依赖列表。

入口必须定义 `setup(ctx)`。
入口必须注册至少一个工具：

```python
from octop_harness.plugins import PluginContext


async def lookup_item(query: str) -> str:
    return query


def setup(ctx: PluginContext) -> None:
    ctx.tool(
        "lookup_item",
        lookup_item,
        description="Look up one item by query.",
    )
```

工具名称使用 ASCII 字母、数字和下划线。
工具描述要说明用途、参数和限制。
Python 函数参数就是模型看到的工具参数。
参数名称和类型必须匹配用户需求。
不要把参数包装成 JSON 字符串，除非用户明确要求原始 JSON。
网络请求必须设置超时。
错误输出不得包含密钥。
所有文本文件必须以换行符结尾。

hybrid Plugin 把 Skill 放在：

```text
skills/<skill-slug>/SKILL.md
```

hybrid Plugin 还必须在 `plugin.yaml` 中声明：

```yaml
skills: skills
```

Octop 在加载 Plugin 后注册这个目录。
不要调用 `ctx.skills()`。Harness 不允许 `kind: tool` 调用它。
