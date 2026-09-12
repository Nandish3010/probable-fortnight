# Pilot

DECISIONS §3.2 "Real pilot" and §17.3. This is a small, real, consented test of the measurement
loop end-to-end on real humans -- it is not the source of the economic headline (that comes from
the seeded tenant's counterfactual card, labelled as such everywhere it appears).

## Pre-registered metric

**Response rate on the target lot**: the fraction of treated participants who order the target
SKU from the target lot inside the play window, versus the same fraction among holdout
participants. Pre-registered before any pilot data is collected, in this file, and not changed
after the fact. No secondary metric (revenue, margin, waste avoided) is claimed as a pilot
finding -- those numbers are reported from the seeded tenant, labelled "estimated" or "seeded
tenant", never blended with the pilot's real numbers on the same chart without a label
distinguishing the two.

## Participants

**50-60 consented testers**, recruited as Kutumb Mart customers on the web chat, for **one week**.
**40-50% holdout** (higher than the platform default 10% minimum, deliberately, because a small
`n` needs a larger holdout fraction to keep both arms informative -- see `agents/gate` for the
default; the pilot's own holdout fraction is set per-play at approval time, within the schema's
`holdout.fraction >= 0.05` floor).

## Recruitment method

Direct outreach to people already known to the team (colleagues, friends, and their households)
who are willing to act as "Kutumb Mart customers" for a week: sent a link to the web chat, asked
to use it as they would a real grocery chat, told plainly this is a pilot and why. No cold
recruitment, no paid panel, no scraped contact list -- recruitment is 1:1 and consent is collected
before any message is sent to a participant.

## Consent text (English)

> You're being invited to try Taal's grocery chat as part of a one-week pilot for a hackathon
> project. If you opt in, you may receive one or more messages from a chat assistant about items
> near their sell-by date, possibly with a discount or bundle offer. Some participants (chosen at
> random) will not receive any offer during the pilot, so we can measure whether the messages
> make a difference -- you may be one of them, and that's expected, not an error. We will record
> your chat messages and any order you place through the chat for this study only, and delete
> your data after the pilot period unless you ask us to keep it for a specific reason. You can
> reply STOP at any time to leave the pilot immediately and receive no further messages. This is
> a small, informal pilot, not a commercial promotion -- prices and offers may not reflect a real
> retailer's pricing.

## The real-order mechanism

Two options, named because the demo tenant has no real warehouse:

1. **A friend's shop's real near-expiry stock** -- if a cooperating small shop has genuine
   near-sell-by stock, the pilot's target SKU and lot are that shop's real inventory, and an
   order placed through the chat becomes a real pickup/delivery arranged with that shop.
2. **A micro-lot bought and resold at cost** -- the team buys a small real lot of a near-expiry
   product itself and resells it at cost (no margin taken) through the pilot chat, so an order is
   a real transaction with a real product changing hands, without needing a partner retailer.

Whichever option is used for a given pilot run is stated plainly in the demo video and README --
it is never left ambiguous which one produced a given order.

## What is and is not claimed

- **Claimed**: the measurement loop (holdout assignment, order attribution, lift and CI
  computation, priors update) runs end-to-end on real participants and real orders, for this one
  metric, at this small scale.
- **Not claimed**: that the pilot's response rate, lift, or CI generalises to a different
  product, tenant, or population; that the rupee figures shown elsewhere in the product (the
  counterfactual card, the cost-per-play estimate) are validated by the pilot; that 50-60
  participants over one week is a statistically well-powered test of anything beyond "the loop
  runs and produces a number with a CI attached."
- **Labelled real everywhere**: the same rupee or rate figure that comes from the pilot is shown
  with the same label ("real pilot data, computed <date>") on every surface it appears --
  Outcomes screen, Looker Studio, README, deck -- per DECISIONS §3.2.

## Analysis plan

The analysis plan is `jobs/measure/run.py`, unmodified for the pilot: responders, units, revenue,
margin, discount, lift with a normal-approximation 95% CI, `status = unmeasured` if treated count
is below `min_treated_n` or the holdout arm is empty (in which case no lift or CI is written),
and the Beta-Binomial prior update. Nothing pilot-specific is added to the analysis code; the
same code path measures the pilot and the seeded tenant, which is itself part of the claim being
made (the loop is real, not a demo-only shortcut).
