# 输出文件示例

练习生成脚本支持 `.md`、`.json`、`.docx` 三种输出。推荐优先使用 `.md`，最稳定、最容易打印。

## 1. 命令示例

```bash
python3 scripts/generate_paper.py \
  --subject 物理 \
  --topic 浮力 \
  --student 小明 \
  --grade 初二 \
  --output 小明-浮力练习.md
```

生成成功后会看到：

```text
练习已生成：小明-浮力练习.md
```

## 2. Markdown 输出长什么样

```markdown
# 小明的物理练习

- 年级：初二
- 知识点：浮力
- 学段：初中

> 先回顾讲解，再完成练习；遇到不会的题，先写出想到的步骤。

## 基础巩固 ⭐

1. 【概念识别】解释“浮力”中的核心概念，并标出关键词。
   - 提示：重点：F浮=G排、ρ液gV排、漂浮时F浮=G、浮沉条件。

2. 【基础计算】完成一道“浮力”基础计算题，要求写出公式、代入、结果和单位。

## 能力提高 ⭐⭐

1. 【应用题】设计一个生活或实验情境，运用“浮力”解决问题，并写出完整步骤。

## 拓展挑战 ⭐⭐⭐

1. 【实验/探究】围绕“浮力”设计一个验证或探究方案，写出变量、步骤和结论。

## 参考答案

开放题暂无唯一答案，请根据讲解要点和表达完整度评价。
```

## 3. JSON 输出适合什么

如果要接入其他系统或二次排版，可以输出 `.json`：

```bash
python3 scripts/generate_paper.py \
  --subject 英语 \
  --topic 现在完成时 \
  --student 小美 \
  --grade 初二 \
  --output present-perfect.json
```

JSON 会包含这些字段：

```json
{
  "subject": "英语",
  "topic": "现在完成时",
  "student": "小美",
  "grade": "初二",
  "stage": "初中",
  "questions": {
    "basic": [],
    "improve": [],
    "challenge": []
  },
  "usage_note": "九大学科均衡题库中的主题会优先生成三层梯度练习..."
}
```

## 4. Word 输出和降级

如果输出路径是 `.docx`：

```bash
python3 scripts/generate_paper.py \
  --subject 语文 \
  --topic 阅读理解 \
  --student 小雨 \
  --grade 五年级 \
  --output 小雨-阅读理解.docx
```

可能出现两种情况：

| 情况 | 结果 |
|------|------|
| 已安装 `python-docx` | 生成 `小雨-阅读理解.docx` |
| 未安装 `python-docx` | 自动生成 `小雨-阅读理解.md`，并提示安装依赖 |

降级提示示例：

```text
提示：Word 依赖不可用，已自动生成 Markdown 文件：小雨-阅读理解.md
```

## 5. 文件选择建议

| 目标 | 推荐格式 |
|------|----------|
| 直接打印给孩子做 | `.md` |
| 给家长预览、复制到文档 | `.md` |
| 接入系统或二次开发 | `.json` |
| 需要正式排版文档 | `.docx` |
