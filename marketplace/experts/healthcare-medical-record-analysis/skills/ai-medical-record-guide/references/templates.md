# 病案首页 & 出院小结标准模板

**Source**: clinical-note-writer-v2.md (Templates Section)

---

## 1. 病案首页标准模板

```markdown
# 住院病案首页

## 患者基本信息
| 项目 | 内容 | 项目 | 内容 |
|------|------|------|------|
| 姓名 | [name] | 性别 | [gender] |
| 出生日期 | [dob] | 年龄 | [age] |
| 身份证号 | [id_number（脱敏）] | 民族 | [ethnicity] |
| 婚姻状况 | [marital_status] | 职业 | [occupation] |
| 出生地 | [birthplace] | 现住址 | [address] |
| 联系电话 | [phone（脱敏）] | 联系人姓名 | [contact_name] |
| 联系人关系 | [contact_relation] | 联系人电话 | [contact_phone（脱敏）] |

## 住院信息
| 项目 | 内容 |
|------|------|
| 医疗机构名称 | [hospital_name] |
| 科别 | [department] |
| 病房 | [ward] |
| 床号 | [bed_no] |
| 入院日期时间 | [admission_datetime] |
| 出院日期时间 | [discharge_datetime] |
| 实际住院天数 | [actual_days] |

## 诊断信息

### 门诊诊断
1. [outpatient_diagnosis_1]
2. [outpatient_diagnosis_2]

### 入院诊断
1. [admission_dx_1] （[ICD_code_1]）
2. [admission_dx_2] （[ICD_code_2]）

### 出院诊断
| # | 诊断名称 | ICD编码 | 入出院对比 | 治愈/好转/未愈/死亡/其他 |
|---|---------|---------|-----------|------------------------|
| 1 | [main_dx] | [ICD] | — | [outcome] |
| 2 | [other_dx_1] | [ICD] | [same/changed/new] | [outcome] |
| 3 | [other_dx_2] | [ICD] | [same/changed/new] | [outcome] |

### 手术及操作
| # | 手术/操作名称 | 日期 | 麻醉方式 | 术者 | 切口愈合等级 |
|---|-------------|------|---------|------|-------------|
| 1 | [surgery_1] | [date] | [anesthesia] | [surgeon] | [healing_grade] |

### 病理诊断
- [pathology_dx] （[pathology_number]）

## 费用信息（元）
| 类别 | 金额 |
|------|------|
| 总费用 | [total_fee] |
| 综合医疗服务类 | [service_fee] |
| 诊断类 | [diagnostic_fee] |
| 治疗类 | [treatment_fee] |
| 康复类 | [rehab_fee] |
| 中医类 | [tcm_fee] |
| 西药费 | [western_med_fee] |
| 中药/成药费 | [chinese_med_fee] |
| 血液和血液制品费 | [blood_fee] |
| 耗材费 | [material_fee] |
| 检查检验费 | [lab_exam_fee] |
| 其他费用 | [other_fee] |

---
**质控医师**：____________　 **质控日期**：______年__月__日
**病案质量评分**：____ 分　 **病案等级**：甲/乙/丙
```

---

## 2. 出院小结标准模板

```markdown
# 出院记录（出院小结）

**姓名**：[name]　**性别**：[gender]　**年龄**：[age]岁
**科室**：[department]　**床号**：[bed_no]
**住院号**：[admission_no]

## 入院诊断
1. [admission_dx_1]
2. [admission_dx_2]

## 诊治经过

患者于 [admission_date] 因 [chief_complaint] 入院。入院后完善相关检查：
[list of key exams and results]

根据检查结果，给予以下治疗：
[treatment summary - medications, procedures, nursing]

治疗期间病情变化：
[key events during hospitalization]

经治疗，患者 [improvement description]，准予出院。

## 出院诊断
1. [discharge_dx_1] （入院诊断：[same/different]）
2. [discharge_dx_2]

## 出院时情况
T [temp]°C　P [hr]次/分　R [rr]次/分　BP [bp] mmHg
[general condition description]

## 出院医嘱

### 用药指导
| 药品名 | 剂量 | 用法 | 数量 | 备注 |
|--------|------|------|------|------|
| [med_1] | [dose] | [usage] | [qty] | [remark] |
| [med_2] | [dose] | [usage] | [qty] | [remark] |

### 生活指导
- 活动：[activity_instruction]
- 饮食：[diet_instruction]

## 随复诊安排
- **复诊时间**：[followup_date]
- **复查项目**：[followup_exams]
- **红线症状**（出现以下情况立即就诊）：
  - [red_flag_symptom_1]
  - [red_flag_symptom_2]
  - [red_flag_symptom_3]

---
记录医师：____________
日期：______年__月__日
```

---

## 3. 门诊病历模板

```markdown
# 门诊病历

**就诊时间**：[datetime]　**科室**：[department]

## 主诉
[chief_complaint]

## 现病史
[present_illness]

## 既往史
[past_history]

## 过敏史
[allergy_history] （无 / 有：[具体过敏原及反应]）

## 体格检查
T [temp]°C　P [hr]次/分　R [rr]次/分　BP [sbp]/[dbp] mmHg

[physical_exam_findings]

## 辅助检查
[lab_and_imaging_results]

## 初步诊断
1. [diagnosis_1]
2. [diagnosis_2]

## 处置
### 处方
[处方内容]

### 医嘱
[instructions]

---
医师：____________
```

---

## 4. 手术记录模板

```markdown
# 手术记录

**手术日期**：[date] **开始时间**：[start_time] **结束时间**：[end_time]

**手术名称**：[surgery_name]

**术前诊断**：[preop_dx]　**术后诊断**：[postop_dx]

**术者**：[surgeon]　**一助**：[first_assist]　**二助**：[second_assist]
**麻醉方式**：[anesthesia]　**麻醉医师**：[anesthesiologist]

## 手术经过

[surgical_procedure_detailed_description]

## 术中情况
- **术中出血量**：[blood_loss] ml
- **输血**：[transfusion_info] （无）
- **切除标本**：[specimen_sent_to_pathology]
- **引流管放置**：[drain_placement]

## 术后处理
[postop_instructions]

---
术者签名：____________
记录者签名：____________
```

---

## 5. 处方模板（全口径）

### 5.1 药品处方

```markdown
### Rp（药品处方）

| # | 药品名称 | 规格 | 剂量 | 频次 | 途径 | 疗程 | 组号 | 皮试 | 数量 |
|---|---------|------|------|------|------|------|------|------|------|
| 1 | [drug_name] | [spec] | [dose] | [freq] | [route] | [duration] | [grp] | [Y/N] | [qty] |
| 2 | ... | | | | | | | | |
```

### 5.2 检查申请单

```markdown
### 检查项目
| # | 项目名称 | 检查部位 | 目的 | 急诊/常规 | 备注 |
|---|---------|---------|------|----------|------|
| 1 | [exam_name] | [site] | [purpose] | [urgency] | [note] |
```

### 5.3 处置申请单

```markdown
### 处置项目
| # | 项目名称 | 操作说明 | 执行频次 | 备注 |
|---|---------|---------|---------|------|
| 1 | [proc_name] | [desc] | [freq] | [note] |
```

### 5.4 材料清单

```markdown
### 材料
| # | 材料名称 | 规格 | 单位 | 数量 | 备注 |
|---|---------|------|------|------|------|
| 1 | [mat_name] | [spec] | [unit] | [qty] | [note] |
```
