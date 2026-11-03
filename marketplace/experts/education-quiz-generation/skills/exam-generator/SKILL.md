---
name: exam-generator
description: 中国中小学试卷生成器。Use when teacher needs to create exam papers for Chinese primary/middle school. Supports all subjects, multiple question types, official curriculum standards, and accurate answers. Uses web search for latest knowledge. 试卷生成、出题、考试卷。
version: 1.0.2
license: MIT-0
metadata: {"openclaw": {"emoji": "📝", "requires": {"bins": ["python3", "curl"], "env": []}}}
---

# 中国中小学试卷生成器

专业试卷生成工具，支持中国中小学各学科，遵循官方课程标准，确保试题准确性。

## Features

- 📚 **全学科支持**: 语文、数学、英语、物理、化学、生物、历史、地理、政治
- 📊 **多种题型**: 选择题、填空题、判断题、简答题、计算题、作文题
- 🎯 **精准出题**: 根据知识点和难度要求生成
- 🌐 **联网验证**: 使用web search获取最新知识和标准答案
- 📐 **专业排版**: 标准试卷格式，可直接打印
- ✅ **答案准确**: 交叉验证确保答案正确

## 支持的学科

| 学科 | 年级 | 题型 |
|------|------|------|
| 语文 | 小学/初中 | 选择、填空、阅读、作文 |
| 数学 | 小学/初中 | 选择、填空、计算、应用 |
| 英语 | 小学/初中 | 选择、填空、阅读、写作 |
| 物理 | 初中 | 选择、填空、实验、计算 |
| 化学 | 初中 | 选择、填空、实验、计算 |
| 生物 | 初中 | 选择、填空、简答 |
| 历史 | 初中 | 选择、填空、简答 |
| 地理 | 初中 | 选择、填空、读图 |
| 政治 | 初中 | 选择、填空、简答 |

## Trigger Conditions

- "生成一份试卷" / "Create an exam"
- "出一套数学题" / "Generate math problems"
- "帮我出英语试卷" / "Create English test"
- "根据知识点出题" / "Generate questions for topics"
- "exam-generator"

---

## Step 1: 理解用户需求

```
请提供以下信息：

学科：语文/数学/英语/物理/化学...
年级：小学X年级/初中X年级
知识点：具体要考察的知识点
题型：选择题/填空题/简答题...
题量：各题型数量
难度：简单/中等/困难
时间：考试时长（分钟）
```

---

## Step 2: 获取最新知识（联网验证）

使用web-search skill获取准确的知识点和标准答案：

```
Agent自动调用web-search skill搜索：
- 学科知识点
- 标准答案
- 官方课程标准
```

### 知识验证流程

```
生成试题
    ↓
搜索标准答案
    ↓
交叉验证
    ↓
标记置信度
    ↓
输出试题
```

---

## Step 3: 生成试卷

### Python代码示例

```python
import os
from datetime import datetime

class ExamGenerator:
    def __init__(self, subject, grade, title='考试试卷'):
        self.subject = subject
        self.grade = grade
        self.title = title
        self.questions = []
        self.answers = []
    
    def add_choice_question(self, question, options, answer, score=2):
        """添加选择题"""
        self.questions.append({
            'type': 'choice',
            'question': question,
            'options': options,
            'score': score
        })
        self.answers.append({
            'type': 'choice',
            'answer': answer,
            'score': score
        })
    
    def add_fill_blank(self, question, answer, score=2):
        """添加填空题"""
        self.questions.append({
            'type': 'fill',
            'question': question,
            'score': score
        })
        self.answers.append({
            'type': 'fill',
            'answer': answer,
            'score': score
        })
    
    def add_true_false(self, question, answer, score=1):
        """添加判断题"""
        self.questions.append({
            'type': 'true_false',
            'question': question,
            'score': score
        })
        self.answers.append({
            'type': 'true_false',
            'answer': answer,
            'score': score
        })
    
    def add_short_answer(self, question, answer, score=10):
        """添加简答题"""
        self.questions.append({
            'type': 'short_answer',
            'question': question,
            'score': score
        })
        self.answers.append({
            'type': 'short_answer',
            'answer': answer,
            'score': score
        })
    
    def add_calculation(self, question, answer, score=15):
        """添加计算题"""
        self.questions.append({
            'type': 'calculation',
            'question': question,
            'score': score
        })
        self.answers.append({
            'type': 'calculation',
            'answer': answer,
            'score': score
        })
    
    def add_essay(self, question, requirements, score=30):
        """添加作文题"""
        self.questions.append({
            'type': 'essay',
            'question': question,
            'requirements': requirements,
            'score': score
        })
        self.answers.append({
            'type': 'essay',
            'answer': '见评分标准',
            'score': score
        })
    
    def generate_exam(self, lang='zh'):
        """生成试卷"""
        total_score = sum(q['score'] for q in self.questions)
        
        if lang == 'zh':
            return self._generate_chinese(total_score)
        else:
            return self._generate_english(total_score)
    
    def _generate_chinese(self, total_score):
        """生成中文试卷"""
        output = []
        output.append(f'┌{"─"*60}┐')
        output.append(f'│  {self.title}')
        output.append(f'│  {self.subject} · {self.grade}')
        output.append(f'│  考试时间：90分钟 · 满分：{total_score}分')
        output.append(f'└{"─"*60}┘')
        output.append('')
        output.append('姓名：__________ 班级：__________ 学号：__________')
        output.append('')
        
        choice_num = 1
        fill_num = 1
        tf_num = 1
        other_num = 1
        
        for q in self.questions:
            if q['type'] == 'choice':
                output.append(f'一、选择题（每题{q["score"]}分）')
                output.append('')
                output.append(f'{choice_num}. {q["question"]}')
                for i, opt in enumerate(q['options']):
                    output.append(f'   {chr(65+i)}. {opt}')
                output.append('')
                choice_num += 1
            
            elif q['type'] == 'fill':
                output.append(f'二、填空题（每空{q["score"]}分）')
                output.append('')
                output.append(f'{fill_num}. {q["question"]}')
                output.append('   答案：__________')
                output.append('')
                fill_num += 1
            
            elif q['type'] == 'true_false':
                output.append(f'三、判断题（每题{q["score"]}分）')
                output.append('')
                output.append(f'{tf_num}. {q["question"]} （  ）')
                output.append('')
                tf_num += 1
            
            elif q['type'] == 'short_answer':
                output.append(f'四、简答题（每题{q["score"]}分）')
                output.append('')
                output.append(f'{other_num}. {q["question"]}')
                output.append('')
                output.append('')
                output.append('')
                other_num += 1
            
            elif q['type'] == 'calculation':
                output.append(f'五、计算题（每题{q["score"]}分）')
                output.append('')
                output.append(f'{other_num}. {q["question"]}')
                output.append('')
                output.append('')
                output.append('')
                other_num += 1
            
            elif q['type'] == 'essay':
                output.append(f'六、作文（{q["score"]}分）')
                output.append('')
                output.append(f'{q["question"]}')
                output.append(f'要求：{q.get("requirements", "")}')
                output.append('')
                output.append('')
                output.append('')
        
        return '\n'.join(output)
    
    def generate_answer_sheet(self, lang='zh'):
        """生成答案"""
        output = []
        output.append(f'{"="*60}')
        output.append(f'{self.title} - 参考答案')
        output.append(f'{"="*60}')
        output.append('')
        
        for i, a in enumerate(self.answers, 1):
            output.append(f'{i}. {a["answer"]} （{a["score"]}分）')
        
        return '\n'.join(output)
    
    def save(self, output_dir):
        """保存试卷和答案（Word格式）"""
        from docx import Document
        from docx.shared import Pt, Cm
        from docx.enum.text import WD_ALIGN_PARAGRAPH
        
        os.makedirs(output_dir, exist_ok=True)
        
        # 生成试卷Word文档
        doc = Document()
        
        # 设置页面
        section = doc.sections[0]
        section.top_margin = Cm(2.54)
        section.bottom_margin = Cm(2.54)
        section.left_margin = Cm(2.54)
        section.right_margin = Cm(2.54)
        
        # 生成内容
        exam_text = self.generate_exam()
        for line in exam_text.split('\n'):
            if line.strip():
                if '═' in line or '─' in line:
                    doc.add_paragraph(line)
                elif line.startswith('一、') or line.startswith('二、') or line.startswith('三、'):
                    doc.add_heading(line, level=2)
                elif line.startswith('1.') or line.startswith('2.') or line.startswith('3.'):
                    doc.add_paragraph(line)
                else:
                    doc.add_paragraph(line)
        
        exam_path = os.path.join(output_dir, 'exam.docx')
        doc.save(exam_path)
        
        # 生成答案Word文档
        doc_answer = Document()
        answer_text = self.generate_answer_sheet()
        for line in answer_text.split('\n'):
            if line.strip():
                doc_answer.add_paragraph(line)
        
        answer_path = os.path.join(output_dir, 'answer.docx')
        doc_answer.save(answer_path)
        
        return exam_path, answer_path

# 使用示例
exam = ExamGenerator('数学', '初中一年级', '2026年春季期中考试')
exam.add_choice_question('下列哪个是质数？', ['4', '6', '7', '9'], 'C', 2)
exam.add_fill_blank('12的平方根是____', '±2√3', 2)
exam.add_true_false('0是最小的自然数', '×', 1)
exam.add_calculation('计算：2x + 5 = 13，求x的值', 'x = 4', 10)

exam.save('/path/to/output')
```

---

## 试卷格式标准

### 试卷结构

```
┌─────────────────────────────────────────────────────────┐
│  2026年春季期中考试                                      │
│  数学 · 初中一年级                                       │
│  考试时间：90分钟 · 满分：100分                          │
└─────────────────────────────────────────────────────────┘

姓名：__________ 班级：__________ 学号：__________

一、选择题（每题2分，共20分）

1. 下列哪个是质数？
   A. 4    B. 6    C. 7    D. 9

二、填空题（每题2分，共20分）

1. 12的平方根是__________

三、计算题（共60分）

1. 解方程：2x + 5 = 13（10分）
```

---

## 使用示例

### 生成数学试卷

```
User: "帮我出一套初中一年级数学试卷，5道选择题，5道填空题，2道计算题"

Agent:
1. 搜索初中数学知识点
2. 生成试题
3. 验证答案
4. 排版输出
```

### 生成语文试卷

```
User: "生成一份小学三年级语文试卷，包含阅读理解"

Agent:
1. 搜索小学语文课程标准
2. 选择合适的阅读材料
3. 生成题目
4. 输出试卷
```

---

## 试题准确性保证

### 验证流程

```
生成试题
    ↓
搜索标准答案
    ↓
多源交叉验证
    ↓
标记置信度
    ↓
输出试题+答案
```

### 置信度标记

- ✅ 高置信度：多源验证一致
- ⚠️ 中置信度：单源验证
- ❌ 低置信度：需要人工确认

---

## Notes

- 使用web search获取最新知识
- 答案经过交叉验证
- 支持中英文输出
- 可直接打印
