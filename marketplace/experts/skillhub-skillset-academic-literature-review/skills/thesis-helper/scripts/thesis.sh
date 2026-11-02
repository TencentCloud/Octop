#!/usr/bin/env bash
# thesis.sh — 论文工具（真实生成版）
# Usage: bash thesis.sh <command> [args...]
# Commands: outline, cite, abstract, format, defense, checklist
set -euo pipefail

CMD="${1:-help}"
shift 2>/dev/null || true
INPUT="$*"

# ── 论文大纲生成 ──
generate_outline() {
  local title="${1:-研究题目}"
  local level="${2:-本科}"
  local field="${3:-计算机科学}"

  echo "# 📑 论文大纲 — ${title}"
  echo ""
  echo "> 层次: ${level}"
  echo "> 学科: ${field}"
  echo "> 生成时间: $(date '+%Y-%m-%d %H:%M')"
  echo ""

  # 根据层次调整大纲深度
  local word_target pages_target ref_count
  case "$level" in
    本科|bachelor)
      word_target="10000-15000"
      pages_target="30-50"
      ref_count="30+"
      ;;
    硕士|master)
      word_target="30000-50000"
      pages_target="60-100"
      ref_count="60+"
      ;;
    博士|phd)
      word_target="80000-100000"
      pages_target="150-300"
      ref_count="100+"
      ;;
    *)
      word_target="8000-15000"
      pages_target="20-40"
      ref_count="20+"
      ;;
  esac

  cat <<EOF
## 论文基本信息

| 项目 | 要求 |
|------|------|
| 题目 | ${title} |
| 层次 | ${level} |
| 学科 | ${field} |
| 字数要求 | ${word_target}字 |
| 页数参考 | ${pages_target}页 |
| 参考文献 | ≥${ref_count}篇 |

## 论文结构

### 前置部分
- [ ] 封面（题目、姓名、导师、日期）
- [ ] 诚信声明
- [ ] 摘要（中文，300-500字）
- [ ] Abstract（英文摘要）
- [ ] 关键词 / Keywords（3-5个）
- [ ] 目录
- [ ] 图表目录（如有）

### 第一章 绪论 (约${level}级: $([ "$level" = "本科" ] && echo "2000" || echo "5000")字)

#### 1.1 研究背景
- 宏观背景：${field}领域的发展现状
- 行业/社会需求：为什么这个问题重要
- 现有不足：当前方案的局限性

#### 1.2 研究目的与意义
- 理论意义：填补什么理论空白
- 实践意义：解决什么实际问题
- 创新点（2-3个）：
  1. [方法创新/模型创新]
  2. [应用创新/场景创新]
  3. [视角创新/跨学科创新]

#### 1.3 国内外研究现状
- 国外研究：按时间/流派梳理
- 国内研究：按时间/方向梳理
- 研究述评：总结现有研究的不足

#### 1.4 研究内容与方法
- 研究内容：本文要做什么（分章概述）
- 研究方法：
  - [ ] 文献分析法
  - [ ] 实验法
  - [ ] 问卷调查法
  - [ ] 案例研究法
  - [ ] 对比分析法
  - [ ] 定量/定性分析

#### 1.5 论文组织结构
- 技术路线图（建议画流程图）

### 第二章 相关理论与技术基础 (约$([ "$level" = "本科" ] && echo "2000" || echo "4000")字)

#### 2.1 核心概念定义
- 概念A的定义与演变
- 概念B的定义与界定

#### 2.2 理论基础
- 理论1：[名称]——核心观点与适用性
- 理论2：[名称]——核心观点与适用性

#### 2.3 技术基础
- 技术/方法1：原理与特点
- 技术/方法2：原理与特点

#### 2.4 本章小结

### 第三章 [方案设计/模型构建/方法论] (核心章节1)

#### 3.1 总体设计/整体框架
- 设计思路
- 架构图

#### 3.2 [模块/方法]详细设计
- 3.2.1 [子模块1]
- 3.2.2 [子模块2]
- 3.2.3 [子模块3]

#### 3.3 关键技术/算法
- 算法描述（伪代码/流程图）
- 复杂度分析

#### 3.4 本章小结

### 第四章 [实验/实现/案例分析] (核心章节2)

#### 4.1 实验环境/研究设计
- 硬件/软件环境
- 数据集/样本说明
- 评估指标

#### 4.2 实验过程/实现过程
- 步骤1
- 步骤2
- 步骤3

#### 4.3 结果与分析
- 结果展示（表格+图表）
- 对比分析
- 显著性检验（如适用）

#### 4.4 讨论
- 结果解释
- 与现有方法的对比
- 局限性说明

#### 4.5 本章小结

### 第五章 总结与展望 (约$([ "$level" = "本科" ] && echo "1000" || echo "2000")字)

#### 5.1 研究总结
- 主要工作回顾（3-5条）
- 创新点总结

#### 5.2 研究不足
- 客观承认局限（2-3点）

#### 5.3 未来展望
- 短期改进方向
- 长期研究方向

### 后置部分
- [ ] 参考文献（${ref_count}篇以上）
- [ ] 附录（代码/问卷/详细数据）
- [ ] 致谢

---

## 📊 章节字数分配

| 章节 | 占比 | 字数估算 |
|------|------|---------|
| 第一章 绪论 | 15-20% | - |
| 第二章 基础 | 15% | - |
| 第三章 设计 | 25-30% | - |
| 第四章 实验 | 25-30% | - |
| 第五章 总结 | 5-10% | - |
EOF
}

# ── 参考文献格式 ──
generate_citation() {
  local style="${1:-gb}"
  local type="${2:-all}"

  echo "# 📚 参考文献格式模板"
  echo ""
  echo "> 格式标准: ${style^^}"
  echo "> 生成时间: $(date '+%Y-%m-%d %H:%M')"
  echo ""

  case "$style" in
    gb|gbt7714|国标)
      cat <<'EOF'
## GB/T 7714-2015 格式（中国国标）

### 期刊论文 [J]
```
[序号] 作者1, 作者2, 作者3, 等. 文章题目[J]. 期刊名, 年, 卷(期): 起始页-结束页.
```
示例:
```
[1] 张三, 李四. 深度学习在自然语言处理中的应用研究[J]. 计算机学报, 2024, 47(3): 621-635.
[2] SMITH J, JOHNSON A B. Deep learning for NLP: A survey[J]. Nature Machine Intelligence, 2023, 5(2): 108-120.
```

### 学位论文 [D]
```
[序号] 作者. 题名[D]. 城市: 学校名, 年.
```
示例:
```
[3] 王五. 基于Transformer的文本分类方法研究[D]. 北京: 清华大学, 2024.
```

### 专著/图书 [M]
```
[序号] 作者. 书名[M]. 版次. 出版地: 出版社, 年: 页码.
```
示例:
```
[4] GOODFELLOW I, BENGIO Y, COURVILLE A. Deep Learning[M]. Cambridge: MIT Press, 2016: 326-366.
[5] 周志华. 机器学习[M]. 北京: 清华大学出版社, 2016.
```

### 会议论文 [C]
```
[序号] 作者. 题名[C]// 会议名. 城市: 出版者, 年: 页码.
```
示例:
```
[6] VASWANI A, SHAZEER N, PARMAR N, et al. Attention is all you need[C]// Proc. of NeurIPS 2017. Long Beach: Curran Associates, 2017: 5998-6008.
```

### 网络资源 [EB/OL]
```
[序号] 作者. 题名[EB/OL]. (发布日期)[引用日期]. URL.
```
示例:
```
[7] OpenAI. GPT-4 Technical Report[EB/OL]. (2023-03-15)[2024-01-10]. https://arxiv.org/abs/2303.08774.
```

### 专利 [P]
```
[序号] 发明人. 专利名[P]. 专利号, 公告日期.
```

### 标准 [S]
```
[序号] 标准号. 标准名称[S]. 出版地: 出版者, 年.
```
EOF
      ;;
    apa)
      cat <<'EOF'
## APA 7th Edition 格式

### 期刊论文
```
Author, A. A., & Author, B. B. (Year). Title of article. Title of Periodical, Volume(Issue), Page–Page. https://doi.org/xxxxx
```
示例:
```
Smith, J., & Johnson, A. B. (2023). Deep learning for NLP: A survey. Nature Machine Intelligence, 5(2), 108-120. https://doi.org/10.1038/s42256-023-00612-2
```

### 图书
```
Author, A. A. (Year). Title of work: Capital letter also for subtitle (Edition). Publisher.
```

### 网络资源
```
Author, A. A. (Year, Month Day). Title of page. Site Name. URL
```

### 注意事项
- 作者超过20人时，列出前19个...后列最后1个
- DOI用https://doi.org/格式
- 悬挂缩进（首行不缩进，其余缩进0.5英寸）
EOF
      ;;
    ieee)
      cat <<'EOF'
## IEEE 格式

### 期刊论文
```
[1] A. Author and B. Author, "Title of article," Title of Journal, vol. X, no. X, pp. xxx-xxx, Month Year.
```

### 会议论文
```
[2] A. Author, "Title of paper," in Proc. Conference Name, City, Country, Year, pp. xxx-xxx.
```

### 注意事项
- 按引用顺序编号[1], [2], [3]...
- 作者名缩写在前: J. Smith
- 标题用引号，期刊/会议名斜体
EOF
      ;;
  esac
}

# ── 摘要模板 ──
generate_abstract() {
  local title="${1:-研究题目}"
  local field="${2:-计算机}"

  cat <<EOF
# 📋 摘要模板 — ${title}

> 生成时间: $(date '+%Y-%m-%d %H:%M')

## 中文摘要（300-500字）

### 结构化模板

**[背景]** 随着${field}领域的快速发展，[问题/需求]日益凸显。[现有方法]虽然在[某方面]取得了一定成效，但仍存在[不足1]和[不足2]等问题。

**[目的]** 本文针对[具体问题]，提出了一种基于[方法/技术]的[解决方案名称]，旨在[解决什么/提升什么]。

**[方法]** 首先，[方法步骤1，如"构建了...模型"]；其次，[方法步骤2，如"设计了...算法"]；最后，[方法步骤3，如"通过...进行了验证"]。

**[结果]** 实验结果表明，所提方法在[评估指标1]上达到了[具体数值]，相比[对比方法]提升了[X]%；在[评估指标2]上，[具体结果]。

**[结论]** 本研究证明了[核心结论]，为[领域/方向]提供了[理论/实践]参考。

**关键词：** [词1]；[词2]；[词3]；[词4]；[词5]

---

## English Abstract

### Structured Template

**[Background]** With the rapid development of [field], [problem] has become increasingly prominent. Although [existing methods] have achieved certain results in [aspect], [limitation1] and [limitation2] remain as challenges.

**[Objective]** This paper proposes a [method]-based [solution name] to address [specific problem], aiming to [goal].

**[Methods]** First, [step1]; Second, [step2]; Finally, [step3].

**[Results]** Experimental results demonstrate that the proposed method achieves [metric1] of [value], outperforming [baseline] by [X]%. For [metric2], [specific results].

**[Conclusions]** This study validates [core conclusion] and provides [theoretical/practical] insights for [field/direction].

**Keywords:** [word1]; [word2]; [word3]; [word4]; [word5]

---

## ⚠️ 摘要写作原则

| 原则 | 说明 |
|------|------|
| ✅ 独立性 | 不需要看正文就能理解 |
| ✅ 完整性 | 包含目的、方法、结果、结论 |
| ✅ 客观性 | 避免主观评价(如"创新性地") |
| ✅ 具体性 | 有具体数据和结果 |
| ❌ 不引用文献 | 摘要中不出现[1]这类引用 |
| ❌ 不用图表 | 不引用"如图X所示" |
| ❌ 不用缩写 | 首次出现写全称 |
| ❌ 不要套话 | 避免"具有重要意义"等空话 |
EOF
}

# ── 答辩准备 ──
generate_defense() {
  local title="${1:-论文题目}"
  local duration="${2:-15}"

  cat <<EOF
# 🎤 答辩准备 — ${title}

> 答辩时长: ${duration}分钟 + Q&A
> 生成时间: $(date '+%Y-%m-%d %H:%M')

## PPT时间分配

| 环节 | 时长 | 页数 | 内容 |
|------|------|------|------|
| 开场 | 1min | 1-2页 | 自我介绍+题目 |
| 背景 | 2min | 2-3页 | 为什么做+现状 |
| 方法 | $(echo "scale=0; $duration * 40 / 100" | bc)min | 5-8页 | 怎么做（核心） |
| 结果 | $(echo "scale=0; $duration * 25 / 100" | bc)min | 3-5页 | 做出了什么 |
| 总结 | 1min | 1-2页 | 结论+贡献+不足 |
| 致谢 | 0.5min | 1页 | 感谢 |
| **共计** | **${duration}min** | **13-21页** | |

## PPT制作要点

1. **每页一个核心观点** — 不要堆砌文字
2. **图表 > 文字** — 框架图、流程图、对比表
3. **字体≥24pt** — 确保后排看得清
4. **动画慎用** — 简洁>花哨
5. **页码要有** — 方便老师提问时定位

## 常见答辩问题（准备30个）

### 研究动机类
1. 为什么选择这个题目？
2. 这个研究的实际应用场景是什么？
3. 你的研究有什么创新点？

### 方法类
4. 为什么选择这个方法而不是[替代方法]？
5. 你的方法和[XXX]方法有什么区别？
6. 算法的时间/空间复杂度是多少？
7. 参数是怎么选择的？有做消融实验吗？

### 实验类
8. 数据集/样本是怎么获取的？有代表性吗？
9. 评估指标为什么选这几个？
10. 实验结果的统计显著性如何？
11. 在什么情况下你的方法会失效？

### 理论类
12. [核心概念]你是怎么定义的？
13. 你的理论基础是什么？
14. 这个模型的假设条件是什么？

### 挑战类
15. 研究过程中遇到的最大困难是什么？
16. 如果重新做，你会怎么改进？
17. 你的研究有什么局限性？

### 延伸类
18. 未来打算怎么继续这个研究？
19. 你的研究对[相关领域]有什么启示？
20. 如果数据量增加10倍，方法还适用吗？

## 答辩技巧

### 陈述阶段
- ⏰ 提前演练3遍，控制时间
- 📝 准备逐字稿但不要念
- 👀 看评委，不要只看屏幕
- 🎯 重点讲创新点和结果

### Q&A阶段
- ✅ 听完问题再回答（可以重复确认）
- ✅ 不知道就诚实说："这个角度我没有深入考虑，感谢老师的建议"
- ✅ 回答要有结构：先结论，再解释
- ❌ 不要和评委争论
- ❌ 不要说"论文里写了"——评委可能没看到那个部分
EOF
}

# ── 完成度检查清单 ──
generate_checklist() {
  local level="${1:-本科}"

  cat <<EOF
# ✅ 论文完成度检查清单 — ${level}

> 打 [x] 表示已完成

## 格式检查
- [ ] 封面信息完整（题目、姓名、学号、导师、日期）
- [ ] 页码正确（摘要用罗马数字，正文用阿拉伯数字）
- [ ] 目录自动生成且页码正确
- [ ] 字体字号符合模板（宋体/Times New Roman）
- [ ] 行距符合要求（通常1.5倍）
- [ ] 页边距正确（通常上下2.5cm，左3cm，右2cm）
- [ ] 章节编号连续正确
- [ ] 图表编号连续且有标题
- [ ] 公式编号右对齐

## 内容检查
- [ ] 摘要300-500字，包含目的/方法/结果/结论
- [ ] 英文摘要与中文摘要对应
- [ ] 关键词3-5个
- [ ] 绪论有研究背景/意义/现状/方法/结构
- [ ] 文献综述覆盖近5年的重要文献
- [ ] 研究方法描述清晰可复现
- [ ] 实验结果有数据支撑
- [ ] 结论不超出实验结果范围
- [ ] 致谢真诚得体

## 参考文献检查
- [ ] 格式统一（GB/T 7714 或学校要求的格式）
- [ ] 数量满足要求（${level}: $([ "$level" = "本科" ] && echo "≥30" || echo "≥60")篇）
- [ ] 英文文献占比合理（≥30%）
- [ ] 近5年文献占比（≥50%）
- [ ] 正文中都有引用（没有"僵尸文献"）
- [ ] 引用序号连续

## 学术规范检查
- [ ] 查重率符合要求（通常<20%）
- [ ] 引用标注正确（非抄袭）
- [ ] 数据/图表来源标注
- [ ] 无AI生成痕迹（语言自然）
- [ ] 无低级语法错误
- [ ] 术语使用一致

## 提交前
- [ ] 导师审阅通过
- [ ] PDF格式导出无乱码
- [ ] 文件命名规范（姓名_学号_毕业论文）
- [ ] 备份存档（至少2份）
- [ ] 答辩PPT准备完成
- [ ] 打印装订（如需要）
EOF
}

# ── 帮助 ──
show_help() {
  cat <<'HELP'
📝 论文工具 — thesis.sh

用法: bash thesis.sh <command> [args...]

命令:
  outline <题目> [本科|硕士|博士] [学科]
        → 生成完整论文大纲（含章节字数分配）
  cite [gb|apa|ieee] [类型]
        → 参考文献格式模板（含示例）
  abstract <题目> [学科]
        → 摘要写作模板（中英文+写作原则）
  defense <题目> [答辩时长]
        → 答辩准备（PPT分配+20个常见问题+技巧）
  checklist [本科|硕士|博士]
        → 论文完成度检查清单
  help  → 显示帮助

示例:
  bash thesis.sh outline "基于深度学习的图像分类" 硕士 计算机科学
  bash thesis.sh cite gb
  bash thesis.sh cite apa
  bash thesis.sh abstract "区块链在供应链中的应用" 管理学
  bash thesis.sh defense "我的论文题目" 15
  bash thesis.sh checklist 本科

💡 特色:
  - 根据学位层次自动调整大纲深度和字数
  - GB/T 7714 + APA + IEEE 三种引用格式
  - 结构化摘要模板（中英双语）
  - 答辩准备含20+常见问题
  - 完成度清单（一键自查）
HELP
}

case "$CMD" in
  outline)
    IFS='|' read -ra A <<< "$(echo "$INPUT" | sed 's/  */|/g')"
    generate_outline "${A[0]:-}" "${A[1]:-本科}" "${A[2]:-计算机}"
    ;;
  cite)
    IFS=' ' read -ra A <<< "$INPUT"
    generate_citation "${A[0]:-gb}" "${A[1]:-all}"
    ;;
  abstract)
    IFS='|' read -ra A <<< "$(echo "$INPUT" | sed 's/  */|/g')"
    generate_abstract "${A[0]:-}" "${A[1]:-计算机}"
    ;;
  defense)
    IFS='|' read -ra A <<< "$(echo "$INPUT" | sed 's/  */|/g')"
    generate_defense "${A[0]:-}" "${A[1]:-15}"
    ;;
  checklist)
    generate_checklist "${INPUT:-本科}"
    ;;
  help|*)  show_help ;;
esac
