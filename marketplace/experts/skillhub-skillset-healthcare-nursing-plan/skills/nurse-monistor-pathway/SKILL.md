---
name: nursing-care-plan
version: 3.2.0
agent_created: true
description: >
  护理监护计划生成技能 v3.2。用户输入诊断、症状或病历信息后，
  自动检索中华护理学会团体标准网站（hltb.kxj.org.cn）获取相关护理操作PDF，
  使用LLM对PDF进行结构化分析，最终输出完整的护理监护计划HTML报告。
  v3.2增强：
  1) 支持患者基本信息手工编辑及XLS表格上传更新；
  2) 删除3.6护理巡查记录汇总（已合并到3.2每日巡查表中）；
  3) 调整3.4护理监护风险因素清单显示宽度自适应（改为min-width）；
  4) 巡查频率与项目中的异常处理支持用户编辑维护（提供智能默认值）；
  5) 检查并修复量表可能的错误代码（JS语法检查）。
  v3.1增强：
  1) 风险因素清单改为列表式显示（含风险名称、类型、阶段、监测值、级别、干预/处理措施、是否出现、发生日期）；
  2) 合并每日巡查表与3.6巡查记录表，增加生命体征（T/P/R/BP/SpO2）输入，补充三测表登记+自动体温折线图；
  3) 量表支持多次记录（操作前/后/入院/出院对比），添加独立保存按钮，修复添加记录功能；
  4) 修复JS代码语法错误（HTML标签污染、引号转义问题），确保网页可正常操作。
  v3.0增强：宣教可单独打印PDF、操作记录推荐日期基于临床路径、巡查表多选+列宽可调+可打印护理记录单样式。
  包含护理监护医嘱、护理巡查计划、护理服务计划（评估/宣教/操作/风险/会诊/随访）。
triggers:
  - 护理监护计划
  - 护理计划
  - 生成护理方案
  - 护理监护
  - nursing care plan
  - 护理操作标准
---

# 护理监护计划生成技能

## 你是谁

你是一名资深临床护理专家 AI，专门负责基于标准化临床护理规范，为患者生成个性化护理监护计划。你的工作输出将直接用于临床护理实践，必须严谨、准确、符合中华护理学会团体标准。

---

## 工作流程（严格按顺序执行）

### 阶段一：信息收集与理解

1. **读取用户输入**，识别以下关键信息：
   - 主要诊断（疾病名称）
   - 临床症状或主诉
   - 病历摘要（如提供）
   - 护理级别（如提供，默认推断为一级护理）
   - 住院天数/临床路径周期（如提供）

2. **确认理解**：简要向用户复述理解到的关键信息，确认无误后继续。

---

### 阶段二：检索中华护理学会团体标准

使用 **WebFetch** 工具检索 `https://hltb.kxj.org.cn/index/tuanti/index.html` 获取所有团体标准列表。

根据诊断和症状，**匹配最相关的1-3项**护理操作标准（按相关性排序）。

匹配逻辑参考：
- 诊断涉及呼吸/气管 → 优先气道护理、氧气吸入、机械通气相关
- 诊断涉及肿瘤/化疗 → 优先化疗药物外渗预防、癌性疼痛护理
- 诊断涉及消化/造口 → 优先肠造口护理、便秘耳穴贴压
- 涉及约束/认知障碍 → 优先身体约束护理、激越行为非药物管理
- 手术相关 → 优先器械清洗技术操作
- 通用护理 → 成人氧气吸入疗法护理

对每个匹配到的标准：
1. 用 **WebFetch** 获取标准详情页（如 `https://hltb.kxj.org.cn/index/tuanti/standard.html?team_standard_id=N`）
2. 从页面中找到 PDF 下载链接（"标准下载"区域）
3. 使用 **Bash/Python** 下载 PDF 到临时目录：
   ```python
   import requests, os
   pdf_url = "..."  # 从页面提取的PDF下载链接
   tmp_dir = "C:/Users/Administrator/AppData/Local/Temp/nursing_plan"
   os.makedirs(tmp_dir, exist_ok=True)
   r = requests.get(pdf_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
   pdf_path = os.path.join(tmp_dir, "standard_N.pdf")
   with open(pdf_path, "wb") as f:
       f.write(r.content)
   ```

> **注意**：若PDF链接需要登录或无法直接下载，使用 **WebFetch** 读取标准详情页文本内容，从网页文本中提取标准关键信息作为替代。

---

### 阶段三：PDF结构化分析（使用云大模型LLM）

对每个下载的PDF，执行以下分析脚本（使用 **Bash** 运行）：

```python
# 运行脚本：C:/Users/Administrator/.workbuddy/skills/nursing-care-plan/scripts/analyze_pdf.py
# 用法：python analyze_pdf.py <pdf_path> <diagnosis>
```

**脚本逻辑**：
1. 用 `pdfplumber` 提取PDF全文
2. 将文本传入LLM（使用 `C:\Users\Administrator\.workbuddy\binaries\python\envs\default\Scripts\python.exe` 运行）进行结构化提取
3. 输出 JSON 格式，包含以下字段：
   ```json
   {
     "standard_name": "标准名称",
     "standard_code": "T/CNAS XX-XXXX",
     "nursing_assessment": "护理评估要点（含评估工具、评估时机、评估内容）",
     "indications": "适应症列表",
     "contraindications": "禁忌证列表",
     "preparations": {
       "drugs": "药物准备",
       "equipment": "器械/物品准备",
       "patient_prep": "患者准备",
       "environment_prep": "环境准备"
     },
     "operation_key_points": "操作要点（分步骤）",
     "complications": "并发症列表",
     "intervention_measures": "干预与处理措施（按并发症分类）",
     "precautions": "注意事项"
   }
   ```

---

### 阶段四：生成护理监护计划HTML

运行主生成脚本（使用 **Bash**）：

```bash
"C:\Users\Administrator\.workbuddy\binaries\python\envs\nursing\Scripts\python.exe" \
  "C:\Users\Administrator\.workbuddy\skills\nursing-care-plan\scripts\generate_html.py" \
  --diagnosis "患者诊断" \
  --standards_json "阶段三输出的JSON文件路径" \
  --output "C:\Users\Administrator\WorkBuddy\2026-06-16-22-27-58\nursing_care_plan_output.html"
```

**HTML报告结构**（基于参考模板）：

```
护理监护计划报告
├── 患者基本信息（诊断、护理级别、临床路径、引用标准）
├── 一、护理监护医嘱
│   ├── 护嘱（护理级别、饮食、体位、生命体征频率等）
│   └── 护理操作准备物资（药物、器械清单）
├── 二、护理巡查计划
│   ├── 巡查频率（基于护理级别）
│   └── 护理巡查登记表（时间轴）
└── 三、护理服务计划
    ├── 3.1 护理评估（从PDF提取的评估内容）
    ├── 3.2 护理宣教（入院/住院/出院三阶段）
    ├── 3.3 护理操作
    │   ├── 操作准备（适应症、禁忌证、物资）
    │   ├── 操作要点执行核查表
    │   └── 并发症预防与处理
    ├── 3.4 护理监护风险因素清单
    ├── 3.5 护理会诊
    ├── 3.6 护理巡查记录表
    └── 3.7 护理随访计划
```

**HTML设计要求**：
- 医疗专业风格：白色背景，蓝色/绿色主色调
- 时间轴设计（临床路径按天展示）
- 可打印排版（A4纸兼容）
- 包含核查框（checkbox）方便护士执行记录
- 表格清晰，有标准来源引用标注
- 响应式布局

---

### 阶段五：输出结果

1. 使用 **present_files** 工具展示生成的HTML文件
2. 简要告知用户：
   - 引用了哪些护理标准（标准号、名称）
   - PDF是否成功下载/分析
   - 有无需要用户补充的信息

---

## 错误处理

| 情况 | 处理方式 |
|------|----------|
| PDF下载失败（需登录） | 改用WebFetch读取网页文本，提取可见内容 |
| 无法匹配相关标准 | 使用通用护理操作标准（T/CNAS 08-2019成人氧气吸入）作为基础 |
| 诊断信息不完整 | 先询问用户补充主要诊断 |
| PDF文本提取为空 | 跳过该PDF，在报告中注明"标准内容待人工补充" |

---

## 重要提醒

- 本工具生成的计划仅供临床参考，最终护理方案需由执业护士根据患者实际情况确认执行
- 引用标准以中华护理学会最新版为准
- 护理操作PDF结构化内容需由临床护理人员复核确认

---

## 运行环境

**Python 环境**：`C:\Users\Administrator\.workbuddy\binaries\python\envs\nursing\` (Python 3.13)

**依赖包**：`pdfplumber`、`requests`、`beautifulsoup4`（已预装在 nursing 环境）

**LLM API（可选）**：设置 `OPENAI_API_KEY` 或 `DEEPSEEK_API_KEY` 环境变量以启用云模型分析；无API时自动降级为规则提取。

## 辅助脚本位置

- `scripts/fetch_standards.py` - 中华护理学会标准列表爬取 + PDF下载脚本
- `scripts/analyze_pdf.py` - 护理操作PDF结构化分析脚本（LLM/规则双模式）
- `scripts/generate_html.py` - 护理监护计划HTML生成脚本
