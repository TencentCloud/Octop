---
name: newmedia-operations
description: |
  全链路新媒体运营技能，覆盖从行业分析→竞品分析→账号养号→爆款内容创作→互动钩子设计的完整运营闭环。结合 opencli（浏览器直操控）、ima知识库、联网搜索、违禁词检测等能力，适用于抖音、视频号、小红书三大平台的品牌账号运营。
  
  触发场景：
  - 用户说"帮我做新媒体运营方案"
  - 用户说"分析竞品账号"
  - 用户说"帮我养号" / "账号冷启动"
  - 用户说"帮我写爆款内容" / "二次创作"
  - 用户说"设计互动钩子" / "提升评论互动"
  - 用户说"做行业分析报告"
  - 用户说"监控对标账号"
  - 用户提供了品牌/产品 PPT，要求制定内容运营策略
---

# 全链路新媒体运营

## 🚀 初始化检查（每次启动必做）

检查以下两个工具是否已安装，二者均为可选但强烈推荐。

### 检查 opencli

检查系统中是否能执行 `opencli list`。

**若未安装**，提示用户：
```
检测到 opencli 尚未安装。opencli 可直接复用浏览器登录态操控抖音、小红书、微博、知乎等平台，是最高效的数据获取方式。

📦 安装方式：
请安装这个仓库技能：https://github.com/jackwener/opencli

安装完成后执行 `opencli list` 验证，然后告诉我，继续运营流程。
（可跳过，跳过后将使用内置脚本 + WebSearch 替代）
```

**若已安装**，执行 `opencli list` 确认可用命令，记录哪些平台有登录态（用于后续步骤自动选择最优方式）。

### 检查 ima-skill

检查 `~/.cursor/skills/` 目录下是否存在 `ima-skill`。

**若未安装**，提示用户：
```
检测到 ima 知识库技能尚未安装。ima-skill 可检索历史积累数据、沉淀运营成果。

📦 安装：下载地址 https://app-dl.ima.qq.com/skills/ima-skills-1.1.2.zip
🔑 API Key：https://ima.qq.com/agent-interface → 「API Key 管理」

安装完成后告诉我，引导配置后继续。（可跳过）
```

**若已安装**，首次使用时确认 API Key 已配置、「新媒体运营」分类已创建。

详细说明见 [IMA_KNOWLEDGE.md](references/IMA_KNOWLEDGE.md) | [OPENCLI.md](references/OPENCLI.md)

---

## 数据获取策略（全局）

每个需要抓取数据的步骤，按以下优先级选择方式，或直接询问用户偏好：

```
① ima 知识库     → 有历史数据时优先复用，避免重复抓取
② opencli        → 有浏览器登录态时使用，实时且准确
③ 内置 Python 脚本 → 需要批量处理/数据清洗时使用
④ WebSearch/WebFetch → 兜底，覆盖公开内容
```

---

## 内置脚本（scripts/ 目录）

```
scripts/
├── fetch_xiaohongshu.py / fetch_douyin.py / fetch_weibo.py
├── fetch_wechat_video.py / fetch_ecommerce_reviews.py
├── clean_data.py / extract_demands.py
├── analyze_industry.py    # 行业大盘分析
├── monitor_competitors.py # 竞品实时监测
├── detect_forbidden_words.py / generate_hook_templates.py
```

---

## 工作流程总览

```
[初始化] 检查 opencli → 检查 ima-skill → 确认数据获取策略
    ↓
Step 1: 行业分析  →  Step 2: 竞品分析  →  Step 3: 账号养号
                                                  ↓
                    Step 5: 互动钩子设计  ←  Step 4: 爆款内容创作

每步均包含：① ima检索 → ② 执行任务（opencli/脚本/搜索任选）→ ③ ima沉淀
```

---

## Step 1：行业分析

详细指南：[INDUSTRY_ANALYSIS.md](references/INDUSTRY_ANALYSIS.md)

### 【知识库检索】开始前
```
ima 搜索：「[行业名] 分析报告」「[行业名] 用户画像」「[行业名] 关键词」
```
有历史报告 → 增量更新；无内容 → 执行完整分析。

### 核心任务
1. 读取客户 PPT/资料，识别核心诉求（涨粉/引流/转化/品牌曝光）
2. 了解现有账号状态（抖音/视频号/小红书基础、历史内容方向）
3. 调研行业大盘数据

### 数据获取方式（任选）

| 来源 | opencli 命令 | 脚本/其他 |
|------|-------------|-----------|
| 小红书行业内容 | `opencli xiaohongshu search "[行业词]"` | `python scripts/fetch_xiaohongshu.py` |
| 抖音行业内容 | `opencli douyin videos --keyword "[行业词]"` | `python scripts/fetch_douyin.py` |
| 微博热搜/舆情 | `opencli weibo hot` / `opencli weibo search "[词]"` | `python scripts/fetch_weibo.py` |
| 知乎行业讨论 | `opencli zhihu hot` / `opencli zhihu search "[词]"` | WebSearch |
| 36氪行业资讯 | `opencli 36kr hot` / `opencli 36kr news` | WebFetch |
| B站行业视频 | `opencli bilibili hot` / `opencli bilibili ranking` | WebFetch |
| 艾媒行业报告 | — | WebFetch `https://www.iiimedia.cn/` |
| 5118关键词 | `opencli google trends "[词]"` | WebSearch |

**关键词体系**：主关键词 → 核心关键词 → 产品关键词 → 用户痛点关键词

**输出**：[templates/industry_report.md](templates/industry_report.md)

### 【知识沉淀】完成后询问
```
行业分析完成。是否保存到 ima？
A. 新笔记「[行业名]-行业分析报告-[日期]」  B. 追加到已有  C. 暂不保存
```

---

## Step 2：竞品分析

详细指南：[COMPETITOR_ANALYSIS.md](references/COMPETITOR_ANALYSIS.md)

### 【知识库检索】开始前
```
ima 搜索：「[竞品名] 账号分析」「[行业] 爆款拆解」「[行业] 竞品对比」
```
有历史数据 → 与当前数据对比趋势变化。

### 数据获取方式（任选）

| 来源 | opencli 命令 | 脚本/其他 |
|------|-------------|-----------|
| 小红书竞品账号 | `opencli xiaohongshu user "[账号]"` / `opencli xiaohongshu creator-notes` | `python scripts/fetch_xiaohongshu.py` |
| 小红书笔记数据 | `opencli xiaohongshu creator-notes-summary` | — |
| 抖音竞品账号 | `opencli douyin profile` / `opencli douyin stats` | `python scripts/fetch_douyin.py` |
| 抖音视频列表 | `opencli douyin videos` | — |
| 微博竞品内容 | `opencli weibo search "[竞品名]"` | `python scripts/fetch_weibo.py` |
| 京东商品评价 | `opencli jd item "[产品名]"` | `python scripts/fetch_ecommerce_reviews.py` |
| 闲鱼/什么值得买 | `opencli xianyu search "[产品]"` / `opencli smzdm search "[产品]"` | WebSearch |

**分析维度**：账号基础 / 内容策略 / 用户互动 / 更新频率 / 电商数据

**实时监测**：`python scripts/monitor_competitors.py --accounts templates/accounts_config.json`

### 【知识沉淀】完成后询问
```
竞品分析完成。是否保存到 ima？
A. 新笔记「[行业]-竞品分析-[日期]」  B. 追加到「[竞品名] 账号分析」  C. 暂不保存
```

---

## Step 3：账号养号

详细指南：[ACCOUNT_NURTURING.md](references/ACCOUNT_NURTURING.md)

### 【知识库检索】开始前
```
ima 搜索：「养号策略」「[平台] 冷启动」「账号运营技巧」
```

### 资料完善清单
- [ ] 实名认证 / [ ] 昵称（品牌+品类+关键词）/ [ ] 头像（高清）
- [ ] 简介（价值定位+核心服务+合规引导）/ [ ] 行业标签

### 每日养号行为（可用 opencli 辅助）

| 行为 | 数量 | opencli 辅助 |
|------|------|-------------|
| 搜索核心关键词 | 每日 | `opencli xiaohongshu search "[关键词]"` |
| 浏览行业内容 | 完播≥80% | `opencli xiaohongshu feed` / `opencli douyin videos` |
| 查看互动通知 | 每日 | `opencli xiaohongshu notifications` |
| 了解平台活动 | 每日 | `opencli douyin activities` |
| 关注对标账号 | 5-10个 | 参考 Step 2 找到的竞品账号 |

### 【知识沉淀】完成后询问
```
账号设置方案完成。是否保存到 ima？
A. 新笔记「[品牌名]-账号设置建议-[日期]」  B. 暂不保存
```

---

## Step 4：爆款内容创作

详细指南：[VIRAL_CONTENT.md](references/VIRAL_CONTENT.md)

### 【知识库检索】开始前
```
ima 搜索：「[行业] 爆款标题」「违禁词库」「内容日历模板」
```
有历史标题库 → 直接复用拓展；有违禁词记录 → 合并使用。

### 内容生产流程

1. **热点选题**（opencli 每日热点组合）：
   ```bash
   opencli weibo hot && opencli zhihu hot && opencli 36kr hot && opencli bilibili hot
   opencli douyin hashtag "[行业标签]"
   ```

2. **爆款参考**：
   ```bash
   opencli xiaohongshu search "[关键词]"        # 小红书热门笔记
   opencli bilibili ranking                      # B站热门视频
   opencli zhihu search "[行业痛点]"             # 知乎高赞内容
   ```
   或：WebFetch `https://www.yizhuan5.com/` / WebSearch `[关键词] site:weixin.qq.com`

3. **违禁词检测**：
   ```bash
   python scripts/detect_forbidden_words.py --text "[内容]" --platform [平台]
   ```

4. **二次创作**：保留逻辑/替换案例，结合客户产品定制，加入品牌专属卖点

5. **内容发布**（opencli 直发）：
   ```bash
   opencli douyin publish    # 发布抖音视频
   opencli douyin drafts     # 查看草稿
   opencli xiaohongshu publish  # 发布小红书笔记
   ```

**内容类型矩阵**：

| 类型 | 标题公式 | 发布账号 |
|------|----------|----------|
| 品牌宣传 | 品牌名 + 核心价值 + 场景 | 大号（360浏览器） |
| 产品种草 | 痛点 + 解决方案 + 效果 | 小号1（QQ浏览器） |
| 科普知识 | 问题 + 答案 + 干货 | 小号2（谷歌浏览器） |
| 招商文章 | 机会 + 数据 + 行动号召 | 大号 |

### 【知识沉淀】完成后询问
```
内容创作计划完成。建议保存：
① 爆款标题库 → 追加到「[行业]-爆款标题库」
② 30天内容日历 → 新笔记「[品牌]-内容日历-[月份]」
③ 违禁词新增条目 → 追加到「通用-违禁词库」
选择保存项（A/B/C/D不保存）：
```

---

## Step 5：互动钩子设计

详细指南：[ENGAGEMENT_HOOKS.md](references/ENGAGEMENT_HOOKS.md)

### 【知识库检索】开始前
```
ima 搜索：「互动话术」「评论钩子」「私域引导」「用户唤醒」
```
有历史话术库 → 直接调取并结合本次行业定制。

### 数据支撑（用 opencli 收集互动数据）

```bash
# 查看自己账号互动情况，分析哪类内容评论率高
opencli xiaohongshu notifications          # 小红书互动通知
opencli xiaohongshu creator-notes-summary  # 笔记数据汇总
opencli douyin stats                       # 抖音各视频互动对比

# 研究竞品评论区用户声音
opencli xiaohongshu creator-note-detail [note_id]
opencli zhihu question [id]               # 收集用户真实提问
```

### 生成定制话术
```bash
python scripts/generate_hook_templates.py \
  --industry "[行业]" --brand "[品牌]" \
  --pain_point "[核心痛点]" --resource "[资料名]" \
  --output data/hooks_[品牌名].md
```

**私域引导**：欢迎语 + 7天未互动用户唤醒 + 强意向识别转人工

### 【知识沉淀】完成后询问
```
互动话术库完成。是否保存到 ima？
A. 新笔记「[品牌/行业]-互动话术库-[日期]」
B. 追加到「通用-互动话术模板库」
C. 暂不保存
```

---

## 输出报告结构

```
运营方案报告/
├── 01_行业分析报告.md
├── 02_竞品分析报告.md
├── 03_账号设置建议.md
├── 04_内容创作计划.md（含30天日历）
└── 05_互动话术库.md
```

完成后询问：是否将整套方案导入 ima 知识库的「[品牌名] 运营档案」？

---

## 参考资料

- [OPENCLI.md](references/OPENCLI.md) - opencli 安装与各步命令速查表
- [IMA_KNOWLEDGE.md](references/IMA_KNOWLEDGE.md) - ima知识库集成指南
- [INDUSTRY_ANALYSIS.md](references/INDUSTRY_ANALYSIS.md) - 行业分析完整指南
- [COMPETITOR_ANALYSIS.md](references/COMPETITOR_ANALYSIS.md) - 竞品分析框架
- [ACCOUNT_NURTURING.md](references/ACCOUNT_NURTURING.md) - 账号养号操作手册
- [VIRAL_CONTENT.md](references/VIRAL_CONTENT.md) - 爆款内容创作指南
- [ENGAGEMENT_HOOKS.md](references/ENGAGEMENT_HOOKS.md) - 互动钩子设计与话术库
