---
name: student-growth-ops
description: 记录少儿英语学习情况与家长反馈（本地档案）。适用于学情记录、家长沟通、学员建档、咨询留档等场景。
---

# 少儿英语学员成长档案

## 使用场景

当用户提出以下任务时使用本 Skill：
- 咨询学生建档
- 试听测评
- 在读课后记录
- 每周跟进
- 月度学情文字总结（写入 `student-record.json` 与 `03`）
- 家长诉求与反馈（对话优先；必要时落档到 `02`）

每个学生都必须在本地拥有独立文件夹，统一存放在 `~/StudentGrowthOps/` 下。

## 本 Skill 依赖的文件

以下路径均相对于**仓库根目录**（包含 `student-growth-ops/` 的那一层），不要使用本机仓库的绝对路径去读取或打开文件。

执行前先读取这些项目内文件：
- `student-growth-ops/question-bank.json`
- `student-growth-ops/student-file-schema.json`
- `student-growth-ops/web/student-form.html`
- `student-growth-ops/server/index.js`
- `student-growth-ops/scripts/open_student_form.js`

如果需要初始化学生目录，在仓库根目录下执行（使用相对路径）：

```bash
python "student-growth-ops/scripts/scaffold_student.py" --student-name "学生名" --grade "G3" --status "leads" --start-date "2026-04-15"
```

若本机中学员服务所在目录与仓库布局不一致，可在启动服务前设置环境变量 `STUDENT_GROWTH_OPS_ROOT` 指向包含 `web/student-form.html` 的 `student-growth-ops` 目录根路径。

## 强制规则

- 第一问必须先确认学生名称。
- 在进入任何阶段前，必须先根据学生名称检查是否已有学生档案。
- 如果已有学生档案，优先进入“跟踪/更新”流程，而不是重复建档。
- 如果没有学生档案，再进入“新建档案”流程。
- 先从用户自然语言里提取已经明确的学生信息和家长诉求。
- 已经明确的信息不要重复问。
- 先问一次填写方式，不要一开始就连续提问。
- 如果走对话填写，每轮只能问 `1-2` 个问题。
- 对话问题必须来自 `student-growth-ops/question-bank.json`。
- 提问时既要给选项，也允许用户自然语言回答。
- 每确认一轮信息后就立即写入对应文件，不要等到最后一次性写入。
- 对话建档和网页建档，最终写入的学生档案文件必须完全使用同一套文件结构和字段语义。
- 不要创建额外的 Markdown 总结文档。
- 业务记录：**系统数据**为单个文件 `_data/student-record.json`（结构见 `student-file-schema.json`）；**老师可读层**为 `02-家长需求.txt`、`03-课后跟进记录.txt`。
- **给家长的沟通话术**：当用户要的是「发给家长的一段话 / 微信 / 短信 / 课堂后简短反馈」等，**在对话里直接输出完整文本即可**，语气**礼貌、温柔、有共情**；除非用户**明确**要求落档，否则不要为此覆盖 `02` 等文件。
- **回复用户时的展示规则**：
  - 不要在对话里贴出 `student-record.json` 全文；用一句「系统数据已同步更新」即可。
  - 若更新了 `02`、`03`，在收尾用**本机绝对路径**（纯文本）标出即可，不要用 Markdown 超链接或 `file://`。

## 项目集成约束

这是当前项目 `abcclaw` 的集成版本，所有路径都以项目根目录下的 `student-growth-ops/` 为准。

- 网页实现必须放在 `student-growth-ops/` 目录内
- 页面启动、表单提交、生成文本文件的逻辑，已经在项目内实现
- 实际运行时，只需要启动已有页面服务并打开页面，不要重新生成网页代码

## 学生目录规则

学生根目录：
- `~/StudentGrowthOps/Leads/`
- `~/StudentGrowthOps/Active/`
- `~/StudentGrowthOps/RenewalWatch/`
- `~/StudentGrowthOps/Archived/`

学生目录命名：
- `{grade}-{studentName}-{startDate}`
- 示例：`G3-Luna-2026-04-15`

### 正式档案：双层保存（老师可读层 + 系统数据层）

**老师可读（学员文件夹根目录）：**
- `02-家长需求.txt`：家长诉求与跟进摘要（纯文本）；即时发家长的话术默认只在对话里输出。
- `03-课后跟进记录.txt`：学习情况与课后跟进要点（纯文本，按日期追加）

**系统数据（`_data/student-record.json`）：**
- 唯一结构化存档，字段分区见 `student-growth-ops/student-file-schema.json`。课次在 `lessonLog.rows` 中追加对象。

**网页中间采集：**
- `~/.openclaw/Workspace/student-growth-ops/form-submissions/*.txt` 为网页提交后的中间文件（逐行 `字段名：内容`），需再合并进学员目录中的 `student-record.json` / `02` / `03`。

## 工作流

### 1. 识别当前阶段

把用户需求映射到以下阶段之一：
- `intake`：咨询、报名、家长需求、回访优先级
- `assessment`：试听、测评、首诊反馈
- `lesson-log`：单次课后记录
- `weekly-followup`：一周汇总、提醒、纠正
- `monthly-report`：月度学情文字总结
- `renewal-watch`：续费相关沟通（写入 `student-record.json` 内 `parentNeeds`、`tags`）

### 2. 先提取，再提问

在提问前，先从用户原话中提取已知信息，优先提取：
- `studentName`
- `grade`
- `status`
- `currentLevel`
- `primaryGoals`
- `painPoints`
- `sourceChannel`
- `parentNeeds`

不要对这些已知字段重复追问。

### 3. 先确认学生名称，再检查是否已有档案

不管用户要做建档、学情更新还是跟踪记录，第一步都先确认学生名称。

执行顺序：
1. 先从自然语言中提取学生名称。
2. 如果学生名称还不明确，先只问一个问题：
   - `请先告诉我学生姓名。`
3. 拿到学生姓名后，先去 `~/StudentGrowthOps/` 下查找是否已有对应学生目录。
4. 如果查到已有学生目录：
   - 视为已有档案
   - 后续默认进入跟踪/更新流程
   - 不要重复新建同名档案
5. 如果没有查到学生目录：
   - 视为新学生
   - 后续进入建档流程
   - 必要时先运行脚手架创建学生目录

判断原则：
- `已有目录` = 跟踪记录 / 更新资料 / 继续补充
- `没有目录` = 新建档案 / 首次采集

### 4. 再问填写方式

正式采集前，先只问这一个问题（**问的时候要把两种方式各自的优势说清楚**，方便用户选）：
- `你想通过网页填写信息，还是通过对话一步步填写？`

**选项说明（给用户看的优势）：**
- **网页填写**：更快、更精准（选项与阶段题目集中展示，一次填完、预览清晰，适合在电脑前集中录入）。
- **对话填写**：更方便（不用开浏览器，按轮回答即可；**在微信等聊天场景里也能完成**，适合碎片化时间）。

建议使用 `AskQuestion` 提供两个选项，标签或说明里可带上上述优势，例如：
- `web`：网页填写（更快、更精准）
- `chat`：对话填写（方便，微信也可以完成）

### 5. 如果用户选择网页填写

网页已经写在项目里的 `student-growth-ops/` 目录下。

运行时要求：
1. 只负责启动已有页面服务。
2. 优先使用一键启动脚本：
   - `node "student-growth-ops/scripts/open_student_form.js"`
3. 如果需要带参数启动，可以使用：
   - `node "student-growth-ops/scripts/open_student_form.js" --studentName=张三 --grade=G3 --status=active --stage=monthly-report`
4. 如需单独启动服务，也可使用：
   - `node "student-growth-ops/server/index.js"`
5. 启动后页面地址：
   - `http://127.0.0.1:8766/student-form`
6. 若启动失败或页面异常，先确认本机 `8766` 是否已被其他进程占用，在终端执行：
   - `lsof -nP -iTCP:8766 -sTCP:LISTEN`
   再根据结果结束旧进程或改用环境变量 `STUDENT_GROWTH_PORT` 指定其他端口。
7. 不要在此时重新生成网页代码。

网页必须满足这些要求：
0. 输入学生姓名后，页面应调用 `GET /api/lookup-student?name=...`（由 `student-growth-ops/server/index.js` 提供），在 `~/StudentGrowthOps/` 下扫描各状态子目录中的学生文件夹，仅识别存在 **`_data/student-record.json`** 且其中 **`studentProfile.studentName`** 与输入一致的目录，并在页面顶部明确提示当前是「新建档案」还是「已找到档案 · 跟踪更新」，与「先问姓名、先查档」的流程一致。
1. 页面字段覆盖当前阶段所需内容。
2. 页面支持下拉选项和自由输入。
3. 页面有明确的 `完成填写` 按钮。
4. 点击 `完成填写` 后立即进入 loading 状态：
   - 按钮禁用
   - 展示 `提交中...` 或 `生成中...`
   - 防止重复点击
5. 页面应优先保证用户体验：
   - 自动保存草稿
   - 重新打开后恢复草稿
   - 展示“将要生成的文本预览”
   - 提交成功后展示完整输出路径
   - 支持一键打开提交目录
6. 提交成功后，在 OpenClaw 工作空间生成一个文本文件：
   - `~/.openclaw/Workspace/student-growth-ops/form-submissions/`
7. 文件名格式：
   - `{studentName}-{timestamp}.txt`
8. 文件内容必须是逐行文本，格式示例：
   - `名字：小明`
   - `年级：G3`
   - `学校：育才小学`
   - `当前英语基础：能跟读`
   - `家长诉求：提分, 口语表达`
9. 文件中不要输出 Markdown、JSON、额外解释或无关标题。
10. 每一行都使用 `字段名：内容` 格式，供后续 AI 直接读取并**合并进正式学生档案**；不要把该 txt 当作最终存档。
11. 网页填写最终落地到学生档案时，必须和对话填写使用完全相同的文件集合：
   - 老师可读层：`02-家长需求.txt`、`03-课后跟进记录.txt`
   - 系统数据层：**`_data/student-record.json`**
12. 不允许网页填写走一套文件结构、对话填写走另一套文件结构。

网页模式下的交互规则：
1. 启动页面并告知用户页面已打开。
2. 告知用户点击 `完成填写` 后会在 OpenClaw 工作空间生成文本文件。
3. 等用户回复 `填写完成`。
4. 用户回复后，明确告诉他去这个路径找：
   - `~/.openclaw/Workspace/student-growth-ops/form-submissions/`
5. 然后读取该文本文件，再回写到学生档案文件中。

### 6. 如果用户选择对话填写

以 `student-growth-ops/question-bank.json` 作为唯一题库来源。

对话规则：
1. 每轮只问 `1-2` 个未完成字段。
2. 优先问当前阶段最关键、最缺失的字段。
3. 有稳定选项的问题优先用 `AskQuestion`。
4. 如果用户直接自然语言回答，要自动解析并映射到最接近的字段值。
5. 只有选项无法覆盖时，才补一个简短自由输入问题。
6. 每轮结束后先写入，再继续下一轮。
7. 对话填写最终落地的学生档案文件，必须和网页填写保持完全一致。

好的方式：
- 先识别出“G3、口语弱、家长想提分”
- 再只问一次填写方式
- 进入对话后每轮只问 `1-2` 个题库问题

错误方式：
- 一上来连续问完整一套问卷
- 用户已经说过的信息又被重复问一遍

### 7. 确保学生文件夹存在

如果学生文件夹不存在：
1. 根据状态选择正确的根目录。
2. 运行 `scaffold_student.py` 初始化。
3. 确认路径后再写入内容。

如果学生文件夹已存在：
1. 直接复用现有目录。
2. 原地更新文件。
3. 除非用户明确要求，不要为同一个学生重复创建新目录。

### 8. 按阶段写入正确文件

文件映射规则（系统数据均写入 **`_data/student-record.json`** 内对应键；老师可读层为根目录 `02`、`03`）：
- `intake` -> 更新 `studentProfile`、`parentNeeds`、`tags`；需要维护建档摘要时再更新 `02-家长需求.txt`（**不是**「发给家长的即时话术」的默认落点）
- `assessment` -> 更新 `learningBaseline`、`tags`
- `lesson-log` -> 向 `lessonLog.rows` **追加**一行（对象字段与 `lessonLog.columns` 一致），并在 `03-课后跟进记录.txt` 记一条可读摘要
- `weekly-followup` -> 更新 `weeklyFollowup`、`tags`，必要时更新 `03-课后跟进记录.txt`
- `monthly-report` -> 更新 `weeklyFollowup`、`tags`，并在 `03-课后跟进记录.txt` 记可读摘要
- `renewal-watch` -> 更新 `parentNeeds`、`tags`；必要时将目录转入 `RenewalWatch`

写入规则：
- 旧值只有在新信息明确覆盖时才替换
- 数组字段去重
- 标签字段保持简短、可搜索
- 日期统一用 `YYYY-MM-DD`
- 小步确认，小步写入
- 网页填写和对话填写最终都必须写入同一批文件，不允许产生分叉结构
- 如果是已有学生目录，则本次操作默认是更新已有文件，而不是重新初始化整套文件

## 对用户的反馈方式

结束时只需要简洁说明：
- **学生目录**用一句话给出**本机绝对路径**即可。
- **结构化数据**：不要贴出 `student-record.json` 全文；用「系统数据已更新」之类概括即可。
- **`02`、`03`**：若本次有更新，**直接写出本机绝对路径**（纯文本），不要用 Markdown 超链接或 `file://`。
- 如果是网页填写，中间采集目录写出 **`~/.openclaw/Workspace/student-growth-ops/form-submissions/`** 展开后的**本机绝对路径**（纯文本）。
- 若本次交付主要是**家长沟通话术**，说明话术已在对话中给出即可，**不必**强调写入了某个 txt 文件。
