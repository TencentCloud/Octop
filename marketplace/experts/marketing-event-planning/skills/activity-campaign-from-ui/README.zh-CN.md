# activity-campaign-from-ui

当前仓库版本：**0.6.0**

一个可复用的 OpenClaw Skill，用来把**活动页参考图**转成**新的 H5/Web 活动方案**，并输出可继续开发的高保真前端初版代码。

## 这个 Skill 做什么
给它活动页截图、海报式活动图、设计预览或参考页面后，它可以：
- 分析参考活动 UI
- 抽象玩法与模块模式
- 基于参考生成一个**新的活动方案**，而不是直接照搬
- 输出页面架构、弹窗、状态与数据结构建议
- 生成 **H5/Web** 的高保真前端初版代码

## 固定平台与技术栈
这个 Skill 采用强约束方案，只支持：

- 平台：**H5 / Web**
- 技术栈：**HTML + CSS + JavaScript**

即使用户提到其他技术栈，也仍然按上面的固定栈输出。

## Mode 说明
一个 Skill，支持多个 mode：

- `analysis`：只分析参考 UI
- `proposal`：基于参考生成新的活动策划
- `architecture`：输出页面模块、状态、弹窗和数据结构
- `delivery`：输出 H5/Web 高保真前端初版代码
- `full`：从参考分析一路输出到代码交付

如果用户没有指定 mode：
- 想要新活动方案，默认 `proposal`
- 明确要代码，默认 `delivery`
- 同时要方案和代码，默认 `full`

## 适用场景
- 节日活动页
- 抽奖 / 九宫格 / 大转盘活动页
- 任务领奖页
- 促活运营页
- 移动端优先的 H5 活动页
- 海报式营销活动页

## 常见输入
- 活动页截图
- 多个竞品活动参考图
- 海报式活动图
- 可访问的设计预览链接
- 用户补充的活动目标、奖励、受众说明

## 常见输出
- 参考分析
- 玩法抽象
- 新活动策划
- 页面架构
- schema / 配置建议，包括活动工厂、动画系统和资源输出约束
- 视觉方向摘要
- H5/Web 高保真前端初版代码（`index.html`、`styles.css`、`main.js`、`mock-data.js`）

## 边界
这个 Skill 不应该：
- 输出其他技术栈代码
- 把模糊文案当成精确事实
- 假装知道图中没展示的隐藏态或后端逻辑
- 直接照搬参考页面

## 视觉质量要求
对于 `delivery` 和 `full`，目标结果应是**更接近可上线质感的 H5 前端成品草案**，而不是普通 starter、demo 壳子或线框页。

强输出应当：
- 在写代码前先概括截图的视觉语言
- 先判断截图配色是否真的适合新的活动主题，再决定是否沿用
- 首屏就具备较完整的视觉层次和模块内部结构
- 当参考图有明显风格时，使用渐变、装饰包裹、徽章、标签、强化 CTA 等方式表达氛围
- 除非用户明确要求极简骨架，否则避免反复输出白底圆角卡片式脚手架

如果参考图主题和新活动主题冲突，应保留结构和玩法启发，但把配色与装饰语言重建到目标主题上。
例如：参考图是春节红金风格，但你要产出端午活动，就不应默认继续走红色春节视觉，而应转向更贴近端午的绿色、青色、水波、粽叶、绳结等方向。

## 新增交付倾向
对于 `delivery` 和 `full`：
- 输出目标应更接近“可上线质感的 H5 前端成品草案”，而不是普通 starter、demo 壳子或线框页
- 当参考图或需求明显依赖人物海报感时，首屏应优先采用成人女性主视觉构图，且默认不要替换成男性人物
- 女性人物的服饰、主色、配饰和道具要贴合活动主题，例如春节活动默认应优先使用红色主调、金色点缀和节庆服饰风格
- 可采用更有吸引力的时尚性感商业海报表达，但必须保持公开活动页可用的非低俗呈现
- 当页面模块较多、内容较密时，H5 默认优先采用 `tab` 布局来控制页面长度，而不是把所有模块自上而下平铺到底
- 如果首屏明显依赖海报感人物主视觉，默认应生成一张人物主视觉资产，并在项目代码里固定引用 `./image/bg.png`
- 生成人物图时应优先追求更接近真实商业海报的人像质感，包括自然皮肤、手部结构、头发、服饰褶皱和光影，而不是偏插画或塑料感结果
- 这张图应聚焦于人物形象和节庆氛围，不应把奖品设置、邀请奖励、任务卡片、规则区块等页面模块一并画进图里
- 参考图只能提供风格、配色、服饰、装饰密度的启发，不能直接复刻原图里美女的脸、姿态、构图或双人站位
- 页面结构上，`./image/bg.png` 必须处于页面最上方的首屏主视觉位置；摘要条、tab、任务模块等应排在其后
- 当该类需求要求必须出图时，应先生成对应 `./image/bg.png` 的图片资产，再交付前端文件，不能只在代码里写一个图片路径
- 默认采用 `regenerate_each_run`：同样的输入再次执行时，仍应重新生成人物图；只有用户明确要求复用旧图时才允许复用
- 如果宿主暴露了具体工具名，例如 `image_generate`，应直接调用，而不是把这一步写成说明文字
- 如果这是必须出图的场景但图像生成不可用，应明确说明本次被阻塞，并停止交付，而不是偷偷降级成占位图
- 最终交付的所有文件都应放到当前执行环境下的 `project/` 目录中；如果该目录不存在，必须自动创建
- 最终交付不能直接平铺在 `project/` 下，而是要再包一层目录，例如 `project/<delivery-slug>/index.html`
- 前端项目应在 `project/<delivery-slug>/` 下创建 `image/` 目录，图片引用路径仍使用 `./image/bg.png`
- 交付代码后应明确提示：`需要把生成好的图片，改名为bg，图片类型为 png，放到 project/<delivery-slug>/image 目录下`
- 当用户没有明确指定活动类型时，应自动生成一个可配置的新活动机制，而不是只重复参考图里的转盘/红包/签到套路
- 节庆或抽奖类活动页默认应增加“一个主互动动画 + 两个辅助动态层”的动画编排，而不是只给一个静态页面壳子
- 这里的“更像成品”指前端质感、结构和状态表达更完整，不代表已经接入真实后端

## 本地文件生成
- `proposal` 模式下，产物应更像运营活动视觉稿，而不是纯文字策划 memo
- 如果用户明确要求本地视觉稿，并且宿主环境支持本地执行，应使用 Python 生成 `project/<delivery-slug>/campaign-proposal.pptx`
- `delivery`、`full` 模式下，如果用户明确要求本地文件，并且宿主环境支持本地执行，应使用 Python 直接写出 `project/<delivery-slug>/index.html`、`project/<delivery-slug>/styles.css`、`project/<delivery-slug>/main.js`、`project/<delivery-slug>/mock-data.js`
- 当前执行环境下的 `project/` 目录是强制的顶层输出根目录；如果不存在，必须自动创建
- 在 `project/` 下还必须自动创建一层交付目录 `project/<delivery-slug>/`，所有最终文件都落在这层目录内
- 使用 Python 本地写文件时，必须先创建 `project/<delivery-slug>/image/`，并把生成的人物图保存到 `project/<delivery-slug>/image/bg.png`
- 当用户明确要求本地输出时，不能只返回交付文件结构或代码块，必须真实写入文件并回报实际落盘路径
- 即使启用本地生成，也不要在回复里输出 shell 写文件命令，而是直接说明已生成的文件路径


## 仓库结构
- `SKILL.md`：主规则说明
- `agents/openai.yaml`：市场与技能选择器使用的 UI 元数据
- `VERSION`：当前仓库版本号
- `LICENSE`：仓库许可证
- `CODEOWNERS`：仓库责任人模板
- `CHANGELOG.md`：仓库变更记录
- `RELEASE.md`：版本策略与发布规则
- `CONTRIBUTING.md`：贡献与维护约束
- `references/scope.md`：边界与非目标
- `examples/input-example.md`：输入示例
- `examples/output-example.md`：输出示例
- `examples/spring-festival-case.md`：完整案例说明
- `examples/campaign-schema-example.json`：活动交付 schema 示例
- `examples/mode-analysis-example.md`：analysis 模式示例
- `examples/mode-proposal-example.md`：proposal 模式示例
- `examples/mode-architecture-example.md`：architecture 模式示例
- `examples/mode-delivery-example.md`：delivery 模式示例
- `examples/full-delivery-example.md`：full 模式完整闭环示例
