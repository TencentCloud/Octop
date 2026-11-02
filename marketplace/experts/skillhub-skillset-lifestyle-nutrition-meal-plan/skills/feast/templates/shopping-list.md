---
# Feast Shopping List
# YAML frontmatter for machine-readable data

version: 1
weekOf: "YYYY-MM-DD"
generatedAt: null
status: draft                     # draft, approved, purchased

totals:
  estimatedCost: null
  actualCost: null
  itemCount: 0
  potentialSavings: null          # Savings from following price recommendations

# Price checking metadata
priceCheck:
  performed: false                # Was price checking done?
  checkedOn: null                 # Date prices were researched
  storesChecked: []               # Which stores were compared
  
  strategy: null                  # Recommended shopping approach
  # Options: "single-store", "split", "deal-driven"
  
  primaryStore: null              # Main recommended store
  secondaryStore: null            # Secondary store if split strategy
  
  keyDeals:                       # Highlighted deals worth grabbing
    - item: ""
      store: ""
      deal: ""                    # e.g., "2 for £5", "Half price"
      normalPrice: null
      dealPrice: null
      savings: null
  
  disclaimer: "Prices checked on [date]. Verify in-store — prices and availability may vary."

items:
  - name: ""
    amount: ""
    unit: ""
    category: proteins            # proteins, vegetables, fruit, dairy, carbs, tins, herbs, spices, oils, frozen, bakery, other
    usedIn: []                    # Which recipes use this ingredient
    seasonal: false
    checked: false
    
    # Price checking for this item (for expensive/flagged items)
    priceCheck:
      flagged: false              # Was this item price-checked?
      cheapestStore: ""
      cheapestPrice: null
      alternativeStore: ""
      alternativePrice: null
      deal: ""                    # Current offer if any
      dealType: ""                # "multi-buy", "loyalty", "temporary", "regular"
      notes: ""                   # e.g., "Clubcard price", "May sell out"
      qualityNote: ""             # If cheapest isn't best quality
  # Add more items...
---

# Shopping List: Week of [DATE]

**Status:** 🟡 Draft / 🟢 Approved / ✅ Purchased

---

## 💰 Price Guidance

**Prices checked:** [Date]  
**Strategy:** [Single store at X / Split: proteins at X, rest at Y]  
**Estimated total:** £XX  
**Potential savings:** £X.XX (if following recommendations)

### ⭐ Key Deals This Week

- **[Item]** — [Deal] at [Store] (save £X.XX)
- **[Item]** — [Deal] at [Store]

### 🏪 Store Recommendation

[Brief explanation of the recommended shopping approach — why this store or this split makes sense for this week's shop.]

> ⚠️ *Prices checked [date]. Verify in-store — prices and availability may vary.*

---

## 🥩 Proteins

- [ ] Item — quantity — **~£X.XX**  
  💰 *Best: [Store] (£X.XX) | Alt: [Store] (£X.XX)*
  
- [ ] Item — quantity — **~£X.XX**  
  ⭐ *Deal: [Offer] at [Store]*

## 🥬 Vegetables

- [ ] Item — quantity
- [ ] Item — quantity  
  🌱 *In season*

## 🍎 Fruit

- [ ] Item — quantity

## 🥛 Dairy

- [ ] Item — quantity — **~£X.XX**  
  💰 *[Price note if applicable]*

## 🍚 Carbs & Grains

- [ ] Item — quantity
- [ ] Item — quantity

## 🥫 Tins & Jars

- [ ] Item — quantity
- [ ] Item — quantity

## 🌿 Fresh Herbs

- [ ] Item — quantity

## 🧂 Spices & Seasonings

- [ ] Item — quantity *(if needed)*

## 🫒 Oils & Condiments

- [ ] Item — quantity *(if needed)*

## 🧊 Frozen

- [ ] Item — quantity

## 🥖 Bakery

- [ ] Item — quantity

## 📦 Other

- [ ] Item — quantity

---

## Storecupboard Check

*Items you should have — tick to confirm:*

- [ ] Olive oil
- [ ] Salt & pepper
- [ ] [Other staples needed this week]

---

## 📝 Notes

- Any special instructions
- Alternative stores for specific items
- Seasonal notes
- Quality recommendations (when cheapest isn't best)

---

## Legend

- 💰 = Notable saving available at a different store
- ⭐ = Deal/offer worth grabbing
- 🌱 = In season (better quality, often cheaper)
- ⚠️ = Stock warning (Lidl/Aldi offers may sell out)
