---
scene: "lifestyle"
sub_scene: "health-data-analysis"
skills:
  - "garmin-pulse"
  - "apple-health-analyzer"
  - "samsung-health"
  - "health-sync"
  - "healthfit-cn"
  - "whoop-health-analysis"
---

# 健康数据分析工作流

你现在要为用户做一次完整的可穿戴/健康数据分析（含数据接入、长期趋势、慢病管理、指标解读教育）。你已安装以下 Skill，请按步骤串联使用：

## 步骤 1：Garmin 数据接入（输入层）
若用户使用 Garmin 设备，使用 **Garmin Pulse** 完成：
- 从 Garmin Connect 同步每日健康与运动数据：睡眠、活动、心率、压力、身体电量、HRV、血氧、体重
- 把数据写入本地 Markdown 文件，按日期/周/月分文件夹
- 校对时间范围与口径

输出 Garmin 标准化数据集（Markdown 文件目录）。

## 步骤 2：Apple Health 全量解析（输入层）
若用户使用 iPhone / Apple Watch，使用 **Apple Health Analyzer苹果健康数据分析** 完成：
- 让用户在 iPhone 上导出 Apple Health export.zip
- 流式解析 export.zip 中的 XML（支持 1-2 GB 大文件）
- 提取 RHR、HRV、VO2 Max、睡眠分期、步数、血氧、呼吸频率等核心指标
- 输入用户个人信息（年龄、性别、身高、体重、病史）做参考值动态校准

输出 Apple Health 结构化数据集 + 个性化参考值校准表。

## 步骤 3：三星健康/安卓阵营数据接入（输入层）
若用户使用三星 Galaxy Watch / 安卓设备，使用 **Samsung Health** 完成：
- 接入同步至 Google Drive 的三星健康数据
- 拉取睡眠分析、计步、心率、血氧、活动数据
- 与上述 Garmin/Apple 路径保持口径一致

输出三星健康标准化数据集。

## 步骤 4：多设备聚合（输入层 / 数据控用户）
若用户同时使用多设备（戒指 Oura + 床垫 Eight Sleep + 手表 Apple Watch + 体重秤 Withings + 运动 Strava + 训练 Hevy + 恢复 WHOOP），使用 **Health Sync** 完成：
- 聚合 Oura / Withings / Hevy / Strava / WHOOP / Eight Sleep 数据
- 处理同一指标在不同设备/算法下的口径差异（例如不同 HRV 算法）
- 输出统一聚合表，方便交叉对比

输出多设备聚合数据集 + 设备口径差异说明。

## 步骤 5：长期趋势 + 慢病 + 中医养生综合分析（处理层）
使用 **HealthFit-cn** 把上述输入层数据合并完成：
- 长期趋势分析：睡眠/HRV/RHR/VO2/体重/血氧的月/季/年趋势
- 接入体检报告、医疗记录、既往病史、用药情况
- 慢病管理：高血压、糖尿病、亚健康调理
- 营养补剂管理 + 中医养生视角（节气养生、体质辨识）
- 异常趋势预警（过度训练 / 恢复不足 / 持续疲劳）

输出综合健康档案 + 长期趋势报告 + 异常预警 + 慢病/中医养生建议。

## 步骤 6：指标解读教育（输出层）
使用 **Wearable Fitness Tech Guide** 完成：
- 对步骤 1-5 中出现的核心指标做通俗解读：HRV、VO2 Max、RHR、训练负荷、身体电量、睡眠分期等
- 给出按用户个人目标的个性化区间建议（休闲健身 vs 竞技训练区间不同）
- 警示常见误用（如把单日 HRV 波动当作大问题）
- 输出实用使用建议（什么时候量、用什么口径对比）

输出指标解读手册 + 个性化区间建议 + 常见误区提醒。

## 最终输出
将以上步骤的结果整合为完整的健康数据分析成果包，交付以下文件：
1. **设备数据集**：Garmin / Apple Health / 三星健康 / 多设备聚合（按用户实际设备）
2. **个性化参考值校准表**：基于用户年龄/性别/身高/体重/病史的指标基线
3. **综合健康档案**：含体检报告 + 病史 + 用药 + 中医体质
4. **长期趋势报告**：核心指标的月/季/年趋势 + 异常预警
5. **慢病/中医养生建议**：针对慢病管理与日常调理的可执行清单
6. **指标解读手册**：HRV / VO2 / RHR / 睡眠分期等术语的通俗解读 + 个性化区间
