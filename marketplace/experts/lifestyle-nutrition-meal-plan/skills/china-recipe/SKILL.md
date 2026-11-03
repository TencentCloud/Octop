---
name: china-recipe
description: 中国菜谱大全。Use when user wants to find Chinese recipes, cooking instructions, ingredient lists, or meal planning. Supports regional cuisines, dietary preferences, and step-by-step cooking guides. 菜谱、烹饪、美食、食谱。
version: 1.0.2
license: MIT-0
metadata: {"openclaw": {"emoji": "🍳", "requires": {"bins": ["python3"], "env": []}}}
---

# China Recipe

中国菜谱大全，支持各大菜系、食材查询、详细做法、营养信息。

## Features

- 🍜 **菜系丰富**: 川菜、粤菜、鲁菜、苏菜、浙菜、闽菜、湘菜、徽菜
- 🥘 **分类齐全**: 荤菜、素菜、汤品、主食、甜点、凉菜
- 📋 **详细做法**: 食材清单、步骤详解、烹饪技巧
- 🔍 **智能搜索**: 按食材、菜名、口味搜索
- 🥗 **营养信息**: 热量、蛋白质、脂肪、碳水
- 🌍 **多语言**: 中英文支持

## Trigger Conditions

- "做什么菜" / "What to cook"
- "给我一个菜谱" / "Give me a recipe"
- "红烧肉怎么做" / "How to make braised pork"
- "今天吃什么" / "What to eat today"
- "有什么简单的菜" / "Easy recipes"
- "china-recipe"

---

## How It Works (工作原理)

### 数据来源

**本skill不维护菜谱数据库**，而是利用LLM的烹饪知识动态生成菜谱：

1. 用户请求菜谱（如"红烧肉怎么做"）
2. Agent根据LLM知识生成详细菜谱
3. 输出标准化格式的菜谱报告

### 优势

- ✅ **无限扩展** - LLM知道几乎所有菜谱
- ✅ **实时生成** - 根据需求动态生成
- ✅ **无需维护** - 无需维护数据库
- ✅ **个性化** - 可根据口味、人数调整

---

## Step 1: 识别用户需求

```
用户输入 → 分析需求：

"红烧肉怎么做"
  → 检测：查询具体菜谱
  → 生成：红烧肉详细做法

"有什么简单的菜"
  → 检测：推荐简单菜
  → 生成：3-5道简单菜谱

"川菜推荐"
  → 检测：推荐菜系
  → 生成：川菜代表菜

"今天吃什么"
  → 检测：随机推荐
  → 生成：2-3道随机菜谱

"用鸡胸肉做什么菜"
  → 检测：按食材推荐
  → 生成：鸡胸肉菜谱
```

---

## Step 2: 返回菜谱详情

### 菜谱详情格式

```
┌──────────────────────────────────────────────┐
│  🍳 红烧肉                                     │
│  川菜 | 难度：⭐⭐⭐ | 时间：90分钟 | 4人份  │
└──────────────────────────────────────────────┘

📝 食材清单
├─ 五花肉 500g
├─ 生姜 3片
├─ 大葱 2段
├─ 八角 2个
├─ 桂皮 1小块
├─ 冰糖 30g
├─ 生抽 2勺
├─ 老抽 1勺
└─ 料酒 2勺

👨‍🍳 做法步骤
1. 五花肉切块，冷水下锅焯水
2. 锅中放油，加冰糖炒糖色
3. 放入肉块翻炒上色
4. 加入调料和热水，大火烧开
5. 转小火炖60分钟
6. 大火收汁即可

💡 烹饪技巧
├─ 选肉：肥瘦相间的五花肉最佳
├─ 炒糖色：小火慢炒，防止焦苦
└─ 炖煮：小火慢炖，肉质软烂

🔥 营养信息
├─ 热量：450 kcal/100g
├─ 蛋白质：15g
├─ 脂肪：40g
└─ 碳水：5g
```

---

## Search Logic (搜索逻辑)

```python
RECIPES = {
    "红烧肉": {
        "cuisine": "川菜",
        "difficulty": 3,
        "time": 90,
        "servings": 4,
        "taste": "咸甜",
        "ingredients": [
            "五花肉 500g",
            "生姜 3片",
            "大葱 2段",
            "八角 2个",
            "桂皮 1小块",
            "冰糖 30g",
            "生抽 2勺",
            "老抽 1勺",
            "料酒 2勺"
        ],
        "steps": [
            "五花肉切块，冷水下锅焯水",
            "锅中放油，加冰糖炒糖色",
            "放入肉块翻炒上色",
            "加入调料和热水，大火烧开",
            "转小火炖60分钟",
            "大火收汁即可"
        ],
        "tips": [
            "选肉：肥瘦相间的五花肉最佳",
            "炒糖色：小火慢炒，防止焦苦",
            "炖煮：小火慢炖，肉质软烂"
        ],
        "nutrition": {
            "calories": 450,
            "protein": 15,
            "fat": 40,
            "carbs": 5
        }
    },
    "番茄炒蛋": {
        "cuisine": "家常菜",
        "difficulty": 1,
        "time": 10,
        "servings": 2,
        "taste": "酸甜",
        "ingredients": [
            "番茄 2个",
            "鸡蛋 3个",
            "葱花 适量",
            "盐 适量",
            "糖 1勺",
            "油 适量"
        ],
        "steps": [
            "番茄切块，鸡蛋打散",
            "锅中倒油，炒散鸡蛋盛出",
            "锅中留油，炒番茄出汁",
            "加入盐和糖调味",
            "放入鸡蛋翻炒均匀",
            "撒葱花出锅"
        ],
        "tips": [
            "番茄要选熟透的，出汁多",
            "鸡蛋要炒嫩一点",
            "加糖可以提鲜"
        ],
        "nutrition": {
            "calories": 150,
            "protein": 8,
            "fat": 10,
            "carbs": 8
        }
    }
}

def search_recipe(query):
    """智能搜索菜谱"""
    
    # 按菜名搜索
    for name, recipe in RECIPES.items():
        if query in name or name in query:
            return {name: recipe}
    
    # 按食材搜索
    results = {}
    for name, recipe in RECIPES.items():
        for ingredient in recipe['ingredients']:
            if query in ingredient:
                results[name] = recipe
                break
    
    # 按难度搜索
    if '简单' in query:
        for name, recipe in RECIPES.items():
            if recipe['difficulty'] <= 2:
                results[name] = recipe
    
    # 按菜系搜索
    for name, recipe in RECIPES.items():
        if query in recipe.get('cuisine', ''):
            results[name] = recipe
    
    return results or RECIPES
```

---

## Notes

- 菜谱数据内置，无需外部API
- 支持多种搜索方式
- 支持中英文输出
- 完全本地运行
