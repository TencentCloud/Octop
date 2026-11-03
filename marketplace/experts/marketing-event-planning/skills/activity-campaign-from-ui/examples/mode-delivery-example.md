# Mode example — delivery

## User input
The user sends one campaign reference and asks:

> 我只要更像可上线成品的前端 H5 页面，固定 H5 / Web，技术栈 HTML + CSS + JS。首屏要有美女人物主视觉，如果我没给人物图就生成一张页面效果图，图片一定要在页面最上面，整体不要拉得太长，走 delivery mode。

## Expected response shape

### Mode
delivery

### Delivery notes
- keep the implementation H5/Web only
- use HTML + CSS + JavaScript only
- output a launch-ready-feeling high-fidelity draft, not a bare wireframe or starter shell
- do not claim pixel-perfect recovery from the screenshot
- summarize the likely visual language before code
- use one adult female hero figure as the dominant first-screen visual focus
- generate a new female hero asset for `./image/bg.png` instead of leaving a placeholder image slot
- push `./image/bg.png` toward a photorealistic commercial-poster result with natural skin, hair, hands, and lighting
- keep the generated image focused on the woman and festive atmosphere rather than embedding prize cards, invitation boards, or lower-page layouts from the references
- use the references as style direction only; do not recreate the same woman's face, pose, or dual-character composition unless the user explicitly asks for it
- keep the first visible block at the top of the page as the hero image itself
- generate the asset used for `./image/bg.png` in the current run before writing the front-end files
- if the host exposes a concrete tool such as `image_generate`, call it directly
- default to `regenerate_each_run` unless the user explicitly asks to reuse an existing image asset
- if image generation is unavailable for this brief, stop and report the run as blocked instead of downgrading to placeholders
- keep the female wardrobe and styling aligned with the campaign theme
- allow glamorous and slightly sexy commercial-fashion styling, while staying suitable for a public campaign page
- prefer sticky tabs when the H5 would otherwise become too long
- when the brief is open, generate a configurable activity family instead of being limited to the reference mechanic
- add one signature interaction animation plus supporting ambient motion so the page feels closer to a live activity page
- if the user explicitly asks for local files and Python/local execution is available, the generated front-end files should be written under `project/<delivery-slug>/`
- when Python writes the local files, create `project/`, `project/<delivery-slug>/`, and `project/<delivery-slug>/image/` first and save the generated hero image to `project/<delivery-slug>/image/bg.png`
- when local output was requested, do not stop at the file tree; actually write the files and return the written paths

### File structure
- `project/<delivery-slug>/index.html`
- `project/<delivery-slug>/styles.css`
- `project/<delivery-slug>/main.js`
- `project/<delivery-slug>/mock-data.js`
- `project/<delivery-slug>/image/`
- `project/<delivery-slug>/image/bg.png` for the top hero visual

### Asset handoff note
`需要把生成好的图片，改名为bg，图片类型为 png，放到 project/<delivery-slug>/image 目录下`

### Visual extraction summary
- warm festive palette with red, gold, and cream contrast
- adult female hero in a red-dominant festive outfit with gold details and lantern accents
- `./image/bg.png` should read like a new photorealistic female hero image with festive atmosphere, not a screenshot-like page collage
- first screen is anchored by the woman, title art, and a loud draw-machine device instead of a text-only layout
- content below the hero is compressed into sticky tabs rather than a long vertical stack
- modules feel like decorated panels, not plain white cards
- the page should include a core spectacle motion such as wheel spin or reward burst, plus ambient sparkle drift, CTA pulse, and popup rise-in
- CTA area is loud and centered, with glow and badge support
- popup style should feel celebratory and branded

### index.html
```html
<div class="page-shell">
  <div class="page-bg-glow page-bg-glow-left"></div>
  <div class="page-bg-glow page-bg-glow-right"></div>

  <main class="festival-page">
    <section id="hero" class="hero-banner">
      <div class="hero-top-visual">
        <img class="hero-top-image" src="./image/bg.png" alt="春节活动首屏主视觉" />
        <div class="hero-top-overlay">
          <p class="hero-badge">春节限定</p>
          <h1 class="hero-title">吃瓜网春游活动</h1>
          <p class="hero-subtitle">完成每日任务赢抽奖机会，解锁限定好礼与终极红包大奖。</p>
          <div class="hero-meta">
            <span class="meta-pill">12.26 - 01.01</span>
            <span class="meta-pill">美女主理人助阵</span>
          </div>
          <div class="hero-actions">
            <button class="hero-main-cta js-open-popup" data-popup="rewardResultPopup">立即开抽</button>
            <button class="hero-secondary-cta js-switch-tab" data-tab="tasks">先做任务</button>
          </div>
        </div>
        <aside class="hero-machine-card">
          <span class="hero-card-kicker">今日主奖</span>
          <strong class="hero-card-value">888 元新春礼盒</strong>
          <p class="hero-card-copy">完成任务可得抽奖次数，晚 20:00 额外掉落红包雨。</p>
        </aside>
      </div>
    </section>

    <section class="hero-summary-panel">
      <div class="summary-chip">
        <span>当前抽奖机会</span>
        <strong>3 次</strong>
      </div>
      <div class="summary-chip">
        <span>已完成任务</span>
        <strong>2 / 5</strong>
      </div>
      <div class="summary-chip summary-chip-hot">
        <span>下一档奖励</span>
        <strong>再做 1 个任务</strong>
      </div>
    </section>

    <nav class="sticky-tabs" aria-label="活动内容导航">
      <button class="sticky-tab is-active js-switch-tab" data-tab="tasks">任务</button>
      <button class="sticky-tab js-switch-tab" data-tab="prizes">奖池</button>
      <button class="sticky-tab js-switch-tab" data-tab="rules">规则/记录</button>
    </nav>

    <section id="tab-tasks" class="tab-panel is-active"></section>
    <section id="tab-prizes" class="tab-panel"></section>
    <section id="tab-rules" class="tab-panel"></section>
  </main>
</div>

<div id="popup-root"></div>
```

### styles.css
```css
:root {
  --bg-top: #7d1018;
  --bg-bottom: #c63a2d;
  --panel-fill: linear-gradient(180deg, #fff7df 0%, #ffe8bb 100%);
  --panel-stroke: rgba(255, 245, 205, 0.84);
  --text-strong: #72140d;
  --text-soft: #9a3d22;
  --gold: #ffd46a;
  --gold-deep: #ffad2e;
  --shadow-panel: 0 18px 40px rgba(102, 12, 8, 0.22);
  --shadow-cta: 0 10px 24px rgba(171, 42, 0, 0.35);
  --radius-xl: 28px;
  --radius-lg: 22px;
}

* { box-sizing: border-box; }

body {
  margin: 0;
  font-family: "PingFang SC", "Microsoft YaHei", sans-serif;
  color: var(--text-strong);
  background:
    radial-gradient(circle at top, rgba(255, 226, 135, 0.28), transparent 28%),
    linear-gradient(180deg, var(--bg-top) 0%, var(--bg-bottom) 42%, #f25c38 100%);
}

.festival-page {
  max-width: 750px;
  margin: 0 auto;
  padding: 20px 16px 36px;
}

.hero-banner,
.hero-summary-panel,
.tab-panel {
  position: relative;
  overflow: hidden;
  border-radius: var(--radius-xl);
  border: 1px solid var(--panel-stroke);
  box-shadow: var(--shadow-panel);
}

.hero-banner {
  padding: 0;
  margin-bottom: 14px;
  background:
    radial-gradient(circle at top, rgba(255, 235, 159, 0.78), transparent 34%),
    linear-gradient(145deg, #a91516 0%, #d73e2f 46%, #ff874f 100%);
  color: #fff8ea;
}

.hero-top-visual {
  position: relative;
  min-height: 540px;
}

.hero-top-image {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: cover;
  object-position: top center;
}

.hero-top-overlay {
  position: absolute;
  inset: auto 20px 20px 20px;
  z-index: 1;
}

.hero-top-visual::after {
  content: "";
  position: absolute;
  inset: 0;
  background: linear-gradient(180deg, rgba(59, 0, 0, 0.04), rgba(85, 9, 12, 0.12) 38%, rgba(74, 7, 8, 0.72) 100%);
  pointer-events: none;
}

.hero-main-cta {
  animation: ctaPulse 1.9s ease-in-out infinite;
}

.hero-machine-card {
  animation: floatCard 3.2s ease-in-out infinite;
}

.festival-page::before {
  content: "";
  position: fixed;
  inset: 0;
  background:
    radial-gradient(circle, rgba(255, 219, 116, 0.28) 0 8%, transparent 9%) 12% 18% / 120px 120px,
    radial-gradient(circle, rgba(255, 244, 205, 0.18) 0 7%, transparent 8%) 78% 24% / 160px 160px;
  pointer-events: none;
  animation: sparkleDrift 10s linear infinite;
}

@keyframes ctaPulse {
  0%, 100% { transform: scale(1); box-shadow: var(--shadow-cta); }
  50% { transform: scale(1.03); box-shadow: 0 14px 32px rgba(171, 42, 0, 0.42); }
}

@keyframes floatCard {
  0%, 100% { transform: translateY(0); }
  50% { transform: translateY(-6px); }
}

@keyframes sparkleDrift {
  0% { transform: translate3d(0, 0, 0); }
  100% { transform: translate3d(0, 18px, 0); }
}

.hero-summary-panel {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
  padding: 14px;
  margin-bottom: 14px;
  background: var(--panel-fill);
}

.sticky-tabs {
  position: sticky;
  top: 0;
  z-index: 5;
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 10px;
  padding: 10px 0 14px;
  background: linear-gradient(180deg, rgba(125, 16, 24, 0.98), rgba(125, 16, 24, 0));
}

.sticky-tab {
  height: 44px;
  border: 0;
  border-radius: 999px;
  font-weight: 700;
  color: #ffe9b0;
  background: rgba(255, 241, 195, 0.14);
}

.sticky-tab.is-active {
  color: #7a180a;
  background: linear-gradient(180deg, #ffe59a 0%, #ffbc46 100%);
  box-shadow: var(--shadow-cta);
}

.tab-panel {
  display: none;
  padding: 18px;
  margin-bottom: 14px;
  background: var(--panel-fill);
}

.tab-panel.is-active {
  display: block;
}
```

### main.js
```javascript
document.addEventListener('DOMContentLoaded', function () {
  renderPage(window.campaignData);
  bindEvents();
  primeHeroMotion(window.campaignData.animationSystem);
  setActiveTab('tasks');
});

function renderPage(data) {
  document.getElementById('tab-tasks').innerHTML = renderTasks(data.tasks);
  document.getElementById('tab-prizes').innerHTML = renderPrizePanel(data.prizePool);
  document.getElementById('tab-rules').innerHTML = renderRulesPanel(data.rules, data.records);
}

function renderTasks(tasks) {
  return tasks.map(function (task) {
    return '<article class="task-card">' +
      '<div><p class="task-tag">' + task.tag + '</p><h3>' + task.title + '</h3><p>' + task.desc + '</p></div>' +
      '<button class="task-cta">' + task.ctaText + '</button>' +
    '</article>';
  }).join('');
}

function renderPrizePanel(prizePool) {
  return '<div class="panel-head"><h2>奖池一览</h2><span>' + prizePool.tip + '</span></div>' +
    '<div class="prize-grid">' + prizePool.items.map(function (item) {
      return '<div class="prize-chip"><span>' + item.name + '</span><b>' + item.stock + '</b></div>';
    }).join('') + '</div>';
}

function renderRulesPanel(rules, records) {
  return '<div class="panel-head"><h2>活动说明</h2><button class="text-link js-open-popup" data-popup="recordPopup">查看中奖记录</button></div>' +
    '<ol class="rules-list">' + rules.map(function (rule) {
      return '<li>' + rule + '</li>';
    }).join('') + '</ol>' +
    '<div class="record-strip">' + records.map(function (item) {
      return '<span>' + item + '</span>';
    }).join('') + '</div>';
}

function bindEvents() {
  document.querySelector('.festival-page').addEventListener('click', function (event) {
    var tabTrigger = event.target.closest('.js-switch-tab');
    if (tabTrigger) {
      setActiveTab(tabTrigger.getAttribute('data-tab'));
      return;
    }

    var popupTrigger = event.target.closest('.js-open-popup');
    if (popupTrigger) {
      openPopup(popupTrigger.getAttribute('data-popup'));
    }
  });
}

function primeHeroMotion(animationSystem) {
  document.documentElement.setAttribute('data-motion-preset', animationSystem.primarySequence);
}

function setActiveTab(tabKey) {
  document.querySelectorAll('.sticky-tab').forEach(function (tab) {
    tab.classList.toggle('is-active', tab.getAttribute('data-tab') === tabKey);
  });

  document.querySelectorAll('.tab-panel').forEach(function (panel) {
    panel.classList.toggle('is-active', panel.id === 'tab-' + tabKey);
  });
}

function openPopup(id) {
  var popup = window.campaignData.popups.filter(function (item) {
    return item.id === id;
  })[0];

  document.getElementById('popup-root').innerHTML =
    '<div class="popup-mask is-open">' +
      '<div class="reward-popup">' +
        '<p class="popup-kicker">' + popup.kicker + '</p>' +
        '<h3>' + popup.title + '</h3>' +
        '<p>' + popup.desc + '</p>' +
      '</div>' +
    '</div>';
}
```

### mock-data.js
```javascript
window.campaignData = {
  activityFactory: {
    activityFamily: 'lucky-draw-stage',
    supportingMechanics: ['daily-task', 'red-packet-burst']
  },
  animationSystem: {
    primarySequence: 'drawBurst',
    ambientLayers: ['sparkleDrift', 'ctaPulse']
  },
  tasks: [
    { tag: '每日任务', title: '浏览主会场 30 秒', desc: '完成后可获得 1 次抽奖机会', ctaText: '去完成' },
    { tag: '加速任务', title: '邀请好友助力 1 次', desc: '完成后额外获得 2 次抽奖机会', ctaText: '去邀请' }
  ],
  prizePool: {
    tip: '每晚 20:00 更新剩余库存',
    items: [
      { name: '888 元礼盒', stock: 'x3' },
      { name: '免单券', stock: 'x48' },
      { name: '红包雨加码卡', stock: 'x188' }
    ]
  },
  rules: [
    '活动期间每日任务可重复完成一次，奖励次日刷新。',
    '中奖结果以系统发放为准，过期不补发。'
  ],
  records: ['用户 138****8821 抽中红包', '用户 159****1688 抽中礼盒'],
  popups: [
    {
      id: 'rewardResultPopup',
      kicker: '恭喜中奖',
      title: '你获得 1 次红包雨加码机会',
      desc: '继续完成任务可解锁更高档位奖池。'
    },
    {
      id: 'recordPopup',
      kicker: '实时滚动',
      title: '中奖记录',
      desc: '最近 10 分钟已有 18 人抽中实物奖励。'
    }
  ]
};
```

## What this mode should not do
- do not switch to Vue, React, or Uni-app
- do not add backend integration claims
- do not collapse into neutral white-card scaffolding
- do not replace the requested adult female hero with a male figure by default
- do not stack every module vertically until the H5 becomes excessively long
- do not generate a full new campaign strategy unless requested elsewhere
