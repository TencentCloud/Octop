# Mode example — architecture

## User input
The user sends a campaign reference and asks:

> 不要代码，帮我把这个新活动拆成页面模块、弹窗、状态流转和埋点方案，按 architecture mode 输出。

## Expected response shape

### Mode
architecture

### Page module plan
1. hero banner
2. dynamic activity stage
3. campaign info bar
4. checkpoint progress strip
5. daily task section
6. reward exchange / draw zone
7. reward pool section
8. rule section
9. record entry

### Module notes
- `hero banner`: communicates theme, date, and primary CTA
- `dynamic activity stage`: hosts the core generated mechanic and can switch between wheel draw, red-packet burst, sign-in stamp, scratch reveal, or treasure chest unlock
- `campaign info bar`: shows time range, eligibility, and shortcut actions
- `checkpoint progress strip`: visualizes progress and unlock milestones
- `daily task section`: lists task items and task states
- `reward exchange / draw zone`: handles the main reward action
- `reward pool section`: previews available rewards
- `rule section`: contains visible summary rules and entry to full rules popup
- `record entry`: links to user history or reward records

### Popup system
- `rulePopup`
- `rewardResultPopup`
- `insufficientChancePopup`
- `checkpointUnlockPopup`

### State flow
`init -> activityReady -> taskUpdated -> checkpointUnlocked -> chanceReady -> actionStarted -> resultShown`

### Tracking suggestions
- `activity_generated`
- `hero_cta_click`
- `activity_action_start`
- `task_action_click`
- `checkpoint_reward_view`
- `draw_start_click`
- `draw_result_view`
- `rules_open`

### Activity factory hint
- `activityFactory`: pick a generated activity family when the brief does not pin one
- `activityConfig`: keep chance count, milestone count, reward cadence, and visual preset configurable
- `animationSystem`: define one signature interaction animation plus two supporting motion layers
- `assetOutput`: reserve `./image/bg.png`, write final files under `project/<delivery-slug>/`, and require local delivery to create `project/`, `project/<delivery-slug>/`, and `project/<delivery-slug>/image/` first

### Delivery contract hint
Suggested file layout for later delivery mode:
- `project/<delivery-slug>/index.html`
- `project/<delivery-slug>/styles.css`
- `project/<delivery-slug>/main.js`
- `project/<delivery-slug>/mock-data.js`
- `project/<delivery-slug>/image/`

## What this mode should not do
- do not write large HTML/CSS/JS code blocks
- do not claim backend or API details unless the user provided them
