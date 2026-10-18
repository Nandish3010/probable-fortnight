# Real-data replay: summary (19 Oct 2026)

Aggregates only, from a pet-care e-commerce company's past data (anonymised). Labels: MEASURED (counted from the data), INFERRED (expiry pull-outs inferred from stock leaving sellable inventory at the cut-off with no recorded sale or exit), ESTIMATED (needs an assumption). Source data and code stay in the private folder and are never copied to the repo.

## Scope
3 months of online data (21 Jul to 19 Oct 2026; about 11 weekly stock snapshots), food and consumables with an expiry date (about 3,000 SKUs, 60 locations). Replay of past data, not a live pilot. Expiry disposal happens outside the stock system, so expiry loss is inferred. Cut-off rule from the data owner: stock leaves sellable inventory when its remaining life falls below the SKU's dispatch tolerance. Customer-targeted offers were not modelled (no customer data).

## Figures
1. INFERRED, scale: about ₹44.5 L of stock (about 8,300 units, at cost) was pulled from sale at the expiry cut-off in about 11 weeks, after subtracting the normal background vanishing rate (about 3% of units a week on lots far from expiry vs about 81% in the week before the cut-off).
2. MEASURED, early warning: replaying each weekly snapshot with only the data available that day, Taal-style flags caught 99% of the lots later pulled for expiry, 87% at least a week ahead; median lead time 30 days before the cut-off.
3. MEASURED, timing vs practice: a median 21 days before the existing markdown trigger (cut-off plus 15 days). MUST be paired with: "a simple 60-days-of-stock rule fires at about the same time, so Taal's added value is in sizing the shortfall and choosing the action, not in timing alone."
4. MEASURED, precision: of flagged lots whose cut-off fell inside the data window, 45% were later pulled; the rest sold through or were moved.
5. ESTIMATED, value: on those lots, the best of an in-city transfer, a markdown or doing nothing would have recovered about ₹8 L at cost after calibration (uncalibrated model ₹15 L; transfers supply most of it), against about ₹3.7 L for a blanket 20% markdown at the trigger: roughly twice the blanket markdown, mostly through transfers.

6. ESTIMATED, value as a range (preferred form of line 5): "would have recovered an estimated ₹8 to 15 L at cost in about 11 weeks (calibrated to uncalibrated), about twice a blanket 20% markdown (about ₹3.7 L)".
7. ANNUALISED (label "INFERRED, annualised" / "ESTIMATED, annualised"; always state the 11-week base and that it assumes the same rate all year, which ignores seasonality):
   - Scale: about ₹44.5 L in about 11 weeks, roughly ₹2.1 crore a year (INFERRED, annualised; online food and consumables only).
   - Value: ₹8 to 15 L in about 11 weeks, roughly ₹35 to 70 L a year (ESTIMATED, annualised), against about ₹17 L a year for a blanket 20% markdown.
   Arithmetic: x 52/11 (44.5 -> 210; 7.8 -> 37; 15.2 -> 72; 3.7 -> 17), rounded down.

## Limits
- Expiry loss is inferred from stock leaving sellable inventory; it cannot separate destruction, returns booked elsewhere or miscounts.
- Recall is flattered: the flag and the label both come from the same sales signal (a lot that reaches its cut-off with stock was slow by definition).
- 11 weeks of data; only about 1,950 flagged lots reached their cut-off inside the window, so value and precision rest on them.
- Values are modelled: price response measured from the company's own promo days (x1.20 at about 9% off, including sitewide sale days), extrapolated to deeper discounts; transfers at ₹40 a unit within a city; margin on rescued stock ignored.

## Headline
"On 3 months of real data from a pet-care e-commerce company, about ₹44.5 L of stock was pulled at the expiry cut-off in 11 weeks, roughly ₹2 crore a year (INFERRED, annualised). Replaying each week, Taal would have flagged 99% of it a median 30 days before the cut-off (MEASURED), and its transfer-or-markdown choice would have recovered an estimated ₹8 to 15 L in those 11 weeks, about twice a blanket markdown (ESTIMATED)."

Short form: "Real data, 11 weeks: about ₹44.5 L pulled at expiry (INFERRED); Taal would have flagged 99% of it a month ahead (45% precision); estimated recovery ₹8 to 15 L, about twice a blanket markdown (ESTIMATED)."
