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
const VERSION = "1.0.2";
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

const CSS = `__THEME_CSS__`;

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
    queueMicrotask(() => { if (!disposed) initColumnResize(); });
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
/* __MODEL_ICONS__ 由 build.py 从 ui/model-icons.js 内联，勿手改 */
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
    dock.innerHTML = '<div class="simple-stats"><button type="button" class="simple-stats-trigger" aria-label="会话用量统计"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true"><path d="M5 20V10m7 10V4m7 16v-7"/></svg></button><div class="simple-stats-detail" role="tooltip"></div></div><div class="simple-current-model"><button type="button" class="simple-model-trigger" aria-label="切换模型"><img alt=""><span></span></button><button type="button" class="simple-model-remove" aria-label="移除选中模型">×</button></div>';
    document.body.appendChild(dock);
    dock.querySelector('.simple-stats-trigger').addEventListener('click', (event) => {
      event.stopPropagation();
      setStatsOpen(!dock.classList.contains('simple-stats-open'));
    });
    dock.querySelector('.simple-model-remove').onclick = () => document.querySelector('[class*="module__contextChipModel__"] button')?.click();
    dock.querySelector('.simple-model-trigger').onclick = () => {
      const plus=document.querySelector('[data-testid="composer-plus"]'); if(!plus)return; plus.click();
      scheduleFrame(() => {
        const label=dock.querySelector('.simple-model-trigger span').textContent;
        const candidate=[...document.querySelectorAll('button')].find(b=>!dock.contains(b)&&b.textContent.trim().endsWith(label)&&b.closest('[class*="Menu"],[class*="menu"],[class*="Popover"],[class*="popover"]'));
        if(candidate)candidate.click();
      });
    };
  }
  const usage=document.querySelector('[class*="module__runUsageBar__"]');
  const detail=dock.querySelector('.simple-stats-detail'); const text=usage?.textContent.trim() || '当前会话暂无用量统计';
  if(detail.textContent!==text)detail.textContent=text;
  const chip=document.querySelector('[class*="module__contextChipModel__"]');
  const name=chip?.querySelector('[class*="module__contextChipLabel__"]')?.textContent.trim() || '自动';
  const label=dock.querySelector('.simple-model-trigger span'); if(label.textContent!==name)label.textContent=name;
  const img=dock.querySelector('.simple-model-trigger img'); const src=modelIcon(modelBrand(name));
  if(src&&img.getAttribute('src')!==src)img.src=src;
  img.hidden=!src; dock.querySelector('.simple-model-remove').hidden=!chip;
  const r=input.getBoundingClientRect();
  const content=input.querySelector('[class*="module__inputWrapper__"]')?.getBoundingClientRect() || r;
  // 贴着输入框的可见上沿放（8px），不再按 chatInput 的 padding 盒算，
  // 否则中间会多出一段 16px 的空档。
  const left=Math.max(12,content.left),bottom=Math.max(12,innerHeight-content.top+8),maxWidth=Math.max(100,content.width);
  const style=`left:${left}px;bottom:${bottom}px;max-width:${maxWidth}px`;
  if(dock.getAttribute('style')!==style)dock.setAttribute('style',style);
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
