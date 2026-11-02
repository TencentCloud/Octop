# 肌群参考手册

## 6大主肌群

| 英文 | 中文 | 包含子肌群 |
|------|------|-----------|
| Chest | 胸部 | 上胸、中胸、下胸 |
| Back | 背部 | 背阔肌、中背、下背、斜方肌 |
| Shoulders | 肩部 | 前束、中束、后束 |
| Arms | 手臂 | 二头肌、三头肌、前臂 |
| Legs | 腿部 | 股四头肌、腘绳肌、臀肌、小腿 |
| Core | 核心 | 腹直肌、腹斜肌、腹横肌 |

## 18子肌群对照表（数据库字段值）

| 数据库值 | 中文 | 所属主肌群 | 数据库值 | 中文 | 所属主肌群 |
|----------|------|-----------|----------|------|-----------|
| chest | 胸肌整体 | Chest | shoulders | 肩部整体 | Shoulders |
| lats | 背阔肌 | Back | biceps | 二头肌 | Arms |
| middle back | 中背/菱形肌 | Back | triceps | 三头肌 | Arms |
| lower back | 下背/竖脊肌 | Back | forearms | 前臂 | Arms |
| traps | 斜方肌 | Back | quadriceps | 股四头肌 | Legs |
| hamstrings | 腘绳肌 | Legs | glutes | 臀大肌 | Legs |
| calves | 小腿 | Legs | adductors | 髋内收肌 | Legs |
| abductors | 髋外展肌 | Legs | abdominals | 腹直肌 | Core |
| neck | 颈部 | — | — | — | — |

## MEV 基准（Schoenfeld 2017）

最小有效训练容量（Minimum Effective Volume）：

- **周 MEV**: **10 组/周/肌群**
- **月 MEV**: 40 组/月/肌群（10 × 4 周）

状态评估：

| 实际/MEV | 标记 | 含义 |
|----------|------|------|
| ≥ 1.0 | ✅ 充足 | 训练量达标 |
| ≥ 0.5 | ⚠️ 偏低 | 需关注，可适当补量 |
| < 0.5 | 🔴 不足 | 明显欠练，需优先补量 |

> 参考: Schoenfeld BJ, et al. "Dose-response relationship between weekly resistance training volume and increases in muscle mass." _J Strength Cond Res_. 2017.

## MRV 与恢复参考

- **最大可恢复容量（MRV）**: 一般 20-25 组/周/肌群，超过则恢复跟不上
- **同一肌群最小间隔**: 48 小时
- **高强度训练后**: 可延长至 72-96 小时

## 常见肌群不平衡指标

| 不平衡表现 | 可能原因 | 调整建议 |
|-----------|---------|---------|
| 胸 > 背容量比 > 1.5:1 | 推多拉少 | 增加划船/引体频次或组数 |
| 股四头 > 腘绳 2:1+ | 腿推主导 | 增加罗马尼亚硬拉、腿弯举 |
| 前/中束 >> 后束 | 侧平举过多 | 加后束飞鸟、面拉 |
| 胸上束薄弱 | 缺上斜动作 | 优先安排上斜卧推/飞鸟 |
| 核心/腹肌为零计划中 | 忽视核心训练 | 每周至少1-2次核心训练 |
| 同侧容量偏差 > 30% | 训练日安排不均 | 检查周计划平衡性 |

## 主肌群 ↔ 数据库字段映射（App兼容）

App 使用 6 大主肌群枚举，数据库使用 18 子肌群。映射关系：

| App主肌群 | 数据库 primaryMuscles 值 |
|-----------|------------------------|
| chest | chest |
| back | lats, middle back, lower back, traps |
| shoulders | shoulders |
| arms | biceps, triceps, forearms |
| legs | quadriceps, hamstrings, glutes, calves, abductors, adductors |
| core | abdominals |
