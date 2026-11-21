# RAGFlow connector / RAGFlow 连接器

## 配置

在「连接器」中新建 ragflow，填写：

- **服务地址**：现有 RAGFlow 的地址，例如 `http://127.0.0.1:9380`，也可填写以 `/api/v1` 结尾的 API 根地址。反向代理的路径前缀会保留。地址相对于运行 Octop 的主机；两者运行在不同容器中时，可使用可互通的内网 IP、`host.docker.internal` 或已有的 HTTPS 反向代理地址；公开地址要求 HTTPS。
- **API Key**：在 RAGFlow 用户菜单的「API」页面生成。密钥通过 Octop 现有凭证存储加密保存，编辑时留空会保留原密钥。
- **默认知识库 ID**（可选）：逗号分隔的 dataset ID，不能使用知识库名称。留空时，让专家先列出知识库，选择 ID 后检索。此设置是检索默认值，专家仍可选择该 API Key 有权限访问的其他知识库。

保存前可点击「测试连接」。测试会使用密钥请求知识库列表，能识别鉴权失败、网络错误，以及 HTTP 200 中的 RAGFlow 业务错误；没有知识库时也可验证连接成功。

在专家或对话中选用该连接器后，可尝试：

> 列出 RAGFlow 里的知识库，在“员工手册”里搜索请假规定，并标出文档名称。

提供三个只读工具：

| 工具 | 用途 |
|------|------|
| `list_datasets` | 分页列出当前凭证可见的知识库及其 ID |
| `search` | 按问题检索指定或默认知识库，返回最多 8 条片段以及来源文档、知识库、相似度和位置信息 |
| `read_document` | 根据检索返回的知识库 ID、文档 ID，分页读取已解析的文档片段 |

检索片段最多返回 1200 字符；读取文档时每个片段最多 4000 字符，并用 `truncated` 标记截断。分页默认每页 20 条、最多 50 条。检索需要 RAGFlow 中的文档已完成解析。

此连接器通过 RAGFlow 的公开 HTTP API 接入，无需额外启动 MCP 服务。文档、解析和索引继续由 RAGFlow 管理；不会导入或同步到 Octop 内置知识库，也不提供上传、删除或其他写入操作。

## Configuration

Create a **ragflow** connector, enter its service URL and API Key, and optionally set comma-separated default dataset IDs. The service URL is resolved from the Octop host, supports reverse-proxy prefixes, and accepts either the service origin or an `/api/v1` API root. Public remote URLs require HTTPS; loopback/private IPs and local hostnames such as `host.docker.internal` may use HTTP.

Test the connection, save it, then select the connector for your expert or conversation. Ask the expert to list datasets, search a chosen dataset, and read the returned documents. Dataset IDs are retrieval defaults, not access restrictions; the API Key determines accessible datasets. Editing without a new API Key preserves the stored key.

The three read-only tools are `list_datasets`, `search`, and `read_document`. Search returns up to eight source passages with dataset/document IDs, names, scores, and positions. Passages are limited to 1200 characters for search and 4000 for document reading, with explicit truncation markers. Lists use pagination (20 items by default, at most 50). Documents must already be parsed in RAGFlow.

This integration uses RAGFlow's public HTTP API, requires no separate MCP server, and keeps the existing Octop knowledge base independent. It does not upload, delete, or synchronize documents.

## References / 参考

- [RAGFlow HTTP API](https://ragflow.io/docs/http_api_reference) — datasets, retrieval, and document chunk endpoints.
- [Acquire RAGFlow API Key](https://ragflow.io/docs/acquire_ragflow_api_key).
- Connector icon: [official RAGFlow SVG](https://github.com/infiniflow/ragflow/blob/main/web/public/logo.svg), from the [Apache-2.0 licensed project](https://github.com/infiniflow/ragflow/blob/main/LICENSE).
