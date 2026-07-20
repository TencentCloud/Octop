# Changelog

本文件记录项目的所有重要变更。

格式遵循 [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)，版本号遵循 [语义化版本规范](https://semver.org/spec/v2.0.0.html)。

## [Unreleased]

## [0.9.11] - 2026-07-19

### 新增
- 新增 SkillHub 专家市场：支持浏览、安装与管理专家，并完善安装安全校验与欢迎页快捷卡片体验
- 新增自定义 MCP 连接器管理，支持探测、工具缓存与连接器配置

## [0.9.10] - 2026-07-18

### 新增
- 新增工作区文件预览与浏览器工作区支持，并完善相关工具链
- 新增聊天面板停靠式文件预览、HTML 预览与历史下拉刷新

### 修复
- 修复连接器 Notion OAuth 弹窗阻塞的问题 (#19)

### 变更
- 重构聊天界面，将浏览器面板与文件面板统一为 ChatDock
- 调整工作区路径透传逻辑，不再重写 BackendWorkspace 路径
- 将上下文使用统计委托给 harness-agent 0.9.10

### 移除
- 移除内置的临床医生专家 (#20)

## [0.9.9] - 2026-07-16

### 新增
- 新增远程桌面安装与连接器探测能力增强 (#16)

## [0.9.8] - 2026-07-15

### 新增
- 远程浏览器/远程桌面安装日志面板新增「复制日志」按钮，并在安装失败时提示可将日志交给 Octop 协助排查
- 新增前端 `copyText` 工具，在非安全上下文（如 plain-http 管理页）下通过临时 textarea + execCommand 回退，保证剪贴板复制可用
- 桌面安装脚本新增 `A-F4`（关闭窗口）与 `C-A-D`（显示桌面）openbox 快捷键，对应桌面快捷键

### 修复
- 修复桌面安装脚本的 Python 构建依赖检测：改用 venv Python（而非系统 `python3`）解析 `pythonX.Y-dev`，避免 evdev 编译时找不到 `Python.h`；`setup.py` 安装构建依赖时显式传入 `--python` 指向当前 venv Python
- 修复连接器类型漂移导致聊天弹窗 logo 解析失败的问题

### 变更
- Docker 构建与 `make build-frontend` 的 `NODE_OPTIONS --max-old-space-size` 由 4096 调低为 2048，降低构建内存占用
- 新增 `docker-publish.yml` 工作流，构建并推送镜像到 Docker Hub
- 移除 `release.yml` 中多余的 `id-token: write` 权限
- 删除已与现行 Docker Hub 发版流程脱节的离线部署脚本 `docker_deploy.sh`，并清理 `docker/README.md`、`README_CN.md` 中的相关章节
- 修正 `docker/README.md` 标题笔误（`ODocker` → `Octop`）

## [0.9.7] - 2026-07-14

### 新增
- 新增多款连接器网关适配器：百度地图、携程问道、飞猪、美团旅游助手、QQ 音乐、元典 (#14)
- 重构连接器网关目录与注册机制，支持更灵活的连接器安装 (#14)

### 修复
- 修复 Linux 远程桌面安装脚本在 EL7（TigerVNC 1.8）下的兼容性，避免 xfdesktop 阻塞安装

## [0.9.6] - 2026-07-13

### 新增
- 新增远程桌面（Remote Desktop）功能，支持跨 Linux、Windows、macOS 的桌面串流 (#7)

### 修复
- 从 .dockerignore 中移除 uv.lock，修正 Docker 构建无法 COPY 锁文件的问题 (#9)
- 修复远程桌面、浏览器、终端及安装向导的本地化（i18n）问题 (#11)

## [0.9.5] - 2026-07-12

### 新增
- 新增 Linux、Windows、macOS 三端的远程桌面串流能力
- 完善远程桌面的安装/卸载交互，并打包 Linux 端安装脚本

### 修复
- 修复 Windows 与 Linux CI 下桌面配置/捕获/输入相关单测与 mypy 报错
- 修复 Mac 端远程桌面安装时误导性的提示文案
- 加固桌面安装 SSE 流式推送并清理 dashboard 端 lint 问题

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

