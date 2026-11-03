# 药物基因组学参考（内部知识库，不直接输出模板给用户）

**用途**：作为 skill 底层判断依据。当用户咨询下列关联药物时，静默检索本表；若命中"高证据 PGx"药物，主动在回答中简要提示 PGx 检测的临床价值（不主动追问基因分型，除非用户已提供）。若用户主动提供分型结果，按下表分层给出临床建议。

**证据等级**：参考 CPIC（Clinical Pharmacogenetics Implementation Consortium）指南等级——A 级（有充分证据支持临床应用）、B 级（证据充分，可选实施）、C/D 级（证据不足或研究性）。本表仅收录 A/B 级药物-基因对。

---

## CPIC A 级药物-基因对（临床应用充分证据）

### CYP2C19

| 药物 | 关联表型 | 临床影响 | 建议 |
|---|---|---|---|
| **氯吡格雷（Clopidogrel）** | PM / IM（慢代谢 / 中间代谢） | 前药无法充分转化为活性代谢物，抗血小板效应下降，ACS/PCI 后 MACE 风险显著升高 | PM/IM 患者改用普拉格雷（Prasugrel）或替格瑞洛（Ticagrelor）；NM/RM 常规剂量 |
| **PPI（Omeprazole、Lansoprazole、Pantoprazole）** | RM / UM（超快代谢） | 血药浓度低，Hp 根除率与 GERD 疗效下降 | UM 患者上调剂量 50-100% 或改用 Esomeprazole/Rabeprazole（CYP2C19 依赖较小） |
| **Voriconazole** | PM | 血药浓度升高，肝毒性、神经毒性风险 | PM 起始剂量降低 50%，或改用 Isavuconazole/Posaconazole |
| **三环类抗抑郁药（Amitriptyline、Nortriptyline）** | PM / UM | PM 血药浓度升高 → 抗胆碱与心律失常风险；UM 疗效不足 | PM 起始剂量降 50% 或换 SSRI；UM 换其他类别 |
| **SSRI（Citalopram、Escitalopram、Sertraline）** | PM / UM | PM QT 延长风险升高（Citalopram/Escitalopram）；UM 疗效不足 | PM Citalopram ≤ 20mg/d、Escitalopram ≤ 10mg/d，或换其他 SSRI |

### CYP2D6

| 药物 | 关联表型 | 临床影响 | 建议 |
|---|---|---|---|
| **可待因（Codeine）、曲马多（Tramadol）** | PM / UM | PM 无法转化为吗啡 → 无镇痛；UM 转化过度 → 呼吸抑制、婴儿哺乳期致死 | PM 改用非 CYP2D6 依赖阿片（吗啡、氢吗啡酮）；UM 避免使用；**哺乳期禁用可待因（FDA 黑框警告）** |
| **他莫昔芬（Tamoxifen）** | PM | 无法转化为活性代谢物 endoxifen → 内分泌治疗失败、乳腺癌复发风险↑ | PM 改用芳香化酶抑制剂（AI）或避免强 CYP2D6 抑制剂（Paroxetine、Fluoxetine） |
| **β-blocker（Metoprolol）** | PM | 血药浓度升高 → 心动过缓、低血压 | PM 起始剂量降低 25-50%，缓慢滴定 |
| **抗精神病药（Aripiprazole、Risperidone）** | PM / UM | PM EPS 与代谢副作用风险↑；UM 疗效不足 | 按分型调整起始剂量或换药 |

### CYP2C9 + VKORC1

| 药物 | 关联表型 | 临床影响 | 建议 |
|---|---|---|---|
| **华法林（Warfarin）** | CYP2C9 \*2/\*3（PM/IM）+ VKORC1 -1639G>A | 敏感性显著升高，起始剂量需下调 30-70%；出血风险↑ | 使用 WarfarinDosing.org 或 IWPC 剂量计算器；起始 INR 监测频率增加至 q2-3d |
| **NSAID（Celecoxib、Ibuprofen、Piroxicam）** | CYP2C9 PM | 血药浓度升高，GI 出血与肾损伤风险↑ | PM 起始剂量降低 25-50%，避免长期使用 |
| **磺酰脲类降糖药（Glimepiride、Glipizide）** | CYP2C9 PM | 血药浓度升高，低血糖风险↑ | PM 起始剂量降低，加强血糖监测 |

### TPMT / NUDT15

| 药物 | 关联表型 | 临床影响 | 建议 |
|---|---|---|---|
| **硫嘌呤类（Azathioprine、6-Mercaptopurine、Thioguanine）** | TPMT 或 NUDT15 缺陷型 | 严重骨髓抑制、致命性中性粒细胞减少 | 起始剂量减至 10-30%，或改用其他免疫抑制剂；**用药前 CPIC 强烈推荐检测** |

### DPYD

| 药物 | 关联表型 | 临床影响 | 建议 |
|---|---|---|---|
| **氟尿嘧啶类（5-FU、Capecitabine）** | DPYD 缺陷型（\*2A、\*13、D949V、HapB3） | 严重致命性毒性（中性粒细胞减少、粘膜炎、腹泻） | 完全缺陷型：禁用；部分缺陷型：起始剂量降低 25-50% |

### HLA-B / HLA-A（免疫介导超敏反应）

| 药物 | 关联等位基因 | 临床影响 | 建议 |
|---|---|---|---|
| **卡马西平（Carbamazepine）** | HLA-B\*15:02（东亚、东南亚人群高频） | SJS/TEN 风险↑ 100 倍以上 | 东亚、东南亚人群用药前**必须**检测 HLA-B\*15:02；阳性者禁用，可考虑丙戊酸、拉莫三嗪、左乙拉西坦 |
| **卡马西平（Carbamazepine）** | HLA-A\*31:01（欧洲、日本、韩国人群） | SJS/TEN、DRESS 风险↑ | 阳性者禁用或高度警惕 |
| **奥卡西平（Oxcarbazepine）** | HLA-B\*15:02 | SJS/TEN 风险↑（与卡马西平交叉反应） | 阳性者禁用 |
| **别嘌醇（Allopurinol）** | HLA-B\*58:01（汉族、韩国、泰国高频） | SJS/TEN、DRESS、AGEP 风险↑ | 中国大陆汉族用药前**推荐**检测；阳性者禁用，可用非布司他、丙磺舒 |
| **阿巴卡韦（Abacavir）** | HLA-B\*57:01 | 超敏反应综合征（发热、皮疹、多器官损伤） | 用药前**强制**检测；阳性者禁用 |
| **苯妥英（Phenytoin）** | HLA-B\*15:02 | SJS/TEN 风险↑ | 阳性者慎用或换药 |

### SLCO1B1

| 药物 | 关联表型 | 临床影响 | 建议 |
|---|---|---|---|
| **辛伐他汀（Simvastatin）** | SLCO1B1 \*5（rs4149056 C 等位基因） | 肌肉毒性、横纹肌溶解风险↑ | 中低功能：Simvastatin ≤ 20mg/d 或换 Pravastatin/Rosuvastatin；低功能：避免 Simvastatin |
| **其他他汀** | 部分影响 Atorvastatin、Pitavastatin | 相对较弱 | 症状性肌痛时考虑检测 |

### UGT1A1

| 药物 | 关联表型 | 临床影响 | 建议 |
|---|---|---|---|
| **伊立替康（Irinotecan）** | UGT1A1\*28（TA7/TA7）纯合子 | 严重中性粒细胞减少、腹泻 | 起始剂量降低 25-50% |
| **阿扎那韦（Atazanavir）** | UGT1A1\*28 | 高胆红素血症、黄疸 | 阳性者考虑换用其他 PI |

---

## Skill 内部使用规则

### 触发时机

当用户提及以下任一药物时，静默检索本表，命中即在回答末尾附**一句** PGx 提示：

- 氯吡格雷、华法林、可待因、曲马多、卡马西平、奥卡西平、别嘌醇、辛伐他汀、他莫昔芬、Voriconazole、伊立替康、阿扎那韦、5-FU/Capecitabine、Azathioprine/6-MP、Abacavir

### 输出格式

**未提供分型时**（简要提示，不追问）：
> 【附】卡马西平的 SJS/TEN 风险与 HLA-B\*15:02 强相关（东亚、东南亚人群高频）。如未做基因分型，建议用药前完善；已知阴性可继续。

**用户提供分型时**（按表分层给方案）：
> 患者 CYP2C19 \*2/\*3（PM）→ 氯吡格雷抗血小板效应显著下降。建议改用替格瑞洛 90mg po bid（负荷 180mg）或普拉格雷 10mg po qd（负荷 60mg），按适应证与出血风险选择。以上依据 2022 CPIC 氯吡格雷指南。

### 结论前置示例

> **建议 PGx 检测后再定方案。** 卡马西平在 HLA-B\*15:02 阳性者中 SJS/TEN 风险升高逾百倍，东亚人群高频（10-15%）。若患者为汉族、泰族、马来族等高频人群，用药前必须完成 HLA-B\*15:02 检测；阴性可用，阳性者禁用，替代方案：丙戊酸、左乙拉西坦、拉莫三嗪（拉莫三嗪起始需缓慢滴定）。以上依据 2018 CPIC HLA/Carbamazepine 指南。

### 证据来源

- CPIC 指南（cpicpgx.org）
- PharmGKB 数据库（pharmgkb.org）
- FDA 药物标签 PGx 生物标志物列表
- 中国药理学会《药物基因组学临床应用专家共识（2020）》
