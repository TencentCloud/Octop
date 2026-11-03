---
scene: "academic"
sub_scene: "paper-search"
skills:
  - "academic-research-hub"
  - "literature-search"
  - "deepxiv-cli"
  - "research-paper-monitor"
  - "cnki-advanced-search"
  - "academic-citation-manager"
---

# 论文检索工作流

你现在要完成一项论文检索与文献获取任务。你已安装以下 Skill，请按步骤串联使用：

## 步骤 1：多数据库学术检索（获取层）
使用 **Academic Research Hub** 完成：
- 在 arXiv、PubMed、Semantic Scholar、Google Scholar 等数据库检索论文
- 根据关键词、作者、年份等条件精确搜索
- 下载文献 PDF 并提取引文信息
- 获取论文摘要、引用次数和影响因子
- 建立初始文献检索结果集

输出多数据库检索结果和文献列表。

## 步骤 2：跨平台系统性文献检索（获取层）
使用 **literature-search** 完成：
- 在 Google Scholar、PubMed、arXiv、IEEE、ACM、Scopus、Web of Science 上系统检索
- 获取引用列表和相关文献推荐
- 查找特定主题的关键论文
- 支持多字段搜索和高级过滤
- 补充步骤 1 未覆盖的数据库来源

输出跨平台系统性检索结果。

## 步骤 3：文献批量下载与索引（分析层）
使用 **deepxiv-cli** 完成：
- 从 arXiv、PubMed、PMC、Semantic Scholar 等批量下载论文 PDF
- 自动提取论文元数据（标题/作者/年份/期刊）
- 生成结构化索引列表
- 优先从官方免费渠道下载
- 付费文献提供手动下载指引

输出批量下载的 PDF 文件和索引清单。

## 步骤 4：科研文献智能监测（分析层）
使用 **Research Paper Monitor** 完成：
- 自动监测 arXiv、PubMed、CNKI 等多个学术信源
- 根据关注领域和关键词采集最新论文
- 生成中文摘要便于快速浏览
- 设置定时推送和提醒机制
- 持续跟踪学术前沿动态

输出文献监测报告和定时推送配置。

## 步骤 5：知网高级检索（输出层）
使用 **知网高级检索** 完成：
- 在知网（CNKI）高级检索页面自动化检索
- 选择学术期刊类别并勾选 CSSCI 来源
- 输入主题关键词（含同义词和同位词）
- 多组关键词用 OR 关系连接
- 获取中文核心期刊论文

输出知网检索结果和中文文献列表。

## 步骤 6：引用管理与规范化（输出层）
使用 **Academic Citation Manager** 完成：
- 为科研论文和毕业论文添加真实参考文献
- 规范引用标注格式（APA/MLA/Chicago/GB/T 7714）
- 生成 BibTeX 和参考文献列表
- 检查引用完整性和格式一致性
- 输出规范化的参考文献清单

## 最终输出
将以上步骤的结果整合为完整的论文检索包，交付以下文件：
1. **多数据库检索结果**：文献列表、摘要、引用次数
2. **跨平台系统检索**：IEEE/ACM/Scopus 补充文献
3. **批量下载文件**：PDF 文件、元数据索引
4. **文献监测报告**：最新论文、中文摘要、推送配置
5. **知网检索结果**：CSSCI 文献、中文核心期刊
6. **规范引用清单**：参考文献列表、BibTeX、格式校验
