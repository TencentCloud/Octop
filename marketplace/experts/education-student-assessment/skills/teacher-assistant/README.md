# 新知绘宇·教师助手

[![SkillHub](https://img.shields.io/badge/Skill-教师助手-blue?style=flat-square)](https://example.com)
[![Version](https://img.shields.io/badge/Version-1.0.0-green?style=flat-square)]()
[![License](https://img.shields.io/badge/License-MIT--0-blue?style=flat-square)](LICENSE)

> 每一位老师的专属 AI 备课、出题、成绩、家校沟通全能助手。由深圳新知绘宇科技有限公司出品。

覆盖 **备课 → 出题 → 教学 → 作业 → 成绩 → 沟通 → 总结** 全链路，一个人，顶一整个教务团队。

---

## 功能特点

| 模块 | 能力 | 触发词示例 | 输出物 |
|:---:|------|-----------|--------|
| 1 | 教案生成 | 备课、教案、写教案、教学设计 | 完整教案（目标/过程/板书/反思）|
| 2 | 智能出题 | 出题、组卷、试卷、考题 | 多种题型试卷（含答案/难度）|
| 3 | 学情分析 | 成绩、排名、班级报告 | 多维分析报告/班级画像 |
| 4 | 家校沟通 | 评语、家长通知、家长信 | 期末评语/通知/个性化反馈 |
| 5 | 教学总结 | 周报、月报、学期总结 | 结构化教学总结 |
| 6 | 作业设计 | 作业、分层作业、练习 | 三层作业（基础/提高/拓展）|
| 7 | 学生档案 | 档案、成长记录、辅导 | 学生画像/成长档案 |
| 8 | 班级管理 | 班规、班委、座位表 | 班级公约/班委职责/座位表 |

---

## 适用对象

- K12 中小学教师（小学/初中/高中）
- 班主任、教务主任
- 教育培训机构教师

---

## 快速开始

### 方式一：在 WorkBuddy 中安装

在 WorkBuddy 的 Skill 市场中搜索「教师助手」，一键安装即可使用。

### 方式二：独立工具脚本

```bash
# 安装依赖
pip install -r requirements.txt

# 教案生成（交互式）
python tool_plans.py

# 智能出题
python tool_exams.py

# 成绩分析
python tool_grades.py

# 评语生成
python tool_comments.py

# 作业设计
python tool_hw.py

# 家校沟通
python tool_comms.py
```

---

## 目录结构

```
teacher-assistant/
├── SKILL.md                    # Skill 定义文件（含完整能力路由和模板）
├── README.md                   # 本文件
├── _skillhub_meta.json         # SkillHub 元信息
│
├── a_plan.md                  # 教案生成模板
├── a_exam.md                  # 智能出题模板
├── a_analysis.md              # 学情分析模板
├── a_comment.md               # 评语生成模板
├── a_weekly.md                # 教学周报模板
├── a_hw.md                    # 分层作业模板
├── a_profile.md               # 学生档案模板
├── a_class.md                 # 班级管理模板
├── a_letter.md                # 家长信模板
├── a_reflect.md              # 教学反思模板
│
├── tool_plans.py             # 教案生成脚本
├── tool_exams.py             # 出题脚本
├── tool_grades.py            # 成绩分析脚本
├── tool_comments.py          # 评语生成脚本
├── tool_comms.py             # 家校沟通脚本
├── tool_hw.py                # 作业设计脚本
│
└── requirements.txt         # Python 依赖
```

---

## 使用示例

### 教案生成

```
用户：帮我写一份五年级语文《落花生》的教案
AI：  → 输出完整教案（教学目标/重点难点/教学过程/板书/作业/反思）
```

### 智能出题

```
用户：出一套五年级语文第二单元测验题，含10道选择、5道填空、2道简答
AI：  → 输出完整试卷 + 参考答案 + 评分标准
```

### 学情分析

```
用户：分析这份成绩单，生成班级分析报告
AI：  → 输出整体概况/分数段/班级画像/教学建议
```

### 期末评语

```
用户：生成小明同学的期末评语
AI：  → 输出个性化评语（德智体美劳全覆盖）
```

### 分层作业

```
用户：设计一份数学分层作业，五年级第二单元
AI：  → 基础层（必做）/ 提高层 / 拓展层（选做）
```

---

## 模板资源

| 文件 | 用途 |
|------|------|
| `a_plan.md` | 通用教案模板 |
| `a_exam.md` | 试卷模板 |
| `a_analysis.md` | 成绩分析报告模板 |
| `a_comment.md` | 期末评语模板集 |
| `a_weekly.md` | 教学周报模板 |
| `a_hw.md` | 分层作业模板 |
| `a_profile.md` | 学生档案模板 |
| `a_class.md` | 班级公约/班委模板 |
| `a_letter.md` | 家长信模板集 |
| `a_reflect.md` | 教学反思模板 |

---

## 内置教学参考

SKILL.md 中内置 5 份教学参考，AI 在生成内容时可直接调用：

1. **2025年教育政策要点** — 双减、新课标、中考改革、家庭教育促进法
2. **各学科命题规范** — 各学科题型分布与命题趋势
3. **学生成长评估标准** — 五育评价、综合素质评价原则
4. **家校沟通话术参考** — 常见场景沟通话术与原则
5. **学科教学策略速查** — 各学科课堂教学策略

---

## 政策合规

- 教学内容符合「双减」政策要求
- 作业设计有分层，书面作业时长合规
- 试卷命题难度比例参考 7:2:1 原则
- 评语写作遵守师德规范，无负面标签
- 生成内容需教师审核后使用

---

## 更新日志

### v1.0.0（2026-04）
- 首发版本
- 8大核心能力，10套模板，5份教学参考
- 支持 WorkBuddy / Cursor / Claude Code

---

## 许可证

MIT-0 License，可商业使用，无需署名。

---

## 联系我们

**深圳新知绘宇科技有限公司**

- 邮箱：contact@xinzhihuiyu.com
- 产品：WorkBuddy / ClawPro AI 助手平台
