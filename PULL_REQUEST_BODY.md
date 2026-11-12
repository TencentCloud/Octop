## What

新增 `request_structured_form` 工具协议——Agent 声明一份带类型约束的表单，网关层在请求和响应两端校验，非法数据不进入 Agent 推理循环。

## Why

现有 `ask_user_question` 是自由文本。Agent 问「端口号多少？」，用户回「八千」，协议层不拦截。

具体问题：
- 用户可能填「八百」而 Agent 需要 1-65535 的整数，prompt 兜底不可靠
- 必填项遗漏、值超范围，没有任何网关拦截——每个 Agent 开发者自己写 prompt 防御
- 自由文本不留 `submission_id`，回溯「当时填了什么参数」很难

本 PR 把「Agent 向人收参数」从自由文本升级为类型安全的协议通道。

## How

### 改了什么

6 个文件，纯增量，零破坏性变更：

| 仓库 | 文件 | 操作 | 行数 | 职责 |
|---|---|---|---|---|
| octop | `src/octop/infra/gateway/hitl/structured_form.py` | 新增 | 145 | 请求/响应双向 schema 校验 |
| octop | `src/octop/infra/gateway/hitl/coordinator.py` | 修改 | +16/-3 | 导入校验函数 + 收紧豁免逻辑 + 新增校验分支 |
| harness | `src/octop_harness/builtin/tools/structured_form.py` | 新增 | 110 | pydantic schema 定义 + headless fallback |
| harness | `src/octop_harness/builtin/tools/__init__.py` | 修改 | +6 | 导入导出 `STRUCTURED_FORM_TOOL_NAME` + `request_structured_form` |
| harness | `src/octop_harness/agent.py` | 修改 | +16 | 工具注册 + `_structured_form_active()` + HITL 中断 |
| harness | `src/octop_harness/config/__init__.py` | 修改 | +7 | `structured_form_enabled: bool = True` |

### 核心逻辑

**1. Agent 调用 `request_structured_form`**

```python
request_structured_form.invoke({
    "form_protocol": "octop.structured_form.v1",
    "form_id": "deploy-settings",
    "title": "部署参数",
    "fields": [
        {"key": "replicas", "label": "副本数", "type": "integer", "min": 1, "max": 20, "required": True, "nullable": False},
        {"key": "max_memory_mb", "label": "内存上限(MB)", "type": "integer", "min": 128, "max": 32768, "required": False, "nullable": True},
    ],
})
```

**2. 网关拦截**

`coordinator.py` 的 `decision_rejection_reason()` 中新增分支：

```python
if action.get("name") == STRUCTURED_FORM_TOOL_NAME:
    request_error = validate_structured_form_request(action.get("args"))
    if request_error:
        return request_error          # 请求阶段就拦截非法参数
    if kind == "respond":
        response_error = validate_structured_form_response(
            action.get("args"), decision.get("message")
        )
        if response_error:
            return response_error      # respond 时再校验用户提交的内容
```

**3. 同时修复了一个已有漏洞**

原逻辑 `if not allowed: continue`——工具未配置 `allowed_decisions` 时直接跳过所有校验。改为 `if allowed and kind not in allowed`，确保「未配置」不等于「无条件放行」。

### 校验规则（网关层完整覆盖）

`validate_structured_form_request` 逐项检查后返回具体原因：

| # | 检查项 | 错误返回示例 |
|---|---|---|
| 1 | args 必须是 dict | `structured form args must be an object` |
| 2 | JSON 大小 ≤ 32KB | `structured form request is too large` |
| 3 | 无非法字段 | `structured form request contains unsupported fields` |
| 4 | 协议版本匹配 | `unsupported structured form protocol` |
| 5 | form_id 格式合法 | `structured form form_id is invalid` |
| 6 | title 非空 | `structured form title is required` |
| 7 | 字段数 1-64 | `structured form must contain between 1 and 64 fields` |
| 8 | 类型仅 integer | `structured form supports integer fields only` |
| 9 | key 唯一 | `structured form field keys must be unique` |
| 10 | required 与 nullable 不互斥 | `required structured form fields cannot be nullable` |

`validate_structured_form_response` 额外检查：

| # | 检查项 | 错误返回示例 |
|---|---|---|
| 11 | 响应是合法 JSON | `structured form response must be valid JSON` |
| 12 | form_id 匹配 | `structured form response form_id does not match` |
| 13 | required 字段有值 | `structured form value is required` |
| 14 | 值在 min-max 范围 | `structured form value is outside the allowed range` |
| 15 | 值非 null（required 字段） | `structured form value is required` |

## MVP 限制

- 字段类型仅 `integer`（min/max/step/required/nullable 已支持）
- 表单渲染由宿主 IM 客户端处理，本 PR 只做协议层
- headless 模式下 `request_structured_form` 立即返回提示文本，不阻塞

## Test

`test_structured_form.py` 25/25 全部通过，不依赖服务启动：

```
═══ 1. Schema imports ═══
  ✅ harness structured_form imports
  ✅ gateway structured_form imports
═══ 2. StructuredIntegerField ═══
  ✅ valid field: key=count, type=integer
  ✅ required + nullable=True correctly rejected
  ✅ max < min correctly rejected
  ✅ invalid key pattern correctly rejected
  ✅ key length > 64 correctly rejected
  ✅ optional field created: required=False, nullable=True
═══ 3. StructuredFormRequestArgs ═══
  ✅ valid request created: form_id=pr-test-1, 2 fields
  ✅ duplicate field keys correctly rejected
  ✅ more than 64 fields correctly rejected
  ✅ empty fields correctly rejected
═══ 4. validate_structured_form_request ═══
  ✅ valid request passes gateway validation
  ✅ empty title rejected
  ✅ non-integer type rejected
  ✅ required+nullable rejected
  ✅ duplicate keys rejected
═══ 5. validate_structured_form_response ═══
  ✅ valid response passes gateway validation
  ✅ missing required value rejected
  ✅ out-of-range value rejected
  ✅ null on required field rejected
  ✅ form_id mismatch rejected
  ✅ non-JSON response rejected
═══ 6. Headless fallback ═══
  ✅ headless fallback returned correctly
═══ 7. Protocol constants ═══
  ✅ all protocol constants verified
══════════════════════════════════════════════════
  TOTAL: 25  |  ✅ 25 passed  |  ❌ 0 failed
```

复跑：`PYTHONPATH=src:/path/to/octop-harness-pr/src python3 test_structured_form.py`

## Checklist

- [x] 🎯 最小修改原则 — 6 文件纯增量，无破坏性变更
- [x] 🧱 测试用例已添加并通过 — 25/25
- [x] 🎯 代码结构清晰 — 每个校验函数返回具体错误原因
- [ ] ✅ CI — 待上游触发
- [x] 📝 异常妥善处理 — 所有校验路径均返回具体消息

## Related

- harner PR: labspc/octop-harness → feature/structured-hitl-forms
- Base: octop v1.0.3b5 / harner v1.0.9