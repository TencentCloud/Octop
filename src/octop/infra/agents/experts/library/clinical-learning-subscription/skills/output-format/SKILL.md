---
name: output-format
description: 医学安全域输出的统一格式校验。四条硬格式（模板头/来源行/边界声明/禁编造）与 validate_output.py 调用流程。指南学习、章节展开、学习路径图、学习诊断、备考推荐、医保内容、指南更新提醒、每日单元等医学安全域输出（含定时推送与对话内即时回答）发出前必走此技能校验；通用任务不套用。
---

# 医学安全域输出格式校验

## 适用范围

以下模块的输出（无论对话内即时回答还是定时推送）必须经本技能校验：

`guideline_learning`、`daily_guideline_learning`、`guideline_section_expansion`、`guideline_learning_pathway`、`guideline_learning_diagnosis`、`guideline_update_reminder`、`professional_update_summary`、`insurance_policy_summary`、`insurance_policy_learning`、`insurance_policy_retrospective`、`exam_material_recommendation`。

**通用任务（写作/翻译/编程/计划/数据整理等）不套用本技能**：不要求模板头、不要求权威来源行、不加医学免责声明。校验时对通用输出使用 `--module general_task`，不要误用医学模块名。

**纯信源核验不套用本技能**：只判断文件是否为权威原文、是否最新有效以及修订/替代/废止关系时，由 `source-verify` skill 使用自己的【信源核验】模板完成，不再调用本技能或 `validate_output.py`。如果核验后还要生成指南学习内容，再对学习内容调用本技能。

## 资源路径

以下路径均从当前 `skills/output-format/SKILL.md` 向上两级定位专家工作区，必须直接使用，不得通过 `glob`、`grep` 或递归 `ls` 寻找，也不得为调用校验器而先读取脚本源码：

- `../../references/output-templates.md`
- `../../references/source-policy.yaml`
- `../../scripts/validate_output.py`

校验器从标准输入或 `--text-file` 接收待校验正文。不要无正文试运行校验器，也不要通过读取/搜索源码猜参数或模板规则。

## 常用模块映射

| 用户请求实质 | module | 模板要求 |
| --- | --- | --- |
| 总结、展开或讲解指南中的某章、某节、筛查/随访等专题 | `guideline_section_expansion` | 【指南章节展开】；含依据、章节、原文定位、原文要点、学习提示、边界及“不替代原文” |
| 把整份指南整理为学习顺序或学习路径 | `guideline_learning_pathway` | 【指南学习路径图】；含依据、前置知识、编号学习顺序、边界 |
| 每日固定学习单元 | `daily_guideline_learning` | 【指南学习单元】；恰好 3 个编号要点及单元进度 |
| 学习状态或薄弱点评估 | `guideline_learning_diagnosis` | 【指南学习诊断】或【指南诊断标准学习】 |

命中上表后直接使用对应 module，不读取校验器源码二次判断。

## 四条硬格式（每次都必须）

1. **模板头**：首行 `【{模块名}｜{主题}】`，如【指南章节展开｜风险分层】。
2. **来源行**：结尾 `来源：{文件名称}：[链接]({URL})`，正例：`来源：国家卫生健康委官网：[链接](https://www.nhc.gov.cn/)`。给出期刊名、DOI、文件名时必须同时包成可点击链接，不允许只写文字出处。取不到权威链接时写明"未取得可核验权威来源，需人工核验"——不得省略来源行，不得伪造链接。
3. **边界声明**：按模块带对应一句——章节展开"不替代原文"、备考"以官方考试大纲为准"、医保"不作为报销依据"、涉患者请求"不提供个体诊疗"。
4. **不得编造**：页码、条目号、版本、文件名、机构名称，取不到权威依据就标"待核验"，绝不凭记忆补全。

详细模板见 `../../references/output-templates.md`。

## 校验流程

每次医学安全域输出前，严格按顺序：

1. 按对应模板一次生成完整草稿，写入 `../../outbound/.clinical-output-draft.md`。
2. 直接运行：
   ```bash
   python3 ../../scripts/validate_output.py --module <模块名> --text-file ../../outbound/.clinical-output-draft.md
   ```
   模块名必须与内容实质一致（医学学习内容用医学模块名，普通任务用 `general_task`）。
3. 校验通过 → 输出草稿正文。
4. 校验失败 → 只根据校验器返回的 `errors` 修正草稿并再校验一次；不得读取或搜索校验器源码，仍不通过则停止并说明原因，**不得绕过校验直接输出**，也不得省略【】模板头和来源行。

## 来源行格式硬规则

只要本次输出查询、引用或核验了权威信源，都必须列出来源。统一格式：

```
来源：{文件或页面名称}：[链接]({URL})
```

- 不得裸露长 URL；
- 不得把链接文字写成"查看原文""官网""点击这里"等其他词；
- 多个来源分多行列出；
- 无可靠来源时不得伪造链接，只写"未取得可核验权威来源或需人工核验"。

## 边界

本技能只管医学安全域输出的格式与校验，不生成医学内容本身（内容由各专业 skill 生成）、不执行登记/订阅、不做信源分级（信源规则见 `../../references/source-policy.yaml` 和 `source-verify` skill）。通用任务与纯信源核验一律豁免，不得借格式校验之名降级通用输出。
