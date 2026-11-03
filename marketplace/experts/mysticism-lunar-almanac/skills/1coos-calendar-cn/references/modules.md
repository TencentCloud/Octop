# 模块配置说明

`config.json` 中的 `modules` 字段控制各数据模块的开关。所有模块默认开启（`true`），设为 `false` 可关闭对应段落的数据提取和输出。

## 模块划分原则

按**信息层级**划分：核心层始终显示，可选层按用户关注的领域独立开关。

### 核心层（始终显示）

构成"今天是什么日子"的基本回答，不可关闭：

- 公历日期、星期
- 农历日期（年月日、干支纪年）
- 生肖、星座
- 季节、六曜、月相
- 农历节日
- 日禄

### 可选模块

| 模块 | 字段名 | 包含内容 | 典型用户 |
|------|--------|----------|----------|
| 干支纳音 | `ganZhi` | 年柱/月柱/日柱干支、纳音五行 | 命理、风水 |
| 宜忌 | `yiJi` | 每日宜忌事项、彭祖百忌 | 择日、婚嫁搬迁 |
| 冲煞 | `chongSha` | 冲生肖、煞方、胎神占方 | 择日、孕妇 |
| 节气 | `jieQi` | 当前/下一节气及日期 | 农事、养生 |
| 法定节假日 | `holiday` | 公历节日（元旦、劳动节等） | 通用 |
| 佛教 | `foto` | 佛教节日（观音诞等）、斋日（月斋/六斋/十斋/观音斋/朔望斋） | 佛教信众 |
| 道教 | `tao` | 道教节日（三清圣诞等） | 道教信众 |
| 星宿 | `xiu` | 二十八星宿、值神（十二天神）、建除十二值星 | 专业黄历 |
| 吉神凶煞 | `jiShen` | 吉神宜趋、凶煞宜忌 | 深度择日 |
| 吉神方位 | `positions` | 喜神/福神/财神/阳贵/阴贵方位 | 风水 |

## 配置示例

### 全量输出（默认）

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

### 精简模式（只看基本信息 + 宜忌）

```json
{
  "lang": "cn",
  "modules": {
    "ganZhi": false,
    "yiJi": true,
    "chongSha": false,
    "jieQi": true,
    "holiday": true,
    "foto": false,
    "tao": false,
    "xiu": false,
    "jiShen": false,
    "positions": false
  }
}
```

### 命理模式（干支 + 星宿 + 方位）

```json
{
  "lang": "cn",
  "modules": {
    "ganZhi": true,
    "yiJi": false,
    "chongSha": true,
    "jieQi": true,
    "holiday": false,
    "foto": false,
    "tao": false,
    "xiu": true,
    "jiShen": true,
    "positions": true
  }
}
```

## 语言配置

`lang` 字段控制日历数据的输出语言：

| 值 | 语言 | 说明 |
|----|------|------|
| `cn` | 简体中文 | 默认值 |
| `en` | English | 干支、生肖、星座、宜忌等翻译为英文 |

语言设置影响 `lunar-typescript` 库输出的数据内容（干支拼音、生肖英文名等），不影响格式化框架的中文标签（如"【基本信息】"）。
