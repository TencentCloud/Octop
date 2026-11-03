---
name: walter-product-research
version: 1.0.0
description: "亚马逊选品调研 - 回答"能不能做"的问题。快速扫描→市场分析→利润测算→竞品发现→风险评估，输出GO/NO-GO决策报告。"
---

# 亚马逊选品调研

## 核心问题

**"我这个想法能不能做？"**

## 用户交互

### 输入

```
用户: "我想做沙滩裤"
用户: "women active shorts能不能做"
用户: "分析下这个市场"
```

### 输出

```
[选品调研报告]

[Decision] GO / CAUTION / NO-GO
[Score] 72/100

├─ 市场容量: 640,240 units/月
├─ 竞争程度: CR3=63% (高)
├─ 市场趋势: +8.5%/月 (上升)
├─ 利润空间: $2.08/unit (8.3%)
└─ 风险提示: 高品牌集中度

[详细报告] [竞品分析] [生成Listing]
```

---

## 分析流程

### Step 1: 快速扫描 (30秒)

- 机会评分 (0-100)
- 市场容量评估
- 竞争程度评估
- 趋势判断

### Step 2: 市场分析

- 品牌集中度 (CR3/CR5)
- 价格带分布
- 头部玩家分析

### Step 3: 利润测算

- 定价建议
- 成本结构分解
- 利润优化场景

### Step 4: 竞品发现

- Top 5 竞品
- 各竞品基础数据
- 差异化机会

### Step 5: 风险评估

- 高风险因素
- 中风险因素
- 进入建议

---

## 技术实现

```python
class ProductResearch:
    def analyze(self, keyword: str, price: float = None, cost: float = None) -> Dict:
        """
        选品调研完整流程
        """
        # 1. 快速扫描
        scan = self.quick_scan(keyword)
        
        # 2. 市场分析
        market = self.analyze_market(scan['node_id'])
        
        # 3. 利润测算
        profit = self.calculate_profit(price, cost)
        
        # 4. 竞品发现
        competitors = self.discover_competitors(keyword)
        
        # 5. 风险评估
        risks = self.assess_risks(scan, market)
        
        return {
            'decision': scan['recommendation'],
            'score': scan['score'],
            'market': market,
            'profit': profit,
            'competitors': competitors,
            'risks': risks
        }
```

---

## 依赖

- `unified_data_layer_v2.py` - 统一数据层
- `sellersprite_mcp.py` - MCP客户端
- SellerSprite API access

---

## 版本

V1 - 2026-04-13
- 第一版发布
- 场景: 选品调研
