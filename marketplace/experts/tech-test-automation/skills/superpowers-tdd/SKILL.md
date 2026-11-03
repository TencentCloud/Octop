---
name: superpowers-tdd
description: Use when implementing any feature or bugfix, before writing implementation code - enforces RED-GREEN-REFACTOR cycle: write failing test first, verify it fails, write minimal code, verify it passes, then refactor
---

# Superpowers TDD - 测试驱动开发

## 核心准则

**先写测试，看着它失败，写最少的代码让它通过。**

如果没看过测试失败，就不知道测试的是不是对的东西。

**违反规则的字面意思 = 违反规则的精神。**

## 铁律

```
没有失败的测试，就不能写生产代码

先写代码后写测试？删除它。从头开始。
```

**没有例外：**
- 不要留着当"参考"
- 不要在写测试时"改编"它
- 不要看它
- 删除就是删除

## 红-绿-重构循环

### RED - 写失败的测试

写一个最小测试，展示应该发生什么。

```python
# Good: 清晰名称，测试真实行为，一件事
def test_retries_failed_operations_3_times():
    attempts = 0
    def operation():
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise Exception('fail')
        return 'success'
    
    result = retry_operation(operation)
    assert result == 'success'
    assert attempts == 3
```

```
❌ Bad: 模糊名称，测试 mock 而不是真实代码
def test_retry_works():
    mock = MagicMock()
    mock.side_effect = [Exception(), Exception(), 'success']
```

**要求：**
- 一个行为
- 清晰名称
- 真实代码（除非不可避免才用 mock）

### 验证 RED - 看着它失败

**必须执行，从不跳过。**

```bash
pytest tests/path/test_name.py -v
# 或项目对应的测试命令
```

确认：
- 测试失败（不是错误）
- 失败信息符合预期
- 失败是因为功能缺失（不是拼写错误）

**测试通过了？** 你在测试已有行为。修复测试。

### GREEN - 最少代码

写最简单的代码让测试通过。

```python
# Good: 刚好够通过测试
def retry_operation(fn, max_retries=3):
    for i in range(max_retries):
        try:
            return fn()
        except Exception as e:
            if i == max_retries - 1:
                raise e
```

```
❌ Bad: 过度设计，加入了测试没要求的功能
def retry_operation(fn, options={max_retries=3, backoff='linear', onRetry=...})
    # YAGNI - 你不需要这个
```

不要添加功能、不要重构其他代码、不要"改进"超过测试要求。

### 验证 GREEN - 看着它通过

**必须执行。**

```bash
pytest tests/path/test_name.py -v
```

确认：
- 测试通过
- 其他测试仍然通过
- 输出干净（无错误、无警告）

**测试失败？** 修代码，不是测试。

**其他测试失败？** 立刻修。

### REFACTOR - 重构

只有在 green 之后：
- 移除重复
- 改进名称
- 提取辅助函数

保持测试 green。不添加行为。

### 重复

下一个失败测试对应下一个功能。

## 好测试的特征

| 质量 | 好 | 坏 |
|------|----|----|
| **最小** | 一件事。名称里有"and"？拆开它。 | `test_validates_email_and_domain_and_whitespace` |
| **清晰** | 名称描述行为 | `test_test1` |
| **展示意图** | 展示期望的 API | 掩盖代码应该做什么 |

## 常见借口（别信）

| 借口 | 现实 |
|------|------|
| "太简单了不用测" | 简单代码也会坏。测试只用30秒。 |
| "我之后测" | 测试立即通过什么也证明不了。 |
| "之后测试也能达到同样目标" | 之后测试 = "这代码干了什么？" 先写测试 = "这代码应该干什么？" |
| "我已经手动测试了" | 手动测试是随意的。没有记录，不能重跑。 |
| "删除 X 小时的工作太浪费" | 沉没成本谬误。留着不可信的代码是技术债。 |
| "留着当参考" | 你会改编它。那就是之后测试。删除就是删除。 |
| "TDD 太教条" | TDD 是务实的：比事后调试快。 |

## 红旗 - 停止并从头开始

- 先写代码后写测试
- 实现之后才写测试
- 测试立即通过
- 说不清为什么测试失败
- "之后"添加的测试
- 合理化"就这一次"
- "我已经手动测试了"
- "之后测试能达到同样目的"
- "这是精神不是仪式"
- "留着当参考"或"改编现有代码"

**所有这些意味着：删除代码。从头用 TDD。**

## Bug 修复示例

**Bug:** 空邮箱被接受

**RED**
```python
def test_rejects_empty_email():
    result = submit_form({'email': ''})
    assert result['error'] == 'Email required'
```

**Verify RED**
```
$ pytest
FAIL: expected 'Email required', got undefined
```

**GREEN**
```python
def submit_form(data):
    if not data.get('email', '').strip():
        return {'error': 'Email required'}
    # ...
```

**Verify GREEN**
```
$ pytest
PASS
```

**REFACTOR**
如需要可提取多字段验证。

## 完成前检查表

- [ ] 每个新函数/方法都有测试
- [ ] 实现前看过每个测试失败
- [ ] 每个测试失败原因符合预期（功能缺失，不是 typo）
- [ ] 写了最少的代码让每个测试通过
- [ ] 所有测试通过
- [ ] 输出干净（无错误、无警告）
- [ ] 测试使用真实代码（除非不可避免才用 mock）
- [ ] 覆盖了边界情况和错误

不能全部打勾？跳过了 TDD。从头开始。
