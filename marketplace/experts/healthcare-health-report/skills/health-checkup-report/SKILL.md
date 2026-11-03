---
name: health-checkup-report
description: Interpret routine health checkup reports and lab results in plain Chinese, highlighting abnormal items, likely meaning, urgency, follow-up questions, and practical next steps. Use when the user shares a体检报告、化验单、检查结果、检验指标、异常箭头项目, asks what abnormal results mean, or wants a structured non-diagnostic explanation rather than raw numbers only.
---

# Health Checkup Report

## Overview

Use this skill to explain common health checkup and lab report findings in a calm, structured way. Focus on helping the user understand what each flagged item may mean, what is worth paying attention to, and what next step is reasonable.

This skill is **not** for diagnosing disease. It should explain, prioritize, and suggest appropriate follow-up.

## Workflow

1. Identify the report type and available context:
   - annual physical exam / 体检报告
   - blood routine / urine routine / liver function / kidney function / blood lipids / blood glucose
   - imaging or ultrasound summary
   - tumor marker or specialty test
2. Extract:
   - test item names
   - numeric values
   - reference ranges
   - high/low flags
   - age/sex if provided
3. Start with the abnormal or borderline items, then mention major normal findings only if helpful.
4. Group related abnormalities instead of explaining every row in isolation.
5. Give a practical interpretation with one of these urgency levels:
   - **观察即可**
   - **建议复查/门诊咨询**
   - **建议尽快就医**
6. End with concrete next steps and questions to clarify if the report is incomplete.

## Safety Rules

- State clearly that this is an informational interpretation, not a medical diagnosis.
- Do not tell the user to ignore serious red flags.
- Escalate clearly for dangerous findings, such as:
  - very high or very low glucose with symptoms
  - severe anemia indicators
  - major liver/kidney function abnormalities
  - chest pain, difficulty breathing, syncope, neurological symptoms, or bleeding mentioned alongside the report
  - imaging findings that explicitly recommend urgent follow-up
- If the user mentions acute symptoms or alarming signs, advise prompt medical care instead of over-analyzing the report.
- Avoid false reassurance.

## Interpretation Rules

For each important abnormal item, explain:
- 这项是什么
- 偏高/偏低通常意味着什么
- 常见但不唯一的原因
- 是否需要结合其他指标一起看
- 建议怎么处理

Prefer clustered interpretation examples:
- ALT/AST/GGT -> liver-related pattern
- LDL-C/TC/TG/HDL-C -> lipid pattern
- 尿酸/肌酐/尿素 -> renal/metabolic pattern
- Hb/WBC/PLT and differential -> blood routine pattern
- TSH/FT3/FT4 -> thyroid pattern
- 空腹血糖/HbA1c -> glucose metabolism pattern

Do not over-interpret a single mild abnormality when the broader context suggests low urgency.

## Clarification Triggers

Ask follow-up questions when needed, for example:
- 缺少参考范围
- 只有项目名没有数值
- 图片不清晰或项目不完整
- 需要年龄/性别才能更合理解读
- 用户只发一句“这个体检有问题吗”但没给报告内容

Useful clarifying questions:
- 方便把异常项目、数值和参考范围一起发我吗？
- 这是体检报告、抽血化验单，还是影像检查结果？
- 你的年龄、性别，以及有没有医生已经提示过重点问题？
- 最近有没有明显不舒服，比如头晕、胸闷、乏力、发热、腹痛等？

## Response Pattern

Default structure:

### 先说结论
- Give a short overall judgment.

### 重点异常项
For each major abnormality:
- 项目
- 当前结果
- 怎么理解
- 常见相关原因
- 建议动作

### 这些指标建议放在一起看
- Group related findings and explain the bigger picture.

### 建议下一步
- Observe / recheck / clinic / urgent care
- Lifestyle or follow-up suggestions when appropriate

### 提醒
- This is an interpretation for reference and does not replace a doctor's diagnosis.

## Output Quality Bar

- Use plain Chinese.
- Be calm, specific, and practical.
- Prefer “可能/常见于/需要结合” over certainty.
- Do not use scary language for mild deviations.
- Do not minimize serious abnormalities.
- If confidence is limited because the data is incomplete, say so directly.

## Good Framing Language

Preferred wording:
- `这项轻度偏高，常见于……，但需要结合……一起看`
- `单看这一项不能直接下诊断`
- `从体检角度看，更像是需要复查确认`
- `如果同时有明显不适，建议尽快线下就医`

Avoid wording like:
- `你就是得了……`
- `肯定没事`
- `完全不用管`

---

## 🚀 First-Success Path

**30秒快速上手：三步获取体检报告解读**

1. **分享异常项** — 粘贴体检报告中的异常数值项目（如：谷丙转氨酶 68 U/L ↑）
2. **告知基本信息** — 年龄、性别、有无不适症状
3. **获取分层解读** — 得到重点异常解读、关联分析、建议下一步

> 示例："谷丙转氨酶 68，谷草转氨酶 45，总胆固醇 6.2，低密度脂蛋白 4.1，尿酸 480。男，32岁，最近应酬多，偶尔喝酒。"

---

## 📝 Sample Prompts

### 示例 1：多指标异常解读
**用户输入：**
```
体检报告：ALT 78 U/L，AST 52 U/L，GGT 85 U/L，总胆红素 21 μmol/L，其余正常。男，40岁，体重偏胖，偶尔喝酒。
```

**期望输出：**
```
### 先说结论
肝功能指标轻度异常，核心是 GGT 升高显著（＞2倍），结合 ALT/AST 同时升高，提示肝细胞损伤合并胆道/酒精相关影响。

### 重点异常项
- **ALT（78↑）**：肝细胞损伤的敏感指标。常见于脂肪肝、饮酒、药物影响。
- **AST（52↑）**：轻度升高，ALT>ASTRatio≈1.5，典型肝细胞来源模式。
- **GGT（85↑）**：GGT显著升高是酒精/胆汁淤积的重要线索。
- **总胆红素（21↑）**：轻度升高，建议进一步查直接/间接胆红素分组。

### 建议下一步
- 建议消化内科门诊，查腹部B超排除脂肪肝
- 肝功能复查前应禁酒1周，清淡饮食
- 如持续异常需筛查乙肝/丙肝

### 提醒
→ 目前属轻度异常，不紧急但值得专科就诊查明原因。
```

### 示例 2：贫血模式判断
**用户输入：**
```
体检：Hb 105 g/L，MCV 78 fL，MCH 26 pg，RDW 16.5%。女，28岁，月经量偏多。
```

**期望输出：**
```
### 先说结论
小细胞低色素性贫血模式，结合用户年龄和月经情况，最可能为缺铁性贫血。建议复查铁代谢指标并补铁治疗。

### 重点异常项
- **Hb（105↓）**：轻度贫血
- **MCV（78↓）、MCH（26↓）**：小细胞低色素特征，提示血红蛋白合成障碍
- **RDW（16.5%↑）**：红细胞大小不均，缺铁性贫血的典型改变

### 建议下一步
- 查铁蛋白、血清铁、总铁结合力确认
- 补铁治疗（口服铁剂），同时排查消化系统慢性失血
- 月经量大的话可咨询妇科
- 一般补铁后2周Hb开始回升
```

### 示例 3：肿瘤标志物解读
**用户输入：**
```
CA19-9 42 U/mL（r0-37），CEA 3.2 ng/mL（r0-5），AFP 6.8 ng/mL（r0-7），其余正常。男，55岁，有吸烟史30年。
```

**期望输出：**
```
### 先说结论
CA19-9 轻度升高（参考上限的1.1倍），其他肿瘤标志物在正常范围。单项轻度升高在非恶性疾病（胰腺炎、胆管炎、糖尿病）中也常见，不用过度担忧但建议复查。

### 重点异常项
- **CA19-9（42↑）**：轻度升高，可见于胰腺/胆道炎症、糖尿病，不特异
- **CEA（3.2）**：正常范围；吸烟者CEA可轻高，这里未超标
- **AFP（6.8）**：正常范围

### 建议下一步
- 1个月后复查CA19-9（复查前避免饮酒、油腻饮食）
- 如持续升高或涨幅明显，做腹部增强CT
- 定期体检、胃肠镜
```

### 示例 4：甲状腺功能解读
**用户输入：**
```
TSH 0.15 mIU/L（r0.35-4.9），FT3 6.8 pmol/L（r3.5-6.5），FT4 22.5 pmol/L（r11.5-22.7）。女，35岁，心悸、易怒、体重下降3个月。
```

**期望输出：**
```
### 先说结论
TSH 被抑制，游离甲状腺激素处于正常高限或轻度升高，结合临床症状，符合甲状腺功能亢进症（甲亢）的典型实验室模式。

### 重点异常项
- **TSH（0.15↓）**：显著抑制，提示甲状腺激素负反馈过度
- **FT3（6.8↑）**：轻度升高，甲亢早期FT3先升高
- **FT4（22.5）**：正常高限，T3型甲亢可能性

### 建议下一步
- 尽快内分泌科就诊
- 查TRAb、TPOAb、TgAb明确病因（Graves病 vs 甲状腺炎）
- 血常规（粒细胞）、肝功能、甲功三项+抗体
- 甲状腺彩超
- 当前不做含碘造影剂/海带紫菜
```

### 示例 5：尿常规异常
**用户输入：**
```
尿常规：潜血（++），蛋白质（+），白细胞（-），亚硝酸盐（-），尿胆原（-）。男，45岁，没有特别不舒服。
```

**期望输出：**
```
### 先说结论
尿潜血阳性伴轻度蛋白尿，白细胞阴性排除典型尿路感染模式。需要明确血尿来源（肾小球性 vs 非肾小球性）。

### 重点异常项
- **潜血（++）**：镜下血尿，需行尿沉渣镜检确认红细胞形态
- **蛋白质（+）**：轻度蛋白尿，与血尿同现需排除肾小球病变
- 白细胞阴性、亚硝酸盐阴性→不支持细菌感染

### 建议下一步
- 查尿沉渣（红细胞形态）、尿微量白蛋白/肌酐比值
- 血压监测
- 肾内科门诊，视结果决定是否做肾B超
- 3~6个月后复查尿常规
```

---

## 📋 Real Task Examples

| 场景 | 用户输入示例 | 技能输出要点 |
|------|-------------|-------------|
| **体检总评** | "我发的体检结果帮忙看看，主要看有没有大问题" | 先给整体判断 → 分系统解读异常 → 标注优先级 → 建议复查/就医路线 |
| **单项咨询** | "尿酸450μmol/L是不是很高？需要注意什么？" | 解释这项指标意义 → 对比参考值 → 饮食/生活方式建议 → 何时需要就医 |
| **老人体检解读** | "我父亲70岁，有糖尿病史，这次体检糖化HbA1c7.2%，肌酐105，帮忙看看"(health-checkup-report) | 结合基础病分析 → 慢病控制评估 → 肾功能动态变化 → 综合管理建议 |
| **影像报告** | "胸部CT报告：右肺上叶磨玻璃结节8mm，建议随访" | 解释磨玻璃结节概念 → 大小/形态风险评估 → 随访频率建议 → 焦虑管理 |
| **备孕检查** | "准备要宝宝，做了孕前检查，请帮忙解读一下优生四项和甲状腺功能结果" | 分项解读 → 疫苗接种/抗体保护 → 甲功对妊娠影响 → 补充叶酸等建议 |