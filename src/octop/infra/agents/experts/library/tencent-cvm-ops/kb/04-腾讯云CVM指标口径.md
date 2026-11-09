# 腾讯云 CVM 指标口径与取数方法

用于解释"页面上的数字为什么是这样"，以及自己在诊断时正确取数。

## 一、数据来源

| 数据 | 接口 | 命名空间 | 说明 |
|---|---|---|---|
| 实例清单/状态/规格/地域 | `cvm DescribeInstances` | — | 分页 100/次，多地域需按 region 循环 |
| CPU/内存/磁盘/网络/负载 | `monitor GetMonitorData` | `QCE/CVM` | 单次最多 50 个实例；数据点上限以接口为准（文档 7200，工作台按 1440 做保守降采样） |
| 地域列表 | `cvm DescribeRegions` | — | 排除 `UNAVAILABLE` |
| OS 层数据 | `tat RunCommand` | — | 需 TAT agent 在线，region-scoped |

## 二、指标名与单位

| 简称 | MetricName | 单位 | 是否依赖云监控组件 |
|---|---|---|---|
| CPU 使用率（页面用这个） | `CpuUsage` | % | **是** |
| 基础 CPU（页面不用） | `BaseCpuUsage` | % | 否，宿主机采集 |
| 内存使用率 | `MemUsage` | % | **是** |
| 磁盘使用率 | `CvmDiskUsage` | % | **是**。所有磁盘中的**最大值**，不能当成某个挂载点 |
| 分区使用率 | `DiskUsage` | % | **是**。维度要带 `diskname`，不是 `CvmDiskUsage` |
| 内网出/入带宽 | `LanOuttraffic` / `LanIntraffic` | Mbps | 否。页面网络用的是这一对 |
| 外网出/入带宽 | `WanOuttraffic` / `WanIntraffic` | Mbps | 否。标准账号上是该 CVM 绑定的 EIP 与公网 CLB 之和，不含 IPv6 |
| 1 分钟负载 | `CpuLoadavg` | 任务数 | **是**。1 分钟内使用和等待 CPU 的平均任务数，不是百分比。Windows 没有这项 |
| 5 / 15 分钟负载 | `Cpuloadavg5m` / `Cpuloadavg15m` | 任务数 | **是**。页面不用这两项 |

> `CpuUsage`、`MemUsage`、`CvmDiskUsage`、`CpuLoadavg` 在未安装**云监控组件**时返回空序列。空 ≠ 0。云监控组件和 TAT 的 `tat_agent` 是两个东西。

## 三、时间粒度与延迟

| 视图 | Period | 这个粒度上的统计方式 |
|---|---|---|
| 近 1 小时 | 60s | `CpuUsage`、`CpuLoadavg`、内网带宽是 **avg**；`CvmDiskUsage` 是 **max** |
| 近 24 小时 | 300s | CPU、磁盘、内网带宽都是 **max**，不是 5 分钟平均值 |
| 近 7 天 | 3600s | 同样是 **max**，不是 1 小时平均值 |

`CvmDiskUsage` 没有 10 秒粒度，最小 60 秒。不要对它传 `Period=10`。

- 云监控数据存在 **1–2 分钟延迟**，查询窗口末端应回退 120 秒再取，否则末点常常缺失
- 数据点按分钟对齐，同一指标不同实例的时间戳可能有秒级偏差，聚合前需按 period 取整分桶

## 四、聚合规则（页面与报告一致）

- 「最新值」= 序列末点。查询窗口已经比现在早 120 秒，末点不是请求时刻的瞬时值
- 60 秒粒度上，CPU 和内网带宽的点本身已是 avg；300 秒、3600 秒的点本身已是 max。不要再把 24 小时曲线上的点叫做「5 分钟平均值」
- 自己对一串点做平均时，分母只用实际取到的有效点，缺失点不补零
- 缺失点**不补零、不参与均值**；一个点都没有时显示 `—`
- 集群趋势 = 抽样实例在同一时间桶上的均值（抽样数量需在报告中标注）

## 五、常用查询命令

```bash
# 单实例 CPU（1 小时）
tccli monitor GetMonitorData --region ap-guangzhou \
  --Namespace QCE/CVM --MetricName CpuUsage \
  --Instances '[{"Dimensions":[{"Name":"InstanceId","Value":"ins-xxx"}]}]' \
  --Period 60 --StartTime "2026-10-28T13:00:00+08:00" --EndTime "2026-10-28T14:00:00+08:00"

# 多实例批量（官方单次最多 50 台；混入已销毁实例会让整批失败）
tccli monitor GetMonitorData --region ap-guangzhou \
  --Namespace QCE/CVM --MetricName CpuUsage \
  --Instances '[{"Dimensions":[{"Name":"InstanceId","Value":"ins-a"}]},{"Dimensions":[{"Name":"InstanceId","Value":"ins-b"}]}]' \
  --Period 60 --StartTime ... --EndTime ...

# 实例清单（分页）
tccli cvm DescribeInstances --region ap-guangzhou --Offset 0 --Limit 100
```

## 六、常见坑

| 坑 | 现象 | 处理 |
|---|---|---|
| 批量请求中混入已销毁实例 | 整批报 `InvalidParameterValue: instance destroyed`，全部无数据 | 二分拆分重试，剔除坏实例 |
| 内存/磁盘为空 | 该项显示 `—` | 说明未装监控组件，不要说 0% |
| 轻量服务器 | `QCE/CVM` 查不到 | 实例用 `lighthouse DescribeInstances`，监控命名空间用 `QCE/LIGHTHOUSE`。不要用 CVM 指标名硬套 |
| 跨地域查询 | 只返回指定 region 的数据 | 按 region 循环后合并 |
| 时间窗口末端 | 末点缺失/延迟 | 末端回退 120 秒 |

## 七、与其他产品的联合诊断

当 CVM 异常可能来自依赖服务时，查对应命名空间：

| 依赖 | Namespace | 关键指标 |
|---|---|---|
| MySQL(CDB) | `QCE/CDB` | `CpuUseRate`、`MemoryUseRate`、`ThreadsConnected`、`SlowQueries`。没有 `CPUUsage`。云盘版指标名要加 `Cluster` 前缀 |
| Redis | `QCE/REDIS_MEM` | 维度名是小写 `instanceid`。指标名以 `tccli monitor GetMonitorData help` 为准，不要套 CVM 的 `CpuUsage` |
| CLB | `QCE/LB_PUBLIC` 或 `QCE/LB_PRIVATE` | 维度是 `vip`。没有 `QCE/LOADBALANCE` |
| COS | `QCE/COS` | 维度是 `appid` + `bucket`，不是实例 ID |
