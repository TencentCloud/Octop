---
name: taobao-product-research
description: 淘宝产品调研和数据采集工具。用于采集淘宝商品信息，包括主图、标题、价格、销量、评价数、店铺等，并生成包含图片的Excel报告。使用场景：(1) 市场调研和竞品分析，(2) 产品价格监控，(3) 销量数据统计，(4) 产品信息批量采集。当用户需要采集淘宝产品数据、进行电商调研、获取商品信息时触发此Skill。
---

# 淘宝产品调研工具

淘宝产品数据采集和调研工具，支持按关键词、价格区间筛选，自动提取产品信息并生成Excel报告。

## 功能特性

- 🔍 **关键词搜索** - 支持任意关键词搜索
- 💰 **价格筛选** - 支持价格区间过滤
- 📊 **数据提取** - 自动提取标题、价格、销量、评价数、店铺
- 🖼️ **图片采集** - 下载产品主图并嵌入Excel
- 🔗 **链接生成** - 生成可点击的商品链接
- 📁 **Excel输出** - 生成格式化的Excel报告

## 使用方法

### 命令行方式

```bash
cd skills/taobao-product-research/scripts
node taobao_research.js <关键词> <价格区间> <数量> [输出目录]
```

**参数说明:**
- `关键词` - 搜索关键词，如 "AI机器人"
- `价格区间` - 价格范围，格式 "min-max"，如 "0-169"
- `数量` - 需要采集的产品数量
- `输出目录` - (可选) 输出文件保存路径

**示例:**
```bash
# 基础用法
node taobao_research.js "AI机器人" "0-169" 15

# 指定输出目录
node taobao_research.js "智能手表" "100-500" 20 ./output

# 高价产品调研
node taobao_research.js "无人机" "1000-5000" 10
```

### 程序化调用

```javascript
const { TaobaoResearcher } = require('./taobao_research.js');

const researcher = new TaobaoResearcher({
    keyword: 'AI机器人',
    priceMin: 0,
    priceMax: 169,
    maxItems: 15,
    outputDir: './research_output'
});

researcher.run().then(result => {
    console.log('完成:', result);
});
```

## 首次使用

1. **安装依赖**
   ```bash
   cd skills/taobao-product-research/scripts
   npm install
   ```

2. **登录淘宝**
   - 首次运行时会自动打开浏览器
   - 手动完成淘宝登录
   - 按回车键继续
   - 登录状态会保存在 `browser_data` 目录，后续无需重复登录

## 输出文件

生成的Excel文件包含以下字段:

| 字段 | 说明 |
|-----|------|
| 序号 | 排名 |
| 主图 | 产品图片（嵌入） |
| 标题 | 产品名称 |
| 价格 | 实际售价 |
| 销量 | 付款人数 |
| 评价数 | 评价数量 |
| 店铺 | 店铺名称 |
| 链接 | 可点击的商品链接 |

文件命名格式: `taobao_<关键词>_<价格区间>_<时间戳>.xlsx`

## 注意事项

1. **反爬机制** - 淘宝有反爬机制，建议:
   - 控制采集频率（脚本已内置随机延迟）
   - 单次采集数量不宜过多（建议10-20个）
   - 不同价格区间之间间隔10秒以上

2. **登录状态** - 需要保持淘宝登录状态，如遇到登录失效请重新登录

3. **网络环境** - 确保网络稳定，避免因网络问题导致数据提取失败

4. **价格筛选** - 脚本会双重验证价格，确保在指定范围内

## 故障排查

**问题: 无法提取数据**
- 检查是否已登录淘宝
- 查看 `debug_*.png` 截图文件
- 可能是页面结构变化，需要更新选择器

**问题: 图片下载失败**
- 检查网络连接
- 图片URL可能已过期，不影响其他数据

**问题: 评价数获取失败**
- 部分商品可能没有评价
- 详情页加载超时，已设置5秒等待时间

## 依赖项

- `playwright` - 浏览器自动化
- `xlsx` - Excel文件处理
- `exceljs` - Excel图片嵌入

## 文件结构

```
skills/taobao-product-research/
├── SKILL.md
└── scripts/
    ├── package.json
    └── taobao_research.js
```

运行后生成的文件:
```
taobao_research/
├── browser_data/          # 浏览器数据（登录状态）
├── images/               # 下载的产品图片
│   ├── 0-169/
│   └── 169-349/
└── taobao_*.xlsx        # Excel报告
```
