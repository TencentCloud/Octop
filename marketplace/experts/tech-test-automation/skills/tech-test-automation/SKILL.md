---
name: tech-test-automation
description: >-
  自动化测试专家包。适用于自动化测试、从TDD方法论指导到自动生成单元测试代码、跨语言测试编写与运行、Playwright/ Cypress E2E测试编排、
  REST/GraphQL API测试自动化、再到QA测试计划与覆盖率矩阵生成的完整自动化测试工作流、Python(pytest)等场景；
  也适用于用户明确要求调用「自动化测试 / 自动化测试专家包 / Test Automation」。
version: 1.0.0
metadata:
  author: SkillHub
  package_type: meta-skill
  display_name: 自动化测试
  aliases:
    - 自动化测试
    - 自动化测试专家包
    - 自动化测试技能包
    - Test Automation
    - tech-test-automation
    - test-automation
orchestration:
  children:
    - superpowers-tdd
    - test-case-generator
    - test-patterns
    - e2e-testing-patterns
    - api-test-automation
    - afrexai-qa-test-plan
compatibility: SkillHub meta-skill, exportable to Claude Code / Codex markdown skill.
---
# 自动化测试工作流

你现在要完成一项软件自动化测试任务。你已安装以下 Skill，请按步骤串联使用：

## 步骤 1：TDD 方法论与测试策略（获取层）
使用 **Superpowers Tdd** 完成：
- 制定测试驱动开发策略：红-绿-重构工作流
- 识别需要测试的功能模块和边界条件
- 确定测试层次：单元测试 → 集成测试 → E2E 测试
- 生成测试固件（fixture）和模拟对象（mock）策略
- 分析现有覆盖率缺口，制定补测计划

输出测试策略文档和优先级排序。

## 步骤 2：自动生成测试用例（分析层）
使用 **Test Case Generator** 完成：
- 分析目标代码的函数签名、逻辑分支和依赖关系
- 自动生成完整的测试代码（含 import、mock、断言）
- 支持 Jest、Mocha、Pytest 等主流测试框架
- 覆盖正常路径、边界条件、异常输入等场景

输出可直接运行的测试文件。

## 步骤 3：跨语言测试编写与运行（分析层）
使用 **Test Patterns** 完成：
- 搭建测试套件并配置测试环境
- 编写单元测试、集成测试和 E2E 测试
- 支持 Node.js（Jest/Vitest）、Python（pytest）、Go 等多语言
- 模拟外部依赖（数据库、API、文件系统）
- 运行测试并测量覆盖率

输出测试执行结果和覆盖率数据。

## 步骤 4：E2E 测试编排与执行（分析层）
使用 **E2E Testing Patterns** 完成：
- 基于 Playwright/Cypress 设计 E2E 测试用例
- 通过源码优先定位页面元素，必要时使用截图识别兜底
- 编排测试执行顺序和数据依赖
- 自动修复因页面变更导致的脚本失效
- 执行跨浏览器兼容性测试

输出 E2E 测试脚本和执行报告。

## 步骤 5：API 接口测试自动化（分析层）
使用 **Api Test Automation** 完成：
- 对 REST/GraphQL 接口进行自动化测试
- 执行接口功能测试（CRUD、认证、权限）
- 运行性能测试和压力测试
- 执行契约测试，验证接口规范一致性
- 配置 Mock 服务进行隔离测试

输出 API 测试结果和性能基准数据。

## 步骤 6：QA 测试计划与报告生成（输出层）
使用 **QA Test Plan Generator** 完成：
- 生成详细的 QA 测试计划文档
- 构建覆盖率矩阵（功能 × 测试类型）
- 汇总测试用例清单和缺陷严重级分类
- 计算自动化 ROI 指标
- 生成发布检查清单和质量仪表板

## 最终输出
将以上步骤的结果整合为完整的自动化测试包，交付以下文件：
1. **测试策略文档**：TDD 方法论、测试层次规划、覆盖率目标
2. **测试代码**：单元测试 + 集成测试 + E2E 测试 + API 测试
3. **测试执行报告**：通过/失败统计、覆盖率数据、性能基准
4. **QA 测试计划**：覆盖率矩阵、发布检查清单、质量仪表板
