# Replay on real data

Aggregates from a private replay; the source data and code are not in this repo. The company is not named: it is a pet-care e-commerce company, and the owner has given written permission to publish these figures anonymised.

## Scope

3 months of online data (21 Jul to 19 Oct 2026; about 11 weekly stock snapshots), food and consumables with an expiry date (about 3,000 SKUs, 60 locations). This is a replay of past data, not a live pilot. Expiry disposal happens outside the stock system, so expiry loss is inferred. Cut-off rule from the data owner: stock leaves sellable inventory when its remaining life falls below the SKU's dispatch tolerance. Customer-targeted offers were not modelled (no customer data).

## Labels

- **MEASURED**: counted from the data.
- **INFERRED**: expiry pull-outs inferred from stock leaving sellable inventory at the cut-off with no recorded sale or exit.
- **ESTIMATED**: needs an assumption.
- **annualised**: the 11-week figure x 52/11, assuming the same rate all year, which ignores seasonality.

## Figures

1. **INFERRED, scale.** About ₹44.5 L of stock (about 8,300 units, at cost) was pulled from sale at the expiry cut-off in about 11 weeks, after subtracting the normal background vanishing rate (about 3% of units a week on lots far from expiry vs about 81% in the week before the cut-off).
2. **MEASURED, early warning.** Replaying each weekly snapshot with only the data available that day, Taal-style flags would have caught 99% of the lots later pulled for expiry, 87% at least a week ahead; median lead time 30 days before the cut-off.
3. **MEASURED, timing vs practice.** A median 21 days before the existing markdown trigger (cut-off plus 15 days). A simple 60-days-of-stock rule fires at about the same time, so Taal's added value is in sizing the shortfall and choosing the action, not in timing alone.
4. **MEASURED, precision.** Of flagged lots whose cut-off fell inside the data window, 45% were later pulled; the rest sold through or were moved. Read the 99% in line 2 together with this 45% and the caveat in line 3.
5. **ESTIMATED, value.** On those lots, the best of an in-city transfer, a markdown or doing nothing would have recovered an estimated ₹8 to 15 L at cost in about 11 weeks (calibrated to uncalibrated; transfers supply most of it), about twice a blanket 20% markdown (about ₹3.7 L).
6. **INFERRED, annualised (scale).** About ₹44.5 L in about 11 weeks, roughly ₹2.1 crore a year (online food and consumables only). Assumes the same rate all year, which ignores seasonality.
7. **ESTIMATED, annualised (value).** ₹8 to 15 L in about 11 weeks, roughly ₹35 to 70 L a year, against about ₹17 L a year for a blanket 20% markdown. Same 11-week base and the same-rate-all-year assumption, which ignores seasonality. Arithmetic: x 52/11, rounded down.

Headline: "On 3 months of real data from a pet-care e-commerce company, about ₹44.5 L of stock was pulled at the expiry cut-off in 11 weeks, roughly ₹2 crore a year (INFERRED, annualised). Replaying each week, Taal would have flagged 99% of it a median 30 days before the cut-off (MEASURED), and its transfer-or-markdown choice would have recovered an estimated ₹8 to 15 L in those 11 weeks, about twice a blanket markdown (ESTIMATED)."

## Limits

- Expiry loss is inferred from stock leaving sellable inventory; it cannot separate destruction, returns booked elsewhere or miscounts.
- Recall is flattered: the flag and the label both come from the same sales signal (a lot that reaches its cut-off with stock was slow by definition).
- 11 weeks of data; only about 1,950 flagged lots reached their cut-off inside the window, so value and precision rest on them.
- Values are modelled: price response measured from the company's own promo days (x1.20 at about 9% off, including sitewide sale days), extrapolated to deeper discounts; transfers at ₹40 a unit within a city; margin on rescued stock ignored.
