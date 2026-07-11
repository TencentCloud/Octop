# Changelog

本文件记录项目的所有重要变更。

格式遵循 [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)，版本号遵循 [语义化版本规范](https://semver.org/spec/v2.0.0.html)。

## [0.9.4] - 2026-07-11

### 新增
- 新增 agent backend 的主机 root_dir 浏览器与权限探测能力
- 改进聊天流式滚动行为与思考计时器

### 修复
- 修复 Windows 下 sqlite 路径测试、媒体路径与 POSIX 专属测试导致的 CI 失败
- 修复 Windows 测试收集问题（惰性导入 pwd 模块）
- 修复 harness-memory Bridge 导入路径
- 修复 CI 流水线并让测试套件通过，项目重命名为 Octop

### 变更
- Windows 兼容：默认 agent backend 限定到 workspace，并集中 POSIX 专属 stdlib 调用以适配 Windows mypy CI

## [0.9.1] - 2026-07-08

### 新增
- 远程浏览器控制页面与浏览器 AI 面板，支持远程浏览器自动化操作
- 附件下载的 `Content-Disposition` 头（RFC 5987，兼容非 ASCII 文件名）
- 前端 UI 语言偏好持久化（自动检测浏览器语言并记忆）
- 专家目录欢迎语（默认欢迎内容 / 工作区清单读取 / 专家目录播种）
- 附件相关国际化域（`i18n/domains/attachment.py`）
- 聊天欢迎语支持

### 变更
- 重构聊天附件与上传处理链路，精简接口与实现
- 重构网关媒体层：附件提示、入站存储、工具媒体展示重写
- 重构 harness 请求构造与消息处理器
- 调整上下文拆分、专家目录、provider 存储与 agent 管理器
- 重构前端聊天界面：输入框、消息气泡、工具媒体条、上下文窗口环等组件大量更新
- 更新登录、初始化向导、终端 AI 面板等前端页面

### 修复
- 修复附件路径解析与内容分发相关问题

### 移除
- 移除模型配置提示弹窗、旧聊天流模块、slash 上下文与附件签名测试

