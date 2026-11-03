---
name: med-medical-term-normalization
description: 将口语化通用医学记录转换为标准化、规范化的医学记录。输入口语化病历文本，调用内部医疗大模型，输出符合临床病历书写规范的标准化记录（术语规范、表述严谨、数据规范、结构规范）。
metadata:
  {
    "openclaw":
      {
        "emoji": "📝"
      }
  }
---

# 医学术语规范化

概述
----
根据患者提供的**口语化通用医学记录**（涵盖门诊、住院日常场景），本技能调用内部医疗大模型将其转换为**标准化、规范化的医学记录**。

医学术语规范化是提升病历质量、确保信息准确传递的重要环节，适用于病历归档、质控审核、医保结算、科研数据统计等场景。转换后需符合临床病历书写规范，术语准确，表述严谨。

数据安全、隐私与伦理声明
------------------------
- **最小必要原则**：仅处理术语规范化所需的病历内容；不要求也不鼓励包含姓名、证件号、手机号、详细地址等身份信息。
- **严格脱敏**：在发送至任何模型/接口前，请确保病历已完成脱敏/去标识化处理。
- **不做本地持久化**：不将输入与中间结果写入本地持久化存储；**本次调用结束即销毁**。
- **医疗边界**：本技能用于医学记录规范化表达的辅助处理，不构成医疗诊断或治疗建议；请由执业医生复核并承担最终医疗责任。

输入格式
--------
统一入口支持 `pdf/doc/docx/xls/xlsx/csv/txt/json`。JSON 可包含结构化病历字段；普通病历文件会先预处理为文本。

### JSON 输入示例

```json
{
  "records": [
    {
      "section": "患者基本情况",
      "content": "男，62 岁，今天早上来门诊看病，说自己最近一周老是觉得胸口闷..."
    },
    {
      "section": "主诉",
      "content": "最近一周胸口发闷、喘气费劲，偶尔咳嗽、有白痰..."
    },
    {
      "section": "现病史",
      "content": "患者一周前没什么原因就开始胸口闷，活动之后更厉害..."
    }
  ]
}
```

也支持直接传入完整 prompt：

```json
{
  "prompt": "请你作为医学术语规范化专家，将提供的口语化通用医学记录转换为标准化、规范化的医学记录...\n\n待规范化医学记录：\n1.  患者基本情况：男，62 岁...\n"
}
```

### 普通文本输入

对于 TXT/PDF/DOC 等格式的口语化病历文件，文件内容会被预处理为纯文本，然后通过命令行参数传入。

快速开始
--------

```bash
python doctor/emr-gen/medical-term-normalization/scripts/run.py \
  --input data/med-medical-term-normalization/gen_records.json \
  --appkey <your-appkey>
```

参数说明
--------
- `--input PATH`：**必填**。输入 JSON 文件或病历文本文件路径。
- `--input-type auto|pdf|doc|docx|xls|xlsx|csv|txt|json`：输入类型，默认 `auto`。
- `--sheet STRING`：读取 Excel 时指定 sheet（可选）。
- `--encoding STRING`：`txt/csv` 编码，默认 `utf-8`。
- `--base URL`：内部大模型 base URL，默认 `https://maas-api.hivoice.cn/v1`。
- `--model STRING`：模型名称，默认 `u2-med`。
- `--timeout SECONDS`：HTTP 超时秒数；`0` 表示一直等待，默认 `0`。
- `--appkey STRING`：**必填**。内部医疗大模型鉴权 key，使用 Bearer 方式认证。
- `--output-json PATH`：可选。保存输出 JSON。
- `--output PATH`：可选。输出规范化记录文本文件路径。
- `--save-prepared`：可选。保存预处理后的文本，便于调试。

输出约定
--------
- 输出为 UTF-8 文本，符合 6 个标准模块规范：

```
医学记录（规范化版）
1.  患者基本情况：男性，62 岁，门诊就诊，主诉胸闷、气短伴偶发咳嗽、少量白痰 1 周，既往高血压病史 8 年，长期规律口服降压药物，血压控制可。
2.  主诉：胸闷、气短 1 周，伴偶发咳嗽、少量白痰，无发热、腹痛、腹泻。
3.  现病史：患者 1 周前无明显诱因出现胸闷，活动后加重，休息后可缓解，偶发咳嗽，咳少量白痰，无发热、畏寒，无恶心、呕吐，无腹泻，食欲可，睡眠一般。既往高血压病史 8 年，长期规律口服降压药物，血压控制尚可，否认糖尿病、冠心病等病史。
4.  体格检查：体温 36.8℃，脉搏 76 次/分，呼吸 18 次/分，血压 138/88mmHg；双肺呼吸音粗，可闻及少量湿性啰音；心率齐，各瓣膜听诊区未闻及病理性杂音；腹平软，无压痛、反跳痛；神志清楚，一般情况可。
5.  辅助检查：胸部 CT 示肺部炎症；心电图未见明显异常。
6.  处理建议：1.  给予抗生素口服，每次 1 片，每日 2 次，疗程 5 天；2.  继续规律口服原有降压药物，不可擅自停药；3.  嘱患者多饮水，避免熬夜、受凉；4.  1 周后门诊复诊，若出现胸闷加重、发热等不适，立即就诊。
```

- 若输出路径父目录不存在，会自动创建。

核心规范化要求
--------
1. **术语规范**：口语化表述替换为标准医学术语（"肚子"→"腹部"、"发烧"→"发热"、"拉肚子"→"腹泻"）
2. **表述严谨**：删除口语化语气词、冗余表述，调整为规范的医学书面句式
3. **数据规范**：生命体征、检查结果、时间、剂量等数据格式统一规范
4. **结构规范**：保留原始记录的核心模块顺序，每个模块表述规范、简洁

依赖
----
### 前置 Skill
`scripts/run.py` 依赖 **`_shared/doc-preprocess`** 提供的公共文件预处理库（`preprocess.py`）。
请确保 `_shared/doc-preprocess/` 位于 `skills/` 根目录下。

### 运行环境
- Python 3.7+

### 外部 API
- 内部医疗大模型：`https://maas-api.hivoice.cn/v1/chat/completions`
  - 方法：POST，OpenAI 兼容格式
  - 需要传入 `--appkey` 参数进行 Bearer 认证

### Python 第三方包（可选，run.py 使用非 txt/json 输入时需要）
| 包名 | 用途 | 必要条件 |
|------|------|---------|
| `openpyxl` | 读取 `.xlsx` 文件 | 输入为 xlsx 时必须 |
| `pypdf` | 提取 PDF 文本 | 输入为 pdf 时必须 |

安装：`pip install openpyxl pypdf`

> 仅使用 TXT/JSON 输入时，无需安装任何额外包。

测试命令
--------
从 `skills` 根目录执行：

```bash
# 离线自测（检查输入和构造请求）
python self_tests/med-medical-term-normalization/self_test_medical_term_normalization.py

# 在线自测（调用内部接口）
python self_tests/med-medical-term-normalization/self_test_medical_term_normalization.py --run-network
```

备注
----
- `scripts/run.py` 是唯一对外入口。
- 示例输入放在 `example/gen_records.json`。
