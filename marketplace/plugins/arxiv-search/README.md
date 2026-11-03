# arXiv 论文查询

无需 API Key，通过 arXiv 官方 API 查询论文元数据。

在 Dashboard 的「插件市场」安装并启用后，普通 Agent 默认获得 `search_arxiv`
工具；可以在 Agent 的工具设置中单独关闭。

调用示例：

```text
search_arxiv(query="retrieval augmented generation", limit=5)
search_arxiv(query="ti:transformer AND cat:cs.CL", sort_by="submittedDate")
search_arxiv(query="au:Vaswani", start=5, limit=5)
search_arxiv(query="1706.03762")
search_arxiv(query="https://arxiv.org/abs/1706.03762")
```

支持关键词、标题/作者/分类等查询语法，以及新旧论文编号、版本号和摘要/PDF
链接。中文提问由 Agent 转换为英文检索词。`limit` 默认为 5，范围 1–20；`start`
为从 0 开始的分页偏移。`sort_by` 支持 `relevance`、`submittedDate` 和
`lastUpdatedDate`，`sort_order` 支持 `ascending` 和 `descending`。

返回标题、作者、完整摘要、分类、发表/更新时间、DOI、期刊引用以及摘要/PDF
链接。聊天卡片支持中英文和深浅主题；IM 渠道使用包含摘要和链接的纯文本回退。
网络请求异步执行，同一进程中的请求串行且至少间隔 3 秒。

API 文档：[arXiv API User's Manual](https://info.arxiv.org/help/api/user-manual.html)。
图标使用 [arXiv 官方 Small Logomark SVG](https://cornell.box.com/v/arxiv-logomark-small-svg)，
保留官方形状与红灰颜色，用于鸣谢论文数据来源。
使用规范：[arXiv Name and Logo Use](https://info.arxiv.org/brand/brand-guidelines.html)。

Thank you to arXiv for use of its open access interoperability. This service was
not reviewed or approved by, nor does it necessarily express or reflect the
policies or opinions of, arXiv.
