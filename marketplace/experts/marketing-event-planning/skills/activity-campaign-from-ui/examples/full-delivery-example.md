# Mode example — full

## User input
The user sends 3 campaign references and asks:

> 参考这 3 个活动页，先分析共性，再给我出一个新的 H5 活动方案，最后补一套更像可上线成品的 HTML + CSS + JS 页面。首屏要有美女人物主视觉，页面别做得太长，走 full mode。

## Expected response shape

### Mode
full

## 1. Reference analysis
### Observed
- all references are mobile-first campaign pages
- each page uses a strong hero section near the top
- a reward promise appears before the detailed rules
- task completion is tied to a visible reward action
- poster-like human visual focus is important to the first screen

### Inferred
- the campaign is designed for repeat daily participation
- the main business goal is likely short-term activation
- reward exposure is used as the primary motivation trigger
- a spokesperson-like female visual helps hold first-screen attention

### Assumed
- exact microcopy and reward probabilities are not fully readable
- hidden states such as “already claimed” or “chance exhausted” are likely present but not fully visible

## 2. Gameplay abstraction
Shared pattern:
1. attract attention with hero and date range
2. expose reward value early
3. drive task completion
4. convert task progress into chances, points, or unlock states
5. reveal result feedback through popups

## 3. New campaign proposal
### Name
Spring Route Challenge

### Goal
Increase repeat visits and task completion during a short seasonal campaign window.

### Main idea
Instead of repeating a direct lucky-draw page, this proposal changes:
- the reward design: from flat prize display to staged checkpoint rewards plus a final draw
- the task structure: from independent tasks to daily progress tasks
- the main interaction: users unlock reward checkpoints before reaching the final action area
- the page structure: from long vertical stacking to a tab-first H5 layout after the hero screen

### Participation path
Enter page → complete daily tasks → unlock route checkpoints → claim checkpoint rewards → use final draw chances

### Anti-copy note
This proposal changes at least 2 required dimensions:
- reward mechanism
- task structure
- core interaction path

## 4. Page architecture
### Modules
1. hero banner
2. hero summary strip
3. sticky tab bar
4. daily task tab
5. checkpoint reward tab
6. reward pool and rules tab
7. popup system

### Popups
- rule popup
- checkpoint unlocked popup
- reward result popup
- insufficient chance popup

### State flow
`init -> taskUpdated -> routeProgressed -> checkpointUnlocked -> chanceReady -> drawing -> resultShown`

### Tracking suggestions
- hero_cta_click
- task_action_click
- checkpoint_claim_click
- draw_start_click
- draw_result_view
- tab_switch_click

## 5. Delivery schema
The schema should cover both campaign config and delivery structure.

### Suggested schema sections
- `campaignMeta`
- `hero`
- `activityFactory`
- `activityConfig`
- `progressRoute`
- `tasks`
- `checkpointRewards`
- `lottery`
- `tabs`
- `popups`
- `animationSystem`
- `assetOutput`
- `stateMachine`
- `tracking`

## 6. Visual direction
- dominant palette: cherry red, amber gold, warm cream
- page mood: festive, busy, rewarding, glossy
- hero composition: a real top-of-page hero image at `./image/bg.png` with one new adult female glamour figure in red-dominant festive styling and photorealistic commercial-poster rendering
- first screen should feel poster-led, with the woman as the primary visual anchor
- secondary content should be compressed into sticky tabs instead of a long stacked page
- module treatment: decorated panels with stronger top headers and contrast separators
- CTA language: loud, central, badge-supported
- motion system: one signature interaction animation plus ambient sparkle drift, CTA pulse, and popup rise-in
- popup style: branded celebration layer instead of a neutral modal

## 7. H5/Web high-fidelity draft files
### File structure
- `project/<delivery-slug>/index.html`
- `project/<delivery-slug>/styles.css`
- `project/<delivery-slug>/main.js`
- `project/<delivery-slug>/mock-data.js`
- `project/<delivery-slug>/image/`
- `project/<delivery-slug>/image/bg.png` for the top hero visual

Execution note:
- generate the asset used for `./image/bg.png` in the current run before the front-end files when the brief is poster-led
- if the host exposes a concrete tool such as `image_generate`, call it directly
- default to `regenerate_each_run`; only reuse an existing image when the user explicitly asks to do so
- if required image generation is unavailable, stop and report the run as blocked instead of downgrading to placeholders
- keep the generated image focused on one new woman and atmosphere instead of copying page modules or the reference face
- when Python writes local files, create `project/`, `project/<delivery-slug>/`, and `project/<delivery-slug>/image/` first and save the hero asset to `project/<delivery-slug>/image/bg.png`
- when local output was requested, do not stop at a file structure summary; actually write the files and report the resulting paths

Asset handoff note:
`需要把生成好的图片，改名为bg，图片类型为 png，放到 project/<delivery-slug>/image 目录下`

If the user explicitly asks for local output and Python/local execution is available, these front-end files should be written inside `project/<delivery-slug>/` in addition to being presented in the response.

### index.html
```html
<div class="route-page">
  <div class="route-page-glow route-page-glow-top"></div>
  <main class="route-shell">
    <section id="hero" class="route-hero">
      <div class="route-hero-visual">
        <img src="./image/bg.png" alt="活动首屏主视觉" />
        <div class="route-hero-copy">
          <span class="hero-pill">春日限定玩法</span>
          <h1 class="route-title">春日闯关大道</h1>
          <p class="route-subtitle">完成每日任务点亮路标，开出阶段宝箱并冲刺终点大奖</p>
          <div class="route-meta">
            <span>活动时间 02.01 - 02.14</span>
            <span>累计完成越多，奖励越高</span>
          </div>
          <div class="route-hero-actions">
            <button class="hero-side-cta js-start-draw">冲刺终点</button>
            <button class="hero-ghost-cta js-switch-tab" data-tab="tasks">先做任务</button>
          </div>
        </div>
        <aside class="hero-side-card">
          <p>终点大奖</p>
          <strong>锦鲤礼包 x 1</strong>
          <span>再完成 1 个任务即可额外解锁 1 次抽奖</span>
        </aside>
      </div>
    </section>

    <section class="route-summary-panel">
      <div class="summary-pill"><span>今日进度</span><strong>2 / 4</strong></div>
      <div class="summary-pill"><span>抽奖机会</span><strong>1 次</strong></div>
      <div class="summary-pill summary-pill-hot"><span>下一档奖励</span><strong>冲刺加速卡</strong></div>
    </section>

    <nav class="route-tabs" aria-label="活动内容导航">
      <button class="route-tab is-active js-switch-tab" data-tab="tasks">任务</button>
      <button class="route-tab js-switch-tab" data-tab="checkpoints">阶段奖励</button>
      <button class="route-tab js-switch-tab" data-tab="benefits">奖池/规则</button>
    </nav>

    <section id="tab-tasks" class="route-panel is-active"></section>
    <section id="tab-checkpoints" class="route-panel"></section>
    <section id="tab-benefits" class="route-panel"></section>
  </main>
</div>

<div id="popup-root"></div>
```

### styles.css
```css
:root {
  --route-bg: #9f1420;
  --route-bg-deep: #5d0912;
  --route-panel: linear-gradient(180deg, #fff7e4 0%, #ffe4a8 100%);
  --route-stroke: rgba(255, 242, 196, 0.9);
  --route-title: #74130f;
  --route-copy: #984021;
}

body {
  margin: 0;
  font-family: "PingFang SC", "Microsoft YaHei", sans-serif;
  background:
    radial-gradient(circle at top, rgba(255, 218, 130, 0.28), transparent 26%),
    linear-gradient(180deg, var(--route-bg-deep) 0%, var(--route-bg) 42%, #db4b34 100%);
}

.route-shell {
  max-width: 750px;
  margin: 0 auto;
  padding: 18px 16px 34px;
}

.route-hero,
.route-summary-panel,
.route-panel {
  position: relative;
  overflow: hidden;
  border-radius: 28px;
  border: 1px solid var(--route-stroke);
  box-shadow: 0 18px 40px rgba(78, 10, 11, 0.22);
}

.route-hero {
  padding: 0;
  margin-bottom: 16px;
  color: #fff8eb;
  background:
    radial-gradient(circle at top right, rgba(255, 244, 199, 0.42), transparent 26%),
    linear-gradient(140deg, #8f0f17 0%, #d33730 52%, #ff8a47 100%);
}

.route-hero-visual {
  position: relative;
  min-height: 560px;
}

.route-hero-visual img {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: cover;
  object-position: top center;
}

.route-hero-copy {
  position: absolute;
  inset: auto 20px 20px 20px;
  z-index: 1;
}

.route-hero-visual::after {
  content: "";
  position: absolute;
  inset: 0;
  background: linear-gradient(180deg, rgba(30, 0, 0, 0.04), rgba(74, 8, 12, 0.12) 36%, rgba(56, 4, 7, 0.7) 100%);
  pointer-events: none;
}

.hero-side-cta {
  animation: routePulse 1.8s ease-in-out infinite;
}

.hero-side-card {
  animation: routeFloat 3s ease-in-out infinite;
}

@keyframes routePulse {
  0%, 100% { transform: scale(1); }
  50% { transform: scale(1.04); }
}

@keyframes routeFloat {
  0%, 100% { transform: translateY(0); }
  50% { transform: translateY(-6px); }
}

.route-summary-panel {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
  padding: 14px;
  margin-bottom: 14px;
  background: var(--route-panel);
}

.route-tabs {
  position: sticky;
  top: 0;
  z-index: 6;
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 10px;
  padding: 8px 0 14px;
  background: linear-gradient(180deg, rgba(93, 9, 18, 0.98), rgba(93, 9, 18, 0));
}

.route-tab {
  height: 44px;
  border: 0;
  border-radius: 999px;
  font-weight: 700;
  color: #ffe6ab;
  background: rgba(255, 246, 214, 0.14);
}

.route-tab.is-active {
  color: #7a180a;
  background: linear-gradient(180deg, #ffe082 0%, #ffb533 100%);
}

.route-panel {
  display: none;
  padding: 18px;
  margin-bottom: 14px;
  background: var(--route-panel);
  color: var(--route-title);
}

.route-panel.is-active {
  display: block;
}
```

### main.js
```javascript
document.addEventListener('DOMContentLoaded', function () {
  renderPage(window.campaignData);
  bindEvents();
  setActiveTab('tasks');
});

function renderPage(data) {
  document.getElementById('tab-tasks').innerHTML = renderTasksTab(data.progressRoute, data.tasks, data.lottery);
  document.getElementById('tab-checkpoints').innerHTML = renderCheckpoints(data.checkpointRewards);
  document.getElementById('tab-benefits').innerHTML = renderBenefitsTab(data.rewardPool, data.rules);
}

function renderTasksTab(route, tasks, lottery) {
  return '<div class="panel-title"><h2>闯关进度</h2><span>' + route.tip + '</span></div><div class="route-track">' +
    route.steps.map(function (item) {
      return '<div class="route-step' + (item.done ? ' is-done' : '') + '">' +
        '<b>' + item.label + '</b><span>' + item.note + '</span>' +
      '</div>';
    }).join('') +
  '</div><div class="task-stack">' + tasks.map(function (task) {
    return '<article class="task-item">' +
      '<div><p class="task-type">' + task.type + '</p><h3>' + task.title + '</h3><p>' + task.benefit + '</p></div>' +
      '<button class="js-task-action" data-id="' + task.id + '">' + task.ctaText + '</button>' +
    '</article>';
  }).join('') + '</div>' +
  '<div class="draw-stage"><strong>' + lottery.chanceText + '</strong><button class="draw-button js-start-draw">' + lottery.ctaText + '</button></div>';
}

function renderCheckpoints(checkpoints) {
  return checkpoints.map(function (item) {
    return '<article class="checkpoint-card">' +
      '<span class="checkpoint-index">' + item.index + '</span>' +
      '<strong>' + item.title + '</strong>' +
      '<p>' + item.desc + '</p>' +
      '<span class="checkpoint-status">' + item.statusText + '</span>' +
    '</article>';
  }).join('');
}

function renderBenefitsTab(rewardPool, rules) {
  return '<div class="panel-title"><h2>奖池展示</h2></div><div class="reward-pool-grid">' +
    rewardPool.map(function (item) {
      return '<div class="reward-pool-card"><span>' + item.tag + '</span><strong>' + item.name + '</strong></div>';
    }).join('') +
  '</div><div class="panel-title"><h2>活动规则</h2></div><ol class="rule-list">' +
    rules.map(function (rule) {
      return '<li>' + rule + '</li>';
    }).join('') +
  '</ol>';
}

function bindEvents() {
  document.querySelector('.route-shell').addEventListener('click', function (event) {
    var tabTrigger = event.target.closest('.js-switch-tab');
    if (tabTrigger) {
      setActiveTab(tabTrigger.getAttribute('data-tab'));
      return;
    }

    if (!event.target.closest('.js-start-draw')) {
      return;
    }

    openPopup('rewardResultPopup');
  });
}

function setActiveTab(tabKey) {
  document.querySelectorAll('.route-tab').forEach(function (tab) {
    tab.classList.toggle('is-active', tab.getAttribute('data-tab') === tabKey);
  });

  document.querySelectorAll('.route-panel').forEach(function (panel) {
    panel.classList.toggle('is-active', panel.id === 'tab-' + tabKey);
  });
}

function openPopup(id) {
  var popup = window.campaignData.popups.filter(function (item) {
    return item.id === id;
  })[0];

  document.getElementById('popup-root').innerHTML =
    '<div class="popup-mask is-open"><div class="route-popup"><p>' + popup.kicker + '</p><h3>' +
    popup.title + '</h3><span>' + popup.desc + '</span></div></div>';
}
```

### mock-data.js
```javascript
window.campaignData = {
  progressRoute: {
    tip: '再完成 1 个任务即可点亮下一路标',
    steps: [
      { id: 'step-1', label: '签到站', note: '已完成', done: true },
      { id: 'step-2', label: '助力站', note: '进行中', done: true },
      { id: 'step-3', label: '终点站', note: '待点亮', done: false }
    ]
  },
  tasks: [
    { id: 'daily-checkin', type: '每日任务', title: '每日签到', benefit: '完成后获得 10 点路程值', ctaText: '立即签到' },
    { id: 'share-campaign', type: '加速任务', title: '邀请好友助力', benefit: '完成后额外获得 20 点路程值', ctaText: '去邀请' }
  ],
  checkpointRewards: [
    { index: '01', title: '启程礼盒', desc: '解锁即得通用优惠券包', statusText: '已解锁' },
    { index: '02', title: '冲刺加速卡', desc: '终极抽奖次数 +1', statusText: '即将解锁' }
  ],
  lottery: {
    chanceText: '当前抽奖机会 1 次',
    ctaText: '立即抽奖'
  },
  rewardPool: [
    { tag: '终点大奖', name: '锦鲤礼包' },
    { tag: '惊喜奖', name: '品牌周边' },
    { tag: '加码奖', name: '满减券包' }
  ],
  rules: [
    '每日任务每天限完成一次，次日 00:00 刷新。',
    '终点大奖数量有限，先到先得。'
  ],
  popups: [
    {
      id: 'rewardResultPopup',
      kicker: '恭喜到站',
      title: '你抽中了终点加码礼',
      desc: '奖励已发放至账户，请前往“我的奖品”查看。'
    }
  ]
};
```

## What this mode should not do
- do not switch to other frameworks
- do not claim backend APIs that were never provided
- do not pretend the screenshot guarantees exact text, sizes, or hidden states
- do not reduce the delivery to empty containers and generic white cards
- do not replace a requested female-led hero with a male figure by default
- do not keep stacking modules vertically when a sticky tab layout would better fit H5 delivery
