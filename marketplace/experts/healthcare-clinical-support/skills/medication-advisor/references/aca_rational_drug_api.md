# ACA 合理用药 API 使用指南

本指南将 `references/aca-2021-03-23/` 中的接口文档整理为 Skill 可执行工作流。详细字段定义和示例以源文档为准：

- `references/aca-2021-03-23/API 概览.md`
- `references/aca-2021-03-23/数据结构.md`
- `references/aca-2021-03-23/合理用药相关接口/*.md`

## 通用调用约定

- 使用腾讯云 API 3.0 POST JSON 调用。
- 生产域名使用 `aca.tencentcloudapi.com`；文档中的开发联调域名为 `aca.dev.tencentcloudapi.com`。
- 固定版本为 `2021-03-23`。
- 必须传入 `Region`，默认优先使用 CLI 参数，其次环境变量/配置文件，未配置时使用 `ap-guangzhou`。
- 支持通过配置文件或环境变量提供密钥；禁止把真实密钥提交到 Skill 仓库。
- 配置优先级：CLI 参数（`--region`、`--endpoint`） > 环境变量 > 配置文件 > 默认值；密钥优先级为环境变量 > 配置文件。
- 禁止在 Skill、日志、对话回复中输出 SecretId、SecretKey、Authorization 或临时 Token。
- 使用 `scripts/aca_rational_drug_client.py` 调用接口；调试请求结构时先使用 `--dry-run`。

配置文件示例（推荐放在 `~/.config/medication-advisor/aca.json`，也可通过 `ACA_CONFIG_FILE` 或 `--config` 指定）：

```json
{
  "secret_id": "your-secret-id",
  "secret_key": "your-secret-key",
  "region": "ap-guangzhou",
  "endpoint": "aca.tencentcloudapi.com",
  "token": "optional-temporary-token"
}
```

调用示例：

```bash
python scripts/aca_rational_drug_client.py MatchDrug \
  --config ~/.config/medication-advisor/aca.json \
  --payload-json '{"Drugs":[{"DrugName":"诺氟沙星片"}],"DrugType":0}'
```

## 接口选择

| 用户意图 | 优先接口 | 前置处理 | 主要使用结果 |
|---|---|---|---|
| 识别/标准化药品名、处方药品 | `MatchDrug` | 提取药品名、规格、批准文号、厂家、商品名等 | `DrugHashId`、`Similarity` |
| 识别/标准化诊断 | `MatchDiagnosis` | 提取诊断文本 | `ICDCode`、`StandardName` |
| 标准化用药频次 | `MatchFrequency` | 提取 `tid`、一日三次等频次 | `StandardCode`、`StandardName`、`DailyTimes` |
| 标准化给药途径 | `MatchRoute` | 提取口服、静滴、外用等途径 | `StandardCode`、`StandardName` |
| 查询药物相互作用/配伍禁忌 | `QueryInteractionRisk` | 先用 `MatchDrug` 获取标准药品 ID | `Interactions` 中的风险等级、影响、处理建议 |
| 查询不良反应风险 | `QueryAdverseReactionRisk` | 先用 `MatchDrug` 获取标准药品 ID | `Reactions` 中的症状和风险等级 |
| 综合审方/处方安全审核 | `ReviewRationalDrugUse` | 标准化患者、诊断、药品、频次、途径，补充过敏史和异常指标 | 9 大维度风险列表 |

## 推荐工作流

### 单药咨询

1. 识别用户问题中的药品名、规格、剂型、生产企业等信息。
2. 调用 `MatchDrug` 获取标准药品 ID；相似度低或多个候选时，先让用户确认。
3. 用户询问不良反应时，调用 `QueryAdverseReactionRisk`。
4. 用户询问用法用量、特殊人群、禁忌等且信息不足时，结合本 Skill 的追问规则补齐必要上下文；如需综合风险，走 `ReviewRationalDrugUse`。
5. 将接口结果转为患者能理解的短句，不直接贴原始 JSON。

### 多药相互作用

1. 提取所有药品名。
2. 批量调用 `MatchDrug`；仅将匹配成功且确认的 `DrugHashId` 传入风险查询。
3. 调用 `QueryInteractionRisk`。
4. 按风险等级输出：是否建议避免合用、需要监测什么、是否需要就医或咨询医生。

### 处方/附件审核

1. 使用 `scripts/parse_attachment.py` 提取患者人口学、诊断、过敏史、处方药品、频次、途径、异常检验指标。
2. 用 `MatchDiagnosis` 标准化诊断。
3. 用 `MatchDrug` 标准化药品，填充 `Prescriptions[].DrugId`。
4. 用 `MatchFrequency` 标准化频次，填充 `TimePerDayNorm` 等字段。
5. 用 `MatchRoute` 标准化给药途径，填充 `RouteNorm`、`RouteNameNorm`。
6. 构造 `ReviewRationalDrugUse` 请求并调用接口。
7. 优先向用户说明高风险项：用法用量、给药途径、重复用药、特殊人群、禁忌症、相互作用、过敏、适应症、异常提醒。

## 关键请求结构

### MatchDrug

```json
{
  "Drugs": [
    {
      "DrugName": "诺氟沙星片",
      "Specifications": "0.1g*36片/盒",
      "ApprovalNumber": "国药准字H13022772",
      "Manufacturer": "石药集团欧意药业有限公司",
      "TradeName": "诺氟沙星胶囊",
      "DrugBaseName": "86904533000738",
      "YbCode": "XA01BA04"
    }
  ],
  "DrugType": 0
}
```

注意：`Drugs` 最多 10 个；`DrugType` 为 `0` 西药、`1` 中药。

### QueryInteractionRisk

```json
{
  "DrugIds": [
    "3f8ce4e9cbc3ab786bb48f8f9ea252df1eec9e92",
    "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0"
  ]
}
```

### QueryAdverseReactionRisk

```json
{
  "DrugIds": ["3f8ce4e9cbc3ab786bb48f8f9ea252df1eec9e92"]
}
```

### ReviewRationalDrugUse

```json
{
  "Patient": {
    "Sex": "male",
    "Age": "53y",
    "Weight": "65kg"
  },
  "Diagnoses": [
    {
      "ICDCode": "J06.9",
      "DiagnosisName": "上呼吸道感染"
    }
  ],
  "Prescriptions": [
    {
      "DrugId": "3f8ce4e9cbc3ab786bb48f8f9ea252df1eec9e92",
      "DrugName": "诺氟沙星片",
      "DosagePerTime": "0.4",
      "DosagePerTimeUnit": "g",
      "TimePerDay": "一天3次",
      "TimePerDayNorm": "tid",
      "Route": "口服"
    }
  ],
  "AllergyInfo": "青霉素过敏",
  "Department": "内科"
}
```

## 响应解释规则

- `Response.Code == 0` 且业务数据存在时，使用 `Data` 生成答复。
- `Response.Code != 0`、网络失败、鉴权失败或无匹配结果时，不编造接口结论；改用通用医学知识并明确“未能完成标准库校验”。
- `Similarity` 为 `-1` 或明显偏低时，不把候选当作已确认药品。
- 高风险等级（如 `high`、`3`）优先提示并建议就医或咨询医生。
- 空列表代表未发现该维度风险，不等于绝对安全；回复仍保留“具体用药请遵医嘱”。
