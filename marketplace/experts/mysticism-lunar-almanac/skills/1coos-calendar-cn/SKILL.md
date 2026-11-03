---
name: 1coos-calendar-cn
description: 查询中国传统日历/黄历信息。TRIGGER when user asks about Chinese calendar, lunar date, 农历, 黄历, 万年历, 节气, 五行， 宜忌, 干支，佛历，道历等。
version: 1.0.2
user-invocable: true
metadata: {"openclaw":{"requires":{"bins":["bun"]},"emoji":"📅"}}
---

# Calendar CN — 中国万年历/黄历

查询任意日期的完整中国传统日历信息，包括农历、干支、节气、宜忌、五行、冲煞、彭祖百忌、胎神、吉神凶煞、星宿、佛教/道教节日等。

## 使用方式

```
/1coos-calendar-cn [日期] [--lunar] [--help]
```

## 参数

| 参数 | 必需 | 说明 |
|------|------|------|
| `[日期]` | 否 | 公历日期，支持 `YYYY-MM-DD`、`YYYY/MM/DD`、`YYYYMMDD` 格式，默认今天 |
| `--lunar` | 否 | 标记输入的日期是农历日期 |
| `--config` | 否 | 指定配置文件路径（默认 skill 目录下的 config.json） |
| `--help` | 否 | 显示帮助信息 |

## 输出信息

- 公历/农历日期、星期
- 生肖、星座、季节
- 干支纪日（年柱、月柱、日柱）+ 纳音五行
- 宜忌事项
- 冲煞、彭祖百忌、胎神
- 吉神宜趋、凶煞宜忌
- 节气（当前/下一个）
- 节日（公历节日、农历节日、佛教节日/斋日、道教节日）
- 二十八星宿、值神、建除十二值星
- 吉神方位（喜神、福神、财神、阳贵、阴贵）
- 六曜、月相、日禄

## 示例

```bash
# 查询今天的黄历
/1coos-calendar-cn

# 查询指定公历日期
/1coos-calendar-cn 2024-02-10

# 查询农历日期（如农历2024年二月十九 观音诞）
/1coos-calendar-cn 2024-02-19 --lunar

# 紧凑日期格式
/1coos-calendar-cn 20240915
```

## 执行指令

当用户调用此 skill 时：

1. **运行脚本**：执行以下命令：
   ```bash
   bun run /path/to/skills/1coos-calendar-cn/scripts/main.js <用户参数>
   ```
2. **展示结果**：将脚本输出直接展示给用户。
3. **处理错误**：
   - 退出码 0：成功
   - 退出码 2：参数错误（无效日期格式等）

## 配置

通过 `config.json` 配置语言和数据模块开关（详见 `references/modules.md`）：

```json
{
  "lang": "cn",
  "modules": {
    "ganZhi": true,
    "yiJi": true,
    "chongSha": true,
    "jieQi": true,
    "holiday": true,
    "foto": true,
    "tao": true,
    "xiu": true,
    "jiShen": true,
    "positions": true
  }
}
```

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| `lang` | 语言：`cn`（简体中文）、`en`（英文） | `cn` |
| `modules.ganZhi` | 干支纪日、纳音五行 | `true` |
| `modules.yiJi` | 宜忌事项、彭祖百忌 | `true` |
| `modules.chongSha` | 冲煞、胎神占方 | `true` |
| `modules.jieQi` | 节气信息 | `true` |
| `modules.holiday` | 法定节假日（公历节日） | `true` |
| `modules.foto` | 佛教节日/斋日（观音诞等） | `true` |
| `modules.tao` | 道教节日 | `true` |
| `modules.xiu` | 二十八星宿、值神、建除 | `true` |
| `modules.jiShen` | 吉神宜趋/凶煞宜忌 | `true` |
| `modules.positions` | 吉神方位（喜神、福神、财神等） | `true` |

CLI 参数 `--config` 可指定自定义配置文件路径。

## 技术说明

- 所有日历计算由 [lunar-typescript](https://github.com/6tail/lunar-typescript) 库本地完成
- 无需网络连接，无外部依赖
- 支持公历/农历双向转换

## 安全说明

此 skill 的打包产物体积较大（~300KB），因为内嵌了 lunar-typescript 库的完整天文计算数据表：
- **节假日数据**（HolidayUtil.DATA）：2001-2026 年中国法定节假日编码表（纯数字）
- **天文历法数据**（ShouXingUtil.QB/SB）：寿星万年历天文计算查表数据（字母编码）

这些数据是日历计算的核心查表数据，非可执行代码。源库地址：https://github.com/6tail/lunar-typescript
