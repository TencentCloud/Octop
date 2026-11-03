# 肾功能校正剂量表（内部工具，不直接输出模板给用户）

**用途**：作为 skill 底层判断依据。当用户提供 Cr / eGFR / CrCl，或已知患者有 CKD 病史时，静默查表校正处方药剂量；直接输出校正后的处方式方案，不向用户展示"完整校正规则表"本体。

---

## eGFR / CrCl 估算公式

### 首选：CKD-EPI 2021（无种族因素）

```
eGFR = 142 × min(Scr/κ, 1)^α × max(Scr/κ, 1)^(-1.200) × 0.9938^age × [1.012 if female]

κ = 0.7 (♀) or 0.9 (♂)
α = -0.241 (♀) or -0.302 (♂)
Scr 单位：mg/dL（1 mg/dL = 88.4 μmol/L）
```

### 药物剂量调整常用：Cockcroft-Gault（估算 CrCl）

```
CrCl (mL/min) = [(140 - age) × weight(kg)] / [72 × Scr(mg/dL)]
              × 0.85 (♀)
```

**注**：多数药品说明书采用 CrCl（Cockcroft-Gault）分层；eGFR（CKD-EPI 或 MDRD）用于 CKD 分期。药物剂量校正统一使用 **CrCl**。

### CKD 分期（KDIGO 2012）

| 期别 | eGFR (mL/min/1.73m²) | 处置 |
|---|---|---|
| G1 | ≥90 + 蛋白尿 | 病因治疗 |
| G2 | 60-89 + 蛋白尿 | 病因治疗 |
| G3a | 45-59 | 多数经肾药需评估 |
| G3b | 30-44 | 多数经肾药需减量 |
| G4 | 15-29 | 严格减量或换药，避免肾毒性药物 |
| G5 | <15 或透析 | 透析剂量、透析后追加 |

---

## 常用药物肾功能校正表

### 抗生素（重点）

| 药物 | 正常剂量 | CrCl 30-60 | CrCl 15-30 | CrCl <15 或 HD |
|---|---|---|---|---|
| **Amoxicillin** | 500mg q8h | 500mg q12h | 500mg q24h | 500mg q24h，HD 后追加 |
| **Amoxicillin-Clavulanate** | 875/125 q12h | 500/125 q12h | 500/125 q24h | 500/125 q24h，HD 后追加 |
| **Cefazolin** | 1-2g q8h | 1-2g q12h | 1-2g q24h | 1-2g q24h，HD 后 500mg |
| **Ceftriaxone** | 1-2g q24h | 无需调整 | 无需调整 | 无需调整（双通道排泄） |
| **Ceftazidime** | 1-2g q8h | 1g q12h | 1g q24h | 1g q48h，HD 后 1g |
| **Cefepime** | 1-2g q8-12h | 1-2g q12-24h | 1g q24h | 500mg q24h，HD 后 1g |
| **Meropenem** | 1g q8h | 1g q12h | 500mg q12h | 500mg q24h，HD 后 500mg |
| **Piperacillin-Tazobactam** | 4.5g q6-8h | 3.375g q6h | 2.25g q6h | 2.25g q8h，HD 后 0.75g |
| **Vancomycin** | 15-20mg/kg q8-12h | 15mg/kg q12-24h | 15mg/kg q24-48h | 按血药浓度监测（谷值 15-20mg/L），HD 后追加 |
| **Gentamicin** | 5-7mg/kg q24h | 5-7mg/kg q36h | 5-7mg/kg q48h | 避免；必须用则按血药浓度 |
| **Levofloxacin** | 750mg q24h | 750mg q48h 或 500mg q24h | 750mg q48h（首剂 750mg） | 500mg q48h（首剂 750mg），HD 后无追加 |
| **Ciprofloxacin** | 400mg iv q12h / 500mg po q12h | 无需调整 | 400mg iv q24h / 500mg po q24h | 400mg iv q24h / 500mg po q24h |
| **Trimethoprim-Sulfamethoxazole** | TMP 160mg q12h | q12h | q24h（半量） | 避免 |
| **Nitrofurantoin** | 100mg q6h | — | **CrCl <60 禁用**（尿药浓度不足 + 神经毒性↑） | 禁用 |
| **Fluconazole** | 200-400mg qd | 无需调整 | 半量 | 半量，HD 后 100% 剂量 |
| **Acyclovir**（iv） | 5-10mg/kg q8h | 5-10mg/kg q12-24h | 5mg/kg q24h | 2.5mg/kg q24h，HD 后追加 |

### 心血管药物

| 药物 | CrCl 30-60 | CrCl 15-30 | CrCl <15 或 HD |
|---|---|---|---|
| **ACEI（Enalapril、Lisinopril）** | 起始半量，监测 K+/Cr | 起始 1/4 量，严密监测 | 慎用；急性肾损伤期禁用 |
| **ARB（Valsartan、Losartan）** | 无需常规调整 | 起始半量，监测 | 慎用 |
| **Spironolactone** | 慎用（高钾风险） | 避免 | 禁用 |
| **Digoxin** | 剂量减 25-50% | 减 50% | 减 75%，血药浓度监测（0.5-2.0 ng/mL） |
| **Atenolol** | 50mg qd | 25mg qd | 25mg q48h |
| **Sotalol** | q24h | q36-48h | 避免（QT 延长 + 累积） |
| **DOAC—Rivaroxaban** | 15mg qd（房颤 CrCl 15-50）| 15mg qd（谨慎） | **CrCl <15 禁用** |
| **DOAC—Apixaban** | 无需调整（除非满足降剂量条件*） | 无需调整 | 2.5mg bid 或避免 |
| **DOAC—Dabigatran** | 150mg bid（CrCl 30-50）；110mg bid | **CrCl <30 禁用** | 禁用 |
| **Enoxaparin** | 无需调整 | 1mg/kg qd（治疗量）或 30mg qd（预防量） | 避免，改用普通肝素 |

*Apixaban 房颤降剂量条件（≥2 项）：≥80 岁、体重 ≤60kg、Scr ≥1.5mg/dL

### 内分泌 / 代谢

| 药物 | CrCl 30-60 | CrCl <30 |
|---|---|---|
| **Metformin** | eGFR 45-59：慎用；30-44：减量 50% | **eGFR <30 禁用** |
| **SGLT-2i（Empagliflozin、Dapagliflozin）** | eGFR ≥20 心衰适应证可用；降糖适应证 eGFR ≥30 | eGFR <20 停药 |
| **GLP-1RA（Semaglutide、Liraglutide）** | 无需调整 | 无需调整（谨慎脱水） |
| **Sulfonylureas（Glimepiride、Glipizide）** | Glipizide 相对安全；Glimepiride 减量 | 避免（低血糖累积） |
| **Insulin** | 剂量减 25% | 剂量减 50% |
| **Allopurinol** | 200mg qd | 100mg qd 或隔日 | **HLA-B\*58:01 阳性禁用** |
| **Colchicine** | 减量 50% | 避免长期使用 |

### 镇痛 / 抗炎

| 药物 | CrCl 30-60 | CrCl <30 |
|---|---|---|
| **NSAID（Ibuprofen、Naproxen、Diclofenac）** | 慎用，短程 | **避免使用**（AKI、CKD 进展风险） |
| **Acetaminophen** | 无需调整 | 无需调整（首选镇痛） |
| **Tramadol** | 100mg q12h | 50mg q12h |
| **Morphine** | 减 25-50% | 避免，改用 Hydromorphone、Fentanyl（不经肾） |
| **Gabapentin** | 300-600mg tid | 100-300mg qd |
| **Pregabalin** | 75-150mg/d | 25-75mg/d |

### 神经精神

| 药物 | CrCl 30-60 | CrCl <30 |
|---|---|---|
| **Lithium** | 减 25-50%，血药浓度监测（0.6-1.2 mmol/L） | 避免；必须用则严密监测 |
| **Levetiracetam** | 500-1000mg q12h | 250-750mg q12h |
| **Topiramate** | 减 50% | 减 50%，HD 后追加 |

### 抗肿瘤 / 免疫

| 药物 | 备注 |
|---|---|
| **Cisplatin** | eGFR <60 慎用；<45 避免；水化 + 甘露醇 |
| **Methotrexate** | 高剂量方案 eGFR <60 严密监测/减量 |
| **Bisphosphonates（Zoledronate）** | CrCl <35 禁用（AKI 风险） |
| **Contrast media（碘造影剂）** | eGFR <30 权衡使用；水化预防 CIN；停用 Metformin 24-48h |

---

## 特殊场景

### 血液透析（HD）患者
- 大部分药物 HD 后需追加剂量（分子量小、蛋白结合率低、Vd 小）
- 长效药物（如 Levofloxacin）HD 后可不追加
- 具体见各药物"HD 后追加"列

### 腹膜透析（PD）患者
- 清除率介于 HD 与 CrCl <15 之间，多数按 CrCl <15 剂量
- 部分抗生素可腹腔内给药

### AKI 患者
- CRRT（连续性肾脏替代治疗）剂量与 CrCl 30-60 相当
- 早期 AKI 恢复期需动态调整，避免固定剂量

### 老年患者
- Scr 正常 ≠ 肾功能正常（肌肉量减少掩盖肾功能下降）
- ≥65 岁必查 CrCl / eGFR，不可仅凭 Scr 判断

---

## Skill 内部使用规则

### 触发时机

- 用户提供 Cr、eGFR、CrCl 等肾功能指标
- 用户提及 CKD 病史、透析、肾功能不全
- 咨询本表收录的经肾排泄药物时，触发门控追问（P1 级）：
  > "在给出方案前需先确认肾功能——[药名]主要经肾排泄，请问 CrCl 或近期 Cr / eGFR？"

### 静默计算流程

1. **提取变量**：Cr、年龄、性别、体重（缺 CrCl 时优先按 C-G 公式估算，标注单位换算）
2. **分层**：按 CrCl 分档（>60 / 30-60 / 15-30 / <15）
3. **查表**：命中即按分档剂量输出
4. **透析患者**：额外加 HD 后追加规则
5. **同时提示需监测的指标**（如 Vancomycin 谷值、Digoxin 浓度、K+/Cr 变化）

### 输出格式示例

**有 Cr 时**：
> 患者 Cr 135μmol/L（1.52 mg/dL），按 C-G 公式估算 CrCl ≈ 42 mL/min（男，65 岁，70kg），属 G3b。
> Amoxicillin 500mg po q12h × 7d（正常 q8h 需延长间隔），疗程结束前复查 Cr。以上依据 KDIGO 2012 + 说明书。

**有 eGFR 时**：
> eGFR 45 mL/min/1.73m²（CKD G3a）。**禁用 Metformin**（eGFR <45 累积乳酸酸中毒风险）。降糖方案改用 Linagliptin 5mg po qd（不经肾）或 Empagliflozin 10mg po qd（eGFR ≥20 均可用，同时具心肾获益）。以上依据 2023 ADA/KDIGO 糖尿病 + CKD 联合共识。

**红旗触发场景**（碘造影剂 + Metformin）：
> ⚠️ **临床红旗：** eGFR 35 mL/min，行碘造影检查前后需**停用 Metformin 48h**（造影剂诱发 AKI + Metformin 蓄积乳酸酸中毒风险），复查 Cr 稳定后再恢复。同时给予水化（生理盐水 1mL/kg/h × 12h 前后），预防 CIN。以上依据 2020 ESUR 造影剂指南。

### 拒绝场景

- 咨询窄治疗窗肾排泄药（Vancomycin、Aminoglycosides、Lithium、Digoxin）但缺 Cr → 门控追问，不给方案
- 剂量表未收录药物 → L3 兜底，标注"未在标准校正表核实，请对照说明书 CrCl 分层"

### 证据来源

- KDIGO 2012 CKD 分期指南
- 各药物说明书肾功能不全用法段
- Sanford Guide to Antimicrobial Therapy
- Renal Drug Handbook (Ashley & Dunleavy)
- 2023 ADA/KDIGO 糖尿病 CKD 共识
- 中华医学会肾脏病学分会《慢性肾脏病患者合理用药指南（2020）》
