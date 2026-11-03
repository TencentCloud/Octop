# RFM Scoring Methodology Guide

## Quintile vs. Quartile vs. Tertile — Which to Use

| Customer Base Size | Recommended Scoring | Segments Per Dimension |
|-------------------|--------------------|-----------------------|
| 50–200 customers | Tertile (1–3) | 3 |
| 200–500 customers | Quartile (1–4) | 4 |
| 500+ customers | Quintile (1–5) | 5 |
| 5,000+ customers | Quintile (1–5) or custom decile | 5–10 |

**Why it matters:** With 150 customers and quintile scoring, each bucket has ~30 people. That's workable. With 80 customers, each bucket has 16 — too small to run meaningful segment campaigns. Use tertile scoring for small lists.

---

## Step-by-Step Quintile Calculation

### 1. Recency Scoring (R)

Sort all customers ascending by days since last order (fewest days = best recency):

```
Total customers: 1,000
Quintile boundaries (20% each = 200 customers per bucket):

R5 (best): Days 0–18     → 200 customers
R4:         Days 19–35   → 200 customers
R3:         Days 36–58   → 200 customers
R2:         Days 59–105  → 200 customers
R1 (worst): Days 106+    → 200 customers
```

*Note: The exact day boundaries depend on your specific customer distribution. Calculate them from your actual data — don't use fixed cutoffs like "0–30 days = R5" because your purchase cycle may differ.*

### 2. Frequency Scoring (F)

Sort all customers descending by number of orders:

```
F5 (best): 8+ orders     → 200 customers (top 20%)
F4:         5–7 orders   → 200 customers
F3:         3–4 orders   → 200 customers
F2:         2 orders     → 200 customers
F1 (worst): 1 order      → 200 customers
```

*Edge case: If a large percentage of customers have exactly 1 order (common for new stores), expand F1 to include all single-purchase customers and score remaining customers across F2–F5.*

### 3. Monetary Scoring (M)

Sort all customers descending by net revenue:

```
M5 (best): $800+         → 200 customers (top 20%)
M4:         $400–799     → 200 customers
M3:         $200–399     → 200 customers
M2:         $100–199     → 200 customers
M1 (worst): <$100        → 200 customers
```

---

## Handling Edge Cases

### Tied Values
When many customers share the same value (e.g., 400 customers have exactly 1 order), you have two options:
1. **Assign all tied values to the same score bucket** — Acceptable if the tied group is <30% of your total.
2. **Random assignment within the tied group** — Distribute ties across adjacent buckets randomly to maintain even distribution.

### Customers With a Single Order
In most ecommerce stores, 40–60% of customers have exactly 1 order. Don't over-segment this group:
- All single-purchase customers get F1 by default
- Use R and M scores to differentiate within this group
- A customer with R5, F1, M5 is a "High-Value New Customer," distinct from R5, F1, M1 (just a new customer with small first order)

### New Store With <12 Months of Data
- Don't force a 12-month window. Use all available data.
- Your "Lost" segment will be empty or tiny — that's fine.
- Focus scoring on R and F (M is less meaningful with a short history).
- Re-run the full model at 12 months when you have enough data for meaningful segmentation.

### Seasonal Businesses
For businesses with strong seasonality (holiday gifts, summer toys, etc.):
- Run RFM analysis within each season rather than across the full year.
- A customer who bought every December for 5 years is a Champion, not a Hibernating customer — but a full-year rolling window would score them as R1.
- Add a "seasonal flag" to your customer record to adjust recency scoring.

---

## Python Code for RFM Scoring (Basic Implementation)

```python
import pandas as pd
from datetime import datetime

# Load order data
df = pd.read_csv('orders.csv')  # columns: customer_id, order_date, order_value_net
df['order_date'] = pd.to_datetime(df['order_date'])

# Set snapshot date
snapshot_date = datetime(2026, 6, 6)

# Calculate R, F, M raw values
rfm = df.groupby('customer_id').agg({
    'order_date': lambda x: (snapshot_date - x.max()).days,  # Recency
    'customer_id': 'count',                                   # Frequency
    'order_value_net': 'sum'                                  # Monetary
}).rename(columns={
    'order_date': 'recency',
    'customer_id': 'frequency',
    'order_value_net': 'monetary'
})

# Score each dimension (1-5, higher = better)
rfm['R_score'] = pd.qcut(rfm['recency'], q=5, labels=[5,4,3,2,1]).astype(int)
rfm['F_score'] = pd.qcut(rfm['frequency'].rank(method='first'), q=5, labels=[1,2,3,4,5]).astype(int)
rfm['M_score'] = pd.qcut(rfm['monetary'].rank(method='first'), q=5, labels=[1,2,3,4,5]).astype(int)

# Create RFM composite score
rfm['RFM_score'] = rfm['R_score'].astype(str) + rfm['F_score'].astype(str) + rfm['M_score'].astype(str)

# Assign segment names
def assign_segment(row):
    r, f, m = row['R_score'], row['F_score'], row['M_score']
    if r >= 4 and f >= 4 and m >= 4:
        return 'Champions'
    elif r >= 3 and f >= 3 and m >= 3:
        return 'Loyal Customers'
    elif r >= 4 and f <= 1:
        return 'New Customers'
    elif r >= 4 and f <= 3 and m <= 3:
        return 'Potential Loyalists'
    elif r <= 2 and f >= 3 and m >= 3:
        if r == 1:
            return "Can't Lose Them"
        return 'At Risk'
    elif r <= 2 and f <= 2 and m <= 2:
        return 'Hibernating'
    elif r >= 2 and f >= 2 and m >= 2:
        return 'Needs Attention'
    else:
        return 'About to Sleep'

rfm['segment'] = rfm.apply(assign_segment, axis=1)

print(rfm['segment'].value_counts())
```

---

## Validating Your Model

Before acting on RFM results, run these sanity checks:

1. **Revenue concentration**: Champions + Loyal Customers should represent 60–80% of total revenue despite being 20–35% of customers. If not, your scoring window or boundaries may be off.

2. **Recency distribution**: If >50% of customers are in R1, your window is too long or your reorder cycle is shorter than you think.

3. **Monetary spread**: The M5 bucket should have substantially higher average spend than M1 (ideally 5–20x higher). If the spread is narrow, consider using a log scale for monetary scoring.

4. **Segment stability**: Run the model on last quarter's data and compare to this quarter. Large sudden swings in segment sizes indicate data quality issues (missing orders, date errors, etc.).
