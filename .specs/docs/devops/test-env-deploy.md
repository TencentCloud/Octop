# 测试环境部署与代码同步

> 本文档说明测试环境相关操作的 Skill 调用方式。
> 所有环境操作通过 **`cvm-dev-workflow` Skill** 统一处理，无需手动执行 CLI 命令。
>
> 本文档由 `specs-sop` skill 维护；初始化或升级 skill 时**会强制刷新**（旧文件自动备份为 `test-env-deploy.md.bk.<timestamp>`）。
> 项目特有的「组件清单」「环境命名」等定制内容请填到下文 `## 项目自定义` 章节，避免被刷新覆盖。

---

## Skill 纵览

| Skill | 用途 | 触发方式 |
|-------|------|---------|
| `cvm-dev-workflow` | 环境创建 / 查询、代码热更、远端命令执行 | 对 AI 说"创建环境"、"同步代码"、"查看日志"等 |
| `cvm-test-tools` | 创建/查询/销毁实例、数据库查询、API 调用 | 对 AI 说"创建实例"、"数据库查询"、"执行接口测试"等 |

---

## 环境操作（cvm-dev-workflow）

> 以下操作统一通过 `cvm-dev-workflow` Skill 完成，AI 会自动调用对应的环境管理能力。

| 操作 | 对 AI 说 | 说明 |
|------|---------|------|
| 创建测试环境 | `创建环境` / `创建环境 <env-name>` | 触发创建流水线，约 10–20 分钟 |
| 查询环境状态 | `查询环境 <env-name>` | 查看环境是否 READY |
| 查询流水线进度 | `查询流水线` | 查看创建/更新流水线状态 |
| 热更代码到环境 | `热更代码到 <env-name>` | 不走流水线，秒级生效 |
| 更新指定组件 | `更新组件 <env-name> <comp>` | 触发组件级重部署 |
| 远端容器执行命令 | `在 <env-name> 的 <comp> 上执行 <command>` | 查日志、排查问题等 |
| **释放测试环境** | `释放环境 <env-name>` / `cvm-envx release -e <env-name>` | **SOP Commit 阶段的强制前置动作**；本任务收尾必须执行，由 `cvm-dev-workflow` 代为执行 `cvm-envx release -e <env-name>`（同时完成环境池标记释放 + 平台 Session 释放）。详见 `plans/_template/09-commit.md` 第 0 节 |

**环境状态说明**

| 状态 | 含义 |
|------|------|
| `READY` | 就绪，可以同步代码 |
| `RUNNING` / `CREATING` | 创建/部署中，等待后重新查询 |
| `ERROR` / `FAILED` | 失败，查看流水线日志排查 |

---

## 集成测试操作（cvm-test-tools）

> 以下操作通过 `cvm-test-tools` Skill 完成。

| 操作 | 对 AI 说 | 说明 |
|------|---------|------|
| 创建测试实例 | `创建实例` | 创建用于 IT 的 CVM 实例 |
| 查询实例 | `查询实例 <instance-id>` | 查看实例状态 |
| 销毁实例 | `销毁实例 <instance-id>` | 清理测试实例 |
| 数据库查询 | `数据库查询 <env-name> <sql>` | 查询测试环境数据库 |
| 调用 CVMAPI | `cvmapi <Action>` | 直接调用 CVM 接口 |
| 调用 VSAPI | `vsapi <Action>` | 直接调用 VS 接口 |

---

## 工具就绪检查

在使用上述 Skill 前，先确认 `cvm-envx` CLI 已安装（`cvm-dev-workflow` 依赖）。

### 检查 cvm-envx 是否就绪

```bash
cvm-envx --version
```

| 输出 | 状态 | 处理方式 |
|------|------|----------|
| 打印版本号（如 `x.y.z`） | ✅ 就绪 | 可直接使用 |
| `command not found` | ❌ 未安装 | 见下方安装引导 |

### 安装 cvm-envx（通过 vortex）

```bash
cd /tmp
git clone git@git.woa.com:cvm/vortex.git /tmp/vortex
bash /tmp/vortex/install_public.sh /tmp/vortex_space
```

安装脚本会自动完成：卸载旧版 `@tencent/zhiyan-cle-cli` → 安装 `@tencent/cvm-env-cli` → 执行 `cvm-envx init`。

安装完成后再次执行 `cvm-envx --version` 确认就绪。

### 工具检查清单

| 工具 | 检查命令 | 缺失处理 |
|------|---------|---------|
| `cvm-envx` | `cvm-envx --version` | 见上方安装引导 |
| `git` | `git --version` | 系统包管理器安装 |

---

## 项目自定义

> 本章节内容**不会**被 skill 刷新覆盖，请按项目实际情况填充。

### 组件清单

| 组件名 | 仓库 / 路径 | 主分支 | 备注 |
|--------|------------|--------|------|
|  |  |  |  |

### 常用环境

| 环境名 | 用途 | 负责人 | 备注 |
|--------|------|--------|------|
|  |  |  |  |

### 项目特有同步规则 / 排雷点

<!-- 例如：某组件需先停服再同步、某目录需 chown、某配置需手动 reload 等 -->
