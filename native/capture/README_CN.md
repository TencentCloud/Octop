# 通用 macOS 采集组件

`OctopCapture` 提供文稿扫描、拍照、USB 手机照片选择和本地文件选择。它不依赖 Octop 的模型、Agent、工作区，也不负责 OCR、分类、归档和发送对话。调用方决定文件保存位置和后续处理。

## 构建与调用

需要 macOS 13+、Python 3，以及用于构建 Swift 的 Xcode Command Line Tools。在仓库根目录执行：

```sh
sh native/capture/build.sh
./native/capture/octop-capture scan --output ./work/captures
./native/capture/octop-capture photo --output ./work/captures
./native/capture/octop-capture album --output ./work/captures
./native/capture/octop-capture import --output ./work/captures
```

每次调用在 `--output` 下创建独立 session 目录，保留原件、预览和 `capture.json`。stdout 只输出一份 JSON；系统诊断写入 stderr。默认等待 600 秒，`--timeout 120` 可调整。成功和用户取消退出码为 0；超时、不可用或失败为 1；命令参数错误为 2。取消属于正常用户操作，调用方应检查 status，不能仅凭退出码判断是否有文件。

构建后，可以把这个目录（包括 OctopCapture.app 和 octop-capture）复制到其它项目使用。不要单独复制 CLI，它需要同目录下的 .app。不自动安装 PATH 或写入全局目录。

## 稳定结果格式 v1

返回字段包括：`schema_version`、`session_id`、`mode`、`status`、`files`、`reason`，已创建会话时包括 `directory` 和 `manifest_path`。`status` 为 ok / cancelled / timeout / unavailable / error。每个 files 项含绝对 `path`、`filename`、`media_type`、`size` 和可选 `preview_path`。已创建且可写的会话中，成功、取消、超时及错误结果均保存到 capture.json，内容与 stdout 一致。原生 result.json 是内部协议，业务代码应使用 capture.json。

扫描原件为多页 PDF，预览为第一页 PNG；拍照原件为 PNG；文件导入及 USB 照片保留所选原件，HEIC/TIFF 等额外提供缩小的 PNG 预览（最长边 800 逻辑点），避免生成比原件更大的全尺寸预览。取消/超时没有可消费文件引用；失败或超时可能留下会话中的中间文件，调用方自行管理保留和清理。

## 其它 skill 调用约定

其它 skill 的操作说明可直接使用下列流程，无需依赖业务插件：

1. 使用宿主 Mac 的命令执行能力运行 octop-capture，对应用户请求选择 scan / photo / album / import，提供自己的持久输出目录。
2. 等用户在原生窗口完成操作，解析 stdout JSON。
3. status 为 ok 时读取 files[].path；如需界面预览使用 preview_path，实际整理保留原始 path。取消时结束本次采集，不当作失败重试。
4. OCR、票据报销、合同分类等由各自 skill 完成。普通 CLI 文件不会自动写入 Octop Agent 工作区；需要使用宿主应用现有附件/工作区导入机制。

命令示例（在 Octop 仓库中）：

```sh
./native/capture/octop-capture scan --output ./work/receipt-captures
```

需要原生窗口的步骤必须在登录中的 macOS 图形会话运行。Linux/Docker 中的 Agent 执行器不能通过这条命令控制宿主 Mac；本组件只支持 macOS，不提供远程桥接。相册模式要求 USB 连接、解锁并信任电脑，只能读取设备提供的媒体，不支持 iCloud-only 原件或手机相册分组。拍照/扫描继续使用 Continuity Camera。

## 验证与范围

原生菜单动作、结果关闭保护、PDF 预览回归：

```sh
sh native/capture/test_scan.sh
uv run --frozen pytest tests/unit/test_native_capture_component.py
```

本组件只支持 macOS 13+，按当前 Mac 的架构本机编译，产物不提交 Git。没有跨平台实现，独立 CLI 不依赖 Agent 或业务插件；Octop 输入框通过一个通用服务端适配器接入现有附件存储和消息流程，不新增 OCR 或分类逻辑。构建产物使用本机临时签名，尚未提供公证安装包。

人工验证建议：依次测试 scan / photo / album / import；扫描两页确认原件 PDF 和首页预览，拍照确认 PNG，USB 多选确认原件与顺序；关闭选择器确认 cancelled；缩短 --timeout 确认 timeout。核对 stdout 与 capture.json 一致，重复调用产生不同 session 目录。真实 iPhone 操作仍需在设备上完成。

## Octop 输入框完整流程

构建 helper 后重启 Octop、刷新网页，附件按钮提供导入文件、iPhone 扫描、拍照、USB 相册。完成采集后，原件和预览写入当前 Agent 的 inbound；附件预览确认后点击发送，沿用现有图片/文件消息处理。无需安装插件，不修改 Agent manager 或插件上下文。

服务端默认查找本仓库构建的 .app。使用安装包部署时，可在启动前设置 OCTOP_NATIVE_CAPTURE_HELPER 为 OctopCapture.app/Contents/MacOS/OctopCapture 的绝对路径。只支持登录中的 macOS 图形会话；非 macOS 服务端保留原有上传按钮。采集入口仅允许 Agent 所有者/管理员，遵循上传容量限制，同一服务进程同时只允许一个采集窗口。反向代理需允许最长十分钟的请求等待。
