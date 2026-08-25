# 多专家协作协议（AGENTS 指南）

本文件定义主 agent 在「多专家协作编排」模式下的派发协议。它把 agency-orchestrator 的 DAG 理念落到 OCTOP 已有的子智能体委派机制上。

## 1. 角色目录与 slug

OCTOP 子智能体人格文件位于：

```
subagents/library/zh/<division>/<slug>.md
```

- `<division>`：academic / design / engineering / finance / game-development / gis / hr / legal / marketing / paid-media / product / project-management / sales / security / spatial-computing / specialized / supply-chain / support / testing
- `<slug>`：文件名（去 .md），如 `engineering-software-architect`、`marketing-content-creator`

委派时引用 `division/slug`（例如 `engineering/engineering-code-reviewer`）。

## 2. DAG 结构（字段约定）

每个协作计划用如下结构描述：

```
goal: <一句话目标>
steps:
  - id: <step_id>
    role: <division>/<slug>        # 该步由哪个子智能体执行
    task: "<任务描述，可用 {{var}} 引用上游输出>"
    depends_on: [<step_id>, ...]   # 空或省略 = 可立即并行
    output: <output_var>           # 本步命名产出，供下游引用
    llm: <可选，覆写该步所用模型>
```

## 3. 接力与并行规则

- **接力**：下游 `task` 中用 `{{上一步output}}` 消费上游结果，避免重复生成或上下文丢失。
- **并行**：`depends_on` 为空的步骤同时派发；有依赖的等依赖完成再派发。
- **收敛**：最后用一步（或主 agent 自身）汇总所有 output 成最终交付。

## 4. 团队复用（team）

对持续项目，把锁定的一组 `role` 记为一个"团队阵容"，例如：

```
team: "产品从0到1"
  - product/product-manager
  - engineering/engineering-software-architect
  - engineering/engineering-frontend-developer
  - engineering/engineering-code-reviewer
  - ops-engineer
```

后续任务直接复用该阵容，省去每次重新选角。

## 5. 执行纪律

- 派发前先把 DAG 计划呈现给用户确认（尤其涉及不可逆操作或外部调用的步骤）。
- 某步失败：回退重排或换角，不要无脑重试同一提示。
- 不可逆/外部副作用步骤（发邮件、改生产、付费）必须 `securityGate` 二次确认。
- 每个子智能体的调用计入会话审计（对接 ai-safety-guardian 的 L8 Session Guard）。

## 6. 与单 agent 模式的边界

- 目标可拆、且各步需要不同专业视角 → 用本协作协议（多专家）。
- 目标单一、专业性集中 → 直接让对口专家/子智能体做，不必强行编排。
