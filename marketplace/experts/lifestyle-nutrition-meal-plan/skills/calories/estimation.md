# Calorie Estimation Framework

Reference only — how to estimate calories from photos and descriptions.

## Estimation Accuracy (Be Honest)
- Single foods: ±10-15% error
- Complex meals: ±25-40% error
- Restaurant: assume +20-30% vs homemade
- AI estimation ≈ dietitian accuracy, better than self-reporting

## Photo Analysis Strategy
1. **Identify foods** in image
2. **Estimate portions** using plate/utensils as reference
3. **Map to nutrition database** (USDA or similar)
4. **Adjust for hidden calories** (oil, butter, sauces)

**Hidden calorie adjustments:**
- Unknown cooking method: +50-100 cal
- Fried food: +15-20%
- Sauces/dressings (not on side): +50-100 cal
- Restaurant vs homemade: +20-30%

## Text Description Strategy
1. Parse food items and quantities
2. Use reasonable defaults if vague (medium portion, typical prep)
3. ONE clarifying question max if needed
4. Give range, not exact number

**Defaults when unspecified:**
- Pizza slice: 250-350 cal (assume medium, standard toppings)
- Pasta portion: 1.5 cups (not restaurant-sized)
- Salad: 150 cal base + dressing estimate

## Personal Library (Learn Over Time)
**Save to library:**
- Packaged foods: scan label once, reuse forever
- Homemade recipes: estimate once, save as template
- Restaurant favorites: estimate once, store as "Dish @ Place"

**Reuse strategy:**
- Exact match (barcode/name): auto-suggest, 1-tap confirm
- Similar match: "Same as last time? (adjust if different)"
- Build library silently, surface when helpful

## Home vs Restaurant
| Context | Strategy |
|---------|----------|
| Home/packaged | Ask for label photo → extract, store |
| Home/cooked | Estimate ingredients, save recipe |
| Restaurant/chain | Look up menu data if available |
| Restaurant/local | Photo estimate, flag as approximate |

## Conservative Direction (Goal-Based)
| User Goal | Adjustment |
|-----------|------------|
| Weight loss | Round UP 10-15% |
| Muscle gain | Round DOWN 10-15% |
| Maintenance | Use midpoint |

## Communicating Uncertainty
- Use ranges: "350-450 cal" not "400 cal"
- Explain briefly: "Restaurant portions vary, estimated higher side"
- Normalize: "±15% margin is typical"
- Focus on weekly trends, not daily precision

## Cost Efficiency (Minimize Image Analysis)
1. **Text first:** Ask user to describe, request photo only if unclear
2. **Cache everything:** Reuse previous estimates for repeat meals
3. **Batch analysis:** Full meal in one photo, not item by item
4. **Label priority:** One label photo = permanent accurate data

## When to Ask for Photo
- Complex mixed dishes (stew, casserole)
- Restaurant meals (unknown portions)
- User seems uncertain in description
- First time seeing a dish
