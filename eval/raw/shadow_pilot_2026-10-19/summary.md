# Real-data replay: reviewed public-safe summary (field-analysis, 19 Oct 2026)

ONLY source for README/deck/video numbers about the real-data replay. Aggregates only. Never name the company: "a pet-care e-commerce company". Labels: MEASURED (counted from the data), INFERRED (expiry pull-outs inferred from stock leaving sellable inventory at the cut-off with no recorded sale or exit), ESTIMATED (needs an assumption). Source data and code stay in the private folder and are never copied to the repo.

## Scope (state wherever the numbers appear)
3 months of online data (21 Jul to 19 Oct 2026; about 11 weekly stock snapshots), food and consumables with an expiry date (about 3,000 SKUs, 60 locations). Replay of past data, not a live pilot. Expiry disposal happens outside the stock system, so expiry loss is inferred. Cut-off rule from the data owner: stock leaves sellable inventory when its remaining life falls below the SKU's dispatch tolerance. Customer-targeted offers were not modelled (no customer data).

## Approved lines (use these numbers, this wording or shorter)
1. INFERRED, scale: about Rs 44.5 L of stock (about 8,300 units, at cost) was pulled from sale at the expiry cut-off in about 11 weeks, after subtracting the normal background vanishing rate (about 3% of units a week on lots far from expiry vs about 81% in the week before the cut-off).
2. MEASURED, early warning: replaying each weekly snapshot with only the data available that day, Taal-style flags caught 99% of the lots later pulled for expiry, 87% at least a week ahead; median lead time 30 days before the cut-off.
3. MEASURED, timing vs practice: a median 21 days before the existing markdown trigger (cut-off plus 15 days). MUST be paired with: "a simple 60-days-of-stock rule fires at about the same time, so Taal's added value is in sizing the shortfall and choosing the action, not in timing alone."
4. MEASURED, precision: of flagged lots whose cut-off fell inside the data window, 45% were later pulled; the rest sold through or were moved.
5. ESTIMATED, value: on those lots, the best of an in-city transfer, a markdown or doing nothing would have recovered about Rs 8 L at cost after calibration (uncalibrated model Rs 15 L; transfers supply most of it), against about Rs 3.7 L for a blanket 20% markdown at the trigger: roughly twice the blanket markdown, mostly through transfers.

6. ESTIMATED, value as a range (preferred form of line 5): "would have recovered an estimated Rs 8 to 15 L at cost in about 11 weeks (calibrated to uncalibrated), about twice a blanket 20% markdown (about Rs 3.7 L)". Never quote a single figure above Rs 15 L; never drop the word "estimated".
7. ANNUALISED (label "INFERRED, annualised" / "ESTIMATED, annualised"; always state the 11-week base and that it assumes the same rate all year, which ignores seasonality):
   - Scale: about Rs 44.5 L in about 11 weeks, roughly Rs 2.1 crore a year (INFERRED, annualised; online food and consumables only).
   - Value: Rs 8 to 15 L in about 11 weeks, roughly Rs 35 to 70 L a year (ESTIMATED, annualised), against about Rs 17 L a year for a blanket 20% markdown.
   Arithmetic: x 52/11 (44.5 -> 210; 7.8 -> 37; 15.2 -> 72; 3.7 -> 17), rounded down.

## Wording rules
- Allowed: "would have flagged", "estimated", "inferred", "replay on real data".
- Not allowed: "saved", "recovered" (without "would have" / "estimated"), "piloted", "deployed at", "predicts expiry with 99% accuracy", any claim that Taal beats the company's existing rules on timing.
- Recall must not be shown without precision (line 4) and without the stock-cover caveat (line 3).
- Never present the ERP write-off total as expiry loss.

## Limits (one line each, in the README section and the deck footnote)
- Expiry loss is inferred from stock leaving sellable inventory; it cannot separate destruction, returns booked elsewhere or miscounts.
- Recall is flattered: the flag and the label both come from the same sales signal (a lot that reaches its cut-off with stock was slow by definition).
- 11 weeks of data; only about 1,950 flagged lots reached their cut-off inside the window, so value and precision rest on them.
- Values are modelled: price response measured from the company's own promo days (x1.20 at about 9% off, including sitewide sale days), extrapolated to deeper discounts; transfers at Rs 40 a unit within a city; margin on rescued stock ignored.

## Suggested headline (README first lines / deck slide)
"On 3 months of real data from a pet-care e-commerce company, about Rs 44.5 L of stock was pulled at the expiry cut-off in 11 weeks, roughly Rs 2 crore a year (INFERRED, annualised). Replaying each week, Taal would have flagged 99% of it a median 30 days before the cut-off (MEASURED), and its transfer-or-markdown choice would have recovered an estimated Rs 8 to 15 L in those 11 weeks, about twice a blanket markdown (ESTIMATED)."

Short form (deck slide 1, video): "Real data, 11 weeks: about Rs 44.5 L pulled at expiry (INFERRED); Taal flagged 99% of it a month ahead; estimated recovery Rs 8 to 15 L, twice a blanket markdown."
