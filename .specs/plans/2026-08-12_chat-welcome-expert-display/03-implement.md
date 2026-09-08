# 03. Implement

> **目的**：按 Plan 写代码，只记录改动点。
> **输入**：`02-plan.md`
> **输出**：代码改动 + 本文件

---

## 1. 改动文件清单

| # | 文件 | 改动摘要 |
|---|------|---------|
| 1 | `dashboard/src/pages/Chat/utils/resolveWelcomeSuffix.ts` | 新增纯函数：非空 description（trim）优先，否则 welcome_message |
| 2 | `dashboard/src/pages/Chat/utils/resolveWelcomeSuffix.test.ts` | Plan §6.1 七条 UT |
| 3 | `dashboard/src/pages/Chat/hooks/useExpertQuickCards.ts` | API welcome 与 `agent.description` 经 `resolveWelcomeSuffix` 组合后返回；Review 去掉多余 `useMemo` |

## 2. 与 Plan 的差异

| # | 偏离项 | 原因 |
|---|--------|------|
|  | 无 |  |

## 3. 自检

- [x] 无硬编码凭证 / Token / 密码
- [x] SQL 全部参数化（无 SQL）
- [x] 外部输入均有校验（trim 空白）
- [x] 错误路径有日志（welcome API catch 保持清空，既有行为）
- [ ] Lint / Format 通过（本环境 `npm install` 失败，未跑 dashboard lint；逻辑 smoke 已过）
- [x] Vitest 等价验证 7/7（`node --experimental-strip-types` 导入真实源码；正式 vitest 待本机 `npm install`）

---

## 完成标志

- [x] 所有改动文件已实现
- [x] 与 Plan 偏离项已记录
- [ ] 自检全部通过（vitest / lint 待本机 npm 可用后补）
- [x] `00-overview.md` Progress / 当前步骤 / 时间记录已同步
- [x] 已与用户完成结束确认

## 验证

- Node smoke（与 UT 用例同构）：`OK 7/7`
- 本地建议：`cd dashboard && npm install && npm test -- src/pages/Chat/utils/resolveWelcomeSuffix.test.ts`
