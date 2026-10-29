// 简单主题：宿主调用 setup 后生效，返回的清理函数负责禁用、卸载及退出登录。
export function setup(host) {
const lifecycle = new AbortController();
let disposed = false;
const frames = new Set();
function scheduleFrame(callback) {
  const id = requestAnimationFrame(() => {
    frames.delete(id);
    if (!disposed) callback();
  });
  frames.add(id);
  return id;
}
let themeFont = null;
const previousRootId = document.documentElement.id;
const themeColors = [...document.querySelectorAll('meta[name="theme-color"]')].map(meta => ({
  meta, content: meta.getAttribute('content'), media: meta.getAttribute('media'),
}));
function listen(target, type, listener, options = {}) {
  target.addEventListener(type, listener, {
    ...(typeof options === 'boolean' ? { capture: options } : options),
    signal: lifecycle.signal,
  });
}
const STYLE_ID = "octop-simple-theme-style";
const ROOT_ID = "octop-simple-theme-root";
const PLUGIN_ID = "simple-theme";
const VERSION = "1.0.3";
const FONT_PATH = "/plugins/simple-theme/ui/fonts/InterVariable.woff2";
const FONT_FAMILY = "Simple Theme Sans";
const STORAGE_KEY = "octop.simple-theme.preference";
const MIGRATION_KEY = "octop.simple-theme.legacy-migration-v1";
// 只运行一次旧存储迁移；完成后运行时完全使用 simple-theme 新键。
try {
  if (window.localStorage.getItem(MIGRATION_KEY) !== "1") {
    const oldPreference = window.localStorage.getItem("octop.gpt-theme.preference");
    const oldWidth = window.localStorage.getItem("octop.gpt-theme.column-width");
    if (window.localStorage.getItem(STORAGE_KEY) === null && oldPreference !== null)
      window.localStorage.setItem(STORAGE_KEY, VERSION);
    if (window.localStorage.getItem("octop.simple-theme.column-width") === null && oldWidth !== null)
      window.localStorage.setItem("octop.simple-theme.column-width", oldWidth);
    window.localStorage.removeItem("octop.gpt-theme.preference");
    window.localStorage.removeItem("octop.gpt-theme.column-width");
    window.localStorage.setItem(MIGRATION_KEY, "1");
  }
} catch (err) { /* localStorage 受限时不阻止主题启动 */ }

const CSS = `/* =========================================================================
   简单主题 · 控制台主题
   ---------------------------------------------------------------------
   目标：把控制台的信息排布改成 简洁、易读的单列布局的读法。
   四条硬规则（违反任何一条都会立刻变回"后台管理系统"）：
   1. 只有一列。正文、标题、输入框共用同一条 768px 中轴，头像列整列拆掉。
   2. 只允许中性灰。品牌粉、Tailwind 冷灰、硬编码靛蓝全部并到同一套灰阶。
   3. 分隔只用 1px 发丝线；浮起只有极淡投影，且只给真正浮起的层。
   4. 次要信息（时间戳、用量、复制、更多）默认透明，悬停该行才出现。

   所有规则挂在 html#octop-simple-theme-root 下，禁用插件即完全还原。
   ========================================================================= */

/* ------------------------------- 令牌 ------------------------------- */
html#octop-simple-theme-root,
html#octop-simple-theme-root[data-theme="light"] {
  --simple-column: var(--simple-user-column, 768px);

  --simple-hairline: #ececec;
  --simple-hairline-strong: #dcdcdc;
  --simple-hover: rgba(13, 13, 13, 0.05);
  --simple-press: rgba(13, 13, 13, 0.09);

  --fn-bg-primary: #ffffff;
  --fn-bg-base: #ffffff;
  --fn-bg-page: #ffffff;
  --fn-bg-layout: #ffffff;
  --fn-bg-container: #ffffff;
  --fn-bg-elevated: #ffffff;
  --fn-bg-secondary: #f4f4f4;
  --fn-bg-tertiary: #ececec;
  --fn-bg-quaternary: rgba(13, 13, 13, 0.03);
  --fn-bg-subtle: #f7f7f8;
  --fn-bg-secondary-hover: #ececec;
  --fn-bg-secondary-active: #e6e6e6;
  --fn-bg-hover: rgba(13, 13, 13, 0.055);
  --fn-bg-active: rgba(13, 13, 13, 0.09);
  --fn-bg-selected: rgba(13, 13, 13, 0.07);
  --fn-bg-code: #f7f7f8;
  --fn-bg-toolbar: #ffffff;
  --fn-bg-toolbar-hover: #f4f4f4;
  --fn-bg-input-label: #f7f7f8;
  --fn-bg-glass: rgba(255, 255, 255, 0.88);
  --fn-bg-sidebar: #f9f9f9;
  --fn-surface: #ffffff;
  --fn-surface-sunken: #f9f9f9;
  --fn-fill-hover: rgba(13, 13, 13, 0.055);
  --fn-fill-tertiary: #ececec;

  --fn-text-primary: #0d0d0d;
  --fn-text-secondary: #5d5d5d;
  --fn-text-tertiary: #8f8f8f;
  --fn-text-quaternary: #a9a9a9;
  --fn-text-placeholder: #b4b4b4;
  --fn-text-disabled: #cdcdcd;
  --fn-text-inverse: #ffffff;
  --fn-text-brand: #0d0d0d;
  --fn-text-link: #0d0d0d;
  --fn-text-danger: #c0392b;
  --fn-logo-color: #0d0d0d;
  --fn-logo-filter: none;

  --fn-border-primary: #ececec;
  --fn-border-secondary: #f0f0f0;
  --fn-border-tertiary: #f4f4f4;
  --fn-border-input: #dedede;
  --fn-border-input-alt: #e6e6e6;
  --fn-border-focus: #c9c9c9;
  --fn-border: #ececec;
  --fn-border-color: #ececec;
  --fn-border-strong: #d4d4d4;
  --fn-border-subtle: rgba(13, 13, 13, 0.07);

  --fn-color-brand: #0d0d0d;
  --fn-color-brand-hover: #262626;
  --fn-color-brand-soft: #262626;
  --fn-color-brand-bg: rgba(13, 13, 13, 0.05);
  --fn-color-brand-border: rgba(13, 13, 13, 0.14);
  --fn-color-on-brand: #ffffff;
  --fn-color-brand-light: #f4f4f4;
  --fn-color-brand-shadow: rgba(13, 13, 13, 0.1);
  --fn-color-brand-glow: rgba(13, 13, 13, 0.06);
  --fn-primary: #0d0d0d;
  --fn-primary-bg: rgba(13, 13, 13, 0.05);
  --fn-color-primary: #0d0d0d;
  --fn-accent: #0d0d0d;

  --fn-sidebar-width: 260px;
  --fn-sidebar-bg: #f9f9f9;
  --fn-sidebar-border: transparent;
  --fn-sidebar-item-hover: rgba(13, 13, 13, 0.05);
  --fn-sidebar-item-active-bg: rgba(13, 13, 13, 0.07);
  --fn-sidebar-item-active: rgba(13, 13, 13, 0.06);
  --fn-sidebar-item-active-text: #0d0d0d;
  --fn-sidebar-group-text: #8f8f8f;
  --fn-header-bg: rgba(255, 255, 255, 0.88);
  --fn-header-blur: 20px;
  --fn-chat-divider: transparent;

  --fn-shadow-xs: 0 1px 1px rgba(13, 13, 13, 0.03);
  --fn-shadow-sm: 0 1px 2px rgba(13, 13, 13, 0.05);
  --fn-shadow-md: 0 2px 6px rgba(13, 13, 13, 0.06), 0 12px 32px rgba(13, 13, 13, 0.06);
  --fn-shadow-lg: 0 4px 10px rgba(13, 13, 13, 0.07), 0 18px 48px rgba(13, 13, 13, 0.08);
  --fn-shadow-xl: 0 8px 20px rgba(13, 13, 13, 0.08), 0 28px 64px rgba(13, 13, 13, 0.1);
  --fn-shadow-brand: var(--fn-shadow-sm);
  --fn-shadow-brand-lg: var(--fn-shadow-md);
  --fn-card-border-normal: var(--simple-hairline);
  --fn-card-shadow-normal: none;

  --fn-radius-sm: 6px;
  --fn-radius-md: 10px;
  --fn-radius-lg: 14px;
  --fn-radius-xl: 18px;
  --fn-radius-full: 980px;
  --fn-card-radius: 14px;

  --fn-assistant-bubble-bg: transparent;
  --fn-assistant-bubble-bg-gradient: none;
  --fn-assistant-bubble-border: transparent;
  --fn-assistant-glow-color: 13, 13, 13;

  --simple-user-bubble: #f4f4f4;
  --simple-code-bg: #f7f7f8;
  --simple-code-fg: #0d0d0d;
  --simple-quote-border: #dcdcdc;
}

html#octop-simple-theme-root[data-theme="dark"] {
  --simple-hairline: #2a2a2a;
  --simple-hairline-strong: #363636;
  --simple-hover: rgba(255, 255, 255, 0.07);
  --simple-press: rgba(255, 255, 255, 0.11);

  --fn-bg-primary: #212121;
  --fn-bg-base: #212121;
  --fn-bg-page: #212121;
  --fn-bg-layout: #212121;
  --fn-bg-container: #212121;
  --fn-bg-elevated: #2a2a2a;
  --fn-bg-secondary: #2f2f2f;
  --fn-bg-tertiary: #333333;
  --fn-bg-quaternary: rgba(255, 255, 255, 0.04);
  --fn-bg-subtle: #282828;
  --fn-bg-secondary-hover: #343434;
  --fn-bg-secondary-active: #3c3c3c;
  --fn-bg-hover: rgba(255, 255, 255, 0.07);
  --fn-bg-active: rgba(255, 255, 255, 0.11);
  --fn-bg-selected: rgba(255, 255, 255, 0.08);
  --fn-bg-code: #171717;
  --fn-bg-toolbar: #212121;
  --fn-bg-toolbar-hover: #2f2f2f;
  --fn-bg-input-label: #2f2f2f;
  --fn-bg-glass: rgba(33, 33, 33, 0.88);
  --fn-bg-sidebar: #171717;
  --fn-surface: #212121;
  --fn-surface-sunken: #171717;
  --fn-fill-hover: rgba(255, 255, 255, 0.07);
  --fn-fill-tertiary: #2f2f2f;

  --fn-text-primary: #ececec;
  --fn-text-secondary: #b7b7b7;
  --fn-text-tertiary: #969696;
  --fn-text-quaternary: #6f6f6f;
  --fn-text-placeholder: #8a8a8a;
  --fn-text-disabled: #5d5d5d;
  --fn-text-inverse: #0d0d0d;
  --fn-text-brand: #ececec;
  --fn-text-link: #ececec;
  --fn-text-danger: #ff8f85;
  --fn-logo-color: #ffffff;
  --fn-logo-filter: brightness(0) invert(1);

  --fn-border-primary: rgba(255, 255, 255, 0.1);
  --fn-border-secondary: rgba(255, 255, 255, 0.07);
  --fn-border-tertiary: rgba(255, 255, 255, 0.05);
  --fn-border-input: rgba(255, 255, 255, 0.15);
  --fn-border-input-alt: rgba(255, 255, 255, 0.1);
  --fn-border-focus: rgba(255, 255, 255, 0.3);
  --fn-border: rgba(255, 255, 255, 0.1);
  --fn-border-color: rgba(255, 255, 255, 0.1);
  --fn-border-strong: rgba(255, 255, 255, 0.22);
  --fn-border-subtle: rgba(255, 255, 255, 0.06);

  --fn-color-brand: #ececec;
  --fn-color-brand-hover: #ffffff;
  --fn-color-brand-soft: #ffffff;
  --fn-color-brand-bg: rgba(255, 255, 255, 0.08);
  --fn-color-brand-border: rgba(255, 255, 255, 0.18);
  --fn-color-on-brand: #0d0d0d;
  --fn-color-brand-light: #2f2f2f;
  --fn-color-brand-shadow: rgba(0, 0, 0, 0.45);
  --fn-color-brand-glow: rgba(255, 255, 255, 0.05);
  --fn-primary: #ececec;
  --fn-primary-bg: rgba(255, 255, 255, 0.1);
  --fn-color-primary: #ececec;
  --fn-accent: #ececec;

  --fn-sidebar-width: 260px;
  --fn-sidebar-bg: #171717;
  --fn-sidebar-border: transparent;
  --fn-sidebar-item-hover: rgba(255, 255, 255, 0.07);
  --fn-sidebar-item-active-bg: rgba(255, 255, 255, 0.1);
  --fn-sidebar-item-active: rgba(255, 255, 255, 0.08);
  --fn-sidebar-item-active-text: #ffffff;
  --fn-sidebar-group-text: #7a7a7a;
  --fn-header-bg: rgba(33, 33, 33, 0.88);
  --fn-chat-divider: transparent;

  --fn-shadow-xs: 0 1px 1px rgba(0, 0, 0, 0.3);
  --fn-shadow-sm: 0 1px 2px rgba(0, 0, 0, 0.35);
  --fn-shadow-md: 0 2px 6px rgba(0, 0, 0, 0.35), 0 12px 32px rgba(0, 0, 0, 0.4);
  --fn-shadow-lg: 0 4px 10px rgba(0, 0, 0, 0.4), 0 18px 48px rgba(0, 0, 0, 0.45);
  --fn-shadow-xl: 0 8px 20px rgba(0, 0, 0, 0.5), 0 28px 64px rgba(0, 0, 0, 0.55);
  --fn-card-border-normal: var(--simple-hairline);
  --fn-card-shadow-normal: none;

  --simple-user-bubble: #303030;
  --simple-code-bg: #0d0d0d;
  --simple-code-fg: #f2f2f2;
  --simple-quote-border: #3d3d3d;
}

/* ------------------------- 全局基底：字体与画布 ------------------------- */
html#octop-simple-theme-root {
  background: var(--fn-bg-primary);
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
  text-rendering: optimizeLegibility;
}
html#octop-simple-theme-root body,
html#octop-simple-theme-root .octop-app,
html#octop-simple-theme-root button,
html#octop-simple-theme-root input,
html#octop-simple-theme-root textarea,
html#octop-simple-theme-root select {
  font-family: "Simple Theme Sans", -apple-system, BlinkMacSystemFont, "Segoe UI",
    "PingFang SC", "Hiragino Sans GB", "Noto Sans CJK SC", "Noto Sans SC",
    "Microsoft YaHei", ui-sans-serif, system-ui, sans-serif;
  font-feature-settings: "cv02" 1, "cv03" 1, "cv04" 1, "ss01" 1;
  letter-spacing: 0;
}

/* 画布：应用会在 html.octop-chat-open 时把 body 刷成 --fn-bg-elevated，
   和布局底色差一档（#2a2a2a vs #212121），这里统一压回主底色。 */
html#octop-simple-theme-root body,
html#octop-simple-theme-root #root {
  background: var(--fn-bg-primary) !important;
  color: var(--fn-text-primary) !important;
}

/* 布局根字号：控制台写死 14，全站正文按 14 继承。抬到 16 后所有
   "rem/em 之外的继承值" 才会跟着正文走。 */
html#octop-simple-theme-root .octop-layout,
html#octop-simple-theme-root .octop-layout-content {
  font-size: 16px !important;
  background: var(--fn-bg-primary) !important;
}

/* 滚动条：细、无轨道、只在悬停加深 */
html#octop-simple-theme-root ::-webkit-scrollbar {
  width: 10px;
  height: 10px;
}
html#octop-simple-theme-root ::-webkit-scrollbar-track {
  background: transparent;
}
html#octop-simple-theme-root ::-webkit-scrollbar-thumb {
  background: var(--simple-hairline-strong);
  border: 3px solid transparent;
  border-radius: 980px;
  background-clip: content-box;
}
html#octop-simple-theme-root ::-webkit-scrollbar-thumb:hover {
  background: var(--fn-text-quaternary);
  background-clip: content-box;
}
html#octop-simple-theme-root ::selection {
  background: rgba(13, 13, 13, 0.14);
}
html#octop-simple-theme-root[data-theme="dark"] ::selection {
  background: rgba(255, 255, 255, 0.18);
}

/* 焦点环：只在键盘操作时出现 */
html#octop-simple-theme-root :focus-visible {
  outline: 2px solid var(--fn-text-secondary);
  outline-offset: 3px;
}

/* 过渡只保留颜色类，几何属性瞬时就位 */
html#octop-simple-theme-root * {
  transition-property: background-color, border-color, color, box-shadow, opacity !important;
  transition-duration: 0.12s !important;
  transition-timing-function: ease !important;
}

/* =========================================================================
   1. 侧栏：一片连续的浅灰，无边框、无分段控件感
   ========================================================================= */
html#octop-simple-theme-root [class*="index-module__sidebar__"] {
  background: var(--fn-bg-sidebar) !important;
  border-right: none !important;
  box-shadow: none !important;
}
html#octop-simple-theme-root [class*="index-module__sidebarWrapper"] {
  background: var(--fn-bg-sidebar) !important;
}
html#octop-simple-theme-root [class*="module__sidebarResizeHandle"],
html#octop-simple-theme-root [class*="RailEdgeControl-module__line"] {
  background: transparent !important;
}
html#octop-simple-theme-root [class*="RailEdgeControl-module__btn"] {
  width: 14px !important;
  height: 40px !important;
  min-width: 0 !important;
  border: none !important;
  border-radius: 8px !important;
  background: transparent !important;
  box-shadow: none !important;
  color: var(--fn-text-tertiary) !important;
  opacity: 0;
}
html#octop-simple-theme-root [class*="RailEdgeControl"]:hover [class*="RailEdgeControl-module__btn"] {
  opacity: 1;
  background: var(--simple-hover) !important;
}
html#octop-simple-theme-root [class*="RailEdgeControl-module__btn"] svg {
  width: 12px !important;
  height: 12px !important;
}

/* 侧栏内容留白 */
html#octop-simple-theme-root [class*="module__sessionList__"][class] {
  padding: 10px 8px 12px !important;
}

/* 搜索框：无边框的凹陷面，聚焦才显出轮廓 */
html#octop-simple-theme-root [class*="module__sessionSearchWrap"] {
  padding: 0 !important;
}
html#octop-simple-theme-root [class*="module__sessionSearchInput"] {
  height: 34px !important;
  padding-left: 30px !important;
  font-size: 14px !important;
  color: var(--fn-text-primary) !important;
  background: var(--fn-sidebar-item-hover) !important;
  border: 1px solid transparent !important;
  border-radius: 10px !important;
  box-shadow: none !important;
}
html#octop-simple-theme-root [class*="module__sessionSearchInput"]::placeholder {
  color: var(--fn-text-quaternary) !important;
}
html#octop-simple-theme-root [class*="module__sessionSearchInput"]:hover {
  background: var(--fn-bg-tertiary) !important;
}
html#octop-simple-theme-root [class*="module__sessionSearchInput"]:focus {
  background: var(--fn-bg-primary) !important;
  border-color: var(--simple-hairline-strong) !important;
}
html#octop-simple-theme-root [class*="module__sessionSearchIcon"],
html#octop-simple-theme-root [class*="module__sessionSearchWrap"] svg {
  color: var(--fn-text-tertiary) !important;
  width: 15px !important;
  height: 15px !important;
}

/* 分段标签（全部 / 专家 / 群组）→ 一行文字 */
html#octop-simple-theme-root [class*="module__sessionScopeTabs"] {
  background: transparent !important;
  border: none !important;
  box-shadow: none !important;
  padding: 0 !important;
  gap: 2px !important;
  margin: 8px 0 4px !important;
  height: auto !important;
}
html#octop-simple-theme-root [class*="module__sessionScopeTab__"] {
  height: 28px !important;
  min-height: 28px !important;
  padding: 0 8px !important;
  font-size: 13px !important;
  font-weight: 400 !important;
  color: var(--fn-text-tertiary) !important;
  background: transparent !important;
  border: none !important;
  border-radius: 8px !important;
  box-shadow: none !important;
}
html#octop-simple-theme-root [class*="module__sessionScopeTab__"]:hover {
  background: var(--fn-sidebar-item-hover) !important;
  color: var(--fn-text-primary) !important;
}
html#octop-simple-theme-root [class*="module__sessionScopeTabActive"] {
  background: var(--fn-sidebar-item-active-bg) !important;
  color: var(--fn-text-primary) !important;
  font-weight: 500 !important;
}

/* 专家行 / 专家卡 */
html#octop-simple-theme-root [class*="module__agentRow__"],
html#octop-simple-theme-root [class*="module__agentCardActive"] {
  border-radius: 10px !important;
  background: transparent !important;
  box-shadow: none !important;
  padding: 6px 8px !important;
}
html#octop-simple-theme-root [class*="module__agentRow__"]:hover {
  background: var(--fn-sidebar-item-hover) !important;
}
html#octop-simple-theme-root [class*="module__agentRowAvatar"],
html#octop-simple-theme-root [class*="module__agentCardAvatar"] {
  width: 24px !important;
  height: 24px !important;
  border-radius: 6px !important;
  background: var(--fn-bg-tertiary) !important;
  border: none !important;
}
html#octop-simple-theme-root [class*="module__agentRowName"],
html#octop-simple-theme-root [class*="module__agentCardName"] {
  font-size: 14px !important;
  font-weight: 500 !important;
  color: var(--fn-text-primary) !important;
  min-width: 0 !important;
  overflow: hidden !important;
  text-overflow: ellipsis !important;
  white-space: nowrap !important;
}
/* 头像里的 img 带内联 26/28px，会从 24px 的框里左右各溢出一两像素；
   改成撑满容器，图标就回到框中线上。 */
html#octop-simple-theme-root [class*="module__agentRowAvatar"] img,
html#octop-simple-theme-root [class*="module__agentCardAvatar"] img {
  width: 100% !important;
  height: 100% !important;
  max-width: 100% !important;
  display: block !important;
  object-fit: contain !important;
  border-radius: inherit !important;
}
/* 专家名 + 进行中标记：名称和圈圈同一条基线排布，名称自己省略 */
html#octop-simple-theme-root [class*="module__agentNameCluster"] {
  display: flex !important;
  align-items: center !important;
  gap: 6px !important;
  min-width: 0 !important;
}
html#octop-simple-theme-root .simple-agent-busy {
  flex: none !important;
  width: 11px !important;
  height: 11px !important;
  border-radius: 50% !important;
  border: 1.5px solid var(--simple-hairline-strong) !important;
  border-top-color: var(--fn-text-secondary) !important;
  animation: simple-agent-busy 800ms linear infinite;
}
@keyframes simple-agent-busy {
  to { transform: rotate(360deg); }
}
@media (prefers-reduced-motion: reduce) {
  html#octop-simple-theme-root .simple-agent-busy { animation-duration: 2.4s !important; }
}
/* 圈圈要靠"腾出位置"而不是"挤掉名字"：专家行里那两个「新建对话 / 置顶」
   按钮平时透明，但仍以 45px 占着文档流宽度；再加上圈圈自己的 6+11px，
   14px 的专家名就被压成省略号，圈圈正好落在被切掉的字上，看起来像圈圈
   遮住了名字。把这对悬浮按钮移出文档流（它们本来也只在 hover / focus
   时可见），名字就能完整显示，圈圈落在名字右侧的留白里。
   绝对定位挂在名字行上，卡片和列表两种形态共用一套。 */
html#octop-simple-theme-root [class*="module__agentRowNameRow"],
html#octop-simple-theme-root [class*="module__agentCardNameRow"] {
  position: relative !important;
}
html#octop-simple-theme-root [class*="module__agentRowNameRow"] > [class*="module__expertNavActions"],
html#octop-simple-theme-root [class*="module__agentCardNameRow"] > [class*="module__expertNavActions"] {
  position: absolute !important;
  top: 50% !important;
  right: 0 !important;
  margin: 0 !important;
  transform: translateY(-50%) !important;
  z-index: 3 !important;
}
/* 名字特别长时，悬浮按钮浮上来会盖住名字尾巴和圈圈。hover 时给名字区
   让出 46px，名字自动收成省略号，圈圈始终留在按钮左边。
   短名字本来就有余量，hover 前后不会跳动。 */
@media (hover: hover) {
  html#octop-simple-theme-root [class*="module__agentRowNameRow"]:hover [class*="module__agentNameCluster"],
  html#octop-simple-theme-root [class*="module__agentCardNameRow"]:hover [class*="module__agentNameCluster"],
  html#octop-simple-theme-root [class*="module__agentRowNameRow"]:focus-within [class*="module__agentNameCluster"],
  html#octop-simple-theme-root [class*="module__agentCardNameRow"]:focus-within [class*="module__agentNameCluster"] {
    padding-right: 46px !important;
  }
}
/* 插件页的"卡片/列表"切换标签：图标原来是贴着左边缘的，补一点内距让它和文字成组 */
html#octop-simple-theme-root [class*="module__viewModeLabel"] {
  padding-inline: 4px !important;
  gap: 5px !important;
  align-items: center !important;
}
html#octop-simple-theme-root [class*="module__agentRowDesc"],
html#octop-simple-theme-root [class*="module__agentCardDesc"] {
  font-size: 12px !important;
  line-height: 17px !important;
  color: var(--fn-text-tertiary) !important;
}
html#octop-simple-theme-root [class*="module__agentNewChatBtn"],
html#octop-simple-theme-root [class*="module__agentPinBtn"] {
  width: 22px !important;
  height: 22px !important;
  min-width: 0 !important;
  padding: 0 !important;
  border: none !important;
  border-radius: 6px !important;
  background: transparent !important;
  color: var(--fn-text-tertiary) !important;
  opacity: 0;
}
html#octop-simple-theme-root [class*="module__agentRow"]:hover [class*="module__agentNewChatBtn"],
html#octop-simple-theme-root [class*="module__agentCard"]:hover [class*="module__agentNewChatBtn"],
html#octop-simple-theme-root [class*="module__agentRow"]:hover [class*="module__agentPinBtn"],
html#octop-simple-theme-root [class*="module__agentCard"]:hover [class*="module__agentPinBtn"] {
  opacity: 1;
}

/* 会话行：32px 高、圆角 8、悬停才浮出底色与"更多" */
html#octop-simple-theme-root [class*="module__sessionRow__"] {
  min-height: 32px !important;
  padding: 0 8px !important;
  border: none !important;
  border-radius: 8px !important;
  box-shadow: none !important;
  font-size: 14px !important;
  color: var(--fn-text-secondary) !important;
  position: relative !important;
  gap: 8px !important;
}
html#octop-simple-theme-root [class*="module__sessionRow__"]:hover {
  background: var(--fn-sidebar-item-hover) !important;
  color: var(--fn-text-primary) !important;
}
html#octop-simple-theme-root [class*="module__sessionRowActive"] {
  background: var(--fn-sidebar-item-active-bg) !important;
  color: var(--fn-text-primary) !important;
  font-weight: 500 !important;
}
html#octop-simple-theme-root [class*="module__sessionRowTitle"] {
  font-size: 15px !important;
  line-height: 21px !important;
  color: inherit !important;
  overflow: hidden !important;
  text-overflow: ellipsis !important;
  white-space: nowrap !important;
}
html#octop-simple-theme-root [class*="module__sessionRowLead"] svg {
  width: 13px !important;
  height: 13px !important;
  color: var(--fn-text-quaternary) !important;
}
html#octop-simple-theme-root [class*="module__sessionRowMore"] {
  position: absolute !important;
  right: 4px !important;
  top: 50% !important;
  transform: translateY(-50%) !important;
  width: 22px !important;
  height: 22px !important;
  padding: 0 !important;
  border: none !important;
  border-radius: 6px !important;
  background: transparent !important;
  color: var(--fn-text-tertiary) !important;
  opacity: 0;
}
html#octop-simple-theme-root [class*="module__sessionRow__"]:hover [class*="module__sessionRowMore"] {
  opacity: 1;
}
html#octop-simple-theme-root [class*="module__sessionRowMore"]:hover {
  background: var(--fn-sidebar-item-active-bg) !important;
  color: var(--fn-text-primary) !important;
}

/* 导航分组标题 */
html#octop-simple-theme-root [class*="Sidebar-module__navGroupHeader"] {
  height: 24px !important;
  min-height: 24px !important;
  padding: 0 8px !important;
  margin-top: 10px !important;
}
html#octop-simple-theme-root [class*="Sidebar-module__navGroupLabel"],
html#octop-simple-theme-root [class*="navGroupLabel"] {
  font-size: 12px !important;
  font-weight: 500 !important;
  letter-spacing: 0.01em !important;
  color: var(--fn-text-quaternary) !important;
  text-transform: none !important;
}
html#octop-simple-theme-root [class*="Sidebar-module__navItemMain"],
html#octop-simple-theme-root [class*="module__navItemRow"] {
  height: 32px !important;
  min-height: 32px !important;
  padding: 0 8px !important;
  gap: 10px !important;
  border: none !important;
  border-radius: 8px !important;
  box-shadow: none !important;
  font-size: 15px !important;
  color: var(--fn-text-secondary) !important;
}
html#octop-simple-theme-root [class*="Sidebar-module__navItemMain"]:hover,
html#octop-simple-theme-root [class*="module__navItemRow"]:hover {
  background: var(--fn-sidebar-item-hover) !important;
  color: var(--fn-text-primary) !important;
}
html#octop-simple-theme-root [class*="Sidebar-module__navItemRow"] svg,
html#octop-simple-theme-root [class*="Sidebar-module__navItemMain"] svg {
  width: 16px !important;
  height: 16px !important;
  color: var(--fn-text-tertiary) !important;
}

/* 账号区与版本号 */
html#octop-simple-theme-root button[class*="AvatarDropdown-module__trigger"] {
  height: 44px !important;
  min-height: 44px !important;
  padding: 0 8px !important;
  border: none !important;
  border-radius: 10px !important;
  font-size: 13px !important;
}
html#octop-simple-theme-root button[class*="AvatarDropdown-module__trigger"]:hover {
  background: var(--fn-sidebar-item-hover) !important;
}
html#octop-simple-theme-root [class*="AvatarDropdown-module__accountAvatar"] {
  width: 22px !important;
  height: 22px !important;
  border-radius: 50% !important;
  background: var(--fn-bg-tertiary) !important;
}
html#octop-simple-theme-root [class*="AvatarDropdown-module__triggerName"] {
  font-size: 13px !important;
  color: var(--fn-text-primary) !important;
}
html#octop-simple-theme-root [class*="module__versionBadge__"] {
  display: inline-flex !important;
  align-items: center !important;
  justify-content: center !important;
  line-height: 16px !important;
  white-space: nowrap !important;
  flex-shrink: 0 !important;
  font-size: 11px !important;
  color: var(--fn-text-quaternary) !important;
  background: transparent !important;
  border: none !important;
  padding: 0 !important;
  height: auto !important;
  min-height: 0 !important;
}
html#octop-simple-theme-root [class*="nav-badge"] {
  font-size: 10px !important;
  font-weight: 500 !important;
  color: var(--fn-text-secondary) !important;
  background: var(--fn-bg-tertiary) !important;
  border-radius: 980px !important;
  padding: 0 6px !important;
}

/* =========================================================================
   2. 对话页骨架：单列中轴
   ========================================================================= */
html#octop-simple-theme-root [class*="module__chatPage"],
html#octop-simple-theme-root [class*="module__chatMain"],
html#octop-simple-theme-root [class*="module__chatContent"] {
  background: var(--fn-bg-primary) !important;
}
html#octop-simple-theme-root [class*="module__messageListWrapper"] {
  background: var(--fn-bg-primary) !important;
}
html#octop-simple-theme-root [class*="module__messageList__"][class] {
  padding: 24px 0 12px !important;
}
html#octop-simple-theme-root [class*="module__messageListInner"] {
  max-width: calc(var(--simple-column) + 40px) !important;
  margin-inline: auto !important;
  /* 消息区比输入区窄一个滚动条宽度（5px）。左右内边距故意不对称，让正文
     左边缘和输入框、标题、免责声明落在同一条竖线上。 */
  padding: 0 15px 0 25px !important;
}

/* 头像列整列拆掉：48px 1fr 48px 的三列网格收成一列，并把钉在 grid-column:2
   的子元素解出来，否则正文会一直缩进 48px、宽度少 96px。 */
html#octop-simple-theme-root [class*="module__turnInset"],
html#octop-simple-theme-root [class*="module__assistantBubble"],
html#octop-simple-theme-root [class*="module__userBubble"],
html#octop-simple-theme-root [class*="module__processSummaryRow"] {
  grid-template-columns: minmax(0, 1fr) !important;
  gap: 0 !important;
}
html#octop-simple-theme-root [class*="module__turnInset"] > *,
html#octop-simple-theme-root [class*="module__assistantBubble"] > *,
html#octop-simple-theme-root [class*="module__userBubble"] > *,
html#octop-simple-theme-root [class*="module__processSummaryRow"] > * {
  grid-column: 1 / -1 !important;
}
html#octop-simple-theme-root [class*="module__avatarCol"] {
  display: none !important;
}
html#octop-simple-theme-root [class*="module__msgSender"],
html#octop-simple-theme-root [class*="module__msgSenderBtn"],
html#octop-simple-theme-root [class*="module__msgUserAvatar"] {
  display: none !important;
}

html#octop-simple-theme-root [class*="module__assistantTurn"] {
  display: flex !important;
  flex-direction: column !important;
  gap: 4px !important;
  margin-bottom: 26px !important;
}
html#octop-simple-theme-root [class*="module__assistantTurnAnswer"],
html#octop-simple-theme-root [class*="module__assistantBubble"],
html#octop-simple-theme-root [class*="module__bubbleContent"] {
  width: 100% !important;
  max-width: none !important;
  padding: 0 !important;
}

/* 顶栏：48px、透明、标题回到 14px 次级灰 */
html#octop-simple-theme-root [class*="module__chatTitleBar__"] {
  height: 48px !important;
  min-height: 48px !important;
  flex: 0 0 48px !important;
  padding: 0 20px !important;
  background: transparent !important;
  border-bottom: none !important;
  box-shadow: none !important;
}
html#octop-simple-theme-root [class*="module__chatTitleLeft"] {
  max-width: var(--simple-column) !important;
  width: 100% !important;
  margin-inline: auto !important;
  padding: 0 !important;
  gap: 6px !important;
}
html#octop-simple-theme-root [class*="module__chatTitleLeadingIcon"] {
  display: none !important;
}
html#octop-simple-theme-root [class*="module__chatTitleText"] {
  font-size: 16px !important;
  font-weight: 500 !important;
  line-height: 22px !important;
  color: var(--fn-text-secondary) !important;
  letter-spacing: 0 !important;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
html#octop-simple-theme-root [class*="module__chatTitleEditBtn"] {
  width: 26px !important;
  height: 26px !important;
  min-width: 0 !important;
  padding: 0 !important;
  border: none !important;
  border-radius: 8px !important;
  background: transparent !important;
  color: var(--fn-text-tertiary) !important;
  opacity: 0;
}
html#octop-simple-theme-root [class*="module__chatTitleBar__"]:hover [class*="module__chatTitleEditBtn"],
html#octop-simple-theme-root [class*="module__chatTitleEditBtn"]:focus-visible {
  opacity: 1;
}
html#octop-simple-theme-root [class*="module__chatTitleEditBtn"]:hover {
  background: var(--simple-hover) !important;
  color: var(--fn-text-primary) !important;
}

/* =========================================================================
   3. 消息：助手纯文字，用户一枚浅灰圆角块
   ========================================================================= */
html#octop-simple-theme-root [class*="module__messageBubble"] {
  background: transparent !important;
  border: none !important;
  border-radius: 0 !important;
  box-shadow: none !important;
  padding: 0 !important;
}
html#octop-simple-theme-root [class*="module__assistantText"] {
  width: 100% !important;
  padding: 0 !important;
  border: none !important;
  border-radius: 0 !important;
  background: transparent !important;
  box-shadow: none !important;
  font-size: 16px !important;
  line-height: 27px !important;
  color: var(--fn-text-primary) !important;
}

/* 用户消息：靠右、最大 80% 宽、圆角 18 */
html#octop-simple-theme-root [class*="module__userBubble"] {
  justify-content: flex-end !important;
  margin: 6px 0 26px !important;
}
/* 用户消息的 bubbleContent 默认是 flex 行：气泡在左、时间/复制/编辑那行在右。
   改成纵向排列，气泡在上、操作行在下（右对齐贴着气泡右边缘）。 */
html#octop-simple-theme-root [class*="module__userBubble"] [class*="module__bubbleContent"] {
  display: flex !important;
  flex-direction: column !important;
  flex-wrap: nowrap !important;
  justify-content: flex-end !important;
  align-items: flex-end !important;
  gap: 0 !important;
}
html#octop-simple-theme-root [class*="module__userBubble"] [class*="module__userMsgRow"] {
  display: flex !important;
  justify-content: flex-end !important;
  max-width: 100% !important;
}
html#octop-simple-theme-root [class*="module__userText"],
html#octop-simple-theme-root [class*="module__userMsgText"] {
  display: inline-block !important;
  max-width: min(620px, 80vw) !important;
  padding: 10px 16px !important;
  border: none !important;
  border-radius: 18px !important;
  background: var(--simple-user-bubble) !important;
  color: var(--fn-text-primary) !important;
  box-shadow: none !important;
  font-size: 16px !important;
  line-height: 26px !important;
  white-space: pre-wrap;
}

/* 正文 Markdown */
html#octop-simple-theme-root [class*="module__markdownBody"] {
  font-size: 16px !important;
  line-height: 27px !important;
  color: inherit !important;
  letter-spacing: -0.001em;
}
html#octop-simple-theme-root [class*="module__markdownBody"] > *:first-child {
  margin-top: 0 !important;
}
html#octop-simple-theme-root [class*="module__markdownBody"] > *:last-child {
  margin-bottom: 0 !important;
}
html#octop-simple-theme-root [class*="module__markdownBody"] p {
  margin: 0 0 14px !important;
}
html#octop-simple-theme-root [class*="module__markdownBody"] h1,
html#octop-simple-theme-root [class*="module__markdownBody"] h2,
html#octop-simple-theme-root [class*="module__markdownBody"] h3,
html#octop-simple-theme-root [class*="module__markdownBody"] h4 {
  margin: 24px 0 10px !important;
  font-weight: 600 !important;
  line-height: 1.35 !important;
  letter-spacing: -0.012em !important;
  color: var(--fn-text-primary) !important;
}
html#octop-simple-theme-root [class*="module__markdownBody"] h1 {
  font-size: 24px !important;
}
html#octop-simple-theme-root [class*="module__markdownBody"] h2 {
  font-size: 20px !important;
}
html#octop-simple-theme-root [class*="module__markdownBody"] h3 {
  font-size: 17px !important;
}
html#octop-simple-theme-root [class*="module__markdownBody"] h4 {
  font-size: 16px !important;
}
html#octop-simple-theme-root [class*="module__markdownBody"] ul,
html#octop-simple-theme-root [class*="module__markdownBody"] ol {
  margin: 0 0 14px !important;
  padding-left: 22px !important;
}
html#octop-simple-theme-root [class*="module__markdownBody"] li {
  margin: 3px 0 !important;
}
html#octop-simple-theme-root [class*="module__markdownBody"] li::marker {
  color: var(--fn-text-quaternary);
}
html#octop-simple-theme-root [class*="module__markdownBody"] strong {
  font-weight: 600 !important;
}
html#octop-simple-theme-root [class*="module__markdownBody"] a {
  color: inherit !important;
  text-decoration: underline;
  text-decoration-thickness: 1px;
  text-underline-offset: 2px;
  text-decoration-color: var(--fn-text-quaternary);
}
html#octop-simple-theme-root [class*="module__markdownBody"] a:hover {
  text-decoration-color: currentColor;
}
html#octop-simple-theme-root [class*="module__markdownBody"] blockquote {
  margin: 14px 0 !important;
  padding: 2px 0 2px 14px !important;
  border-left: 2px solid var(--simple-quote-border) !important;
  background: transparent !important;
  border-radius: 0 !important;
  color: var(--fn-text-secondary) !important;
}
html#octop-simple-theme-root [class*="module__markdownBody"] blockquote p {
  margin: 0 0 8px !important;
}
html#octop-simple-theme-root [class*="module__markdownBody"] hr {
  height: 0 !important;
  margin: 24px 0 !important;
  border: none !important;
  border-top: 1px solid var(--simple-hairline) !important;
}
html#octop-simple-theme-root [class*="module__markdownBody"] :not(pre) > code,
html#octop-simple-theme-root [class*="module__inlineCode"] {
  padding: 1px 5px !important;
  border: none !important;
  border-radius: 5px !important;
  background: var(--fn-bg-code) !important;
  color: inherit !important;
  font-family: ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, monospace !important;
  font-size: 14px !important;
}
html#octop-simple-theme-root [class*="module__markdownBody"] pre {
  margin: 14px 0 !important;
  padding: 0 !important;
  border: none !important;
  background: transparent !important;
  font-size: 14px !important;
  overflow: visible !important;
}
html#octop-simple-theme-root [class*="module__codeBlockWrapper"] {
  margin: 14px 0 !important;
  padding: 0 !important;
  border: 1px solid var(--simple-hairline) !important;
  border-radius: 12px !important;
  background: var(--simple-code-bg) !important;
  box-shadow: none !important;
  overflow: hidden !important;
}
html#octop-simple-theme-root [class*="module__codeBlockHeader"] {
  height: 34px !important;
  min-height: 34px !important;
  padding: 0 10px 0 14px !important;
  border-bottom: 1px solid var(--simple-hairline) !important;
  background: transparent !important;
}
html#octop-simple-theme-root [class*="module__codeBlockLang"] {
  font-size: 12px !important;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace !important;
  color: var(--fn-text-tertiary) !important;
}
html#octop-simple-theme-root [class*="module__codeCopyBtn"] {
  width: 24px !important;
  height: 24px !important;
  min-width: 0 !important;
  padding: 0 !important;
  border: none !important;
  border-radius: 6px !important;
  background: transparent !important;
  color: var(--fn-text-tertiary) !important;
}
html#octop-simple-theme-root [class*="module__codeCopyBtn"]:hover {
  background: var(--simple-hover) !important;
  color: var(--fn-text-primary) !important;
}
html#octop-simple-theme-root [class*="module__codeBlockWrapper"] pre,
html#octop-simple-theme-root [class*="module__codeBlockWrapper"] code {
  margin: 0 !important;
  padding: 14px 16px !important;
  background: transparent !important;
  color: var(--simple-code-fg) !important;
  line-height: 1.6 !important;
}
html#octop-simple-theme-root [class*="module__markdownBody"] table {
  width: auto !important;
  margin: 14px 0 !important;
  border-collapse: collapse !important;
  font-size: 14px !important;
}
html#octop-simple-theme-root [class*="module__markdownBody"] th,
html#octop-simple-theme-root [class*="module__markdownBody"] td {
  padding: 8px 14px !important;
  border: none !important;
  border-bottom: 1px solid var(--simple-hairline) !important;
  text-align: left !important;
}
html#octop-simple-theme-root [class*="module__markdownBody"] th {
  font-size: 13px !important;
  font-weight: 600 !important;
  color: var(--fn-text-secondary) !important;
}
html#octop-simple-theme-root [class*="module__markdownBody"] img {
  max-width: 100% !important;
  border-radius: 12px !important;
}
html#octop-simple-theme-root [class*="module__tableWrapper"] {
  border: none !important;
  border-radius: 0 !important;
  background: transparent !important;
}
html#octop-simple-theme-root [class*="module__messageImages"] img,
html#octop-simple-theme-root [class*="toolMediaImage"] {
  border-radius: 12px !important;
  border: 1px solid var(--simple-hairline) !important;
}

/* 元信息：默认看不见，悬停该条消息才浮出 */
html#octop-simple-theme-root [class*="module__msgMetaRow"] {
  margin-top: 6px !important;
  padding: 0 !important;
  height: 24px !important;
  gap: 2px !important;
  opacity: 0;
}
html#octop-simple-theme-root [class*="module__messageBubble"]:hover [class*="module__msgMetaRow"],
html#octop-simple-theme-root [class*="module__assistantTurn"]:hover [class*="module__msgMetaRow"] {
  opacity: 1;
}
/* 用户消息的时间/复制/编辑行：不再挂在气泡右侧，改为气泡下方一行、右对齐 */
html#octop-simple-theme-root [class*="module__userBubble"] [class*="module__msgMetaRow"] {
  width: auto !important;
  max-width: 100% !important;
  align-self: flex-end !important;
  justify-content: flex-end !important;
  margin: 2px 0 0 !important;
  padding: 0 !important;
  gap: 2px !important;
}
html#octop-simple-theme-root [class*="module__msgTime"],
html#octop-simple-theme-root [class*="module__msgUsage"] {
  font-size: 12px !important;
  line-height: 16px !important;
  color: var(--fn-text-quaternary) !important;
}
html#octop-simple-theme-root [class*="module__msgCopyBtn"],
html#octop-simple-theme-root [class*="module__msgActionBtn"] {
  width: 24px !important;
  height: 24px !important;
  min-width: 0 !important;
  padding: 0 !important;
  border: none !important;
  border-radius: 6px !important;
  background: transparent !important;
  color: var(--fn-text-tertiary) !important;
}
html#octop-simple-theme-root [class*="module__msgCopyBtn"]:hover,
html#octop-simple-theme-root [class*="module__msgActionBtn"]:hover {
  background: var(--simple-hover) !important;
  color: var(--fn-text-primary) !important;
}
html#octop-simple-theme-root [class*="module__msgCopyBtn"] svg,
html#octop-simple-theme-root [class*="module__msgActionBtn"] svg {
  width: 14px !important;
  height: 14px !important;
}

/* 「收起这条回复 / 回到开头」两个图标按钮：挂在消息操作行里（从此处分叉右边），
   和复制 / 朗读 / 重新生成同一套尺寸与配色。 */
html#octop-simple-theme-root .simple-msg-btn {
  display: inline-flex !important;
  align-items: center !important;
  justify-content: center !important;
  width: 24px !important;
  height: 24px !important;
  min-width: 0 !important;
  margin: 0 !important;
  padding: 0 !important;
  border: none !important;
  border-radius: 6px !important;
  background: transparent !important;
  box-shadow: none !important;
  color: var(--fn-text-tertiary) !important;
  cursor: pointer !important;
  transition-property: background-color, color !important;
  transition-duration: 0.15s !important;
}
html#octop-simple-theme-root .simple-msg-btn svg {
  width: 14px !important;
  height: 14px !important;
  flex: none !important;
}
html#octop-simple-theme-root .simple-msg-btn:hover {
  background: var(--simple-hover) !important;
  color: var(--fn-text-primary) !important;
}
html#octop-simple-theme-root .simple-msg-btn:focus-visible {
  outline: 2px solid var(--fn-text-tertiary) !important;
  outline-offset: 1px !important;
}

/* 思维链（思考 + 工具调用）正文下面那个「收起思考与工具」 */
html#octop-simple-theme-root .simple-process-collapse {
  display: flex !important;
  justify-content: flex-start !important;
  align-items: center !important;
  gap: 2px !important;
  margin: 6px 0 2px !important;
  padding: 0 !important;
  height: 24px !important;
}
html#octop-simple-theme-root .simple-collapse-btn {
  display: inline-flex !important;
  align-items: center !important;
  justify-content: center !important;
  gap: 4px !important;
  height: 22px !important;
  margin: 0 !important;
  padding: 0 6px !important;
  border: none !important;
  border-radius: 8px !important;
  background: transparent !important;
  box-shadow: none !important;
  color: var(--fn-text-tertiary) !important;
  font-size: 11.5px !important;
  font-weight: 500 !important;
  line-height: 1 !important;
  cursor: pointer !important;
  transition-property: background-color, color !important;
  transition-duration: 0.15s !important;
}
html#octop-simple-theme-root .simple-collapse-btn svg {
  width: 13px !important;
  height: 13px !important;
  flex: none !important;
}
html#octop-simple-theme-root .simple-collapse-btn:hover {
  background: var(--simple-hover) !important;
  color: var(--fn-text-primary) !important;
}
html#octop-simple-theme-root .simple-collapse-btn:focus-visible {
  outline: 2px solid var(--fn-text-tertiary) !important;
  outline-offset: 1px !important;
}
/* 点了之后立刻生效，不等 React 那一帧 */
html#octop-simple-theme-root [class*="module__processSummaryRow"].simple-process-hiding {
  max-height: 32px !important;
  overflow: hidden !important;
}

/* 收起态：过程摘要只留那行标题，过程卡片（任务进度 / 预览）先收掉，
   正文夹到 300px 并渐隐 —— 夹的是正文本身，操作行（含这两个按钮）要留在外面。 */
html#octop-simple-theme-root .simple-turn-collapsed > [class*="module__processSummaryRow"] {
  max-height: 32px !important;
  overflow: hidden !important;
}
html#octop-simple-theme-root .simple-turn-collapsed > [class*="module__turnInset"] {
  display: none !important;
}
html#octop-simple-theme-root .simple-turn-collapsed.simple-turn-has-meta [class*="module__assistantText"],
html#octop-simple-theme-root .simple-turn-collapsed:not(.simple-turn-has-meta) [class*="module__assistantTurnAnswer"] {
  max-height: 300px !important;
  overflow: hidden !important;
  -webkit-mask-image: linear-gradient(to bottom, #000 72%, transparent 100%) !important;
  mask-image: linear-gradient(to bottom, #000 72%, transparent 100%) !important;
}

/* 思考 / 工具过程：压成一行 14px 灰字，像 "Thought for 6s" */
html#octop-simple-theme-root [class*="module__processSummary__"] {
  width: 100% !important;
  max-width: none !important;
  margin: 0 0 10px !important;
  padding: 0 !important;
  border: none !important;
  border-radius: 0 !important;
  background: transparent !important;
  box-shadow: none !important;
}
html#octop-simple-theme-root [class*="module__processSummaryToggle"] {
  display: inline-flex !important;
  align-items: center !important;
  justify-content: flex-start !important;
  width: auto !important;
  height: 26px !important;
  min-height: 26px !important;
  padding: 0 6px 0 0 !important;
  margin: 0 !important;
  border: none !important;
  border-radius: 6px !important;
  background: transparent !important;
  color: var(--fn-text-tertiary) !important;
  font-size: 16px !important;
  line-height: 24px !important;
  gap: 5px !important;
}
html#octop-simple-theme-root [class*="module__processSummaryToggle"]:hover {
  color: var(--fn-text-primary) !important;
}
html#octop-simple-theme-root [class*="module__processSummaryText__"] {
  width: auto !important; margin: 0 !important; padding: 0 !important;
  line-height: 24px !important; flex: 0 1 auto !important;
  font-size: 16px !important;
  font-weight: 400 !important;
  color: inherit !important;
}
html#octop-simple-theme-root [class*="module__processLiveLabel__"] {
  display: inline-flex !important; align-items: center !important;
  margin: 0 !important; line-height: 24px !important;
  font-size: 16px !important;
  color: inherit !important;
}
html#octop-simple-theme-root [class*="module__processSummaryToggle"] svg {
  width: 13px !important;
  height: 13px !important;
  opacity: 0.8;
}
html#octop-simple-theme-root [class*="module__processSummaryBody"] {
  margin: 2px 0 10px !important;
  padding: 4px 0 0 12px !important;
  border-top: none !important;
  border-left: 1px solid var(--simple-hairline) !important;
}
html#octop-simple-theme-root [class*="module__processThinkingItem"] {
  margin: 0 0 6px !important;
  padding: 0 !important;
  border: none !important;
  background: transparent !important;
}
html#octop-simple-theme-root [class*="module__processThinkingItem"] [class*="module__markdownBody"] {
  font-size: 14px !important;
  line-height: 22px !important;
  color: var(--fn-text-secondary) !important;
}
html#octop-simple-theme-root [class*="module__processThinkingItem"] [class*="module__markdownBody"] p {
  margin: 0 0 6px !important;
}
html#octop-simple-theme-root [class*="module__inlineToolBlock"] {
  margin: 2px 0 !important;
  padding: 0 !important;
  border: none !important;
  background: transparent !important;
  font-size: 13px !important;
  color: var(--fn-text-tertiary) !important;
}
html#octop-simple-theme-root [class*="module__inlineToolIcon"] {
  display: none !important;
}
html#octop-simple-theme-root [class*="module__inlineToolName"] {
  font-size: 13px !important;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace !important;
  color: var(--fn-text-tertiary) !important;
}
html#octop-simple-theme-root [class*="module__inlineToolSummary"],
html#octop-simple-theme-root [class*="module__inlineToolStatus"] {
  font-size: 12px !important;
  color: var(--fn-text-quaternary) !important;
}

/* 待办面板：一层发丝线边框，不再套卡片 */
html#octop-simple-theme-root [class*="module__todoProgressPanel"] {
  margin: 10px 0 !important;
  padding: 10px 14px !important;
  border: 1px solid transparent !important;
  border-radius: 12px !important;
  background: transparent !important;
  box-shadow: none !important;
  font-size: 13px !important;
}
html#octop-simple-theme-root [class*="module__todoListBlock"] {
  border: none !important;
  border-radius: 0 !important;
  background: transparent !important;
  padding: 0 !important;
}
html#octop-simple-theme-root [class*="module__todoListTitle"],
html#octop-simple-theme-root [class*="module__todoListSummary"] {
  font-size: 12px !important;
  font-weight: 500 !important;
  color: var(--fn-text-tertiary) !important;
}
html#octop-simple-theme-root [class*="module__todoListItem"] {
  margin: 3px 0 !important;
  font-size: 13px !important;
  color: var(--fn-text-secondary) !important;
}
html#octop-simple-theme-root [class*="module__todoListTextCompleted"] {
  color: var(--fn-text-quaternary) !important;
}

/* 文件卡片 / 打开浏览器提示 */
html#octop-simple-theme-root [class*="module__messageFileCard"] {
  border: 1px solid var(--simple-hairline) !important;
  border-radius: 10px !important;
  background: transparent !important;
  box-shadow: none !important;
}
html#octop-simple-theme-root [class*="module__messageFileName"] {
  font-size: 13px !important;
  color: var(--fn-text-secondary) !important;
}
html#octop-simple-theme-root [class*="module__openBrowserPrompt__"] {
  display: inline-flex !important; align-items: center !important; gap: 8px !important;
  height: 32px !important;
  padding: 0 12px !important;
  border: 0 !important;
  border-radius: 12px !important;
  background: var(--fn-bg-secondary) !important;
  color: var(--fn-text-secondary) !important;
  font-size: 13px !important;
  box-shadow: none !important;
}
html#octop-simple-theme-root [class*="module__openBrowserPrompt__"]:hover {
  background: var(--simple-hover) !important;
}

/* 回到底部 */
html#octop-simple-theme-root [class*="module__scrollToBottomBtn__"] {
  display: inline-flex !important; align-items: center !important; justify-content: center !important;
  width: max-content !important; max-width: calc(100% - 32px) !important;
  height: 36px !important;
  min-width: 36px !important;
  padding: 0 12px !important; gap: 6px !important; white-space: nowrap !important;
  border: 0 !important;
  border-radius: 12px !important;
  background: var(--fn-bg-elevated) !important;
  color: var(--fn-text-secondary) !important;
  box-shadow: var(--fn-shadow-sm) !important;
  font-size: 12px !important;
}

/* 右侧悬浮按钮列：去掉圆球外壳，只留图标 */
html#octop-simple-theme-root [class*="module__chatFloatActions"] {
  gap: 2px !important;
  padding: 18px 8px !important;
}
html#octop-simple-theme-root [class*="module__chatFloatBtnWrap"] {
  width: 30px !important;
  height: 30px !important;
}
html#octop-simple-theme-root [class*="module__chatFloatBtn"],
html#octop-simple-theme-root [class*="module__installBtnChatFloat"],
html#octop-simple-theme-root [class*="module__agentProfileBtn"],
html#octop-simple-theme-root [class*="module__terminalFloatBtn"],
html#octop-simple-theme-root [class*="module__browserStatusBtn"] {
  width: 30px !important;
  height: 30px !important;
  min-width: 0 !important;
  padding: 0 !important;
  border: none !important;
  border-radius: 8px !important;
  background: transparent !important;
  color: var(--fn-text-tertiary) !important;
  box-shadow: none !important;
  opacity: 0.85;
}
html#octop-simple-theme-root [class*="module__chatFloatBtn"]:hover,
html#octop-simple-theme-root [class*="module__installBtnChatFloat"]:hover,
html#octop-simple-theme-root [class*="module__agentProfileBtn"]:hover,
html#octop-simple-theme-root [class*="module__terminalFloatBtn"]:hover,
html#octop-simple-theme-root [class*="module__browserStatusBtn"]:hover {
  background: var(--simple-hover) !important;
  color: var(--fn-text-primary) !important;
  opacity: 1;
}
html#octop-simple-theme-root [class*="module__chatFloatBadge"] {
  min-width: 16px !important;
  height: 16px !important;
  padding: 0 4px !important;
  border-radius: 980px !important;
  background: var(--fn-text-primary) !important;
  color: var(--fn-bg-primary) !important;
  font-size: 10px !important;
  font-weight: 600 !important;
  line-height: 16px !important;
  box-shadow: 0 0 0 2px var(--fn-bg-primary) !important;
}

/* =========================================================================
   4. 输入框（composer）
   ========================================================================= */
html#octop-simple-theme-root [class*="module__chatInput"] {
  padding: 8px 20px 4px !important;
  background: transparent !important;
}
html#octop-simple-theme-root [class*="module__inputWrapper"] {
  width: 100% !important;
  max-width: var(--simple-column) !important;
  margin-inline: auto !important;
  padding: 8px 16px !important;
  border: 1px solid var(--simple-hairline-strong) !important;
  border-radius: 16px !important;
  background: var(--fn-bg-primary) !important;
  box-shadow: var(--fn-shadow-sm) !important;
  gap: 0 !important;
  /* 组件本身是 column 弹性盒，默认 align-items 会把 inputRow / actionsRow
     缩成内容宽度（textarea 只剩 184px）。必须拉回整行。 */
  align-items: stretch !important;
}
html#octop-simple-theme-root [class*="module__inputWrapper__"]:focus-within {
  border-color: transparent !important;
  box-shadow: none !important;
}
html#octop-simple-theme-root[data-theme="dark"] [class*="module__inputWrapper__"] {
  background: var(--fn-bg-secondary) !important;
  border-color: transparent !important;
  box-shadow: none !important;
}
html#octop-simple-theme-root[data-theme="dark"] [class*="module__inputWrapper__"]:focus-within {
  border-color: transparent !important;
}
html#octop-simple-theme-root [class*="module__inputRow"] {
  display: flex !important;
  width: 100% !important;
  align-items: flex-end !important;
  min-height: 26px !important;
  padding: 0 !important;
  gap: 8px !important;
}
html#octop-simple-theme-root [class*="module__textarea"] {
  height: auto !important;
  min-height: 26px !important;
  max-height: 216px !important;
  padding: 5px 0 !important;
  border: none !important;
  border-radius: 0 !important;
  background: transparent !important;
  box-shadow: none !important;
  font-size: 16px !important;
  line-height: 24px !important;
  color: var(--fn-text-primary) !important;
  resize: none !important;
  field-sizing: content;
}
html#octop-simple-theme-root [class*="module__textarea"]::placeholder {
  color: var(--fn-text-placeholder) !important;
}

/* 输入区只常显「+ / 麦克风 / 发送」，其余图标悬停或聚焦才淡入 */
html#octop-simple-theme-root [class*="module__actionsRow"] {
  width: 100% !important;
  padding: 4px 0 0 !important;
  margin: 0 !important;
  border-top: none !important;
  gap: 2px !important;
  min-height: 0 !important;
  align-items: center !important;
}
html#octop-simple-theme-root [class*="module__secondaryActions"],
html#octop-simple-theme-root [class*="module__inputActions"] {
  gap: 2px !important;
  padding: 0 !important;
  align-items: center !important;
}
html#octop-simple-theme-root [class*="module__secondaryBtn"],
html#octop-simple-theme-root [class*="module__newChatBtn"] {
  width: 30px !important;
  height: 30px !important;
  min-width: 0 !important;
  min-height: 0 !important;
  flex: 0 0 auto !important;
  padding: 0 !important;
  border: none !important;
  border-radius: 980px !important;
  background: transparent !important;
  color: var(--fn-text-secondary) !important;
  box-shadow: none !important;
}
html#octop-simple-theme-root [class*="module__secondaryBtn"]:hover,
html#octop-simple-theme-root [class*="module__newChatBtn"]:hover {
  background: var(--simple-hover) !important;
  color: var(--fn-text-primary) !important;
}
html#octop-simple-theme-root [class*="module__secondaryBtn"] svg,
html#octop-simple-theme-root [class*="module__newChatBtn"] svg {
  width: 17px !important;
  height: 17px !important;
}
html#octop-simple-theme-root [class*="module__secondaryActions"] [class*="module__secondaryBtn"]:nth-child(n + 2),
html#octop-simple-theme-root [class*="module__newChatBtn"],
html#octop-simple-theme-root [class*="module__contextRingBtn"] {
  opacity: 0;
}
html#octop-simple-theme-root [class*="module__inputWrapper"]:hover [class*="module__secondaryBtn"],
html#octop-simple-theme-root [class*="module__inputWrapper"]:hover [class*="module__newChatBtn"],
html#octop-simple-theme-root [class*="module__inputWrapper"]:hover [class*="module__contextRingBtn"],
html#octop-simple-theme-root [class*="module__inputWrapper"]:focus-within [class*="module__secondaryBtn"],
html#octop-simple-theme-root [class*="module__inputWrapper"]:focus-within [class*="module__newChatBtn"],
html#octop-simple-theme-root [class*="module__inputWrapper"]:focus-within [class*="module__contextRingBtn"] {
  opacity: 1;
}
html#octop-simple-theme-root [class*="module__contextRingBtn"] {
  width: 28px !important;
  height: 28px !important;
  min-width: 0 !important;
}
html#octop-simple-theme-root [class*="module__contextRingLabel"] {
  font-size: 9px !important;
  color: var(--fn-text-quaternary) !important;
}
html#octop-simple-theme-root [class*="module__sendBtn"] {
  width: 32px !important;
  height: 32px !important;
  min-width: 0 !important;
  min-height: 0 !important;
  flex: 0 0 auto !important;
  padding: 0 !important;
  border: none !important;
  border-radius: 980px !important;
  background: var(--fn-color-brand) !important;
  color: var(--fn-color-on-brand) !important;
  box-shadow: none !important;
}
html#octop-simple-theme-root [class*="module__sendBtn"]:hover:not(:disabled) {
  background: var(--fn-color-brand-hover) !important;
  transform: none !important;
}
html#octop-simple-theme-root [class*="module__sendBtn"]:disabled {
  background: var(--fn-bg-tertiary) !important;
  color: var(--fn-text-quaternary) !important;
  opacity: 1 !important;
}
html#octop-simple-theme-root [class*="module__sendBtn"] svg {
  width: 17px !important;
  height: 17px !important;
}

/* 上下文小标签 */
html#octop-simple-theme-root [class*="module__imagePreviewBar"] {
  gap: 6px !important;
  padding: 0 0 6px !important;
  margin: 0 !important;
}
html#octop-simple-theme-root [class*="module__contextChip__"] {
  display: inline-flex !important; align-items: center !important; gap: 6px !important;
  width: max-content !important; max-width: 100% !important; min-width: 0 !important;
  height: 28px !important; min-height: 28px !important;
  padding: 0 8px !important;
  border: 0 !important; border-radius: 10px !important;
  background: var(--fn-bg-primary) !important;
  color: var(--fn-text-secondary) !important;
  font-size: 12px !important; line-height: 18px !important;
  box-sizing: border-box !important; overflow: hidden !important;
}
html#octop-simple-theme-root [class*="module__contextChipIcon__"] {
  display: inline-flex !important; align-items: center !important; justify-content: center !important;
  flex: 0 0 14px !important; width: 14px !important; height: 14px !important;
  min-height: 0 !important; padding: 0 !important; background: transparent !important;
}
html#octop-simple-theme-root [class*="module__contextChipLabel__"] {
  display: block !important; flex: 0 1 auto !important;
  min-width: 0 !important; width: auto !important; height: auto !important;
  min-height: 0 !important; padding: 0 !important; margin: 0 !important;
  font-size: 12px !important; line-height: 18px !important; font-weight: 500 !important;
  white-space: nowrap !important; overflow: hidden !important; text-overflow: ellipsis !important;
  background: transparent !important; color: inherit !important;
}
html#octop-simple-theme-root [class*="module__contextChipRemove__"] {
  display: inline-flex !important; align-items: center !important; justify-content: center !important;
  flex: 0 0 18px !important; width: 18px !important; height: 18px !important;
  min-height: 0 !important; min-width: 0 !important; padding: 0 !important; margin: 0 !important;
  border: 0 !important; border-radius: 6px !important; background: transparent !important;
  opacity: 0.6;
}
html#octop-simple-theme-root [class*="module__contextChip__"]:hover [class*="module__contextChipRemove__"] {
  opacity: 1;
}

/* 输入区下方小字：与输入框之间留 4px，别把输入区顶得离底边太远 */
html#octop-simple-theme-root [class*="module__runUsageBar"],
html#octop-simple-theme-root [class*="module__aiDisclaimer"] {
  max-width: var(--simple-column) !important;
  margin: 4px auto 0 !important;
  padding: 0 !important;
  font-size: 12px !important;
  line-height: 18px !important;
  color: var(--fn-text-quaternary) !important;
  text-align: center !important;
}
html#octop-simple-theme-root [class*="module__runUsageBar"] {
  text-align: left !important;
  opacity: 0.9;
}

/* =========================================================================
   5. 空态 / 欢迎页：并到同一条中轴
   ========================================================================= */
html#octop-simple-theme-root [class*="module__welcome__"] {
  padding-inline: 20px !important;
}
html#octop-simple-theme-root [class*="module__welcomeInner"] {
  width: 100% !important;
  max-width: var(--simple-column) !important;
  padding: 0 !important;
}
html#octop-simple-theme-root [class*="module__welcomeHeading"] {
  width: 100% !important;
  align-items: flex-start !important;
  text-align: left !important;
  gap: 8px !important;
  color: var(--fn-text-primary) !important;
}
html#octop-simple-theme-root [class*="module__welcomeTitle"] {
  font-size: 30px !important;
  font-weight: 500 !important;
  line-height: 1.28 !important;
  letter-spacing: -0.022em !important;
  color: var(--fn-text-primary) !important;
  text-align: left !important;
}
html#octop-simple-theme-root [class*="module__welcomeSubtitle"],
html#octop-simple-theme-root [class*="module__welcomeAgentLine"] {
  font-size: 15px !important;
  line-height: 1.6 !important;
  color: var(--fn-text-tertiary) !important;
  justify-content: flex-start !important;
  text-align: left !important;
}
html#octop-simple-theme-root [class*="module__welcomeMascot"] {
  display: block !important;
  width: 104px !important;
  height: auto !important;
  margin-bottom: -2px !important;
  align-self: flex-start !important;
  background: transparent !important;
}
/* 点一下换动作：保留原生 hover / active / focus 反馈，只补一点位移让它更像在探头 */
html#octop-simple-theme-root [class*="module__welcomeMascot"]:hover {
  transform: scale(1.04) translateY(-2px);
}
html#octop-simple-theme-root [class*="module__quickSection"] {
  width: 100% !important;
  max-width: var(--simple-column) !important;
}
html#octop-simple-theme-root [class*="module__quickCards"] {
  display: grid !important;
  grid-template-columns: repeat(auto-fit, minmax(210px, 1fr)) !important;
  gap: 8px !important;
  width: 100% !important;
  /* 3.9.9 — 最外两列原本正好压在中轴上，卡片描边与内容框边缘重合，
     看上去是「贴死在边上」。给网格自身让出 8px（与列间距一致），卡片离开边缘。 */
  box-sizing: border-box !important;
  padding-inline: 8px !important;
}
html#octop-simple-theme-root [class*="module__quickCard__"] {
  width: auto !important;
  min-width: 0 !important;
  padding: 12px 14px !important;
  border: 1px solid transparent !important;
  border-radius: 12px !important;
  background: transparent !important;
  box-shadow: none !important;
  font-size: 14px !important;
  line-height: 20px !important;
  color: var(--fn-text-primary) !important;
  text-align: left !important;
}
html#octop-simple-theme-root [class*="module__quickCard__"]:hover {
  background: var(--simple-hover) !important;
}
html#octop-simple-theme-root [class*="module__quickCardIcon"] {
  width: 28px !important;
  height: 28px !important;
  border-radius: 8px !important;
  background: var(--fn-bg-secondary) !important;
  color: var(--fn-text-secondary) !important;
  padding: 0 !important;
  display: grid !important;
  place-items: center !important;
}
html#octop-simple-theme-root [class*="module__quickCardIcon"] svg {
  width: 16px !important;
  height: 16px !important;
  min-width: 16px !important;
  max-width: 100% !important;
  flex: none !important;
  display: block !important;
}
html#octop-simple-theme-root [class*="module__quickCardTitleRow"],
html#octop-simple-theme-root [class*="module__quickCardTitle"],
html#octop-simple-theme-root [class*="module__quickCardBody"] {
  font-size: 14px !important;
  line-height: 20px !important;
  font-weight: 500 !important;
  color: var(--fn-text-primary) !important;
}
html#octop-simple-theme-root [class*="module__quickCardDesc"] {
  font-size: 13px !important;
  line-height: 19px !important;
  font-weight: 400 !important;
  color: var(--fn-text-tertiary) !important;
}

/* =========================================================================
   6. 设置 / 后台 / 列表页：扁平化，卡片只留发丝线与 14px 圆角
   ========================================================================= */
html#octop-simple-theme-root .page-container,
html#octop-simple-theme-root .page-content {
  background: var(--fn-bg-primary) !important;
}
html#octop-simple-theme-root [class*="PageShell-module__tabbedBody"] {
  padding-right: 0 !important;
  padding-top: 0 !important;
}
html#octop-simple-theme-root [class*="PageShell-module__agentBar"] {
  margin-bottom: 10px !important;
  padding: 8px 12px !important;
  border: 1px solid var(--simple-hairline) !important;
  border-radius: 10px !important;
  background: transparent !important;
  box-shadow: none !important;
}

/* 页面标题：18px/600 + 13px 说明，跟正文同一套灰阶 */
html#octop-simple-theme-root .octop-typography h4,
html#octop-simple-theme-root h4.octop-typography {
  font-size: 18px !important;
  font-weight: 600 !important;
  line-height: 26px !important;
  letter-spacing: -0.01em !important;
  color: var(--fn-text-primary) !important;
}
html#octop-simple-theme-root .octop-typography-secondary,
html#octop-simple-theme-root [class*="module__sectionDesc"],
html#octop-simple-theme-root [class*="tabContent-module__sectionDesc"] {
  font-size: 13px !important;
  line-height: 20px !important;
  color: var(--fn-text-tertiary) !important;
}
html#octop-simple-theme-root [class*="tabContent-module__sectionTitle"] {
  font-size: 14px !important;
  font-weight: 600 !important;
  color: var(--fn-text-primary) !important;
}
html#octop-simple-theme-root [class*="tabContent-module__panelHeader__"] {
  padding: 0 0 14px !important;
  border-bottom: 1px solid var(--simple-hairline) !important;
  margin-bottom: 16px !important;
}
/* 面板头图标：组件本身只有尺寸，图标按 flex-start 贴住 30px 方块的左边，
   22px 的图标因此比框心左偏 4–5px；每个管理页的每个面板都有这一个，看着
   就像"一堆图标不居中"。改成网格居中，图标永远落在方块正中。 */
html#octop-simple-theme-root [class*="tabContent-module__panelHeaderIcon"] {
  width: 30px !important;
  height: 30px !important;
  border-radius: 9px !important;
  background: var(--fn-bg-secondary) !important;
  color: var(--fn-text-secondary) !important;
  display: grid !important;
  place-items: center !important;
  padding: 0 !important;
  line-height: 0 !important;
}
html#octop-simple-theme-root [class*="tabContent-module__panelHeaderIcon"] > svg,
html#octop-simple-theme-root [class*="tabContent-module__panelHeaderIcon"] > img {
  display: block !important;
  margin: 0 !important;
  flex: none !important;
}

/* 页内标签页：下划线式，去底色 */
html#octop-simple-theme-root [class*="module__tabBar"] {
  gap: 18px !important;
  margin-bottom: 16px !important;
  padding-bottom: 0 !important;
  border-bottom: 1px solid var(--simple-hairline) !important;
}
html#octop-simple-theme-root [class*="module__tab__"][class] {
  padding: 0 0 9px !important;
  border: none !important;
  border-bottom: 1.5px solid transparent !important;
  border-radius: 0 !important;
  background: transparent !important;
  font-size: 14px !important;
  font-weight: 500 !important;
  color: var(--fn-text-tertiary) !important;
  margin-bottom: -1px !important;
  box-shadow: none !important;
}
html#octop-simple-theme-root [class*="module__tab__"][class]:hover {
  color: var(--fn-text-primary) !important;
}
html#octop-simple-theme-root [class*="module__tabIcon"] svg {
  width: 15px !important;
  height: 15px !important;
}
/* active 用双属性提权，压过后台默认的粉色下划线 */
html#octop-simple-theme-root [class*="module__tab__"][class*="active"][class] {
  color: var(--fn-text-primary) !important;
  border-bottom-color: var(--fn-text-primary) !important;
}

/* antd 风格标签页 */
html#octop-simple-theme-root .octop-tabs-nav {
  margin-bottom: 14px !important;
}
html#octop-simple-theme-root .octop-tabs-nav::before {
  border-bottom: 1px solid var(--simple-hairline) !important;
}
html#octop-simple-theme-root .octop-tabs-tab {
  padding: 0 0 9px !important;
  font-size: 14px !important;
  color: var(--fn-text-tertiary) !important;
}
html#octop-simple-theme-root .octop-tabs-tab:hover {
  color: var(--fn-text-primary) !important;
}
html#octop-simple-theme-root .octop-tabs-tab-active .octop-tabs-tab-btn {
  color: var(--fn-text-primary) !important;
  font-weight: 500 !important;
}
html#octop-simple-theme-root .octop-tabs-ink-bar {
  background: var(--fn-text-primary) !important;
  height: 1.5px !important;
}

/* 卡片：只有发丝线，没有阴影，hover 只加深描边 */
html#octop-simple-theme-root .octop-card,
html#octop-simple-theme-root [class*="module__card__"],
html#octop-simple-theme-root [class*="module__poolGroup__"] {
  border: 1px solid var(--simple-hairline) !important;
  border-radius: 14px !important;
  background: var(--fn-bg-primary) !important;
  box-shadow: none !important;
}
html#octop-simple-theme-root .octop-card-hoverable:hover,
html#octop-simple-theme-root [class*="module__card__"]:hover {
  border-color: var(--simple-hairline-strong) !important;
  box-shadow: none !important;
}
html#octop-simple-theme-root .octop-card-head {
  min-height: 0 !important;
  padding: 14px 16px 0 !important;
  border-bottom: none !important;
  font-size: 14px !important;
  font-weight: 600 !important;
}
html#octop-simple-theme-root .octop-card-body {
  padding: 14px 16px !important;
  font-size: 14px !important;
}
html#octop-simple-theme-root [class*="module__cardBody"] {
  padding: 0 !important;
}
html#octop-simple-theme-root [class*="module__card__"] {
  padding: 14px 16px !important;
}
html#octop-simple-theme-root [class*="module__cardName"] {
  font-size: 14px !important;
  font-weight: 600 !important;
  color: var(--fn-text-primary) !important;
}
html#octop-simple-theme-root [class*="module__cardDesc"] {
  font-size: 13px !important;
  line-height: 19px !important;
  color: var(--fn-text-tertiary) !important;
}
html#octop-simple-theme-root [class*="module__cardIcon"] {
  width: 32px !important;
  height: 32px !important;
  border-radius: 9px !important;
  background: var(--fn-bg-secondary) !important;
  border: none !important;
  color: var(--fn-text-secondary) !important;
}
html#octop-simple-theme-root [class*="module__cardGrid"] {
  gap: 10px !important;
  padding: 4px 0 20px !important;
}
html#octop-simple-theme-root [class*="module__cardDisabled"] {
  opacity: 0.6 !important;
}

/* 工具栏 / 搜索行 */
html#octop-simple-theme-root [class*="module__toolbar__"][class],
html#octop-simple-theme-root [class*="module__pageTop"],
html#octop-simple-theme-root [class*="module__gridToolbar"] {
  gap: 8px !important;
  margin-bottom: 12px !important;
}
html#octop-simple-theme-root [class*="module__toolbarCount"],
html#octop-simple-theme-root [class*="module__roleLegend"] {
  font-size: 13px !important;
  color: var(--fn-text-tertiary) !important;
}

/* 表格：无外框、表头 12px 灰字、行悬停浅底、发丝线分隔 */
html#octop-simple-theme-root .octop-table-wrapper,
html#octop-simple-theme-root [class*="module__userTable"] {
  border: 1px solid var(--simple-hairline) !important;
  border-radius: 12px !important;
  background: var(--fn-bg-primary) !important;
  overflow: hidden !important;
}
html#octop-simple-theme-root .octop-table,
html#octop-simple-theme-root .octop-table > .octop-table-container,
html#octop-simple-theme-root .octop-table-wrapper .octop-table {
  font-size: 14px !important;
  border-radius: 12px !important;
  /* antd 把表格底色写死成 #fff，深色下必须显式覆盖 */
  background: var(--fn-bg-primary) !important;
  color: var(--fn-text-primary) !important;
}
html#octop-simple-theme-root .octop-table-wrapper .octop-table-thead > tr > th,
html#octop-simple-theme-root .octop-table-wrapper .octop-table-tbody > tr > td {
  background: transparent !important;
}
html#octop-simple-theme-root .octop-table-wrapper .octop-table-tbody > tr:hover > td {
  background: var(--simple-hover) !important;
}
html#octop-simple-theme-root .octop-table-thead > tr > th {
  padding: 10px 14px !important;
  border-bottom: 1px solid var(--simple-hairline) !important;
  background: transparent !important;
  font-size: 12px !important;
  font-weight: 500 !important;
  letter-spacing: 0.01em !important;
  color: var(--fn-text-tertiary) !important;
}
html#octop-simple-theme-root .octop-table-thead > tr > th::before {
  display: none !important;
}
html#octop-simple-theme-root .octop-table-tbody > tr > td {
  padding: 10px 14px !important;
  border-bottom: 1px solid var(--fn-border-secondary) !important;
  font-size: 14px !important;
  color: var(--fn-text-primary) !important;
  background: transparent !important;
}
html#octop-simple-theme-root .octop-table-tbody > tr:last-child > td {
  border-bottom: none !important;
}
html#octop-simple-theme-root .octop-table-tbody > tr:hover > td,
html#octop-simple-theme-root .octop-table-tbody > tr.octop-table-row-hover > td {
  background: var(--simple-hover) !important;
}
html#octop-simple-theme-root .octop-table-cell-fix-left,
html#octop-simple-theme-root .octop-table-cell-fix-right {
  background: var(--fn-bg-primary) !important;
}
html#octop-simple-theme-root .octop-table-pagination {
  margin: 12px 0 0 !important;
}

/* =========================================================================
   7. 控件层：按钮、输入、选择、开关、分段、标签、弹层
   ========================================================================= */
html#octop-simple-theme-root .octop-btn {
  display: inline-flex !important;
  align-items: center !important;
  justify-content: center !important;
  gap: 8px !important;
  line-height: 20px !important;
  height: 34px !important;
  padding: 0 14px !important;
  border-radius: 980px !important;
  font-size: 14px !important;
  font-weight: 500 !important;
  box-shadow: none !important;
}
html#octop-simple-theme-root .octop-btn-sm {
  height: 28px !important;
  padding: 0 10px !important;
  font-size: 13px !important;
}
html#octop-simple-theme-root .octop-btn > .octop-btn-icon {
  display: inline-flex !important;
  align-items: center !important;
  justify-content: center !important;
  flex: 0 0 auto !important;
  width: auto !important; height: auto !important;
  padding: 0 !important; margin: 0 !important;
  line-height: 0 !important;
}
html#octop-simple-theme-root .octop-btn > .octop-btn-icon > svg {
  display: block !important; vertical-align: initial !important;
}
html#octop-simple-theme-root .octop-btn.octop-btn-icon-only {
  width: 32px !important;
  height: 32px !important;
  padding: 0 !important;
  border-radius: 980px !important;
}
html#octop-simple-theme-root .octop-btn-default,
html#octop-simple-theme-root .octop-btn-variant-outlined {
  border: 1px solid var(--simple-hairline-strong) !important;
  background: transparent !important;
  color: var(--fn-text-primary) !important;
}
html#octop-simple-theme-root .octop-btn-default:hover,
html#octop-simple-theme-root .octop-btn-variant-outlined:hover {
  border-color: var(--fn-text-quaternary) !important;
  background: var(--simple-hover) !important;
  color: var(--fn-text-primary) !important;
}
html#octop-simple-theme-root .octop-btn-primary,
html#octop-simple-theme-root .octop-btn-variant-solid.octop-btn-color-primary {
  border: 1px solid transparent !important;
  background: var(--fn-text-primary) !important;
  color: var(--fn-bg-primary) !important;
}
html#octop-simple-theme-root .octop-btn-primary:hover,
html#octop-simple-theme-root .octop-btn-variant-solid.octop-btn-color-primary:hover {
  background: var(--fn-text-secondary) !important;
  color: var(--fn-bg-primary) !important;
}
html#octop-simple-theme-root .octop-btn-link,
html#octop-simple-theme-root .octop-btn-variant-link {
  height: auto !important;
  padding: 0 !important;
  border: none !important;
  background: transparent !important;
  color: var(--fn-text-secondary) !important;
  font-size: 13px !important;
  box-shadow: none !important;
}
html#octop-simple-theme-root .octop-btn-link:hover,
html#octop-simple-theme-root .octop-btn-variant-link:hover {
  color: var(--fn-text-primary) !important;
  text-decoration: underline;
  text-underline-offset: 2px;
}
html#octop-simple-theme-root .octop-btn-dangerous {
  color: var(--fn-text-danger) !important;
}

/* 输入 / 选择 / 数字框：34px、10px 圆角、聚焦发丝描边 */
html#octop-simple-theme-root .octop-input,
html#octop-simple-theme-root .octop-input-affix-wrapper,
html#octop-simple-theme-root .octop-select .octop-select-selector,
html#octop-simple-theme-root .octop-ant-input,
html#octop-simple-theme-root .octop-ant-input-affix-wrapper,
html#octop-simple-theme-root .octop-ant-input-number,
html#octop-simple-theme-root .octop-ant-select-selector {
  min-height: 34px !important;
  border: 1px solid var(--simple-hairline-strong) !important;
  border-radius: 10px !important;
  background: var(--fn-bg-primary) !important;
  box-shadow: none !important;
  font-size: 14px !important;
  color: var(--fn-text-primary) !important;
}
html#octop-simple-theme-root .octop-input:hover,
html#octop-simple-theme-root .octop-input-affix-wrapper:hover,
html#octop-simple-theme-root .octop-select:hover .octop-select-selector,
html#octop-simple-theme-root .octop-ant-input:hover,
html#octop-simple-theme-root .octop-ant-input-affix-wrapper:hover,
html#octop-simple-theme-root .octop-ant-select-selector:hover {
  border-color: var(--fn-text-quaternary) !important;
}
html#octop-simple-theme-root .octop-input:focus,
html#octop-simple-theme-root .octop-input-focused,
html#octop-simple-theme-root .octop-input-affix-wrapper-focused,
html#octop-simple-theme-root .octop-select-focused .octop-select-selector,
html#octop-simple-theme-root .octop-ant-input:focus,
html#octop-simple-theme-root .octop-ant-input-affix-wrapper-focused,
html#octop-simple-theme-root .octop-ant-select-focused .octop-ant-select-selector {
  border-color: var(--fn-text-primary) !important;
  box-shadow: 0 0 0 3px var(--simple-hover) !important;
}
html#octop-simple-theme-root .octop-input::placeholder,
html#octop-simple-theme-root .octop-ant-input::placeholder {
  color: var(--fn-text-placeholder) !important;
}
html#octop-simple-theme-root .octop-select-selector {
  padding-inline: 12px !important;
}
html#octop-simple-theme-root textarea.octop-input,
html#octop-simple-theme-root textarea.octop-ant-input {
  padding: 8px 12px !important;
  border-radius: 10px !important;
  line-height: 1.6 !important;
}
html#octop-simple-theme-root .octop-form-item {
  margin-bottom: 18px !important;
}
html#octop-simple-theme-root .octop-form-item-label > label,
html#octop-simple-theme-root .octop-ant-form-item-label > label {
  font-size: 13px !important;
  font-weight: 500 !important;
  color: var(--fn-text-secondary) !important;
}
html#octop-simple-theme-root .octop-form-item-label {
  padding-bottom: 8px !important;
}
html#octop-simple-theme-root .octop-form-item-extra {
  margin-top: 10px !important;
  padding: 0 !important;
  font-size: 12px !important;
  line-height: 18px !important;
  color: var(--fn-text-tertiary) !important;
}
html#octop-simple-theme-root .octop-form-item-control-input + .octop-form-item-extra,
html#octop-simple-theme-root .octop-form-item-control > .octop-form-item-extra {
  margin-top: 10px !important;
}

/* 下拉菜单 / 气泡卡 / 提示：实心面 + 发丝线 + 一层薄影 */
html#octop-simple-theme-root .octop-dropdown-menu,
html#octop-simple-theme-root .octop-select-dropdown,
html#octop-simple-theme-root .octop-ant-select-dropdown,
html#octop-simple-theme-root .octop-popover-inner,
html#octop-simple-theme-root .octop-ant-popover-inner {
  padding: 5px !important;
  border: 1px solid var(--simple-hairline) !important;
  border-radius: 12px !important;
  background: var(--fn-bg-elevated) !important;
  box-shadow: var(--fn-shadow-md) !important;
}
html#octop-simple-theme-root .octop-dropdown-menu-item,
html#octop-simple-theme-root .octop-select-item,
html#octop-simple-theme-root .octop-ant-select-item {
  min-height: 30px !important;
  padding: 5px 10px !important;
  border-radius: 8px !important;
  font-size: 14px !important;
  color: var(--fn-text-primary) !important;
}
html#octop-simple-theme-root .octop-dropdown-menu-item:hover,
html#octop-simple-theme-root .octop-select-item-option-active,
html#octop-simple-theme-root .octop-ant-select-item-option-active {
  background: var(--simple-hover) !important;
}
html#octop-simple-theme-root .octop-select-item-option-selected,
html#octop-simple-theme-root .octop-ant-select-item-option-selected {
  font-weight: 500 !important;
  background: var(--fn-bg-secondary) !important;
  color: var(--fn-text-primary) !important;
}
html#octop-simple-theme-root .octop-tooltip-inner,
html#octop-simple-theme-root .octop-ant-tooltip-inner {
  padding: 5px 9px !important;
  border-radius: 8px !important;
  background: var(--fn-text-primary) !important;
  color: var(--fn-bg-primary) !important;
  font-size: 12px !important;
  box-shadow: var(--fn-shadow-sm) !important;
}

/* 弹窗 / 抽屉 */
html#octop-simple-theme-root .octop-modal-mask,
html#octop-simple-theme-root .octop-drawer-mask {
  background: rgba(13, 13, 13, 0.32) !important;
  backdrop-filter: blur(2px);
}
html#octop-simple-theme-root .octop-modal .octop-modal-content,
html#octop-simple-theme-root .octop-ant-modal-content {
  padding: 0 !important;
  border: 1px solid var(--simple-hairline) !important;
  border-radius: 18px !important;
  background: var(--fn-bg-elevated) !important;
  box-shadow: var(--fn-shadow-xl) !important;
  overflow: hidden !important;
}
html#octop-simple-theme-root .octop-modal-header,
html#octop-simple-theme-root .octop-ant-modal-header {
  margin: 0 !important;
  padding: 18px 20px 10px !important;
  border-bottom: none !important;
  font-size: 16px !important;
  font-weight: 600 !important;
}
html#octop-simple-theme-root .octop-modal-body,
html#octop-simple-theme-root .octop-ant-modal-body {
  padding: 0 20px 16px !important;
  font-size: 14px !important;
}
html#octop-simple-theme-root .octop-modal-footer {
  padding: 0 20px 18px !important;
  border-top: none !important;
}
html#octop-simple-theme-root .octop-drawer-content,
html#octop-simple-theme-root .octop-ant-drawer-content {
  background: var(--fn-bg-elevated) !important;
  border-left: 1px solid var(--simple-hairline) !important;
}
html#octop-simple-theme-root .octop-drawer-header {
  padding: 16px 20px !important;
  border-bottom: 1px solid var(--simple-hairline) !important;
  font-size: 15px !important;
  font-weight: 600 !important;
}
html#octop-simple-theme-root .octop-drawer-body {
  padding: 18px 20px !important;
  font-size: 14px !important;
}
html#octop-simple-theme-root .octop-drawer-footer {
  padding: 12px 20px 16px !important;
  border-top: 1px solid var(--simple-hairline) !important;
}
html#octop-simple-theme-root .octop-drawer-close {
  color: var(--fn-text-tertiary) !important;
}

/* 开关 / 复选 / 分段 / 标签 */
html#octop-simple-theme-root .octop-switch,
html#octop-simple-theme-root .octop-ant-switch {
  background: var(--fn-bg-tertiary) !important;
  box-shadow: none !important;
}
html#octop-simple-theme-root .octop-switch-checked,
html#octop-simple-theme-root .octop-ant-switch-checked {
  background: var(--fn-text-primary) !important;
}
html#octop-simple-theme-root .octop-checkbox-inner,
html#octop-simple-theme-root .octop-ant-checkbox-inner {
  border-color: var(--simple-hairline-strong) !important;
  border-radius: 5px !important;
}
html#octop-simple-theme-root .octop-checkbox-checked .octop-checkbox-inner,
html#octop-simple-theme-root .octop-ant-checkbox-checked .octop-ant-checkbox-inner {
  border-color: var(--fn-text-primary) !important;
  background: var(--fn-text-primary) !important;
}
html#octop-simple-theme-root .octop-segmented,
html#octop-simple-theme-root .octop-ant-segmented {
  padding: 2px !important;
  border-radius: 10px !important;
  background: var(--fn-bg-secondary) !important;
}
html#octop-simple-theme-root .octop-segmented-item-label,
html#octop-simple-theme-root .octop-ant-segmented-item-label {
  font-size: 13px !important;
  color: var(--fn-text-secondary) !important;
  /* 图标与文字成组居中，别让图标顶在控件左边缘 */
  padding-inline: 4px !important;
  gap: 5px !important;
}
html#octop-simple-theme-root .octop-segmented-item-selected,
html#octop-simple-theme-root .octop-ant-segmented-item-selected {
  border-radius: 8px !important;
  background: var(--fn-bg-primary) !important;
  color: var(--fn-text-primary) !important;
  box-shadow: var(--fn-shadow-sm) !important;
}
html#octop-simple-theme-root .octop-tag,
html#octop-simple-theme-root .octop-ant-tag {
  margin: 0 !important;
  padding: 1px 8px !important;
  border: 1px solid var(--simple-hairline) !important;
  border-radius: 980px !important;
  background: transparent !important;
  font-size: 11px !important;
  line-height: 17px !important;
  color: var(--fn-text-tertiary) !important;
}
html#octop-simple-theme-root .octop-divider {
  border-color: var(--simple-hairline) !important;
  margin: 16px 0 !important;
}

/* 空态 / 加载 / 通知 */
html#octop-simple-theme-root .octop-ant-empty-description {
  font-size: 13px !important;
  color: var(--fn-text-tertiary) !important;
}
html#octop-simple-theme-root .octop-spin-text,
html#octop-simple-theme-root .octop-ant-spin-text {
  font-size: 13px !important;
  color: var(--fn-text-tertiary) !important;
}
html#octop-simple-theme-root .octop-notification-notice,
html#octop-simple-theme-root .octop-ant-notification-notice {
  padding: 14px 16px !important;
  border: 1px solid var(--simple-hairline) !important;
  border-radius: 12px !important;
  background: var(--fn-bg-elevated) !important;
  box-shadow: var(--fn-shadow-lg) !important;
  font-size: 14px !important;
}
html#octop-simple-theme-root .octop-message-notice-content {
  padding: 8px 14px !important;
  border: 1px solid var(--simple-hairline) !important;
  border-radius: 980px !important;
  background: var(--fn-bg-elevated) !important;
  box-shadow: var(--fn-shadow-md) !important;
  font-size: 13px !important;
}

/* 头像底色：清掉写死的靛蓝 / 品红 */
html#octop-simple-theme-root [class*="userCellAvatar"],
html#octop-simple-theme-root [class*="toolMediaFallback"],
html#octop-simple-theme-root [class*="expertAgentAvatar"] {
  background: var(--fn-bg-tertiary) !important;
  background-image: none !important;
  color: var(--fn-text-secondary) !important;
  border: none !important;
  box-shadow: none !important;
}

/* 深色下主色是白色，一批按钮把文字写死成 #fff，会白底白字 */
html#octop-simple-theme-root[data-theme="dark"] [class*="editSaveBtn"],
html#octop-simple-theme-root[data-theme="dark"] [class*="drawerSaveBtn"],
html#octop-simple-theme-root[data-theme="dark"] [class*="toolbarBtnPrimary"],
html#octop-simple-theme-root[data-theme="dark"] [class*="catalogCardActionBtnPrimary"],
html#octop-simple-theme-root[data-theme="dark"] [class*="btnPrimary"],
html#octop-simple-theme-root[data-theme="dark"] .octop-btn-primary,
html#octop-simple-theme-root[data-theme="dark"] .octop-switch-checked .octop-switch-handle {
  color: var(--fn-color-on-brand) !important;
}
html#octop-simple-theme-root[data-theme="dark"] .octop-btn-primary svg {
  color: var(--fn-color-on-brand) !important;
}

/* 减少动效 */
@media (prefers-reduced-motion: reduce) {
  html#octop-simple-theme-root * {
    transition-duration: 0.01ms !important;
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
  }
}

/* 窄屏：单列宽度交回视口，左右内边距对齐 */
@media (max-width: 900px) {
  /* 双属性压过基础令牌里的 html#id[data-theme="light"]（特异性更高） */
  html#octop-simple-theme-root[data-theme],
  html#octop-simple-theme-root[data-theme="light"],
  html#octop-simple-theme-root[data-theme="dark"] {
    --simple-column: 100%;
  }
  html#octop-simple-theme-root [class*="module__messageListInner"] {
    max-width: 100% !important;
    padding: 0 16px !important;
  }
  html#octop-simple-theme-root [class*="module__chatInput"],
  html#octop-simple-theme-root [class*="module__chatTitleBar__"] {
    padding-inline: 16px !important;
  }
  html#octop-simple-theme-root [class*="module__welcome__"] {
    padding-inline: 16px !important;
  }
  html#octop-simple-theme-root [class*="module__inputWrapper"] {
    border-radius: 16px !important;
  }
  html#octop-simple-theme-root [class*="module__welcomeTitle"] {
    font-size: 26px !important;
  }
  html#octop-simple-theme-root [class*="module__welcomeMascot"] {
    width: 88px !important;
    margin-bottom: 0 !important;
  }
  /* 窄屏只收起用量详情，模型保留为紧凑只读状态，名称取末段短名 */
  html#octop-simple-theme-root #simple-chat-dock .simple-stats {
    display: none !important;
  }
  html#octop-simple-theme-root [class*="module__chatFloatActions"] {
    display: none !important;
  }
  /* 窄屏快捷卡两列，避免单卡被挤成一条 */
  html#octop-simple-theme-root [class*="module__quickCards"] {
    grid-template-columns: repeat(2, minmax(0, 1fr)) !important;
  }
}

/* =========================================================================
   3.1 — Hierarchy polish: canvas → section → control, never boxes within boxes.
   ========================================================================= */
html#octop-simple-theme-root :focus:not(:focus-visible) { outline: none !important; }
html#octop-simple-theme-root .page-content { --simple-section-gap: 32px; }
/* One page rail, including the expert selector and both navigation levels. */
html#octop-simple-theme-root .page-content [class*="PageShell-module__agentBar__"] {
  border: 0 !important; border-radius: 0 !important; box-shadow: none !important;
  background: transparent !important; padding: 0 !important; margin: 8px 0 24px !important;
}
html#octop-simple-theme-root [class*="AgentSelector-module__chip__"],
html#octop-simple-theme-root [class*="AgentSelector-module__moreBtn__"] {
  border: 0 !important; border-radius: 999px !important; box-shadow: none !important;
  background: transparent !important; color: var(--fn-text-secondary) !important;
  min-height: 36px !important; padding: 8px 12px !important; font-size: 14px !important;
}
html#octop-simple-theme-root [class*="AgentSelector-module__chipActive__"] {
  background: var(--fn-bg-secondary) !important; color: var(--fn-text-primary) !important;
}
html#octop-simple-theme-root [class*="AgentSelector-module__chip__"]:hover {
  background: var(--simple-hover) !important;
}
html#octop-simple-theme-root [class*="AgentSelector-module__group__"] {
  border: 0 !important; background: transparent !important; box-shadow: none !important;
  gap: 4px !important; align-items: center !important;
}
/* Sidebar scope tabs: wrapper and item are different elements. */
html#octop-simple-theme-root [class*="module__sessionScopeTabs__"] {
  display: flex !important; align-items: center !important; gap: 4px !important;
  height: auto !important; padding: 0 !important; margin: 12px 0 !important;
  background: transparent !important; border: 0 !important; box-shadow: none !important;
}
html#octop-simple-theme-root [class*="module__sessionScopeTab__"] {
  flex: 1 1 0 !important; height: 32px !important; margin: 0 !important;
  padding: 0 8px !important; border: 0 !important; border-radius: 999px !important;
  display: inline-flex !important; align-items: center !important; justify-content: center !important;
  background: transparent !important; box-shadow: none !important;
}
html#octop-simple-theme-root [class*="module__sessionScopeTabActive__"] {
  background: var(--fn-sidebar-item-active-bg) !important; color: var(--fn-text-primary) !important;
}
/* Navigation uses weight and a single soft capsule, not enclosing rules. */
html#octop-simple-theme-root .page-content [class*="module__tabBar__"],
html#octop-simple-theme-root .page-content .octop-tabs-nav,
html#octop-simple-theme-root .page-content .octop-tabs-nav::before {
  border: 0 !important; box-shadow: none !important;
}
html#octop-simple-theme-root .page-content [class*="module__tabBar__"] {
  gap: 8px !important; margin-bottom: 24px !important;
}
html#octop-simple-theme-root .page-content [class*="module__tab__"][class] {
  padding: 8px 12px !important; margin: 0 !important; border: 0 !important;
  border-radius: 999px !important; line-height: 20px !important;
}
html#octop-simple-theme-root .page-content [class*="module__tab__"][class*="active"][class] {
  background: var(--fn-bg-secondary) !important;
}
html#octop-simple-theme-root .page-content .octop-tabs-tab {
  padding: 8px 0 !important; margin-top: 0 !important;
}
html#octop-simple-theme-root .page-content .octop-tabs-ink-bar { display: none !important; }
html#octop-simple-theme-root .page-content .octop-tabs-tab-active .octop-tabs-tab-btn {
  font-weight: 600 !important; color: var(--fn-text-primary) !important;
}
/* Sections are typography and whitespace; only independent catalog tiles have surfaces. */
html#octop-simple-theme-root .page-content .octop-card,
html#octop-simple-theme-root .page-content [class*="module__poolGroup__"],
html#octop-simple-theme-root .page-content [class*="tabContent-module__panelHeader__"] {
  border: 0 !important; border-radius: 0 !important; background: transparent !important;
  box-shadow: none !important;
}
html#octop-simple-theme-root .page-content .octop-card-head,
html#octop-simple-theme-root .page-content .octop-card-body {
  padding-inline: 0 !important; border: 0 !important;
}
html#octop-simple-theme-root .page-content .octop-card-head { padding-top: 0 !important; }
html#octop-simple-theme-root .page-content .octop-card { margin-bottom: 24px !important; }
html#octop-simple-theme-root .page-content [class*="module__card__"] {
  border: 0 !important; background: var(--fn-bg-secondary) !important;
  border-radius: 20px !important; padding: 20px !important;
}
html#octop-simple-theme-root .page-content [class*="Overview-module__summaryCard__"] {
  border: 0 !important; border-radius: 0 !important; box-shadow: none !important;
  background: transparent !important; padding: 16px 0 !important;
}
html#octop-simple-theme-root .page-content .octop-table-wrapper,
html#octop-simple-theme-root .page-content [class*="module__userTable__"] {
  border: 0 !important; border-radius: 0 !important;
}
/* Informational notices are quiet text, not a second framed panel. */
html#octop-simple-theme-root .page-content .octop-alert-info {
  border: 0 !important; border-radius: 0 !important; background: transparent !important;
  box-shadow: none !important; padding: 12px 0 !important;
}
html#octop-simple-theme-root .page-content .octop-alert-info .octop-alert-message,
html#octop-simple-theme-root .page-content .octop-alert-info .octop-alert-description {
  color: var(--fn-text-secondary) !important; line-height: 1.6 !important;
}
/* Neutral secondary actions are ghost capsules. Destructive semantics are retained. */
html#octop-simple-theme-root .octop-btn-default:not(.octop-btn-dangerous),
html#octop-simple-theme-root .octop-btn-variant-outlined:not(.octop-btn-dangerous) {
  border-color: transparent !important; border-radius: 999px !important;
  background: transparent !important; box-shadow: none !important;
}
html#octop-simple-theme-root .octop-btn-default:not(:disabled):hover {
  border-color: transparent !important; background: var(--simple-hover) !important;
}
/* One selected surface; remove the competing animated segmented thumb. */
html#octop-simple-theme-root .octop-segmented { background: transparent !important; padding: 0 !important; }
html#octop-simple-theme-root .octop-segmented-item { border-radius: 999px !important; }
html#octop-simple-theme-root .octop-segmented-item-selected {
  background: var(--fn-bg-secondary) !important; box-shadow: none !important;
}
html#octop-simple-theme-root .octop-segmented-thumb {
  background: transparent !important; box-shadow: none !important;
}
/* Composer: a single continuous surface, no top rule or nested input frame. */
html#octop-simple-theme-root [class*="module__chatInput__"] {
  border: 0 !important; box-shadow: none !important; background: transparent !important;
}
html#octop-simple-theme-root [class*="module__inputWrapper__"] {
  border: 0 !important; background: var(--fn-bg-secondary) !important;
  box-shadow: none !important;
}
html#octop-simple-theme-root [class*="module__inputRow__"],
html#octop-simple-theme-root [class*="module__actionsRow__"] {
  border: 0 !important; background: transparent !important; box-shadow: none !important;
}
/* Editor surfaces remain recognisable, with no permanent outlined box. */
html#octop-simple-theme-root .page-content textarea.octop-input {
  border: 1px solid transparent !important; border-radius: 16px !important;
  background: var(--fn-bg-secondary) !important; padding: 16px !important; box-shadow: none !important;
}
html#octop-simple-theme-root .page-content textarea.octop-input:focus-visible {
  outline: 1px solid var(--fn-text-secondary) !important; outline-offset: 2px !important;
}

/* Remove the second 24px inset inside page shells: headings and content share a rail. */
html#octop-simple-theme-root .page-content > .octop-desktop-drag > .octop-desktop-no-drag {
  padding: 0 !important; background: transparent !important; border: 0 !important;
}

/* 3.2 — Apple Store card geometry. Only independent objects receive a surface. */
html#octop-simple-theme-root {
  --simple-store-card-radius: 18px;
  --simple-store-card-bg: #fff;
  /* 3.9.18 — 原来 2px/4px 的偏置投影像是把卡「贴」在页面上，和描边叠成两道线。
     改成一层贴地的接触阴影 + 一层大扩散的环境光，卡片自己浮起来，边界只有一道发丝环。 */
  --simple-store-card-shadow: 0 1px 2px rgba(13,13,13,.04), 0 10px 26px -18px rgba(13,13,13,.22);
  --simple-store-card-shadow-hover: 0 2px 6px rgba(13,13,13,.06), 0 18px 38px -20px rgba(13,13,13,.30);
}
html#octop-simple-theme-root[data-theme="dark"] {
  --simple-store-card-bg: #2a2a2a;
  --simple-store-card-shadow: 0 1px 2px rgba(0,0,0,.28), 0 10px 26px -18px rgba(0,0,0,.5);
  --simple-store-card-shadow-hover: 0 2px 6px rgba(0,0,0,.34), 0 18px 38px -20px rgba(0,0,0,.6);
}
html#octop-simple-theme-root .page-content :is([class*="module__card__"], [class*="module__skillCard__"], [class*="module__catalogCard__"], [class*="Overview-module__summaryCard__"]) {
  border: 0 !important;
  border-radius: var(--simple-store-card-radius) !important;
  background: var(--simple-store-card-bg) !important;
  box-shadow: var(--simple-store-card-shadow) !important;
  padding: 24px !important;
  min-width: 0 !important;
  transition: box-shadow 300ms cubic-bezier(0,0,.5,1), transform 300ms cubic-bezier(0,0,.5,1) !important;
}
/* Catalog cards previously had a second inset and a rule around their footer. */
html#octop-simple-theme-root .page-content :is([class*="module__card__"], [class*="module__skillCard__"], [class*="module__catalogCard__"]) [class*="module__cardFooter__"] {
  border: 0 !important; padding: 16px 0 0 !important; margin: 0 !important;
  background: transparent !important;
}
html#octop-simple-theme-root .page-content [class*="module__cardGrid__"],
html#octop-simple-theme-root .page-content [class*="module__skillGrid__"] {
  gap: 20px !important; padding-block: 8px 24px !important;
}
html#octop-simple-theme-root .page-content [class*="module__skillCard__"]:has(input:checked) {
  box-shadow: 0 0 0 2px #0071e3, var(--simple-store-card-shadow) !important;
}
/* Align icon and label as one unit; do not apply navigation padding to descendants. */
html#octop-simple-theme-root .page-content [class*="module__tabLabel__"] {
  display: inline-flex !important; align-items: center !important; gap: 8px !important;
  line-height: 20px !important;
}
html#octop-simple-theme-root .page-content [class*="module__tabIcon__"] {
  display: inline-flex !important; align-items: center !important; justify-content: center !important;
  width: 16px !important; height: 20px !important; flex: 0 0 16px !important;
  padding: 0 !important; margin: 0 !important; background: transparent !important;
}
@media (hover: hover) and (prefers-reduced-motion: no-preference) {
  html#octop-simple-theme-root .page-content :is([class*="module__card__"], [class*="module__skillCard__"], [class*="module__catalogCard__"]):hover {
    transform: translateY(-2px) !important;
    box-shadow: var(--simple-store-card-shadow-hover) !important;
  }
}
/* Text entry has one neutral focus surface, never a blue nested rectangle. */
html#octop-simple-theme-root [class*="module__textarea__"]:focus,
html#octop-simple-theme-root [class*="module__textarea__"]:focus-visible {
  outline: none !important; box-shadow: none !important;
}
html#octop-simple-theme-root [class*="module__inputWrapper__"]:has([class*="module__textarea__"]:focus-visible) {
  box-shadow: none !important;
}
html#octop-simple-theme-root [class*="module__inputWrapper__"]:has([class*="module__textarea__"]:focus-visible)::after {
  content: none !important;
}
/* Keyboard focus is indicated at the caret, without adding a rule to the composer. */
html#octop-simple-theme-root :is(input.octop-input,textarea.octop-input,.octop-input-affix-wrapper,.octop-input-number):is(:focus,:focus-within) {
  outline: none !important; border-color: var(--fn-text-tertiary) !important;
  box-shadow: none !important;
}
html#octop-simple-theme-root .octop-select-focused .octop-select-selector {
  outline: none !important; border-color: var(--fn-text-tertiary) !important; box-shadow: none !important;
}
/* 3.3 — Verified omissions: settings sections are not catalog objects. */
html#octop-simple-theme-root [class*="Overview-module__overviewHero__"],
html#octop-simple-theme-root [class*="MemorySettings-module__advancedSettings__"],
html#octop-simple-theme-root [class*="MemorySettings-module__saveBar__"],
html#octop-simple-theme-root .page-content [class*="module__tableCard__"] {
  border: 0 !important; box-shadow: none !important; background: transparent !important; border-radius: 0 !important;
}
html#octop-simple-theme-root [class*="Overview-module__overviewHero__"] { padding: 0 0 24px !important; }
html#octop-simple-theme-root [class*="Overview-module__pipelineStage__"] {
  border: 0 !important; box-shadow: none !important; border-radius: 12px !important; background: var(--fn-bg-secondary) !important;
}
html#octop-simple-theme-root [class*="MemorySettings-module__saveBar__"] { padding: 24px 0 0 !important; }
html#octop-simple-theme-root [class*="MemorySettings-module__advancedSettings__"] > .octop-collapse-item,
html#octop-simple-theme-root [class*="MemorySettings-module__advancedSettings__"] .octop-collapse-content {
  border: 0 !important; background: transparent !important;
}
html#octop-simple-theme-root [class*="MemorySettings-module__advancedSettings__"] .octop-collapse-header,
html#octop-simple-theme-root [class*="MemorySettings-module__advancedSettings__"] .octop-collapse-content-box { padding-inline: 0 !important; }
/* 3.9.12 — 3.3 把这张卡的内边距拉平为 0 的时候，卡片本身是没有轮廓的；
   3.9.6 给它补上 1px 内环之后，toolbar 和 addBar 里的文字、按钮就正好压在环上
   （变量区「0 变量」与「添加变量」的左缘和卡框重合，右侧同理）。环在，内边距必须回来，
   数值对齐 emptyState 原生的 24px，窄屏回收成 16px。 */
html#octop-simple-theme-root .page-content [class*="module__tableCard__"] > [class*="module__toolbar__"],
html#octop-simple-theme-root .page-content [class*="module__tableCard__"] > [class*="module__addBar__"] {
  border: 0 !important; padding-inline: 24px !important; background: transparent !important;
}
@media (max-width: 640px) {
  html#octop-simple-theme-root .page-content [class*="module__tableCard__"] > [class*="module__toolbar__"],
  html#octop-simple-theme-root .page-content [class*="module__tableCard__"] > [class*="module__addBar__"] {
    padding-inline: 16px !important;
  }
}
html#octop-simple-theme-root .page-content [class*="module__tableCard__"] [class*="module__addBtn__"] {
  border: 0 !important; border-radius: 999px !important; background: var(--fn-bg-secondary) !important;
}
html#octop-simple-theme-root :is(.octop-input-affix-wrapper,.octop-ant-input-affix-wrapper) > :is(.octop-input,.octop-ant-input) {
  border: 0 !important; background: transparent !important; box-shadow: none !important; border-radius: 0 !important;
}
html#octop-simple-theme-root .octop-ant-segmented { background: transparent !important; padding: 0 !important; }
html#octop-simple-theme-root .octop-ant-segmented-item { border-radius: 999px !important; }
html#octop-simple-theme-root .octop-ant-segmented-item-selected { background: var(--fn-bg-secondary) !important; box-shadow: none !important; }
html#octop-simple-theme-root .octop-ant-segmented-thumb { background: transparent !important; box-shadow: none !important; }

/* 3.4 — Exact component boundaries; icons never inherit button geometry. */
html#octop-simple-theme-root [class*="AvatarDropdown-module__triggerName__"] {
  display: flex !important; align-items: center !important;
  height: auto !important; min-height: 0 !important; padding: 0 !important;
  line-height: 20px !important; border: 0 !important; background: transparent !important;
}
html#octop-simple-theme-root [class*="AvatarDropdown-module__triggerChevron__"] {
  width: 14px !important; height: 14px !important; padding: 0 !important;
  flex: 0 0 14px !important; border: 0 !important; background: transparent !important;
}
html#octop-simple-theme-root [class*="module__openBrowserPrompt__"] > svg {
  display: block !important; width: 16px !important; height: 16px !important;
  flex: 0 0 16px !important; padding: 0 !important; margin: 0 !important;
  border: 0 !important; border-radius: 0 !important; background: transparent !important;
}
html#octop-simple-theme-root [class*="module__scrollToBottomBtn__"] > svg { flex-shrink: 0 !important; }
html#octop-simple-theme-root .page-content :is([class*="module__providerCard__"],[class*="module__poolGroup__"],[class*="Overview-module__overviewChartCard__"],[class*="Overview-module__pipelineCard__"]) {
  border: 0 !important; border-radius: var(--simple-store-card-radius) !important;
  background: var(--simple-store-card-bg) !important;
  box-shadow: var(--simple-store-card-shadow) !important;
  padding: 24px !important; min-width: 0 !important;
}
html#octop-simple-theme-root .page-content :is([class*="module__providerCard__"],[class*="Overview-module__overviewChartCard__"],[class*="Overview-module__pipelineCard__"]) > .octop-card-body {
  padding: 0 !important; background: transparent !important;
}
/* 3.2.1 — Stable card rhythm and compound interaction states. */
html#octop-simple-theme-root .page-content :is([class*="module__card__"], [class*="module__skillCard__"], [class*="module__catalogCard__"]) [class*="module__cardDesc__"] {
  font-size: 14px !important; line-height: 22px !important;
  min-height: 44px !important; max-height: 44px !important;
  display: -webkit-box !important; -webkit-box-orient: vertical !important;
  -webkit-line-clamp: 2 !important; overflow: hidden !important;
  overflow-wrap: anywhere !important;
}
html#octop-simple-theme-root .page-content :is([class*="module__card__"], [class*="module__skillCard__"], [class*="module__catalogCard__"]) :is([class*="module__cardName__"], [class*="module__cardTitle__"]) {
  min-width: 0 !important; overflow-wrap: anywhere !important;
}
@media (hover: hover) {
  html#octop-simple-theme-root .page-content [class*="module__skillCard__"]:has(input:checked):hover {
    box-shadow: 0 0 0 2px #0071e3, var(--simple-store-card-shadow-hover) !important;
  }
}
/* Attached sheets are not floating cards: round only the exposed edge. */
html#octop-simple-theme-root .octop-drawer-right .octop-drawer-content {
  border-radius: 18px 0 0 18px !important;
}
html#octop-simple-theme-root .octop-drawer-left .octop-drawer-content {
  border-radius: 0 18px 18px 0 !important;
}
html#octop-simple-theme-root .octop-drawer-bottom .octop-drawer-content {
  border-radius: 18px 18px 0 0 !important;
}
html#octop-simple-theme-root .octop-drawer-header,
html#octop-simple-theme-root .octop-drawer-footer {
  border: 0 !important; padding: 24px !important;
}
html#octop-simple-theme-root .octop-drawer-body { padding: 0 24px 24px !important; }
@media (max-width: 600px) {
  html#octop-simple-theme-root .octop-drawer-right .octop-drawer-content,
  html#octop-simple-theme-root .octop-drawer-left .octop-drawer-content { border-radius: 0 !important; }
  html#octop-simple-theme-root .octop-drawer-header,
  html#octop-simple-theme-root .octop-drawer-footer { padding: 20px !important; }
  html#octop-simple-theme-root .octop-drawer-body { padding: 0 20px 20px !important; }
}

@media (max-width: 600px) {
  html#octop-simple-theme-root .page-content :is([class*="module__card__"], [class*="module__skillCard__"], [class*="module__catalogCard__"], [class*="Overview-module__summaryCard__"]) { padding: 20px !important; }
}


/* 3.5 — Five confirmed standalone surfaces, not substring-matched internals. */
html#octop-simple-theme-root [class*="module__chatTitleBar__"] {
 display: none !important; height: 0 !important; min-height: 0 !important;
 margin: 0 !important; padding: 0 !important; border: 0 !important;
}
html#octop-simple-theme-root :is([class*="module__backendCard__"],[class*="module__channelCard__"],[class*="module__hubCard__"],[class*="module__agentCard2__"],[class*="module__emptyStateSuggestionItem__"]) {
 border: 0 !important; border-radius: var(--simple-store-card-radius) !important;
 background: var(--simple-store-card-bg) !important; box-shadow: var(--simple-store-card-shadow) !important;
 padding: 24px !important; min-width: 0 !important; box-sizing: border-box !important;
 transition: box-shadow .3s cubic-bezier(0,0,.5,1), transform .3s cubic-bezier(0,0,.5,1) !important;
}
html#octop-simple-theme-root [class*="module__agentCard2Accent__"] { display: none !important; }
html#octop-simple-theme-root [class*="module__agentCard2Header__"] { padding: 0 !important; margin-bottom: 16px !important; }
html#octop-simple-theme-root [class*="module__agentCard2Desc__"] { margin: 0 !important; min-height: 44px !important; font-size: 14px !important; line-height: 22px !important; }
html#octop-simple-theme-root [class*="module__agentCard2Footer__"] { padding: 20px 0 0 !important; margin-top: auto !important; border: 0 !important; }
html#octop-simple-theme-root [class*="module__backendCardActions__"] { border: 0 !important; padding: 16px 0 0 !important; }
html#octop-simple-theme-root [class*="module__channelCard__"] [class*="module__cardDescription__"],
html#octop-simple-theme-root [class*="module__hubCardDesc__"] {
 font-size: 14px !important; line-height: 22px !important; min-height: 44px !important; max-height: 44px !important;
 color: var(--fn-text-secondary) !important; overflow: hidden !important; overflow-wrap: anywhere !important;
 display: -webkit-box !important; -webkit-line-clamp: 2 !important; -webkit-box-orient: vertical !important;
}
html#octop-simple-theme-root [class*="module__hubCardName__"] { min-width: 0 !important; overflow-wrap: anywhere !important; }
html#octop-simple-theme-root [class*="module__hubCardFooter__"] { padding-top: 12px !important; border: 0 !important; margin-top: auto !important; }
html#octop-simple-theme-root [class*="module__emptyStateSuggestionItem__"] { height: auto !important; min-height: 96px !important; text-align: left !important; }
html#octop-simple-theme-root [class*="module__emptyStateSuggestionText__"] { line-height: 22px !important; min-width: 0 !important; }
@media (hover:hover) and (prefers-reduced-motion:no-preference) {
 html#octop-simple-theme-root :is([class*="module__backendCard__"],[class*="module__channelCard__"],[class*="module__hubCard__"],[class*="module__agentCard2__"],[class*="module__emptyStateSuggestionItem__"]):hover {
  box-shadow: var(--simple-store-card-shadow-hover) !important; transform: translateY(-2px) !important;
 }
}
@media (max-width:600px) {
 html#octop-simple-theme-root :is([class*="module__backendCard__"],[class*="module__channelCard__"],[class*="module__hubCard__"],[class*="module__agentCard2__"],[class*="module__emptyStateSuggestionItem__"]) { padding: 20px !important; }
}


/* ============================================================
   3.6 — Card coverage completion + control rhythm.

   Why this layer exists: 3.2/3.5 matched a hand-written allowlist of
   module names. Every surface shipped after that list was written
   (connector catalog, cron, teams, MCP, presets, memory, desktop ...)
   kept the factory surface: a 2px hairline box, a 12px corner and no
   elevation, which reads as a different product on the same page.

   Rule: a card root owns a surface; anything inside it does not. Card
   roots are the only module classes whose name ends in Card before the
   hash suffix, so a single guarded attribute match covers unknown
   future cards without touching their headers, chips or footers.
   ============================================================ */

html#octop-simple-theme-root :is(
  [class*="module__typeCard__"],
  [class*="module__customMcpServerCard__"],
  [class*="module__cronCard__"],
  [class*="module__agentCard__"],
  [class*="module__expertTemplateCard__"],
  [class*="module__teamCard__"],
  [class*="module__roleCard__"],
  [class*="module__userCard__"],
  [class*="module__inviteCard__"],
  [class*="module__presetCard__"],
  [class*="module__wizardPresetCard__"],
  [class*="module__wizardCard__"],
  [class*="module__docCard__"],
  [class*="module__backupCard__"],
  [class*="module__configuredCard__"],
  [class*="module__disabledCard__"],
  [class*="module__reconnectCard__"],
  [class*="module__conversationCard__"],
  [class*="module__conversationTableCard__"],
  [class*="module__attachmentPreviewCard__"],
  [class*="module__messageFileCard__"],
  [class*="module__marketQuickPromptCard__"],
  [class*="module__memberPickCard__"],
  [class*="module__settingCard__"],
  [class*="module__settingsCard__"],
  [class*="module__shortcutsCard__"],
  [class*="module__versionCard__"],
  [class*="module__configCard__"],
  [class*="module__installCard__"],
  [class*="module__entityCard__"],
  [class*="module__candidatesCard__"],
  [class*="module__resultCard__"],
  [class*="module__chartCard__"],
  [class*="module__compCard__"],
  [class*="module__overviewTurnsCard__"]
) {
  border: 0 !important;
  border-radius: var(--simple-store-card-radius) !important;
  background: var(--simple-store-card-bg) !important;
  box-shadow: var(--simple-store-card-shadow) !important;
  padding: 24px !important;
  min-width: 0 !important;
  box-sizing: border-box !important;
  transition: box-shadow .3s cubic-bezier(0,0,.5,1), transform .3s cubic-bezier(0,0,.5,1) !important;
}

/* Catch-all for card roots introduced by later builds. Card internals never
   contain the Card__ suffix, so headers, chips and footers stay flat. The
   chart widgets below are inner panels of an analytics card, not cards. */
html#octop-simple-theme-root :is([class*="module__"][class*="Card__"]):not(
  :is(
    [class*="module__dimBarCard__"],
    [class*="module__donutCard__"],
    [class*="module__dimTableCard__"],
    [class*="module__trendCard__"],
    [class*="module__summaryTrendCard__"],
    /* 3.9.9 — quickCard 也满足 module__ + Card__，被这条盖成 18px 圆角 + 纯白底，
       自己的 12px 圆角和 --fn-bg-secondary 底色全被吃掉，只剩一道硬描边。
       这里把它排除，让 12px 圆角与浅灰面生效。 */
    [class*="module__quickCard__"]
  )
) {
  border: 0 !important;
  border-radius: var(--simple-store-card-radius) !important;
  background: var(--simple-store-card-bg) !important;
  box-shadow: var(--simple-store-card-shadow) !important;
  min-width: 0 !important;
  box-sizing: border-box !important;
  transition: box-shadow .3s cubic-bezier(0,0,.5,1), transform .3s cubic-bezier(0,0,.5,1) !important;
}

@media (hover: hover) and (prefers-reduced-motion: no-preference) {
  html#octop-simple-theme-root :is([class*="module__"][class*="Card__"]):not(
    :is(
      [class*="module__dimBarCard__"],
      [class*="module__donutCard__"],
      [class*="module__dimTableCard__"],
      [class*="module__trendCard__"],
      [class*="module__summaryTrendCard__"],
      [class*="module__quickCard__"]
    )
  ):hover {
    box-shadow: var(--simple-store-card-shadow-hover) !important;
    transform: translateY(-2px) !important;
  }
}

/* 3.6.1 — Connector catalog: one neutral grid, one card rhythm.
   Factory values: 240px tracks, 12px column gap, 20px inset, 2px border,
   0 gap between the icon/title row and the description, and a footer that
   floats wherever the copy happens to end. */
html#octop-simple-theme-root [class*="module__typeGrid__"] {
  grid-template-columns: repeat(auto-fill, minmax(248px, 1fr)) !important;
  column-gap: 20px !important;
  row-gap: 20px !important;
  padding-block: 8px 24px !important;
}
html#octop-simple-theme-root [class*="module__typeCard__"] {
  padding: 24px !important;
  gap: 0 !important;
  min-height: 176px !important;
}
html#octop-simple-theme-root [class*="module__typeCardBody__"] {
  flex: 1 1 auto !important;
  display: flex !important;
  flex-direction: column !important;
  gap: 12px !important;
  padding: 0 !important;
}
html#octop-simple-theme-root [class*="module__typeCardHeader__"] {
  display: flex !important;
  align-items: flex-start !important;
  gap: 12px !important;
  min-height: 0 !important;
}
html#octop-simple-theme-root [class*="module__typeCardIconLarge__"] {
  flex: 0 0 44px !important;
  width: 44px !important;
  height: 44px !important;
  border-radius: 10px !important;
}
html#octop-simple-theme-root [class*="module__typeCardTitleCol__"] {
  display: flex !important;
  flex-direction: column !important;
  gap: 6px !important;
  min-width: 0 !important;
}
html#octop-simple-theme-root [class*="module__typeCardTitle__"] {
  display: block !important;
  min-width: 0 !important;
  font-size: 15px !important;
  line-height: 20px !important;
  font-weight: 600 !important;
  overflow: hidden !important;
  text-overflow: ellipsis !important;
  white-space: nowrap !important;
}
html#octop-simple-theme-root [class*="module__categoryChip__"] {
  align-self: flex-start !important;
  margin: 0 !important;
  padding: 0 8px !important;
  border: 0 !important;
  border-radius: 999px !important;
  font-size: 11px !important;
  line-height: 18px !important;
}
html#octop-simple-theme-root [class*="module__typeCardDesc__"] {
  margin: 0 !important;
  min-height: 38px !important;
  max-height: 38px !important;
  font-size: 13px !important;
  line-height: 19px !important;
  color: var(--fn-text-secondary) !important;
  display: -webkit-box !important;
  -webkit-box-orient: vertical !important;
  -webkit-line-clamp: 2 !important;
  overflow: hidden !important;
  overflow-wrap: anywhere !important;
}
html#octop-simple-theme-root [class*="module__typeCardFooter__"] {
  margin-top: auto !important;
  padding: 16px 0 0 !important;
  border: 0 !important;
  min-height: 0 !important;
}
html#octop-simple-theme-root [class*="module__typeCardHint__"] {
  display: inline-flex !important;
  align-items: center !important;
  min-height: 20px !important;
  font-size: 13px !important;
  font-weight: 500 !important;
  line-height: 20px !important;
}

@media (max-width: 600px) {
  html#octop-simple-theme-root :is(
    [class*="module__typeCard__"],
    [class*="module__customMcpServerCard__"],
    [class*="module__cronCard__"],
    [class*="module__agentCard__"],
    [class*="module__expertTemplateCard__"],
    [class*="module__teamCard__"],
    [class*="module__roleCard__"],
    [class*="module__userCard__"],
    [class*="module__inviteCard__"],
    [class*="module__presetCard__"],
    [class*="module__wizardPresetCard__"],
    [class*="module__wizardCard__"],
    [class*="module__docCard__"],
    [class*="module__backupCard__"],
    [class*="module__configuredCard__"],
    [class*="module__disabledCard__"],
    [class*="module__reconnectCard__"],
    [class*="module__conversationCard__"],
    [class*="module__conversationTableCard__"],
    [class*="module__settingCard__"],
    [class*="module__settingsCard__"],
    [class*="module__shortcutsCard__"],
    [class*="module__versionCard__"],
    [class*="module__configCard__"],
    [class*="module__installCard__"],
    [class*="module__entityCard__"],
    [class*="module__candidatesCard__"],
    [class*="module__resultCard__"]
  ) {
    padding: 20px !important;
  }
}


/* ============================================================
   3.7 — Sidebar: retire the tinted frame around the current agent.

   The active agent card is the container that holds this agent session
   list, so whatever it paints becomes a frame around the whole list.
   The app writes that frame as an inline style with the agent accent:

     background: rgba(accent, .03); border-color: rgba(accent, .094)

   A token reset cannot reach an inline colour, so the fill went away but
   the 1px accent border stayed behind: a pale violet line floating around
   the session list, with nothing inside it. Same story for the 24px avatar,
   which keeps an inline accent ring on top of its neutral chip.

   Rule: the current agent is identified by position and type weight, not by
   a drawn box. No accent tint, no frame, no ring.
   ============================================================ */
html#octop-simple-theme-root [class*="module__agentCardActive"] {
  border-color: transparent !important;
  background: transparent !important;
  box-shadow: none !important;
}
html#octop-simple-theme-root [class*="module__agentCardActive"] [class*="module__agentCardAvatar"],
html#octop-simple-theme-root [class*="module__agentCardActive"] :is([class*="Avatar"], [class*="avatar"]) {
  box-shadow: none !important;
  border-color: transparent !important;
  background: var(--fn-bg-tertiary) !important;
}
/* The profile block keeps the same 8px rail as the expert rows above it. */
html#octop-simple-theme-root [class*="module__agentCardActive"] [class*="module__agentCardProfile"] {
  padding: 2px 2px 0 !important;
  margin: 0 0 2px !important;
}
html#octop-simple-theme-root [class*="module__agentCardActive"] [class*="module__agentCardSessions"] {
  padding: 2px 0 0 !important;
  gap: 2px !important;
}

/* v3.7 Model family icons and trailing, non-overlapping remove action. */
html#octop-simple-theme-root [class*="module__contextChipModel__"] {
  flex-direction: row !important; flex-wrap: nowrap !important;
}
html#octop-simple-theme-root [class*="module__contextChipIcon__"][data-simple-model-brand] {
  background-size: contain !important; background-repeat: no-repeat !important;
  background-position: center !important;
}
html#octop-simple-theme-root [class*="module__contextChipIcon__"][data-simple-model-brand] > * { visibility: hidden !important; }
/* 模型下拉里的同一套图标：IMG 走 object-fit，其余元素走背景图 */
html#octop-simple-theme-root [class*="module__modelMenuIcon__"][data-simple-model-brand] {
  background-size: contain !important; background-repeat: no-repeat !important;
  background-position: center !important;
}
html#octop-simple-theme-root [class*="module__modelMenuIcon__"][data-simple-model-brand] > * { visibility: hidden !important; }
html#octop-simple-theme-root [class*="module__contextChipModel__"] > [class*="module__contextChipRemove__"] {
  position: static !important; inset: auto !important; transform: none !important;
  order: 3 !important; flex: 0 0 20px !important; width: 20px !important; height: 20px !important;
  opacity: 0 !important; pointer-events: none; transition: opacity 140ms ease;
}
html#octop-simple-theme-root [class*="module__contextChipModel__"]:hover > [class*="module__contextChipRemove__"],
html#octop-simple-theme-root [class*="module__contextChipModel__"]:focus-within > [class*="module__contextChipRemove__"] {
  opacity: 1 !important; pointer-events: auto;
}
html#octop-simple-theme-root [class*="module__contextChipRemove__"]:focus-visible { outline: 2px solid var(--fn-text-secondary) !important; outline-offset: 1px; }
@media (hover: none), (pointer: coarse) {
  html#octop-simple-theme-root [class*="module__contextChipModel__"] > [class*="module__contextChipRemove__"] { opacity: .65 !important; pointer-events: auto; }
}
@media (prefers-reduced-motion: reduce) {
  html#octop-simple-theme-root [class*="module__contextChipModel__"] > [class*="module__contextChipRemove__"] { transition: none; }
}

/* v3.8: one hover surface and shared vertical centre for the chat nav row. */
html#octop-simple-theme-root [class*="Sidebar-module__navItemRow__"] { display:flex !important; align-items:center !important; padding:0 !important; gap:0 !important; }
html#octop-simple-theme-root [class*="Sidebar-module__navItemRow__"] > button { display:flex !important;align-items:center !important;justify-content:center; height:32px !important;min-height:32px !important;margin:0 !important;align-self:center !important;position:static !important;transform:none !important; }
html#octop-simple-theme-root [class*="Sidebar-module__navItemRow__"] > [class*="navItemMain__"] {justify-content:flex-start !important;flex:1 !important;}
html#octop-simple-theme-root [class*="Sidebar-module__navItemRow__"] > button,
html#octop-simple-theme-root [class*="Sidebar-module__navItemRow__"] > button:hover { background:transparent !important;box-shadow:none !important; }
html#octop-simple-theme-root [class*="Sidebar-module__navItemRow__"] svg {display:block !important;flex-shrink:0 !important;}
/* Avatars and model logos have no container fill or ring. */
html#octop-simple-theme-root :is([class*="agentCardAvatar__"],[class*="agentRowAvatar__"],[class*="modelMenuIcon__"],[class*="AvatarDropdown-module__avatar"]) {background:transparent !important;box-shadow:none !important;border:0 !important;}
html#octop-simple-theme-root [class*="modelMenuIcon__"] {object-fit:contain !important;border-radius:0 !important;padding:0 !important;}
/* Native data/actions remain mounted; floating proxy avoids React reconciliation bugs. */
html#octop-simple-theme-root [class*="module__contextChipModel__"],
html#octop-simple-theme-root [class*="module__runUsageBar__"] {display:none !important;}
html#octop-simple-theme-root [class*="module__imagePreviewBar__"]:not(:has(> :not([class*="module__contextChipModel__"]))) {display:none !important;}
html#octop-simple-theme-root #simple-chat-dock {position:fixed;z-index:90;display:flex;align-items:center;gap:8px;width:max-content;max-width:calc(100vw - 24px);background:transparent !important;box-shadow:none;border:0;padding:0;pointer-events:none;color:var(--fn-text-secondary);font-size:12px;}
html#octop-simple-theme-root #simple-chat-dock :is(button,.simple-stats) {pointer-events:auto;}
html#octop-simple-theme-root #simple-chat-dock button {display:inline-flex;align-items:center;justify-content:center;gap:6px;height:28px;min-height:28px;padding:0 4px;border:0;box-shadow:none;background:transparent;color:inherit;border-radius:6px;cursor:pointer;font:inherit;}
html#octop-simple-theme-root #simple-chat-dock button:focus-visible {outline:2px solid var(--fn-text-secondary);outline-offset:2px;}
html#octop-simple-theme-root #simple-chat-dock button:hover {color:var(--fn-text-primary);}
/* 当前模型是只读状态；切换仍走原生 + 菜单，避免两套交互抢焦点。 */
html#octop-simple-theme-root #simple-chat-dock .simple-current-model {display:flex;align-items:center;min-width:0;max-width:100%;gap:6px;background:transparent;color:var(--fn-text-secondary);}
html#octop-simple-theme-root #simple-chat-dock .simple-model-name {min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}
html#octop-simple-theme-root #simple-chat-dock img {width:16px;height:16px;object-fit:contain;background:transparent;border:0;flex:none;}
html#octop-simple-theme-root #simple-chat-dock [hidden] {display:none !important;}
html#octop-simple-theme-root #simple-chat-dock .simple-stats {position:relative;flex:none;}
html#octop-simple-theme-root #simple-chat-dock .simple-stats-detail {position:absolute;bottom:100%;left:0;width:320px;max-width:calc(100vw - 40px);padding:12px 16px;border-radius:12px;background:var(--fn-bg-primary);box-shadow:0 4px 24px #0002;color:var(--fn-text-secondary);line-height:1.7;opacity:0;visibility:hidden;pointer-events:none;transform:translateY(4px);transition:opacity 140ms,transform 140ms;}
/* 用量浮层只认"点开"这一种状态：hover / 焦点不再自己把面板翻出来，
   否则鼠标一离开或一失焦面板就消失，点了也关不干净。 */
html#octop-simple-theme-root #simple-chat-dock.simple-stats-open .simple-stats-detail {opacity:1;visibility:visible;transform:none;pointer-events:auto;}
html#octop-simple-theme-root #simple-chat-dock .simple-stats-trigger[aria-expanded="true"] {color:var(--fn-text-primary);}
@media(prefers-reduced-motion:reduce) {html#octop-simple-theme-root #simple-chat-dock * {transition:none !important;}}

html#octop-simple-theme-root [class*="module__agentCardActive"] :is([class*="Avatar"], [class*="avatar"]) {background:transparent !important;box-shadow:none !important;border:0 !important;}

/* Conversation resize rails: visible only on hover/focus, outside content. */
html#octop-simple-theme-root .simple-column-handle { position:fixed; width:6px; z-index:40; cursor:ew-resize; touch-action:none; border-radius:3px; background:transparent; transition:background 140ms; }
html#octop-simple-theme-root .simple-column-handle:hover, html#octop-simple-theme-root .simple-column-handle:focus-visible, html#octop-simple-theme-root.simple-column-dragging .simple-column-handle { background:var(--simple-hairline-strong); }
html#octop-simple-theme-root.simple-column-dragging, html#octop-simple-theme-root.simple-column-dragging * { cursor:ew-resize !important; user-select:none !important; }
@media(max-width:767px) { html#octop-simple-theme-root .simple-column-handle { display:none; } }

/* ============================================================
   3.10 — Touch and small-screen hardening.

   Measured before writing: at 390px the drawer (fixed, top 12 /
   bottom 12) still resolved to height:100%, so it hung 12px past the
   viewport and its session list could not scroll. The header carried no
   notch inset, the composer none for the home indicator, the message
   action row was reveal-on-hover only (invisible on touch), 14px inputs
   triggered iOS focus zoom, and the agent bar / page tabs clipped their
   own content.
   ============================================================ */
html#octop-simple-theme-root { -webkit-text-size-adjust: 100%; }

@media (max-width: 767px) {
  /* 外壳顶栏让开刘海 */
  html#octop-simple-theme-root .octop-layout-header {
    height: auto !important;
    min-height: calc(56px + env(safe-area-inset-top, 0px)) !important;
    padding-top: env(safe-area-inset-top, 0px) !important;
  }
  /* 抽屉：高度交回内容，不再越出视口底部；内层列表自己滚 */
  html#octop-simple-theme-root [class*="index-module__sidebar__"] {
    top: max(12px, env(safe-area-inset-top, 0px)) !important;
    bottom: auto !important;
    /* dvh 优先，老内核退回 vh */
    height: calc(100vh - 24px - env(safe-area-inset-top, 0px) - env(safe-area-inset-bottom, 0px)) !important;
    height: calc(100dvh - 24px - env(safe-area-inset-top, 0px) - env(safe-area-inset-bottom, 0px)) !important;
    max-height: calc(100vh - 24px - env(safe-area-inset-top, 0px) - env(safe-area-inset-bottom, 0px)) !important;
    max-height: calc(100dvh - 24px - env(safe-area-inset-top, 0px) - env(safe-area-inset-bottom, 0px)) !important;
  }
  html#octop-simple-theme-root [class*="module__sessionList__"][class] {
    height: auto !important;
    min-height: 0 !important;
    flex: 1 1 auto !important;
  }
  html#octop-simple-theme-root [class*="module__sessionItems__"] {
    flex: 1 1 auto !important;
    min-height: 0 !important;
    overflow-y: auto !important;
    overscroll-behavior: contain !important;
    padding-bottom: max(16px, env(safe-area-inset-bottom, 0px)) !important;
  }
  /* 输入区让开底部手势条 */
  html#octop-simple-theme-root [class*="module__chatInput"] {
    padding-bottom: calc(8px + env(safe-area-inset-bottom, 0px)) !important;
  }
  /* 聚焦不缩放：输入类控件不低于 16px */
  html#octop-simple-theme-root textarea,
  html#octop-simple-theme-root input:not([type="checkbox"]):not([type="radio"]):not([type="file"]),
  html#octop-simple-theme-root select {
    font-size: 16px !important;
  }
  /* 专家选择条与页内标签：可以横滑，别把字裁掉 */
  html#octop-simple-theme-root [class*="AgentSelector-module__bar"] {
    scroll-padding-inline: 16px;
    -webkit-overflow-scrolling: touch;
  }
  html#octop-simple-theme-root .octop-segmented {
    max-width: 100% !important;
    overflow-x: auto !important;
    scrollbar-width: none;
    -webkit-overflow-scrolling: touch;
  }
  html#octop-simple-theme-root .octop-segmented::-webkit-scrollbar { display: none; }
  html#octop-simple-theme-root .octop-segmented-item { flex: 0 0 auto !important; }
  html#octop-simple-theme-root .octop-segmented-item-label { padding-inline: 11px !important; }
  /* 正文里的宽内容自己滚，不顶破单列 */
  html#octop-simple-theme-root [class*="markdownBody__"] :is(pre, table) {
    max-width: 100% !important;
    overflow-x: auto !important;
    -webkit-overflow-scrolling: touch;
  }
  html#octop-simple-theme-root [class*="markdownBody__"] img {
    max-width: 100% !important;
    height: auto !important;
  }
  html#octop-simple-theme-root [class*="module__messageList__"][class] {
    overscroll-behavior: contain;
  }
}

/* 无悬停的设备：消息操作常驻，不再靠 hover 才能看见 */
@media (hover: none), (pointer: coarse) {
  html#octop-simple-theme-root [class*="module__msgMetaRow"] {
    opacity: 1 !important;
  }
  html#octop-simple-theme-root [class*="module__msgCopyBtn"],
  html#octop-simple-theme-root [class*="module__msgActionBtn"],
  html#octop-simple-theme-root .simple-msg-btn {
    width: 30px !important;
    height: 30px !important;
  }
  /* 悬浮入口：可点面积放大到 32px，视觉仍保持 28px 间距 */
  html#octop-simple-theme-root #simple-chat-dock button {
    min-width: 32px;
    min-height: 32px;
  }
  /* 触屏按压反馈（移动端默认已关掉高亮） */
  html#octop-simple-theme-root #simple-chat-dock { font-size: 11px; }
  html#octop-simple-theme-root #simple-chat-dock button:active,
  html#octop-simple-theme-root [class*="module__msgCopyBtn"]:active {
    background: var(--fn-sidebar-item-hover) !important;
  }
}

/* ============================================================
   3.11 — Attachment/file row.

   The card layer above treats every *Card__ root as a store card:
   24px padding, 18px corner, white surface. For an attachment row that
   reads wrong — it is a file, not a product tile. Measured before the
   change: 76px tall on a single 13px filename, pure white surface.
   Now it is a 48px inline strip on a paper-blue tint, with the paperclip
   in its own tinted tile so the file type reads before the name.
   ============================================================ */
html#octop-simple-theme-root {
  --simple-file-bg: #eef2f8;
  --simple-file-bg-hover: #e6ecf5;
  --simple-file-accent: #2f6feb;
  --simple-file-tile: #dbe5f4;
}
html#octop-simple-theme-root[data-theme="dark"] {
  --simple-file-bg: #222932;
  --simple-file-bg-hover: #2a323d;
  --simple-file-accent: #79a6f5;
  --simple-file-tile: #2b3747;
}
html#octop-simple-theme-root [class*="module__messageFileCard__"][class][class][class] {
  display: inline-flex !important;
  align-items: center !important;
  gap: 8px !important;
  box-sizing: border-box !important;
  height: 48px !important;
  min-height: 48px !important;
  max-width: min(100%, 360px) !important;
  padding: 8px 8px 8px 10px !important;
  border: 1px solid transparent !important;
  border-radius: 12px !important;
  background: var(--simple-file-bg) !important;
  box-shadow: none !important;
  transform: none !important;
}
html#octop-simple-theme-root [class*="module__messageFileMeta__"] {
  display: flex !important;
  align-items: center !important;
  gap: 10px !important;
  min-width: 0 !important;
  flex: 1 1 auto !important;
}
/* 图标单独成块，文件类型先于文件名被读到 */
html#octop-simple-theme-root [class*="module__messageFileIcon__"] {
  flex: none !important;
  box-sizing: border-box !important;
  width: 26px !important;
  height: 26px !important;
  padding: 5px !important;
  border-radius: 8px !important;
  background: var(--simple-file-tile) !important;
  color: var(--simple-file-accent) !important;
  stroke-width: 2 !important;
}
html#octop-simple-theme-root [class*="module__messageFileName__"] {
  font-size: 13px !important;
  line-height: 18px !important;
  font-weight: 500 !important;
  color: var(--fn-text-primary) !important;
  min-width: 0 !important;
  overflow: hidden !important;
  text-overflow: ellipsis !important;
  white-space: nowrap !important;
  direction: ltr !important;
  text-align: left !important;
}
html#octop-simple-theme-root [class*="module__messageFileActionBtn__"] {
  flex: none !important;
  display: inline-flex !important;
  align-items: center !important;
  justify-content: center !important;
  box-sizing: border-box !important;
  width: 28px !important;
  height: 28px !important;
  min-width: 0 !important;
  padding: 0 !important;
  border: 0 !important;
  border-radius: 8px !important;
  background: transparent !important;
  box-shadow: none !important;
  color: var(--fn-text-secondary) !important;
  cursor: pointer !important;
}
html#octop-simple-theme-root [class*="module__messageFileActionBtn__"]:is(:hover, :focus-visible) {
  background: var(--simple-file-bg-hover) !important;
  color: var(--simple-file-accent) !important;
}
html#octop-simple-theme-root [class*="module__messageFiles__"] {
  gap: 8px !important;
  align-items: flex-start !important;
}
@media (hover: none), (pointer: coarse) {
  html#octop-simple-theme-root [class*="module__messageFileActionBtn__"] {
    width: 32px !important;
    height: 32px !important;
  }
}

/* ============================================================
   3.9.6 — Card boundaries that survive a white page.

   Measured before writing: the store-card layer sets border:0 and a
   white surface. On the light page (also #fff) the only separation
   left was a 2px/8% shadow, so every card's left and right edge read
   as missing — worst on the quick-prompt grid, the attachment row and
   the settings cards. Dark mode had the same problem inverted
   (#2a2a2a on #0d0d0d is the only cue).

   Fix: a 1px inset ring drawn with box-shadow, so it never changes
   layout width, never stacks with the radius, and cannot be dropped by
   overflow clipping. Elevation stays on top of the ring.

   3.9.9 — .16 在白底上实渲染成 216 灰，1px 硬线太抢眼。降到 .09
   （≈233 灰）只作轮廓提示，靠底色和投影承担"这是一块面"。
   ============================================================ */
html#octop-simple-theme-root {
  --simple-card-ring: rgba(13, 13, 13, .09);
  --simple-card-ring-hover: rgba(13, 13, 13, .16);
}
html#octop-simple-theme-root[data-theme="dark"] {
  --simple-card-ring: rgba(255, 255, 255, .13);
  --simple-card-ring-hover: rgba(255, 255, 255, .2);
}
html#octop-simple-theme-root :is([class*="module__"][class*="Card__"]):not(
  :is(
    [class*="module__dimBarCard__"],
    [class*="module__donutCard__"],
    [class*="module__dimTableCard__"],
    [class*="module__trendCard__"],
    [class*="module__summaryTrendCard__"],
    /* 3.9.9 — quickCard 自带浅灰底，再套一道环会变成双线，交给底色即可 */
    [class*="module__quickCard__"]
  )
) {
  box-shadow: inset 0 0 0 1px var(--simple-card-ring), var(--simple-store-card-shadow) !important;
}
@media (hover: hover) {
  html#octop-simple-theme-root :is([class*="module__"][class*="Card__"]):not([class*="module__quickCard__"]):hover {
    box-shadow: inset 0 0 0 1px var(--simple-card-ring-hover), var(--simple-store-card-shadow-hover) !important;
  }
}
/* 选中态同样走 inset，避免被容器裁掉一半 */
html#octop-simple-theme-root [class*="module__skillCard__"]:has(input:checked) {
  box-shadow: inset 0 0 0 2px #0071e3, var(--simple-store-card-shadow) !important;
}

/* 快速提示卡：环之外再给一个独立底色，白页上也能看出是一块面 */
html#octop-simple-theme-root [class*="module__quickCard__"] {
  background: var(--fn-bg-secondary) !important;
}
html#octop-simple-theme-root [class*="module__quickCard__"]:hover {
  background: var(--simple-hover) !important;
}

/* 进行中圈圈：原来的 11px 是内容盒，加上 1.5px 描边实渲染 14–16px，
   与 15px 名称不成比例。改成 border-box 后永远是 11px。 */
html#octop-simple-theme-root .simple-agent-busy {
  box-sizing: border-box !important;
  width: 11px !important;
  height: 11px !important;
  min-width: 11px !important;
  max-width: 11px !important;
  min-height: 11px !important;
}

/* "NEW" 角标在 15px 名称行里会被行框裁掉右侧 3px：给自己留出内距，
   并禁止父级把它当作可压缩项。 */
html#octop-simple-theme-root [class*="nav-badge"],
html#octop-simple-theme-root [class*="badge-new"] {
  flex: none !important;
  padding-inline: 5px !important;
  line-height: 16px !important;
  overflow: visible !important;
}

/* 导航分组标题：折叠箭头原来被 space-between 推到 x188，离标题 168px，
   读起来像两件无关的东西。收成一组，右侧留 8px 光差。 */
html#octop-simple-theme-root [class*="Sidebar-module__navGroupHeader"] {
  justify-content: flex-start !important;
  gap: 6px !important;
}
html#octop-simple-theme-root [class*="Sidebar-module__navGroupHeader"] svg {
  margin-left: auto !important;
  margin-right: 0 !important;
  width: 12px !important;
  height: 12px !important;
  color: var(--fn-text-quaternary) !important;
}

/* 会话行的"更多"悬浮钮原来用 absolute right:4px 顶在行尾，与 22px 的
   行内留白不一致；改成行内 flex 尾项，和 lead 图标同一条基线。 */
html#octop-simple-theme-root [class*="module__sessionRow__"] {
  padding-right: 6px !important;
}
html#octop-simple-theme-root [class*="module__sessionRowMore"] {
  position: static !important;
  transform: none !important;
  right: auto !important;
  margin-left: auto !important;
  flex: none !important;
}

/* 快速卡：图标与两行文字之间的固定 10px 呼吸，图标块自己不会被压扁 */
html#octop-simple-theme-root [class*="module__quickCard__"] {
  gap: 10px !important;
  align-items: flex-start !important;
}
html#octop-simple-theme-root [class*="module__quickCardIcon"] {
  flex: none !important;
}

/* ==============================================================
   3.9.7 - 768-1099px: 左侧只留 44px 图标栏
   ============================================================== */
@media (min-width: 768px) and (max-width: 1099px) {
  /* 3.9.12 — 这条规则原来只按「有 drag 直系子节点」认侧栏，但
     .page-content 和 .chatMain 里也各有一个 octop-desktop-drag，于是 768-1099
     之间整块主内容被夹成 44px 宽（实测 /admin/advanced、/chat 全白，只剩一条图标栏）。
     改成同时要求容器里有 navGroup（只有侧栏满足），主内容区不再被误伤。 */
  /* rail 本体：44px 图标列 */
  html#octop-simple-theme-root div:has(> [class*="octop-desktop-drag"]):has([class*="navGroup"]) {
    width: 44px !important;
    min-width: 44px !important;
    max-width: 44px !important;
    flex: 0 0 44px !important;
    padding-inline: 0 !important;
  }
  /* 顶栏：44 高居中，logo 与版本号藏掉 */
  html#octop-simple-theme-root div:has(> [class*="octop-desktop-drag"]):has([class*="navGroup"]) > .octop-desktop-drag {
    width: 44px !important;
    height: 44px !important;
    padding-inline: 0 !important;
    justify-content: center !important;
  }
  html#octop-simple-theme-root div:has(> [class*="octop-desktop-drag"]):has([class*="navGroup"]) [class*="versionBadge"],
  html#octop-simple-theme-root div:has(> [class*="octop-desktop-drag"]):has([class*="navGroup"]) > .octop-desktop-drag img {
    display: none !important;
  }
  /* 抽屉列 0 宽，sidebar 跟着夹住，抽屉内容整段隐藏 */
  html#octop-simple-theme-root div:has(> [class*="sidebarWrapper"]) {
    width: 0 !important;
  }
  html#octop-simple-theme-root div:has(> [class*="sidebarWrapper"]) {
    min-width: 0 !important;
    flex: 0 0 0 !important;
    overflow: visible !important;
  }
  html#octop-simple-theme-root [class*="sessionSearchWrap"],
  html#octop-simple-theme-root [class*="sessionScopeTabs"],
  html#octop-simple-theme-root [class*="sessionItems__"],
  html#octop-simple-theme-root [class*="expertSection"] {
    display: none !important;
  }
  html#octop-simple-theme-root [class*="newChatRow"],
  html#octop-simple-theme-root [class*="sessionList__"] {
    display: none !important;
  }
  /* 导航收成 44 见方、图标居中 */
  html#octop-simple-theme-root [class*="navGroup"],
  html#octop-simple-theme-root [class*="navGroupItems"],
  html#octop-simple-theme-root [class*="navItemRow"],
  html#octop-simple-theme-root [class*="navItemMain"] {
    width: 44px !important;
  }
  html#octop-simple-theme-root [class*="navItem"] {
    margin-inline: 0 !important;
  }
  html#octop-simple-theme-root [class*="navItemRow"],
  html#octop-simple-theme-root [class*="navItemMain"] {
    height: 32px !important;
    padding: 0 !important;
    flex: none !important;
  }
  html#octop-simple-theme-root [class*="navItemMain"] {
    justify-content: center;
  }
  html#octop-simple-theme-root [class*="navItemMain"] > span:not(:has(svg)) {
    display: none !important;
    width: 0 !important;
  }
  html#octop-simple-theme-root [class*="navItemMain"] svg {
    width: 18px !important;
    height: 18px !important;
    margin: 0 !important;
  }
  /* 分组标题在图标列里只是噪音 */
  html#octop-simple-theme-root [class*="navGroupHeader"] {
    height: 0 !important;
    min-height: 0 !important;
    margin: 0 !important;
    padding: 0 !important;
    overflow: hidden !important;
    border: 0 !important;
  }
  /* 底部账号区只留头像 */
  html#octop-simple-theme-root div:has(> .octop-desktop-drag):has([class*="navGroup"]) button[class*="AvatarDropdown-module__trigger"] {
    width: 36px !important;
    padding: 0 !important;
    margin-inline: auto !important;
    justify-content: center !important;
  }
  html#octop-simple-theme-root div:has(> .octop-desktop-drag):has([class*="navGroup"]) button[class*="AvatarDropdown-module__trigger"] > :not([class*="accountAvatar"]) {
    display: none !important;
  }
  /* 抽屉真被打开时让出 248 宽，并把列表放回来。
     只写 width 不够：上面那条 flex:0 0 0 的 flex-basis 会赢过 width，
     外层停在 0 宽，248px 的列表就悬空盖住输入框左侧的「+」。 */
  html#octop-simple-theme-root div:has(> [class*="sidebarWrapper"]):has([class*="sidebarOpen"]) {
    width: 248px !important;
    min-width: 248px !important;
    flex: 0 0 248px !important;
  }
  html#octop-simple-theme-root [class*="sidebarOpen"] [class*="sessionList__"] {
    display: flex !important;
  }
  /* 3.8 的 flex:1 / flex-start 特异性更高，这里压回去 */
  html#octop-simple-theme-root [class*="navItemRow"] > [class*="navItemMain"] {
    flex: 0 0 44px !important;
    justify-content: center !important;
  }
  /* rail 内层还有 12px 内边距，会把 44px 的行推到右边 */
  html#octop-simple-theme-root div:has(> [class*="navGroup"]) {
    padding-inline: 0 !important;
  }
  html#octop-simple-theme-root [class*="navItemRow"] > [class*="chatRailExpandBtn"] {
    display: none !important;
  }
  html#octop-simple-theme-root div:has(> .octop-desktop-drag):has([class*="navGroup"]) > div {
    padding-inline: 0 !important;
  }
  html#octop-simple-theme-root [class*="nav-badge"] {
    display: none !important;
  }
  /* 头像外层 span 被 8px 内边距压成 16px，头像整体左溢 */
  html#octop-simple-theme-root [class*="AvatarDropdown-module__trigger"] > span:has([class*="Avatar"]) {
    width: 36px !important;
    padding-inline: 0 !important;
  }
  /* 图标 span 固定 18px，配合按钮 44px 居中，图标中心正好 22 */
  html#octop-simple-theme-root [class*="navItemMain"] > span:has(svg) {
    display: flex !important;
    align-items: center !important;
    justify-content: center !important;
    width: 18px !important;
    flex: 0 0 18px !important;
    margin: 0 !important;
  }
  html#octop-simple-theme-root [class*="navItemMain"] {
    gap: 0 !important;
  }
}


/* =========================================================================
   3.9.18 — 欢迎页快捷卡：一张安静的白卡
   原来的「灰面 + 隐形图标块 + 无阴影」在纯白页上像一块贴纸，跟标题、输入框
   都不是一个语气。这里给一套和设置页卡片同源的规格：白面、一道发丝环、
   极浅的环境光；hover 只抬 1px、环和光各深一档，图标块随卡片一起亮一点。
   ========================================================================= */
html#octop-simple-theme-root [class*="module__quickSection"] {
  margin-top: 26px !important;
}
html#octop-simple-theme-root [class*="module__quickCards"] {
  grid-template-columns: repeat(auto-fit, minmax(212px, 1fr)) !important;
  gap: 12px !important;
  /* 卡片左沿与「快速提示」标题、正文同一条竖线，不再额外缩进 8px */
  padding-inline: 0 !important;
}
html#octop-simple-theme-root [class*="module__quickCard__"] {
  display: flex !important;
  flex-direction: row !important;
  align-items: flex-start !important;
  flex-wrap: nowrap !important;
  gap: 12px !important;
  padding: 14px 16px !important;
  border: 0 !important;
  border-radius: 14px !important;
  background: var(--simple-store-card-bg) !important;
  box-shadow: inset 0 0 0 1px var(--simple-card-ring), var(--simple-store-card-shadow) !important;
  color: var(--fn-text-primary) !important;
  transition: transform .22s cubic-bezier(.2,.8,.3,1),
              box-shadow .22s cubic-bezier(.2,.8,.3,1),
              background-color .22s ease !important;
}
html#octop-simple-theme-root [class*="module__quickCard__"]:hover {
  background: var(--simple-store-card-bg) !important;
  box-shadow: inset 0 0 0 1px var(--simple-card-ring-hover), var(--simple-store-card-shadow-hover) !important;
}
html#octop-simple-theme-root [class*="module__quickCard__"]:active {
  transform: translateY(0) !important;
}
@media (hover: hover) and (prefers-reduced-motion: no-preference) {
  html#octop-simple-theme-root [class*="module__quickCard__"]:hover {
    transform: translateY(-1px) !important;
  }
}
html#octop-simple-theme-root [class*="module__quickCardIcon"] {
  flex: 0 0 30px !important;
  width: 30px !important;
  height: 30px !important;
  border-radius: 9px !important;
  background: var(--fn-bg-secondary) !important;
  color: var(--fn-text-secondary) !important;
  display: grid !important;
  place-items: center !important;
  transition: background-color .22s ease !important;
}
html#octop-simple-theme-root [class*="module__quickCard__"]:hover [class*="module__quickCardIcon"] {
  background: var(--fn-bg-secondary-hover) !important;
}
/* 深色下卡面 2a2a2a 与 2f2f2f 只差一点点，图标块会糊进卡里，单独抬一档亮度 */
html#octop-simple-theme-root[data-theme="dark"] [class*="module__quickCardIcon"] {
  background: rgba(255,255,255,.08) !important;
}
html#octop-simple-theme-root[data-theme="dark"] [class*="module__quickCard__"]:hover [class*="module__quickCardIcon"] {
  background: rgba(255,255,255,.14) !important;
}
html#octop-simple-theme-root [class*="module__quickCardIcon"] svg {
  width: 16px !important;
  height: 16px !important;
  min-width: 16px !important;
  max-width: 16px !important;
  flex: none !important;
  display: block !important;
}
html#octop-simple-theme-root [class*="module__quickCardBody"] {
  display: flex !important;
  flex-direction: column !important;
  gap: 2px !important;
  min-width: 0 !important;
  font-size: 13.5px !important;
  line-height: 19px !important;
  font-weight: 500 !important;
  color: var(--fn-text-primary) !important;
}
html#octop-simple-theme-root [class*="module__quickCardTitleRow"],
html#octop-simple-theme-root [class*="module__quickCardTitle"] {
  font-size: 13.5px !important;
  line-height: 19px !important;
  font-weight: 600 !important;
  letter-spacing: -.006em !important;
  color: var(--fn-text-primary) !important;
}
html#octop-simple-theme-root [class*="module__quickCardDesc"] {
  font-size: 12.5px !important;
  line-height: 18px !important;
  font-weight: 400 !important;
  color: var(--fn-text-tertiary) !important;
  overflow: hidden !important;
  display: -webkit-box !important;
  -webkit-line-clamp: 2 !important;
  -webkit-box-orient: vertical !important;
}
/* 「换一批」按钮：给一个圆角 hover 面，别让它裸在卡片下面 */
html#octop-simple-theme-root [class*="module__quickMoreButton"] {
  display: inline-flex !important;
  align-items: center !important;
  justify-content: center !important;
  width: 28px !important;
  height: 28px !important;
  margin-top: 10px !important;
  padding: 0 !important;
  border: 0 !important;
  border-radius: 8px !important;
  background: transparent !important;
  color: var(--fn-text-tertiary) !important;
  transition: background-color .18s ease, color .18s ease !important;
}
html#octop-simple-theme-root [class*="module__quickMoreButton"]:hover {
  background: var(--fn-bg-secondary) !important;
  color: var(--fn-text-primary) !important;
}

/* ===== 3.9.20 — 专家详情抽屉：技能/子智能体卡只保留一层描边 ===== */
/* 应用里这些卡片是「fileItem 外框（1px + 圆角 10）里再放一个 entityCard」，
   entityCard 本身没有边框/底色/圆角；主题的 Card__ 通配规则多给了一层 18px 圆角
   + 1px 内描边 + 投影，于是同一处出现两道描边、且圆角不一致。这里把内层还给应用。 */
html#octop-simple-theme-root [class*="module__entityCard"][class*="Card__"]:not(#\\9),
html#octop-simple-theme-root [class*="module__entityCard"][class*="Card__"]:not(#\\9):hover {
  border: 0 !important;
  border-radius: 0 !important;
  background: transparent !important;
  box-shadow: none !important;
}
/* 外框本身也别再叠主题的阴影，只留应用那道 1px 描边 */
html#octop-simple-theme-root [class*="module__fileItem"]:has([class*="module__entityCard"]):not(#\\9) {
  box-shadow: none !important;
  border-color: var(--simple-hairline) !important;
  border-radius: 14px !important;
}

/* Tablet edge controls must not be covered by desktop column-resize handles. */
@media (max-width: 1099px) {
  html#octop-simple-theme-root .simple-column-handle { display: none !important; }
}
@media (min-width: 768px) and (max-width: 1099px) {
  html#octop-simple-theme-root div:has(> [class*="module__sidebarWrapper__"]) {
    position: relative !important; z-index: 5 !important;
  }
  html#octop-simple-theme-root [class*="RailEdgeControl-module__btn__"] {
    pointer-events: auto !important; opacity: 1 !important;
  }
  html#octop-simple-theme-root [class*="module__sidebarOpen__"] :is(
    [class*="module__expertSection"], [class*="module__sessionItems__"],
    [class*="module__sessionScopeTabs"], [class*="module__sessionSearchWrap"]
  ) { display: flex !important; }
  html#octop-simple-theme-root [class*="module__sidebarOpen__"] [class*="module__expertSection"] {
    flex-direction: column !important;
  }
}

/* 1.0 — bounded catalog surfaces and persistent expert pin state.
   Keep 3.9.20 entityCard/fileItem overrides above unchanged.
   Gutters live INSIDE each grid: overflow:auto ancestors keep scrolling,
   while the first/last card now has room for its ambient shadow. */
html#octop-simple-theme-root .page-content :is(
  [class*="module__channelsGrid__"],
  [class*="module__cardGrid__"]
) {
  box-sizing: border-box !important;
  min-width: 0 !important;
  padding: 16px 16px 24px !important;
  gap: 20px !important;
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 260px), 1fr)) !important;
}
html#octop-simple-theme-root [class*="module__channelsBody__"] {
  padding: 0 !important;
  min-width: 0 !important;
}
html#octop-simple-theme-root .page-content :is(
  [class*="module__channelCard__"],
  article[class*="module__card__"],
  [class*="module__agentCard2__"]
):not(#simple-catalog-specificity) {
  border: 0 !important;
  border-radius: 20px !important;
  background: var(--simple-store-card-bg) !important;
  box-shadow: 0 3px 12px rgba(0,0,0,.075) !important;
  padding: 24px !important;
  min-width: 0 !important;
  max-width: 100% !important;
  box-sizing: border-box !important;
  transform: none !important;
}
html#octop-simple-theme-root[data-theme="dark"] .page-content :is(
  [class*="module__channelCard__"], article[class*="module__card__"], [class*="module__agentCard2__"]
):not(#simple-catalog-specificity) {
  box-shadow: 0 3px 12px rgba(0,0,0,.22) !important;
}
/* A quiet vertical hierarchy like the supplied Apple benefit cards. */
html#octop-simple-theme-root [class*="module__channelCard__"] [class*="module__cardTop__"] {
  display: grid !important;
  grid-template-columns: minmax(0,1fr) auto !important;
  gap: 16px 12px !important;
  align-items: center !important;
  margin-bottom: 12px !important;
}
html#octop-simple-theme-root [class*="module__channelCard__"] [class*="module__channelIcon__"] {
  width: 32px !important; height: 32px !important; grid-column: 1 !important;
}
html#octop-simple-theme-root [class*="module__channelCard__"] [class*="module__cardTop__"] > div {
  grid-column: 2 !important; grid-row: 1 !important;
}
html#octop-simple-theme-root [class*="module__channelCard__"] [class*="module__cardTitle__"] {
  grid-column: 1 / -1 !important; grid-row: 2 !important;
  font-size: 18px !important; font-weight: 600 !important; line-height: 26px !important;
}
html#octop-simple-theme-root [class*="module__channelCard__"] [class*="module__cardDescription__"] {
  margin: 0 !important; line-height: 22px !important;
  min-height: 66px !important; max-height: none !important;
  display: block !important; overflow-wrap: anywhere !important;
}
html#octop-simple-theme-root [class*="module__channelCard__"] [class*="module__cardBottom__"] {
  margin-top: 24px !important; padding: 0 !important; border: 0 !important;
}
html#octop-simple-theme-root article[class*="module__card__"]:has([class*="module__cardMetaRow__"]) {
  opacity: 1 !important;
}
html#octop-simple-theme-root article[class*="module__card__"] :is([class*="module__cardMetaRow__"], [class*="module__cardFooter__"]) {
  flex-wrap: wrap !important; gap: 8px !important;
}
html#octop-simple-theme-root article[class*="module__card__"] [class*="module__cardTitleCol__"] {
  min-width: 0 !important;
}
/* Footer actions must wrap at narrow card widths, including tablet two-column grids. */
html#octop-simple-theme-root [class*="module__agentCard2Footer__"] {
  flex-wrap: wrap !important; gap: 8px !important;
}
html#octop-simple-theme-root [class*="module__agentCard2TitleBlock__"] { min-width: 0 !important; }
/* Active state is semantic, not hover. Reserve the space at the same time. */
html#octop-simple-theme-root [class*="module__agentPinBtnActive__"] {
  opacity: 1 !important;
  color: var(--fn-text-primary) !important;
  visibility: visible !important;
}
html#octop-simple-theme-root :is([class*="module__agentRowNameRow__"], [class*="module__agentCardNameRow__"]):has([class*="module__agentPinBtnActive__"]) [class*="module__agentNameCluster"] {
  padding-right: 46px !important;
}
html#octop-simple-theme-root :is([class*="module__agentRow__"], [class*="module__agentCard__"]):focus-within :is([class*="module__agentPinBtn__"], [class*="module__agentNewChatBtn__"]) {
  opacity: 1 !important;
}
@media (hover: none), (pointer: coarse) {
  html#octop-simple-theme-root :is([class*="module__agentPinBtn__"], [class*="module__agentNewChatBtn__"]) {
    opacity: 1 !important; width: 44px !important; height: 44px !important;
  }
  html#octop-simple-theme-root :is([class*="module__agentRowNameRow__"], [class*="module__agentCardNameRow__"]) {
    min-height: 44px !important;
  }
  html#octop-simple-theme-root :is([class*="module__agentRowNameRow__"], [class*="module__agentCardNameRow__"]) [class*="module__agentNameCluster"] {
    padding-right: 92px !important;
  }
}
@media (max-width: 767px) {
  html#octop-simple-theme-root .page-content :is([class*="module__channelsGrid__"], [class*="module__cardGrid__"]) {
    grid-template-columns: minmax(0,1fr) !important;
    gap: 16px !important;
  }
  html#octop-simple-theme-root .page-content :is([class*="module__channelCard__"], article[class*="module__card__"], [class*="module__agentCard2__"]):not(#simple-catalog-specificity) {
    padding: 20px !important;
  }
  html#octop-simple-theme-root [class*="module__agentCard2Footer__"] {
    flex-wrap: wrap !important; gap: 8px !important;
  }
  html#octop-simple-theme-root [class*="module__agentCard2TitleBlock__"] { min-width: 0 !important; }
  html#octop-simple-theme-root .octop-drawer-content-wrapper { max-width: 100% !important; }
  html#octop-simple-theme-root .octop-drawer-body { min-width: 0 !important; overflow-wrap: anywhere !important; }
}

/* 1.0 — shared card surface, applied only to audited component roots.
   No module__*Card__ catch-all: entityCard remains owned by fileItem (3.9.20). */
html#octop-simple-theme-root {
  --simple-card-radius: 20px;
  --simple-card-surface: var(--simple-store-card-bg);
  --simple-card-shadow: 0 3px 12px rgba(0,0,0,.075);
  --simple-card-shadow-dark: 0 3px 12px rgba(0,0,0,.22);
  --simple-card-padding: 24px;
  --simple-card-grid-safe: 16px;
  --simple-card-hairline: transparent;
}
html#octop-simple-theme-root[data-theme="dark"] { --simple-card-shadow: var(--simple-card-shadow-dark); }
/* Audited card roots. Keep entityCard and chart inner widgets out. */
html#octop-simple-theme-root :is(
 [class*="module__skillCard__"], [class*="module__toolsPanel__card__"],
 [class*="ToolsPanel-module__card__"], [class*="module__typeCard__"],
 [class*="module__catalogCard__"], [class*="module__expertTemplateCard__"],
 [class*="module__userCard__"], [class*="module__providerCard__"],
 [class*="module__backendCard__"], [class*="catalogTypeCard-module__card__"],
 [class*="module__settingCard__"], [class*="module__candidatesCard__"],
 [class*="module__configCard__"], [class*="module__versionCard__"],
 [class*="module__emptyStateSuggestionItem__"], [class*="module__card__"],
 [class*="module__agentCard2__"]
):not([class*="entityCard__"]):not([class*="quickCard__"]):not(#simple-card-exclusion) {
  border: 0 !important; border-radius: var(--simple-card-radius) !important;
  background: var(--simple-card-surface) !important;
  box-shadow: var(--simple-card-shadow) !important;
  box-sizing: border-box !important; min-width: 0 !important; max-width: 100% !important;
}
/* Cards whose contents are cards or charts retain their internal rhythm. */
html#octop-simple-theme-root :is(
 [class*="module__skillCard__"], [class*="ToolsPanel-module__card__"],
 [class*="module__typeCard__"], [class*="module__catalogCard__"],
 [class*="module__expertTemplateCard__"], [class*="module__userCard__"],
 [class*="module__providerCard__"], [class*="module__backendCard__"],
 [class*="module__settingCard__"], [class*="module__candidatesCard__"],
 [class*="module__configCard__"], [class*="module__versionCard__"],
 [class*="module__emptyStateSuggestionItem__"]
):not([class*="entityCard__"]):not(#simple-card-exclusion) { padding: var(--simple-card-padding) !important; }
/* Every audited grid gets an internal shadow gutter; the scroll owner stays intact. */
html#octop-simple-theme-root :is(
 [class*="module__skillsGrid__"], [class*="ToolsPanel-module__grid__"],
 [class*="module__typeGrid__"], [class*="module__catalogGrid__"],
 [class*="module__cardGrid__"], [class*="module__userCardGrid__"],
 [class*="module__providerCards__"], [class*="module__providerGrid__"],
 [class*="storage-module__cardGrid__"], [class*="module__summaryGrid__"],
 [class*="module__trendGrid__"], [class*="module__dimChartRow__"],
 [class*="module__versionGrid__"], [class*="module__grid__"]
) { box-sizing:border-box !important; min-width:0 !important; padding:16px 16px 24px !important; gap:20px !important; }
@media (max-width:767px) {
 html#octop-simple-theme-root :is(
  [class*="module__skillsGrid__"], [class*="ToolsPanel-module__grid__"], [class*="module__typeGrid__"],
  [class*="module__catalogGrid__"], [class*="module__cardGrid__"], [class*="module__userCardGrid__"],
  [class*="module__providerCards__"], [class*="module__providerGrid__"], [class*="storage-module__cardGrid__"],
  [class*="module__summaryGrid__"], [class*="module__trendGrid__"], [class*="module__dimChartRow__"],
  [class*="module__versionGrid__"], [class*="module__grid__"]
 ) { grid-template-columns:minmax(0,1fr) !important; gap:16px !important; }
 html#octop-simple-theme-root :is(
  [class*="module__skillCard__"], [class*="ToolsPanel-module__card__"], [class*="module__typeCard__"],
  [class*="module__catalogCard__"], [class*="module__expertTemplateCard__"], [class*="module__userCard__"],
  [class*="module__providerCard__"], [class*="module__backendCard__"], [class*="module__settingCard__"],
  [class*="module__candidatesCard__"], [class*="module__configCard__"], [class*="module__versionCard__"],
  [class*="module__emptyStateSuggestionItem__"], [class*="module__card__"]
 ):not([class*="entityCard__"]):not(#simple-card-exclusion) { padding:20px !important; }
}
/* Empty guides are standalone surfaces, not nested Card__ internals. */
html#octop-simple-theme-root [class*="StreamSetupGuide-module__card__"] {
 border:0 !important; border-radius:var(--simple-card-radius) !important;
 background:var(--simple-card-surface) !important; box-shadow:var(--simple-card-shadow) !important;
 padding:var(--simple-card-padding) !important; box-sizing:border-box !important; max-width:100% !important;
}
/* Explicitly preserve the 3.9.20 expert detail single outer frame. */
html#octop-simple-theme-root [class*="entityCard__"] { border:0 !important; border-radius:0 !important; background:transparent !important; box-shadow:none !important; padding:24px !important; }
html#octop-simple-theme-root [class*="fileItem__"]:has([class*="entityCard__"]) { border-radius:14px !important; box-shadow:none !important; }
@media (max-width:767px) {
 html#octop-simple-theme-root [class*="module__tableCard__"] { width:100% !important; max-width:100% !important; box-sizing:border-box !important; overflow:hidden !important; }
}

/* 1.0.1 — deletion only: neutral warning chrome, readable risk copy, black actions. */
html#octop-simple-theme-root [data-simple-delete-dialog] {
  --simple-delete-inset:24px;
  max-width:calc(100vw - 32px) !important;
  box-sizing:border-box !important;
}
html#octop-simple-theme-root [data-simple-delete-dialog] :is(.octop-modal-content,.octop-ant-modal-content) {
  padding:var(--simple-delete-inset) !important;
}
/* confirm() already renders its title inside confirm-paragraph; avoid the duplicate header. */
html#octop-simple-theme-root [data-simple-delete-dialog]:is(.octop-modal-confirm,.octop-ant-modal-confirm) > div > :is(.octop-modal-content,.octop-ant-modal-content) > :is(.octop-modal-header,.octop-ant-modal-header) { display:none !important; }
html#octop-simple-theme-root [data-simple-delete-dialog] :is(.octop-modal-header,.octop-ant-modal-header) { padding:0 0 12px !important; }
html#octop-simple-theme-root [data-simple-delete-dialog] :is(.octop-modal-body,.octop-ant-modal-body,.octop-modal-footer,.octop-ant-modal-footer) {
  padding:0 !important; min-width:0 !important;
}
html#octop-simple-theme-root [data-simple-delete-dialog] :is(.octop-popover-inner,.octop-ant-popover-inner) {
  padding:var(--simple-delete-inset) !important; border-radius:16px !important;
  max-width:100% !important; box-sizing:border-box !important;
}
html#octop-simple-theme-root [data-simple-delete-dialog] :is(.octop-modal-confirm-body,.octop-popconfirm-message) {
  display:flex !important; gap:12px !important; align-items:flex-start !important; min-width:0 !important;
}
html#octop-simple-theme-root [data-simple-delete-dialog] :is(.octop-modal-confirm-paragraph,.octop-popconfirm-message-text) {
  flex:1 !important; min-width:0 !important; max-width:100% !important; margin:0 !important;
}
html#octop-simple-theme-root [data-simple-delete-dialog] :is(.octop-modal-confirm-title,.octop-popconfirm-title) {
  display:block !important; font-size:16px !important; line-height:24px !important;
  margin:0 !important; overflow-wrap:anywhere !important; white-space:normal !important;
}
html#octop-simple-theme-root [data-simple-delete-dialog] :is(.octop-modal-confirm-content,.octop-popconfirm-description) {
  margin:10px 0 0 !important; line-height:1.65 !important;
  overflow-wrap:anywhere !important; white-space:normal !important; max-width:100% !important;
}
/* Only the confirmation's decorative warning icon/background is neutralized.
   Risk text, semantic alerts and field validation are deliberately untouched. */
html#octop-simple-theme-root [data-simple-delete-dialog] :is(.octop-modal-confirm-body > .anticon,.octop-popconfirm-message-icon,.octop-popconfirm-message-icon > .anticon) {
  color:var(--fn-text-secondary) !important; background:transparent !important;
  position:static !important; flex:none !important; margin:2px 0 0 !important;
}
html#octop-simple-theme-root [data-simple-delete-dialog] :is(.octop-popconfirm-message,.octop-modal-confirm-body) { background:transparent !important; }
html#octop-simple-theme-root [data-simple-delete-footer] {
  display:flex !important; flex-wrap:wrap !important; justify-content:flex-end !important;
  align-items:center !important; gap:12px !important; margin:24px 0 0 !important;
}
html#octop-simple-theme-root [data-simple-delete-footer] > button { margin:0 !important; }
html#octop-simple-theme-root [data-simple-delete-action]:not(#simple-delete-specificity) {
  background:#111 !important; color:#fff !important; border:1px solid #666 !important;
  border-radius:10px !important; box-shadow:none !important;
  display:inline-flex !important; align-items:center !important; justify-content:center !important;
  padding:7px 14px !important; min-height:36px !important; line-height:20px !important;
  white-space:normal !important; overflow-wrap:anywhere !important; text-decoration:none !important;
}
html#octop-simple-theme-root [data-simple-delete-action]:not(#simple-delete-specificity):has(svg):not(:has(span:not(.octop-btn-icon))) {
  min-width:36px !important; padding:7px !important;
}
html#octop-simple-theme-root [data-simple-delete-action]:not(#simple-delete-specificity):not(:disabled):not([aria-disabled="true"]):not(.octop-btn-loading):hover {
  background:#303030 !important; color:#fff !important; border-color:#999 !important;
}
html#octop-simple-theme-root [data-simple-delete-action]:not(#simple-delete-specificity):focus-visible {
  outline:2px solid var(--fn-text-primary) !important; outline-offset:3px !important;
}
html#octop-simple-theme-root [data-simple-delete-action]:not(#simple-delete-specificity):is(:disabled,[aria-disabled="true"],.octop-btn-loading,[aria-busy="true"]) {
  opacity:.45 !important; cursor:not-allowed !important;
}
@media (max-width:600px) {
  html#octop-simple-theme-root [data-simple-delete-dialog] { --simple-delete-inset:20px; }
  html#octop-simple-theme-root [data-simple-delete-footer] { gap:10px !important; }
  html#octop-simple-theme-root [data-simple-delete-footer] > button { min-height:44px !important; height:auto !important; }
}
@media (hover:none),(pointer:coarse) {
  html#octop-simple-theme-root [data-simple-delete-action]:not(#simple-delete-specificity) { min-width:44px !important; min-height:44px !important; height:auto !important; }
}

/* Portal placement is computed before theme padding settles; constrain only mobile delete popovers. */
@media (max-width:600px) {
 html#octop-simple-theme-root .octop-popconfirm[data-simple-delete-dialog] {
   left:16px !important; right:auto !important; width:calc(100vw - 32px) !important;
   max-width:calc(100vw - 32px) !important;
 }
}
html#octop-simple-theme-root [data-simple-delete-dialog] :is(.octop-modal-confirm-title,.octop-popconfirm-title) { color:var(--fn-text-primary) !important; }
html#octop-simple-theme-root [data-simple-delete-dialog] :is(.octop-modal-confirm-content,.octop-popconfirm-description) { color:var(--fn-text-secondary) !important; }
`;

/* ------------------------------- 注入 ------------------------------- */

function currentMode() {
  const attr = document.documentElement.getAttribute("data-theme");
  if (attr === "dark" || attr === "light") return attr;
  try {
    return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  } catch (err) {
    return "light";
  }
}

function applyTheme() {
  if (disposed) return false;
  try {
    const root = document.documentElement;
    root.id = ROOT_ID;
    // 供样式或调试脚本读取当前模式，避免各处自己再判断一次
    root.setAttribute("data-octop-simple-theme", VERSION);
    let style = document.getElementById(STYLE_ID);
    if (!style) {
      style = document.createElement("style");
      style.id = STYLE_ID;
      style.setAttribute("data-plugin", PLUGIN_ID);
      document.head.appendChild(style);
    }
    if (style.textContent !== CSS) style.textContent = CSS;
    // 主题色跟随（移动端地址栏 / PWA 标题栏）
    for (const meta of document.querySelectorAll('meta[name="theme-color"]')) {
      meta.setAttribute("content", currentMode() === "dark" ? "#212121" : "#ffffff");
      meta.removeAttribute("media");
    }
    queueMicrotask(() => {
      if (disposed) return;
      initColumnResize();
      // 样式刚注入时输入框可能已经在（懒加载路由先挂载），这里补一次；
      // 否则浮动条要等下一次无关的 DOM 变更才出现。
      syncFloatingControls();
      settleFloatingControls();
    });
    return true;
  } catch (err) {
    console.warn("[simple-theme] 应用主题失败:", err);
    return false;
  }
}

function removeTheme() {
  window.__simpleDeleteObserver?.disconnect();
  document.querySelectorAll("[data-simple-delete-action],[data-simple-delete-dialog],[data-simple-delete-footer]").forEach(e => { e.removeAttribute("data-simple-delete-action"); e.removeAttribute("data-simple-delete-dialog"); e.removeAttribute("data-simple-delete-footer"); });
  window.__simpleColumnResize?.destroy();
  if (window.__simpleAgentBusyTimer) { clearInterval(window.__simpleAgentBusyTimer); delete window.__simpleAgentBusyTimer; }
  if (window.__simpleAgentBusyPoll) { clearInterval(window.__simpleAgentBusyPoll); delete window.__simpleAgentBusyPoll; }
  document.querySelectorAll('.simple-agent-busy').forEach(e => e.remove());
  document.querySelectorAll('.simple-msg-collapse, .simple-msg-top').forEach(e => e.remove());
  document.querySelectorAll('.simple-process-collapse').forEach(e => e.remove());
  document.querySelectorAll('.simple-turn-answer-clamped').forEach(e => e.classList.remove('simple-turn-answer-clamped'));
  document.getElementById("simple-chat-dock")?.remove();
  const root = document.documentElement;
  if (root.id === ROOT_ID) root.id = "";
  root.removeAttribute("data-octop-simple-theme");
  const style = document.getElementById(STYLE_ID);
  if (style) style.remove();
  for (const icon of document.querySelectorAll('[data-simple-model-brand]')) {
    if (icon.tagName === 'IMG') icon.setAttribute('src', icon.dataset.simpleOriginal || '');
    else icon.style.removeProperty('background-image');
    delete icon.dataset.simpleModelBrand;
  }
}

window.__octopSimpleTheme = {
  version: VERSION,
  apply: applyTheme,
  remove: removeTheme,
  get active() {
    return !!document.getElementById(STYLE_ID);
  },
  get mode() {
    return currentMode();
  },
  /* 调试用：专家忙碌状态是轮询来的，出问题时先看这张表 */
  get agentBusy() {
    try { return Object.fromEntries(agentBusyState); } catch (err) { return null; }
  },
  pollAgents() {
    try { return refreshAgentDirectory().then(pollAgentBusy); } catch (err) { return null; }
  },
};


/* Match the model family, not an OpenAI-compatible proxy's transport kind. */
/* 自动生成，勿手改：python3 tools/gen_model_icons.py
   图标来源 https://lobehub.com/zh/icons（@lobehub/icons-static-svg，MIT） */
const MODEL_ICONS = {"OpenAI":{"light":"data:image/svg+xml,%3Csvg%20fill=%22%2310A37F%22%20fill-rule=%22evenodd%22%20height=%221em%22%20style=%22flex:none;line-height:1%22%20viewBox=%220%200%2024%2024%22%20width=%221em%22%20xmlns=%22http://www.w3.org/2000/svg%22%3E%3Ctitle%3EOpenAI%3C/title%3E%3Cpath%20d=%22M9.205%208.658v-2.26c0-.19.072-.333.238-.428l4.543-2.616c.619-.357%201.356-.523%202.117-.523%202.854%200%204.662%202.212%204.662%204.566%200%20.167%200%20.357-.024.547l-4.71-2.759a.797.797%200%2000-.856%200l-5.97%203.473zm10.609%208.8V12.06c0-.333-.143-.57-.429-.737l-5.97-3.473%201.95-1.118a.433.433%200%2001.476%200l4.543%202.617c1.309.76%202.189%202.378%202.189%203.948%200%201.808-1.07%203.473-2.76%204.163zM7.802%2012.703l-1.95-1.142c-.167-.095-.239-.238-.239-.428V5.899c0-2.545%201.95-4.472%204.591-4.472%201%200%201.927.333%202.712.928L8.23%205.067c-.285.166-.428.404-.428.737v6.898zM12%2015.128l-2.795-1.57v-3.33L12%208.658l2.795%201.57v3.33L12%2015.128zm1.796%207.23c-1%200-1.927-.332-2.712-.927l4.686-2.712c.285-.166.428-.404.428-.737v-6.898l1.974%201.142c.167.095.238.238.238.428v5.233c0%202.545-1.974%204.472-4.614%204.472zm-5.637-5.303l-4.544-2.617c-1.308-.761-2.188-2.378-2.188-3.948A4.482%204.482%200%20014.21%206.327v5.423c0%20.333.143.571.428.738l5.947%203.449-1.95%201.118a.432.432%200%2001-.476%200zm-.262%203.9c-2.688%200-4.662-2.021-4.662-4.519%200-.19.024-.38.047-.57l4.686%202.71c.286.167.571.167.856%200l5.97-3.448v2.26c0%20.19-.07.333-.237.428l-4.543%202.616c-.619.357-1.356.523-2.117.523zm5.899%202.83a5.947%205.947%200%20005.827-4.756C22.287%2018.339%2024%2015.84%2024%2013.296c0-1.665-.713-3.282-1.998-4.448.119-.5.19-.999.19-1.498%200-3.401-2.759-5.947-5.946-5.947-.642%200-1.26.095-1.88.31A5.962%205.962%200%200010.205%200a5.947%205.947%200%2000-5.827%204.757C1.713%205.447%200%207.945%200%2010.49c0%201.666.713%203.283%201.998%204.448-.119.5-.19%201-.19%201.499%200%203.401%202.759%205.946%205.946%205.946.642%200%201.26-.095%201.88-.309a5.96%205.96%200%20004.162%201.713z%22%3E%3C/path%3E%3C/svg%3E","dark":"data:image/svg+xml,%3Csvg%20fill=%22%2310A37F%22%20fill-rule=%22evenodd%22%20height=%221em%22%20style=%22flex:none;line-height:1%22%20viewBox=%220%200%2024%2024%22%20width=%221em%22%20xmlns=%22http://www.w3.org/2000/svg%22%3E%3Ctitle%3EOpenAI%3C/title%3E%3Cpath%20d=%22M9.205%208.658v-2.26c0-.19.072-.333.238-.428l4.543-2.616c.619-.357%201.356-.523%202.117-.523%202.854%200%204.662%202.212%204.662%204.566%200%20.167%200%20.357-.024.547l-4.71-2.759a.797.797%200%2000-.856%200l-5.97%203.473zm10.609%208.8V12.06c0-.333-.143-.57-.429-.737l-5.97-3.473%201.95-1.118a.433.433%200%2001.476%200l4.543%202.617c1.309.76%202.189%202.378%202.189%203.948%200%201.808-1.07%203.473-2.76%204.163zM7.802%2012.703l-1.95-1.142c-.167-.095-.239-.238-.239-.428V5.899c0-2.545%201.95-4.472%204.591-4.472%201%200%201.927.333%202.712.928L8.23%205.067c-.285.166-.428.404-.428.737v6.898zM12%2015.128l-2.795-1.57v-3.33L12%208.658l2.795%201.57v3.33L12%2015.128zm1.796%207.23c-1%200-1.927-.332-2.712-.927l4.686-2.712c.285-.166.428-.404.428-.737v-6.898l1.974%201.142c.167.095.238.238.238.428v5.233c0%202.545-1.974%204.472-4.614%204.472zm-5.637-5.303l-4.544-2.617c-1.308-.761-2.188-2.378-2.188-3.948A4.482%204.482%200%20014.21%206.327v5.423c0%20.333.143.571.428.738l5.947%203.449-1.95%201.118a.432.432%200%2001-.476%200zm-.262%203.9c-2.688%200-4.662-2.021-4.662-4.519%200-.19.024-.38.047-.57l4.686%202.71c.286.167.571.167.856%200l5.97-3.448v2.26c0%20.19-.07.333-.237.428l-4.543%202.616c-.619.357-1.356.523-2.117.523zm5.899%202.83a5.947%205.947%200%20005.827-4.756C22.287%2018.339%2024%2015.84%2024%2013.296c0-1.665-.713-3.282-1.998-4.448.119-.5.19-.999.19-1.498%200-3.401-2.759-5.947-5.946-5.947-.642%200-1.26.095-1.88.31A5.962%205.962%200%200010.205%200a5.947%205.947%200%2000-5.827%204.757C1.713%205.447%200%207.945%200%2010.49c0%201.666.713%203.283%201.998%204.448-.119.5-.19%201-.19%201.499%200%203.401%202.759%205.946%205.946%205.946.642%200%201.26-.095%201.88-.309a5.96%205.96%200%20004.162%201.713z%22%3E%3C/path%3E%3C/svg%3E"},"Codex":{"light":"data:image/svg+xml,%3Csvg%20fill=%22%236E56CF%22%20fill-rule=%22evenodd%22%20height=%221em%22%20style=%22flex:none;line-height:1%22%20viewBox=%220%200%2024%2024%22%20width=%221em%22%20xmlns=%22http://www.w3.org/2000/svg%22%3E%3Ctitle%3ECodex%3C/title%3E%3Cpath%20clip-rule=%22evenodd%22%20d=%22M8.086.457a6.105%206.105%200%20013.046-.415c1.333.153%202.521.72%203.564%201.7a.117.117%200%2000.107.029c1.408-.346%202.762-.224%204.061.366l.063.03.154.076c1.357.703%202.33%201.77%202.918%203.198.278.679.418%201.388.421%202.126a5.655%205.655%200%2001-.18%201.631.167.167%200%2000.04.155%205.982%205.982%200%20011.578%202.891c.385%201.901-.01%203.615-1.183%205.14l-.182.22a6.063%206.063%200%2001-2.934%201.851.162.162%200%2000-.108.102c-.255.736-.511%201.364-.987%201.992-1.199%201.582-2.962%202.462-4.948%202.451-1.583-.008-2.986-.587-4.21-1.736a.145.145%200%2000-.14-.032c-.518.167-1.04.191-1.604.185a5.924%205.924%200%2001-2.595-.622%206.058%206.058%200%2001-2.146-1.781c-.203-.269-.404-.522-.551-.821a7.74%207.74%200%2001-.495-1.283%206.11%206.11%200%2001-.017-3.064.166.166%200%2000.008-.074.115.115%200%2000-.037-.064%205.958%205.958%200%2001-1.38-2.202%205.196%205.196%200%2001-.333-1.589%206.915%206.915%200%2001.188-2.132c.45-1.484%201.309-2.648%202.577-3.493.282-.188.55-.334.802-.438.286-.12.573-.22.861-.304a.129.129%200%2000.087-.087A6.016%206.016%200%20015.635%202.31C6.315%201.464%207.132.846%208.086.457zm-.804%207.85a.848.848%200%2000-1.473.842l1.694%202.965-1.688%202.848a.849.849%200%20001.46.864l1.94-3.272a.849.849%200%2000.007-.854l-1.94-3.393zm5.446%206.24a.849.849%200%20000%201.695h4.848a.849.849%200%20000-1.696h-4.848z%22%3E%3C/path%3E%3C/svg%3E","dark":"data:image/svg+xml,%3Csvg%20fill=%22%236E56CF%22%20fill-rule=%22evenodd%22%20height=%221em%22%20style=%22flex:none;line-height:1%22%20viewBox=%220%200%2024%2024%22%20width=%221em%22%20xmlns=%22http://www.w3.org/2000/svg%22%3E%3Ctitle%3ECodex%3C/title%3E%3Cpath%20clip-rule=%22evenodd%22%20d=%22M8.086.457a6.105%206.105%200%20013.046-.415c1.333.153%202.521.72%203.564%201.7a.117.117%200%2000.107.029c1.408-.346%202.762-.224%204.061.366l.063.03.154.076c1.357.703%202.33%201.77%202.918%203.198.278.679.418%201.388.421%202.126a5.655%205.655%200%2001-.18%201.631.167.167%200%2000.04.155%205.982%205.982%200%20011.578%202.891c.385%201.901-.01%203.615-1.183%205.14l-.182.22a6.063%206.063%200%2001-2.934%201.851.162.162%200%2000-.108.102c-.255.736-.511%201.364-.987%201.992-1.199%201.582-2.962%202.462-4.948%202.451-1.583-.008-2.986-.587-4.21-1.736a.145.145%200%2000-.14-.032c-.518.167-1.04.191-1.604.185a5.924%205.924%200%2001-2.595-.622%206.058%206.058%200%2001-2.146-1.781c-.203-.269-.404-.522-.551-.821a7.74%207.74%200%2001-.495-1.283%206.11%206.11%200%2001-.017-3.064.166.166%200%2000.008-.074.115.115%200%2000-.037-.064%205.958%205.958%200%2001-1.38-2.202%205.196%205.196%200%2001-.333-1.589%206.915%206.915%200%2001.188-2.132c.45-1.484%201.309-2.648%202.577-3.493.282-.188.55-.334.802-.438.286-.12.573-.22.861-.304a.129.129%200%2000.087-.087A6.016%206.016%200%20015.635%202.31C6.315%201.464%207.132.846%208.086.457zm-.804%207.85a.848.848%200%2000-1.473.842l1.694%202.965-1.688%202.848a.849.849%200%20001.46.864l1.94-3.272a.849.849%200%2000.007-.854l-1.94-3.393zm5.446%206.24a.849.849%200%20000%201.695h4.848a.849.849%200%20000-1.696h-4.848z%22%3E%3C/path%3E%3C/svg%3E"},"Anthropic":{"light":"data:image/svg+xml,%3Csvg%20fill=%22%23D97757%22%20fill-rule=%22evenodd%22%20height=%221em%22%20style=%22flex:none;line-height:1%22%20viewBox=%220%200%2024%2024%22%20width=%221em%22%20xmlns=%22http://www.w3.org/2000/svg%22%3E%3Ctitle%3EAnthropic%3C/title%3E%3Cpath%20d=%22M13.827%203.52h3.603L24%2020h-3.603l-6.57-16.48zm-7.258%200h3.767L16.906%2020h-3.674l-1.343-3.461H5.017l-1.344%203.46H0L6.57%203.522zm4.132%209.959L8.453%207.687%206.205%2013.48H10.7z%22%3E%3C/path%3E%3C/svg%3E","dark":"data:image/svg+xml,%3Csvg%20fill=%22%23D97757%22%20fill-rule=%22evenodd%22%20height=%221em%22%20style=%22flex:none;line-height:1%22%20viewBox=%220%200%2024%2024%22%20width=%221em%22%20xmlns=%22http://www.w3.org/2000/svg%22%3E%3Ctitle%3EAnthropic%3C/title%3E%3Cpath%20d=%22M13.827%203.52h3.603L24%2020h-3.603l-6.57-16.48zm-7.258%200h3.767L16.906%2020h-3.674l-1.343-3.461H5.017l-1.344%203.46H0L6.57%203.522zm4.132%209.959L8.453%207.687%206.205%2013.48H10.7z%22%3E%3C/path%3E%3C/svg%3E"},"Claude":{"light":"data:image/svg+xml,%3Csvg%20fill=%22%23D97757%22%20fill-rule=%22evenodd%22%20height=%221em%22%20style=%22flex:none;line-height:1%22%20viewBox=%220%200%2024%2024%22%20width=%221em%22%20xmlns=%22http://www.w3.org/2000/svg%22%3E%3Ctitle%3EClaude%3C/title%3E%3Cpath%20d=%22M4.709%2015.955l4.72-2.647.08-.23-.08-.128H9.2l-.79-.048-2.698-.073-2.339-.097-2.266-.122-.571-.121L0%2011.784l.055-.352.48-.321.686.06%201.52.103%202.278.158%201.652.097%202.449.255h.389l.055-.157-.134-.098-.103-.097-2.358-1.596-2.552-1.688-1.336-.972-.724-.491-.364-.462-.158-1.008.656-.722.881.06.225.061.893.686%201.908%201.476%202.491%201.833.365.304.145-.103.019-.073-.164-.274-1.355-2.446-1.446-2.49-.644-1.032-.17-.619a2.97%202.97%200%2001-.104-.729L6.283.134%206.696%200l.996.134.42.364.62%201.414%201.002%202.229%201.555%203.03.456.898.243.832.091.255h.158V9.01l.128-1.706.237-2.095.23-2.695.08-.76.376-.91.747-.492.584.28.48.685-.067.444-.286%201.851-.559%202.903-.364%201.942h.212l.243-.242.985-1.306%201.652-2.064.73-.82.85-.904.547-.431h1.033l.76%201.129-.34%201.166-1.064%201.347-.881%201.142-1.264%201.7-.79%201.36.073.11.188-.02%202.856-.606%201.543-.28%201.841-.315.833.388.091.395-.328.807-1.969.486-2.309.462-3.439.813-.042.03.049.061%201.549.146.662.036h1.622l3.02.225.79.522.474.638-.079.485-1.215.62-1.64-.389-3.829-.91-1.312-.329h-.182v.11l1.093%201.068%202.006%201.81%202.509%202.33.127.578-.322.455-.34-.049-2.205-1.657-.851-.747-1.926-1.62h-.128v.17l.444.649%202.345%203.521.122%201.08-.17.353-.608.213-.668-.122-1.374-1.925-1.415-2.167-1.143-1.943-.14.08-.674%207.254-.316.37-.729.28-.607-.461-.322-.747.322-1.476.389-1.924.315-1.53.286-1.9.17-.632-.012-.042-.14.018-1.434%201.967-2.18%202.945-1.726%201.845-.414.164-.717-.37.067-.662.401-.589%202.388-3.036%201.44-1.882.93-1.086-.006-.158h-.055L4.132%2018.56l-1.13.146-.487-.456.061-.746.231-.243%201.908-1.312-.006.006z%22%3E%3C/path%3E%3C/svg%3E","dark":"data:image/svg+xml,%3Csvg%20fill=%22%23D97757%22%20fill-rule=%22evenodd%22%20height=%221em%22%20style=%22flex:none;line-height:1%22%20viewBox=%220%200%2024%2024%22%20width=%221em%22%20xmlns=%22http://www.w3.org/2000/svg%22%3E%3Ctitle%3EClaude%3C/title%3E%3Cpath%20d=%22M4.709%2015.955l4.72-2.647.08-.23-.08-.128H9.2l-.79-.048-2.698-.073-2.339-.097-2.266-.122-.571-.121L0%2011.784l.055-.352.48-.321.686.06%201.52.103%202.278.158%201.652.097%202.449.255h.389l.055-.157-.134-.098-.103-.097-2.358-1.596-2.552-1.688-1.336-.972-.724-.491-.364-.462-.158-1.008.656-.722.881.06.225.061.893.686%201.908%201.476%202.491%201.833.365.304.145-.103.019-.073-.164-.274-1.355-2.446-1.446-2.49-.644-1.032-.17-.619a2.97%202.97%200%2001-.104-.729L6.283.134%206.696%200l.996.134.42.364.62%201.414%201.002%202.229%201.555%203.03.456.898.243.832.091.255h.158V9.01l.128-1.706.237-2.095.23-2.695.08-.76.376-.91.747-.492.584.28.48.685-.067.444-.286%201.851-.559%202.903-.364%201.942h.212l.243-.242.985-1.306%201.652-2.064.73-.82.85-.904.547-.431h1.033l.76%201.129-.34%201.166-1.064%201.347-.881%201.142-1.264%201.7-.79%201.36.073.11.188-.02%202.856-.606%201.543-.28%201.841-.315.833.388.091.395-.328.807-1.969.486-2.309.462-3.439.813-.042.03.049.061%201.549.146.662.036h1.622l3.02.225.79.522.474.638-.079.485-1.215.62-1.64-.389-3.829-.91-1.312-.329h-.182v.11l1.093%201.068%202.006%201.81%202.509%202.33.127.578-.322.455-.34-.049-2.205-1.657-.851-.747-1.926-1.62h-.128v.17l.444.649%202.345%203.521.122%201.08-.17.353-.608.213-.668-.122-1.374-1.925-1.415-2.167-1.143-1.943-.14.08-.674%207.254-.316.37-.729.28-.607-.461-.322-.747.322-1.476.389-1.924.315-1.53.286-1.9.17-.632-.012-.042-.14.018-1.434%201.967-2.18%202.945-1.726%201.845-.414.164-.717-.37.067-.662.401-.589%202.388-3.036%201.44-1.882.93-1.086-.006-.158h-.055L4.132%2018.56l-1.13.146-.487-.456.061-.746.231-.243%201.908-1.312-.006.006z%22%3E%3C/path%3E%3C/svg%3E"},"Google Gemini":{"light":"data:image/svg+xml,%3Csvg%20fill=%22%238E75B2%22%20fill-rule=%22evenodd%22%20height=%221em%22%20style=%22flex:none;line-height:1%22%20viewBox=%220%200%2024%2024%22%20width=%221em%22%20xmlns=%22http://www.w3.org/2000/svg%22%3E%3Ctitle%3EGemini%3C/title%3E%3Cpath%20d=%22M20.616%2010.835a14.147%2014.147%200%2001-4.45-3.001%2014.111%2014.111%200%2001-3.678-6.452.503.503%200%2000-.975%200%2014.134%2014.134%200%2001-3.679%206.452%2014.155%2014.155%200%2001-4.45%203.001c-.65.28-1.318.505-2.002.678a.502.502%200%20000%20.975c.684.172%201.35.397%202.002.677a14.147%2014.147%200%20014.45%203.001%2014.112%2014.112%200%20013.679%206.453.502.502%200%2000.975%200c.172-.685.397-1.351.677-2.003a14.145%2014.145%200%20013.001-4.45%2014.113%2014.113%200%20016.453-3.678.503.503%200%20000-.975%2013.245%2013.245%200%2001-2.003-.678z%22%3E%3C/path%3E%3C/svg%3E","dark":"data:image/svg+xml,%3Csvg%20fill=%22%238E75B2%22%20fill-rule=%22evenodd%22%20height=%221em%22%20style=%22flex:none;line-height:1%22%20viewBox=%220%200%2024%2024%22%20width=%221em%22%20xmlns=%22http://www.w3.org/2000/svg%22%3E%3Ctitle%3EGemini%3C/title%3E%3Cpath%20d=%22M20.616%2010.835a14.147%2014.147%200%2001-4.45-3.001%2014.111%2014.111%200%2001-3.678-6.452.503.503%200%2000-.975%200%2014.134%2014.134%200%2001-3.679%206.452%2014.155%2014.155%200%2001-4.45%203.001c-.65.28-1.318.505-2.002.678a.502.502%200%20000%20.975c.684.172%201.35.397%202.002.677a14.147%2014.147%200%20014.45%203.001%2014.112%2014.112%200%20013.679%206.453.502.502%200%2000.975%200c.172-.685.397-1.351.677-2.003a14.145%2014.145%200%20013.001-4.45%2014.113%2014.113%200%20016.453-3.678.503.503%200%20000-.975%2013.245%2013.245%200%2001-2.003-.678z%22%3E%3C/path%3E%3C/svg%3E"},"Gemma":{"light":"data:image/svg+xml,%3Csvg%20fill=%22%234285F4%22%20fill-rule=%22evenodd%22%20height=%221em%22%20style=%22flex:none;line-height:1%22%20viewBox=%220%200%2024%2024%22%20width=%221em%22%20xmlns=%22http://www.w3.org/2000/svg%22%3E%3Ctitle%3EGemma%3C/title%3E%3Cpath%20d=%22M12.34%205.953a8.233%208.233%200%2001-.247-1.125V3.72a8.25%208.25%200%20015.562%202.232H12.34zm-.69%200c.113-.373.199-.755.257-1.145V3.72a8.25%208.25%200%2000-5.562%202.232h5.304zm-5.433.187h5.373a7.98%207.98%200%2001-.267.696%208.41%208.41%200%2001-1.76%202.65L6.216%206.14zm-.264-.187H2.977v.187h2.915a8.436%208.436%200%2000-2.357%205.767H0v.186h3.535a8.436%208.436%200%20002.357%205.767H2.977v.186h2.976v2.977h.187v-2.915a8.436%208.436%200%20005.767%202.357V24h.186v-3.535a8.436%208.436%200%20005.767-2.357v2.915h.186v-2.977h2.977v-.186h-2.915a8.436%208.436%200%20002.357-5.767H24v-.186h-3.535a8.436%208.436%200%2000-2.357-5.767h2.915v-.187h-2.977V2.977h-.186v2.915a8.436%208.436%200%2000-5.767-2.357V0h-.186v3.535A8.436%208.436%200%20006.14%205.892V2.977h-.187v2.976zm6.14%2014.326a8.25%208.25%200%20005.562-2.233H12.34c-.108.367-.19.743-.247%201.126v1.107zm-.186-1.087a8.015%208.015%200%2000-.258-1.146H6.345a8.25%208.25%200%20005.562%202.233v-1.087zm-8.186-7.285h1.107a8.23%208.23%200%20001.125-.247V6.345a8.25%208.25%200%2000-2.232%205.562zm1.087.186H3.72a8.25%208.25%200%20002.232%205.562v-5.304a8.012%208.012%200%2000-1.145-.258zm15.47-.186a8.25%208.25%200%2000-2.232-5.562v5.315c.367.108.743.19%201.126.247h1.107zm-1.086.186c-.39.058-.772.144-1.146.258v5.304a8.25%208.25%200%20002.233-5.562h-1.087zm-1.332%205.69V12.41a7.97%207.97%200%2000-.696.267%208.409%208.409%200%2000-2.65%201.76l3.346%203.346zm0-6.18v-5.45l-.012-.013h-5.451c.076.235.162.468.26.696a8.698%208.698%200%20001.819%202.688%208.698%208.698%200%20002.688%201.82c.228.097.46.183.696.259zM6.14%2017.848V12.41c.235.078.468.167.696.267a8.403%208.403%200%20012.688%201.799%208.404%208.404%200%20011.799%202.688c.1.228.19.46.267.696H6.152l-.012-.012zm0-6.245V6.326l3.29%203.29a8.716%208.716%200%2001-2.594%201.728%208.14%208.14%200%2001-.696.259zm6.257%206.257h5.277l-3.29-3.29a8.716%208.716%200%2000-1.728%202.594%208.135%208.135%200%2000-.259.696zm-2.347-7.81a9.435%209.435%200%2001-2.88%201.96%209.14%209.14%200%20012.88%201.94%209.14%209.14%200%20011.94%202.88%209.435%209.435%200%20011.96-2.88%209.14%209.14%200%20012.88-1.94%209.435%209.435%200%2001-2.88-1.96%209.434%209.434%200%2001-1.96-2.88%209.14%209.14%200%2001-1.94%202.88z%22%3E%3C/path%3E%3C/svg%3E","dark":"data:image/svg+xml,%3Csvg%20fill=%22%234285F4%22%20fill-rule=%22evenodd%22%20height=%221em%22%20style=%22flex:none;line-height:1%22%20viewBox=%220%200%2024%2024%22%20width=%221em%22%20xmlns=%22http://www.w3.org/2000/svg%22%3E%3Ctitle%3EGemma%3C/title%3E%3Cpath%20d=%22M12.34%205.953a8.233%208.233%200%2001-.247-1.125V3.72a8.25%208.25%200%20015.562%202.232H12.34zm-.69%200c.113-.373.199-.755.257-1.145V3.72a8.25%208.25%200%2000-5.562%202.232h5.304zm-5.433.187h5.373a7.98%207.98%200%2001-.267.696%208.41%208.41%200%2001-1.76%202.65L6.216%206.14zm-.264-.187H2.977v.187h2.915a8.436%208.436%200%2000-2.357%205.767H0v.186h3.535a8.436%208.436%200%20002.357%205.767H2.977v.186h2.976v2.977h.187v-2.915a8.436%208.436%200%20005.767%202.357V24h.186v-3.535a8.436%208.436%200%20005.767-2.357v2.915h.186v-2.977h2.977v-.186h-2.915a8.436%208.436%200%20002.357-5.767H24v-.186h-3.535a8.436%208.436%200%2000-2.357-5.767h2.915v-.187h-2.977V2.977h-.186v2.915a8.436%208.436%200%2000-5.767-2.357V0h-.186v3.535A8.436%208.436%200%20006.14%205.892V2.977h-.187v2.976zm6.14%2014.326a8.25%208.25%200%20005.562-2.233H12.34c-.108.367-.19.743-.247%201.126v1.107zm-.186-1.087a8.015%208.015%200%2000-.258-1.146H6.345a8.25%208.25%200%20005.562%202.233v-1.087zm-8.186-7.285h1.107a8.23%208.23%200%20001.125-.247V6.345a8.25%208.25%200%2000-2.232%205.562zm1.087.186H3.72a8.25%208.25%200%20002.232%205.562v-5.304a8.012%208.012%200%2000-1.145-.258zm15.47-.186a8.25%208.25%200%2000-2.232-5.562v5.315c.367.108.743.19%201.126.247h1.107zm-1.086.186c-.39.058-.772.144-1.146.258v5.304a8.25%208.25%200%20002.233-5.562h-1.087zm-1.332%205.69V12.41a7.97%207.97%200%2000-.696.267%208.409%208.409%200%2000-2.65%201.76l3.346%203.346zm0-6.18v-5.45l-.012-.013h-5.451c.076.235.162.468.26.696a8.698%208.698%200%20001.819%202.688%208.698%208.698%200%20002.688%201.82c.228.097.46.183.696.259zM6.14%2017.848V12.41c.235.078.468.167.696.267a8.403%208.403%200%20012.688%201.799%208.404%208.404%200%20011.799%202.688c.1.228.19.46.267.696H6.152l-.012-.012zm0-6.245V6.326l3.29%203.29a8.716%208.716%200%2001-2.594%201.728%208.14%208.14%200%2001-.696.259zm6.257%206.257h5.277l-3.29-3.29a8.716%208.716%200%2000-1.728%202.594%208.135%208.135%200%2000-.259.696zm-2.347-7.81a9.435%209.435%200%2001-2.88%201.96%209.14%209.14%200%20012.88%201.94%209.14%209.14%200%20011.94%202.88%209.435%209.435%200%20011.96-2.88%209.14%209.14%200%20012.88-1.94%209.435%209.435%200%2001-2.88-1.96%209.434%209.434%200%2001-1.96-2.88%209.14%209.14%200%2001-1.94%202.88z%22%3E%3C/path%3E%3C/svg%3E"},"Google":{"light":"data:image/svg+xml,%3Csvg%20fill=%22%234285F4%22%20fill-rule=%22evenodd%22%20height=%221em%22%20style=%22flex:none;line-height:1%22%20viewBox=%220%200%2024%2024%22%20width=%221em%22%20xmlns=%22http://www.w3.org/2000/svg%22%3E%3Ctitle%3EGoogle%3C/title%3E%3Cpath%20d=%22M23%2012.245c0-.905-.075-1.565-.236-2.25h-10.54v4.083h6.186c-.124%201.014-.797%202.542-2.294%203.569l-.021.136%203.332%202.53.23.022C21.779%2018.417%2023%2015.593%2023%2012.245z%22%3E%3C/path%3E%3Cpath%20d=%22M12.225%2023c3.03%200%205.574-.978%207.433-2.665l-3.542-2.688c-.948.648-2.22%201.1-3.891%201.1a6.745%206.745%200%2001-6.386-4.572l-.132.011-3.465%202.628-.045.124C4.043%2020.531%207.835%2023%2012.225%2023z%22%3E%3C/path%3E%3Cpath%20d=%22M5.84%2014.175A6.65%206.65%200%20015.463%2012c0-.758.138-1.491.361-2.175l-.006-.147-3.508-2.67-.115.054A10.831%2010.831%200%20001%2012c0%201.772.436%203.447%201.197%204.938l3.642-2.763z%22%3E%3C/path%3E%3Cpath%20d=%22M12.225%205.253c2.108%200%203.529.892%204.34%201.638l3.167-3.031C17.787%202.088%2015.255%201%2012.225%201%207.834%201%204.043%203.469%202.197%207.062l3.63%202.763a6.77%206.77%200%20016.398-4.572z%22%3E%3C/path%3E%3C/svg%3E","dark":"data:image/svg+xml,%3Csvg%20fill=%22%234285F4%22%20fill-rule=%22evenodd%22%20height=%221em%22%20style=%22flex:none;line-height:1%22%20viewBox=%220%200%2024%2024%22%20width=%221em%22%20xmlns=%22http://www.w3.org/2000/svg%22%3E%3Ctitle%3EGoogle%3C/title%3E%3Cpath%20d=%22M23%2012.245c0-.905-.075-1.565-.236-2.25h-10.54v4.083h6.186c-.124%201.014-.797%202.542-2.294%203.569l-.021.136%203.332%202.53.23.022C21.779%2018.417%2023%2015.593%2023%2012.245z%22%3E%3C/path%3E%3Cpath%20d=%22M12.225%2023c3.03%200%205.574-.978%207.433-2.665l-3.542-2.688c-.948.648-2.22%201.1-3.891%201.1a6.745%206.745%200%2001-6.386-4.572l-.132.011-3.465%202.628-.045.124C4.043%2020.531%207.835%2023%2012.225%2023z%22%3E%3C/path%3E%3Cpath%20d=%22M5.84%2014.175A6.65%206.65%200%20015.463%2012c0-.758.138-1.491.361-2.175l-.006-.147-3.508-2.67-.115.054A10.831%2010.831%200%20001%2012c0%201.772.436%203.447%201.197%204.938l3.642-2.763z%22%3E%3C/path%3E%3Cpath%20d=%22M12.225%205.253c2.108%200%203.529.892%204.34%201.638l3.167-3.031C17.787%202.088%2015.255%201%2012.225%201%207.834%201%204.043%203.469%202.197%207.062l3.63%202.763a6.77%206.77%200%20016.398-4.572z%22%3E%3C/path%3E%3C/svg%3E"},"DeepMind":{"light":"data:image/svg+xml,%3Csvg%20fill=%22%234285F4%22%20fill-rule=%22evenodd%22%20height=%221em%22%20style=%22flex:none;line-height:1%22%20viewBox=%220%200%2024%2024%22%20width=%221em%22%20xmlns=%22http://www.w3.org/2000/svg%22%3E%3Ctitle%3EDeepMind%3C/title%3E%3Cpath%20d=%22M5.988%201.622A8.539%208.539%200%20003.45%208.446c.349%204.408%204.506%207.995%208.276%207.995%203.507%200%204.88-3.061%204.541-5.14a4.318%204.318%200%2000-.95-2.073c.632.34%201.244.776%201.809%201.3%201.52%201.415%202.44%203.229%202.587%205.1C20.04%2019.763%2016.98%2024%2011.863%2024c-1.695%200-3.48-.432-4.98-1.143C2.816%2020.937%200%2016.797%200%2012.002%200%207.571%202.405%203.7%205.988%201.622zM12.136%200c1.696%200%203.481.432%204.98%201.143C21.186%203.063%2024%207.203%2024%2011.998c0%204.431-2.405%208.303-5.988%2010.38a8.539%208.539%200%20002.538-6.824c-.349-4.408-4.506-7.995-8.276-7.995-3.507%200-4.88%203.061-4.541%205.14a4.3%204.3%200%2000.953%202.073%208.723%208.723%200%2001-1.81-1.3c-1.52-1.415-2.44-3.227-2.589-5.1C3.96%204.237%207.02%200%2012.137%200z%22%3E%3C/path%3E%3C/svg%3E","dark":"data:image/svg+xml,%3Csvg%20fill=%22%234285F4%22%20fill-rule=%22evenodd%22%20height=%221em%22%20style=%22flex:none;line-height:1%22%20viewBox=%220%200%2024%2024%22%20width=%221em%22%20xmlns=%22http://www.w3.org/2000/svg%22%3E%3Ctitle%3EDeepMind%3C/title%3E%3Cpath%20d=%22M5.988%201.622A8.539%208.539%200%20003.45%208.446c.349%204.408%204.506%207.995%208.276%207.995%203.507%200%204.88-3.061%204.541-5.14a4.318%204.318%200%2000-.95-2.073c.632.34%201.244.776%201.809%201.3%201.52%201.415%202.44%203.229%202.587%205.1C20.04%2019.763%2016.98%2024%2011.863%2024c-1.695%200-3.48-.432-4.98-1.143C2.816%2020.937%200%2016.797%200%2012.002%200%207.571%202.405%203.7%205.988%201.622zM12.136%200c1.696%200%203.481.432%204.98%201.143C21.186%203.063%2024%207.203%2024%2011.998c0%204.431-2.405%208.303-5.988%2010.38a8.539%208.539%200%20002.538-6.824c-.349-4.408-4.506-7.995-8.276-7.995-3.507%200-4.88%203.061-4.541%205.14a4.3%204.3%200%2000.953%202.073%208.723%208.723%200%2001-1.81-1.3c-1.52-1.415-2.44-3.227-2.589-5.1C3.96%204.237%207.02%200%2012.137%200z%22%3E%3C/path%3E%3C/svg%3E"},"xAI Grok":{"light":"data:image/svg+xml,%3Csvg%20fill=%22%23111827%22%20fill-rule=%22evenodd%22%20height=%221em%22%20style=%22flex:none;line-height:1%22%20viewBox=%220%200%2024%2024%22%20width=%221em%22%20xmlns=%22http://www.w3.org/2000/svg%22%3E%3Ctitle%3EGrok%3C/title%3E%3Cpath%20d=%22M9.27%2015.29l7.978-5.897c.391-.29.95-.177%201.137.272.98%202.369.542%205.215-1.41%207.169-1.951%201.954-4.667%202.382-7.149%201.406l-2.711%201.257c3.889%202.661%208.611%202.003%2011.562-.953%202.341-2.344%203.066-5.539%202.388-8.42l.006.007c-.983-4.232.242-5.924%202.75-9.383.06-.082.12-.164.179-.248l-3.301%203.305v-.01L9.267%2015.292M7.623%2016.723c-2.792-2.67-2.31-6.801.071-9.184%201.761-1.763%204.647-2.483%207.166-1.425l2.705-1.25a7.808%207.808%200%2000-1.829-1A8.975%208.975%200%20005.984%205.83c-2.533%202.536-3.33%206.436-1.962%209.764%201.022%202.487-.653%204.246-2.34%206.022-.599.63-1.199%201.259-1.682%201.925l7.62-6.815%22%3E%3C/path%3E%3C/svg%3E","dark":"data:image/svg+xml,%3Csvg%20fill=%22%23111827%22%20fill-rule=%22evenodd%22%20height=%221em%22%20style=%22flex:none;line-height:1%22%20viewBox=%220%200%2024%2024%22%20width=%221em%22%20xmlns=%22http://www.w3.org/2000/svg%22%3E%3Ctitle%3EGrok%3C/title%3E%3Cpath%20d=%22M9.27%2015.29l7.978-5.897c.391-.29.95-.177%201.137.272.98%202.369.542%205.215-1.41%207.169-1.951%201.954-4.667%202.382-7.149%201.406l-2.711%201.257c3.889%202.661%208.611%202.003%2011.562-.953%202.341-2.344%203.066-5.539%202.388-8.42l.006.007c-.983-4.232.242-5.924%202.75-9.383.06-.082.12-.164.179-.248l-3.301%203.305v-.01L9.267%2015.292M7.623%2016.723c-2.792-2.67-2.31-6.801.071-9.184%201.761-1.763%204.647-2.483%207.166-1.425l2.705-1.25a7.808%207.808%200%2000-1.829-1A8.975%208.975%200%20005.984%205.83c-2.533%202.536-3.33%206.436-1.962%209.764%201.022%202.487-.653%204.246-2.34%206.022-.599.63-1.199%201.259-1.682%201.925l7.62-6.815%22%3E%3C/path%3E%3C/svg%3E"},"xAI":{"light":"data:image/svg+xml,%3Csvg%20fill=%22%23111827%22%20fill-rule=%22evenodd%22%20height=%221em%22%20style=%22flex:none;line-height:1%22%20viewBox=%220%200%2024%2024%22%20width=%221em%22%20xmlns=%22http://www.w3.org/2000/svg%22%3E%3Ctitle%3EGrok%3C/title%3E%3Cpath%20d=%22M6.469%208.776L16.512%2023h-4.464L2.005%208.776H6.47zm-.004%207.9l2.233%203.164L6.467%2023H2l4.465-6.324zM22%202.582V23h-3.659V7.764L22%202.582zM22%201l-9.952%2014.095-2.233-3.163L17.533%201H22z%22%3E%3C/path%3E%3C/svg%3E","dark":"data:image/svg+xml,%3Csvg%20fill=%22%23111827%22%20fill-rule=%22evenodd%22%20height=%221em%22%20style=%22flex:none;line-height:1%22%20viewBox=%220%200%2024%2024%22%20width=%221em%22%20xmlns=%22http://www.w3.org/2000/svg%22%3E%3Ctitle%3EGrok%3C/title%3E%3Cpath%20d=%22M6.469%208.776L16.512%2023h-4.464L2.005%208.776H6.47zm-.004%207.9l2.233%203.164L6.467%2023H2l4.465-6.324zM22%202.582V23h-3.659V7.764L22%202.582zM22%201l-9.952%2014.095-2.233-3.163L17.533%201H22z%22%3E%3C/path%3E%3C/svg%3E"},"DeepSeek":{"light":"data:image/svg+xml,%3Csvg%20fill=%22%234D6BFE%22%20fill-rule=%22evenodd%22%20height=%221em%22%20style=%22flex:none;line-height:1%22%20viewBox=%220%200%2024%2024%22%20width=%221em%22%20xmlns=%22http://www.w3.org/2000/svg%22%3E%3Ctitle%3EDeepSeek%3C/title%3E%3Cpath%20d=%22M23.748%204.482c-.254-.124-.364.113-.512.234-.051.039-.094.09-.137.136-.372.397-.806.657-1.373.626-.829-.046-1.537.214-2.163.848-.133-.782-.575-1.248-1.247-1.548-.352-.156-.708-.311-.955-.65-.172-.241-.219-.51-.305-.774-.055-.16-.11-.323-.293-.35-.2-.031-.278.136-.356.276-.313.572-.434%201.202-.422%201.84.027%201.436.633%202.58%201.838%203.393.137.093.172.187.129.323-.082.28-.18.552-.266.833-.055.179-.137.217-.329.14a5.526%205.526%200%2001-1.736-1.18c-.857-.828-1.631-1.742-2.597-2.458a11.365%2011.365%200%2000-.689-.471c-.985-.957.13-1.743.388-1.836.27-.098.093-.432-.779-.428-.872.004-1.67.295-2.687.684a3.055%203.055%200%2001-.465.137%209.597%209.597%200%2000-2.883-.102c-1.885.21-3.39%201.102-4.497%202.623C.082%208.606-.231%2010.684.152%2012.85c.403%202.284%201.569%204.175%203.36%205.653%201.858%201.533%203.997%202.284%206.438%202.14%201.482-.085%203.133-.284%204.994-1.86.47.234.962.327%201.78.397.63.059%201.236-.03%201.705-.128.735-.156.684-.837.419-.961-2.155-1.004-1.682-.595-2.113-.926%201.096-1.296%202.746-2.642%203.392-7.003.05-.347.007-.565%200-.845-.004-.17.035-.237.23-.256a4.173%204.173%200%20001.545-.475c1.396-.763%201.96-2.015%202.093-3.517.02-.23-.004-.467-.247-.588zM11.581%2018c-2.089-1.642-3.102-2.183-3.52-2.16-.392.024-.321.471-.235.763.09.288.207.486.371.739.114.167.192.416-.113.603-.673.416-1.842-.14-1.897-.167-1.361-.802-2.5-1.86-3.301-3.307-.774-1.393-1.224-2.887-1.298-4.482-.02-.386.093-.522.477-.592a4.696%204.696%200%20011.529-.039c2.132.312%203.946%201.265%205.468%202.774.868.86%201.525%201.887%202.202%202.891.72%201.066%201.494%202.082%202.48%202.914.348.292.625.514.891.677-.802.09-2.14.11-3.054-.614zm1-6.44a.306.306%200%2001.415-.287.302.302%200%2001.2.288.306.306%200%2001-.31.307.303.303%200%2001-.304-.308zm3.11%201.596c-.2.081-.399.151-.59.16a1.245%201.245%200%2001-.798-.254c-.274-.23-.47-.358-.552-.758a1.73%201.73%200%2001.016-.588c.07-.327-.008-.537-.239-.727-.187-.156-.426-.199-.688-.199a.559.559%200%2001-.254-.078c-.11-.054-.2-.19-.114-.358.028-.054.16-.186.192-.21.356-.202.767-.136%201.146.016.352.144.618.408%201.001.782.391.451.462.576.685.914.176.265.336.537.445.848.067.195-.019.354-.25.452z%22%3E%3C/path%3E%3C/svg%3E","dark":"data:image/svg+xml,%3Csvg%20fill=%22%234D6BFE%22%20fill-rule=%22evenodd%22%20height=%221em%22%20style=%22flex:none;line-height:1%22%20viewBox=%220%200%2024%2024%22%20width=%221em%22%20xmlns=%22http://www.w3.org/2000/svg%22%3E%3Ctitle%3EDeepSeek%3C/title%3E%3Cpath%20d=%22M23.748%204.482c-.254-.124-.364.113-.512.234-.051.039-.094.09-.137.136-.372.397-.806.657-1.373.626-.829-.046-1.537.214-2.163.848-.133-.782-.575-1.248-1.247-1.548-.352-.156-.708-.311-.955-.65-.172-.241-.219-.51-.305-.774-.055-.16-.11-.323-.293-.35-.2-.031-.278.136-.356.276-.313.572-.434%201.202-.422%201.84.027%201.436.633%202.58%201.838%203.393.137.093.172.187.129.323-.082.28-.18.552-.266.833-.055.179-.137.217-.329.14a5.526%205.526%200%2001-1.736-1.18c-.857-.828-1.631-1.742-2.597-2.458a11.365%2011.365%200%2000-.689-.471c-.985-.957.13-1.743.388-1.836.27-.098.093-.432-.779-.428-.872.004-1.67.295-2.687.684a3.055%203.055%200%2001-.465.137%209.597%209.597%200%2000-2.883-.102c-1.885.21-3.39%201.102-4.497%202.623C.082%208.606-.231%2010.684.152%2012.85c.403%202.284%201.569%204.175%203.36%205.653%201.858%201.533%203.997%202.284%206.438%202.14%201.482-.085%203.133-.284%204.994-1.86.47.234.962.327%201.78.397.63.059%201.236-.03%201.705-.128.735-.156.684-.837.419-.961-2.155-1.004-1.682-.595-2.113-.926%201.096-1.296%202.746-2.642%203.392-7.003.05-.347.007-.565%200-.845-.004-.17.035-.237.23-.256a4.173%204.173%200%20001.545-.475c1.396-.763%201.96-2.015%202.093-3.517.02-.23-.004-.467-.247-.588zM11.581%2018c-2.089-1.642-3.102-2.183-3.52-2.16-.392.024-.321.471-.235.763.09.288.207.486.371.739.114.167.192.416-.113.603-.673.416-1.842-.14-1.897-.167-1.361-.802-2.5-1.86-3.301-3.307-.774-1.393-1.224-2.887-1.298-4.482-.02-.386.093-.522.477-.592a4.696%204.696%200%20011.529-.039c2.132.312%203.946%201.265%205.468%202.774.868.86%201.525%201.887%202.202%202.891.72%201.066%201.494%202.082%202.48%202.914.348.292.625.514.891.677-.802.09-2.14.11-3.054-.614zm1-6.44a.306.306%200%2001.415-.287.302.302%200%2001.2.288.306.306%200%2001-.31.307.303.303%200%2001-.304-.308zm3.11%201.596c-.2.081-.399.151-.59.16a1.245%201.245%200%2001-.798-.254c-.274-.23-.47-.358-.552-.758a1.73%201.73%200%2001.016-.588c.07-.327-.008-.537-.239-.727-.187-.156-.426-.199-.688-.199a.559.559%200%2001-.254-.078c-.11-.054-.2-.19-.114-.358.028-.054.16-.186.192-.21.356-.202.767-.136%201.146.016.352.144.618.408%201.001.782.391.451.462.576.685.914.176.265.336.537.445.848.067.195-.019.354-.25.452z%22%3E%3C/path%3E%3C/svg%3E"},"Qwen":{"light":"data:image/svg+xml,%3Csvg%20fill=%22%23615CED%22%20fill-rule=%22evenodd%22%20height=%221em%22%20style=%22flex:none;line-height:1%22%20viewBox=%220%200%2024%2024%22%20width=%221em%22%20xmlns=%22http://www.w3.org/2000/svg%22%3E%3Ctitle%3EQwen%3C/title%3E%3Cpath%20d=%22M19.713%202.825h-5.907c0-.251-.066-.503-.196-.728L12.819.728A1.46%201.46%200%200%200%2011.559%200h-1.58c-.52%200-1%20.275-1.26.728l-2.42%204.19a1.45%201.45%200%200%200%200%201.453l.791%201.37c.26.448.74.727%201.26.727h11.36c.52%200%201-.275%201.26-.728l.79-1.37a1.45%201.45%200%200%200%200-1.451l-.79-1.37a1.46%201.46%200%200%200-1.26-.728zM.195%209.905l2.951%205.115a1.46%201.46%200%200%200-.531.531l-.791%201.37a1.45%201.45%200%200%200%200%201.452l.79%201.37c.26.448.74.727%201.26.727h4.84c.52%200%201-.275%201.26-.728l.79-1.37a1.45%201.45%200%200%200%200-1.451L5.086%207.083a1.46%201.46%200%200%200-1.26-.728h-1.58c-.52%200-1%20.276-1.26.728l-.79%201.37a1.45%201.45%200%200%200%200%201.452m15.888%2013.367%202.951-5.115c.217.125.469.196.728.196h1.582c.52%200%201-.275%201.26-.728l.79-1.37a1.45%201.45%200%200%200%200-1.451l-2.42-4.191a1.46%201.46%200%200%200-1.259-.728h-1.582c-.52%200-1%20.276-1.259.728l-5.678%209.838a1.45%201.45%200%200%200%200%201.452l.79%201.37c.26.448.74.727%201.26.727h1.582c.52%200%201-.275%201.26-.728z%22%3E%3C/path%3E%3C/svg%3E","dark":"data:image/svg+xml,%3Csvg%20fill=%22%23615CED%22%20fill-rule=%22evenodd%22%20height=%221em%22%20style=%22flex:none;line-height:1%22%20viewBox=%220%200%2024%2024%22%20width=%221em%22%20xmlns=%22http://www.w3.org/2000/svg%22%3E%3Ctitle%3EQwen%3C/title%3E%3Cpath%20d=%22M19.713%202.825h-5.907c0-.251-.066-.503-.196-.728L12.819.728A1.46%201.46%200%200%200%2011.559%200h-1.58c-.52%200-1%20.275-1.26.728l-2.42%204.19a1.45%201.45%200%200%200%200%201.453l.791%201.37c.26.448.74.727%201.26.727h11.36c.52%200%201-.275%201.26-.728l.79-1.37a1.45%201.45%200%200%200%200-1.451l-.79-1.37a1.46%201.46%200%200%200-1.26-.728zM.195%209.905l2.951%205.115a1.46%201.46%200%200%200-.531.531l-.791%201.37a1.45%201.45%200%200%200%200%201.452l.79%201.37c.26.448.74.727%201.26.727h4.84c.52%200%201-.275%201.26-.728l.79-1.37a1.45%201.45%200%200%200%200-1.451L5.086%207.083a1.46%201.46%200%200%200-1.26-.728h-1.58c-.52%200-1%20.276-1.26.728l-.79%201.37a1.45%201.45%200%200%200%200%201.452m15.888%2013.367%202.951-5.115c.217.125.469.196.728.196h1.582c.52%200%201-.275%201.26-.728l.79-1.37a1.45%201.45%200%200%200%200-1.451l-2.42-4.191a1.46%201.46%200%200%200-1.259-.728h-1.582c-.52%200-1%20.276-1.259.728l-5.678%209.838a1.45%201.45%200%200%200%200%201.452l.79%201.37c.26.448.74.727%201.26.727h1.582c.52%200%201-.275%201.26-.728z%22%3E%3C/path%3E%3C/svg%3E"},"Alibaba":{"light":"data:image/svg+xml,%3Csvg%20fill=%22%23FF6A00%22%20fill-rule=%22evenodd%22%20height=%221em%22%20style=%22flex:none;line-height:1%22%20viewBox=%220%200%2024%2024%22%20width=%221em%22%20xmlns=%22http://www.w3.org/2000/svg%22%3E%3Ctitle%3EAlibaba%3C/title%3E%3Cpath%20d=%22M24%2014.014c-2.8%201.512-5.62%202.896-8.759%203.524-.7.139-1.476.139-2.187.043-.678-.085-1.017-.682-.776-1.31.23-.585.536-1.181.93-1.671.852-1.065%201.814-2.034%202.678-3.088a15.75%2015.75%200%20001.422-2.054c.306-.511.164-1.129-.372-1.384-.897-.437-1.859-.745-2.81-1.075-.11-.043-.274.074-.492.149.273.244.47.425.743.67-2.821.48-5.49%201.16-8.08%202.098-.012.053-.033.095-.023.117.383.585.208%201.032-.35%201.394a2.365%202.365%200%2000-.568.522c1.706.5%203.226.213%204.68-.735-.087-.127-.175-.244-.262-.372.546.096.874.394.918.862.011.107-.054.213-.087.32-.077-.086-.175-.17-.24-.267-.045-.064-.056-.138-.088-.245-1.728%201.15-3.587%201.438-5.632.842%200%20.404-.022.745.011%201.075.022.287-.098.415-.36.564-.591.362-1.204.735-1.696%201.214-.59.585-.371%201.299.427%201.597.907.34%201.859.35%202.81.234%201.126-.139%202.23-.32%203.456-.49-1.433.67-2.844%201.14-4.33%201.33-1.04.14-2.078.214-3.106-.084-1.476-.415-2.133-1.501-1.75-2.96.361-1.363%201.236-2.449%202.176-3.45%203.139-3.332%207.108-5.024%2011.7-5.365%201.072-.074%202.155.064%203.16.511%201.411.639%202.002%201.99%201.313%203.354-.448.905-1.072%201.735-1.695%202.555-.612.809-1.301%201.554-1.946%202.331-.186.234-.361.48-.503.745-.274.5-.088.83.492.778%201.213-.118%202.45-.213%203.62-.511%201.716-.437%203.389-1.054%205.084-1.597.175-.043.339-.107.492-.17z%22%3E%3C/path%3E%3C/svg%3E","dark":"data:image/svg+xml,%3Csvg%20fill=%22%23FF6A00%22%20fill-rule=%22evenodd%22%20height=%221em%22%20style=%22flex:none;line-height:1%22%20viewBox=%220%200%2024%2024%22%20width=%221em%22%20xmlns=%22http://www.w3.org/2000/svg%22%3E%3Ctitle%3EAlibaba%3C/title%3E%3Cpath%20d=%22M24%2014.014c-2.8%201.512-5.62%202.896-8.759%203.524-.7.139-1.476.139-2.187.043-.678-.085-1.017-.682-.776-1.31.23-.585.536-1.181.93-1.671.852-1.065%201.814-2.034%202.678-3.088a15.75%2015.75%200%20001.422-2.054c.306-.511.164-1.129-.372-1.384-.897-.437-1.859-.745-2.81-1.075-.11-.043-.274.074-.492.149.273.244.47.425.743.67-2.821.48-5.49%201.16-8.08%202.098-.012.053-.033.095-.023.117.383.585.208%201.032-.35%201.394a2.365%202.365%200%2000-.568.522c1.706.5%203.226.213%204.68-.735-.087-.127-.175-.244-.262-.372.546.096.874.394.918.862.011.107-.054.213-.087.32-.077-.086-.175-.17-.24-.267-.045-.064-.056-.138-.088-.245-1.728%201.15-3.587%201.438-5.632.842%200%20.404-.022.745.011%201.075.022.287-.098.415-.36.564-.591.362-1.204.735-1.696%201.214-.59.585-.371%201.299.427%201.597.907.34%201.859.35%202.81.234%201.126-.139%202.23-.32%203.456-.49-1.433.67-2.844%201.14-4.33%201.33-1.04.14-2.078.214-3.106-.084-1.476-.415-2.133-1.501-1.75-2.96.361-1.363%201.236-2.449%202.176-3.45%203.139-3.332%207.108-5.024%2011.7-5.365%201.072-.074%202.155.064%203.16.511%201.411.639%202.002%201.99%201.313%203.354-.448.905-1.072%201.735-1.695%202.555-.612.809-1.301%201.554-1.946%202.331-.186.234-.361.48-.503.745-.274.5-.088.83.492.778%201.213-.118%202.45-.213%203.62-.511%201.716-.437%203.389-1.054%205.084-1.597.175-.043.339-.107.492-.17z%22%3E%3C/path%3E%3C/svg%3E"},"Kimi":{"light":"data:image/svg+xml,%3Csvg%20fill=%22%235B6CFF%22%20fill-rule=%22evenodd%22%20height=%221em%22%20style=%22flex:none;line-height:1%22%20viewBox=%220%200%2024%2024%22%20width=%221em%22%20xmlns=%22http://www.w3.org/2000/svg%22%3E%3Ctitle%3EKimi%3C/title%3E%3Cpath%20d=%22M21.846%200a1.923%201.923%200%20110%203.846H20.15a.226.226%200%2001-.227-.226V1.923C19.923.861%2020.784%200%2021.846%200z%22%3E%3C/path%3E%3Cpath%20d=%22M11.065%2011.199l7.257-7.2c.137-.136.06-.41-.116-.41H14.3a.164.164%200%2000-.117.051l-7.82%207.756c-.122.12-.302.013-.302-.179V3.82c0-.127-.083-.23-.185-.23H3.186c-.103%200-.186.103-.186.23V19.77c0%20.128.083.23.186.23h2.69c.103%200%20.186-.102.186-.23v-3.25c0-.069.025-.135.069-.178l2.424-2.406a.158.158%200%2001.205-.023l6.484%204.772a7.677%207.677%200%20003.453%201.283c.108.012.2-.095.2-.23v-3.06c0-.117-.07-.212-.164-.227a5.028%205.028%200%2001-2.027-.807l-5.613-4.064c-.117-.078-.132-.279-.028-.381z%22%3E%3C/path%3E%3C/svg%3E","dark":"data:image/svg+xml,%3Csvg%20fill=%22%235B6CFF%22%20fill-rule=%22evenodd%22%20height=%221em%22%20style=%22flex:none;line-height:1%22%20viewBox=%220%200%2024%2024%22%20width=%221em%22%20xmlns=%22http://www.w3.org/2000/svg%22%3E%3Ctitle%3EKimi%3C/title%3E%3Cpath%20d=%22M21.846%200a1.923%201.923%200%20110%203.846H20.15a.226.226%200%2001-.227-.226V1.923C19.923.861%2020.784%200%2021.846%200z%22%3E%3C/path%3E%3Cpath%20d=%22M11.065%2011.199l7.257-7.2c.137-.136.06-.41-.116-.41H14.3a.164.164%200%2000-.117.051l-7.82%207.756c-.122.12-.302.013-.302-.179V3.82c0-.127-.083-.23-.185-.23H3.186c-.103%200-.186.103-.186.23V19.77c0%20.128.083.23.186.23h2.69c.103%200%20.186-.102.186-.23v-3.25c0-.069.025-.135.069-.178l2.424-2.406a.158.158%200%2001.205-.023l6.484%204.772a7.677%207.677%200%20003.453%201.283c.108.012.2-.095.2-.23v-3.06c0-.117-.07-.212-.164-.227a5.028%205.028%200%2001-2.027-.807l-5.613-4.064c-.117-.078-.132-.279-.028-.381z%22%3E%3C/path%3E%3C/svg%3E"},"Moonshot":{"light":"data:image/svg+xml,%3Csvg%20fill=%22%235B6CFF%22%20fill-rule=%22evenodd%22%20height=%221em%22%20style=%22flex:none;line-height:1%22%20viewBox=%220%200%2024%2024%22%20width=%221em%22%20xmlns=%22http://www.w3.org/2000/svg%22%3E%3Ctitle%3EMoonshotAI%3C/title%3E%3Cpath%20d=%22M1.052%2016.916l9.539%202.552a21.007%2021.007%200%2000.06%202.033l5.956%201.593a11.997%2011.997%200%2001-5.586.865l-.18-.016-.044-.004-.084-.009-.094-.01a11.605%2011.605%200%2001-.157-.02l-.107-.014-.11-.016a11.962%2011.962%200%2001-.32-.051l-.042-.008-.075-.013-.107-.02-.07-.015-.093-.019-.075-.016-.095-.02-.097-.023-.094-.022-.068-.017-.088-.022-.09-.024-.095-.025-.082-.023-.109-.03-.062-.02-.084-.025-.093-.028-.105-.034-.058-.019-.08-.026-.09-.031-.066-.024a6.293%206.293%200%2001-.044-.015l-.068-.025-.101-.037-.057-.022-.08-.03-.087-.035-.088-.035-.079-.032-.095-.04-.063-.028-.063-.027a5.655%205.655%200%2001-.041-.018l-.066-.03-.103-.047-.052-.024-.096-.046-.062-.03-.084-.04-.086-.044-.093-.047-.052-.027-.103-.055-.057-.03-.058-.032a6.49%206.49%200%2001-.046-.026l-.094-.053-.06-.034-.051-.03-.072-.041-.082-.05-.093-.056-.052-.032-.084-.053-.061-.039-.079-.05-.07-.047-.053-.035a7.785%207.785%200%2001-.054-.036l-.044-.03-.044-.03a6.066%206.066%200%2001-.04-.028l-.057-.04-.076-.054-.069-.05-.074-.054-.056-.042-.076-.057-.076-.059-.086-.067-.045-.035-.064-.052-.074-.06-.089-.073-.046-.039-.046-.039a7.516%207.516%200%2001-.043-.037l-.045-.04-.061-.053-.07-.062-.068-.06-.062-.058-.067-.062-.053-.05-.088-.084a13.28%2013.28%200%2001-.099-.097l-.029-.028-.041-.042-.069-.07-.05-.051-.05-.053a6.457%206.457%200%2001-.168-.179l-.08-.088-.062-.07-.071-.08-.042-.049-.053-.062-.058-.068-.046-.056a7.175%207.175%200%2001-.027-.033l-.045-.055-.066-.082-.041-.052-.05-.064-.02-.025a11.99%2011.99%200%2001-1.44-2.402zm-1.02-5.794l11.353%203.037a20.468%2020.468%200%2000-.469%202.011l10.817%202.894a12.076%2012.076%200%2001-1.845%202.005L.657%2015.923l-.016-.046-.035-.104a11.965%2011.965%200%2001-.05-.153l-.007-.023a11.896%2011.896%200%2001-.207-.741l-.03-.126-.018-.08-.021-.097-.018-.081-.018-.09-.017-.084-.018-.094c-.026-.141-.05-.283-.071-.426l-.017-.118-.011-.083-.013-.102a12.01%2012.01%200%2001-.019-.161l-.005-.047a12.12%2012.12%200%2001-.034-2.145zm1.593-5.15l11.948%203.196c-.368.605-.705%201.231-1.01%201.875l11.295%203.022c-.142.82-.368%201.612-.668%202.365l-11.55-3.09L.124%2010.26l.015-.1.008-.049.01-.067.015-.087.018-.098c.026-.148.056-.295.088-.442l.028-.124.02-.085.024-.097c.022-.09.045-.18.07-.268l.028-.102.023-.083.03-.1.025-.082.03-.096.026-.082.031-.095a11.896%2011.896%200%20011.01-2.232zm4.442-4.4L17.352%204.59a20.77%2020.77%200%2000-1.688%201.721l7.823%202.093c.267.852.442%201.744.513%202.665L2.106%205.213l.045-.065.027-.04.04-.055.046-.065.055-.076.054-.072.064-.086.05-.065.057-.073.055-.07.06-.074.055-.069.065-.077.054-.066.066-.077.053-.06.072-.082.053-.06.067-.074.054-.058.073-.078.058-.06.063-.067.168-.17.1-.098.059-.056.076-.071a12.084%2012.084%200%20012.272-1.677zM12.017%200h.097l.082.001.069.001.054.002.068.002.046.001.076.003.047.002.06.003.054.002.087.005.105.007.144.011.088.007.044.004.077.008.082.008.047.005.102.012.05.006.108.014.081.01.042.006.065.01.207.032.07.012.065.011.14.026.092.018.11.022.046.01.075.016.041.01L14.7.3l.042.01.065.015.049.012.071.017.096.024.112.03.113.03.113.032.05.015.07.02.078.024.073.023.05.016.05.016.076.025.099.033.102.036.048.017.064.023.093.034.11.041.116.045.1.04.047.02.06.024.041.018.063.026.04.018.057.025.11.048.1.046.074.035.075.036.06.028.092.046.091.045.102.052.053.028.049.026.046.024.06.033.041.022.052.029.088.05.106.06.087.051.057.034.053.032.096.059.088.055.098.062.036.024.064.041.084.056.04.027.062.042.062.043.023.017c.054.037.108.075.161.114l.083.06.065.048.056.043.086.065.082.064.04.03.05.041.086.069.079.065.085.071c.712.6%201.353%201.283%201.909%202.031L7.222.994l.062-.027.065-.028.081-.034.086-.035c.113-.045.227-.09.341-.131l.096-.035.093-.033.084-.03.096-.031c.087-.03.176-.058.264-.085l.091-.027.086-.025.102-.03.085-.023.1-.026L9.04.37l.09-.023.091-.022.095-.022.09-.02.098-.021.091-.02.095-.018.092-.018.1-.018.091-.016.098-.017.092-.014.097-.015.092-.013.102-.013.091-.012.105-.012.09-.01.105-.01c.093-.01.186-.018.28-.024l.106-.008.09-.005.11-.006.093-.004.1-.004.097-.002.099-.002.197-.002z%22%3E%3C/path%3E%3C/svg%3E","dark":"data:image/svg+xml,%3Csvg%20fill=%22%235B6CFF%22%20fill-rule=%22evenodd%22%20height=%221em%22%20style=%22flex:none;line-height:1%22%20viewBox=%220%200%2024%2024%22%20width=%221em%22%20xmlns=%22http://www.w3.org/2000/svg%22%3E%3Ctitle%3EMoonshotAI%3C/title%3E%3Cpath%20d=%22M1.052%2016.916l9.539%202.552a21.007%2021.007%200%2000.06%202.033l5.956%201.593a11.997%2011.997%200%2001-5.586.865l-.18-.016-.044-.004-.084-.009-.094-.01a11.605%2011.605%200%2001-.157-.02l-.107-.014-.11-.016a11.962%2011.962%200%2001-.32-.051l-.042-.008-.075-.013-.107-.02-.07-.015-.093-.019-.075-.016-.095-.02-.097-.023-.094-.022-.068-.017-.088-.022-.09-.024-.095-.025-.082-.023-.109-.03-.062-.02-.084-.025-.093-.028-.105-.034-.058-.019-.08-.026-.09-.031-.066-.024a6.293%206.293%200%2001-.044-.015l-.068-.025-.101-.037-.057-.022-.08-.03-.087-.035-.088-.035-.079-.032-.095-.04-.063-.028-.063-.027a5.655%205.655%200%2001-.041-.018l-.066-.03-.103-.047-.052-.024-.096-.046-.062-.03-.084-.04-.086-.044-.093-.047-.052-.027-.103-.055-.057-.03-.058-.032a6.49%206.49%200%2001-.046-.026l-.094-.053-.06-.034-.051-.03-.072-.041-.082-.05-.093-.056-.052-.032-.084-.053-.061-.039-.079-.05-.07-.047-.053-.035a7.785%207.785%200%2001-.054-.036l-.044-.03-.044-.03a6.066%206.066%200%2001-.04-.028l-.057-.04-.076-.054-.069-.05-.074-.054-.056-.042-.076-.057-.076-.059-.086-.067-.045-.035-.064-.052-.074-.06-.089-.073-.046-.039-.046-.039a7.516%207.516%200%2001-.043-.037l-.045-.04-.061-.053-.07-.062-.068-.06-.062-.058-.067-.062-.053-.05-.088-.084a13.28%2013.28%200%2001-.099-.097l-.029-.028-.041-.042-.069-.07-.05-.051-.05-.053a6.457%206.457%200%2001-.168-.179l-.08-.088-.062-.07-.071-.08-.042-.049-.053-.062-.058-.068-.046-.056a7.175%207.175%200%2001-.027-.033l-.045-.055-.066-.082-.041-.052-.05-.064-.02-.025a11.99%2011.99%200%2001-1.44-2.402zm-1.02-5.794l11.353%203.037a20.468%2020.468%200%2000-.469%202.011l10.817%202.894a12.076%2012.076%200%2001-1.845%202.005L.657%2015.923l-.016-.046-.035-.104a11.965%2011.965%200%2001-.05-.153l-.007-.023a11.896%2011.896%200%2001-.207-.741l-.03-.126-.018-.08-.021-.097-.018-.081-.018-.09-.017-.084-.018-.094c-.026-.141-.05-.283-.071-.426l-.017-.118-.011-.083-.013-.102a12.01%2012.01%200%2001-.019-.161l-.005-.047a12.12%2012.12%200%2001-.034-2.145zm1.593-5.15l11.948%203.196c-.368.605-.705%201.231-1.01%201.875l11.295%203.022c-.142.82-.368%201.612-.668%202.365l-11.55-3.09L.124%2010.26l.015-.1.008-.049.01-.067.015-.087.018-.098c.026-.148.056-.295.088-.442l.028-.124.02-.085.024-.097c.022-.09.045-.18.07-.268l.028-.102.023-.083.03-.1.025-.082.03-.096.026-.082.031-.095a11.896%2011.896%200%20011.01-2.232zm4.442-4.4L17.352%204.59a20.77%2020.77%200%2000-1.688%201.721l7.823%202.093c.267.852.442%201.744.513%202.665L2.106%205.213l.045-.065.027-.04.04-.055.046-.065.055-.076.054-.072.064-.086.05-.065.057-.073.055-.07.06-.074.055-.069.065-.077.054-.066.066-.077.053-.06.072-.082.053-.06.067-.074.054-.058.073-.078.058-.06.063-.067.168-.17.1-.098.059-.056.076-.071a12.084%2012.084%200%20012.272-1.677zM12.017%200h.097l.082.001.069.001.054.002.068.002.046.001.076.003.047.002.06.003.054.002.087.005.105.007.144.011.088.007.044.004.077.008.082.008.047.005.102.012.05.006.108.014.081.01.042.006.065.01.207.032.07.012.065.011.14.026.092.018.11.022.046.01.075.016.041.01L14.7.3l.042.01.065.015.049.012.071.017.096.024.112.03.113.03.113.032.05.015.07.02.078.024.073.023.05.016.05.016.076.025.099.033.102.036.048.017.064.023.093.034.11.041.116.045.1.04.047.02.06.024.041.018.063.026.04.018.057.025.11.048.1.046.074.035.075.036.06.028.092.046.091.045.102.052.053.028.049.026.046.024.06.033.041.022.052.029.088.05.106.06.087.051.057.034.053.032.096.059.088.055.098.062.036.024.064.041.084.056.04.027.062.042.062.043.023.017c.054.037.108.075.161.114l.083.06.065.048.056.043.086.065.082.064.04.03.05.041.086.069.079.065.085.071c.712.6%201.353%201.283%201.909%202.031L7.222.994l.062-.027.065-.028.081-.034.086-.035c.113-.045.227-.09.341-.131l.096-.035.093-.033.084-.03.096-.031c.087-.03.176-.058.264-.085l.091-.027.086-.025.102-.03.085-.023.1-.026L9.04.37l.09-.023.091-.022.095-.022.09-.02.098-.021.091-.02.095-.018.092-.018.1-.018.091-.016.098-.017.092-.014.097-.015.092-.013.102-.013.091-.012.105-.012.09-.01.105-.01c.093-.01.186-.018.28-.024l.106-.008.09-.005.11-.006.093-.004.1-.004.097-.002.099-.002.197-.002z%22%3E%3C/path%3E%3C/svg%3E"},"Zhipu":{"light":"data:image/svg+xml,%3Csvg%20fill=%22%233B82F6%22%20fill-rule=%22evenodd%22%20height=%221em%22%20style=%22flex:none;line-height:1%22%20viewBox=%220%200%2024%2024%22%20width=%221em%22%20xmlns=%22http://www.w3.org/2000/svg%22%3E%3Ctitle%3EZhipu%3C/title%3E%3Cpath%20d=%22M11.991%2023.503a.24.24%200%2000-.244.248.24.24%200%2000.244.249.24.24%200%2000.245-.249.24.24%200%2000-.22-.247l-.025-.001zM9.671%205.365a1.697%201.697%200%20011.099%202.132l-.071.172-.016.04-.018.054c-.07.16-.104.32-.104.498-.035.71.47%201.279%201.186%201.314h.366c1.309.053%202.338%201.173%202.286%202.523-.052%201.332-1.152%202.38-2.478%202.327h-.174c-.715.018-1.274.64-1.239%201.368%200%20.124.018.23.053.337.209.373.54.658.96.8.75.23%201.517-.125%201.9-.782l.018-.035c.402-.64%201.17-.96%201.92-.711.854.284%201.378%201.226%201.099%202.167a1.661%201.661%200%2001-2.077%201.102%201.711%201.711%200%2001-.907-.711l-.017-.035c-.2-.323-.463-.58-.851-.711l-.056-.018a1.646%201.646%200%2000-1.954.746%201.66%201.66%200%2001-1.065.764%201.677%201.677%200%2001-1.989-1.279c-.209-.906.332-1.83%201.257-2.043a1.51%201.51%200%2001.296-.035h.018c.68-.071%201.151-.622%201.116-1.333a1.307%201.307%200%2000-.227-.693%202.515%202.515%200%2001-.366-1.403%202.39%202.39%200%2001.366-1.208c.14-.195.21-.444.227-.693.018-.71-.506-1.261-1.186-1.332l-.07-.018a1.43%201.43%200%2001-.299-.07l-.05-.019a1.7%201.7%200%2001-1.047-2.114%201.68%201.68%200%20012.094-1.101zm-5.575%2010.11c.26-.264.639-.367.994-.27.355.096.633.379.728.74.095.362-.007.748-.267%201.013-.402.41-1.053.41-1.455%200a1.062%201.062%200%20010-1.482zm14.845-.294c.359-.09.738.024.992.297.254.274.344.665.237%201.025-.107.36-.396.634-.756.718-.551.128-1.1-.22-1.23-.781a1.05%201.05%200%2001.757-1.26zm-.064-4.39c.314.32.49.753.49%201.206%200%20.452-.176.886-.49%201.206-.315.32-.74.5-1.185.5-.444%200-.87-.18-1.184-.5a1.727%201.727%200%20010-2.412%201.654%201.654%200%20012.369%200zm-11.243.163c.364.484.447%201.128.218%201.691a1.665%201.665%200%2001-2.188.923c-.855-.36-1.26-1.358-.907-2.228a1.68%201.68%200%20011.33-1.038c.593-.08%201.183.169%201.547.652zm11.545-4.221c.368%200%20.708.2.892.524.184.324.184.724%200%201.048a1.026%201.026%200%2001-.892.524c-.568%200-1.03-.47-1.03-1.048%200-.579.462-1.048%201.03-1.048zm-14.358%200c.368%200%20.707.2.891.524.184.324.184.724%200%201.048a1.026%201.026%200%2001-.891.524c-.569%200-1.03-.47-1.03-1.048%200-.579.461-1.048%201.03-1.048zm10.031-1.475c.925%200%201.675.764%201.675%201.706s-.75%201.705-1.675%201.705-1.674-.763-1.674-1.705c0-.942.75-1.706%201.674-1.706zm-2.626-.684c.362-.082.653-.356.761-.718a1.062%201.062%200%2000-.238-1.028%201.017%201.017%200%2000-.996-.294c-.547.14-.881.7-.752%201.257.13.558.675.907%201.225.783zm0%2016.876c.359-.087.644-.36.75-.72a1.062%201.062%200%2000-.237-1.019%201.018%201.018%200%2000-.985-.301%201.037%201.037%200%2000-.762.717c-.108.361-.017.754.239%201.028.245.263.606.377.953.305l.043-.01zM17.19%203.5a.631.631%200%2000.628-.64c0-.355-.279-.64-.628-.64a.631.631%200%2000-.628.64c0%20.355.28.64.628.64zm-10.38%200a.631.631%200%2000.628-.64c0-.355-.28-.64-.628-.64a.631.631%200%2000-.628.64c0%20.355.279.64.628.64zm-5.182%207.852a.631.631%200%2000-.628.64c0%20.354.28.639.628.639a.63.63%200%2000.627-.606l.001-.034a.62.62%200%2000-.628-.64zm5.182%209.13a.631.631%200%2000-.628.64c0%20.355.279.64.628.64a.631.631%200%2000.628-.64c0-.355-.28-.64-.628-.64zm10.38.018a.631.631%200%2000-.628.64c0%20.355.28.64.628.64a.631.631%200%2000.628-.64c0-.355-.279-.64-.628-.64zm5.182-9.148a.631.631%200%2000-.628.64c0%20.354.279.639.628.639a.631.631%200%2000.628-.64c0-.355-.28-.64-.628-.64zm-.384-4.992a.24.24%200%2000.244-.249.24.24%200%2000-.244-.249.24.24%200%2000-.244.249c0%20.142.122.249.244.249zM11.991.497a.24.24%200%2000.245-.248A.24.24%200%200011.99%200a.24.24%200%2000-.244.249c0%20.133.108.236.223.247l.021.001zM2.011%206.36a.24.24%200%2000.245-.249.24.24%200%2000-.244-.249.24.24%200%2000-.244.249.24.24%200%2000.244.249zm0%2011.263a.24.24%200%2000-.243.248.24.24%200%2000.244.249.24.24%200%2000.244-.249.252.252%200%2000-.244-.248zm19.995-.018a.24.24%200%2000-.245.248.24.24%200%2000.245.25.24.24%200%2000.244-.25.252.252%200%2000-.244-.248z%22%3E%3C/path%3E%3C/svg%3E","dark":"data:image/svg+xml,%3Csvg%20fill=%22%233B82F6%22%20fill-rule=%22evenodd%22%20height=%221em%22%20style=%22flex:none;line-height:1%22%20viewBox=%220%200%2024%2024%22%20width=%221em%22%20xmlns=%22http://www.w3.org/2000/svg%22%3E%3Ctitle%3EZhipu%3C/title%3E%3Cpath%20d=%22M11.991%2023.503a.24.24%200%2000-.244.248.24.24%200%2000.244.249.24.24%200%2000.245-.249.24.24%200%2000-.22-.247l-.025-.001zM9.671%205.365a1.697%201.697%200%20011.099%202.132l-.071.172-.016.04-.018.054c-.07.16-.104.32-.104.498-.035.71.47%201.279%201.186%201.314h.366c1.309.053%202.338%201.173%202.286%202.523-.052%201.332-1.152%202.38-2.478%202.327h-.174c-.715.018-1.274.64-1.239%201.368%200%20.124.018.23.053.337.209.373.54.658.96.8.75.23%201.517-.125%201.9-.782l.018-.035c.402-.64%201.17-.96%201.92-.711.854.284%201.378%201.226%201.099%202.167a1.661%201.661%200%2001-2.077%201.102%201.711%201.711%200%2001-.907-.711l-.017-.035c-.2-.323-.463-.58-.851-.711l-.056-.018a1.646%201.646%200%2000-1.954.746%201.66%201.66%200%2001-1.065.764%201.677%201.677%200%2001-1.989-1.279c-.209-.906.332-1.83%201.257-2.043a1.51%201.51%200%2001.296-.035h.018c.68-.071%201.151-.622%201.116-1.333a1.307%201.307%200%2000-.227-.693%202.515%202.515%200%2001-.366-1.403%202.39%202.39%200%2001.366-1.208c.14-.195.21-.444.227-.693.018-.71-.506-1.261-1.186-1.332l-.07-.018a1.43%201.43%200%2001-.299-.07l-.05-.019a1.7%201.7%200%2001-1.047-2.114%201.68%201.68%200%20012.094-1.101zm-5.575%2010.11c.26-.264.639-.367.994-.27.355.096.633.379.728.74.095.362-.007.748-.267%201.013-.402.41-1.053.41-1.455%200a1.062%201.062%200%20010-1.482zm14.845-.294c.359-.09.738.024.992.297.254.274.344.665.237%201.025-.107.36-.396.634-.756.718-.551.128-1.1-.22-1.23-.781a1.05%201.05%200%2001.757-1.26zm-.064-4.39c.314.32.49.753.49%201.206%200%20.452-.176.886-.49%201.206-.315.32-.74.5-1.185.5-.444%200-.87-.18-1.184-.5a1.727%201.727%200%20010-2.412%201.654%201.654%200%20012.369%200zm-11.243.163c.364.484.447%201.128.218%201.691a1.665%201.665%200%2001-2.188.923c-.855-.36-1.26-1.358-.907-2.228a1.68%201.68%200%20011.33-1.038c.593-.08%201.183.169%201.547.652zm11.545-4.221c.368%200%20.708.2.892.524.184.324.184.724%200%201.048a1.026%201.026%200%2001-.892.524c-.568%200-1.03-.47-1.03-1.048%200-.579.462-1.048%201.03-1.048zm-14.358%200c.368%200%20.707.2.891.524.184.324.184.724%200%201.048a1.026%201.026%200%2001-.891.524c-.569%200-1.03-.47-1.03-1.048%200-.579.461-1.048%201.03-1.048zm10.031-1.475c.925%200%201.675.764%201.675%201.706s-.75%201.705-1.675%201.705-1.674-.763-1.674-1.705c0-.942.75-1.706%201.674-1.706zm-2.626-.684c.362-.082.653-.356.761-.718a1.062%201.062%200%2000-.238-1.028%201.017%201.017%200%2000-.996-.294c-.547.14-.881.7-.752%201.257.13.558.675.907%201.225.783zm0%2016.876c.359-.087.644-.36.75-.72a1.062%201.062%200%2000-.237-1.019%201.018%201.018%200%2000-.985-.301%201.037%201.037%200%2000-.762.717c-.108.361-.017.754.239%201.028.245.263.606.377.953.305l.043-.01zM17.19%203.5a.631.631%200%2000.628-.64c0-.355-.279-.64-.628-.64a.631.631%200%2000-.628.64c0%20.355.28.64.628.64zm-10.38%200a.631.631%200%2000.628-.64c0-.355-.28-.64-.628-.64a.631.631%200%2000-.628.64c0%20.355.279.64.628.64zm-5.182%207.852a.631.631%200%2000-.628.64c0%20.354.28.639.628.639a.63.63%200%2000.627-.606l.001-.034a.62.62%200%2000-.628-.64zm5.182%209.13a.631.631%200%2000-.628.64c0%20.355.279.64.628.64a.631.631%200%2000.628-.64c0-.355-.28-.64-.628-.64zm10.38.018a.631.631%200%2000-.628.64c0%20.355.28.64.628.64a.631.631%200%2000.628-.64c0-.355-.279-.64-.628-.64zm5.182-9.148a.631.631%200%2000-.628.64c0%20.354.279.639.628.639a.631.631%200%2000.628-.64c0-.355-.28-.64-.628-.64zm-.384-4.992a.24.24%200%2000.244-.249.24.24%200%2000-.244-.249.24.24%200%2000-.244.249c0%20.142.122.249.244.249zM11.991.497a.24.24%200%2000.245-.248A.24.24%200%200011.99%200a.24.24%200%2000-.244.249c0%20.133.108.236.223.247l.021.001zM2.011%206.36a.24.24%200%2000.245-.249.24.24%200%2000-.244-.249.24.24%200%2000-.244.249.24.24%200%2000.244.249zm0%2011.263a.24.24%200%2000-.243.248.24.24%200%2000.244.249.24.24%200%2000.244-.249.252.252%200%2000-.244-.248zm19.995-.018a.24.24%200%2000-.245.248.24.24%200%2000.245.25.24.24%200%2000.244-.25.252.252%200%2000-.244-.248z%22%3E%3C/path%3E%3C/svg%3E"},"ChatGLM":{"light":"data:image/svg+xml,%3Csvg%20fill=%22%233B82F6%22%20fill-rule=%22evenodd%22%20height=%221em%22%20style=%22flex:none;line-height:1%22%20viewBox=%220%200%2024%2024%22%20width=%221em%22%20xmlns=%22http://www.w3.org/2000/svg%22%3E%3Ctitle%3EChatGLM%3C/title%3E%3Cpath%20d=%22M9.917%202c4.906%200%2010.178%203.947%208.93%2010.58-.014.07-.037.14-.057.21l-.003-.277c-.083-3-1.534-8.934-8.87-8.934-3.393%200-8.137%203.054-7.93%208.158-.04%204.778%203.555%208.4%207.95%208.332l.073-.001c1.2-.033%202.763-.429%203.1-1.657.063-.031.26.534.268.598.048.256.112.369.192.34.981-.348%202.286-1.222%201.952-2.38-.176-.61-1.775-.147-1.921-.347.418-.979%202.234-.926%203.153-.716.443.102.657.38%201.012.442.29.052.981-.2.96.242C17.226%2019.632%2013.833%2022%209.918%2022%203.654%2022%200%2016.574%200%2011.737%200%205.947%204.959%202%209.917%202zM9.9%205.3c.484%200%201.125.225%201.38.585%203.669.145%204.313%202.686%204.694%205.444.255%201.838.315%202.3.182%201.387l.083.59c.068.448.554.737.982.516.144-.075.254-.231.328-.47a.2.2%200%2001.258-.13l.625.22a.2.2%200%2001.124.238%202.172%202.172%200%2001-.51.92c-.878.917-2.757.664-3.08-.62-.14-.554-.055-.626-.345-1.242-.292-.621-1.238-.709-1.69-.295-.345.315-.407.805-.406%201.282L12.6%2015.9a.9.9%200%2001-.9.9h-1.4a.9.9%200%2001-.9-.9v-.65a1.15%201.15%200%2010-2.3%200v.65a.9.9%200%2001-.9.9H4.8a.9.9%200%2001-.9-.9l.035-3.239c.012-1.884.356-3.658%202.47-4.134.2-.045.252.13.29.342.025.154.043.252.053.294.701%203.058%201.75%204.299%203.144%203.722l.66-.331.254-.13c.158-.082.25-.131.276-.15.012-.01-.165-.206-.407-.464l-1.012-1.067a8.925%208.925%200%2001-.199-.216c-.047-.034-.116.068-.208.306-.074.157-.251.252-.272.326-.013.058.108.298.362.72.164.288.22.508-.31.343-1.04-.8-1.518-2.273-1.684-3.725-.004-.035-.162-1.913-.162-1.913a1.2%201.2%200%20011.113-1.281L9.9%205.3zm12.994%208.68c.037.697-.403.704-1.213.591l-1.783-.276c-.265-.053-.385-.099-.313-.147.47-.315%203.268-.93%203.31-.168zm-.915-.083l-.926.042c-.85.077-1.452.24.338.336l.103.003c.815.012%201.264-.359.485-.381zm1.667-3.601h.01c.79.398.067%201.03-.65%201.393-.14.07-.491.176-1.052.315-.241.04-.457.092-.333.16l.01.005c1.952.958-3.123%201.534-2.495%201.285l.38-.148c.68-.266%201.614-.682%201.666-1.337.038-.48%201.253-.442%201.493-.968.048-.106%200-.236-.144-.389-.05-.047-.094-.094-.107-.148-.073-.305.7-.431%201.222-.168zm-2.568-.474c-.135%201.198-2.479%204.192-1.949%202.863l.017-.042c.298-.717.376-2.221%201.337-3.221.25-.26.636.035.595.4zm-7.976-.253c.02-.694%201.002-.968%201.346-.347.01-1.274-1.941-.768-1.346.347z%22%3E%3C/path%3E%3C/svg%3E","dark":"data:image/svg+xml,%3Csvg%20fill=%22%233B82F6%22%20fill-rule=%22evenodd%22%20height=%221em%22%20style=%22flex:none;line-height:1%22%20viewBox=%220%200%2024%2024%22%20width=%221em%22%20xmlns=%22http://www.w3.org/2000/svg%22%3E%3Ctitle%3EChatGLM%3C/title%3E%3Cpath%20d=%22M9.917%202c4.906%200%2010.178%203.947%208.93%2010.58-.014.07-.037.14-.057.21l-.003-.277c-.083-3-1.534-8.934-8.87-8.934-3.393%200-8.137%203.054-7.93%208.158-.04%204.778%203.555%208.4%207.95%208.332l.073-.001c1.2-.033%202.763-.429%203.1-1.657.063-.031.26.534.268.598.048.256.112.369.192.34.981-.348%202.286-1.222%201.952-2.38-.176-.61-1.775-.147-1.921-.347.418-.979%202.234-.926%203.153-.716.443.102.657.38%201.012.442.29.052.981-.2.96.242C17.226%2019.632%2013.833%2022%209.918%2022%203.654%2022%200%2016.574%200%2011.737%200%205.947%204.959%202%209.917%202zM9.9%205.3c.484%200%201.125.225%201.38.585%203.669.145%204.313%202.686%204.694%205.444.255%201.838.315%202.3.182%201.387l.083.59c.068.448.554.737.982.516.144-.075.254-.231.328-.47a.2.2%200%2001.258-.13l.625.22a.2.2%200%2001.124.238%202.172%202.172%200%2001-.51.92c-.878.917-2.757.664-3.08-.62-.14-.554-.055-.626-.345-1.242-.292-.621-1.238-.709-1.69-.295-.345.315-.407.805-.406%201.282L12.6%2015.9a.9.9%200%2001-.9.9h-1.4a.9.9%200%2001-.9-.9v-.65a1.15%201.15%200%2010-2.3%200v.65a.9.9%200%2001-.9.9H4.8a.9.9%200%2001-.9-.9l.035-3.239c.012-1.884.356-3.658%202.47-4.134.2-.045.252.13.29.342.025.154.043.252.053.294.701%203.058%201.75%204.299%203.144%203.722l.66-.331.254-.13c.158-.082.25-.131.276-.15.012-.01-.165-.206-.407-.464l-1.012-1.067a8.925%208.925%200%2001-.199-.216c-.047-.034-.116.068-.208.306-.074.157-.251.252-.272.326-.013.058.108.298.362.72.164.288.22.508-.31.343-1.04-.8-1.518-2.273-1.684-3.725-.004-.035-.162-1.913-.162-1.913a1.2%201.2%200%20011.113-1.281L9.9%205.3zm12.994%208.68c.037.697-.403.704-1.213.591l-1.783-.276c-.265-.053-.385-.099-.313-.147.47-.315%203.268-.93%203.31-.168zm-.915-.083l-.926.042c-.85.077-1.452.24.338.336l.103.003c.815.012%201.264-.359.485-.381zm1.667-3.601h.01c.79.398.067%201.03-.65%201.393-.14.07-.491.176-1.052.315-.241.04-.457.092-.333.16l.01.005c1.952.958-3.123%201.534-2.495%201.285l.38-.148c.68-.266%201.614-.682%201.666-1.337.038-.48%201.253-.442%201.493-.968.048-.106%200-.236-.144-.389-.05-.047-.094-.094-.107-.148-.073-.305.7-.431%201.222-.168zm-2.568-.474c-.135%201.198-2.479%204.192-1.949%202.863l.017-.042c.298-.717.376-2.221%201.337-3.221.25-.26.636.035.595.4zm-7.976-.253c.02-.694%201.002-.968%201.346-.347.01-1.274-1.941-.768-1.346.347z%22%3E%3C/path%3E%3C/svg%3E"},"Doubao":{"light":"data:image/svg+xml,%3Csvg%20fill=%22%234D6BFE%22%20fill-rule=%22evenodd%22%20height=%221em%22%20style=%22flex:none;line-height:1%22%20viewBox=%220%200%2024%2024%22%20width=%221em%22%20xmlns=%22http://www.w3.org/2000/svg%22%3E%3Ctitle%3EDoubao%3C/title%3E%3Cpath%20d=%22M5.31%2015.756c.172-3.75%201.883-5.999%202.549-6.739-3.26%202.058-5.425%205.658-6.358%208.308v1.12C1.501%2021.513%204.226%2024%207.59%2024a6.59%206.59%200%20002.2-.375c.353-.12.7-.248%201.039-.378.913-.899%201.65-1.91%202.243-2.992-4.877%202.431-7.974.072-7.763-4.5l.002.001z%22%20fill-opacity=%22.5%22%3E%3C/path%3E%3Cpath%20d=%22M22.57%2010.283c-1.212-.901-4.109-2.404-7.397-2.8.295%203.792.093%208.766-2.1%2012.773a12.782%2012.782%200%2001-2.244%202.992c3.764-1.448%206.746-3.457%208.596-5.219%202.82-2.683%203.353-5.178%203.361-6.66a2.737%202.737%200%2000-.216-1.084v-.002zM14.303%201.867C12.955.7%2011.248%200%209.39%200%207.532%200%205.883.677%204.545%201.807%202.791%203.29%201.627%205.557%201.5%208.125v9.201c.932-2.65%203.097-6.25%206.357-8.307.5-.318%201.025-.595%201.569-.829%201.883-.801%203.878-.932%205.746-.706-.222-2.83-.718-5.002-.87-5.617h.001z%22%3E%3C/path%3E%3Cpath%20d=%22M17.305%204.961a199.47%20199.47%200%2001-1.08-1.094c-.202-.213-.398-.419-.586-.622l-1.333-1.378c.151.615.648%202.786.869%205.617%203.288.395%206.185%201.898%207.396%202.8-1.306-1.275-3.475-3.487-5.266-5.323z%22%20fill-opacity=%22.5%22%3E%3C/path%3E%3C/svg%3E","dark":"data:image/svg+xml,%3Csvg%20fill=%22%234D6BFE%22%20fill-rule=%22evenodd%22%20height=%221em%22%20style=%22flex:none;line-height:1%22%20viewBox=%220%200%2024%2024%22%20width=%221em%22%20xmlns=%22http://www.w3.org/2000/svg%22%3E%3Ctitle%3EDoubao%3C/title%3E%3Cpath%20d=%22M5.31%2015.756c.172-3.75%201.883-5.999%202.549-6.739-3.26%202.058-5.425%205.658-6.358%208.308v1.12C1.501%2021.513%204.226%2024%207.59%2024a6.59%206.59%200%20002.2-.375c.353-.12.7-.248%201.039-.378.913-.899%201.65-1.91%202.243-2.992-4.877%202.431-7.974.072-7.763-4.5l.002.001z%22%20fill-opacity=%22.5%22%3E%3C/path%3E%3Cpath%20d=%22M22.57%2010.283c-1.212-.901-4.109-2.404-7.397-2.8.295%203.792.093%208.766-2.1%2012.773a12.782%2012.782%200%2001-2.244%202.992c3.764-1.448%206.746-3.457%208.596-5.219%202.82-2.683%203.353-5.178%203.361-6.66a2.737%202.737%200%2000-.216-1.084v-.002zM14.303%201.867C12.955.7%2011.248%200%209.39%200%207.532%200%205.883.677%204.545%201.807%202.791%203.29%201.627%205.557%201.5%208.125v9.201c.932-2.65%203.097-6.25%206.357-8.307.5-.318%201.025-.595%201.569-.829%201.883-.801%203.878-.932%205.746-.706-.222-2.83-.718-5.002-.87-5.617h.001z%22%3E%3C/path%3E%3Cpath%20d=%22M17.305%204.961a199.47%20199.47%200%2001-1.08-1.094c-.202-.213-.398-.419-.586-.622l-1.333-1.378c.151.615.648%202.786.869%205.617%203.288.395%206.185%201.898%207.396%202.8-1.306-1.275-3.475-3.487-5.266-5.323z%22%20fill-opacity=%22.5%22%3E%3C/path%3E%3C/svg%3E"},"Volcano Engine":{"light":"data:image/svg+xml,%3Csvg%20fill=%22%234D6BFE%22%20fill-rule=%22evenodd%22%20height=%221em%22%20style=%22flex:none;line-height:1%22%20viewBox=%220%200%2024%2024%22%20width=%221em%22%20xmlns=%22http://www.w3.org/2000/svg%22%3E%3Ctitle%3EVolcengine%3C/title%3E%3Cpath%20d=%22M7.29%205.36L3.148%2021.737a.215.215%200%2000.203.261h8.29a.214.214%200%2000.215-.261L7.7%205.359a.214.214%200%2000-.41%200z%22%20fill-opacity=%22.5%22%3E%3C/path%3E%3Cpath%20clip-rule=%22evenodd%22%20d=%22M4.553%2016.18l-1.406%205.558a.214.214%200%2000.203.261h2.42-4.551a.214.214%200%2001-.214-.26l2.275-8.961a.214.214%200%2001.409%200l.864%203.402z%22%3E%3C/path%3E%3Cpath%20d=%22M14.44.15a.214.214%200%2000-.41%200L8.366%2021.739a.214.214%200%2000.214.261H19.9a.214.214%200%2000.215-.261L14.44.151z%22%20fill-opacity=%22.5%22%3E%3C/path%3E%3Cpath%20clip-rule=%22evenodd%22%20d=%22M16.694%2022h3.207a.215.215%200%2000.214-.262l-1.839-6.993%201.164-4.592a.214.214%200%2001.411%200l2.951%2011.586a.214.214%200%2001-.214.261h-5.894z%22%3E%3C/path%3E%3Cpath%20d=%22M10.278%207.741L6.685%2021.736a.214.214%200%2000.214.264h7.17a.216.216%200%2000.214-.166.216.216%200%20000-.098L10.687%207.742a.214.214%200%2000-.409%200z%22%3E%3C/path%3E%3C/svg%3E","dark":"data:image/svg+xml,%3Csvg%20fill=%22%234D6BFE%22%20fill-rule=%22evenodd%22%20height=%221em%22%20style=%22flex:none;line-height:1%22%20viewBox=%220%200%2024%2024%22%20width=%221em%22%20xmlns=%22http://www.w3.org/2000/svg%22%3E%3Ctitle%3EVolcengine%3C/title%3E%3Cpath%20d=%22M7.29%205.36L3.148%2021.737a.215.215%200%2000.203.261h8.29a.214.214%200%2000.215-.261L7.7%205.359a.214.214%200%2000-.41%200z%22%20fill-opacity=%22.5%22%3E%3C/path%3E%3Cpath%20clip-rule=%22evenodd%22%20d=%22M4.553%2016.18l-1.406%205.558a.214.214%200%2000.203.261h2.42-4.551a.214.214%200%2001-.214-.26l2.275-8.961a.214.214%200%2001.409%200l.864%203.402z%22%3E%3C/path%3E%3Cpath%20d=%22M14.44.15a.214.214%200%2000-.41%200L8.366%2021.739a.214.214%200%2000.214.261H19.9a.214.214%200%2000.215-.261L14.44.151z%22%20fill-opacity=%22.5%22%3E%3C/path%3E%3Cpath%20clip-rule=%22evenodd%22%20d=%22M16.694%2022h3.207a.215.215%200%2000.214-.262l-1.839-6.993%201.164-4.592a.214.214%200%2001.411%200l2.951%2011.586a.214.214%200%2001-.214.261h-5.894z%22%3E%3C/path%3E%3Cpath%20d=%22M10.278%207.741L6.685%2021.736a.214.214%200%2000.214.264h7.17a.216.216%200%2000.214-.166.216.216%200%20000-.098L10.687%207.742a.214.214%200%2000-.409%200z%22%3E%3C/path%3E%3C/svg%3E"},"ByteDance":{"light":"data:image/svg+xml,%3Csvg%20fill=%22%23111827%22%20fill-rule=%22evenodd%22%20height=%221em%22%20style=%22flex:none;line-height:1%22%20viewBox=%220%200%2024%2024%22%20width=%221em%22%20xmlns=%22http://www.w3.org/2000/svg%22%3E%3Ctitle%3EByteDance%3C/title%3E%3Cpath%20d=%22M14.944%2018.587l-1.704-.445V10.01l1.824-.462c1-.254%201.84-.461%201.88-.453.032%200%20.056%202.235.056%204.972v4.973l-.176-.008c-.104%200-.952-.207-1.88-.446z%22%3E%3C/path%3E%3Cpath%20d=%22M7%2016.542c0-2.736.024-4.98.064-4.98.032-.008.872.2%201.88.454l1.816.461-.016%204.05-.024%204.049-1.632.422c-.896.23-1.736.445-1.856.469L7%2021.523v-4.98z%22%3E%3C/path%3E%3Cpath%20d=%22M19.24%2012.477c0-9.03.008-9.515.144-9.475.072.024.784.207%201.576.406.792.207%201.576.405%201.744.445l.296.08-.016%208.56-.024%208.568-1.624.414c-.888.23-1.728.437-1.856.47l-.24.055v-9.523z%22%3E%3C/path%3E%3Cpath%20d=%22M1%2012.509c0-4.678.024-8.505.064-8.505.032%200%20.872.207%201.872.454l1.824.461v7.582c0%204.16-.016%207.574-.032%207.574-.024%200-.872.215-1.88.47L1%2021.013v-8.505z%22%3E%3C/path%3E%3C/svg%3E","dark":"data:image/svg+xml,%3Csvg%20fill=%22%23111827%22%20fill-rule=%22evenodd%22%20height=%221em%22%20style=%22flex:none;line-height:1%22%20viewBox=%220%200%2024%2024%22%20width=%221em%22%20xmlns=%22http://www.w3.org/2000/svg%22%3E%3Ctitle%3EByteDance%3C/title%3E%3Cpath%20d=%22M14.944%2018.587l-1.704-.445V10.01l1.824-.462c1-.254%201.84-.461%201.88-.453.032%200%20.056%202.235.056%204.972v4.973l-.176-.008c-.104%200-.952-.207-1.88-.446z%22%3E%3C/path%3E%3Cpath%20d=%22M7%2016.542c0-2.736.024-4.98.064-4.98.032-.008.872.2%201.88.454l1.816.461-.016%204.05-.024%204.049-1.632.422c-.896.23-1.736.445-1.856.469L7%2021.523v-4.98z%22%3E%3C/path%3E%3Cpath%20d=%22M19.24%2012.477c0-9.03.008-9.515.144-9.475.072.024.784.207%201.576.406.792.207%201.576.405%201.744.445l.296.08-.016%208.56-.024%208.568-1.624.414c-.888.23-1.728.437-1.856.47l-.24.055v-9.523z%22%3E%3C/path%3E%3Cpath%20d=%22M1%2012.509c0-4.678.024-8.505.064-8.505.032%200%20.872.207%201.872.454l1.824.461v7.582c0%204.16-.016%207.574-.032%207.574-.024%200-.872.215-1.88.47L1%2021.013v-8.505z%22%3E%3C/path%3E%3C/svg%3E"},"Hunyuan":{"light":"data:image/svg+xml,%3Csvg%20fill=%22%236C5CE7%22%20fill-rule=%22evenodd%22%20height=%221em%22%20style=%22flex:none;line-height:1%22%20viewBox=%220%200%2024%2024%22%20width=%221em%22%20xmlns=%22http://www.w3.org/2000/svg%22%3E%3Ctitle%3EHunyuan%3C/title%3E%3Cpath%20d=%22M12%200c6.627%200%2012%205.373%2012%2012s-5.373%2012-12%2012S0%2018.627%200%2012%205.373%200%2012%200zm1.652%201.123l-.01-.001c.533.097%201.023.233%201.41.404%206.084%202.683%207.396%209.214%201.601%2014.338a3.781%203.781%200%2001-5.337-.328%203.654%203.654%200%2001-.884-3.044c-1.934.6-3.295%202.305-3.524%204.45-.204%201.912.324%204.044%202.056%205.634l.245.067C10.1%2022.876%2011.036%2023%2012%2023c6.075%200%2011-4.925%2011-11%200-5.513-4.056-10.08-9.348-10.877zM2.748%206.21c-.178.269-.348.536-.51.803l-.235.394.078-.167A10.957%2010.957%200%20001%2012c0%204.919%203.228%209.083%207.682%2010.49l.214.065C3.523%2018.528%202.84%2014.149%206.47%208.68A2.234%202.234%200%20102.748%206.21zm10.157-5.172c4.408%201.33%203.61%205.41%202.447%206.924-.86%201.117-2.922%201.46-3.708%202.238-.666.657-1.077%201.462-1.212%202.291A5.303%205.303%200%200112%2012.258a5.672%205.672%200%20001.404-11.169%2010.51%2010.51%200%2000-.5-.052z%22%3E%3C/path%3E%3C/svg%3E","dark":"data:image/svg+xml,%3Csvg%20fill=%22%236C5CE7%22%20fill-rule=%22evenodd%22%20height=%221em%22%20style=%22flex:none;line-height:1%22%20viewBox=%220%200%2024%2024%22%20width=%221em%22%20xmlns=%22http://www.w3.org/2000/svg%22%3E%3Ctitle%3EHunyuan%3C/title%3E%3Cpath%20d=%22M12%200c6.627%200%2012%205.373%2012%2012s-5.373%2012-12%2012S0%2018.627%200%2012%205.373%200%2012%200zm1.652%201.123l-.01-.001c.533.097%201.023.233%201.41.404%206.084%202.683%207.396%209.214%201.601%2014.338a3.781%203.781%200%2001-5.337-.328%203.654%203.654%200%2001-.884-3.044c-1.934.6-3.295%202.305-3.524%204.45-.204%201.912.324%204.044%202.056%205.634l.245.067C10.1%2022.876%2011.036%2023%2012%2023c6.075%200%2011-4.925%2011-11%200-5.513-4.056-10.08-9.348-10.877zM2.748%206.21c-.178.269-.348.536-.51.803l-.235.394.078-.167A10.957%2010.957%200%20001%2012c0%204.919%203.228%209.083%207.682%2010.49l.214.065C3.523%2018.528%202.84%2014.149%206.47%208.68A2.234%202.234%200%20102.748%206.21zm10.157-5.172c4.408%201.33%203.61%205.41%202.447%206.924-.86%201.117-2.922%201.46-3.708%202.238-.666.657-1.077%201.462-1.212%202.291A5.303%205.303%200%200112%2012.258a5.672%205.672%200%20001.404-11.169%2010.51%2010.51%200%2000-.5-.052z%22%3E%3C/path%3E%3C/svg%3E"},"Tencent Cloud":{"light":"data:image/svg+xml,%3Csvg%20fill=%22%2300A4FF%22%20fill-rule=%22evenodd%22%20height=%221em%22%20style=%22flex:none;line-height:1%22%20viewBox=%220%200%2024%2024%22%20width=%221em%22%20xmlns=%22http://www.w3.org/2000/svg%22%3E%3Ctitle%3ETencentCloud%3C/title%3E%3Cpath%20d=%22M20.0483%2017.1416C19.6945%2017.4914%2018.987%2018.0161%2017.7488%2018.0161C17.2182%2018.0161%2016.5991%2018.0161%2016.3338%2018.0161C15.98%2018.0161%2013.3268%2018.0161%2010.143%2018.0161C12.4424%2015.8298%2014.3881%2013.9932%2014.565%2013.8183C14.7419%2013.6434%2015.1841%2013.2061%2015.6263%2012.8563C16.5107%2012.0692%2017.2182%2011.9817%2017.8373%2011.9817C18.7217%2011.9817%2019.4292%2012.3316%2020.0483%2012.8563C21.2864%2013.9932%2021.2864%2016.0047%2020.0483%2017.1416ZM21.5518%2011.457C20.6674%2010.495%2019.3408%209.88281%2017.9257%209.88281C16.6875%209.88281%2015.6263%2010.3201%2014.6534%2011.0197C14.2997%2011.3695%2013.769%2011.7194%2013.3268%2012.2441C12.9731%2012.5939%205.36719%2019.9401%205.36719%2019.9401C5.80939%2020.0276%206.34003%2020.0276%206.78223%2020.0276C7.22443%2020.0276%2016.0685%2020.0276%2016.4222%2020.0276C17.1298%2020.0276%2017.6604%2020.0276%2018.191%2019.9401C19.3408%2019.8527%2020.4905%2019.4154%2021.4633%2018.5409C23.4975%2016.6168%2023.4975%2013.381%2021.5518%2011.457Z%22%3E%3C/path%3E%3Cpath%20d=%22M9.1701%2010.9323C8.19726%2010.2326%207.22442%209.88281%206.07469%209.88281C4.65965%209.88281%203.33304%2010.495%202.44864%2011.457C0.502952%2013.4685%200.502952%2016.6168%202.53708%2018.6283C3.42148%2019.4154%204.30589%2019.8527%205.36717%2019.9401L7.4013%2018.0161C7.04754%2018.0161%206.60533%2018.0161%206.25157%2018.0161C5.10185%2017.9287%204.39433%2017.5789%203.95212%2017.1416C2.71396%2015.9172%202.71396%2013.9932%203.86368%2012.7688C4.48277%2012.1566%205.19029%2011.8943%206.07469%2011.8943C6.60533%2011.8943%207.4013%2011.9817%208.19726%2012.7688C8.55102%2013.1186%209.52386%2013.8183%209.87763%2014.1681H9.96607L11.2927%2012.8563V12.7688C10.6736%2012.1566%209.70075%2011.3695%209.1701%2010.9323Z%22%3E%3C/path%3E%3Cpath%20d=%22M18.4564%208.74536C17.4836%206.12171%2014.9188%204.28516%2012.0003%204.28516C8.5511%204.28516%205.80945%206.82135%205.27881%209.96973C5.54413%209.96973%205.80945%209.88228%206.16321%209.88228C6.51697%209.88228%206.95917%209.96973%207.31294%209.96973C7.75514%207.78336%209.70082%206.20917%2012.0003%206.20917C13.946%206.20917%2015.6263%207.34608%2016.4223%209.00773C16.4223%209.00773%2016.5107%209.09518%2016.5107%209.00773C17.1298%208.92027%2017.8373%208.74536%2018.4564%208.74536C18.4564%208.83282%2018.4564%208.83282%2018.4564%208.74536Z%22%3E%3C/path%3E%3C/svg%3E","dark":"data:image/svg+xml,%3Csvg%20fill=%22%2300A4FF%22%20fill-rule=%22evenodd%22%20height=%221em%22%20style=%22flex:none;line-height:1%22%20viewBox=%220%200%2024%2024%22%20width=%221em%22%20xmlns=%22http://www.w3.org/2000/svg%22%3E%3Ctitle%3ETencentCloud%3C/title%3E%3Cpath%20d=%22M20.0483%2017.1416C19.6945%2017.4914%2018.987%2018.0161%2017.7488%2018.0161C17.2182%2018.0161%2016.5991%2018.0161%2016.3338%2018.0161C15.98%2018.0161%2013.3268%2018.0161%2010.143%2018.0161C12.4424%2015.8298%2014.3881%2013.9932%2014.565%2013.8183C14.7419%2013.6434%2015.1841%2013.2061%2015.6263%2012.8563C16.5107%2012.0692%2017.2182%2011.9817%2017.8373%2011.9817C18.7217%2011.9817%2019.4292%2012.3316%2020.0483%2012.8563C21.2864%2013.9932%2021.2864%2016.0047%2020.0483%2017.1416ZM21.5518%2011.457C20.6674%2010.495%2019.3408%209.88281%2017.9257%209.88281C16.6875%209.88281%2015.6263%2010.3201%2014.6534%2011.0197C14.2997%2011.3695%2013.769%2011.7194%2013.3268%2012.2441C12.9731%2012.5939%205.36719%2019.9401%205.36719%2019.9401C5.80939%2020.0276%206.34003%2020.0276%206.78223%2020.0276C7.22443%2020.0276%2016.0685%2020.0276%2016.4222%2020.0276C17.1298%2020.0276%2017.6604%2020.0276%2018.191%2019.9401C19.3408%2019.8527%2020.4905%2019.4154%2021.4633%2018.5409C23.4975%2016.6168%2023.4975%2013.381%2021.5518%2011.457Z%22%3E%3C/path%3E%3Cpath%20d=%22M9.1701%2010.9323C8.19726%2010.2326%207.22442%209.88281%206.07469%209.88281C4.65965%209.88281%203.33304%2010.495%202.44864%2011.457C0.502952%2013.4685%200.502952%2016.6168%202.53708%2018.6283C3.42148%2019.4154%204.30589%2019.8527%205.36717%2019.9401L7.4013%2018.0161C7.04754%2018.0161%206.60533%2018.0161%206.25157%2018.0161C5.10185%2017.9287%204.39433%2017.5789%203.95212%2017.1416C2.71396%2015.9172%202.71396%2013.9932%203.86368%2012.7688C4.48277%2012.1566%205.19029%2011.8943%206.07469%2011.8943C6.60533%2011.8943%207.4013%2011.9817%208.19726%2012.7688C8.55102%2013.1186%209.52386%2013.8183%209.87763%2014.1681H9.96607L11.2927%2012.8563V12.7688C10.6736%2012.1566%209.70075%2011.3695%209.1701%2010.9323Z%22%3E%3C/path%3E%3Cpath%20d=%22M18.4564%208.74536C17.4836%206.12171%2014.9188%204.28516%2012.0003%204.28516C8.5511%204.28516%205.80945%206.82135%205.27881%209.96973C5.54413%209.96973%205.80945%209.88228%206.16321%209.88228C6.51697%209.88228%206.95917%209.96973%207.31294%209.96973C7.75514%207.78336%209.70082%206.20917%2012.0003%206.20917C13.946%206.20917%2015.6263%207.34608%2016.4223%209.00773C16.4223%209.00773%2016.5107%209.09518%2016.5107%209.00773C17.1298%208.92027%2017.8373%208.74536%2018.4564%208.74536C18.4564%208.83282%2018.4564%208.83282%2018.4564%208.74536Z%22%3E%3C/path%3E%3C/svg%3E"},"Wenxin":{"light":"data:image/svg+xml,%3Csvg%20fill=%22%232468F2%22%20fill-rule=%22evenodd%22%20height=%221em%22%20style=%22flex:none;line-height:1%22%20viewBox=%220%200%2024%2024%22%20width=%221em%22%20xmlns=%22http://www.w3.org/2000/svg%22%3E%3Ctitle%3EWenxin%3C/title%3E%3Cpath%20d=%22M11.32%201.176a1.4%201.4%200%20011.36%200l8.64%204.843c.421.234.68.67.68%201.141v9.68c0%20.472-.259.908-.68%201.143l-8.64%204.84a1.4%201.4%200%2001-1.36%200l-8.64-4.84A1.31%201.31%200%20012%2016.84V7.159c0-.471.259-.907.68-1.142l8.64-4.84zm7.42%2013.839V8.227L12.002%2012%2012%2019.551l6.059-3.394a1.31%201.31%200%2000.68-1.142zM12.68%204.833a1.393%201.393%200%2000-1.36%200L5.944%207.846c-.421.235-.68.67-.68%201.142v6.027c0%20.47.259.905.68%201.142l2.795%201.566V11.09a1.546%201.546%200%2000.221.79%201.527%201.527%200%2001-.216-.834l.004-.094.02-.15.018-.084.017-.062.039-.117.062-.142.035-.065.081-.13.094-.122.084-.091.08-.075.125-.1.071-.048.134-.076%205.87-3.29-2.796-1.566z%22%3E%3C/path%3E%3C/svg%3E","dark":"data:image/svg+xml,%3Csvg%20fill=%22%232468F2%22%20fill-rule=%22evenodd%22%20height=%221em%22%20style=%22flex:none;line-height:1%22%20viewBox=%220%200%2024%2024%22%20width=%221em%22%20xmlns=%22http://www.w3.org/2000/svg%22%3E%3Ctitle%3EWenxin%3C/title%3E%3Cpath%20d=%22M11.32%201.176a1.4%201.4%200%20011.36%200l8.64%204.843c.421.234.68.67.68%201.141v9.68c0%20.472-.259.908-.68%201.143l-8.64%204.84a1.4%201.4%200%2001-1.36%200l-8.64-4.84A1.31%201.31%200%20012%2016.84V7.159c0-.471.259-.907.68-1.142l8.64-4.84zm7.42%2013.839V8.227L12.002%2012%2012%2019.551l6.059-3.394a1.31%201.31%200%2000.68-1.142zM12.68%204.833a1.393%201.393%200%2000-1.36%200L5.944%207.846c-.421.235-.68.67-.68%201.142v6.027c0%20.47.259.905.68%201.142l2.795%201.566V11.09a1.546%201.546%200%2000.221.79%201.527%201.527%200%2001-.216-.834l.004-.094.02-.15.018-.084.017-.062.039-.117.062-.142.035-.065.081-.13.094-.122.084-.091.08-.075.125-.1.071-.048.134-.076%205.87-3.29-2.796-1.566z%22%3E%3C/path%3E%3C/svg%3E"},"Baidu":{"light":"data:image/svg+xml,%3Csvg%20fill=%22%232468F2%22%20fill-rule=%22evenodd%22%20height=%221em%22%20style=%22flex:none;line-height:1%22%20viewBox=%220%200%2024%2024%22%20width=%221em%22%20xmlns=%22http://www.w3.org/2000/svg%22%3E%3Ctitle%3EBaidu%3C/title%3E%3Cpath%20d=%22M8.859%2011.735c1.017-1.71%204.059-3.083%206.202.286%201.579%202.284%204.284%204.397%204.284%204.397s2.027%201.601.73%204.684c-1.24%202.956-5.64%201.607-6.005%201.49l-.024-.009s-1.746-.568-3.776-.112c-2.026.458-3.773.286-3.773.286l-.045-.001c-.328-.01-2.38-.187-3.001-2.968-.675-3.028%202.365-4.687%202.592-4.968.226-.288%201.802-1.37%202.816-3.085zm.986%201.738v2.032h-1.64s-1.64.138-2.213%202.014c-.2%201.252.177%201.99.242%202.148.067.157.596%201.073%201.927%201.342h3.078v-7.514l-1.394-.022zm3.588%202.191l-1.44.024v3.956s.064.985%201.44%201.344h3.541v-5.3h-1.528v3.979h-1.46s-.466-.068-.553-.447v-3.556zM9.82%2016.715v3.06H8.58s-.863-.045-1.126-1.049c-.136-.445.02-.959.088-1.16.063-.203.353-.671.951-.85H9.82zm9.525-9.036c2.086%200%202.646%202.06%202.646%202.742%200%20.688.284%203.597-2.309%203.655-2.595.057-2.704-1.77-2.704-3.08%200-1.374.277-3.317%202.367-3.317zM4.24%206.08c1.523-.135%202.645%201.55%202.762%202.513.07.625.393%203.486-1.975%204-2.364.515-3.244-2.249-2.984-3.544%200%200%20.28-2.797%202.197-2.969zm8.847-1.483c.14-1.31%201.69-3.316%202.931-3.028%201.236.285%202.367%201.944%202.137%203.37-.224%201.428-1.345%203.313-3.095%203.082-1.748-.226-2.143-1.823-1.973-3.424zM9.425%201c1.307%200%202.364%201.519%202.364%203.398%200%201.879-1.057%203.4-2.364%203.4s-2.367-1.521-2.367-3.4C7.058%202.518%208.118%201%209.425%201z%22%3E%3C/path%3E%3C/svg%3E","dark":"data:image/svg+xml,%3Csvg%20fill=%22%232468F2%22%20fill-rule=%22evenodd%22%20height=%221em%22%20style=%22flex:none;line-height:1%22%20viewBox=%220%200%2024%2024%22%20width=%221em%22%20xmlns=%22http://www.w3.org/2000/svg%22%3E%3Ctitle%3EBaidu%3C/title%3E%3Cpath%20d=%22M8.859%2011.735c1.017-1.71%204.059-3.083%206.202.286%201.579%202.284%204.284%204.397%204.284%204.397s2.027%201.601.73%204.684c-1.24%202.956-5.64%201.607-6.005%201.49l-.024-.009s-1.746-.568-3.776-.112c-2.026.458-3.773.286-3.773.286l-.045-.001c-.328-.01-2.38-.187-3.001-2.968-.675-3.028%202.365-4.687%202.592-4.968.226-.288%201.802-1.37%202.816-3.085zm.986%201.738v2.032h-1.64s-1.64.138-2.213%202.014c-.2%201.252.177%201.99.242%202.148.067.157.596%201.073%201.927%201.342h3.078v-7.514l-1.394-.022zm3.588%202.191l-1.44.024v3.956s.064.985%201.44%201.344h3.541v-5.3h-1.528v3.979h-1.46s-.466-.068-.553-.447v-3.556zM9.82%2016.715v3.06H8.58s-.863-.045-1.126-1.049c-.136-.445.02-.959.088-1.16.063-.203.353-.671.951-.85H9.82zm9.525-9.036c2.086%200%202.646%202.06%202.646%202.742%200%20.688.284%203.597-2.309%203.655-2.595.057-2.704-1.77-2.704-3.08%200-1.374.277-3.317%202.367-3.317zM4.24%206.08c1.523-.135%202.645%201.55%202.762%202.513.07.625.393%203.486-1.975%204-2.364.515-3.244-2.249-2.984-3.544%200%200%20.28-2.797%202.197-2.969zm8.847-1.483c.14-1.31%201.69-3.316%202.931-3.028%201.236.285%202.367%201.944%202.137%203.37-.224%201.428-1.345%203.313-3.095%203.082-1.748-.226-2.143-1.823-1.973-3.424zM9.425%201c1.307%200%202.364%201.519%202.364%203.398%200%201.879-1.057%203.4-2.364%203.4s-2.367-1.521-2.367-3.4C7.058%202.518%208.118%201%209.425%201z%22%3E%3C/path%3E%3C/svg%3E"},"Spark":{"light":"data:image/svg+xml,%3Csvg%20fill=%22%234B7BFF%22%20fill-rule=%22evenodd%22%20height=%221em%22%20style=%22flex:none;line-height:1%22%20viewBox=%220%200%2024%2024%22%20width=%221em%22%20xmlns=%22http://www.w3.org/2000/svg%22%3E%3Ctitle%3ESpark%3C/title%3E%3Cpath%20d=%22M11.615%200l6.237%206.107c2.382%202.338%202.823%203.743%203.161%206.15-1.197-1.732-1.776-2.02-4.504-2.772C12.48%208.374%2011.095%205.933%2011.615%200z%22%3E%3C/path%3E%3Cpath%20d=%22M9.32%202.122C4.771%206.367%202%209.182%202%2013.08c0%205.76%204.288%209.788%209.745%209.918%205.457.13%209.441-5.284%209.095-8.403-.347-3.118-4.418-3.81-4.418-3.81%201.69%203.16-.13%208.098-4.894%208.098-5.154%200-6.8-6.02-4.2-9.008.82%201.617%201.879%202.563%202.674%203.273.717.64%201.219%201.09%201.136%201.664-.173%201.213-1.385.866-1.385.866.346.607%203.6%201.473%204.59-1.342.613-1.741-.423-2.789-1.714-4.096-1.632-1.651-3.672-3.717-3.31-8.118z%22%3E%3C/path%3E%3C/svg%3E","dark":"data:image/svg+xml,%3Csvg%20fill=%22%234B7BFF%22%20fill-rule=%22evenodd%22%20height=%221em%22%20style=%22flex:none;line-height:1%22%20viewBox=%220%200%2024%2024%22%20width=%221em%22%20xmlns=%22http://www.w3.org/2000/svg%22%3E%3Ctitle%3ESpark%3C/title%3E%3Cpath%20d=%22M11.615%200l6.237%206.107c2.382%202.338%202.823%203.743%203.161%206.15-1.197-1.732-1.776-2.02-4.504-2.772C12.48%208.374%2011.095%205.933%2011.615%200z%22%3E%3C/path%3E%3Cpath%20d=%22M9.32%202.122C4.771%206.367%202%209.182%202%2013.08c0%205.76%204.288%209.788%209.745%209.918%205.457.13%209.441-5.284%209.095-8.403-.347-3.118-4.418-3.81-4.418-3.81%201.69%203.16-.13%208.098-4.894%208.098-5.154%200-6.8-6.02-4.2-9.008.82%201.617%201.879%202.563%202.674%203.273.717.64%201.219%201.09%201.136%201.664-.173%201.213-1.385.866-1.385.866.346.607%203.6%201.473%204.59-1.342.613-1.741-.423-2.789-1.714-4.096-1.632-1.651-3.672-3.717-3.31-8.118z%22%3E%3C/path%3E%3C/svg%3E"},"iFlytek":{"light":"data:image/svg+xml,%3Csvg%20fill=%22%232878FF%22%20fill-rule=%22evenodd%22%20height=%221em%22%20style=%22flex:none;line-height:1%22%20viewBox=%220%200%2024%2024%22%20width=%221em%22%20xmlns=%22http://www.w3.org/2000/svg%22%3E%3Ctitle%3EiFlyTekCloud%3C/title%3E%3Cpath%20d=%22M20.713%206.655c-.414-1.426-1.748-2.472-3.357-2.472a3.62%203.62%200%2000-1.7.423C14.62%203.046%2012.804%202%2010.735%202%207.77%202%205.31%204.16%204.943%206.944%202.138%207.39%200%209.728%200%2012.58c0%203.14%202.62%205.68%205.862%205.68%201.61%200%203.08-.646%204.138-1.671.276-.267.529-.557.736-.89a5.02%205.02%200%2001-.713.845%208.998%208.998%200%2000-1.77%205.39V22a16.682%2016.682%200%20018.666-2.717h.046c3.035%200%205.633-1.871%206.621-4.499A6.599%206.599%200%200024%2012.445c0-2.427-1.31-4.565-3.287-5.79zM6.966%2012.869a.836.836%200%2001-.851.824.81.81%200%2001-.805-.824v-2.183a.81.81%200%2001.805-.824c.46%200%20.85.379.85.824v2.183zm3.011%201.069a.86.86%200%2001-.874.846.86.86%200%2001-.873-.846v-4.9a.86.86%200%2001.873-.846.86.86%200%2001.874.846v4.9zm3.104-1.047c0%20.445-.414.824-.874.824s-.85-.379-.85-.824v-2.227c0-.446.367-.824.85-.824.46%200%20.873.378.873.824v2.227zm3.149%201.069a.86.86%200%2001-.874.846.86.86%200%2001-.873-.846v-4.9a.86.86%200%2001.873-.846.86.86%200%2001.874.846v4.9zm3.08-1.091a.836.836%200%2001-.85.824.81.81%200%2001-.805-.824v-2.183a.81.81%200%2001.805-.824c.46%200%20.85.379.85.824v2.183z%22%3E%3C/path%3E%3C/svg%3E","dark":"data:image/svg+xml,%3Csvg%20fill=%22%232878FF%22%20fill-rule=%22evenodd%22%20height=%221em%22%20style=%22flex:none;line-height:1%22%20viewBox=%220%200%2024%2024%22%20width=%221em%22%20xmlns=%22http://www.w3.org/2000/svg%22%3E%3Ctitle%3EiFlyTekCloud%3C/title%3E%3Cpath%20d=%22M20.713%206.655c-.414-1.426-1.748-2.472-3.357-2.472a3.62%203.62%200%2000-1.7.423C14.62%203.046%2012.804%202%2010.735%202%207.77%202%205.31%204.16%204.943%206.944%202.138%207.39%200%209.728%200%2012.58c0%203.14%202.62%205.68%205.862%205.68%201.61%200%203.08-.646%204.138-1.671.276-.267.529-.557.736-.89a5.02%205.02%200%2001-.713.845%208.998%208.998%200%2000-1.77%205.39V22a16.682%2016.682%200%20018.666-2.717h.046c3.035%200%205.633-1.871%206.621-4.499A6.599%206.599%200%200024%2012.445c0-2.427-1.31-4.565-3.287-5.79zM6.966%2012.869a.836.836%200%2001-.851.824.81.81%200%2001-.805-.824v-2.183a.81.81%200%2001.805-.824c.46%200%20.85.379.85.824v2.183zm3.011%201.069a.86.86%200%2001-.874.846.86.86%200%2001-.873-.846v-4.9a.86.86%200%2001.873-.846.86.86%200%2001.874.846v4.9zm3.104-1.047c0%20.445-.414.824-.874.824s-.85-.379-.85-.824v-2.227c0-.446.367-.824.85-.824.46%200%20.873.378.873.824v2.227zm3.149%201.069a.86.86%200%2001-.874.846.86.86%200%2001-.873-.846v-4.9a.86.86%200%2001.873-.846.86.86%200%2001.874.846v4.9zm3.08-1.091a.836.836%200%2001-.85.824.81.81%200%2001-.805-.824v-2.183a.81.81%200%2001.805-.824c.46%200%20.85.379.85.824v2.183z%22%3E%3C/path%3E%3C/svg%3E"},"MiniMax":{"light":"data:image/svg+xml,%3Csvg%20fill=%22%236D5CE8%22%20fill-rule=%22evenodd%22%20height=%221em%22%20style=%22flex:none;line-height:1%22%20viewBox=%220%200%2024%2024%22%20width=%221em%22%20xmlns=%22http://www.w3.org/2000/svg%22%3E%3Ctitle%3EMinimax%3C/title%3E%3Cpath%20d=%22M16.278%202c1.156%200%202.093.927%202.093%202.07v12.501a.74.74%200%2000.744.709.74.74%200%2000.743-.709V9.099a2.06%202.06%200%20012.071-2.049A2.06%202.06%200%200124%209.1v6.561a.649.649%200%2001-.652.645.649.649%200%2001-.653-.645V9.1a.762.762%200%2000-.766-.758.762.762%200%2000-.766.758v7.472a2.037%202.037%200%2001-2.048%202.026%202.037%202.037%200%2001-2.048-2.026v-12.5a.785.785%200%2000-.788-.753.785.785%200%2000-.789.752l-.001%2015.904A2.037%202.037%200%200113.441%2022a2.037%202.037%200%2001-2.048-2.026V18.04c0-.356.292-.645.652-.645.36%200%20.652.289.652.645v1.934c0%20.263.142.506.372.638.23.131.514.131.744%200a.734.734%200%2000.372-.638V4.07c0-1.143.937-2.07%202.093-2.07zm-5.674%200c1.156%200%202.093.927%202.093%202.07v11.523a.648.648%200%2001-.652.645.648.648%200%2001-.652-.645V4.07a.785.785%200%2000-.789-.78.785.785%200%2000-.789.78v14.013a2.06%202.06%200%2001-2.07%202.048%202.06%202.06%200%2001-2.071-2.048V9.1a.762.762%200%2000-.766-.758.762.762%200%2000-.766.758v3.8a2.06%202.06%200%2001-2.071%202.049A2.06%202.06%200%20010%2012.9v-1.378c0-.357.292-.646.652-.646.36%200%20.653.29.653.646V12.9c0%20.418.343.757.766.757s.766-.339.766-.757V9.099a2.06%202.06%200%20012.07-2.048%202.06%202.06%200%20012.071%202.048v8.984c0%20.419.343.758.767.758.423%200%20.766-.339.766-.758V4.07c0-1.143.937-2.07%202.093-2.07z%22%3E%3C/path%3E%3C/svg%3E","dark":"data:image/svg+xml,%3Csvg%20fill=%22%236D5CE8%22%20fill-rule=%22evenodd%22%20height=%221em%22%20style=%22flex:none;line-height:1%22%20viewBox=%220%200%2024%2024%22%20width=%221em%22%20xmlns=%22http://www.w3.org/2000/svg%22%3E%3Ctitle%3EMinimax%3C/title%3E%3Cpath%20d=%22M16.278%202c1.156%200%202.093.927%202.093%202.07v12.501a.74.74%200%2000.744.709.74.74%200%2000.743-.709V9.099a2.06%202.06%200%20012.071-2.049A2.06%202.06%200%200124%209.1v6.561a.649.649%200%2001-.652.645.649.649%200%2001-.653-.645V9.1a.762.762%200%2000-.766-.758.762.762%200%2000-.766.758v7.472a2.037%202.037%200%2001-2.048%202.026%202.037%202.037%200%2001-2.048-2.026v-12.5a.785.785%200%2000-.788-.753.785.785%200%2000-.789.752l-.001%2015.904A2.037%202.037%200%200113.441%2022a2.037%202.037%200%2001-2.048-2.026V18.04c0-.356.292-.645.652-.645.36%200%20.652.289.652.645v1.934c0%20.263.142.506.372.638.23.131.514.131.744%200a.734.734%200%2000.372-.638V4.07c0-1.143.937-2.07%202.093-2.07zm-5.674%200c1.156%200%202.093.927%202.093%202.07v11.523a.648.648%200%2001-.652.645.648.648%200%2001-.652-.645V4.07a.785.785%200%2000-.789-.78.785.785%200%2000-.789.78v14.013a2.06%202.06%200%2001-2.07%202.048%202.06%202.06%200%2001-2.071-2.048V9.1a.762.762%200%2000-.766-.758.762.762%200%2000-.766.758v3.8a2.06%202.06%200%2001-2.071%202.049A2.06%202.06%200%20010%2012.9v-1.378c0-.357.292-.646.652-.646.36%200%20.653.29.653.646V12.9c0%20.418.343.757.766.757s.766-.339.766-.757V9.099a2.06%202.06%200%20012.07-2.048%202.06%202.06%200%20012.071%202.048v8.984c0%20.419.343.758.767.758.423%200%20.766-.339.766-.758V4.07c0-1.143.937-2.07%202.093-2.07z%22%3E%3C/path%3E%3C/svg%3E"},"Xiaomi MiMo":{"light":"data:image/svg+xml,%3Csvg%20fill=%22%23FF6900%22%20fill-rule=%22evenodd%22%20height=%221em%22%20style=%22flex:none;line-height:1%22%20viewBox=%220%200%2024%2024%22%20width=%221em%22%20xmlns=%22http://www.w3.org/2000/svg%22%3E%3Ctitle%3EXiaomiMiMo%3C/title%3E%3Cpath%20d=%22M.958%2015.936a.459.459%200%2001.459.44v2.729a.46.46%200%2001-.918%200v-2.729a.459.459%200%2001.459-.44zm4.814-2.035a.46.46%200%2001.553.45v4.754a.458.458%200%2011-.918%200V15.48L3.74%2017.202a.462.462%200%2001-.655.016.462.462%200%2001-.065-.082L.628%2014.67a.459.459%200%2001.658-.637l2.124%202.187%202.127-2.188a.46.46%200%2001.235-.13zm2.068.004a.46.46%200%2001.458.445v4.755a.46.46%200%2001-.458.458.459.459%200%2001-.458-.458V14.35a.459.459%200%2001.458-.445zm1.973%202.014a.46.46%200%2001.46.457v2.729a.46.46%200%2001-.784.324.46.46%200%2001-.134-.324v-2.729a.46.46%200%2001.458-.458zm.002-2.045a.458.458%200%2001.328.157l2.127%202.19%202.125-2.19a.459.459%200%2001.784.318v4.756a.46.46%200%2001-.455.458.46.46%200%2001-.458-.458V15.48l-1.667%201.723a.46.46%200%2001-.65.008l-.005-.005c0-.002-.002-.002-.004-.003l-2.455-2.534a.46.46%200%2001-.008-.667.461.461%200%2001.338-.128zm6.797%201.206a.46.46%200%2001.53.651A1.966%201.966%200%200019.81%2018.4a.462.462%200%2001.623.18.46.46%200%2001-.181.624%202.863%202.863%200%2001-1.38.353l-.142-.004a2.88%202.88%200%2001-2.393-4.263.461.461%200%2001.274-.21zm.864-.931a2.884%202.884%200%20013.915%203.914.46.46%200%2001-.402.24l-.057-.004a.458.458%200%2001-.164-.055.46.46%200%2001-.182-.622%201.967%201.967%200%2000-2.669-2.67.459.459%200%2011-.441-.803zM9.59%206.368c1.481%200%201.696%201.202%201.696%201.654v2.648h-.917v-.432c-.26.346-.792.535-1.36.535-.133%200-1.289-.03-1.384-1.136-.082-.932.675-1.61%202.053-1.61h.691c0-.563-.367-.886-.983-.886-.44.013-.864.174-1.2.458l-.36-.664c.484-.379%201.012-.567%201.764-.567zm4.427.1c1.263%200%202.082.97%202.083%202.15%200%201.181-.824%202.154-2.083%202.154-1.26%200-2.084-.972-2.084-2.152%200-1.18.82-2.153%202.084-2.153zm6.801.015c.68%200%201.202.465%201.197%201.548v2.642H21.1V8.29c0-.312-.002-.98-.63-.98s-.628.667-.628.838v2.524h-.89V8.148c0-.17-.001-.838-.63-.838-.628%200-.628.668-.628.98v2.383h-.917v-4.03h.917V7a1.22%201.22%200%2001.947-.516c.398%200%20.76.193.982.686a1.321%201.321%200%20011.195-.686zm-18.093.872l1.457-1.772H5.32L3.311%208.07l2.14%202.602H4.24L2.725%208.796%201.21%2010.672H0L2.138%208.07.13%205.583h1.138l1.458%201.772zm4.149%203.317h-.916V6.644h.916v4.028zm16.99%200h-.916V6.644h.916v4.028zM9.925%208.71c-1.055%200-1.359.412-1.326.742.032.329.324.537.757.537a1.013%201.013%200%20001.014-.968l.002-.31h-.447zM14.018%207.3c-.663%200-1.184.487-1.184%201.32%200%20.832.52%201.32%201.184%201.32.662%200%201.182-.49%201.182-1.32%200-.832-.52-1.32-1.182-1.32zM6.417%205.001a.568.568%200%2001.587.582.588.588%200%2001-1.175%200A.57.57%200%20016.417%205zm16.991%200a.57.57%200%2001.592.582.588.588%200%2001-1.174%200%20.57.57%200%2001.357-.542.572.572%200%2001.225-.04z%22%3E%3C/path%3E%3C/svg%3E","dark":"data:image/svg+xml,%3Csvg%20fill=%22%23FF6900%22%20fill-rule=%22evenodd%22%20height=%221em%22%20style=%22flex:none;line-height:1%22%20viewBox=%220%200%2024%2024%22%20width=%221em%22%20xmlns=%22http://www.w3.org/2000/svg%22%3E%3Ctitle%3EXiaomiMiMo%3C/title%3E%3Cpath%20d=%22M.958%2015.936a.459.459%200%2001.459.44v2.729a.46.46%200%2001-.918%200v-2.729a.459.459%200%2001.459-.44zm4.814-2.035a.46.46%200%2001.553.45v4.754a.458.458%200%2011-.918%200V15.48L3.74%2017.202a.462.462%200%2001-.655.016.462.462%200%2001-.065-.082L.628%2014.67a.459.459%200%2001.658-.637l2.124%202.187%202.127-2.188a.46.46%200%2001.235-.13zm2.068.004a.46.46%200%2001.458.445v4.755a.46.46%200%2001-.458.458.459.459%200%2001-.458-.458V14.35a.459.459%200%2001.458-.445zm1.973%202.014a.46.46%200%2001.46.457v2.729a.46.46%200%2001-.784.324.46.46%200%2001-.134-.324v-2.729a.46.46%200%2001.458-.458zm.002-2.045a.458.458%200%2001.328.157l2.127%202.19%202.125-2.19a.459.459%200%2001.784.318v4.756a.46.46%200%2001-.455.458.46.46%200%2001-.458-.458V15.48l-1.667%201.723a.46.46%200%2001-.65.008l-.005-.005c0-.002-.002-.002-.004-.003l-2.455-2.534a.46.46%200%2001-.008-.667.461.461%200%2001.338-.128zm6.797%201.206a.46.46%200%2001.53.651A1.966%201.966%200%200019.81%2018.4a.462.462%200%2001.623.18.46.46%200%2001-.181.624%202.863%202.863%200%2001-1.38.353l-.142-.004a2.88%202.88%200%2001-2.393-4.263.461.461%200%2001.274-.21zm.864-.931a2.884%202.884%200%20013.915%203.914.46.46%200%2001-.402.24l-.057-.004a.458.458%200%2001-.164-.055.46.46%200%2001-.182-.622%201.967%201.967%200%2000-2.669-2.67.459.459%200%2011-.441-.803zM9.59%206.368c1.481%200%201.696%201.202%201.696%201.654v2.648h-.917v-.432c-.26.346-.792.535-1.36.535-.133%200-1.289-.03-1.384-1.136-.082-.932.675-1.61%202.053-1.61h.691c0-.563-.367-.886-.983-.886-.44.013-.864.174-1.2.458l-.36-.664c.484-.379%201.012-.567%201.764-.567zm4.427.1c1.263%200%202.082.97%202.083%202.15%200%201.181-.824%202.154-2.083%202.154-1.26%200-2.084-.972-2.084-2.152%200-1.18.82-2.153%202.084-2.153zm6.801.015c.68%200%201.202.465%201.197%201.548v2.642H21.1V8.29c0-.312-.002-.98-.63-.98s-.628.667-.628.838v2.524h-.89V8.148c0-.17-.001-.838-.63-.838-.628%200-.628.668-.628.98v2.383h-.917v-4.03h.917V7a1.22%201.22%200%2001.947-.516c.398%200%20.76.193.982.686a1.321%201.321%200%20011.195-.686zm-18.093.872l1.457-1.772H5.32L3.311%208.07l2.14%202.602H4.24L2.725%208.796%201.21%2010.672H0L2.138%208.07.13%205.583h1.138l1.458%201.772zm4.149%203.317h-.916V6.644h.916v4.028zm16.99%200h-.916V6.644h.916v4.028zM9.925%208.71c-1.055%200-1.359.412-1.326.742.032.329.324.537.757.537a1.013%201.013%200%20001.014-.968l.002-.31h-.447zM14.018%207.3c-.663%200-1.184.487-1.184%201.32%200%20.832.52%201.32%201.184%201.32.662%200%201.182-.49%201.182-1.32%200-.832-.52-1.32-1.182-1.32zM6.417%205.001a.568.568%200%2001.587.582.588.588%200%2001-1.175%200A.57.57%200%20016.417%205zm16.991%200a.57.57%200%2001.592.582.588.588%200%2001-1.174%200%20.57.57%200%2001.357-.542.572.572%200%2001.225-.04z%22%3E%3C/path%3E%3C/svg%3E"},"StepFun":{"light":"data:image/svg+xml,%3Csvg%20fill=%22%235B5CE2%22%20fill-rule=%22evenodd%22%20height=%221em%22%20style=%22flex:none;line-height:1%22%20viewBox=%220%200%2024%2024%22%20width=%221em%22%20xmlns=%22http://www.w3.org/2000/svg%22%3E%3Ctitle%3EStepFun%3C/title%3E%3Cpath%20d=%22M12%200C5.372%200%200%205.372%200%2012s5.372%2012%2012%2012%2012-5.372%2012-12S18.628%200%2012%200zM8.762%2019.614H4.376v-4.386h4.386v4.386zm5.423%200H9.798v-4.386h4.387v4.386zm0-5.42H9.798V9.81h4.387v4.386zm0-5.418H9.798V4.39h4.387v4.386zm5.422-.004h-4.386V4.386h4.386v4.386z%22%3E%3C/path%3E%3C/svg%3E","dark":"data:image/svg+xml,%3Csvg%20fill=%22%235B5CE2%22%20fill-rule=%22evenodd%22%20height=%221em%22%20style=%22flex:none;line-height:1%22%20viewBox=%220%200%2024%2024%22%20width=%221em%22%20xmlns=%22http://www.w3.org/2000/svg%22%3E%3Ctitle%3EStepFun%3C/title%3E%3Cpath%20d=%22M12%200C5.372%200%200%205.372%200%2012s5.372%2012%2012%2012%2012-5.372%2012-12S18.628%200%2012%200zM8.762%2019.614H4.376v-4.386h4.386v4.386zm5.423%200H9.798v-4.386h4.387v4.386zm0-5.42H9.798V9.81h4.387v4.386zm0-5.418H9.798V4.39h4.387v4.386zm5.422-.004h-4.386V4.386h4.386v4.386z%22%3E%3C/path%3E%3C/svg%3E"},"Yi":{"light":"data:image/svg+xml,%3Csvg%20fill=%22%236A5AE0%22%20fill-rule=%22evenodd%22%20height=%221em%22%20style=%22flex:none;line-height:1%22%20viewBox=%220%200%2024%2024%22%20width=%221em%22%20xmlns=%22http://www.w3.org/2000/svg%22%3E%3Ctitle%3EYi%3C/title%3E%3Cpath%20d=%22M18.62%2013.927c.611%200%201.107.505%201.107%201.128v5.817c0%20.623-.496%201.128-1.108%201.128a1.118%201.118%200%2001-1.108-1.128v-5.817c0-.623.496-1.128%201.108-1.128zM16.59%203.052a1.094%201.094%200%20011.562-.129c.466.404.522%201.116.126%201.59l-5.938%207.111v9.147c0%20.624-.496%201.129-1.108%201.129a1.118%201.118%200%2001-1.108-1.129v-9.477l.003-.088.01-.087c.015-.232.102-.462.261-.654l6.192-7.413zM2.906%202.256a1.094%201.094%200%20011.559.157l4.387%205.45a1.142%201.142%200%2001-.155%201.587%201.094%201.094%200%2001-1.559-.157l-4.387-5.45a1.144%201.144%200%2001.06-1.498l.095-.09z%22%3E%3C/path%3E%3Cellipse%20cx=%2220.146%22%20cy=%2210.692%22%20rx=%221.354%22%20ry=%221.379%22%3E%3C/ellipse%3E%3C/svg%3E","dark":"data:image/svg+xml,%3Csvg%20fill=%22%236A5AE0%22%20fill-rule=%22evenodd%22%20height=%221em%22%20style=%22flex:none;line-height:1%22%20viewBox=%220%200%2024%2024%22%20width=%221em%22%20xmlns=%22http://www.w3.org/2000/svg%22%3E%3Ctitle%3EYi%3C/title%3E%3Cpath%20d=%22M18.62%2013.927c.611%200%201.107.505%201.107%201.128v5.817c0%20.623-.496%201.128-1.108%201.128a1.118%201.118%200%2001-1.108-1.128v-5.817c0-.623.496-1.128%201.108-1.128zM16.59%203.052a1.094%201.094%200%20011.562-.129c.466.404.522%201.116.126%201.59l-5.938%207.111v9.147c0%20.624-.496%201.129-1.108%201.129a1.118%201.118%200%2001-1.108-1.129v-9.477l.003-.088.01-.087c.015-.232.102-.462.261-.654l6.192-7.413zM2.906%202.256a1.094%201.094%200%20011.559.157l4.387%205.45a1.142%201.142%200%2001-.155%201.587%201.094%201.094%200%2001-1.559-.157l-4.387-5.45a1.144%201.144%200%2001.06-1.498l.095-.09z%22%3E%3C/path%3E%3Cellipse%20cx=%2220.146%22%20cy=%2210.692%22%20rx=%221.354%22%20ry=%221.379%22%3E%3C/ellipse%3E%3C/svg%3E"},"ZeroOne":{"light":"data:image/svg+xml,%3Csvg%20fill=%22%236B5CE7%22%20fill-rule=%22evenodd%22%20height=%221em%22%20style=%22flex:none;line-height:1%22%20viewBox=%220%200%2024%2024%22%20width=%221em%22%20xmlns=%22http://www.w3.org/2000/svg%22%3E%3Ctitle%3E01.AI%3C/title%3E%3Cpath%20clip-rule=%22evenodd%22%20d=%22M18.62%2013.927c.611%200%201.107.505%201.107%201.128v5.817c0%20.623-.496%201.128-1.108%201.128a1.118%201.118%200%2001-1.108-1.128v-5.817c0-.623.496-1.128%201.108-1.128h.001zM16.59%203.052a1.095%201.095%200%20011.562-.13c.466.405.522%201.117.126%201.59l-5.938%207.112v9.147c0%20.624-.496%201.129-1.108%201.129a1.119%201.119%200%2001-1.108-1.13v-9.476l.003-.088.01-.087a1.14%201.14%200%2001.261-.654l6.192-7.413zM2.906%202.256a1.094%201.094%200%20011.559.157l4.387%205.45a1.142%201.142%200%2001-.155%201.587%201.094%201.094%200%2001-1.559-.157l-4.387-5.45a1.144%201.144%200%2001.06-1.498l.095-.09z%22%3E%3C/path%3E%3Cpath%20d=%22M20.146%2012.071c.748%200%201.354-.617%201.354-1.379s-.606-1.379-1.354-1.379c-.748%200-1.354.617-1.354%201.379s.606%201.379%201.354%201.379z%22%3E%3C/path%3E%3C/svg%3E","dark":"data:image/svg+xml,%3Csvg%20fill=%22%236B5CE7%22%20fill-rule=%22evenodd%22%20height=%221em%22%20style=%22flex:none;line-height:1%22%20viewBox=%220%200%2024%2024%22%20width=%221em%22%20xmlns=%22http://www.w3.org/2000/svg%22%3E%3Ctitle%3E01.AI%3C/title%3E%3Cpath%20clip-rule=%22evenodd%22%20d=%22M18.62%2013.927c.611%200%201.107.505%201.107%201.128v5.817c0%20.623-.496%201.128-1.108%201.128a1.118%201.118%200%2001-1.108-1.128v-5.817c0-.623.496-1.128%201.108-1.128h.001zM16.59%203.052a1.095%201.095%200%20011.562-.13c.466.405.522%201.117.126%201.59l-5.938%207.112v9.147c0%20.624-.496%201.129-1.108%201.129a1.119%201.119%200%2001-1.108-1.13v-9.476l.003-.088.01-.087a1.14%201.14%200%2001.261-.654l6.192-7.413zM2.906%202.256a1.094%201.094%200%20011.559.157l4.387%205.45a1.142%201.142%200%2001-.155%201.587%201.094%201.094%200%2001-1.559-.157l-4.387-5.45a1.144%201.144%200%2001.06-1.498l.095-.09z%22%3E%3C/path%3E%3Cpath%20d=%22M20.146%2012.071c.748%200%201.354-.617%201.354-1.379s-.606-1.379-1.354-1.379c-.748%200-1.354.617-1.354%201.379s.606%201.379%201.354%201.379z%22%3E%3C/path%3E%3C/svg%3E"},"Baichuan":{"light":"data:image/svg+xml,%3Csvg%20fill=%22%2320A37F%22%20fill-rule=%22evenodd%22%20height=%221em%22%20style=%22flex:none;line-height:1%22%20viewBox=%220%200%2024%2024%22%20width=%221em%22%20xmlns=%22http://www.w3.org/2000/svg%22%3E%3Ctitle%3EBaichuan%3C/title%3E%3Cpath%20d=%22M7.333%202h-3.2l-2%204.333V17.8L0%2022h5.2l2.028-4.2L7.333%202zm7.334%200h-5.2v20h5.2V2zM16.8%207.733H22V22h-5.2V7.733zM22%202h-5.2v4.133H22V2z%22%3E%3C/path%3E%3C/svg%3E","dark":"data:image/svg+xml,%3Csvg%20fill=%22%2320A37F%22%20fill-rule=%22evenodd%22%20height=%221em%22%20style=%22flex:none;line-height:1%22%20viewBox=%220%200%2024%2024%22%20width=%221em%22%20xmlns=%22http://www.w3.org/2000/svg%22%3E%3Ctitle%3EBaichuan%3C/title%3E%3Cpath%20d=%22M7.333%202h-3.2l-2%204.333V17.8L0%2022h5.2l2.028-4.2L7.333%202zm7.334%200h-5.2v20h5.2V2zM16.8%207.733H22V22h-5.2V7.733zM22%202h-5.2v4.133H22V2z%22%3E%3C/path%3E%3C/svg%3E"},"InternLM":{"light":"data:image/svg+xml,%3Csvg%20fill=%22%230F766E%22%20fill-rule=%22evenodd%22%20height=%221em%22%20style=%22flex:none;line-height:1%22%20viewBox=%220%200%2024%2024%22%20width=%221em%22%20xmlns=%22http://www.w3.org/2000/svg%22%3E%3Ctitle%3EInternLM%3C/title%3E%3Cpath%20d=%22M5.54%2019.662s2.24-.25%202.365-.29c.125-.042%202.45.082%202.45.082l1.493.374%201.37.498.373.125%202.033-.748%202.45-.373%201.659.041%201.286.166.54.166-.042%202.242-1.12-.291-2.159-.166-1.494.124-1.286.291-1.161.374-.83.332-1.744-.664-2.116-.416H7.158l-1.618.291v-2.158z%22%20fill-opacity=%22.5%22%3E%3C/path%3E%3Cpath%20d=%22M13.46%2023c-3.773-2.078-7.78-.832-7.82-.819l-.453.144v-2.86l.24-.078c.174-.056%204.324-1.354%208.366.871l-.333.607c-3.244-1.786-6.66-1.115-7.58-.885V21.4c1.203-.286%204.595-.834%207.913.993L13.46%2023V23z%22%3E%3C/path%3E%3Cpath%20d=%22M13.413%2023l-.334-.607c3.319-1.827%206.71-1.279%207.914-.993v-1.419c-.92-.231-4.337-.9-7.58.885l-.334-.607c4.042-2.225%208.192-.927%208.366-.87l.24.077v2.862l-.452-.147c-.04-.013-4.046-1.258-7.82.819z%22%3E%3C/path%3E%3Cpath%20d=%22M17.756%2016.476a.904.904%200%2000-.264-.651.822.822%200%2000-.632-.255.997.997%200%2000-.644.293c-.175.212-.26.433-.259.685a.874.874%200%2000.256.632c.175.187.39.272.644.255.246%200%20.459-.1.633-.293a.97.97%200%2000.268-.667l-.002.001zM10.769%2017.143a.928.928%200%2000.264-.658.993.993%200%2000-.262-.679.908.908%200%2000-.633-.227%201.089%201.089%200%2000-.644.274%201.005%201.005%200%2000-.265.685c0%20.25.089.465.264.643.17.187.383.271.636.255.26-.008.471-.1.639-.293z%22%20fill-opacity=%22.5%22%3E%3C/path%3E%3Cpath%20d=%22M13.4%2019.65c-.693%200-1.374-.058-1.895-.192-1.403-.36-2.52-1.01-3.413-1.986-.929-1.017-.988-1.996-1.05-3.033-.008-.133-.016-.267-.026-.405-.083-1.147-.626-2.941-.631-2.958l-.043-.141.086-.119A6.966%206.966%200%20019.44%208.441c1.128-.47%202.47-.716%204.105-.752%202.721-.159%205.688.973%207.056%202.692l.086.109-.62%202.89c-.006.155-.052.968-.276%202.63-.263%201.947-2.668%203.061-3.903%203.377-.628.162-1.57.262-2.488.262zm-6.41-8.603c.134.46.538%201.912.613%202.944.01.139.018.277.026.412.06%201.01.109%201.809.896%202.672.815.89%201.837%201.484%203.125%201.814%201.092.28%203.061.194%204.091-.071.887-.228%203.24-1.19%203.468-2.889.24-1.786.272-2.593.273-2.6v-.026l.572-2.664c-.9-1.728-1.433-2.082-2.578-2.514-1.206-.455-2.677.075-3.903.148h-.01c-3.126.068-5.418-.935-6.574%202.773h.001z%22%3E%3C/path%3E%3Cpath%20d=%22M19.545%2010.862c.223.573.317.86.526%201.386%200%200%20.552-.887.727-1.522.175-.641.068-1.458-.07-2.221-.344-1.282-.612-1.381-1.647-2.14a8.668%208.668%200%2000-1.565-.84%2012.303%2012.303%200%2000-3.83-.8%2012.175%2012.175%200%2000-3.842.57%208.258%208.258%200%2000-1.602.745c-1.075.695-1.823%201.674-2.24%202.932-.112.473-.29.927-.245%201.365.2%202.01%201.512%202.893%201.422%202.409-.117-.625-.042-.994.119-1.592.304-1.13%201.025-1.965%202.163-2.497h.004c.221-.062%201.344-.7%202.834.062.396.17%201.088.629%201.434.618.347-.01.846-.345%201.21-.572.683-.428%201.33-.574%202.184-.303%201.243.39%202.005%201.274%202.418%202.401z%22%3E%3C/path%3E%3Cpath%20d=%22M1.217%209.86l.934.274%201.071-.055.77-.522.825-.742.604-.825.77-.797.741-.467%201.016-.22-.687%201.209-.577.576-1.209%201.676-.549.825-.632.44-.907.604s-.797.165-.879.192c-.081.028-.741.138-.741.138l-.577-.028-.44-.137.412-.825.056-.604v-.714l-.001.002z%22%20fill-opacity=%22.5%22%3E%3C/path%3E%3Cpath%20d=%22M3.607%205.108l-.083.63-.22.441-.274.412-.688.412.825.412.907.357.934.193.412.028.99-.688%201.043-.934-.357-.11-1.29-.137-.963-.358-.687-.356-.55-.302z%22%20fill-opacity=%22.5%22%3E%3C/path%3E%3Cpath%20d=%22M1.521%2012.399c-.29%200-.596-.018-.917-.051L0%2012.278l.298-.19.159-.173c.022-.033.085-.144.19-.377v-.002c.17-.365.228-.975.177-1.813l-.036-.564.435.36c.454.376%201.024.466%201.74.272.64-.182%201.337-.78%202.068-1.774.673-.968%201.64-1.624%202.88-1.952l.116-.031.783.61-.704-.05a2.182%202.182%200%2000-.191.206l-.014.017-.018.016c-.404.718-.982%201.426-1.56%202.201l-.008.014c-.089.156-.18.317-.279.477v.009l-.032.051c-.592.962-1.243%201.683-1.935%202.145-.635.445-1.49.67-2.548.67v-.001zm-.5-.505c1.194.077%202.124-.112%202.77-.567l.005-.003c.626-.417%201.223-1.078%201.773-1.964a.244.244%200%2001.041-.074c.098-.159.19-.321.28-.48v-.001c.392-.75.842-1.417%201.343-1.988-.748.33-1.341.82-1.8%201.481l-.004.006c-.808%201.101-1.572%201.742-2.333%201.958-.673.182-1.263.15-1.764-.095.01.69-.068%201.207-.237%201.573-.026.058-.05.108-.072.153h-.002z%22%3E%3C/path%3E%3Cpath%20d=%22M1.577%2012.399c-.29%200-.596-.018-.917-.051l.05-.486c1.371.145%202.425-.035%203.136-.535l.006-.003c.626-.417%201.222-1.078%201.772-1.963a.277.277%200%2001.079-.116l.32.37a.22.22%200%2000.072-.141l-.005.058-.03.052c-.592.962-1.243%201.683-1.935%202.145-.636.445-1.49.67-2.548.67zM5.751%207.717a9.381%209.381%200%2001-.311.016c-.823.029-1.7-.2-2.615-.682.792-.512%201.013-1.096.982-1.621.189.15.386.281.591.393%201.345.758%202.766.878%205.195.198l-.165-.46c-2.308.637-3.558.532-4.793-.165a3.803%203.803%200%2001-.967-.759l-.033-.036-.5-.542.094.697c.014.058.3%201.417-1.01%202.08l-.398.201.383.228c1.073.638%202.114.96%203.094.96l.453-.507v-.001zM11.93%2015.21a.405.405%200%2001-.366-.253c-.326-.745-.582-1.055-.969-1.525-.39-.474-1.223-1.277-1.36-1.393-.184-.156-.236-.368-.126-.515.055-.072.219-.219.556.005.683.452%202.198%201.812%202.608%202.904.15.397%200%20.667-.201.749a.367.367%200%2001-.143.028h.001zM14.877%2015.23a.37.37%200%2001-.146-.03c-.201-.085-.346-.357-.192-.752.424-1.086%201.957-2.427%202.645-2.87.34-.22.502-.072.556.002.109.147.054.358-.131.512-.139.115-.982.905-1.379%201.376-.392.465-.651.772-.988%201.513a.404.404%200%2001-.364.25v-.002z%22%3E%3C/path%3E%3Cpath%20d=%22M16.382%203.316c.01-.566-.265-1.054-.827-1.462-.57-.4-1.252-.602-2.045-.608-.792-.006-1.471.189-2.031.587-.563.401-.85.884-.857%201.445.002.176.017.336.04.486%202.1-.676%203.981-.62%205.64.167.045-.21.072-.414.08-.616v.001z%22%20fill-opacity=%22.5%22%3E%3C/path%3E%3Cpath%20d=%22M7.6%2014.716l-.01-.024a1.824%201.824%200%2001-.072-.192l-.059-.189-.388.013-.03.326c.002.013.009.044.016.1v.011c.003.02.004.036.008.052a.555.555%200%2001-.164.431c-.112.12-.258.172-.45.164-.24-.01-.32-.105-.358-.176-.105-.19-.112-.291-.107-.336.015-.123.04-.254.077-.385.055-.206.013-.444-.126-.708l-.143-.272a1.787%201.787%200%2001-.14-.384.974.974%200%2001.022-.458.641.641%200%2001.264-.374.695.695%200%2001.496-.1l.015.002h.015c.192%200%20.349.02.469.051a2.208%202.208%200%2001-.027-.58%201.5%201.5%200%2000-.38-.107H6.52l-.095-.008a1.369%201.369%200%2000-.826.189c-.272.16-.456.394-.544.7a1.691%201.691%200%2000-.03.815c.008.041.017.09.033.136.043.135.113.285.21.446.148.243.193.323.205.35l.005.009c.018.033.022.084.01.15l-.005.023a7.4%207.4%200%2001-.034.172c-.115.298-.127.574-.036.815a.964.964%200%2000.486.558c.134.066.288.108.46.125.094.01.192.01.294.005a.957.957%200%2000.784-.454%201.13%201.13%200%2000.17-.87l-.004-.026H7.6zM21.925%2012.059a1.165%201.165%200%2000-.556-.697h-.001a1.325%201.325%200%2000-.797-.175l-.031.003-.093.011h-.008a1.553%201.553%200%2000-.528.197%201.959%201.959%200%2001-.016.563l.1-.04c.128-.053.302-.095.532-.13l.013-.002a.567.567%200%2001.474.103c.155.113.26.254.32.428.05.164.057.305.022.43a2.77%202.77%200%2001-.144.41%209.169%209.169%200%2001-.191.383.908.908%200%2000-.102.57c.024.176.05.322.078.446a.608.608%200%2001-.036.329l-.003.006c-.037.117-.235.18-.35.208-.263.063-.381-.033-.451-.12a.78.78%200%2001-.173-.51l.004-.053a.806.806%200%2001.014-.093l-.008-.337-.431.01-.046.185a1.285%201.285%200%2001-.064.188l-.011.027-.005.029c-.05.307.013.598.187.868l.004.006c.19.274.463.426.787.437.087.005.17.002.25-.004.192-.018.363-.069.509-.15a.992.992%200%2000.459-.567c.085-.252.068-.527-.05-.816l-.03-.171-.002-.013a.306.306%200%2001.015-.18c.045-.108.106-.233.181-.375.098-.173.162-.32.196-.444a.665.665%200%2000.033-.152%201.75%201.75%200%2000-.053-.806l.002-.002zM16.59%203.853c.033-.185.053-.359.06-.533.012-.648-.301-1.209-.93-1.667-.609-.427-1.344-.646-2.184-.653-.843-.008-1.575.207-2.176.633-.628.45-.951%201.002-.96%201.643v.006c.002.128.01.256.026.39a.38.38%200%2000-.095.23v.01c0%20.216.032.433.097.643l.001.006c.09.265.245.518.46.75l.063.068.567.063c.485.282%201.132.433%201.928.447h.103c.587%200%201.1-.072%201.527-.213l.011-.004c.16-.063.316-.138.465-.224.452.043.791-.18.965-.633l.043-.046-.002-.065c.067-.205.184-.608.03-.851h.001zM11.643%202.03c.514-.365%201.149-.547%201.888-.542.74.006%201.38.196%201.903.562.497.361.735.774.727%201.255-.004.089-.01.18-.023.274a6.882%206.882%200%2000-2.685-.527c-.816%200-1.67.13-2.558.39a4.038%204.038%200%2001-.006-.165c.006-.482.253-.89.754-1.247zm4.513%202.293l-.165.357s-.215.311-.45.272l-.092-.015-.078.049a2.724%202.724%200%2001-.454.226c-.397.13-.89.192-1.462.184-.708-.014-1.276-.14-1.688-.38l-.037-.021-.048-.03-.491-.054c-.094-.11-.226-.34-.226-.34l-.135-.392-.008-.204c1.988-.626%203.79-.574%205.355.155.002.029-.02.193-.02.193zm.147.364v-.004l.003.004h-.003z%22%3E%3C/path%3E%3C/svg%3E","dark":"data:image/svg+xml,%3Csvg%20fill=%22%230F766E%22%20fill-rule=%22evenodd%22%20height=%221em%22%20style=%22flex:none;line-height:1%22%20viewBox=%220%200%2024%2024%22%20width=%221em%22%20xmlns=%22http://www.w3.org/2000/svg%22%3E%3Ctitle%3EInternLM%3C/title%3E%3Cpath%20d=%22M5.54%2019.662s2.24-.25%202.365-.29c.125-.042%202.45.082%202.45.082l1.493.374%201.37.498.373.125%202.033-.748%202.45-.373%201.659.041%201.286.166.54.166-.042%202.242-1.12-.291-2.159-.166-1.494.124-1.286.291-1.161.374-.83.332-1.744-.664-2.116-.416H7.158l-1.618.291v-2.158z%22%20fill-opacity=%22.5%22%3E%3C/path%3E%3Cpath%20d=%22M13.46%2023c-3.773-2.078-7.78-.832-7.82-.819l-.453.144v-2.86l.24-.078c.174-.056%204.324-1.354%208.366.871l-.333.607c-3.244-1.786-6.66-1.115-7.58-.885V21.4c1.203-.286%204.595-.834%207.913.993L13.46%2023V23z%22%3E%3C/path%3E%3Cpath%20d=%22M13.413%2023l-.334-.607c3.319-1.827%206.71-1.279%207.914-.993v-1.419c-.92-.231-4.337-.9-7.58.885l-.334-.607c4.042-2.225%208.192-.927%208.366-.87l.24.077v2.862l-.452-.147c-.04-.013-4.046-1.258-7.82.819z%22%3E%3C/path%3E%3Cpath%20d=%22M17.756%2016.476a.904.904%200%2000-.264-.651.822.822%200%2000-.632-.255.997.997%200%2000-.644.293c-.175.212-.26.433-.259.685a.874.874%200%2000.256.632c.175.187.39.272.644.255.246%200%20.459-.1.633-.293a.97.97%200%2000.268-.667l-.002.001zM10.769%2017.143a.928.928%200%2000.264-.658.993.993%200%2000-.262-.679.908.908%200%2000-.633-.227%201.089%201.089%200%2000-.644.274%201.005%201.005%200%2000-.265.685c0%20.25.089.465.264.643.17.187.383.271.636.255.26-.008.471-.1.639-.293z%22%20fill-opacity=%22.5%22%3E%3C/path%3E%3Cpath%20d=%22M13.4%2019.65c-.693%200-1.374-.058-1.895-.192-1.403-.36-2.52-1.01-3.413-1.986-.929-1.017-.988-1.996-1.05-3.033-.008-.133-.016-.267-.026-.405-.083-1.147-.626-2.941-.631-2.958l-.043-.141.086-.119A6.966%206.966%200%20019.44%208.441c1.128-.47%202.47-.716%204.105-.752%202.721-.159%205.688.973%207.056%202.692l.086.109-.62%202.89c-.006.155-.052.968-.276%202.63-.263%201.947-2.668%203.061-3.903%203.377-.628.162-1.57.262-2.488.262zm-6.41-8.603c.134.46.538%201.912.613%202.944.01.139.018.277.026.412.06%201.01.109%201.809.896%202.672.815.89%201.837%201.484%203.125%201.814%201.092.28%203.061.194%204.091-.071.887-.228%203.24-1.19%203.468-2.889.24-1.786.272-2.593.273-2.6v-.026l.572-2.664c-.9-1.728-1.433-2.082-2.578-2.514-1.206-.455-2.677.075-3.903.148h-.01c-3.126.068-5.418-.935-6.574%202.773h.001z%22%3E%3C/path%3E%3Cpath%20d=%22M19.545%2010.862c.223.573.317.86.526%201.386%200%200%20.552-.887.727-1.522.175-.641.068-1.458-.07-2.221-.344-1.282-.612-1.381-1.647-2.14a8.668%208.668%200%2000-1.565-.84%2012.303%2012.303%200%2000-3.83-.8%2012.175%2012.175%200%2000-3.842.57%208.258%208.258%200%2000-1.602.745c-1.075.695-1.823%201.674-2.24%202.932-.112.473-.29.927-.245%201.365.2%202.01%201.512%202.893%201.422%202.409-.117-.625-.042-.994.119-1.592.304-1.13%201.025-1.965%202.163-2.497h.004c.221-.062%201.344-.7%202.834.062.396.17%201.088.629%201.434.618.347-.01.846-.345%201.21-.572.683-.428%201.33-.574%202.184-.303%201.243.39%202.005%201.274%202.418%202.401z%22%3E%3C/path%3E%3Cpath%20d=%22M1.217%209.86l.934.274%201.071-.055.77-.522.825-.742.604-.825.77-.797.741-.467%201.016-.22-.687%201.209-.577.576-1.209%201.676-.549.825-.632.44-.907.604s-.797.165-.879.192c-.081.028-.741.138-.741.138l-.577-.028-.44-.137.412-.825.056-.604v-.714l-.001.002z%22%20fill-opacity=%22.5%22%3E%3C/path%3E%3Cpath%20d=%22M3.607%205.108l-.083.63-.22.441-.274.412-.688.412.825.412.907.357.934.193.412.028.99-.688%201.043-.934-.357-.11-1.29-.137-.963-.358-.687-.356-.55-.302z%22%20fill-opacity=%22.5%22%3E%3C/path%3E%3Cpath%20d=%22M1.521%2012.399c-.29%200-.596-.018-.917-.051L0%2012.278l.298-.19.159-.173c.022-.033.085-.144.19-.377v-.002c.17-.365.228-.975.177-1.813l-.036-.564.435.36c.454.376%201.024.466%201.74.272.64-.182%201.337-.78%202.068-1.774.673-.968%201.64-1.624%202.88-1.952l.116-.031.783.61-.704-.05a2.182%202.182%200%2000-.191.206l-.014.017-.018.016c-.404.718-.982%201.426-1.56%202.201l-.008.014c-.089.156-.18.317-.279.477v.009l-.032.051c-.592.962-1.243%201.683-1.935%202.145-.635.445-1.49.67-2.548.67v-.001zm-.5-.505c1.194.077%202.124-.112%202.77-.567l.005-.003c.626-.417%201.223-1.078%201.773-1.964a.244.244%200%2001.041-.074c.098-.159.19-.321.28-.48v-.001c.392-.75.842-1.417%201.343-1.988-.748.33-1.341.82-1.8%201.481l-.004.006c-.808%201.101-1.572%201.742-2.333%201.958-.673.182-1.263.15-1.764-.095.01.69-.068%201.207-.237%201.573-.026.058-.05.108-.072.153h-.002z%22%3E%3C/path%3E%3Cpath%20d=%22M1.577%2012.399c-.29%200-.596-.018-.917-.051l.05-.486c1.371.145%202.425-.035%203.136-.535l.006-.003c.626-.417%201.222-1.078%201.772-1.963a.277.277%200%2001.079-.116l.32.37a.22.22%200%2000.072-.141l-.005.058-.03.052c-.592.962-1.243%201.683-1.935%202.145-.636.445-1.49.67-2.548.67zM5.751%207.717a9.381%209.381%200%2001-.311.016c-.823.029-1.7-.2-2.615-.682.792-.512%201.013-1.096.982-1.621.189.15.386.281.591.393%201.345.758%202.766.878%205.195.198l-.165-.46c-2.308.637-3.558.532-4.793-.165a3.803%203.803%200%2001-.967-.759l-.033-.036-.5-.542.094.697c.014.058.3%201.417-1.01%202.08l-.398.201.383.228c1.073.638%202.114.96%203.094.96l.453-.507v-.001zM11.93%2015.21a.405.405%200%2001-.366-.253c-.326-.745-.582-1.055-.969-1.525-.39-.474-1.223-1.277-1.36-1.393-.184-.156-.236-.368-.126-.515.055-.072.219-.219.556.005.683.452%202.198%201.812%202.608%202.904.15.397%200%20.667-.201.749a.367.367%200%2001-.143.028h.001zM14.877%2015.23a.37.37%200%2001-.146-.03c-.201-.085-.346-.357-.192-.752.424-1.086%201.957-2.427%202.645-2.87.34-.22.502-.072.556.002.109.147.054.358-.131.512-.139.115-.982.905-1.379%201.376-.392.465-.651.772-.988%201.513a.404.404%200%2001-.364.25v-.002z%22%3E%3C/path%3E%3Cpath%20d=%22M16.382%203.316c.01-.566-.265-1.054-.827-1.462-.57-.4-1.252-.602-2.045-.608-.792-.006-1.471.189-2.031.587-.563.401-.85.884-.857%201.445.002.176.017.336.04.486%202.1-.676%203.981-.62%205.64.167.045-.21.072-.414.08-.616v.001z%22%20fill-opacity=%22.5%22%3E%3C/path%3E%3Cpath%20d=%22M7.6%2014.716l-.01-.024a1.824%201.824%200%2001-.072-.192l-.059-.189-.388.013-.03.326c.002.013.009.044.016.1v.011c.003.02.004.036.008.052a.555.555%200%2001-.164.431c-.112.12-.258.172-.45.164-.24-.01-.32-.105-.358-.176-.105-.19-.112-.291-.107-.336.015-.123.04-.254.077-.385.055-.206.013-.444-.126-.708l-.143-.272a1.787%201.787%200%2001-.14-.384.974.974%200%2001.022-.458.641.641%200%2001.264-.374.695.695%200%2001.496-.1l.015.002h.015c.192%200%20.349.02.469.051a2.208%202.208%200%2001-.027-.58%201.5%201.5%200%2000-.38-.107H6.52l-.095-.008a1.369%201.369%200%2000-.826.189c-.272.16-.456.394-.544.7a1.691%201.691%200%2000-.03.815c.008.041.017.09.033.136.043.135.113.285.21.446.148.243.193.323.205.35l.005.009c.018.033.022.084.01.15l-.005.023a7.4%207.4%200%2001-.034.172c-.115.298-.127.574-.036.815a.964.964%200%2000.486.558c.134.066.288.108.46.125.094.01.192.01.294.005a.957.957%200%2000.784-.454%201.13%201.13%200%2000.17-.87l-.004-.026H7.6zM21.925%2012.059a1.165%201.165%200%2000-.556-.697h-.001a1.325%201.325%200%2000-.797-.175l-.031.003-.093.011h-.008a1.553%201.553%200%2000-.528.197%201.959%201.959%200%2001-.016.563l.1-.04c.128-.053.302-.095.532-.13l.013-.002a.567.567%200%2001.474.103c.155.113.26.254.32.428.05.164.057.305.022.43a2.77%202.77%200%2001-.144.41%209.169%209.169%200%2001-.191.383.908.908%200%2000-.102.57c.024.176.05.322.078.446a.608.608%200%2001-.036.329l-.003.006c-.037.117-.235.18-.35.208-.263.063-.381-.033-.451-.12a.78.78%200%2001-.173-.51l.004-.053a.806.806%200%2001.014-.093l-.008-.337-.431.01-.046.185a1.285%201.285%200%2001-.064.188l-.011.027-.005.029c-.05.307.013.598.187.868l.004.006c.19.274.463.426.787.437.087.005.17.002.25-.004.192-.018.363-.069.509-.15a.992.992%200%2000.459-.567c.085-.252.068-.527-.05-.816l-.03-.171-.002-.013a.306.306%200%2001.015-.18c.045-.108.106-.233.181-.375.098-.173.162-.32.196-.444a.665.665%200%2000.033-.152%201.75%201.75%200%2000-.053-.806l.002-.002zM16.59%203.853c.033-.185.053-.359.06-.533.012-.648-.301-1.209-.93-1.667-.609-.427-1.344-.646-2.184-.653-.843-.008-1.575.207-2.176.633-.628.45-.951%201.002-.96%201.643v.006c.002.128.01.256.026.39a.38.38%200%2000-.095.23v.01c0%20.216.032.433.097.643l.001.006c.09.265.245.518.46.75l.063.068.567.063c.485.282%201.132.433%201.928.447h.103c.587%200%201.1-.072%201.527-.213l.011-.004c.16-.063.316-.138.465-.224.452.043.791-.18.965-.633l.043-.046-.002-.065c.067-.205.184-.608.03-.851h.001zM11.643%202.03c.514-.365%201.149-.547%201.888-.542.74.006%201.38.196%201.903.562.497.361.735.774.727%201.255-.004.089-.01.18-.023.274a6.882%206.882%200%2000-2.685-.527c-.816%200-1.67.13-2.558.39a4.038%204.038%200%2001-.006-.165c.006-.482.253-.89.754-1.247zm4.513%202.293l-.165.357s-.215.311-.45.272l-.092-.015-.078.049a2.724%202.724%200%2001-.454.226c-.397.13-.89.192-1.462.184-.708-.014-1.276-.14-1.688-.38l-.037-.021-.048-.03-.491-.054c-.094-.11-.226-.34-.226-.34l-.135-.392-.008-.204c1.988-.626%203.79-.574%205.355.155.002.029-.02.193-.02.193zm.147.364v-.004l.003.004h-.003z%22%3E%3C/path%3E%3C/svg%3E"},"Tiangong":{"light":"data:image/svg+xml,%3Csvg%20fill=%22%234F46E5%22%20fill-rule=%22evenodd%22%20height=%221em%22%20style=%22flex:none;line-height:1%22%20viewBox=%220%200%2024%2024%22%20width=%221em%22%20xmlns=%22http://www.w3.org/2000/svg%22%3E%3Ctitle%3ETiangong%3C/title%3E%3Cpath%20d=%22M7.852%202.88H.647a.594.594%200%2001-.592-.592.592.592%200%2001.594-.588h7.205c1.49%200%202.96.474%204.157%201.335A7.196%207.196%200%200116.173%201.7h7.198a.592.592%200%2001.596.588.595.595%200%2001-.596.589h-7.198a5.944%205.944%200%2000-3.226.96c.355.357.671.754.938%201.18a5.647%205.647%200%20013.183-.987h6.303a.594.594%200%2001.596.588.595.595%200%2001-.596.589h-6.303c-.956%200-1.894.308-2.654.869.194.472.332.963.417%201.467a3.99%203.99%200%20012.898-1.238h5.642a.592.592%200%2001.55.815.594.594%200%2001-.55.362h-5.63a2.79%202.79%200%2000-2.804%202.764v3.511c.004%201.522%201.262%202.763%202.804%202.764h5.685l.02.002a.592.592%200%2001.553.626.592.592%200%2001-.592.547H17.74c-2.197-.004-3.988-1.769-3.99-3.937V8.702c-.006-3.207-2.65-5.817-5.899-5.821z%22%3E%3C/path%3E%3Cpath%20d=%22M.647%205.203h6.31c2.445%200%204.434%201.967%204.432%204.38v4.838c0%203.06%202.524%205.552%205.628%205.552h6.31a.592.592%200%2000.597-.586.59.59%200%2000-.596-.589h-6.323a4.428%204.428%200%2001-4.094-2.7%204.325%204.325%200%2001-.335-1.68V9.584c0-3.055-2.52-5.549-5.618-5.555H.647a.592.592%200%2000-.594.589.592.592%200%2000.594.586z%22%3E%3C/path%3E%3Cpath%20d=%22M23.361%2021.116h.063a.531.531%200%2001.417.208.587.587%200%2001-.448.973l-.02-.002h-7.21a7.159%207.159%200%2001-4.158-1.333%207.212%207.212%200%2001-4.162%201.333H.606l-.02-.002H.568a.588.588%200%2001.04-1.175l.02.002H7.84a5.937%205.937%200%20003.234-.957%207.033%207.033%200%2001-.94-1.181%205.609%205.609%200%2001-3.181.987H.644a.593.593%200%2001-.597-.588.592.592%200%2001.596-.587h6.32c.951%200%201.877-.304%202.643-.867a6.886%206.886%200%2001-.415-1.465%204.003%204.003%200%2001-2.902%201.234H.592a.589.589%200%2001.02-1.177l.02.003h5.65c1.543-.002%202.8-1.244%202.803-2.765v-3.509c-.002-1.524-1.258-2.764-2.802-2.764H.645a.592.592%200%2001-.596-.589.592.592%200%2001.596-.588h5.638c2.195.004%203.988%201.771%203.99%203.937V15.3c.002%203.209%202.648%205.821%205.899%205.825h7.142l.047-.008z%22%3E%3C/path%3E%3C/svg%3E","dark":"data:image/svg+xml,%3Csvg%20fill=%22%234F46E5%22%20fill-rule=%22evenodd%22%20height=%221em%22%20style=%22flex:none;line-height:1%22%20viewBox=%220%200%2024%2024%22%20width=%221em%22%20xmlns=%22http://www.w3.org/2000/svg%22%3E%3Ctitle%3ETiangong%3C/title%3E%3Cpath%20d=%22M7.852%202.88H.647a.594.594%200%2001-.592-.592.592.592%200%2001.594-.588h7.205c1.49%200%202.96.474%204.157%201.335A7.196%207.196%200%200116.173%201.7h7.198a.592.592%200%2001.596.588.595.595%200%2001-.596.589h-7.198a5.944%205.944%200%2000-3.226.96c.355.357.671.754.938%201.18a5.647%205.647%200%20013.183-.987h6.303a.594.594%200%2001.596.588.595.595%200%2001-.596.589h-6.303c-.956%200-1.894.308-2.654.869.194.472.332.963.417%201.467a3.99%203.99%200%20012.898-1.238h5.642a.592.592%200%2001.55.815.594.594%200%2001-.55.362h-5.63a2.79%202.79%200%2000-2.804%202.764v3.511c.004%201.522%201.262%202.763%202.804%202.764h5.685l.02.002a.592.592%200%2001.553.626.592.592%200%2001-.592.547H17.74c-2.197-.004-3.988-1.769-3.99-3.937V8.702c-.006-3.207-2.65-5.817-5.899-5.821z%22%3E%3C/path%3E%3Cpath%20d=%22M.647%205.203h6.31c2.445%200%204.434%201.967%204.432%204.38v4.838c0%203.06%202.524%205.552%205.628%205.552h6.31a.592.592%200%2000.597-.586.59.59%200%2000-.596-.589h-6.323a4.428%204.428%200%2001-4.094-2.7%204.325%204.325%200%2001-.335-1.68V9.584c0-3.055-2.52-5.549-5.618-5.555H.647a.592.592%200%2000-.594.589.592.592%200%2000.594.586z%22%3E%3C/path%3E%3Cpath%20d=%22M23.361%2021.116h.063a.531.531%200%2001.417.208.587.587%200%2001-.448.973l-.02-.002h-7.21a7.159%207.159%200%2001-4.158-1.333%207.212%207.212%200%2001-4.162%201.333H.606l-.02-.002H.568a.588.588%200%2001.04-1.175l.02.002H7.84a5.937%205.937%200%20003.234-.957%207.033%207.033%200%2001-.94-1.181%205.609%205.609%200%2001-3.181.987H.644a.593.593%200%2001-.597-.588.592.592%200%2001.596-.587h6.32c.951%200%201.877-.304%202.643-.867a6.886%206.886%200%2001-.415-1.465%204.003%204.003%200%2001-2.902%201.234H.592a.589.589%200%2001.02-1.177l.02.003h5.65c1.543-.002%202.8-1.244%202.803-2.765v-3.509c-.002-1.524-1.258-2.764-2.802-2.764H.645a.592.592%200%2001-.596-.589.592.592%200%2001.596-.588h5.638c2.195.004%203.988%201.771%203.99%203.937V15.3c.002%203.209%202.648%205.821%205.899%205.825h7.142l.047-.008z%22%3E%3C/path%3E%3C/svg%3E"},"SenseNova":{"light":"data:image/svg+xml,%3Csvg%20fill=%22%236254E8%22%20fill-rule=%22evenodd%22%20height=%221em%22%20style=%22flex:none;line-height:1%22%20viewBox=%220%200%2024%2024%22%20width=%221em%22%20xmlns=%22http://www.w3.org/2000/svg%22%3E%3Ctitle%3ESenseNova%3C/title%3E%3Cpath%20d=%22M23%208.333h-7.333v7.334H23V8.333z%22%3E%3C/path%3E%3Cpath%20d=%22M1%201v14.667h7.333V8.333h7.334V1H1z%22%20fill-opacity=%22.33%22%3E%3C/path%3E%3Cpath%20d=%22M14.038%204.333h.17l1.459%201.456v.17l-1.63-1.626zM13.224%204.333h.17l2.273%202.268v.17l-2.443-2.438zM12.41%204.333h.17l3.087%203.08v.17l-3.257-3.25zM11.596%204.333h.17l3.9%203.892v.108h-.06l-4.01-4zM10.782%204.333h.17l4.01%204h-.17l-4.01-4zM9.968%204.333h.17l4.009%204h-.17l-4.01-4zM9.154%204.333h.17l4.009%204h-.17l-4.01-4zM8.34%204.333h.17l4.01%204h-.17l-4.01-4zM7.521%204.333h.17l4.01%204h-.17l-4.01-4zM6.707%204.333h.17l4.01%204h-.17l-4.01-4zM5.892%204.333h.17l4.009%204h-.17l-4.01-4zM5.077%204.333h.17l4.01%204h-.17l-4.01-4zM4.333%204.403v-.07h.1l4.01%204h-.11v.06l-4-3.99zM4.333%205.215v-.17l4%203.991v.17l-4-3.99zM4.333%206.027v-.17l4%203.991v.17l-4-3.99zM4.333%206.84v-.17l4%203.99v.17l-4-3.99zM4.333%207.652v-.17l4%203.99v.17l-4-3.99zM4.333%208.464v-.17l4%203.99v.17l-4-3.99zM4.333%209.276v-.17l4%203.991v.17l-4-3.991zM4.333%2010.088v-.17l4%203.991v.17l-4-3.991zM4.333%2010.9v-.17l4%203.991v.17l-4-3.991zM4.333%2011.712v-.17l4%203.991v.134h-.036l-3.964-3.955zM4.333%2012.526v-.17l3.318%203.31h-.17l-3.148-3.14zM4.333%2013.34v-.169l2.502%202.496h-.17L4.333%2013.34zM4.333%2014.152v-.169l1.688%201.684h-.17l-1.518-1.514zM4.333%2014.965v-.17l.874.872h-.17l-.704-.702zM15.667%205.146l-.815-.813h.17l.645.644v.169z%22%3E%3C/path%3E%3Cpath%20d=%22M23%2015.667h-7.333V23H23v-7.333z%22%20fill-opacity=%22.33%22%3E%3C/path%3E%3Cpath%20d=%22M15.667%2015.667H8.333V23h7.334v-7.333z%22%3E%3C/path%3E%3C/svg%3E","dark":"data:image/svg+xml,%3Csvg%20fill=%22%236254E8%22%20fill-rule=%22evenodd%22%20height=%221em%22%20style=%22flex:none;line-height:1%22%20viewBox=%220%200%2024%2024%22%20width=%221em%22%20xmlns=%22http://www.w3.org/2000/svg%22%3E%3Ctitle%3ESenseNova%3C/title%3E%3Cpath%20d=%22M23%208.333h-7.333v7.334H23V8.333z%22%3E%3C/path%3E%3Cpath%20d=%22M1%201v14.667h7.333V8.333h7.334V1H1z%22%20fill-opacity=%22.33%22%3E%3C/path%3E%3Cpath%20d=%22M14.038%204.333h.17l1.459%201.456v.17l-1.63-1.626zM13.224%204.333h.17l2.273%202.268v.17l-2.443-2.438zM12.41%204.333h.17l3.087%203.08v.17l-3.257-3.25zM11.596%204.333h.17l3.9%203.892v.108h-.06l-4.01-4zM10.782%204.333h.17l4.01%204h-.17l-4.01-4zM9.968%204.333h.17l4.009%204h-.17l-4.01-4zM9.154%204.333h.17l4.009%204h-.17l-4.01-4zM8.34%204.333h.17l4.01%204h-.17l-4.01-4zM7.521%204.333h.17l4.01%204h-.17l-4.01-4zM6.707%204.333h.17l4.01%204h-.17l-4.01-4zM5.892%204.333h.17l4.009%204h-.17l-4.01-4zM5.077%204.333h.17l4.01%204h-.17l-4.01-4zM4.333%204.403v-.07h.1l4.01%204h-.11v.06l-4-3.99zM4.333%205.215v-.17l4%203.991v.17l-4-3.99zM4.333%206.027v-.17l4%203.991v.17l-4-3.99zM4.333%206.84v-.17l4%203.99v.17l-4-3.99zM4.333%207.652v-.17l4%203.99v.17l-4-3.99zM4.333%208.464v-.17l4%203.99v.17l-4-3.99zM4.333%209.276v-.17l4%203.991v.17l-4-3.991zM4.333%2010.088v-.17l4%203.991v.17l-4-3.991zM4.333%2010.9v-.17l4%203.991v.17l-4-3.991zM4.333%2011.712v-.17l4%203.991v.134h-.036l-3.964-3.955zM4.333%2012.526v-.17l3.318%203.31h-.17l-3.148-3.14zM4.333%2013.34v-.169l2.502%202.496h-.17L4.333%2013.34zM4.333%2014.152v-.169l1.688%201.684h-.17l-1.518-1.514zM4.333%2014.965v-.17l.874.872h-.17l-.704-.702zM15.667%205.146l-.815-.813h.17l.645.644v.169z%22%3E%3C/path%3E%3Cpath%20d=%22M23%2015.667h-7.333V23H23v-7.333z%22%20fill-opacity=%22.33%22%3E%3C/path%3E%3Cpath%20d=%22M15.667%2015.667H8.333V23h7.334v-7.333z%22%3E%3C/path%3E%3C/svg%3E"},"Mistral":{"light":"data:image/svg+xml,%3Csvg%20fill=%22%23F97316%22%20fill-rule=%22evenodd%22%20height=%221em%22%20style=%22flex:none;line-height:1%22%20viewBox=%220%200%2024%2024%22%20width=%221em%22%20xmlns=%22http://www.w3.org/2000/svg%22%3E%3Ctitle%3EMistral%3C/title%3E%3Cpath%20clip-rule=%22evenodd%22%20d=%22M3.428%203.4h3.429v3.428h3.429v3.429h-.002%203.431V6.828h3.427V3.4h3.43v13.714H24v3.429H13.714v-3.428h-3.428v-3.429h-3.43v3.428h3.43v3.429H0v-3.429h3.428V3.4zm10.286%2013.715h3.428v-3.429h-3.427v3.429z%22%3E%3C/path%3E%3C/svg%3E","dark":"data:image/svg+xml,%3Csvg%20fill=%22%23F97316%22%20fill-rule=%22evenodd%22%20height=%221em%22%20style=%22flex:none;line-height:1%22%20viewBox=%220%200%2024%2024%22%20width=%221em%22%20xmlns=%22http://www.w3.org/2000/svg%22%3E%3Ctitle%3EMistral%3C/title%3E%3Cpath%20clip-rule=%22evenodd%22%20d=%22M3.428%203.4h3.429v3.428h3.429v3.429h-.002%203.431V6.828h3.427V3.4h3.43v13.714H24v3.429H13.714v-3.428h-3.428v-3.429h-3.43v3.428h3.43v3.429H0v-3.429h3.428V3.4zm10.286%2013.715h3.428v-3.429h-3.427v3.429z%22%3E%3C/path%3E%3C/svg%3E"},"Meta":{"light":"data:image/svg+xml,%3Csvg%20fill=%22%230866FF%22%20fill-rule=%22evenodd%22%20height=%221em%22%20style=%22flex:none;line-height:1%22%20viewBox=%220%200%2024%2024%22%20width=%221em%22%20xmlns=%22http://www.w3.org/2000/svg%22%3E%3Ctitle%3EMeta%3C/title%3E%3Cpath%20d=%22M6.897%204c1.915%200%203.516.932%205.43%203.376l.282-.373c.19-.246.383-.484.58-.71l.313-.35C14.588%204.788%2015.792%204%2017.225%204c1.273%200%202.469.557%203.491%201.516l.218.213c1.73%201.765%202.917%204.71%203.053%208.026l.011.392.002.25c0%201.501-.28%202.759-.818%203.7l-.14.23-.108.153c-.301.42-.664.758-1.086%201.009l-.265.142-.087.04a3.493%203.493%200%2001-.302.118%204.117%204.117%200%2001-1.33.208c-.524%200-.996-.067-1.438-.215-.614-.204-1.163-.56-1.726-1.116l-.227-.235c-.753-.812-1.534-1.976-2.493-3.586l-1.43-2.41-.544-.895-1.766%203.13-.343.592C7.597%2019.156%206.227%2020%204.356%2020c-1.21%200-2.205-.42-2.936-1.182l-.168-.184c-.484-.573-.837-1.311-1.043-2.189l-.067-.32a8.69%208.69%200%2001-.136-1.288L0%2014.468c.002-.745.06-1.49.174-2.23l.1-.573c.298-1.53.828-2.958%201.536-4.157l.209-.34c1.177-1.83%202.789-3.053%204.615-3.16L6.897%204zm-.033%202.615l-.201.01c-.83.083-1.606.673-2.252%201.577l-.138.199-.01.018c-.67%201.017-1.185%202.378-1.456%203.845l-.004.022a12.591%2012.591%200%2000-.207%202.254l.002.188c.004.18.017.36.04.54l.043.291c.092.503.257.908.486%201.208l.117.137c.303.323.698.492%201.17.492%201.1%200%201.796-.676%203.696-3.641l2.175-3.4.454-.701-.139-.198C9.11%207.3%208.084%206.616%206.864%206.616zm10.196-.552l-.176.007c-.635.048-1.223.359-1.82.933l-.196.198c-.439.462-.887%201.064-1.367%201.807l.266.398c.18.274.362.56.55.858l.293.475%201.396%202.335.695%201.114c.583.926%201.03%201.6%201.408%202.082l.213.262c.282.326.529.54.777.673l.102.05c.227.1.457.138.718.138.176.002.35-.023.518-.073.338-.104.61-.32.813-.637l.095-.163.077-.162c.194-.459.29-1.06.29-1.785l-.006-.449c-.08-2.871-.938-5.372-2.2-6.798l-.176-.189c-.67-.683-1.444-1.074-2.27-1.074z%22%3E%3C/path%3E%3C/svg%3E","dark":"data:image/svg+xml,%3Csvg%20fill=%22%230866FF%22%20fill-rule=%22evenodd%22%20height=%221em%22%20style=%22flex:none;line-height:1%22%20viewBox=%220%200%2024%2024%22%20width=%221em%22%20xmlns=%22http://www.w3.org/2000/svg%22%3E%3Ctitle%3EMeta%3C/title%3E%3Cpath%20d=%22M6.897%204c1.915%200%203.516.932%205.43%203.376l.282-.373c.19-.246.383-.484.58-.71l.313-.35C14.588%204.788%2015.792%204%2017.225%204c1.273%200%202.469.557%203.491%201.516l.218.213c1.73%201.765%202.917%204.71%203.053%208.026l.011.392.002.25c0%201.501-.28%202.759-.818%203.7l-.14.23-.108.153c-.301.42-.664.758-1.086%201.009l-.265.142-.087.04a3.493%203.493%200%2001-.302.118%204.117%204.117%200%2001-1.33.208c-.524%200-.996-.067-1.438-.215-.614-.204-1.163-.56-1.726-1.116l-.227-.235c-.753-.812-1.534-1.976-2.493-3.586l-1.43-2.41-.544-.895-1.766%203.13-.343.592C7.597%2019.156%206.227%2020%204.356%2020c-1.21%200-2.205-.42-2.936-1.182l-.168-.184c-.484-.573-.837-1.311-1.043-2.189l-.067-.32a8.69%208.69%200%2001-.136-1.288L0%2014.468c.002-.745.06-1.49.174-2.23l.1-.573c.298-1.53.828-2.958%201.536-4.157l.209-.34c1.177-1.83%202.789-3.053%204.615-3.16L6.897%204zm-.033%202.615l-.201.01c-.83.083-1.606.673-2.252%201.577l-.138.199-.01.018c-.67%201.017-1.185%202.378-1.456%203.845l-.004.022a12.591%2012.591%200%2000-.207%202.254l.002.188c.004.18.017.36.04.54l.043.291c.092.503.257.908.486%201.208l.117.137c.303.323.698.492%201.17.492%201.1%200%201.796-.676%203.696-3.641l2.175-3.4.454-.701-.139-.198C9.11%207.3%208.084%206.616%206.864%206.616zm10.196-.552l-.176.007c-.635.048-1.223.359-1.82.933l-.196.198c-.439.462-.887%201.064-1.367%201.807l.266.398c.18.274.362.56.55.858l.293.475%201.396%202.335.695%201.114c.583.926%201.03%201.6%201.408%202.082l.213.262c.282.326.529.54.777.673l.102.05c.227.1.457.138.718.138.176.002.35-.023.518-.073.338-.104.61-.32.813-.637l.095-.163.077-.162c.194-.459.29-1.06.29-1.785l-.006-.449c-.08-2.871-.938-5.372-2.2-6.798l-.176-.189c-.67-.683-1.444-1.074-2.27-1.074z%22%3E%3C/path%3E%3C/svg%3E"},"Cohere":{"light":"data:image/svg+xml,%3Csvg%20fill=%22%2339594D%22%20fill-rule=%22evenodd%22%20height=%221em%22%20style=%22flex:none;line-height:1%22%20viewBox=%220%200%2024%2024%22%20width=%221em%22%20xmlns=%22http://www.w3.org/2000/svg%22%3E%3Ctitle%3ECohere%3C/title%3E%3Cpath%20clip-rule=%22evenodd%22%20d=%22M8.128%2014.099c.592%200%201.77-.033%203.398-.703%201.897-.781%205.672-2.2%208.395-3.656%201.905-1.018%202.74-2.366%202.74-4.18A4.56%204.56%200%200018.1%201H7.549A6.55%206.55%200%20001%207.55c0%203.617%202.745%206.549%207.128%206.549z%22%3E%3C/path%3E%3Cpath%20clip-rule=%22evenodd%22%20d=%22M9.912%2018.61a4.387%204.387%200%20012.705-4.052l3.323-1.38c3.361-1.394%207.06%201.076%207.06%204.715a5.104%205.104%200%2001-5.105%205.104l-3.597-.001a4.386%204.386%200%2001-4.386-4.387z%22%3E%3C/path%3E%3Cpath%20d=%22M4.776%2014.962A3.775%203.775%200%20001%2018.738v.489a3.776%203.776%200%20007.551%200v-.49a3.775%203.775%200%2000-3.775-3.775z%22%3E%3C/path%3E%3C/svg%3E","dark":"data:image/svg+xml,%3Csvg%20fill=%22%2339594D%22%20fill-rule=%22evenodd%22%20height=%221em%22%20style=%22flex:none;line-height:1%22%20viewBox=%220%200%2024%2024%22%20width=%221em%22%20xmlns=%22http://www.w3.org/2000/svg%22%3E%3Ctitle%3ECohere%3C/title%3E%3Cpath%20clip-rule=%22evenodd%22%20d=%22M8.128%2014.099c.592%200%201.77-.033%203.398-.703%201.897-.781%205.672-2.2%208.395-3.656%201.905-1.018%202.74-2.366%202.74-4.18A4.56%204.56%200%200018.1%201H7.549A6.55%206.55%200%20001%207.55c0%203.617%202.745%206.549%207.128%206.549z%22%3E%3C/path%3E%3Cpath%20clip-rule=%22evenodd%22%20d=%22M9.912%2018.61a4.387%204.387%200%20012.705-4.052l3.323-1.38c3.361-1.394%207.06%201.076%207.06%204.715a5.104%205.104%200%2001-5.105%205.104l-3.597-.001a4.386%204.386%200%2001-4.386-4.387z%22%3E%3C/path%3E%3Cpath%20d=%22M4.776%2014.962A3.775%203.775%200%20001%2018.738v.489a3.776%203.776%200%20007.551%200v-.49a3.775%203.775%200%2000-3.775-3.775z%22%3E%3C/path%3E%3C/svg%3E"},"Nvidia":{"light":"data:image/svg+xml,%3Csvg%20fill=%22%2376B900%22%20fill-rule=%22evenodd%22%20height=%221em%22%20style=%22flex:none;line-height:1%22%20viewBox=%220%200%2024%2024%22%20width=%221em%22%20xmlns=%22http://www.w3.org/2000/svg%22%3E%3Ctitle%3ENvidia%3C/title%3E%3Cpath%20d=%22M10.212%208.976V7.62c.127-.01.256-.017.388-.021%203.596-.117%205.957%203.184%205.957%203.184s-2.548%203.647-5.282%203.647a3.227%203.227%200%2001-1.063-.175v-4.109c1.4.174%201.681.812%202.523%202.258l1.873-1.627a4.905%204.905%200%2000-3.67-1.846%206.594%206.594%200%2000-.729.044m0-4.476v2.025c.13-.01.259-.019.388-.024%205.002-.174%208.261%204.226%208.261%204.226s-3.743%204.69-7.643%204.69c-.338%200-.675-.031-1.007-.092v1.25c.278.038.558.057.838.057%203.629%200%206.253-1.91%208.794-4.169.421.347%202.146%201.193%202.501%201.564-2.416%202.083-8.048%203.763-11.24%203.763-.308%200-.603-.02-.894-.048V19.5H24v-15H10.21zm0%209.756v1.068c-3.356-.616-4.287-4.21-4.287-4.21a7.173%207.173%200%20014.287-2.138v1.172h-.005a3.182%203.182%200%2000-2.502%201.178s.615%202.276%202.507%202.931m-5.961-3.3c1.436-1.935%203.604-3.148%205.961-3.336V6.523C5.81%206.887%202%2010.723%202%2010.723s2.158%206.427%208.21%207.015v-1.166C5.77%2016%204.25%2010.958%204.25%2010.958h-.002z%22%3E%3C/path%3E%3C/svg%3E","dark":"data:image/svg+xml,%3Csvg%20fill=%22%2376B900%22%20fill-rule=%22evenodd%22%20height=%221em%22%20style=%22flex:none;line-height:1%22%20viewBox=%220%200%2024%2024%22%20width=%221em%22%20xmlns=%22http://www.w3.org/2000/svg%22%3E%3Ctitle%3ENvidia%3C/title%3E%3Cpath%20d=%22M10.212%208.976V7.62c.127-.01.256-.017.388-.021%203.596-.117%205.957%203.184%205.957%203.184s-2.548%203.647-5.282%203.647a3.227%203.227%200%2001-1.063-.175v-4.109c1.4.174%201.681.812%202.523%202.258l1.873-1.627a4.905%204.905%200%2000-3.67-1.846%206.594%206.594%200%2000-.729.044m0-4.476v2.025c.13-.01.259-.019.388-.024%205.002-.174%208.261%204.226%208.261%204.226s-3.743%204.69-7.643%204.69c-.338%200-.675-.031-1.007-.092v1.25c.278.038.558.057.838.057%203.629%200%206.253-1.91%208.794-4.169.421.347%202.146%201.193%202.501%201.564-2.416%202.083-8.048%203.763-11.24%203.763-.308%200-.603-.02-.894-.048V19.5H24v-15H10.21zm0%209.756v1.068c-3.356-.616-4.287-4.21-4.287-4.21a7.173%207.173%200%20014.287-2.138v1.172h-.005a3.182%203.182%200%2000-2.502%201.178s.615%202.276%202.507%202.931m-5.961-3.3c1.436-1.935%203.604-3.148%205.961-3.336V6.523C5.81%206.887%202%2010.723%202%2010.723s2.158%206.427%208.21%207.015v-1.166C5.77%2016%204.25%2010.958%204.25%2010.958h-.002z%22%3E%3C/path%3E%3C/svg%3E"},"Perplexity":{"light":"data:image/svg+xml,%3Csvg%20fill=%22%2320B8A9%22%20fill-rule=%22evenodd%22%20height=%221em%22%20style=%22flex:none;line-height:1%22%20viewBox=%220%200%2024%2024%22%20width=%221em%22%20xmlns=%22http://www.w3.org/2000/svg%22%3E%3Ctitle%3EPerplexity%3C/title%3E%3Cpath%20d=%22M19.785%200v7.272H22.5V17.62h-2.935V24l-7.037-6.194v6.145h-1.091v-6.152L4.392%2024v-6.465H1.5V7.188h2.884V0l7.053%206.494V.19h1.09v6.49L19.786%200zm-7.257%209.044v7.319l5.946%205.234V14.44l-5.946-5.397zm-1.099-.08l-5.946%205.398v7.235l5.946-5.234V8.965zm8.136%207.58h1.844V8.349H13.46l6.105%205.54v2.655zm-8.982-8.28H2.59v8.195h1.8v-2.576l6.192-5.62zM5.475%202.476v4.71h5.115l-5.115-4.71zm13.219%200l-5.115%204.71h5.115v-4.71z%22%3E%3C/path%3E%3C/svg%3E","dark":"data:image/svg+xml,%3Csvg%20fill=%22%2320B8A9%22%20fill-rule=%22evenodd%22%20height=%221em%22%20style=%22flex:none;line-height:1%22%20viewBox=%220%200%2024%2024%22%20width=%221em%22%20xmlns=%22http://www.w3.org/2000/svg%22%3E%3Ctitle%3EPerplexity%3C/title%3E%3Cpath%20d=%22M19.785%200v7.272H22.5V17.62h-2.935V24l-7.037-6.194v6.145h-1.091v-6.152L4.392%2024v-6.465H1.5V7.188h2.884V0l7.053%206.494V.19h1.09v6.49L19.786%200zm-7.257%209.044v7.319l5.946%205.234V14.44l-5.946-5.397zm-1.099-.08l-5.946%205.398v7.235l5.946-5.234V8.965zm8.136%207.58h1.844V8.349H13.46l6.105%205.54v2.655zm-8.982-8.28H2.59v8.195h1.8v-2.576l6.192-5.62zM5.475%202.476v4.71h5.115l-5.115-4.71zm13.219%200l-5.115%204.71h5.115v-4.71z%22%3E%3C/path%3E%3C/svg%3E"},"Groq":{"light":"data:image/svg+xml,%3Csvg%20fill=%22%23F55036%22%20fill-rule=%22evenodd%22%20height=%221em%22%20style=%22flex:none;line-height:1%22%20viewBox=%220%200%2024%2024%22%20width=%221em%22%20xmlns=%22http://www.w3.org/2000/svg%22%3E%3Ctitle%3EGroq%3C/title%3E%3Cpath%20d=%22M12.036%202c-3.853-.035-7%203-7.036%206.781-.035%203.782%203.055%206.872%206.908%206.907h2.42v-2.566h-2.292c-2.407.028-4.38-1.866-4.408-4.23-.029-2.362%201.901-4.298%204.308-4.326h.1c2.407%200%204.358%201.915%204.365%204.278v6.305c0%202.342-1.944%204.25-4.323%204.279a4.375%204.375%200%2001-3.033-1.252l-1.851%201.818A7%207%200%200012.029%2022h.092c3.803-.056%206.858-3.083%206.879-6.816v-6.5C18.907%204.963%2015.817%202%2012.036%202z%22%3E%3C/path%3E%3C/svg%3E","dark":"data:image/svg+xml,%3Csvg%20fill=%22%23F55036%22%20fill-rule=%22evenodd%22%20height=%221em%22%20style=%22flex:none;line-height:1%22%20viewBox=%220%200%2024%2024%22%20width=%221em%22%20xmlns=%22http://www.w3.org/2000/svg%22%3E%3Ctitle%3EGroq%3C/title%3E%3Cpath%20d=%22M12.036%202c-3.853-.035-7%203-7.036%206.781-.035%203.782%203.055%206.872%206.908%206.907h2.42v-2.566h-2.292c-2.407.028-4.38-1.866-4.408-4.23-.029-2.362%201.901-4.298%204.308-4.326h.1c2.407%200%204.358%201.915%204.365%204.278v6.305c0%202.342-1.944%204.25-4.323%204.279a4.375%204.375%200%2001-3.033-1.252l-1.851%201.818A7%207%200%200012.029%2022h.092c3.803-.056%206.858-3.083%206.879-6.816v-6.5C18.907%204.963%2015.817%202%2012.036%202z%22%3E%3C/path%3E%3C/svg%3E"},"OpenRouter":{"light":"data:image/svg+xml,%3Csvg%20fill=%22%236366F1%22%20fill-rule=%22evenodd%22%20height=%221em%22%20style=%22flex:none;line-height:1%22%20viewBox=%220%200%2024%2024%22%20width=%221em%22%20xmlns=%22http://www.w3.org/2000/svg%22%3E%3Ctitle%3EOpenRouter%3C/title%3E%3Cpath%20d=%22M18.654%203.87a5.087%205.087%200%20110%2010.174L23.7%2019.09c.64.641.187%201.737-.72%201.737H8.48a8.479%208.479%200%20010-16.958h10.175zM8.479%207.26a5.087%205.087%200%20100%2010.176%205.087%205.087%200%20000-10.175z%22%3E%3C/path%3E%3C/svg%3E","dark":"data:image/svg+xml,%3Csvg%20fill=%22%236366F1%22%20fill-rule=%22evenodd%22%20height=%221em%22%20style=%22flex:none;line-height:1%22%20viewBox=%220%200%2024%2024%22%20width=%221em%22%20xmlns=%22http://www.w3.org/2000/svg%22%3E%3Ctitle%3EOpenRouter%3C/title%3E%3Cpath%20d=%22M18.654%203.87a5.087%205.087%200%20110%2010.174L23.7%2019.09c.64.641.187%201.737-.72%201.737H8.48a8.479%208.479%200%20010-16.958h10.175zM8.479%207.26a5.087%205.087%200%20100%2010.176%205.087%205.087%200%20000-10.175z%22%3E%3C/path%3E%3C/svg%3E"},"SiliconFlow":{"light":"data:image/svg+xml,%3Csvg%20fill=%22%23615CED%22%20fill-rule=%22evenodd%22%20height=%221em%22%20style=%22flex:none;line-height:1%22%20viewBox=%220%200%2024%2024%22%20width=%221em%22%20xmlns=%22http://www.w3.org/2000/svg%22%3E%3Ctitle%3ESiliconCloud%3C/title%3E%3Cpath%20clip-rule=%22evenodd%22%20d=%22M22.956%206.521H12.522c-.577%200-1.044.468-1.044%201.044v3.13c0%20.577-.466%201.044-1.043%201.044H1.044c-.577%200-1.044.467-1.044%201.044v4.174C0%2017.533.467%2018%201.044%2018h10.434c.577%200%201.044-.467%201.044-1.043v-3.13c0-.578.466-1.044%201.043-1.044h9.391c.577%200%201.044-.467%201.044-1.044V7.565c0-.576-.467-1.044-1.044-1.044z%22%3E%3C/path%3E%3C/svg%3E","dark":"data:image/svg+xml,%3Csvg%20fill=%22%23615CED%22%20fill-rule=%22evenodd%22%20height=%221em%22%20style=%22flex:none;line-height:1%22%20viewBox=%220%200%2024%2024%22%20width=%221em%22%20xmlns=%22http://www.w3.org/2000/svg%22%3E%3Ctitle%3ESiliconCloud%3C/title%3E%3Cpath%20clip-rule=%22evenodd%22%20d=%22M22.956%206.521H12.522c-.577%200-1.044.468-1.044%201.044v3.13c0%20.577-.466%201.044-1.043%201.044H1.044c-.577%200-1.044.467-1.044%201.044v4.174C0%2017.533.467%2018%201.044%2018h10.434c.577%200%201.044-.467%201.044-1.043v-3.13c0-.578.466-1.044%201.043-1.044h9.391c.577%200%201.044-.467%201.044-1.044V7.565c0-.576-.467-1.044-1.044-1.044z%22%3E%3C/path%3E%3C/svg%3E"},"ModelScope":{"light":"data:image/svg+xml,%3Csvg%20fill=%22%236246EA%22%20fill-rule=%22evenodd%22%20height=%221em%22%20style=%22flex:none;line-height:1%22%20viewBox=%220%200%2024%2024%22%20width=%221em%22%20xmlns=%22http://www.w3.org/2000/svg%22%3E%3Ctitle%3EModelScope%3C/title%3E%3Cpath%20d=%22M2.667%205.3H8v2.667H5.333v2.666H2.667V8.467H.5v2.166h2.167V13.3H0V7.967h2.667V5.3zM2.667%2013.3h2.666v2.667H8v2.666H2.667V13.3zM8%2010.633h2.667V13.3H8v-2.667zM13.333%2013.3v2.667h-2.666V13.3h2.666zM13.333%2013.3v-2.667H16V13.3h-2.667z%22%3E%3C/path%3E%3Cpath%20clip-rule=%22evenodd%22%20d=%22M21.333%2013.3v-2.667h-2.666V7.967H16V5.3h5.333v2.667H24V13.3h-2.667zm0-2.667H23.5V8.467h-2.167v2.166z%22%3E%3C/path%3E%3Cpath%20d=%22M21.333%2013.3v5.333H16v-2.666h2.667V13.3h2.666z%22%3E%3C/path%3E%3C/svg%3E","dark":"data:image/svg+xml,%3Csvg%20fill=%22%236246EA%22%20fill-rule=%22evenodd%22%20height=%221em%22%20style=%22flex:none;line-height:1%22%20viewBox=%220%200%2024%2024%22%20width=%221em%22%20xmlns=%22http://www.w3.org/2000/svg%22%3E%3Ctitle%3EModelScope%3C/title%3E%3Cpath%20d=%22M2.667%205.3H8v2.667H5.333v2.666H2.667V8.467H.5v2.166h2.167V13.3H0V7.967h2.667V5.3zM2.667%2013.3h2.666v2.667H8v2.666H2.667V13.3zM8%2010.633h2.667V13.3H8v-2.667zM13.333%2013.3v2.667h-2.666V13.3h2.666zM13.333%2013.3v-2.667H16V13.3h-2.667z%22%3E%3C/path%3E%3Cpath%20clip-rule=%22evenodd%22%20d=%22M21.333%2013.3v-2.667h-2.666V7.967H16V5.3h5.333v2.667H24V13.3h-2.667zm0-2.667H23.5V8.467h-2.167v2.166z%22%3E%3C/path%3E%3Cpath%20d=%22M21.333%2013.3v5.333H16v-2.666h2.667V13.3h2.666z%22%3E%3C/path%3E%3C/svg%3E"},"Agnes":{"light":"data:image/svg+xml,%3Csvg%20fill=%22%230891B2%22%20fill-rule=%22evenodd%22%20height=%221em%22%20style=%22flex:none;line-height:1%22%20viewBox=%220%200%2024%2024%22%20width=%221em%22%20xmlns=%22http://www.w3.org/2000/svg%22%3E%3Ctitle%3EAgnes%20AI%3C/title%3E%3Cpath%20d=%22M12%200c6.627%200%2012%205.373%2012%2012s-5.373%2012-12%2012S0%2018.627%200%2012%205.373%200%2012%200zm5.013%208.817c-.2-.003-.4.026-.59.084-.51.153-.991.405-1.256.906-1.248%202.369-7.222%209.47-9.446%204.707H5.72c-.007.021-1.176%203.606.999%203.968%202.182.362%205.8-.672%209.798-8.227-.007.03-.496%202.381-.762%203.731a.885.885%200%2001-.308.513.906.906%200%2001-.567.204h-.533a.157.157%200%2000-.088.287c.506.345%201.154%201.094%201.258%202.68a.487.487%200%2000.239.388.503.503%200%2000.459.029.824.824%200%2000.38-.353c.085-.154.132-.325.136-.5l-.073-.66a.77.77%200%2001.507-.79c.474-.17%201.114-.525%201.427-1.252a.11.11%200%2000.009-.046.11.11%200%2000-.013-.045.108.108%200%2000-.03-.036.113.113%200%2000-.104-.017c-.317.113-.918.299-1.443.296a.261.261%200%2001-.244-.185.254.254%200%2001-.007-.108l.728-5.013a.484.484%200%2000-.475-.56zm-.406-3.169a1.204%201.204%200%2010-.384%202.378%201.204%201.204%200%2000.384-2.378z%22%3E%3C/path%3E%3C/svg%3E","dark":"data:image/svg+xml,%3Csvg%20fill=%22%230891B2%22%20fill-rule=%22evenodd%22%20height=%221em%22%20style=%22flex:none;line-height:1%22%20viewBox=%220%200%2024%2024%22%20width=%221em%22%20xmlns=%22http://www.w3.org/2000/svg%22%3E%3Ctitle%3EAgnes%20AI%3C/title%3E%3Cpath%20d=%22M12%200c6.627%200%2012%205.373%2012%2012s-5.373%2012-12%2012S0%2018.627%200%2012%205.373%200%2012%200zm5.013%208.817c-.2-.003-.4.026-.59.084-.51.153-.991.405-1.256.906-1.248%202.369-7.222%209.47-9.446%204.707H5.72c-.007.021-1.176%203.606.999%203.968%202.182.362%205.8-.672%209.798-8.227-.007.03-.496%202.381-.762%203.731a.885.885%200%2001-.308.513.906.906%200%2001-.567.204h-.533a.157.157%200%2000-.088.287c.506.345%201.154%201.094%201.258%202.68a.487.487%200%2000.239.388.503.503%200%2000.459.029.824.824%200%2000.38-.353c.085-.154.132-.325.136-.5l-.073-.66a.77.77%200%2001.507-.79c.474-.17%201.114-.525%201.427-1.252a.11.11%200%2000.009-.046.11.11%200%2000-.013-.045.108.108%200%2000-.03-.036.113.113%200%2000-.104-.017c-.317.113-.918.299-1.443.296a.261.261%200%2001-.244-.185.254.254%200%2001-.007-.108l.728-5.013a.484.484%200%2000-.475-.56zm-.406-3.169a1.204%201.204%200%2010-.384%202.378%201.204%201.204%200%2000.384-2.378z%22%3E%3C/path%3E%3C/svg%3E"},"Together":{"light":"data:image/svg+xml,%3Csvg%20fill=%22%237C3AED%22%20fill-rule=%22evenodd%22%20height=%221em%22%20style=%22flex:none;line-height:1%22%20viewBox=%220%200%2024%2024%22%20width=%221em%22%20xmlns=%22http://www.w3.org/2000/svg%22%3E%3Ctitle%3Etogether.ai%3C/title%3E%3Cpath%20d=%22M23.197%204.503A6%206%200%200015%202.307a5.973%205.973%200%2000-2.995%204.933l5.996.008v.515h-5.996c.039.937.298%201.87.8%202.74a6%206%200%201010.39-6z%22%3E%3C/path%3E%3Cpath%20d=%22M.805%204.5A6%206%200%20003%2012.697a5.972%205.972%200%20005.77.127L5.779%207.627l.446-.257%202.997%205.192A6%206%200%2010.804%204.5z%22%3E%3C/path%3E%3Cpath%20d=%22M12%2023.894a6%206%200%20005.999-6c0-2.13-1.1-3.996-2.775-5.06l-3.005%205.189-.444-.258%202.997-5.192A6%206%200%201012%2023.894z%22%3E%3C/path%3E%3C/svg%3E","dark":"data:image/svg+xml,%3Csvg%20fill=%22%237C3AED%22%20fill-rule=%22evenodd%22%20height=%221em%22%20style=%22flex:none;line-height:1%22%20viewBox=%220%200%2024%2024%22%20width=%221em%22%20xmlns=%22http://www.w3.org/2000/svg%22%3E%3Ctitle%3Etogether.ai%3C/title%3E%3Cpath%20d=%22M23.197%204.503A6%206%200%200015%202.307a5.973%205.973%200%2000-2.995%204.933l5.996.008v.515h-5.996c.039.937.298%201.87.8%202.74a6%206%200%201010.39-6z%22%3E%3C/path%3E%3Cpath%20d=%22M.805%204.5A6%206%200%20003%2012.697a5.972%205.972%200%20005.77.127L5.779%207.627l.446-.257%202.997%205.192A6%206%200%2010.804%204.5z%22%3E%3C/path%3E%3Cpath%20d=%22M12%2023.894a6%206%200%20005.999-6c0-2.13-1.1-3.996-2.775-5.06l-3.005%205.189-.444-.258%202.997-5.192A6%206%200%201012%2023.894z%22%3E%3C/path%3E%3C/svg%3E"},"Fireworks":{"light":"data:image/svg+xml,%3Csvg%20fill=%22%232563EB%22%20fill-rule=%22evenodd%22%20height=%221em%22%20style=%22flex:none;line-height:1%22%20viewBox=%220%200%2024%2024%22%20width=%221em%22%20xmlns=%22http://www.w3.org/2000/svg%22%3E%3Ctitle%3EFireworks%3C/title%3E%3Cpath%20clip-rule=%22evenodd%22%20d=%22M14.8%205l-2.801%206.795L9.195%205H7.397l3.072%207.428a1.64%201.64%200%20003.038.002L16.598%205H14.8zm1.196%2010.352l5.124-5.244-.699-1.669-5.596%205.739a1.664%201.664%200%2000-.343%201.807%201.642%201.642%200%20001.516%201.012L16%2017l8-.02-.699-1.669-7.303.041h-.002zM2.88%2010.104l.699-1.669%205.596%205.739c.468.479.603%201.189.343%201.807a1.643%201.643%200%2001-1.516%201.012l-8-.018-.002.002.699-1.669%207.303.042-5.122-5.246z%22%3E%3C/path%3E%3C/svg%3E","dark":"data:image/svg+xml,%3Csvg%20fill=%22%232563EB%22%20fill-rule=%22evenodd%22%20height=%221em%22%20style=%22flex:none;line-height:1%22%20viewBox=%220%200%2024%2024%22%20width=%221em%22%20xmlns=%22http://www.w3.org/2000/svg%22%3E%3Ctitle%3EFireworks%3C/title%3E%3Cpath%20clip-rule=%22evenodd%22%20d=%22M14.8%205l-2.801%206.795L9.195%205H7.397l3.072%207.428a1.64%201.64%200%20003.038.002L16.598%205H14.8zm1.196%2010.352l5.124-5.244-.699-1.669-5.596%205.739a1.664%201.664%200%2000-.343%201.807%201.642%201.642%200%20001.516%201.012L16%2017l8-.02-.699-1.669-7.303.041h-.002zM2.88%2010.104l.699-1.669%205.596%205.739c.468.479.603%201.189.343%201.807a1.643%201.643%200%2001-1.516%201.012l-8-.018-.002.002.699-1.669%207.303.042-5.122-5.246z%22%3E%3C/path%3E%3C/svg%3E"},"Cerebras":{"light":"data:image/svg+xml,%3Csvg%20fill=%22%23C2410C%22%20fill-rule=%22evenodd%22%20height=%221em%22%20style=%22flex:none;line-height:1%22%20viewBox=%220%200%2024%2024%22%20width=%221em%22%20xmlns=%22http://www.w3.org/2000/svg%22%3E%3Ctitle%3ECerebras%3C/title%3E%3Cpath%20clip-rule=%22evenodd%22%20d=%22M14.121%202.701a9.299%209.299%200%20000%2018.598V22.7c-5.91%200-10.7-4.791-10.7-10.701S8.21%201.299%2014.12%201.299V2.7zm4.752%203.677A7.353%207.353%200%20109.42%2017.643l-.901%201.074a8.754%208.754%200%2001-1.08-12.334%208.755%208.755%200%200112.335-1.08l-.901%201.075zm-2.255.844a5.407%205.407%200%2000-5.048%209.563l-.656%201.24a6.81%206.81%200%20016.358-12.043l-.654%201.24zM14.12%208.539a3.46%203.46%200%20100%206.922v1.402a4.863%204.863%200%20010-9.726v1.402z%22%3E%3C/path%3E%3Cpath%20d=%22M15.407%2010.836a2.24%202.24%200%2000-.51-.409%201.084%201.084%200%2000-.544-.152c-.255%200-.483.047-.684.14a1.58%201.58%200%2000-.84.912c-.074.203-.11.416-.11.631%200%20.218.036.43.11.631a1.594%201.594%200%2000.84.913c.2.093.43.14.684.14.216%200%20.417-.046.602-.135.188-.09.35-.225.475-.392l.928%201.006c-.14.14-.3.261-.482.363a3.367%203.367%200%2001-1.083.38c-.17.026-.317.04-.44.04a3.315%203.315%200%2001-1.182-.21%202.825%202.825%200%2001-.961-.597%202.816%202.816%200%2001-.644-.929%202.987%202.987%200%2001-.238-1.21c0-.444.08-.847.238-1.21.15-.35.368-.666.643-.929.278-.261.605-.464.962-.596a3.315%203.315%200%20011.182-.21c.355%200%20.712.068%201.072.204.361.138.685.36.944.649l-.962.97z%22%3E%3C/path%3E%3C/svg%3E","dark":"data:image/svg+xml,%3Csvg%20fill=%22%23C2410C%22%20fill-rule=%22evenodd%22%20height=%221em%22%20style=%22flex:none;line-height:1%22%20viewBox=%220%200%2024%2024%22%20width=%221em%22%20xmlns=%22http://www.w3.org/2000/svg%22%3E%3Ctitle%3ECerebras%3C/title%3E%3Cpath%20clip-rule=%22evenodd%22%20d=%22M14.121%202.701a9.299%209.299%200%20000%2018.598V22.7c-5.91%200-10.7-4.791-10.7-10.701S8.21%201.299%2014.12%201.299V2.7zm4.752%203.677A7.353%207.353%200%20109.42%2017.643l-.901%201.074a8.754%208.754%200%2001-1.08-12.334%208.755%208.755%200%200112.335-1.08l-.901%201.075zm-2.255.844a5.407%205.407%200%2000-5.048%209.563l-.656%201.24a6.81%206.81%200%20016.358-12.043l-.654%201.24zM14.12%208.539a3.46%203.46%200%20100%206.922v1.402a4.863%204.863%200%20010-9.726v1.402z%22%3E%3C/path%3E%3Cpath%20d=%22M15.407%2010.836a2.24%202.24%200%2000-.51-.409%201.084%201.084%200%2000-.544-.152c-.255%200-.483.047-.684.14a1.58%201.58%200%2000-.84.912c-.074.203-.11.416-.11.631%200%20.218.036.43.11.631a1.594%201.594%200%2000.84.913c.2.093.43.14.684.14.216%200%20.417-.046.602-.135.188-.09.35-.225.475-.392l.928%201.006c-.14.14-.3.261-.482.363a3.367%203.367%200%2001-1.083.38c-.17.026-.317.04-.44.04a3.315%203.315%200%2001-1.182-.21%202.825%202.825%200%2001-.961-.597%202.816%202.816%200%2001-.644-.929%202.987%202.987%200%2001-.238-1.21c0-.444.08-.847.238-1.21.15-.35.368-.666.643-.929.278-.261.605-.464.962-.596a3.315%203.315%200%20011.182-.21c.355%200%20.712.068%201.072.204.361.138.685.36.944.649l-.962.97z%22%3E%3C/path%3E%3C/svg%3E"},"Novita":{"light":"data:image/svg+xml,%3Csvg%20fill=%22%23059669%22%20fill-rule=%22evenodd%22%20height=%221em%22%20style=%22flex:none;line-height:1%22%20viewBox=%220%200%2024%2024%22%20width=%221em%22%20xmlns=%22http://www.w3.org/2000/svg%22%3E%3Ctitle%3ENovita%20AI%3C/title%3E%3Cpath%20clip-rule=%22evenodd%22%20d=%22M9.167%204.17v5.665L0%2019.003h9.167v-5.666l5.666%205.666H24L9.167%204.17z%22%3E%3C/path%3E%3C/svg%3E","dark":"data:image/svg+xml,%3Csvg%20fill=%22%23059669%22%20fill-rule=%22evenodd%22%20height=%221em%22%20style=%22flex:none;line-height:1%22%20viewBox=%220%200%2024%2024%22%20width=%221em%22%20xmlns=%22http://www.w3.org/2000/svg%22%3E%3Ctitle%3ENovita%20AI%3C/title%3E%3Cpath%20clip-rule=%22evenodd%22%20d=%22M9.167%204.17v5.665L0%2019.003h9.167v-5.666l5.666%205.666H24L9.167%204.17z%22%3E%3C/path%3E%3C/svg%3E"},"Hyperbolic":{"light":"data:image/svg+xml,%3Csvg%20fill=%22%230F766E%22%20fill-rule=%22evenodd%22%20height=%221em%22%20style=%22flex:none;line-height:1%22%20viewBox=%220%200%2024%2024%22%20width=%221em%22%20xmlns=%22http://www.w3.org/2000/svg%22%3E%3Ctitle%3EHyperbolic%3C/title%3E%3Cpath%20d=%22M.193%2019.503a2.413%202.413%200%2000-.186.925c0%201.317%201.112%202.518%202.95%203.437a1.337%201.337%200%20001.838-.738l2.049-4.93c.359-.857.642-1.745.846-2.652-3.795.637-6.656%202.092-7.448%203.872l-.032.076-.017.01zm7.49-11.047a15.981%2015.981%200%2000-.846-2.653L4.79.873a1.34%201.34%200%2000-1.84-.738C1.112%201.054%200%202.256%200%203.573c0%20.317.064.631.186.924v.01l.032.077c.81%201.78%203.67%203.234%207.466%203.872zM21.049.136c1.838.918%202.95%202.12%202.95%203.436a2.454%202.454%200%2001-.196.925l-.027.063c-.785%201.792-3.653%203.254-7.46%203.896.204-.907.487-1.795.846-2.653L19.21.873a1.337%201.337%200%20011.839-.738zm-4.722%2015.409c.201.906.48%201.793.837%202.65l2.048%204.932a1.338%201.338%200%20001.838.738c1.839-.92%202.951-2.12%202.951-3.437a2.446%202.446%200%2000-.186-.925l-.027-.062c-.782-1.792-3.66-3.256-7.46-3.896zm-.129-6.04c2.695-.415%204.935-1.223%206.48-2.278L22.24%208.28a9.755%209.755%200%20000%207.437l.435%201.048c-1.547-1.055-3.787-1.855-6.479-2.275l-.07-.01A27.196%2027.196%200%200012%2014.172c-1.377-.002-2.752.1-4.114.307l-.071.01c-2.693.413-4.933%201.222-6.48%202.277l.437-1.05a9.755%209.755%200%20000-7.437l-.437-1.052c1.54%201.06%203.78%201.863%206.473%202.278l.071.01c2.734.407%205.513.407%208.246%200l.071-.01z%22%3E%3C/path%3E%3C/svg%3E","dark":"data:image/svg+xml,%3Csvg%20fill=%22%230F766E%22%20fill-rule=%22evenodd%22%20height=%221em%22%20style=%22flex:none;line-height:1%22%20viewBox=%220%200%2024%2024%22%20width=%221em%22%20xmlns=%22http://www.w3.org/2000/svg%22%3E%3Ctitle%3EHyperbolic%3C/title%3E%3Cpath%20d=%22M.193%2019.503a2.413%202.413%200%2000-.186.925c0%201.317%201.112%202.518%202.95%203.437a1.337%201.337%200%20001.838-.738l2.049-4.93c.359-.857.642-1.745.846-2.652-3.795.637-6.656%202.092-7.448%203.872l-.032.076-.017.01zm7.49-11.047a15.981%2015.981%200%2000-.846-2.653L4.79.873a1.34%201.34%200%2000-1.84-.738C1.112%201.054%200%202.256%200%203.573c0%20.317.064.631.186.924v.01l.032.077c.81%201.78%203.67%203.234%207.466%203.872zM21.049.136c1.838.918%202.95%202.12%202.95%203.436a2.454%202.454%200%2001-.196.925l-.027.063c-.785%201.792-3.653%203.254-7.46%203.896.204-.907.487-1.795.846-2.653L19.21.873a1.337%201.337%200%20011.839-.738zm-4.722%2015.409c.201.906.48%201.793.837%202.65l2.048%204.932a1.338%201.338%200%20001.838.738c1.839-.92%202.951-2.12%202.951-3.437a2.446%202.446%200%2000-.186-.925l-.027-.062c-.782-1.792-3.66-3.256-7.46-3.896zm-.129-6.04c2.695-.415%204.935-1.223%206.48-2.278L22.24%208.28a9.755%209.755%200%20000%207.437l.435%201.048c-1.547-1.055-3.787-1.855-6.479-2.275l-.07-.01A27.196%2027.196%200%200012%2014.172c-1.377-.002-2.752.1-4.114.307l-.071.01c-2.693.413-4.933%201.222-6.48%202.277l.437-1.05a9.755%209.755%200%20000-7.437l-.437-1.052c1.54%201.06%203.78%201.863%206.473%202.278l.071.01c2.734.407%205.513.407%208.246%200l.071-.01z%22%3E%3C/path%3E%3C/svg%3E"},"Vertex AI":{"light":"data:image/svg+xml,%3Csvg%20fill=%22%234285F4%22%20fill-rule=%22evenodd%22%20height=%221em%22%20style=%22flex:none;line-height:1%22%20viewBox=%220%200%2024%2024%22%20width=%221em%22%20xmlns=%22http://www.w3.org/2000/svg%22%3E%3Ctitle%3EVertexAI%3C/title%3E%3Cpath%20d=%22M11.995%2020.216a1.892%201.892%200%20100%203.785%201.892%201.892%200%20000-3.785zm0%202.806a.927.927%200%2011.927-.914.914.914%200%2001-.927.914z%22%3E%3C/path%3E%3Cpath%20clip-rule=%22evenodd%22%20d=%22M21.687%2014.144c.237.038.452.16.605.344a.978.978%200%2001-.18%201.3l-8.24%206.082a1.892%201.892%200%2000-1.147-1.508l8.28-6.08a.991.991%200%2001.682-.138z%22%3E%3C/path%3E%3Cpath%20clip-rule=%22evenodd%22%20d=%22M10.122%2021.842l-8.217-6.066a.952.952%200%2001-.206-1.287.978.978%200%20011.287-.206l8.28%206.08a1.893%201.893%200%2000-1.144%201.479z%22%3E%3C/path%3E%3Cpath%20d=%22M4.273%204.475a.978.978%200%2001-.965-.965V1.09a.978.978%200%20111.943%200v2.42a.978.978%200%2001-.978.965zM4.247%2013.034a.978.978%200%20100-1.956.978.978%200%20000%201.956zM4.247%2010.19a.978.978%200%20100-1.956.978.978%200%20000%201.956zM4.247%207.332a.978.978%200%20100-1.956.978.978%200%20000%201.956z%22%3E%3C/path%3E%3Cpath%20d=%22M19.718%207.307a.978.978%200%2001-.965-.979v-2.42a.965.965%200%20011.93%200v2.42a.964.964%200%2001-.965.979zM19.743%2013.047a.978.978%200%20100-1.956.978.978%200%20000%201.956zM19.743%2010.151a.978.978%200%20100-1.956.978.978%200%20000%201.956zM19.743%202.068a.978.978%200%20100-1.956.978.978%200%20000%201.956z%22%3E%3C/path%3E%3Cpath%20d=%22M11.995%2015.917a.978.978%200%2001-.965-.965v-2.459a.978.978%200%20011.943%200v2.433a.976.976%200%2001-.978.991zM11.995%2018.762a.978.978%200%20100-1.956.978.978%200%20000%201.956zM11.995%2010.64a.978.978%200%20100-1.956.978.978%200%20000%201.956zM11.995%207.783a.978.978%200%20100-1.956.978.978%200%20000%201.956z%22%3E%3C/path%3E%3Cpath%20d=%22M15.856%2010.177a.978.978%200%2001-.965-.965v-2.42a.977.977%200%20011.702-.763.979.979%200%2001.241.763v2.42a.978.978%200%2001-.978.965zM15.869%204.913a.978.978%200%20100-1.956.978.978%200%20000%201.956zM15.869%2015.853a.978.978%200%20100-1.956.978.978%200%20000%201.956zM15.869%2012.996a.978.978%200%20100-1.956.978.978%200%20000%201.956z%22%3E%3C/path%3E%3Cpath%20d=%22M8.121%2015.853a.978.978%200%20100-1.956.978.978%200%20000%201.956zM8.121%207.783a.978.978%200%20100-1.956.978.978%200%20000%201.956zM8.121%204.913a.978.978%200%20100-1.957.978.978%200%20000%201.957zM8.134%2012.996a.978.978%200%2001-.978-.94V9.611a.965.965%200%20011.93%200v2.445a.966.966%200%2001-.952.94z%22%3E%3C/path%3E%3C/svg%3E","dark":"data:image/svg+xml,%3Csvg%20fill=%22%234285F4%22%20fill-rule=%22evenodd%22%20height=%221em%22%20style=%22flex:none;line-height:1%22%20viewBox=%220%200%2024%2024%22%20width=%221em%22%20xmlns=%22http://www.w3.org/2000/svg%22%3E%3Ctitle%3EVertexAI%3C/title%3E%3Cpath%20d=%22M11.995%2020.216a1.892%201.892%200%20100%203.785%201.892%201.892%200%20000-3.785zm0%202.806a.927.927%200%2011.927-.914.914.914%200%2001-.927.914z%22%3E%3C/path%3E%3Cpath%20clip-rule=%22evenodd%22%20d=%22M21.687%2014.144c.237.038.452.16.605.344a.978.978%200%2001-.18%201.3l-8.24%206.082a1.892%201.892%200%2000-1.147-1.508l8.28-6.08a.991.991%200%2001.682-.138z%22%3E%3C/path%3E%3Cpath%20clip-rule=%22evenodd%22%20d=%22M10.122%2021.842l-8.217-6.066a.952.952%200%2001-.206-1.287.978.978%200%20011.287-.206l8.28%206.08a1.893%201.893%200%2000-1.144%201.479z%22%3E%3C/path%3E%3Cpath%20d=%22M4.273%204.475a.978.978%200%2001-.965-.965V1.09a.978.978%200%20111.943%200v2.42a.978.978%200%2001-.978.965zM4.247%2013.034a.978.978%200%20100-1.956.978.978%200%20000%201.956zM4.247%2010.19a.978.978%200%20100-1.956.978.978%200%20000%201.956zM4.247%207.332a.978.978%200%20100-1.956.978.978%200%20000%201.956z%22%3E%3C/path%3E%3Cpath%20d=%22M19.718%207.307a.978.978%200%2001-.965-.979v-2.42a.965.965%200%20011.93%200v2.42a.964.964%200%2001-.965.979zM19.743%2013.047a.978.978%200%20100-1.956.978.978%200%20000%201.956zM19.743%2010.151a.978.978%200%20100-1.956.978.978%200%20000%201.956zM19.743%202.068a.978.978%200%20100-1.956.978.978%200%20000%201.956z%22%3E%3C/path%3E%3Cpath%20d=%22M11.995%2015.917a.978.978%200%2001-.965-.965v-2.459a.978.978%200%20011.943%200v2.433a.976.976%200%2001-.978.991zM11.995%2018.762a.978.978%200%20100-1.956.978.978%200%20000%201.956zM11.995%2010.64a.978.978%200%20100-1.956.978.978%200%20000%201.956zM11.995%207.783a.978.978%200%20100-1.956.978.978%200%20000%201.956z%22%3E%3C/path%3E%3Cpath%20d=%22M15.856%2010.177a.978.978%200%2001-.965-.965v-2.42a.977.977%200%20011.702-.763.979.979%200%2001.241.763v2.42a.978.978%200%2001-.978.965zM15.869%204.913a.978.978%200%20100-1.956.978.978%200%20000%201.956zM15.869%2015.853a.978.978%200%20100-1.956.978.978%200%20000%201.956zM15.869%2012.996a.978.978%200%20100-1.956.978.978%200%20000%201.956z%22%3E%3C/path%3E%3Cpath%20d=%22M8.121%2015.853a.978.978%200%20100-1.956.978.978%200%20000%201.956zM8.121%207.783a.978.978%200%20100-1.956.978.978%200%20000%201.956zM8.121%204.913a.978.978%200%20100-1.957.978.978%200%20000%201.957zM8.134%2012.996a.978.978%200%2001-.978-.94V9.611a.965.965%200%20011.93%200v2.445a.966.966%200%2001-.952.94z%22%3E%3C/path%3E%3C/svg%3E"},"Bedrock":{"light":"data:image/svg+xml,%3Csvg%20fill=%22%23FF9900%22%20fill-rule=%22evenodd%22%20height=%221em%22%20style=%22flex:none;line-height:1%22%20viewBox=%220%200%2024%2024%22%20width=%221em%22%20xmlns=%22http://www.w3.org/2000/svg%22%3E%3Ctitle%3EBedrock%3C/title%3E%3Cpath%20d=%22M13.05%2015.513h3.08c.214%200%20.389.177.389.394v1.82a1.704%201.704%200%20011.296%201.661c0%20.943-.755%201.708-1.685%201.708-.931%200-1.686-.765-1.686-1.708%200-.807.554-1.484%201.297-1.662v-1.425h-2.69v4.663a.395.395%200%2001-.188.338l-2.69%201.641a.385.385%200%2001-.405-.002l-4.926-3.086a.395.395%200%2001-.185-.336V16.3L2.196%2014.87A.395.395%200%20012%2014.555L2%2014.528V9.406c0-.14.073-.27.192-.34l2.465-1.462V4.448c0-.129.062-.249.165-.322l.021-.014L9.77%201.058a.385.385%200%2001.407%200l2.69%201.675a.395.395%200%2001.185.336V7.6h3.856V5.683a1.704%201.704%200%2001-1.296-1.662c0-.943.755-1.708%201.685-1.708.931%200%201.685.765%201.685%201.708%200%20.807-.553%201.484-1.296%201.662v2.311a.391.391%200%2001-.389.394h-4.245v1.806h6.624a1.69%201.69%200%20011.64-1.313c.93%200%201.685.764%201.685%201.707%200%20.943-.754%201.708-1.685%201.708a1.69%201.69%200%2001-1.64-1.314H13.05v1.937h4.953l.915%201.18a1.66%201.66%200%2001.84-.227c.931%200%201.685.764%201.685%201.707%200%20.943-.754%201.708-1.685%201.708-.93%200-1.685-.765-1.685-1.708%200-.346.102-.668.276-.937l-.724-.935H13.05v1.806zM9.973%201.856L7.93%203.122V6.09h-.778V3.604L5.435%204.669v2.945l2.11%201.36L9.712%207.61V5.334h.778V7.83c0%20.136-.07.263-.184.335L7.963%209.638v2.081l1.422%201.009-.446.646-1.406-.998-1.53%201.005-.423-.66%201.605-1.055v-1.99L5.038%208.29l-2.26%201.34v1.676l1.972-1.189.398.677-2.37%201.429V14.3l2.166%201.258%202.27-1.368.397.677-2.176%201.311V19.3l1.876%201.175%202.365-1.426.398.678-2.017%201.216%201.918%201.201%202.298-1.403v-5.78l-4.758%202.893-.4-.675%205.158-3.136V3.289L9.972%201.856zM16.13%2018.47a.913.913%200%2000-.908.92c0%20.507.406.918.908.918a.913.913%200%2000.907-.919.913.913%200%2000-.907-.92zm3.63-3.81a.913.913%200%2000-.908.92c0%20.508.406.92.907.92a.913.913%200%2000.908-.92.913.913%200%2000-.908-.92zm1.555-4.99a.913.913%200%2000-.908.92c0%20.507.407.918.908.918a.913.913%200%2000.907-.919.913.913%200%2000-.907-.92zM17.296%203.1a.913.913%200%2000-.907.92c0%20.508.406.92.907.92a.913.913%200%2000.908-.92.913.913%200%2000-.908-.92z%22%3E%3C/path%3E%3C/svg%3E","dark":"data:image/svg+xml,%3Csvg%20fill=%22%23FF9900%22%20fill-rule=%22evenodd%22%20height=%221em%22%20style=%22flex:none;line-height:1%22%20viewBox=%220%200%2024%2024%22%20width=%221em%22%20xmlns=%22http://www.w3.org/2000/svg%22%3E%3Ctitle%3EBedrock%3C/title%3E%3Cpath%20d=%22M13.05%2015.513h3.08c.214%200%20.389.177.389.394v1.82a1.704%201.704%200%20011.296%201.661c0%20.943-.755%201.708-1.685%201.708-.931%200-1.686-.765-1.686-1.708%200-.807.554-1.484%201.297-1.662v-1.425h-2.69v4.663a.395.395%200%2001-.188.338l-2.69%201.641a.385.385%200%2001-.405-.002l-4.926-3.086a.395.395%200%2001-.185-.336V16.3L2.196%2014.87A.395.395%200%20012%2014.555L2%2014.528V9.406c0-.14.073-.27.192-.34l2.465-1.462V4.448c0-.129.062-.249.165-.322l.021-.014L9.77%201.058a.385.385%200%2001.407%200l2.69%201.675a.395.395%200%2001.185.336V7.6h3.856V5.683a1.704%201.704%200%2001-1.296-1.662c0-.943.755-1.708%201.685-1.708.931%200%201.685.765%201.685%201.708%200%20.807-.553%201.484-1.296%201.662v2.311a.391.391%200%2001-.389.394h-4.245v1.806h6.624a1.69%201.69%200%20011.64-1.313c.93%200%201.685.764%201.685%201.707%200%20.943-.754%201.708-1.685%201.708a1.69%201.69%200%2001-1.64-1.314H13.05v1.937h4.953l.915%201.18a1.66%201.66%200%2001.84-.227c.931%200%201.685.764%201.685%201.707%200%20.943-.754%201.708-1.685%201.708-.93%200-1.685-.765-1.685-1.708%200-.346.102-.668.276-.937l-.724-.935H13.05v1.806zM9.973%201.856L7.93%203.122V6.09h-.778V3.604L5.435%204.669v2.945l2.11%201.36L9.712%207.61V5.334h.778V7.83c0%20.136-.07.263-.184.335L7.963%209.638v2.081l1.422%201.009-.446.646-1.406-.998-1.53%201.005-.423-.66%201.605-1.055v-1.99L5.038%208.29l-2.26%201.34v1.676l1.972-1.189.398.677-2.37%201.429V14.3l2.166%201.258%202.27-1.368.397.677-2.176%201.311V19.3l1.876%201.175%202.365-1.426.398.678-2.017%201.216%201.918%201.201%202.298-1.403v-5.78l-4.758%202.893-.4-.675%205.158-3.136V3.289L9.972%201.856zM16.13%2018.47a.913.913%200%2000-.908.92c0%20.507.406.918.908.918a.913.913%200%2000.907-.919.913.913%200%2000-.907-.92zm3.63-3.81a.913.913%200%2000-.908.92c0%20.508.406.92.907.92a.913.913%200%2000.908-.92.913.913%200%2000-.908-.92zm1.555-4.99a.913.913%200%2000-.908.92c0%20.507.407.918.908.918a.913.913%200%2000.907-.919.913.913%200%2000-.907-.92zM17.296%203.1a.913.913%200%2000-.907.92c0%20.508.406.92.907.92a.913.913%200%2000.908-.92.913.913%200%2000-.908-.92z%22%3E%3C/path%3E%3C/svg%3E"},"Azure":{"light":"data:image/svg+xml,%3Csvg%20fill=%22%230078D4%22%20fill-rule=%22evenodd%22%20height=%221em%22%20style=%22flex:none;line-height:1%22%20viewBox=%220%200%2024%2024%22%20width=%221em%22%20xmlns=%22http://www.w3.org/2000/svg%22%3E%3Ctitle%3EAzure%3C/title%3E%3Cpath%20d=%22M18.397%2015.296H7.4a.51.51%200%2000-.347.882l7.066%206.595c.206.192.477.298.758.298h6.226l-2.706-7.775z%22%20fill-opacity=%22.75%22%3E%3C/path%3E%3Cpath%20d=%22M8.295.857c-.477%200-.9.304-1.053.756L.495%2021.605a1.11%201.11%200%20001.052%201.466h5.43c.477%200%20.9-.304%201.053-.755l1.341-3.975-2.318-2.163a.51.51%200%2001.347-.882h3L15.271.857H8.295z%22%20fill-opacity=%22.5%22%3E%3C/path%3E%3Cpath%20d=%22M17.193%201.613a1.11%201.11%200%2000-1.052-.756h-7.81.035c.477%200%20.9.304%201.052.756l6.748%2019.992a1.11%201.11%200%2001-1.052%201.466h-.12%207.895a1.11%201.11%200%20001.052-1.466L17.193%201.613z%22%3E%3C/path%3E%3C/svg%3E","dark":"data:image/svg+xml,%3Csvg%20fill=%22%230078D4%22%20fill-rule=%22evenodd%22%20height=%221em%22%20style=%22flex:none;line-height:1%22%20viewBox=%220%200%2024%2024%22%20width=%221em%22%20xmlns=%22http://www.w3.org/2000/svg%22%3E%3Ctitle%3EAzure%3C/title%3E%3Cpath%20d=%22M18.397%2015.296H7.4a.51.51%200%2000-.347.882l7.066%206.595c.206.192.477.298.758.298h6.226l-2.706-7.775z%22%20fill-opacity=%22.75%22%3E%3C/path%3E%3Cpath%20d=%22M8.295.857c-.477%200-.9.304-1.053.756L.495%2021.605a1.11%201.11%200%20001.052%201.466h5.43c.477%200%20.9-.304%201.053-.755l1.341-3.975-2.318-2.163a.51.51%200%2001.347-.882h3L15.271.857H8.295z%22%20fill-opacity=%22.5%22%3E%3C/path%3E%3Cpath%20d=%22M17.193%201.613a1.11%201.11%200%2000-1.052-.756h-7.81.035c.477%200%20.9.304%201.052.756l6.748%2019.992a1.11%201.11%200%2001-1.052%201.466h-.12%207.895a1.11%201.11%200%20001.052-1.466L17.193%201.613z%22%3E%3C/path%3E%3C/svg%3E"},"Ollama":{"light":"data:image/svg+xml,%3Csvg%20fill=%22%23111827%22%20fill-rule=%22evenodd%22%20height=%221em%22%20style=%22flex:none;line-height:1%22%20viewBox=%220%200%2024%2024%22%20width=%221em%22%20xmlns=%22http://www.w3.org/2000/svg%22%3E%3Ctitle%3EOllama%3C/title%3E%3Cpath%20d=%22M7.905%201.09c.216.085.411.225.588.41.295.306.544.744.734%201.263.191.522.315%201.1.362%201.68a5.054%205.054%200%20012.049-.636l.051-.004c.87-.07%201.73.087%202.48.474.101.053.2.11.297.17.05-.569.172-1.134.36-1.644.19-.52.439-.957.733-1.264a1.67%201.67%200%2001.589-.41c.257-.1.53-.118.796-.042.401.114.745.368%201.016.737.248.337.434.769.561%201.287.23.934.27%202.163.115%203.645l.053.04.026.019c.757.576%201.284%201.397%201.563%202.35.435%201.487.216%203.155-.534%204.088l-.018.021.002.003c.417.762.67%201.567.724%202.4l.002.03c.064%201.065-.2%202.137-.814%203.19l-.007.01.01.024c.472%201.157.62%202.322.438%203.486l-.006.039a.651.651%200%2001-.747.536.648.648%200%2001-.54-.742c.167-1.033.01-2.069-.48-3.123a.643.643%200%2001.04-.617l.004-.006c.604-.924.854-1.83.8-2.72-.046-.779-.325-1.544-.8-2.273a.644.644%200%2001.18-.886l.009-.006c.243-.159.467-.565.58-1.12a4.229%204.229%200%2000-.095-1.974c-.205-.7-.58-1.284-1.105-1.683-.595-.454-1.383-.673-2.38-.61a.653.653%200%2001-.632-.371c-.314-.665-.772-1.141-1.343-1.436a3.288%203.288%200%2000-1.772-.332c-1.245.099-2.343.801-2.67%201.686a.652.652%200%2001-.61.425c-1.067.002-1.893.252-2.497.703-.522.39-.878.935-1.066%201.588a4.07%204.07%200%2000-.068%201.886c.112.558.331%201.02.582%201.269l.008.007c.212.207.257.53.109.785-.36.622-.629%201.549-.673%202.44-.05%201.018.186%201.902.719%202.536l.016.019a.643.643%200%2001.095.69c-.576%201.236-.753%202.252-.562%203.052a.652.652%200%2001-1.269.298c-.243-1.018-.078-2.184.473-3.498l.014-.035-.008-.012a4.339%204.339%200%2001-.598-1.309l-.005-.019a5.764%205.764%200%2001-.177-1.785c.044-.91.278-1.842.622-2.59l.012-.026-.002-.002c-.293-.418-.51-.953-.63-1.545l-.005-.024a5.352%205.352%200%2001.093-2.49c.262-.915.777-1.701%201.536-2.269.06-.045.123-.09.186-.132-.159-1.493-.119-2.73.112-3.67.127-.518.314-.95.562-1.287.27-.368.614-.622%201.015-.737.266-.076.54-.059.797.042zm4.116%209.09c.936%200%201.8.313%202.446.855.63.527%201.005%201.235%201.005%201.94%200%20.888-.406%201.58-1.133%202.022-.62.375-1.451.557-2.403.557-1.009%200-1.871-.259-2.493-.734-.617-.47-.963-1.13-.963-1.845%200-.707.398-1.417%201.056-1.946.668-.537%201.55-.849%202.485-.849zm0%20.896a3.07%203.07%200%2000-1.916.65c-.461.37-.722.835-.722%201.25%200%20.428.21.829.61%201.134.455.347%201.124.548%201.943.548.799%200%201.473-.147%201.932-.426.463-.28.7-.686.7-1.257%200-.423-.246-.89-.683-1.256-.484-.405-1.14-.643-1.864-.643zm.662%201.21l.004.004c.12.151.095.37-.056.49l-.292.23v.446a.375.375%200%2001-.376.373.375.375%200%2001-.376-.373v-.46l-.271-.218a.347.347%200%2001-.052-.49.353.353%200%2001.494-.051l.215.172.22-.174a.353.353%200%2001.49.051zm-5.04-1.919c.478%200%20.867.39.867.871a.87.87%200%2001-.868.871.87.87%200%2001-.867-.87.87.87%200%2001.867-.872zm8.706%200c.48%200%20.868.39.868.871a.87.87%200%2001-.868.871.87.87%200%2001-.867-.87.87.87%200%2001.867-.872zM7.44%202.3l-.003.002a.659.659%200%2000-.285.238l-.005.006c-.138.189-.258.467-.348.832-.17.692-.216%201.631-.124%202.782.43-.128.899-.208%201.404-.237l.01-.001.019-.034c.046-.082.095-.161.148-.239.123-.771.022-1.692-.253-2.444-.134-.364-.297-.65-.453-.813a.628.628%200%2000-.107-.09L7.44%202.3zm9.174.04l-.002.001a.628.628%200%2000-.107.09c-.156.163-.32.45-.453.814-.29.794-.387%201.776-.23%202.572l.058.097.008.014h.03a5.184%205.184%200%20011.466.212c.086-1.124.038-2.043-.128-2.722-.09-.365-.21-.643-.349-.832l-.004-.006a.659.659%200%2000-.285-.239h-.004z%22%3E%3C/path%3E%3C/svg%3E","dark":"data:image/svg+xml,%3Csvg%20fill=%22%23111827%22%20fill-rule=%22evenodd%22%20height=%221em%22%20style=%22flex:none;line-height:1%22%20viewBox=%220%200%2024%2024%22%20width=%221em%22%20xmlns=%22http://www.w3.org/2000/svg%22%3E%3Ctitle%3EOllama%3C/title%3E%3Cpath%20d=%22M7.905%201.09c.216.085.411.225.588.41.295.306.544.744.734%201.263.191.522.315%201.1.362%201.68a5.054%205.054%200%20012.049-.636l.051-.004c.87-.07%201.73.087%202.48.474.101.053.2.11.297.17.05-.569.172-1.134.36-1.644.19-.52.439-.957.733-1.264a1.67%201.67%200%2001.589-.41c.257-.1.53-.118.796-.042.401.114.745.368%201.016.737.248.337.434.769.561%201.287.23.934.27%202.163.115%203.645l.053.04.026.019c.757.576%201.284%201.397%201.563%202.35.435%201.487.216%203.155-.534%204.088l-.018.021.002.003c.417.762.67%201.567.724%202.4l.002.03c.064%201.065-.2%202.137-.814%203.19l-.007.01.01.024c.472%201.157.62%202.322.438%203.486l-.006.039a.651.651%200%2001-.747.536.648.648%200%2001-.54-.742c.167-1.033.01-2.069-.48-3.123a.643.643%200%2001.04-.617l.004-.006c.604-.924.854-1.83.8-2.72-.046-.779-.325-1.544-.8-2.273a.644.644%200%2001.18-.886l.009-.006c.243-.159.467-.565.58-1.12a4.229%204.229%200%2000-.095-1.974c-.205-.7-.58-1.284-1.105-1.683-.595-.454-1.383-.673-2.38-.61a.653.653%200%2001-.632-.371c-.314-.665-.772-1.141-1.343-1.436a3.288%203.288%200%2000-1.772-.332c-1.245.099-2.343.801-2.67%201.686a.652.652%200%2001-.61.425c-1.067.002-1.893.252-2.497.703-.522.39-.878.935-1.066%201.588a4.07%204.07%200%2000-.068%201.886c.112.558.331%201.02.582%201.269l.008.007c.212.207.257.53.109.785-.36.622-.629%201.549-.673%202.44-.05%201.018.186%201.902.719%202.536l.016.019a.643.643%200%2001.095.69c-.576%201.236-.753%202.252-.562%203.052a.652.652%200%2001-1.269.298c-.243-1.018-.078-2.184.473-3.498l.014-.035-.008-.012a4.339%204.339%200%2001-.598-1.309l-.005-.019a5.764%205.764%200%2001-.177-1.785c.044-.91.278-1.842.622-2.59l.012-.026-.002-.002c-.293-.418-.51-.953-.63-1.545l-.005-.024a5.352%205.352%200%2001.093-2.49c.262-.915.777-1.701%201.536-2.269.06-.045.123-.09.186-.132-.159-1.493-.119-2.73.112-3.67.127-.518.314-.95.562-1.287.27-.368.614-.622%201.015-.737.266-.076.54-.059.797.042zm4.116%209.09c.936%200%201.8.313%202.446.855.63.527%201.005%201.235%201.005%201.94%200%20.888-.406%201.58-1.133%202.022-.62.375-1.451.557-2.403.557-1.009%200-1.871-.259-2.493-.734-.617-.47-.963-1.13-.963-1.845%200-.707.398-1.417%201.056-1.946.668-.537%201.55-.849%202.485-.849zm0%20.896a3.07%203.07%200%2000-1.916.65c-.461.37-.722.835-.722%201.25%200%20.428.21.829.61%201.134.455.347%201.124.548%201.943.548.799%200%201.473-.147%201.932-.426.463-.28.7-.686.7-1.257%200-.423-.246-.89-.683-1.256-.484-.405-1.14-.643-1.864-.643zm.662%201.21l.004.004c.12.151.095.37-.056.49l-.292.23v.446a.375.375%200%2001-.376.373.375.375%200%2001-.376-.373v-.46l-.271-.218a.347.347%200%2001-.052-.49.353.353%200%2001.494-.051l.215.172.22-.174a.353.353%200%2001.49.051zm-5.04-1.919c.478%200%20.867.39.867.871a.87.87%200%2001-.868.871.87.87%200%2001-.867-.87.87.87%200%2001.867-.872zm8.706%200c.48%200%20.868.39.868.871a.87.87%200%2001-.868.871.87.87%200%2001-.867-.87.87.87%200%2001.867-.872zM7.44%202.3l-.003.002a.659.659%200%2000-.285.238l-.005.006c-.138.189-.258.467-.348.832-.17.692-.216%201.631-.124%202.782.43-.128.899-.208%201.404-.237l.01-.001.019-.034c.046-.082.095-.161.148-.239.123-.771.022-1.692-.253-2.444-.134-.364-.297-.65-.453-.813a.628.628%200%2000-.107-.09L7.44%202.3zm9.174.04l-.002.001a.628.628%200%2000-.107.09c-.156.163-.32.45-.453.814-.29.794-.387%201.776-.23%202.572l.058.097.008.014h.03a5.184%205.184%200%20011.466.212c.086-1.124.038-2.043-.128-2.722-.09-.365-.21-.643-.349-.832l-.004-.006a.659.659%200%2000-.285-.239h-.004z%22%3E%3C/path%3E%3C/svg%3E"},"Copilot":{"light":"data:image/svg+xml,%3Csvg%20fill=%22%237C3AED%22%20fill-rule=%22evenodd%22%20height=%221em%22%20style=%22flex:none;line-height:1%22%20viewBox=%220%200%2024%2024%22%20width=%221em%22%20xmlns=%22http://www.w3.org/2000/svg%22%3E%3Ctitle%3ECopilot%3C/title%3E%3Cpath%20d=%22M16.295%205.29l-0.242%200.986h-2.32c-1.721%200-3.22%201.197-3.638%202.902l-2.101%208.593H3.798c-2.44%200-4.229-2.342-3.637-4.761l2.106-8.612c0.557-2.274%202.556-3.87%204.85-3.87h5.54c2.44%200%204.23%202.343%203.638%204.761%22%3E%3C/path%3E%3Cpath%20d=%22M16.295%205.29l-0.242%200.986h-2.32c-1.721%200-3.22%201.197-3.638%202.902l-2.101%208.593H3.798c-2.44%200-4.229-2.342-3.637-4.761l2.106-8.612c0.557-2.274%202.556-3.87%204.85-3.87h5.54c2.44%200%204.23%202.343%203.638%204.761M7.752%2018.758l0.242-0.986h2.321c1.72%200%203.22-1.197%203.637-2.903l2.102-8.593h4.196c2.439%200%204.228%202.343%203.637%204.762l-2.107%208.611c-0.556%202.274-2.555%203.87-4.85%203.87h-5.54c-2.44%200-4.229-2.342-3.638-4.761%22%3E%3C/path%3E%3Cpath%20d=%22M7.752%2018.758l0.242-0.986h2.321c1.72%200%203.22-1.197%203.637-2.903l2.102-8.593h4.196c2.439%200%204.228%202.343%203.637%204.762l-2.107%208.611c-0.556%202.274-2.555%203.87-4.85%203.87h-5.54c-2.44%200-4.229-2.342-3.638-4.761%22%3E%3C/path%3E%3C/svg%3E","dark":"data:image/svg+xml,%3Csvg%20fill=%22%237C3AED%22%20fill-rule=%22evenodd%22%20height=%221em%22%20style=%22flex:none;line-height:1%22%20viewBox=%220%200%2024%2024%22%20width=%221em%22%20xmlns=%22http://www.w3.org/2000/svg%22%3E%3Ctitle%3ECopilot%3C/title%3E%3Cpath%20d=%22M16.295%205.29l-0.242%200.986h-2.32c-1.721%200-3.22%201.197-3.638%202.902l-2.101%208.593H3.798c-2.44%200-4.229-2.342-3.637-4.761l2.106-8.612c0.557-2.274%202.556-3.87%204.85-3.87h5.54c2.44%200%204.23%202.343%203.638%204.761%22%3E%3C/path%3E%3Cpath%20d=%22M16.295%205.29l-0.242%200.986h-2.32c-1.721%200-3.22%201.197-3.638%202.902l-2.101%208.593H3.798c-2.44%200-4.229-2.342-3.637-4.761l2.106-8.612c0.557-2.274%202.556-3.87%204.85-3.87h5.54c2.44%200%204.23%202.343%203.638%204.761M7.752%2018.758l0.242-0.986h2.321c1.72%200%203.22-1.197%203.637-2.903l2.102-8.593h4.196c2.439%200%204.228%202.343%203.637%204.762l-2.107%208.611c-0.556%202.274-2.555%203.87-4.85%203.87h-5.54c-2.44%200-4.229-2.342-3.638-4.761%22%3E%3C/path%3E%3Cpath%20d=%22M7.752%2018.758l0.242-0.986h2.321c1.72%200%203.22-1.197%203.637-2.903l2.102-8.593h4.196c2.439%200%204.228%202.343%203.637%204.762l-2.107%208.611c-0.556%202.274-2.555%203.87-4.85%203.87h-5.54c-2.44%200-4.229-2.342-3.638-4.761%22%3E%3C/path%3E%3C/svg%3E"},"LM Studio":{"light":"data:image/svg+xml,%3Csvg%20fill=%22%23536DFE%22%20fill-rule=%22evenodd%22%20height=%221em%22%20style=%22flex:none;line-height:1%22%20viewBox=%220%200%2024%2024%22%20width=%221em%22%20xmlns=%22http://www.w3.org/2000/svg%22%3E%3Ctitle%3ELM%20Studio%3C/title%3E%3Cpath%20d=%22M2.84%202a1.273%201.273%200%20100%202.547h14.107a1.273%201.273%200%20100-2.547H2.84zM7.935%205.33a1.273%201.273%200%20000%202.548H22.04a1.274%201.274%200%20000-2.547H7.935zM3.624%209.935c0-.704.57-1.274%201.274-1.274h14.106a1.274%201.274%200%20010%202.547H4.898c-.703%200-1.274-.57-1.274-1.273zM1.273%2012.188a1.273%201.273%200%20100%202.547H15.38a1.274%201.274%200%20000-2.547H1.273zM3.624%2016.792c0-.704.57-1.274%201.274-1.274h14.106a1.273%201.273%200%20110%202.547H4.898c-.703%200-1.274-.57-1.274-1.273zM13.029%2018.849a1.273%201.273%200%20100%202.547h9.698a1.273%201.273%200%20100-2.547h-9.698z%22%20fill-opacity=%22.3%22%3E%3C/path%3E%3Cpath%20d=%22M2.84%202a1.273%201.273%200%20100%202.547h10.287a1.274%201.274%200%20000-2.547H2.84zM7.935%205.33a1.273%201.273%200%20000%202.548H18.22a1.274%201.274%200%20000-2.547H7.935zM3.624%209.935c0-.704.57-1.274%201.274-1.274h10.286a1.273%201.273%200%20010%202.547H4.898c-.703%200-1.274-.57-1.274-1.273zM1.273%2012.188a1.273%201.273%200%20100%202.547H11.56a1.274%201.274%200%20000-2.547H1.273zM3.624%2016.792c0-.704.57-1.274%201.274-1.274h10.286a1.273%201.273%200%20110%202.547H4.898c-.703%200-1.274-.57-1.274-1.273zM13.029%2018.849a1.273%201.273%200%20100%202.547h5.78a1.273%201.273%200%20100-2.547h-5.78z%22%3E%3C/path%3E%3C/svg%3E","dark":"data:image/svg+xml,%3Csvg%20fill=%22%23536DFE%22%20fill-rule=%22evenodd%22%20height=%221em%22%20style=%22flex:none;line-height:1%22%20viewBox=%220%200%2024%2024%22%20width=%221em%22%20xmlns=%22http://www.w3.org/2000/svg%22%3E%3Ctitle%3ELM%20Studio%3C/title%3E%3Cpath%20d=%22M2.84%202a1.273%201.273%200%20100%202.547h14.107a1.273%201.273%200%20100-2.547H2.84zM7.935%205.33a1.273%201.273%200%20000%202.548H22.04a1.274%201.274%200%20000-2.547H7.935zM3.624%209.935c0-.704.57-1.274%201.274-1.274h14.106a1.274%201.274%200%20010%202.547H4.898c-.703%200-1.274-.57-1.274-1.273zM1.273%2012.188a1.273%201.273%200%20100%202.547H15.38a1.274%201.274%200%20000-2.547H1.273zM3.624%2016.792c0-.704.57-1.274%201.274-1.274h14.106a1.273%201.273%200%20110%202.547H4.898c-.703%200-1.274-.57-1.274-1.273zM13.029%2018.849a1.273%201.273%200%20100%202.547h9.698a1.273%201.273%200%20100-2.547h-9.698z%22%20fill-opacity=%22.3%22%3E%3C/path%3E%3Cpath%20d=%22M2.84%202a1.273%201.273%200%20100%202.547h10.287a1.274%201.274%200%20000-2.547H2.84zM7.935%205.33a1.273%201.273%200%20000%202.548H18.22a1.274%201.274%200%20000-2.547H7.935zM3.624%209.935c0-.704.57-1.274%201.274-1.274h10.286a1.273%201.273%200%20010%202.547H4.898c-.703%200-1.274-.57-1.274-1.273zM1.273%2012.188a1.273%201.273%200%20100%202.547H11.56a1.274%201.274%200%20000-2.547H1.273zM3.624%2016.792c0-.704.57-1.274%201.274-1.274h10.286a1.273%201.273%200%20110%202.547H4.898c-.703%200-1.274-.57-1.274-1.273zM13.029%2018.849a1.273%201.273%200%20100%202.547h5.78a1.273%201.273%200%20100-2.547h-5.78z%22%3E%3C/path%3E%3C/svg%3E"},"vLLM":{"light":"data:image/svg+xml,%3Csvg%20fill=%22%2300A67E%22%20fill-rule=%22evenodd%22%20height=%221em%22%20style=%22flex:none;line-height:1%22%20viewBox=%220%200%2024%2024%22%20width=%221em%22%20xmlns=%22http://www.w3.org/2000/svg%22%3E%3Ctitle%3EvLLM%3C/title%3E%3Cpath%20d=%22M0%204.973h9.324V23L0%204.973z%22%3E%3C/path%3E%3Cpath%20d=%22M13.986%204.351L22.378%200l-6.216%2023H9.324l4.662-18.649z%22%3E%3C/path%3E%3C/svg%3E","dark":"data:image/svg+xml,%3Csvg%20fill=%22%2300A67E%22%20fill-rule=%22evenodd%22%20height=%221em%22%20style=%22flex:none;line-height:1%22%20viewBox=%220%200%2024%2024%22%20width=%221em%22%20xmlns=%22http://www.w3.org/2000/svg%22%3E%3Ctitle%3EvLLM%3C/title%3E%3Cpath%20d=%22M0%204.973h9.324V23L0%204.973z%22%3E%3C/path%3E%3Cpath%20d=%22M13.986%204.351L22.378%200l-6.216%2023H9.324l4.662-18.649z%22%3E%3C/path%3E%3C/svg%3E"},"HuggingFace":{"light":"data:image/svg+xml,%3Csvg%20fill=%22%23F4A261%22%20fill-rule=%22evenodd%22%20height=%221em%22%20style=%22flex:none;line-height:1%22%20viewBox=%220%200%2024%2024%22%20width=%221em%22%20xmlns=%22http://www.w3.org/2000/svg%22%3E%3Ctitle%3EHuggingFace%3C/title%3E%3Cpath%20d=%22M16.781%203.277c2.997%201.704%204.844%204.851%204.844%208.258%200%20.995-.155%201.955-.443%202.857a1.332%201.332%200%20011.125.4%201.41%201.41%200%2001.2%201.723c.204.165.352.385.428.632l.017.062c.06.222.12.69-.2%201.166.244.37.279.836.093%201.236-.255.57-.893%201.018-2.128%201.5l-.202.078-.131.048c-.478.173-.89.295-1.061.345l-.086.024c-.89.243-1.808.375-2.732.394-1.32%200-2.3-.36-2.923-1.067a9.852%209.852%200%2001-3.18.018C9.778%2021.647%208.802%2022%207.494%2022a11.249%2011.249%200%2001-2.541-.343l-.221-.06-.273-.08a16.574%2016.574%200%2001-1.175-.405c-1.237-.483-1.875-.93-2.13-1.501-.186-.4-.151-.867.093-1.236a1.42%201.42%200%2001-.2-1.166c.069-.273.226-.516.447-.694a1.41%201.41%200%2001.2-1.722c.233-.248.557-.391.917-.407l.078-.001a9.385%209.385%200%2001-.44-2.85c0-3.407%201.847-6.554%204.844-8.258a9.822%209.822%200%20019.687%200zM4.188%2014.758c.125.687%202.357%202.35%202.14%202.707-.19.315-.796-.239-.948-.386l-.041-.04-.168-.147c-.561-.479-2.304-1.9-2.74-1.432-.43.46.119.859%201.055%201.42l.784.467.136.083c1.045.643%201.12.84.95%201.113-.188.295-3.07-2.1-3.34-1.083-.27%201.011%202.942%201.304%202.744%202.006-.2.7-2.265-1.324-2.685-.537-.425.79%202.913%201.718%202.94%201.725l.16.04.175.042c1.227.284%203.565.65%204.435-.604.673-.973.64-1.709-.248-2.61l-.057-.057c-.945-.928-1.495-2.288-1.495-2.288l-.017-.058-.025-.072c-.082-.22-.284-.639-.63-.584-.46.073-.798%201.21.12%201.933l.05.038c.977.721-.195%201.21-.573.534l-.058-.104-.143-.25c-.463-.799-1.282-2.111-1.739-2.397-.532-.332-.907-.148-.782.541zm14.842-.541c-.533.335-1.563%202.074-1.94%202.751a.613.613%200%2001-.687.302.436.436%200%2001-.176-.098.303.303%200%2001-.049-.06l-.014-.028-.008-.02-.007-.019-.003-.013-.003-.017a.289.289%200%2001-.004-.048c0-.12.071-.266.25-.427.026-.024.054-.047.084-.07l.047-.036c.022-.016.043-.032.063-.049.883-.71.573-1.81.131-1.917l-.031-.006-.056-.004a.368.368%200%2000-.062.006l-.028.005-.042.014-.039.017-.028.015-.028.019-.036.027-.023.02c-.173.158-.273.428-.31.542l-.016.054s-.53%201.309-1.439%202.234l-.054.054c-.365.358-.596.69-.702%201.018-.143.437-.066.868.21%201.353.055.097.117.195.187.296.882%201.275%203.282.876%204.494.59l.286-.07.25-.074c.276-.084.736-.233%201.2-.42l.188-.077.065-.028.064-.028.124-.056.081-.038c.529-.252.964-.543.994-.827l.001-.036a.299.299%200%2000-.037-.139c-.094-.176-.271-.212-.491-.168l-.045.01c-.044.01-.09.024-.136.04l-.097.035-.054.022c-.559.23-1.238.705-1.607.745h.006a.452.452%200%2001-.05.003h-.024l-.024-.003-.023-.005c-.068-.016-.116-.06-.14-.142a.22.22%200%2001-.005-.1c.062-.345.958-.595%201.713-.91l.066-.028c.528-.224.97-.483.985-.832v-.04a.47.47%200%2000-.016-.098c-.048-.18-.175-.251-.36-.251-.785%200-2.55%201.36-2.92%201.36-.025%200-.048-.007-.058-.024a.6.6%200%2001-.046-.088c-.1-.238.068-.462%201.06-1.066l.209-.126c.538-.32%201.01-.588%201.341-.831.29-.212.475-.406.503-.6l.003-.028c.008-.113-.038-.227-.147-.344a.266.266%200%2000-.07-.054l-.034-.015-.013-.005a.403.403%200%2000-.13-.02c-.162%200-.369.07-.595.18-.637.313-1.431.952-1.826%201.285l-.249.215-.033.033c-.08.078-.288.27-.493.386l-.071.037-.041.019a.535.535%200%2001-.122.036h.005a.346.346%200%2001-.031.003l.01-.001-.013.001c-.079.005-.145-.021-.19-.095a.113.113%200%2001-.014-.065c.027-.465%202.034-1.991%202.152-2.642l.009-.048c.1-.65-.271-.817-.791-.493zM11.938%202.984c-4.798%200-8.688%203.829-8.688%208.55%200%20.692.083%201.364.24%202.008l.008-.009c.252-.298.612-.46%201.017-.46.355.008.699.117.993.312.22.14.465.384.715.694.261-.372.69-.598%201.15-.605.852%200%201.367.728%201.562%201.383l.047.105.06.127c.192.396.595%201.139%201.143%201.68%201.06%201.04%201.324%202.115.8%203.266a8.865%208.865%200%20002.024-.014c-.505-1.12-.26-2.17.74-3.186l.066-.066c.695-.684%201.157-1.69%201.252-1.912.195-.655.708-1.383%201.56-1.383.46.007.889.233%201.15.605.25-.31.495-.553.718-.694a1.87%201.87%200%2001.99-.312c.357%200%20.682.126.925.36.14-.61.215-1.245.215-1.898%200-4.722-3.89-8.55-8.687-8.55zm1.857%208.926l.439-.212c.553-.264.89-.383.89.152%200%201.093-.771%203.208-3.155%203.262h-.184c-2.325-.052-3.116-2.06-3.156-3.175l-.001-.087c0-1.107%201.452.586%203.25.586.716%200%201.379-.272%201.917-.526zm4.017-3.143c.45%200%20.813.358.813.8%200%20.441-.364.8-.813.8a.806.806%200%2001-.812-.8c0-.442.364-.8.812-.8zm-11.624%200c.448%200%20.812.358.812.8%200%20.441-.364.8-.812.8a.806.806%200%2001-.813-.8c0-.442.364-.8.813-.8zm7.79-.841c.32-.384.846-.54%201.33-.394.483.146.83.564.878%201.06.048.495-.212.97-.659%201.203-.322.168-.447-.477-.767-.585l.002-.003c-.287-.098-.772.362-.925.079a1.215%201.215%200%2001.14-1.36zm-4.323%200c.322.384.377.92.14%201.36-.152.283-.64-.177-.925-.079l.003.003c-.108.036-.194.134-.273.24l-.118.165c-.11.15-.22.262-.377.18a1.226%201.226%200%2001-.658-1.204c.048-.495.395-.913.878-1.059a1.262%201.262%200%20011.33.394z%22%3E%3C/path%3E%3C/svg%3E","dark":"data:image/svg+xml,%3Csvg%20fill=%22%23F4A261%22%20fill-rule=%22evenodd%22%20height=%221em%22%20style=%22flex:none;line-height:1%22%20viewBox=%220%200%2024%2024%22%20width=%221em%22%20xmlns=%22http://www.w3.org/2000/svg%22%3E%3Ctitle%3EHuggingFace%3C/title%3E%3Cpath%20d=%22M16.781%203.277c2.997%201.704%204.844%204.851%204.844%208.258%200%20.995-.155%201.955-.443%202.857a1.332%201.332%200%20011.125.4%201.41%201.41%200%2001.2%201.723c.204.165.352.385.428.632l.017.062c.06.222.12.69-.2%201.166.244.37.279.836.093%201.236-.255.57-.893%201.018-2.128%201.5l-.202.078-.131.048c-.478.173-.89.295-1.061.345l-.086.024c-.89.243-1.808.375-2.732.394-1.32%200-2.3-.36-2.923-1.067a9.852%209.852%200%2001-3.18.018C9.778%2021.647%208.802%2022%207.494%2022a11.249%2011.249%200%2001-2.541-.343l-.221-.06-.273-.08a16.574%2016.574%200%2001-1.175-.405c-1.237-.483-1.875-.93-2.13-1.501-.186-.4-.151-.867.093-1.236a1.42%201.42%200%2001-.2-1.166c.069-.273.226-.516.447-.694a1.41%201.41%200%2001.2-1.722c.233-.248.557-.391.917-.407l.078-.001a9.385%209.385%200%2001-.44-2.85c0-3.407%201.847-6.554%204.844-8.258a9.822%209.822%200%20019.687%200zM4.188%2014.758c.125.687%202.357%202.35%202.14%202.707-.19.315-.796-.239-.948-.386l-.041-.04-.168-.147c-.561-.479-2.304-1.9-2.74-1.432-.43.46.119.859%201.055%201.42l.784.467.136.083c1.045.643%201.12.84.95%201.113-.188.295-3.07-2.1-3.34-1.083-.27%201.011%202.942%201.304%202.744%202.006-.2.7-2.265-1.324-2.685-.537-.425.79%202.913%201.718%202.94%201.725l.16.04.175.042c1.227.284%203.565.65%204.435-.604.673-.973.64-1.709-.248-2.61l-.057-.057c-.945-.928-1.495-2.288-1.495-2.288l-.017-.058-.025-.072c-.082-.22-.284-.639-.63-.584-.46.073-.798%201.21.12%201.933l.05.038c.977.721-.195%201.21-.573.534l-.058-.104-.143-.25c-.463-.799-1.282-2.111-1.739-2.397-.532-.332-.907-.148-.782.541zm14.842-.541c-.533.335-1.563%202.074-1.94%202.751a.613.613%200%2001-.687.302.436.436%200%2001-.176-.098.303.303%200%2001-.049-.06l-.014-.028-.008-.02-.007-.019-.003-.013-.003-.017a.289.289%200%2001-.004-.048c0-.12.071-.266.25-.427.026-.024.054-.047.084-.07l.047-.036c.022-.016.043-.032.063-.049.883-.71.573-1.81.131-1.917l-.031-.006-.056-.004a.368.368%200%2000-.062.006l-.028.005-.042.014-.039.017-.028.015-.028.019-.036.027-.023.02c-.173.158-.273.428-.31.542l-.016.054s-.53%201.309-1.439%202.234l-.054.054c-.365.358-.596.69-.702%201.018-.143.437-.066.868.21%201.353.055.097.117.195.187.296.882%201.275%203.282.876%204.494.59l.286-.07.25-.074c.276-.084.736-.233%201.2-.42l.188-.077.065-.028.064-.028.124-.056.081-.038c.529-.252.964-.543.994-.827l.001-.036a.299.299%200%2000-.037-.139c-.094-.176-.271-.212-.491-.168l-.045.01c-.044.01-.09.024-.136.04l-.097.035-.054.022c-.559.23-1.238.705-1.607.745h.006a.452.452%200%2001-.05.003h-.024l-.024-.003-.023-.005c-.068-.016-.116-.06-.14-.142a.22.22%200%2001-.005-.1c.062-.345.958-.595%201.713-.91l.066-.028c.528-.224.97-.483.985-.832v-.04a.47.47%200%2000-.016-.098c-.048-.18-.175-.251-.36-.251-.785%200-2.55%201.36-2.92%201.36-.025%200-.048-.007-.058-.024a.6.6%200%2001-.046-.088c-.1-.238.068-.462%201.06-1.066l.209-.126c.538-.32%201.01-.588%201.341-.831.29-.212.475-.406.503-.6l.003-.028c.008-.113-.038-.227-.147-.344a.266.266%200%2000-.07-.054l-.034-.015-.013-.005a.403.403%200%2000-.13-.02c-.162%200-.369.07-.595.18-.637.313-1.431.952-1.826%201.285l-.249.215-.033.033c-.08.078-.288.27-.493.386l-.071.037-.041.019a.535.535%200%2001-.122.036h.005a.346.346%200%2001-.031.003l.01-.001-.013.001c-.079.005-.145-.021-.19-.095a.113.113%200%2001-.014-.065c.027-.465%202.034-1.991%202.152-2.642l.009-.048c.1-.65-.271-.817-.791-.493zM11.938%202.984c-4.798%200-8.688%203.829-8.688%208.55%200%20.692.083%201.364.24%202.008l.008-.009c.252-.298.612-.46%201.017-.46.355.008.699.117.993.312.22.14.465.384.715.694.261-.372.69-.598%201.15-.605.852%200%201.367.728%201.562%201.383l.047.105.06.127c.192.396.595%201.139%201.143%201.68%201.06%201.04%201.324%202.115.8%203.266a8.865%208.865%200%20002.024-.014c-.505-1.12-.26-2.17.74-3.186l.066-.066c.695-.684%201.157-1.69%201.252-1.912.195-.655.708-1.383%201.56-1.383.46.007.889.233%201.15.605.25-.31.495-.553.718-.694a1.87%201.87%200%2001.99-.312c.357%200%20.682.126.925.36.14-.61.215-1.245.215-1.898%200-4.722-3.89-8.55-8.687-8.55zm1.857%208.926l.439-.212c.553-.264.89-.383.89.152%200%201.093-.771%203.208-3.155%203.262h-.184c-2.325-.052-3.116-2.06-3.156-3.175l-.001-.087c0-1.107%201.452.586%203.25.586.716%200%201.379-.272%201.917-.526zm4.017-3.143c.45%200%20.813.358.813.8%200%20.441-.364.8-.813.8a.806.806%200%2001-.812-.8c0-.442.364-.8.812-.8zm-11.624%200c.448%200%20.812.358.812.8%200%20.441-.364.8-.812.8a.806.806%200%2001-.813-.8c0-.442.364-.8.813-.8zm7.79-.841c.32-.384.846-.54%201.33-.394.483.146.83.564.878%201.06.048.495-.212.97-.659%201.203-.322.168-.447-.477-.767-.585l.002-.003c-.287-.098-.772.362-.925.079a1.215%201.215%200%2001.14-1.36zm-4.323%200c.322.384.377.92.14%201.36-.152.283-.64-.177-.925-.079l.003.003c-.108.036-.194.134-.273.24l-.118.165c-.11.15-.22.262-.377.18a1.226%201.226%200%2001-.658-1.204c.048-.495.395-.913.878-1.059a1.262%201.262%200%20011.33.394z%22%3E%3C/path%3E%3C/svg%3E"},"OpenCode":{"light":"data:image/svg+xml,%3Csvg%20fill=%22%230891B2%22%20fill-rule=%22evenodd%22%20height=%221em%22%20style=%22flex:none;line-height:1%22%20viewBox=%220%200%2024%2024%22%20width=%221em%22%20xmlns=%22http://www.w3.org/2000/svg%22%3E%3Ctitle%3Eopencode%3C/title%3E%3Cpath%20d=%22M16%206H8v12h8V6zm4%2016H4V2h16v20z%22%3E%3C/path%3E%3C/svg%3E","dark":"data:image/svg+xml,%3Csvg%20fill=%22%230891B2%22%20fill-rule=%22evenodd%22%20height=%221em%22%20style=%22flex:none;line-height:1%22%20viewBox=%220%200%2024%2024%22%20width=%221em%22%20xmlns=%22http://www.w3.org/2000/svg%22%3E%3Ctitle%3Eopencode%3C/title%3E%3Cpath%20d=%22M16%206H8v12h8V6zm4%2016H4V2h16v20z%22%3E%3C/path%3E%3C/svg%3E"},"Gitee AI":{"light":"data:image/svg+xml,%3Csvg%20fill=%22%237C3AED%22%20fill-rule=%22evenodd%22%20height=%221em%22%20style=%22flex:none;line-height:1%22%20viewBox=%220%200%2024%2024%22%20width=%221em%22%20xmlns=%22http://www.w3.org/2000/svg%22%3E%3Ctitle%3EGiteeAI%3C/title%3E%3Cpath%20clip-rule=%22evenodd%22%20d=%22M15.08%2014.637c.218.815.46%201.648.72%202.513.238.79-.472%201.1-.755.356a66.148%2066.148%200%2001-.864-2.402c-1.542.775-3.08%201.421-4.823%202.148.697%202.563%201.34%204.707%202.34%206.744.1.003.2.004.302.004%206.628%200%2012-5.373%2012-12%200-2.38-.693-4.598-1.888-6.464-3.117.281-5.881.738-8.42%201.308a39.775%2039.775%200%20001.077%206.587%2097.459%2097.459%200%20003.64-1.718c.92-.46%201.808-.49.312.683a37.134%2037.134%200%2001-3.642%202.24zm6.614-9.712A11.993%2011.993%200%200013.557.1c-.101%201.617-.07%203.658.052%205.603%202.44-.37%205.094-.627%208.085-.778zM11.962%200a37.821%2037.821%200%2000.152%205.948c-1.69.298-3.28.656-4.818%201.074-.067-.767-.1-1.467-.1-2.077a.8.8%200%2000-1.6%200c0%20.742.061%201.594.172%202.518-.767.234-1.524.484-2.276.75a.8.8%200%2000.533%201.508c.65-.23%201.306-.458%201.969-.681.32%201.96.807%204.126%201.368%206.21.098.363.202.726.31%201.086-2.067.712-4.176%201.29-6.105%201.597A11.945%2011.945%200%20010%2012C0%205.385%205.352.02%2011.962%200zM2.515%2019.352a11.985%2011.985%200%20008.237%204.584c-.797-1.463-1.792-3.706-2.628-6.182-1.86.712-3.769%201.208-5.61%201.598zm11.27-5.484a39.054%2039.054%200%2001-1.232-5.302%2015.441%2015.441%200%2001-.277-1.388A74.043%2074.043%200%20007.46%208.556c.248%201.93.666%204.124%201.246%206.277l.264.983v.002l.013.046a56.801%2056.801%200%20002.134-.849%20174.05%20174.05%200%20002.666-1.147z%22%3E%3C/path%3E%3C/svg%3E","dark":"data:image/svg+xml,%3Csvg%20fill=%22%237C3AED%22%20fill-rule=%22evenodd%22%20height=%221em%22%20style=%22flex:none;line-height:1%22%20viewBox=%220%200%2024%2024%22%20width=%221em%22%20xmlns=%22http://www.w3.org/2000/svg%22%3E%3Ctitle%3EGiteeAI%3C/title%3E%3Cpath%20clip-rule=%22evenodd%22%20d=%22M15.08%2014.637c.218.815.46%201.648.72%202.513.238.79-.472%201.1-.755.356a66.148%2066.148%200%2001-.864-2.402c-1.542.775-3.08%201.421-4.823%202.148.697%202.563%201.34%204.707%202.34%206.744.1.003.2.004.302.004%206.628%200%2012-5.373%2012-12%200-2.38-.693-4.598-1.888-6.464-3.117.281-5.881.738-8.42%201.308a39.775%2039.775%200%20001.077%206.587%2097.459%2097.459%200%20003.64-1.718c.92-.46%201.808-.49.312.683a37.134%2037.134%200%2001-3.642%202.24zm6.614-9.712A11.993%2011.993%200%200013.557.1c-.101%201.617-.07%203.658.052%205.603%202.44-.37%205.094-.627%208.085-.778zM11.962%200a37.821%2037.821%200%2000.152%205.948c-1.69.298-3.28.656-4.818%201.074-.067-.767-.1-1.467-.1-2.077a.8.8%200%2000-1.6%200c0%20.742.061%201.594.172%202.518-.767.234-1.524.484-2.276.75a.8.8%200%2000.533%201.508c.65-.23%201.306-.458%201.969-.681.32%201.96.807%204.126%201.368%206.21.098.363.202.726.31%201.086-2.067.712-4.176%201.29-6.105%201.597A11.945%2011.945%200%20010%2012C0%205.385%205.352.02%2011.962%200zM2.515%2019.352a11.985%2011.985%200%20008.237%204.584c-.797-1.463-1.792-3.706-2.628-6.182-1.86.712-3.769%201.208-5.61%201.598zm11.27-5.484a39.054%2039.054%200%2001-1.232-5.302%2015.441%2015.441%200%2001-.277-1.388A74.043%2074.043%200%20007.46%208.556c.248%201.93.666%204.124%201.246%206.277l.264.983v.002l.013.046a56.801%2056.801%200%20002.134-.849%20174.05%20174.05%200%20002.666-1.147z%22%3E%3C/path%3E%3C/svg%3E"},"LongCat":{"light":"data:image/svg+xml,%3Csvg%20fill=%22%232563EB%22%20fill-rule=%22evenodd%22%20height=%221em%22%20style=%22flex:none;line-height:1%22%20viewBox=%220%200%2024%2024%22%20width=%221em%22%20xmlns=%22http://www.w3.org/2000/svg%22%3E%3Ctitle%3ELongCat%3C/title%3E%3Cpath%20clip-rule=%22evenodd%22%20d=%22M.507%2019.883a.507.507%200%2001-.489-.642L4.29%203.745a1.013%201.013%200%20011.533-.578l5.622%203.687a1.013%201.013%200%20001.11%200L18.2%203.165a1.013%201.013%200%20011.532.58l4.25%2015.497a.506.506%200%2001-.49.64H18.07a6.297%206.297%200%20001.53-4.115v-.177a6.09%206.09%200%2000-1.513-4.017l-.697-3.495a.438.438%200%2000-.694-.266L14.07%209.781a.748.748%200%2001-.654.121%205.156%205.156%200%2000-2.833%200%20.746.746%200%2001-.653-.121L7.302%207.81a.435.435%200%2000-.688.269l-.675%203.652a5.36%205.36%200%2000-1.539%203.76v.333c0%201.474.527%202.9%201.488%204.02l.032.038H.507z%22%3E%3C/path%3E%3Cpath%20d=%22M9.213%2016.843h1.52v-3.546h-1.29l-.23%203.546zm5.573%200h-1.52v-3.546h1.29l.23%203.546z%22%3E%3C/path%3E%3C/svg%3E","dark":"data:image/svg+xml,%3Csvg%20fill=%22%232563EB%22%20fill-rule=%22evenodd%22%20height=%221em%22%20style=%22flex:none;line-height:1%22%20viewBox=%220%200%2024%2024%22%20width=%221em%22%20xmlns=%22http://www.w3.org/2000/svg%22%3E%3Ctitle%3ELongCat%3C/title%3E%3Cpath%20clip-rule=%22evenodd%22%20d=%22M.507%2019.883a.507.507%200%2001-.489-.642L4.29%203.745a1.013%201.013%200%20011.533-.578l5.622%203.687a1.013%201.013%200%20001.11%200L18.2%203.165a1.013%201.013%200%20011.532.58l4.25%2015.497a.506.506%200%2001-.49.64H18.07a6.297%206.297%200%20001.53-4.115v-.177a6.09%206.09%200%2000-1.513-4.017l-.697-3.495a.438.438%200%2000-.694-.266L14.07%209.781a.748.748%200%2001-.654.121%205.156%205.156%200%2000-2.833%200%20.746.746%200%2001-.653-.121L7.302%207.81a.435.435%200%2000-.688.269l-.675%203.652a5.36%205.36%200%2000-1.539%203.76v.333c0%201.474.527%202.9%201.488%204.02l.032.038H.507z%22%3E%3C/path%3E%3Cpath%20d=%22M9.213%2016.843h1.52v-3.546h-1.29l-.23%203.546zm5.573%200h-1.52v-3.546h1.29l.23%203.546z%22%3E%3C/path%3E%3C/svg%3E"},"Ling":{"light":"data:image/svg+xml,%3Csvg%20fill=%22%23C2410C%22%20fill-rule=%22evenodd%22%20height=%221em%22%20style=%22flex:none;line-height:1%22%20viewBox=%220%200%2024%2024%22%20width=%221em%22%20xmlns=%22http://www.w3.org/2000/svg%22%3E%3Ctitle%3ELing%3C/title%3E%3Cpath%20d=%22M9.561%200.074a0.46%200.46%200%200%201%200.517%200.011l2.848%201.357a0.222%200.222%200%200%201-0.033%200.374C9.008%203.93%206.663%205.994%205.43%207.997c-0.798%201.296-2.264%204.83-0.937%208.02%201.375%203.301%204.49%204.493%206.797%204.493%201.743%200%202.927-0.522%204.13-1.334%203.262-2.204%203.638-6.503%201.21-9.46a10%2010%200%200%201%202.2%202.902%206.5%206.5%200%200%200-0.72-1.664c-0.72-1.176-1.688-2.163-3.056-2.849-3.045-1.526-9.397-0.79-10.397%205.78%200.1-4.557%203.127-7.416%205.868-8.3a9.7%209.7%200%200%201%204.654-0.314c2.029-1.639%204.272-2.376%205.075-2.601a0.53%200.53%200%200%201%200.522%200.137c0.23%200.23%200.63%200.632%201.142%201.135h0.003c0.152%200.15%200.073%200.41-0.138%200.45-1.974%200.38-3.322%200.755-4.746%201.412%201.727%200.698%203.206%201.92%204.108%203.606a0.367%200.367%200%200%201-0.199%200.52l-1.207%200.437c1.061%201.8%201.334%204.006%200.813%206.266-0.884%203.843-3.845%206.562-7.626%207.209a9.5%209.5%200%200%201-1.756%200.157%200.37%200.37%200%200%201-0.363-0.341%200.36%200.36%200%200%201-0.043-0.245l0.231-1.295c-1.055-0.074-2.045-0.248-3.036-0.648C2.077%2019.094%201.46%2013.297%202.304%209.785%203.4%205.23%206.766%201.78%209.561%200.074%22%3E%3C/path%3E%3C/svg%3E","dark":"data:image/svg+xml,%3Csvg%20fill=%22%23C2410C%22%20fill-rule=%22evenodd%22%20height=%221em%22%20style=%22flex:none;line-height:1%22%20viewBox=%220%200%2024%2024%22%20width=%221em%22%20xmlns=%22http://www.w3.org/2000/svg%22%3E%3Ctitle%3ELing%3C/title%3E%3Cpath%20d=%22M9.561%200.074a0.46%200.46%200%200%201%200.517%200.011l2.848%201.357a0.222%200.222%200%200%201-0.033%200.374C9.008%203.93%206.663%205.994%205.43%207.997c-0.798%201.296-2.264%204.83-0.937%208.02%201.375%203.301%204.49%204.493%206.797%204.493%201.743%200%202.927-0.522%204.13-1.334%203.262-2.204%203.638-6.503%201.21-9.46a10%2010%200%200%201%202.2%202.902%206.5%206.5%200%200%200-0.72-1.664c-0.72-1.176-1.688-2.163-3.056-2.849-3.045-1.526-9.397-0.79-10.397%205.78%200.1-4.557%203.127-7.416%205.868-8.3a9.7%209.7%200%200%201%204.654-0.314c2.029-1.639%204.272-2.376%205.075-2.601a0.53%200.53%200%200%201%200.522%200.137c0.23%200.23%200.63%200.632%201.142%201.135h0.003c0.152%200.15%200.073%200.41-0.138%200.45-1.974%200.38-3.322%200.755-4.746%201.412%201.727%200.698%203.206%201.92%204.108%203.606a0.367%200.367%200%200%201-0.199%200.52l-1.207%200.437c1.061%201.8%201.334%204.006%200.813%206.266-0.884%203.843-3.845%206.562-7.626%207.209a9.5%209.5%200%200%201-1.756%200.157%200.37%200.37%200%200%201-0.363-0.341%200.36%200.36%200%200%201-0.043-0.245l0.231-1.295c-1.055-0.074-2.045-0.248-3.036-0.648C2.077%2019.094%201.46%2013.297%202.304%209.785%203.4%205.23%206.766%201.78%209.561%200.074%22%3E%3C/path%3E%3C/svg%3E"},"Reka":{"light":"data:image/svg+xml,%3Csvg%20fill=%22%23059669%22%20fill-rule=%22evenodd%22%20height=%221em%22%20style=%22flex:none;line-height:1%22%20viewBox=%220%200%2024%2024%22%20width=%221em%22%20xmlns=%22http://www.w3.org/2000/svg%22%3E%3Ctitle%3EReka%3C/title%3E%3Cpath%20d=%22M3.662.014C4.347.004%205.052.012%205.74.012h3.9q1.01.006%202.02-.006c-.005.87-.01%201.779%200%202.647-.16-.027-.593-.018-.774-.018H4.943l-1.408.001c-.263.001-.595.01-.852-.004.014%201.216.002%202.455.002%203.673v4.681c0%20.185-.008.48.016.656-.834-.039-1.849-.005-2.7-.01.032-.717.008-1.576.008-2.307V3.69c-.001-.44-.023-.812.065-1.246.11-.557.377-1.07.77-1.481A3%203%200%200%201%202.756.03c.245-.022.644-.01.905-.017M23.74%2011.641c-.688-.03-1.54-.007-2.237-.007H15.92c-.853.001-1.373.024-2.139-.422a3.02%203.02%200%200%201-1.4-1.842c-.146-.553-.1-1.285-.1-1.863V5.299l-.002-1.535c0-.37-.011-.794.035-1.156.053-.388.183-.763.382-1.1A3.01%203.01%200%200%201%2015.102.013c.387-.022.869-.01%201.261-.01l2.224.001h1.607c.88-.001%201.449-.037%202.237.426a3.02%203.02%200%200%201%201.293%201.544c.08.217.12.395.177.615v1.027c-.072.167-.123.472-.227.719a3.04%203.04%200%200%201-1.176%201.375c-.318.204-.74.34-1.098.467l-.951.34-3.181%201.132c-.552.196-1.205.41-1.74.626-.03-.646.008-1.316-.007-1.965-.005-.2-.006-.432.01-.632.463-.189.96-.368%201.43-.547l2.719-1.038c.357-.137.717-.268%201.074-.405.174-.067.352-.135.433-.315.186-.414-.112-.74-.538-.739q-.555%200-1.106.003l-2.161-.002H16.12c-.248%200-.506-.008-.752.018-.124.008-.327.157-.362.28-.07.246-.052.597-.052.852l.003%201.055V7.5c0%20.497.01%201.024-.004%201.519.334-.026.816-.01%201.164-.01H18.2c1.825%200%203.726-.027%205.547.004-.023.228-.01.686-.01.93zm-11.272.779h7.626c.361%200%20.814-.013%201.165.03a3.04%203.04%200%200%201%202.45%201.907c.084.215.13.419.192.64v6.485c-.052.193-.097.395-.166.58a3.05%203.05%200%200%201-1.352%201.597c-.154.088-.241.13-.404.19-.078.028-.388.124-.43.15h-6.903c-.062-.036-.497-.172-.648-.245A3.05%203.05%200%200%201%2012.444%2022c-.47-1.365.06-2.953%201.31-3.685.356-.209.745-.33%201.132-.467l1.37-.486c1.465-.52%202.956-1.073%204.424-1.571-.029.83.016%201.742-.005%202.588-.121.057-.337.13-.468.18l-.894.34-2.847%201.085c-.158.06-.327.118-.481.181-.188.098-.73.226-.864.37-.36.388-.097.89.415.887.42-.003.772%200%201.15-.002l1.988.001h1.367c.256%200%20.52.008.774-.013.21-.018.393-.228.416-.432.026-.229.018-.458.017-.688l-.001-1.018v-2.639c0-.516-.008-1.054.006-1.568-1.352-.03-2.79-.007-4.148-.007-1.532%200-3.117-.02-4.645.007.015-.292.006-.642.006-.939zm-4.554.015c.33-.021.705-.002%201.04-.008.847-.016%201.738.023%202.582-.002-.195.22-.434.43-.646.637l-1.017%201.002L7.04%2016.84c-.435.427-.912.866-1.333%201.304.124.154.418.431.571.585l1.084%201.082%202.176%202.168q1.034%201%202.047%202.022H7.849c-.248-.236-.495-.493-.74-.735l-1.632-1.6q-.595-.569-1.18-1.147c-.27-.268-.57-.541-.775-.86a2.656%202.656%200%200%201%20.338-3.262c.21-.22.454-.447.672-.66l1.58-1.548q.611-.612%201.239-1.21c.137-.134.427-.44.564-.543m-7.909-.001c.755-.032%201.53.006%202.286-.008.13-.002.273-.003.403.002-.029.317-.01.988-.01%201.338v2.557L2.686%2024H.007l.002-7.917V13.61c0-.34-.018-.847-.003-1.175%22%3E%3C/path%3E%3C/svg%3E","dark":"data:image/svg+xml,%3Csvg%20fill=%22%23059669%22%20fill-rule=%22evenodd%22%20height=%221em%22%20style=%22flex:none;line-height:1%22%20viewBox=%220%200%2024%2024%22%20width=%221em%22%20xmlns=%22http://www.w3.org/2000/svg%22%3E%3Ctitle%3EReka%3C/title%3E%3Cpath%20d=%22M3.662.014C4.347.004%205.052.012%205.74.012h3.9q1.01.006%202.02-.006c-.005.87-.01%201.779%200%202.647-.16-.027-.593-.018-.774-.018H4.943l-1.408.001c-.263.001-.595.01-.852-.004.014%201.216.002%202.455.002%203.673v4.681c0%20.185-.008.48.016.656-.834-.039-1.849-.005-2.7-.01.032-.717.008-1.576.008-2.307V3.69c-.001-.44-.023-.812.065-1.246.11-.557.377-1.07.77-1.481A3%203%200%200%201%202.756.03c.245-.022.644-.01.905-.017M23.74%2011.641c-.688-.03-1.54-.007-2.237-.007H15.92c-.853.001-1.373.024-2.139-.422a3.02%203.02%200%200%201-1.4-1.842c-.146-.553-.1-1.285-.1-1.863V5.299l-.002-1.535c0-.37-.011-.794.035-1.156.053-.388.183-.763.382-1.1A3.01%203.01%200%200%201%2015.102.013c.387-.022.869-.01%201.261-.01l2.224.001h1.607c.88-.001%201.449-.037%202.237.426a3.02%203.02%200%200%201%201.293%201.544c.08.217.12.395.177.615v1.027c-.072.167-.123.472-.227.719a3.04%203.04%200%200%201-1.176%201.375c-.318.204-.74.34-1.098.467l-.951.34-3.181%201.132c-.552.196-1.205.41-1.74.626-.03-.646.008-1.316-.007-1.965-.005-.2-.006-.432.01-.632.463-.189.96-.368%201.43-.547l2.719-1.038c.357-.137.717-.268%201.074-.405.174-.067.352-.135.433-.315.186-.414-.112-.74-.538-.739q-.555%200-1.106.003l-2.161-.002H16.12c-.248%200-.506-.008-.752.018-.124.008-.327.157-.362.28-.07.246-.052.597-.052.852l.003%201.055V7.5c0%20.497.01%201.024-.004%201.519.334-.026.816-.01%201.164-.01H18.2c1.825%200%203.726-.027%205.547.004-.023.228-.01.686-.01.93zm-11.272.779h7.626c.361%200%20.814-.013%201.165.03a3.04%203.04%200%200%201%202.45%201.907c.084.215.13.419.192.64v6.485c-.052.193-.097.395-.166.58a3.05%203.05%200%200%201-1.352%201.597c-.154.088-.241.13-.404.19-.078.028-.388.124-.43.15h-6.903c-.062-.036-.497-.172-.648-.245A3.05%203.05%200%200%201%2012.444%2022c-.47-1.365.06-2.953%201.31-3.685.356-.209.745-.33%201.132-.467l1.37-.486c1.465-.52%202.956-1.073%204.424-1.571-.029.83.016%201.742-.005%202.588-.121.057-.337.13-.468.18l-.894.34-2.847%201.085c-.158.06-.327.118-.481.181-.188.098-.73.226-.864.37-.36.388-.097.89.415.887.42-.003.772%200%201.15-.002l1.988.001h1.367c.256%200%20.52.008.774-.013.21-.018.393-.228.416-.432.026-.229.018-.458.017-.688l-.001-1.018v-2.639c0-.516-.008-1.054.006-1.568-1.352-.03-2.79-.007-4.148-.007-1.532%200-3.117-.02-4.645.007.015-.292.006-.642.006-.939zm-4.554.015c.33-.021.705-.002%201.04-.008.847-.016%201.738.023%202.582-.002-.195.22-.434.43-.646.637l-1.017%201.002L7.04%2016.84c-.435.427-.912.866-1.333%201.304.124.154.418.431.571.585l1.084%201.082%202.176%202.168q1.034%201%202.047%202.022H7.849c-.248-.236-.495-.493-.74-.735l-1.632-1.6q-.595-.569-1.18-1.147c-.27-.268-.57-.541-.775-.86a2.656%202.656%200%200%201%20.338-3.262c.21-.22.454-.447.672-.66l1.58-1.548q.611-.612%201.239-1.21c.137-.134.427-.44.564-.543m-7.909-.001c.755-.032%201.53.006%202.286-.008.13-.002.273-.003.403.002-.029.317-.01.988-.01%201.338v2.557L2.686%2024H.007l.002-7.917V13.61c0-.34-.018-.847-.003-1.175%22%3E%3C/path%3E%3C/svg%3E"},"AI21":{"light":"data:image/svg+xml,%3Csvg%20fill=%22%230F766E%22%20fill-rule=%22evenodd%22%20height=%221em%22%20style=%22flex:none;line-height:1%22%20viewBox=%220%200%2024%2024%22%20width=%221em%22%20xmlns=%22http://www.w3.org/2000/svg%22%3E%3Ctitle%3EAI21%3C/title%3E%3Cpath%20d=%22M6.47%2017l-.367-1.189H2.718L2.35%2017H0l3.398-9.789h2.026L8.864%2017H6.47zm-2.052-6.993l-1.17%204.028H5.56l-1.142-4.028zm4.707-2.796h2.23V17h-2.23V7.211zM11.955%2015c.1-.483.277-.946.524-1.37.214-.359.482-.68.795-.951.32-.273.658-.52%201.013-.741.28-.168.54-.33.781-.483.222-.14.433-.296.632-.468.172-.148.317-.325.428-.525.107-.199.16-.423.157-.65%200-.392-.104-.674-.313-.846a1.176%201.176%200%2000-.775-.259%201.207%201.207%200%2000-.863.329c-.231.219-.347.585-.347%201.098H11.8a3.387%203.387%200%2001.224-1.245c.146-.377.371-.716.66-.993.306-.29.667-.514%201.06-.657A4.04%204.04%200%200115.183%207c.42-.002.84.057%201.244.175.376.107.73.287%201.04.531.305.246.55.562.714.923.185.419.275.875.265%201.335.005.39-.084.774-.259%201.12-.167.328-.38.63-.632.894-.246.259-.517.49-.808.693-.29.2-.554.37-.789.51-.326.224-.596.417-.809.58a3.872%203.872%200%2000-.51.455%201.229%201.229%200%2000-.265.434%201.633%201.633%200%2000-.074.517h4.078V17h-6.606a9.24%209.24%200%2001.183-2zM18.8%208.93a5.05%205.05%200%20001.135-.105c.25-.049.484-.156.686-.314.163-.139.28-.324.34-.532.068-.25.1-.51.095-.77H23V17h-2.243v-6.475H18.8V8.93z%22%3E%3C/path%3E%3C/svg%3E","dark":"data:image/svg+xml,%3Csvg%20fill=%22%230F766E%22%20fill-rule=%22evenodd%22%20height=%221em%22%20style=%22flex:none;line-height:1%22%20viewBox=%220%200%2024%2024%22%20width=%221em%22%20xmlns=%22http://www.w3.org/2000/svg%22%3E%3Ctitle%3EAI21%3C/title%3E%3Cpath%20d=%22M6.47%2017l-.367-1.189H2.718L2.35%2017H0l3.398-9.789h2.026L8.864%2017H6.47zm-2.052-6.993l-1.17%204.028H5.56l-1.142-4.028zm4.707-2.796h2.23V17h-2.23V7.211zM11.955%2015c.1-.483.277-.946.524-1.37.214-.359.482-.68.795-.951.32-.273.658-.52%201.013-.741.28-.168.54-.33.781-.483.222-.14.433-.296.632-.468.172-.148.317-.325.428-.525.107-.199.16-.423.157-.65%200-.392-.104-.674-.313-.846a1.176%201.176%200%2000-.775-.259%201.207%201.207%200%2000-.863.329c-.231.219-.347.585-.347%201.098H11.8a3.387%203.387%200%2001.224-1.245c.146-.377.371-.716.66-.993.306-.29.667-.514%201.06-.657A4.04%204.04%200%200115.183%207c.42-.002.84.057%201.244.175.376.107.73.287%201.04.531.305.246.55.562.714.923.185.419.275.875.265%201.335.005.39-.084.774-.259%201.12-.167.328-.38.63-.632.894-.246.259-.517.49-.808.693-.29.2-.554.37-.789.51-.326.224-.596.417-.809.58a3.872%203.872%200%2000-.51.455%201.229%201.229%200%2000-.265.434%201.633%201.633%200%2000-.074.517h4.078V17h-6.606a9.24%209.24%200%2001.183-2zM18.8%208.93a5.05%205.05%200%20001.135-.105c.25-.049.484-.156.686-.314.163-.139.28-.324.34-.532.068-.25.1-.51.095-.77H23V17h-2.243v-6.475H18.8V8.93z%22%3E%3C/path%3E%3C/svg%3E"},"Upstage":{"light":"data:image/svg+xml,%3Csvg%20fill=%22%234F46E5%22%20fill-rule=%22evenodd%22%20height=%221em%22%20style=%22flex:none;line-height:1%22%20viewBox=%220%200%2024%2024%22%20width=%221em%22%20xmlns=%22http://www.w3.org/2000/svg%22%3E%3Ctitle%3EUpsate%3C/title%3E%3Cpath%20d=%22M19.763%200l-.373%201.297h2.594L22.354%200h-2.591z%22%3E%3C/path%3E%3Cpath%20d=%22M16.192%202.27l-.376%201.298h5.52l.37-1.298h-5.514z%22%3E%3C/path%3E%3Cpath%20d=%22M12.897%204.54l-.377%201.298h8.167l.37-1.297h-8.16z%22%3E%3C/path%3E%3Cpath%20d=%22M2.85%206.81l-.377%201.298h17.565l.37-1.297H2.85z%22%3E%3C/path%3E%3Cpath%20d=%22M3.884%209.081l-.376%201.297H19.39l.37-1.297H3.883z%22%3E%3C/path%3E%3Cpath%20d=%22M4.088%2024l.376-1.297H1.866L1.5%2024h2.588z%22%3E%3C/path%3E%3Cpath%20d=%22M7.662%2021.73l.376-1.298H2.515L2.15%2021.73h5.513z%22%3E%3C/path%3E%3Cpath%20d=%22M10.957%2019.46l.377-1.298h-8.17l-.367%201.297h8.16z%22%3E%3C/path%3E%3Cpath%20d=%22M21.005%2017.19l.376-1.298H3.812l-.366%201.297h17.559z%22%3E%3C/path%3E%3Cpath%20d=%22M19.967%2014.919l.376-1.297H4.461l-.366%201.297h15.872z%22%3E%3C/path%3E%3Cpath%20d=%22M18.787%2012.649l.376-1.298H4.26l-.366%201.298h14.893z%22%3E%3C/path%3E%3C/svg%3E","dark":"data:image/svg+xml,%3Csvg%20fill=%22%234F46E5%22%20fill-rule=%22evenodd%22%20height=%221em%22%20style=%22flex:none;line-height:1%22%20viewBox=%220%200%2024%2024%22%20width=%221em%22%20xmlns=%22http://www.w3.org/2000/svg%22%3E%3Ctitle%3EUpsate%3C/title%3E%3Cpath%20d=%22M19.763%200l-.373%201.297h2.594L22.354%200h-2.591z%22%3E%3C/path%3E%3Cpath%20d=%22M16.192%202.27l-.376%201.298h5.52l.37-1.298h-5.514z%22%3E%3C/path%3E%3Cpath%20d=%22M12.897%204.54l-.377%201.298h8.167l.37-1.297h-8.16z%22%3E%3C/path%3E%3Cpath%20d=%22M2.85%206.81l-.377%201.298h17.565l.37-1.297H2.85z%22%3E%3C/path%3E%3Cpath%20d=%22M3.884%209.081l-.376%201.297H19.39l.37-1.297H3.883z%22%3E%3C/path%3E%3Cpath%20d=%22M4.088%2024l.376-1.297H1.866L1.5%2024h2.588z%22%3E%3C/path%3E%3Cpath%20d=%22M7.662%2021.73l.376-1.298H2.515L2.15%2021.73h5.513z%22%3E%3C/path%3E%3Cpath%20d=%22M10.957%2019.46l.377-1.298h-8.17l-.367%201.297h8.16z%22%3E%3C/path%3E%3Cpath%20d=%22M21.005%2017.19l.376-1.298H3.812l-.366%201.297h17.559z%22%3E%3C/path%3E%3Cpath%20d=%22M19.967%2014.919l.376-1.297H4.461l-.366%201.297h15.872z%22%3E%3C/path%3E%3Cpath%20d=%22M18.787%2012.649l.376-1.298H4.26l-.366%201.298h14.893z%22%3E%3C/path%3E%3C/svg%3E"},"TII":{"light":"data:image/svg+xml,%3Csvg%20fill=%22%230891B2%22%20fill-rule=%22evenodd%22%20height=%221em%22%20style=%22flex:none;line-height:1%22%20viewBox=%220%200%2024%2024%22%20width=%221em%22%20xmlns=%22http://www.w3.org/2000/svg%22%3E%3Ctitle%3ETechnology%20Innovation%20Institute%3C/title%3E%3Cpath%20d=%22M11.098%207.563H4.75V9.77h1.77v6.668h2.807V9.77h1.77V7.563zM14.812%207.563h-2.807v8.875h2.807V7.563zM19.433%207.563h-2.807v8.875h2.807V7.563z%22%3E%3C/path%3E%3Cpath%20d=%22M12%2024v-1.055c3.01%200%205.613-1.079%207.737-3.208%202.123-2.13%203.209-4.727%203.209-7.737%200-3.009-1.08-5.607-3.209-7.736-2.128-2.13-4.732-3.21-7.736-3.21V0c3.294%200%206.148%201.184%208.482%203.518C22.817%205.852%2024%208.706%2024%2012c0%203.295-1.183%206.155-3.518%208.483C18.147%2022.811%2015.3%2024%2012.001%2024z%22%3E%3C/path%3E%3C/svg%3E","dark":"data:image/svg+xml,%3Csvg%20fill=%22%230891B2%22%20fill-rule=%22evenodd%22%20height=%221em%22%20style=%22flex:none;line-height:1%22%20viewBox=%220%200%2024%2024%22%20width=%221em%22%20xmlns=%22http://www.w3.org/2000/svg%22%3E%3Ctitle%3ETechnology%20Innovation%20Institute%3C/title%3E%3Cpath%20d=%22M11.098%207.563H4.75V9.77h1.77v6.668h2.807V9.77h1.77V7.563zM14.812%207.563h-2.807v8.875h2.807V7.563zM19.433%207.563h-2.807v8.875h2.807V7.563z%22%3E%3C/path%3E%3Cpath%20d=%22M12%2024v-1.055c3.01%200%205.613-1.079%207.737-3.208%202.123-2.13%203.209-4.727%203.209-7.737%200-3.009-1.08-5.607-3.209-7.736-2.128-2.13-4.732-3.21-7.736-3.21V0c3.294%200%206.148%201.184%208.482%203.518C22.817%205.852%2024%208.706%2024%2012c0%203.295-1.183%206.155-3.518%208.483C18.147%2022.811%2015.3%2024%2012.001%2024z%22%3E%3C/path%3E%3C/svg%3E"},"Sakana":{"light":"data:image/svg+xml,%3Csvg%20fill=%22%237C3AED%22%20fill-rule=%22evenodd%22%20height=%221em%22%20style=%22flex:none;line-height:1%22%20viewBox=%220%200%2024%2024%22%20width=%221em%22%20xmlns=%22http://www.w3.org/2000/svg%22%3E%3Ctitle%3Esakana.ai%3C/title%3E%3Cpath%20d=%22M15.568%203.02c2.621-.149%205.368.572%207.88%201.323.455.136.642.493.511.962-.425%201.516-.763%203.077-1.34%204.545a17.1%2017.1%200%200%201-6.447%207.982c-1.461.975-3.224%201.864-4.747%202.784-.774.431-1.528.91-2.313%201.32-.301.158-.741.006-.912-.278a.75.75%200%200%201-.082-.572c.126-.468%201.603-1.182%202.066-1.448l3.579-2.058c-1.09-1.631-2.457-2.584-4.184-3.438-.644%202.639-2.597%204.942-4.872%206.37q-.066.045-.135.084a.863.863%200%200%201-1.136-.295c-.141-.225.04-.672.253-.794%202.31-1.324%203.771-3.218%204.552-5.757-1.557-.467-3.522-.362-5.072.091-.833.244-1.463.574-2.23.953a.71.71%200%200%201-.8-.278c-.626-.937%201.02-1.5%201.699-1.763a10.94%2010.94%200%200%201%206.684-.427c.16-1.959-.05-3.54-.89-5.333-.818.47-5.133%203.08-5.6%203.14A.73.73%200%200%201%201.5%209.98a.7.7%200%200%201-.263-.484.78.78%200%200%201%20.181-.558c.297-.33%202.11-1.277%202.616-1.566%204.122-2.362%206.6-4.11%2011.533-4.351M8.89%206.223c.921%201.992%201.411%204.3.989%206.484%202.027.813%203.96%202.242%205.13%204.107l.477-.309c2.955-2.1%204.873-4.56%206.052-8.024.332-.974.533-1.999.832-2.969-2.234-.589-4.6-1.284-6.955-1.063-2.413.164-4.356.675-6.525%201.774%22%3E%3C/path%3E%3C/svg%3E","dark":"data:image/svg+xml,%3Csvg%20fill=%22%237C3AED%22%20fill-rule=%22evenodd%22%20height=%221em%22%20style=%22flex:none;line-height:1%22%20viewBox=%220%200%2024%2024%22%20width=%221em%22%20xmlns=%22http://www.w3.org/2000/svg%22%3E%3Ctitle%3Esakana.ai%3C/title%3E%3Cpath%20d=%22M15.568%203.02c2.621-.149%205.368.572%207.88%201.323.455.136.642.493.511.962-.425%201.516-.763%203.077-1.34%204.545a17.1%2017.1%200%200%201-6.447%207.982c-1.461.975-3.224%201.864-4.747%202.784-.774.431-1.528.91-2.313%201.32-.301.158-.741.006-.912-.278a.75.75%200%200%201-.082-.572c.126-.468%201.603-1.182%202.066-1.448l3.579-2.058c-1.09-1.631-2.457-2.584-4.184-3.438-.644%202.639-2.597%204.942-4.872%206.37q-.066.045-.135.084a.863.863%200%200%201-1.136-.295c-.141-.225.04-.672.253-.794%202.31-1.324%203.771-3.218%204.552-5.757-1.557-.467-3.522-.362-5.072.091-.833.244-1.463.574-2.23.953a.71.71%200%200%201-.8-.278c-.626-.937%201.02-1.5%201.699-1.763a10.94%2010.94%200%200%201%206.684-.427c.16-1.959-.05-3.54-.89-5.333-.818.47-5.133%203.08-5.6%203.14A.73.73%200%200%201%201.5%209.98a.7.7%200%200%201-.263-.484.78.78%200%200%201%20.181-.558c.297-.33%202.11-1.277%202.616-1.566%204.122-2.362%206.6-4.11%2011.533-4.351M8.89%206.223c.921%201.992%201.411%204.3.989%206.484%202.027.813%203.96%202.242%205.13%204.107l.477-.309c2.955-2.1%204.873-4.56%206.052-8.024.332-.974.533-1.999.832-2.969-2.234-.589-4.6-1.284-6.955-1.063-2.413.164-4.356.675-6.525%201.774%22%3E%3C/path%3E%3C/svg%3E"},"Liquid":{"light":"data:image/svg+xml,%3Csvg%20fill=%22%232563EB%22%20fill-rule=%22evenodd%22%20height=%221em%22%20style=%22flex:none;line-height:1%22%20viewBox=%220%200%2024%2024%22%20width=%221em%22%20xmlns=%22http://www.w3.org/2000/svg%22%3E%3Ctitle%3ELiquid%3C/title%3E%3Cpath%20d=%22M12.028%208.546l-.008.005%203.03%205.25a3.94%203.94%200%2001.643%202.162c0%20.754-.212%201.46-.58%202.062l6.173-1.991L11.63%200%209.304%203.872l2.724%204.674zM6.837%2024l4.85-4.053h-.013c-2.219%200-4.017-1.784-4.017-3.984%200-.794.235-1.534.64-2.156l2.865-4.976-2.381-4.087L2%2016.034%206.83%2024h.007zM13.737%2019.382h-.001L8.222%2024h8.182l4.148-6.769-6.815%202.151z%22%3E%3C/path%3E%3C/svg%3E","dark":"data:image/svg+xml,%3Csvg%20fill=%22%232563EB%22%20fill-rule=%22evenodd%22%20height=%221em%22%20style=%22flex:none;line-height:1%22%20viewBox=%220%200%2024%2024%22%20width=%221em%22%20xmlns=%22http://www.w3.org/2000/svg%22%3E%3Ctitle%3ELiquid%3C/title%3E%3Cpath%20d=%22M12.028%208.546l-.008.005%203.03%205.25a3.94%203.94%200%2001.643%202.162c0%20.754-.212%201.46-.58%202.062l6.173-1.991L11.63%200%209.304%203.872l2.724%204.674zM6.837%2024l4.85-4.053h-.013c-2.219%200-4.017-1.784-4.017-3.984%200-.794.235-1.534.64-2.156l2.865-4.976-2.381-4.087L2%2016.034%206.83%2024h.007zM13.737%2019.382h-.001L8.222%2024h8.182l4.148-6.769-6.815%202.151z%22%3E%3C/path%3E%3C/svg%3E"},"RWKV":{"light":"data:image/svg+xml,%3Csvg%20fill=%22%23C2410C%22%20fill-rule=%22evenodd%22%20height=%221em%22%20style=%22flex:none;line-height:1%22%20viewBox=%220%200%2024%2024%22%20width=%221em%22%20xmlns=%22http://www.w3.org/2000/svg%22%3E%3Ctitle%3ERWKV%3C/title%3E%3Cpath%20d=%22M15.127%2021.824c.093.299.339.553.345.896.022.107-.051.417-.168.21-.249-.832-.33-.035-1.065-1.184-.158-.313-.429-.055-.663-.04-.694-.228-.49-.293-.905.3-.315.088-.049-.643.101-.724.29-.248.749-.086.917-.356.282-1.143-.64-2.567-1.158-3.55-.169-.264.013-.577-.025-.862-.15-.408-.188-.302-.049-.734-.227-.473-.863.266-1.22.255-.285.004-.523-.45-.893-.48-1.335.004-2.581.808-3.926.671a1.228%201.228%200%2000-.681.215c-.414.222-.909.203-1.288.522-.119.095-.27.104-.414.098-.27.04-.477.37-.784.34-.312-.109-.566.079-.86.057-.34-.285-.781-.057-1.174.008a.286.286%200%2001-.308-.05c-.09-.072-.264-.082-.324-.177-.03-.059.028-.145.1-.204.527-.405%201.137-.666%201.72-.974%201.146-.594%202.118-1.463%203.16-2.218.066-.05.085-.12-.035-.119-1.612.135-3.146%201.048-4.74%201.012-.176.023-.339.127-.522.15-.876-.185.65-1.16.954-1.261%201.704-.711%203.598-.843%205.184-1.836.188-.132-.17-.268-.004-.53.39-1.29%201.576-1.805%202.735-2.184.594-.231%201.137-.672%201.797-.679.325.016.634-.113.852-.36%201.163-1.071%202.442-2.012%203.674-2.999%201.413-1.783%202.282-5.175%205.216-3.656.92.395%201.974.365%202.807.976.297.189.857.765.236.85-1.702.291-2.552-.23-2.63%201.454-.03.39.064.75-.158%201.086-.014.694.352%201.508-.084%202.129-.364.63-.078%201.413-.38%202.047-.22.534-.65.93-1.049%201.323-1.304%201.63-2.266%203.476-2.589%205.572-.122.627-.478%201.56.097%202.056.607.612%201.25%201.458%202.18%201.012.306-.14.884-.189.84.274-.05.083-.258-.098-.371-.056-.16.102.072.316.029.465-.022.14-.134.12-.23.054-.281-.112-.685.002-1.005-.01-.258.045-.512.162-.762.05-.116-.049-.229-.1-.356-.103-.39-.022-.884.182-1.103-.147-.242-.454-.293-.104-.532.048-.235-.015-.067-.35.014-.46.249-.57%201.846.517%201.183-.432-2.29-2.01-.777-2.686-1.646-2.69-.17-.089-.103-.405-.366-.173-.335.35-.46-.098-.46-.4-.04-.175-.177-.3-.125-.479.022-.39-.496.085-.38.41.057.616-.132%201.225-.102%201.833.24%201.276.41%202.897%201.864%203.276.177.076.463.432.253.565-.093-.01-.16-.11-.243-.153-.116-.078-.257.009-.378.018-.034.008-.088.007-.1.046l-.003.002z%22%3E%3C/path%3E%3C/svg%3E","dark":"data:image/svg+xml,%3Csvg%20fill=%22%23C2410C%22%20fill-rule=%22evenodd%22%20height=%221em%22%20style=%22flex:none;line-height:1%22%20viewBox=%220%200%2024%2024%22%20width=%221em%22%20xmlns=%22http://www.w3.org/2000/svg%22%3E%3Ctitle%3ERWKV%3C/title%3E%3Cpath%20d=%22M15.127%2021.824c.093.299.339.553.345.896.022.107-.051.417-.168.21-.249-.832-.33-.035-1.065-1.184-.158-.313-.429-.055-.663-.04-.694-.228-.49-.293-.905.3-.315.088-.049-.643.101-.724.29-.248.749-.086.917-.356.282-1.143-.64-2.567-1.158-3.55-.169-.264.013-.577-.025-.862-.15-.408-.188-.302-.049-.734-.227-.473-.863.266-1.22.255-.285.004-.523-.45-.893-.48-1.335.004-2.581.808-3.926.671a1.228%201.228%200%2000-.681.215c-.414.222-.909.203-1.288.522-.119.095-.27.104-.414.098-.27.04-.477.37-.784.34-.312-.109-.566.079-.86.057-.34-.285-.781-.057-1.174.008a.286.286%200%2001-.308-.05c-.09-.072-.264-.082-.324-.177-.03-.059.028-.145.1-.204.527-.405%201.137-.666%201.72-.974%201.146-.594%202.118-1.463%203.16-2.218.066-.05.085-.12-.035-.119-1.612.135-3.146%201.048-4.74%201.012-.176.023-.339.127-.522.15-.876-.185.65-1.16.954-1.261%201.704-.711%203.598-.843%205.184-1.836.188-.132-.17-.268-.004-.53.39-1.29%201.576-1.805%202.735-2.184.594-.231%201.137-.672%201.797-.679.325.016.634-.113.852-.36%201.163-1.071%202.442-2.012%203.674-2.999%201.413-1.783%202.282-5.175%205.216-3.656.92.395%201.974.365%202.807.976.297.189.857.765.236.85-1.702.291-2.552-.23-2.63%201.454-.03.39.064.75-.158%201.086-.014.694.352%201.508-.084%202.129-.364.63-.078%201.413-.38%202.047-.22.534-.65.93-1.049%201.323-1.304%201.63-2.266%203.476-2.589%205.572-.122.627-.478%201.56.097%202.056.607.612%201.25%201.458%202.18%201.012.306-.14.884-.189.84.274-.05.083-.258-.098-.371-.056-.16.102.072.316.029.465-.022.14-.134.12-.23.054-.281-.112-.685.002-1.005-.01-.258.045-.512.162-.762.05-.116-.049-.229-.1-.356-.103-.39-.022-.884.182-1.103-.147-.242-.454-.293-.104-.532.048-.235-.015-.067-.35.014-.46.249-.57%201.846.517%201.183-.432-2.29-2.01-.777-2.686-1.646-2.69-.17-.089-.103-.405-.366-.173-.335.35-.46-.098-.46-.4-.04-.175-.177-.3-.125-.479.022-.39-.496.085-.38.41.057.616-.132%201.225-.102%201.833.24%201.276.41%202.897%201.864%203.276.177.076.463.432.253.565-.093-.01-.16-.11-.243-.153-.116-.078-.257.009-.378.018-.034.008-.088.007-.1.046l-.003.002z%22%3E%3C/path%3E%3C/svg%3E"}};
/* 品牌识别：只认「模型名里能确定的厂牌」，认出来就用专属图标，
   认不出来的统一落到 Azure（数据中心里那朵云，语义最接近「某台机器上的模型」）。 */
const MODEL_BRAND_RULES = [
  [/grok|xai|\bgrok-/, 'xAI Grok'],
  [/agnes|agnesai/, 'Agnes'],
  [/claude|anthropic/, 'Anthropic'],
  [/gemini|gemma/, 'Google Gemini'],
  [/learnlm|imagen|veo|palm/, 'Google'],
  [/deepseek/, 'DeepSeek'],
  [/chatglm|zhipu|\bglm/, 'Zhipu'],
  [/qwen|qwq|qvq|wan[-_ ]?\d|通义|千问/, 'Qwen'],
  [/kimi|moonshot/, 'Kimi'],
  [/minimax|abab/, 'MiniMax'],
  [/doubao|豆包/, 'Doubao'],
  [/volcengine|volcano/, 'Volcano Engine'],
  [/mimo|小米/, 'Xiaomi MiMo'],
  [/hunyuan|混元/, 'Hunyuan'],
  [/spark|astron/, 'Spark'],
  [/iflytek|讯飞/, 'iFlytek'],
  [/ernie|wenxin|文心/, 'Wenxin'],
  [/step[-_ ]?\d|stepfun|阶跃/, 'StepFun'],
  [/internlm|书生/, 'InternLM'],
  [/baichuan|百川/, 'Baichuan'],
  [/sensechat|sensenova|商汤/, 'SenseNova'],
  [/^yi([-_ ]|$)|零一/, 'Yi'],
  [/mistral|mixtral|codestral|magistral|devstral/, 'Mistral'],
  [/llama/, 'Meta'],
  [/command[-_ ]?r|cohere/, 'Cohere'],
  [/nemotron|nvidia/, 'Nvidia'],
  [/sonar|perplexity/, 'Perplexity'],
  [/groq/, 'Groq'],
  [/openrouter/, 'OpenRouter'],
  [/siliconflow|siliconcloud|硅基流动/, 'SiliconFlow'],
  [/modelscope|魔搭/, 'ModelScope'],
  [/opencode/, 'OpenCode'],
  [/gitee/, 'Gitee AI'],
  [/ollama/, 'Ollama'],
  [/copilot/, 'Copilot'],
  [/lm[-_ ]?studio/, 'LM Studio'],
  [/huggingface|\bhf[-_.]/, 'HuggingFace'],
  [/vertex/, 'Vertex AI'],
  [/bedrock/, 'Bedrock'],
  [/reka/, 'Reka'],
  [/jamba|ai21/, 'AI21'],
  [/upstage|solar[-_ ]?pro/, 'Upstage'],
  [/liquid/, 'Liquid'],
  [/rwkv/, 'RWKV'],
  [/sakana/, 'Sakana'],
  [/^ling([-_ ]|$)|蚂蚁百灵/, 'Ling'],
  [/longcat|龙猫/, 'LongCat'],
  [/^tii|falcon/, 'TII'],
  [/together/, 'Together'],
  [/fireworks/, 'Fireworks'],
  [/cerebras/, 'Cerebras'],
  [/novita/, 'Novita'],
  [/hyperbolic/, 'Hyperbolic'],
  [/vllm/, 'vLLM'],
  [/azure/, 'Azure'],
  [/^(openai|codex|o[134](?:[-_.]|$))/, 'OpenAI'],
  [/^(gpt|chatgpt)(?:[-_.].*)?$/, 'OpenAI'],
  [/dall-e|whisper|text-embedding/, 'OpenAI'],
  [/^tts(?:[-_.]|$)/, 'OpenAI'],
];
function modelBrand(name) {
  const raw = String(name || '').toLowerCase().trim();
  if (!raw || /^(自动|auto|default|默认|无)$/.test(raw)) return null;
  const n = raw.split('/').pop().trim();
  if (!n) return 'Azure';
  return MODEL_BRAND_RULES.find(([pattern]) => pattern.test(n))?.[1] || 'Azure';
}
/* 图标取当前配色那一版：图标已把 currentColor 烤成墨色，深色下不会糊成一团。 */
function modelIcon(brand) {
  if (!brand) return null;
  const entry = MODEL_ICONS[brand] || MODEL_ICONS.Azure;
  if (!entry) return null;
  if (typeof entry === 'string') return entry;
  return currentMode() === 'dark' ? (entry.dark || entry.light) : (entry.light || entry.dark);
}
/* Theme-owned floating controls: proxy native actions, never reparent React nodes. */
function syncFloatingControls() {
  const input = document.querySelector('[class*="module__chatInput__"]');
  let dock = document.getElementById('simple-chat-dock');
  if (!document.getElementById(STYLE_ID) || !input) { dock?.remove(); return; }
  if (!dock) {
    dock = document.createElement('div'); dock.id = 'simple-chat-dock';
    dock.innerHTML = '<div class="simple-stats"><button type="button" class="simple-stats-trigger" aria-label="会话用量统计"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true"><path d="M5 20V10m7 10V4m7 16v-7"/></svg></button><div class="simple-stats-detail" role="tooltip"></div></div><div class="simple-current-model" role="status" aria-live="polite"><img alt="" aria-hidden="true"><span class="simple-model-name"></span></div>';
    document.body.appendChild(dock);
    dock.querySelector('.simple-stats-trigger').addEventListener('click', (event) => {
      event.stopPropagation();
      setStatsOpen(!dock.classList.contains('simple-stats-open'));
    });
  }
  const usage=document.querySelector('[class*="module__runUsageBar__"]');
  const detail=dock.querySelector('.simple-stats-detail'); const text=usage?.textContent.trim() || '当前会话暂无用量统计';
  if(detail.textContent!==text)detail.textContent=text;
  const chip=document.querySelector('[class*="module__contextChipModel__"]');
  // 只读状态展示：切换入口仍是宿主原生 + 菜单，这里不复制按钮语义。
  const name=chip?.querySelector('[class*="module__contextChipLabel__"]')?.textContent.trim() || '自动选择';
  // 窄屏只显示模型名末段，全名仍挂在 title / aria-label，不必靠截断猜测。
  const short=innerWidth<=430?name.split('/').pop().trim()||name:name;
  const label=dock.querySelector('.simple-model-name'); if(label.textContent!==short)label.textContent=short;
  const holder=dock.querySelector('.simple-current-model');
  if(holder.getAttribute('aria-label')!==name)holder.setAttribute('aria-label',name);
  if(holder.getAttribute('title')!==name)holder.setAttribute('title',name);
  const img=dock.querySelector('.simple-current-model img'); const src=modelIcon(modelBrand(name));
  if(src&&img.getAttribute('src')!==src)img.src=src;
  img.hidden=!src;
  const r=input.getBoundingClientRect();
  const content=input.querySelector('[class*="module__inputWrapper__"]')?.getBoundingClientRect() || r;
  // 贴着输入框的可见上沿放（8px），不再按 chatInput 的 padding 盒算，
  // 否则中间会多出一段 16px 的空档。
  const left=Math.max(12,content.left),bottom=Math.max(12,innerHeight-content.top+8),maxWidth=Math.max(100,content.width);
  const style=`left:${left}px;bottom:${bottom}px;max-width:${maxWidth}px`;
  if(dock.getAttribute('style')!==style)dock.setAttribute('style',style);
}

/* 首帧时懒加载的对话路由可能还没渲染出输入框。DOM 变更观察器只在确实有
   变更时才会兜底，所以这里自己重试几帧，让浮动条不依赖无关的页面动作。 */
function settleFloatingControls(tries=30){
  if(disposed||tries<=0||document.getElementById('simple-chat-dock')||!document.getElementById(STYLE_ID))return;
  scheduleFrame(()=>{if(disposed)return;syncFloatingControls();if(!document.getElementById('simple-chat-dock'))settleFloatingControls(tries-1);});
}

/* 用量浮层：点击开关、点面板内部不关、点别处 / Esc 关闭。
   以前 hover 展开和点击开关抢同一份可见状态，鼠标一移开面板就没了，
   点第二下也关不干净。 */
function setStatsOpen(open) {
  const dock = document.getElementById('simple-chat-dock');
  if (!dock) return;
  dock.classList.toggle('simple-stats-open', !!open);
  dock.querySelector('.simple-stats-trigger')?.setAttribute('aria-expanded', String(!!open));
}
if (!window.__simpleStatsOutsideBound) {
  window.__simpleStatsOutsideBound = true;
  listen(document, 'pointerdown', (event) => {
    const dock = document.getElementById('simple-chat-dock');
    if (!dock || !dock.classList.contains('simple-stats-open')) return;
    if (dock.contains(event.target)) return;
    setStatsOpen(false);
  }, true);
  listen(document, 'keydown', (event) => {
    if (event.key !== 'Escape') return;
    const dock = document.getElementById('simple-chat-dock');
    if (!dock || !dock.classList.contains('simple-stats-open')) return;
    setStatsOpen(false);
    dock.querySelector('.simple-stats-trigger')?.focus();
  });
}
if(window.__simpleDockResize)window.removeEventListener('resize',window.__simpleDockResize);
window.__simpleDockResize=syncFloatingControls;listen(window, 'resize',syncFloatingControls);
listen(window, 'scroll',syncFloatingControls,{passive:true});

function refreshModelIcons() {
  if (!document.getElementById(STYLE_ID)) return;
  const entries = [
    ...[...document.querySelectorAll('[class*="module__contextChipModel__"]')].map(e => [e, e.querySelector('[class*="module__contextChipLabel__"]'), e.querySelector('[class*="module__contextChipIcon__"]')]),
    ...[...document.querySelectorAll('[class*="module__modelMenuSelect__"]')].map(e => [e, e.querySelector('[class*="module__modelMenuLabel__"]'), e.querySelector('[class*="module__modelMenuIcon__"]')]),
  ];
  for (const [row, label, icon] of entries) {
    if (!label || !icon) continue;
    const brand = modelBrand(label.textContent);
    const src = modelIcon(brand);
    if (src) {
      if (!icon.dataset.simpleOriginal) icon.dataset.simpleOriginal = icon.getAttribute('src') || '';
      if (icon.tagName === 'IMG') {
        if (icon.getAttribute('src') !== src) icon.setAttribute('src', src);
      } else {
        // Leave React-managed children untouched; an overlay avoids reconciliation errors.
        if (icon.style.backgroundImage !== 'url("' + src + '")') icon.style.backgroundImage = 'url("' + src + '")';
      }
      if (icon.dataset.simpleModelBrand !== brand) icon.dataset.simpleModelBrand = brand;
    } else if (icon.dataset.simpleModelBrand) {
      if (icon.tagName === 'IMG') icon.setAttribute('src', icon.dataset.simpleOriginal);
      else icon.style.removeProperty('background-image');
      delete icon.dataset.simpleModelBrand;
    }
    if (row.matches('[class*="module__contextChipModel__"]')) {
      const close = row.querySelector('button[class*="module__contextChipRemove__"]');
      const text = '移除模型 ' + label.textContent.trim();
      if (close && close.getAttribute('aria-label') !== text) { close.setAttribute('aria-label', text); close.title = text; }
    }
  }
}
/* 元素是否被某个 overflow hidden 的祖先整块裁掉（侧栏收起成图标轨时就是这种情况） */
function simpleClippedOut(el) {
  const a = el.getBoundingClientRect();
  if (a.width < 8 || a.height < 8) return true;
  for (let p = el.parentElement; p && p !== document.body; p = p.parentElement) {
    const cs = getComputedStyle(p);
    if (cs.overflowX === 'hidden' || cs.overflowX === 'clip' || cs.overflow === 'hidden' || cs.overflow === 'clip') {
      const b = p.getBoundingClientRect();
      if (b.width < 8 || a.right <= b.left + 2 || a.left >= b.right - 2) return true;
    }
  }
  return false;
}
/* 专家有会话在跑时，把进行中的圈圈提到专家名右侧，
   这样多专家并行时不必逐条扫会话列表就知道谁还没结束。

   v3.9.13：圈圈原来只认"这一行里有没有 sessionRowWorkingSpinner"，
   可侧栏一次只展开当前专家的会话——切到别的专家，那个还在跑的专家行里
   没有会话行，圈圈就跟着没了，等于看不出谁还在工作。现在改成两条腿：
   1. 行内真有进行中的会话（本专家）→ 立刻亮；
   2. 每条专家行按 agent_id 轮询 /api/agents/{id}/history-migration/status 的
      agent_busy，切走以后也能继续反映那个专家是否还在跑。
   id 优先从头像地址（/agents/<id>/avatar）里取，取不到用专家名对
   /api/agents 的结果匹配。 */
const agentBusyState = new Map();
let agentIdByName = null;
let agentIdByNameAt = 0;
let agentBusyPolledAt = 0;

function agentRowAgentId(row) {
  const img = row.querySelector('img[src*="/agents/"]');
  const hit = /\/agents\/([^/?#]+)\//.exec(img?.getAttribute('src') || '');
  if (hit) return hit[1];
  if (!agentIdByName) return null;
  const name = (row.querySelector('[class*="agentName"], [class*="minimalAgentName"]')?.textContent || '')
    .replace(/\s+/g, ' ').trim();
  return name ? agentIdByName.get(name) || null : null;
}

async function refreshAgentDirectory() {
  if (agentIdByName && Date.now() - agentIdByNameAt < 300000) return agentIdByName;
  try {
    const list = await host.request('/agents', { signal: lifecycle.signal });
    if (disposed) return agentIdByName;
    const map = new Map();
    for (const agent of list || []) {
      const name = String(agent?.name || '').replace(/\s+/g, ' ').trim();
      if (name && agent.agent_id) map.set(name, agent.agent_id);
    }
    agentIdByName = map;
    agentIdByNameAt = Date.now();
  } catch (err) {
    /* 拿不到就沿用上一次的表 */
  }
  return agentIdByName;
}

async function pollAgentBusy() {
  if (!document.getElementById(STYLE_ID) || document.hidden) return;
  await refreshAgentDirectory();
  const ids = new Set();
  for (const row of document.querySelectorAll('[class*="module__agentRow__"], [class*="module__agentCardActive"]')) {
    const id = agentRowAgentId(row);
    if (id) ids.add(id);
  }
  if (!ids.size) return;
  let changed = false;
  await Promise.all([...ids].map(async (id) => {
    try {
      // history-migration/status 里的 agent_busy 是服务端 active-invocation 计数：
      // 切到别的专家、甚至刷新页面它都不会清零（threads 里的 turn_active 会
      // 跟着浏览器连接断开而掉，正是"切走就不转了"的原因）。
      const body = await host.request(`/agents/${encodeURIComponent(id)}/history-migration/status`, { signal: lifecycle.signal });
      if (disposed) return;
      const busy = body?.agent_busy === true;
      if (agentBusyState.get(id) !== busy) {
        agentBusyState.set(id, busy);
        changed = true;
      }
    } catch (err) {
      /* 网络抖动：保留上一次状态，别把圈圈闪掉 */
    }
  }));
  if (changed) syncAgentBusy();
}

/* 轮询最密 8s，切专家、刚进页面时都会顺带触发一次 */
function maybePollAgentBusy() {
  const now = Date.now();
  if (now - agentBusyPolledAt < 8000) return;
  agentBusyPolledAt = now;
  pollAgentBusy();
}

function syncAgentBusy() {
  if (!document.getElementById(STYLE_ID)) return;
  let missingId = false;
  for (const row of document.querySelectorAll('[class*="module__agentRow__"], [class*="module__agentCardActive"]')) {
    const cluster = row.querySelector('[class*="module__agentNameCluster"]');
    if (!cluster) continue;
    // 侧栏收成 44px 图标轨时整行名字都被裁掉，圈圈会飘到行框外压住相邻图标。
    // 只在名字真的露得出来时才挂；收起后立刻摘掉。
    const room = cluster.getBoundingClientRect().width >= 32 && !simpleClippedOut(cluster);
    const id = agentRowAgentId(row);
    if (!id) missingId = true;
    const inRow = !!row.querySelector('[class*="sessionRowWorkingSpinner"]');
    const busy = room && (inRow || (id ? agentBusyState.get(id) === true : false));
    const dot = cluster.querySelector(':scope > .simple-agent-busy');
    if (busy && !dot) {
      const span = document.createElement('span');
      span.className = 'simple-agent-busy';
      span.setAttribute('aria-hidden', 'true');
      cluster.appendChild(span);
    } else if (!busy && dot) {
      dot.remove();
    }
  }
  if (missingId) maybePollAgentBusy();
}
/* ------------------------------------------------------------------
   消息操作行里的「收起这条回复 / 回到开头」。

   这两个按钮挂在消息操作行内、「从此处分叉」右边，和复制 / 朗读 / 重新生成
   同一套尺寸（24px，14px 图标），不额外占一行。收起时给这条回复挂
   .simple-turn-collapsed：过程摘要只留标题行、过程卡片收掉、正文夹到 300px
   并渐隐（夹的是正文本身，操作行留在外面，按钮始终点得到）。
   ------------------------------------------------------------------ */
const simple_TURN_CLASS = 'simple-turn-collapsed';
const simple_TURN_META_CLASS = 'simple-turn-has-meta';
const simple_BTN_COLLAPSE = 'simple-msg-collapse';
const simple_BTN_TOP = 'simple-msg-top';
const simple_COLLAPSE_MIN_ANSWER = 360;   // 正文高过这个才值得折叠
const simple_COLLAPSE_CLAMP = 300;        // 收起时正文夹到的高度（与 CSS 里一致）
const simple_TURN_TOKEN = /__assistantTurn__[A-Za-z0-9_-]+$/;
const simple_SVG = (body) => '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' + body + '</svg>';
const simple_ICON_COLLAPSE = simple_SVG('<path d="m7 20 5-5 5 5"/><path d="m7 4 5 5 5-5"/>');
const simple_ICON_EXPAND = simple_SVG('<path d="m7 15 5 5 5-5"/><path d="m7 9 5-5 5 5"/>');
const simple_ICON_TOP = simple_SVG('<path d="M5 3h14"/><path d="m18 13-6-6-6 6"/><path d="M12 7v14"/>');
const simple_COLLAPSE_ICON = '<svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M18 15l-6-6-6 6"/></svg>';

/* [class*="assistantTurn"] 会把 assistantTurnAnswer 也带上，按 class token 精确认 */
function simpleAssistantTurns() {
  const out = [];
  for (const el of document.querySelectorAll('[class*="module__assistantTurn"]')) {
    if ([...el.classList].some((c) => simple_TURN_TOKEN.test(c))) out.push(el);
  }
  return out;
}

/* 「从此处分叉」那个按钮：aria-label 是「从此处分叉」，未就绪时 title 会变成提示语 */
function simpleForkButton(turn) {
  for (const btn of turn.querySelectorAll('button')) {
    const label = (btn.getAttribute('aria-label') || '') + ' ' + (btn.title || '');
    if (label.includes('分叉')) return btn;
  }
  return null;
}

function paintTurnCollapse(turn) {
  const collapsed = turn.classList.contains(simple_TURN_CLASS);
  const btn = turn.querySelector('.' + simple_BTN_COLLAPSE);
  if (btn) {
    const mode = collapsed ? 'expand' : 'collapse';
    if (btn.dataset.simpleMode !== mode) {
      btn.innerHTML = collapsed ? simple_ICON_EXPAND : simple_ICON_COLLAPSE;
      btn.dataset.simpleMode = mode;
    }
    const label = collapsed ? '展开这条回复' : '收起这条回复';
    if (btn.title !== label) {
      btn.title = label;
      btn.setAttribute('aria-label', label);
    }
    btn.setAttribute('aria-expanded', collapsed ? 'false' : 'true');
  }
  const top = turn.querySelector('.' + simple_BTN_TOP);
  if (top && !top.title) {
    top.title = '回到这条回复的开头';
    top.setAttribute('aria-label', '回到这条回复的开头');
  }
}

function setTurnCollapsed(turn, collapsed) {
  const toggle = turn.querySelector('[class*="module__processSummaryToggle"]');
  const processOpen = !!turn.querySelector('[class*="module__processSummaryBody"]');
  turn.classList.toggle(simple_TURN_META_CLASS, !!turn.querySelector('[class*="module__msgMetaRow"]'));
  turn.classList.toggle(simple_TURN_CLASS, collapsed);
  turn.dataset.simpleTouched = '1';                              // 用户明确表态过，别再自动判态
  // React 的合成事件挂在外层，原生 click 冒泡上去就能触发它自己的开合逻辑
  if (toggle && processOpen === collapsed) toggle.click();
  paintTurnCollapse(turn);
  if (collapsed) {
    // 收起后整条只剩几百 px，把消息顶部带进视野，别让视口停在空白处
    scheduleFrame(() => { try { turn.scrollIntoView({ block: 'start' }); } catch (err) {} });
  }
}

function buildTurnAction(turn, className, icon, onClick) {
  const btn = document.createElement('button');
  btn.type = 'button';
  btn.className = 'simple-msg-btn ' + className;
  btn.innerHTML = icon;
  btn.addEventListener('click', (event) => {
    event.preventDefault();
    event.stopPropagation();
    onClick();
  });
  return btn;
}

function syncTurnCollapse() {
  if (!document.getElementById(STYLE_ID)) {
    document.querySelectorAll('.' + simple_BTN_COLLAPSE + ', .' + simple_BTN_TOP).forEach((node) => node.remove());
    document.querySelectorAll('.' + simple_TURN_CLASS).forEach((node) => node.classList.remove(simple_TURN_CLASS));
    return;
  }
  for (const turn of simpleAssistantTurns()) {
    const toggle = turn.querySelector('[class*="module__processSummaryToggle"]');
    const answer = turn.querySelector('[class*="module__assistantTurnAnswer"]');
    const fork = simpleForkButton(turn);
    let collapseBtn = turn.querySelector('.' + simple_BTN_COLLAPSE);
    let topBtn = turn.querySelector('.' + simple_BTN_TOP);
    if (!fork || !fork.parentElement) {
      collapseBtn?.remove();
      topBtn?.remove();
      continue;
    }
    const answerFull = answer ? answer.scrollHeight : 0;
    const processOpen = !!turn.querySelector('[class*="module__processSummaryBody"]');
    // 既没有过程摘要可开合、正文也不长 —— 操作行里不多摆两个图标
    if (!toggle && answerFull <= simple_COLLAPSE_MIN_ANSWER) {
      collapseBtn?.remove();
      topBtn?.remove();
      continue;
    }
    if (!collapseBtn) collapseBtn = buildTurnAction(turn, simple_BTN_COLLAPSE, simple_ICON_COLLAPSE, () => setTurnCollapsed(turn, !turn.classList.contains(simple_TURN_CLASS)));
    if (!topBtn) topBtn = buildTurnAction(turn, simple_BTN_TOP, simple_ICON_TOP, () => { try { turn.scrollIntoView({ block: 'start' }); } catch (err) {} });
    // 挨着「从此处分叉」放：… 复制 | 朗读 | 重新生成 | 分叉 | 收起 | ⇱
    if (fork.nextElementSibling !== collapseBtn) fork.insertAdjacentElement('afterend', collapseBtn);
    if (collapseBtn.nextElementSibling !== topBtn) collapseBtn.insertAdjacentElement('afterend', topBtn);
    // 收起态生效时夹的是正文本身，操作行得留在裁切范围外
    turn.classList.toggle(simple_TURN_META_CLASS, !!turn.querySelector('[class*="module__msgMetaRow"]'));
    // 没被用户手动表过态的，按原生状态给个初始判断：过程收着、正文也没过夹取高度
    // （夹取高度以下夹了也白夹，不会裁掉任何内容）= 这条本来就是收起的样子。
    // 正在生成时正文会长过这个高度，这里会自动解除，不会把流式内容夹住。
    if (turn.dataset.simpleTouched !== '1') {
      turn.classList.toggle(simple_TURN_CLASS, !processOpen && answerFull <= simple_COLLAPSE_CLAMP);
    }
    paintTurnCollapse(turn);
  }
}

/* ------------------------------------------------------------------
   思维链（思考 + 工具调用）正文下面的「收起思考与工具」。

   生成过程中这段默认展开，几千 px 高，原生开关却在它的最上面。这里在过程
   正文的末尾补一个开关：点它就点一下原生 toggle，并先给这一行套上
   .simple-process-hiding 立刻夹到 32px（不等 React 那一帧）；重新展开后会自己
   再长出来。只在这一段超过 180px 时才出现，短过程不占地方。
   ------------------------------------------------------------------ */
const simple_PROCESS_WRAP = 'simple-process-collapse';
const simple_PROCESS_MIN_HEIGHT = 180;

function findProcessCollapse(turn) {
  const box = turn.querySelector('[class*="module__processSummary__"]');
  if (!box) return null;
  for (const child of box.children) {
    if (child.classList && child.classList.contains(simple_PROCESS_WRAP)) return child;
  }
  return null;
}

function buildProcessCollapse(turn) {
  const wrap = document.createElement('div');
  wrap.className = simple_PROCESS_WRAP;
  const btn = document.createElement('button');
  btn.type = 'button';
  btn.className = 'simple-collapse-btn';
  btn.innerHTML = simple_COLLAPSE_ICON + '<span>收起思考与工具</span>';
  btn.setAttribute('aria-label', '收起思考与工具调用');
  btn.title = '收起思考与工具调用（正文里原生的开关也能展开）';
  btn.addEventListener('click', (event) => {
    event.preventDefault();
    event.stopPropagation();
    const row = turn.querySelector('[class*="module__processSummaryRow"]');
    row?.classList.add('simple-process-hiding');
    turn.querySelector('[class*="module__processSummaryToggle"]')?.click();
    wrap.remove();
  });
  wrap.appendChild(btn);
  return wrap;
}

function syncProcessCollapse() {
  if (!document.getElementById(STYLE_ID)) {
    document.querySelectorAll('.' + simple_PROCESS_WRAP).forEach((node) => node.remove());
    document.querySelectorAll('.simple-process-hiding').forEach((node) => node.classList.remove('simple-process-hiding'));
    return;
  }
  for (const turn of simpleAssistantTurns()) {
    const box = turn.querySelector('[class*="module__processSummary__"]');
    const body = turn.querySelector('[class*="module__processSummaryBody"]');
    const row = turn.querySelector('[class*="module__processSummaryRow"]');
    const existing = findProcessCollapse(turn);
    // 过程收起来了（React 已经不再渲染正文）：按钮和临时夹取都撤掉
    if (!body) {
      existing?.remove();
      row?.classList.remove('simple-process-hiding');
      continue;
    }
    const tall = (row?.getBoundingClientRect().height || 0) > simple_PROCESS_MIN_HEIGHT;
    if (!tall) { existing?.remove(); continue; }
    const wrap = existing || buildProcessCollapse(turn);
    if (!wrap) continue;
    if (wrap.parentElement !== box) box.appendChild(wrap);
    else if (box.lastElementChild !== wrap) box.appendChild(wrap);
  }
}


/* 侧栏收起/展开只改 class，不会触发 body 上的结构变更，靠定时器兜一次。 */
if (window.__simpleAgentBusyTimer) clearInterval(window.__simpleAgentBusyTimer);
window.__simpleAgentBusyTimer = setInterval(syncAgentBusy, 900);
/* 服务端状态另开一条慢速轮询：切专家后仍然能知道对方还在跑 */
if (window.__simpleAgentBusyPoll) clearInterval(window.__simpleAgentBusyPoll);
window.__simpleAgentBusyPoll = setInterval(maybePollAgentBusy, 8000);
listen(document, 'visibilitychange', () => {
  if (!document.hidden) {
    agentBusyPolledAt = 0;
    maybePollAgentBusy();
  }
});
if (window.__simpleThemeModelIconObserver) window.__simpleThemeModelIconObserver.disconnect();
let modelIconsQueued = false;
const modelIconObserver = new MutationObserver(() => {
  if (modelIconsQueued) return;
  modelIconsQueued = true;
  scheduleFrame(() => { if (disposed) return; modelIconsQueued = false; refreshModelIcons(); syncAgentBusy(); syncFloatingControls(); syncTurnCollapse(); syncProcessCollapse(); window.__simpleColumnResize?.sync(); });
});
modelIconObserver.observe(document.body, {subtree:true, childList:true, characterData:true, attributes:true, attributeFilter:['src']});
window.__simpleThemeModelIconObserver = modelIconObserver;
window.__simpleThemeModelBrand = modelBrand;
refreshModelIcons();
syncAgentBusy();
syncFloatingControls();
settleFloatingControls();
syncTurnCollapse();
syncProcessCollapse();

/* Resizable conversation column: theme-owned handles, no React node mutation. */
function initColumnResize() {
  if (window.__simpleColumnResize) return;
  const key='octop.simple-theme.column-width';
  const state={width:768,drag:null,observer:null,observed:null};
  try { const n=Number(localStorage.getItem(key)); if(n>=480&&n<=4000)state.width=n; } catch(e) {}
  const root=document.documentElement;
  const apply=()=>{root.style.setProperty('--simple-user-column',state.width+'px');syncFloatingControls();};
  const finish=()=>{if(!state.drag)return;state.drag=null;root.classList.remove('simple-column-dragging');try{localStorage.setItem(key,String(state.width));}catch(e){};};
  const sync=()=>{
    const input=document.querySelector('[class*="module__inputWrapper__"]');
    const area=document.querySelector('[class*="module__chatInput__"]');
    const enabled=document.getElementById(STYLE_ID)&&input&&area&&innerWidth>=768;
    if(!enabled){document.querySelectorAll('.simple-column-handle').forEach(e=>e.remove());finish();return;}
    const effective=Math.min(state.width,maxWidth())+'px';
    if(root.style.getPropertyValue('--simple-user-column')!==effective)root.style.setProperty('--simple-user-column',effective);
    if(state.observed!==area){state.observer?.disconnect();state.observer=new ResizeObserver(()=>{sync();syncFloatingControls();});state.observer.observe(area);state.observer.observe(input);state.observed=area;}
    const r=input.getBoundingClientRect();
    const messages=document.querySelector('[class*="module__messageListWrapper"]');
    const top=Math.max(12,messages?.getBoundingClientRect().top||12),bottom=Math.min(innerHeight-12,r.bottom);
    for(const side of ['left','right']){
      const id='simple-column-'+side;let h=document.getElementById(id);
      if(!h){
        h=document.createElement('div');h.id=id;h.className='simple-column-handle';h.tabIndex=0;h.setAttribute('role','separator');h.setAttribute('aria-orientation','vertical');h.setAttribute('aria-label',(side==='left'?'左':'右')+'侧对话宽度，方向键调整，双击恢复默认');h.title='拖动调整对话宽度 · 双击恢复默认';document.body.appendChild(h);
        h.onpointerdown=e=>{if(e.button!==0)return;e.preventDefault();state.drag={side,x:e.clientX,width:rereadWidth()};h.setPointerCapture(e.pointerId);root.classList.add('simple-column-dragging');};
        h.onpointermove=e=>{if(!state.drag||state.drag.side!==side)return;setWidth(state.drag.width+(e.clientX-state.drag.x)*(side==='right'?2:-2));};
        h.onpointerup=finish;h.onpointercancel=finish;h.onlostpointercapture=finish;
        h.ondblclick=()=>{state.width=768;apply();sync();try{localStorage.removeItem(key);}catch(e){}};
        h.onkeydown=e=>{if(!['ArrowLeft','ArrowRight','Home'].includes(e.key))return;e.preventDefault();setWidth(e.key==='Home'?768:rereadWidth()+(e.key==='ArrowRight'?1:-1)*(side==='right'?1:-1)*(e.shiftKey?64:16));try{localStorage.setItem(key,String(state.width));}catch(e){}};
      }
      const style=`left:${(side==='left'?r.left-8:r.right+2)}px;top:${top}px;height:${Math.max(0,bottom-top)}px`;
      if(h.getAttribute('style')!==style)h.setAttribute('style',style);
      h.setAttribute('aria-valuemin','480');h.setAttribute('aria-valuemax',String(maxWidth()));h.setAttribute('aria-valuenow',String(Math.round(r.width)));
    }
  };
  const rereadWidth=()=>document.querySelector('[class*="module__inputWrapper__"]')?.getBoundingClientRect().width||state.width;
  const maxWidth=()=>Math.max(480,Math.floor((document.querySelector('[class*="module__chatInput__"]')?.getBoundingClientRect().width||innerWidth)-56));
  const setWidth=n=>{state.width=Math.max(480,Math.min(maxWidth(),n));apply();sync();};
  const destroy=()=>{finish();state.observer?.disconnect();window.removeEventListener('resize',sync);window.removeEventListener('blur',finish);document.querySelectorAll('.simple-column-handle').forEach(e=>e.remove());root.style.removeProperty('--simple-user-column');delete window.__simpleColumnResize;};
  window.__simpleColumnResize={sync,destroy};listen(window, 'resize',sync);listen(window, 'blur',finish);apply();sync();
}

initColumnResize();

/* 1.0.1 — presentation-only deletion markers. No reparenting, handlers or text edits.
   danger alone is NOT deletion: disable/revoke/error actions must stay untouched. */
function initDeletePresentation() {
  window.__simpleDeleteObserver?.disconnect();
  const compact = value => String(value || '').replace(/\s+/g, '').toLowerCase();
  const destructive = value => /删除|卸载|^(?:delete|uninstall|remove)(?:\b|[A-Z])/i.test(String(value || ''));
  const cancel = value => /取消|cancel|关闭|close|禁用|disable/.test(compact(value));
  const exactAction = button => {
    const label = button.getAttribute('aria-label') || button.getAttribute('title') || button.textContent;
    return !cancel(label) && (/^(?:删除|确认删除|只删除|删除并整理|卸载)(?:.*)?$/.test(compact(label)) || /^(?:delete|uninstall|remove)(?:\b|$)/i.test(String(label || '').trim()));
  };
  const mark = (node, attr, yes) => {
    if (yes && !node.hasAttribute(attr)) node.setAttribute(attr, '');
    else if (!yes && node.hasAttribute(attr)) node.removeAttribute(attr);
  };
  const refresh = () => {
    if (!document.getElementById(STYLE_ID)) return;
    const layers = [...document.querySelectorAll('.octop-modal,.octop-popconfirm,.octop-ant-modal,.octop-ant-popconfirm')];
    for (const layer of layers) {
      const heading = layer.querySelector('.octop-modal-confirm-title,.octop-modal-title,.octop-popconfirm-title,.octop-ant-modal-confirm-title,.octop-ant-modal-title,.octop-ant-popconfirm-title');
      // Only titles identify a delete layer; descriptions may mention unrelated deletion.
      const isDelete = !!heading && destructive(heading.textContent);
      mark(layer, 'data-simple-delete-dialog', isDelete);
      for (const button of layer.querySelectorAll('button')) {
        const label = button.getAttribute('aria-label') || button.textContent;
        const genericConfirm = /^(确定|确认|ok|confirm|yes)$/.test(compact(label)) && button.matches('.octop-btn-primary,.octop-ant-btn-primary');
        mark(button, 'data-simple-delete-action', exactAction(button) || (isDelete && genericConfirm && !cancel(label)));
      }
      const footer = layer.querySelector('.octop-modal-confirm-btns,.octop-modal-footer,.octop-popconfirm-buttons,.octop-ant-modal-confirm-btns,.octop-ant-modal-footer,.octop-ant-popconfirm-buttons') || (isDelete ? layer.querySelector('.octop-modal-confirm-body-wrapper')?.lastElementChild : null);
      if (footer) mark(footer, 'data-simple-delete-footer', isDelete && !!footer.querySelector('button'));
    }
    for (const button of document.querySelectorAll('button,[role="menuitem"]')) {
      if (button.closest('.octop-modal,.octop-popconfirm,.octop-ant-modal,.octop-ant-popconfirm')) continue;
      mark(button, 'data-simple-delete-action', exactAction(button));
    }
  };
  let scheduled = false;
  const observer = new MutationObserver(() => {
    if (scheduled) return;
    scheduled = true;
    scheduleFrame(() => { if (disposed) return; scheduled = false; refresh(); });
  });
  observer.observe(document.body, {childList:true,subtree:true,characterData:true,attributes:true,attributeFilter:['class','aria-label','title','disabled','aria-disabled','aria-busy']});
  window.__simpleDeleteObserver = observer;
  refresh();
}
initDeletePresentation();

/* ------------------------------- 字体 ------------------------------- */
// 插件静态资源走鉴权接口，CSS 里的 url() 带不上 Authorization 头，
// 因此 fetch 回来用 FontFace 注册。取不到就静默退回系统字体栈。
async function loadFont() {
  if (window.__octopSimpleThemeFont) return;
  try {
    const blob = await host.requestBlob(FONT_PATH, { signal: lifecycle.signal });
    const buf = await blob.arrayBuffer();
    if (disposed) return;
    const face = new FontFace(FONT_FAMILY, buf, { weight: "100 900", display: "swap" });
    await face.load();
    if (disposed) return;
    document.fonts.add(face);
    themeFont = face;
    window.__octopSimpleThemeFont = true;
  } catch (err) {
    if (!disposed) console.warn("[simple-theme] 字体加载失败，回退系统字体:", err);
  }
}

loadFont();

/* ----------------------------- 状态卡片 ----------------------------- */

function ThemeCard(props) {
  const React = window.__OCTOP_REACT__;
  const data = (props && props.data) || {};
  const [, force] = React.useState(0);
  const enabled = !!document.getElementById(STYLE_ID);
  const mode = currentMode();

  const dot = React.createElement("span", {
    style: {
      width: 7,
      height: 7,
      borderRadius: "50%",
      background: enabled ? "#1a7f4b" : "var(--fn-text-quaternary)",
      display: "inline-block",
      flex: "none",
    },
  });

  return React.createElement(
    "div",
    {
      style: {
        border: "1px solid var(--fn-border-primary)",
        borderRadius: 14,
        padding: "14px 16px",
        background: "var(--fn-bg-primary)",
        color: "var(--fn-text-primary)",
        maxWidth: 460,
        fontSize: 14,
        lineHeight: 1.6,
      },
    },
    React.createElement(
      "div",
      { style: { display: "flex", alignItems: "center", gap: 8, fontWeight: 600 } },
      dot,
      "简单主题",
      React.createElement(
        "span",
        { style: { marginLeft: "auto", fontSize: 12, color: "var(--fn-text-tertiary)" } },
        `v${data.version || VERSION}`,
      ),
    ),
    React.createElement(
      "div",
      { style: { marginTop: 8, color: "var(--fn-text-secondary)" } },
      enabled
        ? "已生效：对话、输入框、侧栏和设置页使用统一的简洁排版。"
        : "当前未生效（样式表被移除），点下面的按钮重新注入。",
    ),
    React.createElement(
      "div",
      { style: { marginTop: 4, fontSize: 12, color: "var(--fn-text-tertiary)" } },
      `当前配色：${mode === "dark" ? "深色" : "浅色"}（跟随控制台外观设置）`,
    ),
    React.createElement(
      "button",
      {
        type: "button",
        onClick: () => {
          applyTheme();
          force((n) => n + 1);
        },
        style: {
          marginTop: 12,
          padding: "6px 14px",
          borderRadius: 980,
          border: "1px solid var(--fn-border-primary)",
          background: "var(--fn-text-primary)",
          color: "var(--fn-bg-primary)",
          cursor: "pointer",
          fontSize: 13,
          fontWeight: 500,
        },
      },
      "重新应用主题",
    ),
  );
}

// —— 诊断面板（3.9.19）：Ctrl/⌘+Alt+D 打开，列出当前视口内所有带描边/阴影的元素，
// 并标出「内层卡片距外层描边 <24px」的组合 —— 就是用户说的「两层描边」。
function collectDiagReport() {
  const lines = [];
  const vw = window.innerWidth, vh = window.innerHeight;
  lines.push("简单主题 v" + VERSION + " | " + location.pathname + " | " + vw + "x" + vh + " dpr=" + (window.devicePixelRatio || 1) + " | theme=" + (document.documentElement.dataset.theme || "-"));
  const items = [];
  for (const el of document.querySelectorAll("body *")) {
    const cs = getComputedStyle(el);
    const r = el.getBoundingClientRect();
    if (r.width < 40 || r.height < 14) continue;
    if (r.bottom < 0 || r.top > vh) continue;
    const bt = parseFloat(cs.borderTopWidth) || 0;
    const bl = parseFloat(cs.borderLeftWidth) || 0;
    const bc = cs.borderTopColor;
    const transparent = /,\s*0\)$/.test(bc);
    const hasBorder = (bt > 0 || bl > 0) && !transparent;
    const sh = cs.boxShadow && cs.boxShadow !== "none" ? cs.boxShadow : "";
    if (!hasBorder && !sh) continue;
    const cls = (typeof el.className === "string" ? el.className : "").trim() || el.tagName.toLowerCase();
    items.push({ el, cls, r, bt, bl, bc, sh, hasBorder, bg: cs.backgroundColor });
  }
  items.sort((a, b) => (a.r.top - b.r.top) || (a.r.left - b.r.left));
  for (const it of items.slice(0, 120)) {
    let nest = "";
    let p = it.el.parentElement;
    while (p && p !== document.body) {
      const pcs = getComputedStyle(p);
      const pw = parseFloat(pcs.borderTopWidth) || 0;
      if (pw > 0 && !/,\s*0\)$/.test(pcs.borderTopColor)) {
        const pr = p.getBoundingClientRect();
        const gapT = Math.round(it.r.top - pr.top), gapL = Math.round(it.r.left - pr.left);
        if (gapT >= 0 && gapT < 24 && gapL >= 0 && gapL < 24) {
          const pcls = (typeof p.className === "string" ? p.className : "").trim() || p.tagName.toLowerCase();
          nest = "  <<双层 parent=" + pcls.slice(0, 44) + " gap=" + gapT + "/" + gapL;
        }
        break;
      }
      p = p.parentElement;
    }
    lines.push(
      it.cls.slice(0, 74) +
        " | " + Math.round(it.r.x) + "," + Math.round(it.r.y) + " " + Math.round(it.r.width) + "x" + Math.round(it.r.height) +
        " | 边 " + it.bt + "/" + it.bl + " " + it.bc +
        " | 影 " + (it.sh ? it.sh.slice(0, 76) : "无") +
        " | 底 " + it.bg +
        (it.hasBorder && it.sh ? " | !!边+影" : "") + nest
    );
  }
  lines.push("共 " + items.length + " 个带描边/阴影元素（已列前 120）");
  return lines.join("\n");
}

function openDiag() {
  const old = document.getElementById("simple-diag");
  if (old) old.remove();
  const box = document.createElement("div");
  box.id = "simple-diag";
  box.setAttribute("style", "position:fixed;left:8%;right:8%;top:6%;z-index:2147483000;background:var(--fn-bg-primary,#fff);color:var(--fn-text-primary,#111);border-radius:14px;box-shadow:0 24px 60px rgba(0,0,0,.28),inset 0 0 0 1px rgba(0,0,0,.08);padding:14px;display:flex;flex-direction:column;gap:10px;max-height:80vh;");
  const ta = document.createElement("textarea");
  ta.value = collectDiagReport();
  ta.setAttribute("style", "flex:1;min-height:340px;width:100%;resize:vertical;border-radius:10px;border:1px solid rgba(0,0,0,.12);padding:10px;font:12px/1.5 ui-monospace,Menlo,Consolas,monospace;background:var(--fn-bg-secondary,#f4f4f4);color:inherit;outline:none;");
  const row = document.createElement("div");
  row.setAttribute("style", "display:flex;gap:8px;justify-content:flex-end;align-items:center;");
  const mk = (label, fn) => {
    const b = document.createElement("button");
    b.textContent = label;
    b.setAttribute("style", "padding:7px 14px;border-radius:980px;border:1px solid rgba(0,0,0,.12);background:transparent;color:inherit;cursor:pointer;font-size:12px;font-weight:500;");
    b.onclick = fn;
    return b;
  };
  const tip = document.createElement("span");
  tip.textContent = "把这个面板打开后按 Ctrl/⌘+Alt+D，复制内容发给开发者";
  tip.setAttribute("style", "margin-right:auto;font-size:12px;opacity:.55;");
  row.append(
    tip,
    mk("复制全部", () => {
      ta.focus();
      ta.select();
      try { document.execCommand("copy"); } catch (err) { /* 忽略 */ }
      try { navigator.clipboard && navigator.clipboard.writeText(ta.value); } catch (err) { /* 忽略 */ }
      tip.textContent = "已复制，贴给开发者即可";
    }),
    mk("关闭", () => box.remove())
  );
  box.append(ta, row);
  document.body.append(box);
  ta.focus();
  ta.select();
}

if (!window.__simpleDiagBound) {
  window.__simpleDiagBound = true;
  listen(document,
    "keydown",
    (event) => {
      if ((event.ctrlKey || event.metaKey) && event.altKey && (event.key === "d" || event.key === "D")) {
        event.preventDefault();
        openDiag();
      }
    },
    true
  );
}
window.simpleThemeDiag = openDiag;

function registerTheme() {
  applyTheme();
  // SPA 路由切换后 <html> 上的 id 不受影响，但 meta 主题色可能被 App 重写，
  // 用 MutationObserver 盯住 data-theme，切浅/深色时同步一次。
  try {
    if (window.__octopSimpleThemeObserver) window.__octopSimpleThemeObserver.disconnect();
    const observer = new MutationObserver(() => {
      // 宿主先更新模式和地址栏颜色；卸载时应还原当前模式的颜色。
      for (const color of themeColors) color.content = color.meta.getAttribute('content');
      applyTheme();
      // 图标是按配色烤好两版再挑的，深浅切换后要换一份（浮动条上的那份也要换）。
      try { refreshModelIcons(); syncFloatingControls(); } catch (err) { /* 忽略 */ }
    });
    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["data-theme"],
    });
    window.__octopSimpleThemeObserver = observer;
  } catch (err) {
    /* 忽略 */
  }
  try {
    window.localStorage.setItem(STORAGE_KEY, VERSION);
  } catch (err) {
    /* 忽略 */
  }
  if (host && typeof host.registerRenderer === "function") {
    host.registerRenderer({
      id: "theme_card",
      tools: ["simple_theme_info"],
      component: ThemeCard,
    });
  }
}

registerTheme();
return () => {
  if (disposed) return;
  disposed = true;
  lifecycle.abort();
  for (const id of frames) cancelAnimationFrame(id);
  frames.clear();
  window.__octopSimpleThemeObserver?.disconnect();
  window.__simpleThemeModelIconObserver?.disconnect();
  removeTheme();
  document.documentElement.id = previousRootId;
  for (const { meta, content, media } of themeColors) {
    if (content === null) meta.removeAttribute('content'); else meta.setAttribute('content', content);
    if (media === null) meta.removeAttribute('media'); else meta.setAttribute('media', media);
  }
  if (themeFont) document.fonts.delete(themeFont);
  document.getElementById('simple-diag')?.remove();
  for (const key of [
    '__octopSimpleTheme', '__octopSimpleThemeObserver', '__octopSimpleThemeFont',
    '__simpleThemeModelIconObserver', '__simpleThemeModelBrand', '__simpleDeleteObserver',
    '__simpleStatsOutsideBound', '__simpleDiagBound', '__simpleDockResize', 'simpleThemeDiag',
  ]) delete window[key];
};
}
