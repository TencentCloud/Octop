# RFM Segmenter — Quality Checklist

Use before deploying any RFM-driven campaign. All sections must be checked.

---

## 1. Data Quality (8 items)
- [ ] Order data exported from ecommerce backend (Shopify/WooCommerce/BigCommerce), not marketing platform
- [ ] Refunds and returns subtracted — using net revenue, not gross
- [ ] Test orders excluded (internal team purchases, dummy orders)
- [ ] Wholesale / B2B accounts excluded or flagged separately
- [ ] Analysis window clearly defined (start date and end date)
- [ ] Duplicate customer records merged (same customer, multiple emails/accounts)
- [ ] Cancelled orders excluded from frequency and monetary totals
- [ ] Order dates verified — no future dates, no clearly erroneous dates (e.g., year 1900)

## 2. Scoring Accuracy (7 items)
- [ ] Scoring method (quintile/quartile/tertile) matches customer base size
- [ ] Recency scored correctly: lower days = higher score
- [ ] Frequency scored correctly: more orders = higher score
- [ ] Monetary scored correctly: higher net spend = higher score
- [ ] Tied values handled (not leaving gaps in quintile buckets)
- [ ] Single-purchase customers (F1) correctly identified and not forced into multiple frequency buckets
- [ ] Segment boundaries documented and reproducible

## 3. Segment Assignment (5 items)
- [ ] All customers assigned to exactly one segment (no gaps or duplicates)
- [ ] Segment mapping rules documented and reviewed
- [ ] Champions segment represents recognizable top customers (spot-check 10 names)
- [ ] Lost/Hibernating segments represent recognizable lapsed customers (spot-check)
- [ ] Segment sizes pass the reasonableness check (Champions 5–15%, Lost <20%)

## 4. Campaign Readiness (8 items)
- [ ] Each segment has a defined campaign strategy (message angle, offer, channel)
- [ ] At Risk and Can't Lose Them campaigns are prioritized (highest ROI recovery)
- [ ] Champions campaign uses no discount (or minimal incentive only)
- [ ] Email audiences built in ESP (Klaviyo, Mailchimp) for each active segment
- [ ] Suppression list applied (Lost segment excluded from active sends)
- [ ] SMS list built for At Risk and Can't Lose Them segments (if applicable)
- [ ] Retargeting audiences uploaded to Meta/Google Ads for key segments
- [ ] A/B test designed for at least one segment campaign (message or offer variant)

## 5. Tracking & Reporting (6 items)
- [ ] Campaign UTM parameters set up per segment (utm_content=rfm-champions, etc.)
- [ ] Baseline conversion metrics documented before campaigns launch
- [ ] Revenue attribution plan defined (how will you measure each segment's campaign contribution?)
- [ ] Next RFM refresh date scheduled (30/60/90 days)
- [ ] Segment migration tracking set up (can you see who moved between segments?)
- [ ] KPIs defined per segment (e.g., At Risk: reactivation rate; New Customers: 90-day repeat rate)

## 6. Final Review (4 items)
- [ ] RFM output reviewed by someone who knows the customer base (does it "feel" right?)
- [ ] Top 20 Champions verified to be recognizable high-value customers
- [ ] Top 20 Can't Lose Them verified to be recognizable formerly-valuable lapsed customers
- [ ] Report shared with marketing team with clear action items and owners

---

**Total items: 38**
**Minimum before sending any campaign: Sections 1–3 fully complete + Section 4 complete for that specific segment**
