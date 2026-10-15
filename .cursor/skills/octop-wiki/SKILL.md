---
name: octop-wiki
description: >-
  检索本仓库 docs/ 里的 Octop 产品文档，回答安装、配置、专家、人格、通道、连接器、定时任务、CLI、HTTP/WebSocket API、ACP、LDAP 和排障。
  当用户询问 Octop 的用法、命令、配置键、接口或官方行为时使用。
  不用于 octop-harness、octop-memory、octop-browser、octop-gateway 这些独立库的内部实现，也不用于 WeKnora。
---

# Octop 文档

本仓库 `docs/` 是 Octop 产品文档。回答用法、命令、配置和接口时先检索，再读少量相关页面。不要一次加载全部文档。

## 资源

- [文档索引](references/INDEX.md)：不确定关键词时先看目录。
- [来源](references/SOURCE.md)：核对文档范围和许可。
- `docs/`：仓库根目录下的正文。只读和当前问题直接相关的文件。
- `scripts/search_docs.py`：对 `docs/**/*.md` 做本地全文检索。

## 回答

1. 从本 `SKILL.md` 的位置确定仓库根目录：`.cursor/skills/octop-wiki/` 往上四级。
2. 把问题收成 2–5 个关键词，保留命令、配置键、接口路径和错误码。
3. 运行：

   ```bash
   python .cursor/skills/octop-wiki/scripts/search_docs.py "关键词"
   ```

   没有命中时换同义词再试一次。
4. 读取排名靠前且互相补充的 1–3 篇 `docs/...`。
5. 命令、配置键、路径和接口以读到的原文为准。回答里列出实际读过的路径。
6. 文档没写到的内容说明缺口，不把没搜到说成不存在。

## 不在这包里

- `docs/*.html` 是导出副本，以同名 Markdown 为准。
- Harness、Memory、Browser、Gateway 的库文档在各自仓库。
- WeKnora 是另一套知识库产品。
