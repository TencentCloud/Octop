# 跨境电商商品文案智能生成器
## Skill基本信息
- **Skill名称**：跨境电商商品文案生成助手（A/B测试+多小语种版）
- **适用场景**：Amazon、SHEIN、Temu、Shopee、TikTok Shop等跨境平台商品文案生成
- **核心功能**：多语种文案生成、A/B测试多版本输出、合规检查、字符长度自动适配、SEO关键词植入

## 一、Skill简介
本Skill是一款专为跨境电商卖家打造的智能文案生成工具，支持多平台、多语种、多风格文案输出，新增A/B测试多版本生成、小语种适配、合规检查、字符长度自动适配四大核心能力，可快速生成符合平台规则、适配目标市场的商品标题、短描述、详细描述及卖点列表，提升商品搜索曝光和转化率。

## 二、核心功能
### 1. 原有核心能力（保留并优化）
- 智能关键词植入：自动将用户提供的SEO关键词自然融入文案，提升搜索排名
- 平台风格适配：根据不同跨境平台规则，生成适配风格的文案（如Amazon专业风、TikTok营销风）
- 多语言自动生成：支持中文、英文及中英双语，符合海外用户阅读习惯
- 卖点结构化：自动整理零散卖点为清晰的bullet points，提升文案可读性
- 营销话术库内置：覆盖跨境通用营销表达，适配不同风格需求

### 2. 新增核心能力
#### （1）A/B测试多版本自动生成
- 版本数量：支持1-5个版本生成，满足不同平台A/B测试需求
- 差异类型：
  - keyword：关键词顺序差异，测试关键词权重影响
  - tone：风格差异，同一商品生成不同风格文案（专业/营销/轻奢/亲民）
  - structure：结构差异，调整文案段落、卖点排序
  - content：内容侧重点差异，针对不同卖点侧重描述
- 一致性保障：多版本文案保留核心卖点和关键词，仅在指定维度调整

#### （2）小语种支持（6种语言全覆盖）
- 支持语种：西班牙语（es）、法语（fr）、德语（de）、日语（ja）、阿拉伯语（ar）+ 中英双语
- 本地化适配：
  - 阿拉伯语：适配从右到左阅读习惯，调整排版
  - 日语：适配敬语使用场景，贴合日本消费者习惯
  - 西/法/德语：适配当地电商营销话术，避免文化禁忌
- 小语种营销话术库：内置各语种4种风格专属话术，无需手动编写

#### （3）合规检查（侵权+违禁+平台违规）
- 内置合规词库：整合主流平台侵权词、违禁词，覆盖多语种，实时可更新
- 智能检测与修正：自动扫描文案中的违规内容，进行同义替换；无法替换时提示用户修改
- 多语种合规适配：针对各小语种市场特殊合规要求优化（如欧盟CE认证表述、阿拉伯语宗教禁忌）

#### （4）自动适配字符长度
- 平台限制内置：预设Amazon、Temu等主流平台各模块字符限制，自动适配
- 智能压缩/扩充：超出限制时压缩冗余词汇（保留核心信息），不足时补充卖点话术
- 小语种适配：针对不同语种字符特性，调整计数逻辑，确保符合平台要求

## 三、输入参数说明
| 参数名        | 类型    | 必填 | 说明                                                                 |
|---------------|---------|------|----------------------------------------------------------------------|
| product_name  | 字符串  | 是   | 商品名称（中文/英文均可，小语种生成时自动翻译适配）                   |
| category      | 字符串  | 否   | 品类：3C/服装/家居/美妆/户外/家电/饰品等                             |
| platform      | 字符串  | 否   | 目标平台：Amazon/Shopee/Temu/TikTok等（默认Amazon）                  |
| language      | 字符串  | 否   | 输出语言：en/zh/bilingual/es/fr/de/ja/ar（默认en）                   |
| keywords      | 数组    | 否   | 搜索关键词/SEO词列表（支持小语种关键词，自动融入文案）               |
| features      | 数组    | 否   | 商品卖点：材质、功能、尺寸、优势等（小语种生成时自动翻译卖点）       |
| tone          | 字符串  | 否   | 风格：professional/marketing/luxury/casual（默认professional）       |
| length        | 字符串  | 否   | 长度：short(标题)/medium(短描述)/long(详情)（默认long）              |
| ab_version    | 数字    | 否   | A/B测试版本数量：1-5（默认1个版本）                                  |
| ab_diff_type  | 字符串  | 否   | 版本差异类型：keyword/tone/structure/content（默认keyword）          |

## 四、输出结构说明
### 1. 输出格式
JSON格式，支持单版本和多版本（A/B测试）输出，包含以下核心字段：
```json
{
  "ab_version_count": 2,          // A/B测试版本总数
  "ab_diff_type": "keyword",      // 版本差异类型
  "versions": [                   // 多版本文案数组
    {
      "version": "A",             // 版本标识（A/B/C/D/E）
      "title": "商品标题",         // 平台SEO标题
      "short_description": "短描述", // 主图下方/卡片短描述
      "long_description": "详细描述", // 商品详情页描述
      "bullet_points": ["卖点1", "卖点2"], // 卖点列表
      "tags": ["标签1", "标签2"], // 商品标签（SEO用）
      "language": "de",           // 输出语言
      "platform_fit": "Amazon",   // 适配平台
      "compliance_check": {       // 合规检查结果
        "status": "通过",
        "suggestion": ""
      },
      "character_adaptation": {   // 字符适配详情
        "title": "138字符（≤200字符，符合Amazon要求）",
        "short_description": "126字符（≤150字符，符合Amazon要求）",
        "long_description": "386字符（≤500字符，符合Amazon要求）"
      }
    }
  ]
}
```

### 2. 输出说明
- 合规检查：返回通过/未通过状态，未通过时给出具体修改建议
- 字符适配：明确标注各模块字符数及是否符合平台要求
- 多版本：所有版本均同步适配合规和字符限制，无需单独调整

## 五、示例调用与输出
### 示例调用（Prompt模板）
```plain text
生成跨境电商文案
商品：便携式无线蓝牙耳机
品类：3C数码
平台：Amazon（欧洲站）
语言：de（德语）
关键词：drahtlose Ohrhörer, Bluetooth 5.3, Rauschunterdrückung, 24h Spielzeit
卖点：降噪、长续航、轻便、防水、触控
风格：professional
长度：完整
ab_version：2
ab_diff_type：keyword
```

### 示例输出（精简版）
```json
{
  "ab_version_count": 2,
  "ab_diff_type": "keyword",
  "versions": [
    {
      "version": "A",
      "title": "Drahtlose Ohrhörer Bluetooth 5.3 mit Rauschunterdrückung und 24h Spielzeit, wasserdicht, berührungsempfindlich",
      "short_description": "Leichte drahtlose Ohrhörer mit fortschrittlicher Rauschunterdrückung, 24h langer Spielzeit, IPX5 wasserdicht und intelligenter Berührungssteuerung für den täglichen Gebrauch.",
      "long_description": "Erleben Sie eine hervorragende Klangqualität mit unseren drahtlosen Ohrhörern mit Bluetooth 5.3 für eine stabile Verbindung...",
      "bullet_points": [
        "Verwendet Bluetooth 5.3 für eine schnelle und stabile Verbindung",
        "Effektive Rauschunterdrückung für klare Tonqualität in jeder Umgebung"
      ],
      "tags": ["drahtlose Ohrhörer", "Rauschunterdrückung", "Bluetooth Ohrhörer"],
      "language": "de",
      "platform_fit": "Amazon（欧洲站）",
      "compliance_check": {"status": "通过", "suggestion": ""},
      "character_adaptation": {
        "title": "138字符（≤200字符，符合Amazon要求）",
        "short_description": "126字符（≤150字符，符合Amazon要求）",
        "long_description": "386字符（≤500字符，符合Amazon要求）"
      }
    },
    {
      "version": "B",
      "title": "Bluetooth 5.3 Drahtlose Ohrhörer, 24h Spielzeit mit Rauschunterdrückung, wasserdicht und berührungsempfindlich",
      "short_description": "Drahtlose Ohrhörer mit 24h langer Spielzeit, fortschrittlicher Rauschunterdrückung, IPX5 wasserdicht und intelligenter Berührungssteuerung – ideal für den täglichen Gebrauch.",
      "long_description": "Erleben Sie eine hervorragende Klangqualität mit unseren drahtlosen Ohrhörern mit Bluetooth 5.3 für eine stabile Verbindung...",
      "bullet_points": [
        "Verwendet Bluetooth 5.3 für eine schnelle und stabile Verbindung",
        "Effektive Rauschunterdrückung für klare Tonqualität in jeder Umgebung"
      ],
      "tags": ["Bluetooth Ohrhörer", "drahtlose Ohrhörer", "Rauschunterdrückung"],
      "language": "de",
      "platform_fit": "Amazon（欧洲站）",
      "compliance_check": {"status": "通过", "suggestion": ""},
      "character_adaptation": {
        "title": "132字符（≤200字符，符合Amazon要求）",
        "short_description": "128字符（≤150字符，符合Amazon要求）",
        "long_description": "386字符（≤500字符，符合Amazon要求）"
      }
    }
  ]
}
```

## 六、部署与运行
### 1. 运行环境
- Python 3.7及以上版本
- 无额外依赖库（使用原生Python库）

### 2. 运行方式
#### 方式1：直接运行
```bash
python cross_border_copywriter_v2.py
```
运行后将执行测试代码，输出示例文案结果

#### 方式2：作为模块调用
```python
from cross_border_copywriter_v2 import CrossBorderCopywriter

# 定义输入参数
params = {
    "product_name": "便携式无线蓝牙耳机",
    "category": "3C数码",
    "platform": "Amazon",
    "language": "de",
    "keywords": ["drahtlose Ohrhörer", "Bluetooth 5.3"],
    "features": ["降噪", "长续航"],
    "ab_version": 2,
    "ab_diff_type": "keyword"
}

# 生成文案
writer = CrossBorderCopywriter()
result = writer.generate_copy(params)
print(result)
```

## 七、扩展能力（可升级）
1.  结合AI生成配图描述（SEO alt text）
2.  小语种文化适配优化（针对不同市场调整营销话术）
3.  合规词库实时更新（同步各平台最新规则）
4.  自定义字符限制（支持用户手动设置平台字符标准）

## 八、注意事项
1.  输入参数中，product_name为必填项，其他参数可根据需求选择填写
2.  小语种生成时，确保language参数填写正确（es/fr/de/ja/ar）
3.  若需调整平台字符限制，可修改.py文件中platform_char_limit配置
4.  合规词库需根据平台规则定期更新，避免违规风险
5.  A/B测试版本数量建议不超过5个，确保测试变量清晰
