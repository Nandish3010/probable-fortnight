"""The Customer Agent tools (DECISIONS §5.5). Contracts: docs/schemas/tools/customer.*.

Holdout customers never see an offer: `get_customer_context` returns no pending offers for them,
`apply_offer` refuses, and proactive delivery (services/api) checks the arm before writing offers.
`negotiate_offer` is the one exception to "every discount comes from an approved, holdout-measured
play": a live, ad-hoc concession for a sku with no play targeting the customer, bounded by its own
(more conservative) guardrails -- see its docstring. `place_order` goes through the MCP order mock
over an in-memory MCP session.
"""
from __future__ import annotations

import json
import re
import statistics
import uuid
from collections import defaultdict
from datetime import date, timedelta
from typing import Any

from mcp.client import Client

from agents.gate.assignment import assign_arm
from agents.mcp_orders.server import server as orders_server

from .context import current


def _resolve_node(ctx, node_id: str | None) -> str:
    """The node to act at: the model's own `node_id`/`home_node_id` argument if it names a node
    that actually exists, else the customer's real home node. get_stock,
    find_substitutes and list_products all name this parameter "home_node_id" in
    agents/customer/prompts/customer.md but the actual schema field is "node_id" with no
    description -- nothing tells the model to reuse the value get_customer_context already gave
    it, so a live call can fabricate a plausible-looking but nonexistent id instead."""
    if node_id and ctx.store.find("nodes", node_id=node_id):
        return node_id
    cust = _customer_profile(ctx, ctx.customer_id)
    return cust["home_node_id"] if cust else "DS-01"


def _customer_profile(ctx, customer_id: str) -> dict[str, Any] | None:
    """Home node, language, display name. From the serving cache when it is safe for this
    visitor (ServingReads: no overlay rows in `customers`, doc as_of/snapshot current), else
    the visitor's own store."""
    if ctx.cache is not None:
        cached = ctx.cache.customer(customer_id)
        if cached is not None:
            return cached
    rows = ctx.store.find("customers", customer_id=customer_id)
    return rows[-1] if rows else None


def _arms(ctx, customer_id: str) -> dict[str, str]:
    arms = {a["play_id"]: a["arm"] for a in ctx.store.read("play_assignments") if a["customer_id"] == customer_id}
    return arms


def _play(ctx, play_id: str) -> dict[str, Any] | None:
    rows = ctx.store.find("plays", play_id=play_id)
    if not rows:
        return None
    r = rows[-1]
    return json.loads(r["play_json"]) if isinstance(r.get("play_json"), str) else r.get("play_json")


def _consent_ok(ctx, customer_id: str) -> bool:
    """Always the visitor's own store, never the serving cache: STOP changes it per visitor."""
    rows = [r for r in ctx.store.read("consent") if r["customer_id"] == customer_id and r["purpose"] == "marketing" and r["channel"] == ctx.channel]
    return bool(rows) and not rows[-1].get("withdrawn_at")


def _record_request(ctx, node_id: str, request_type: str, sku: str | None = None, query_text: str | None = None) -> None:
    """Deterministic instrumentation, not an LLM decision: get_stock and list_products call this
    themselves whenever they turn up nothing, so the demand signal is recorded regardless of what
    the model does or does not decide to say. Read back by Sense (unmet_demand gaps) and by
    _customer_memory (cross-session recall for this customer)."""
    ctx.store.append("customer_requests", [{
        "tenant_id": ctx.tenant.tenant_id, "customer_id": ctx.customer_id, "node_id": node_id,
        "sku": sku, "query_text": query_text, "request_type": request_type,
        "session_id": f"{ctx.customer_id}:{ctx.channel}", "ts": ctx.now_iso,
    }])


def _customer_memory(ctx, customer_id: str, limit: int = 5) -> list[dict[str, Any]]:
    """This customer's own unmet requests across every past session (the store is keyed by
    customer_id, not session_id, so this is real cross-session memory, not a per-conversation
    cache). Grouped by (sku or query_text, request_type, node), most recent first. `now_in_stock`
    is checked at the node the request was actually made at, not assumed to be the home node."""
    rows = [r for r in ctx.store.read("customer_requests") if r["customer_id"] == customer_id]
    grouped: dict[tuple[str, str, str | None], dict[str, Any]] = {}
    for r in sorted(rows, key=lambda r: r["ts"]):
        key = (r["request_type"], r["node_id"], r["sku"] or r["query_text"])
        g = grouped.setdefault(key, {"request_type": r["request_type"], "node_id": r["node_id"], "sku": r["sku"], "query_text": r["query_text"], "times_asked": 0})
        g["times_asked"] += 1
        g["last_asked_at"] = r["ts"]
    out = sorted(grouped.values(), key=lambda g: g["last_asked_at"], reverse=True)[:limit]
    for g in out:
        g["name"] = ctx.products.get(g["sku"], {}).get("name", g["sku"]) if g["sku"] else None
        if g["sku"]:
            g["now_in_stock"] = _stock_info(ctx, g["sku"], g["node_id"]).get("qty", 0) > 0
        g.pop("node_id", None)
    return out


def get_customer_context(customer_id: str) -> dict:
    """Home node, language, pending offers (treated arm only), arms per play and marketing consent."""
    ctx = current()
    c = _customer_profile(ctx, customer_id)
    if not c:
        return {"customer_id": customer_id, "home_node_id": "DS-01", "language": "en", "pending_offers": [], "arms": {}, "consent_marketing": False}
    arms = _arms(ctx, customer_id)
    consent = _consent_ok(ctx, customer_id)
    offers = []
    if consent:
        # Always the visitor's own store: Approve writes offers into their sandbox only.
        raw_offers = [o for o in ctx.store.read("offers") if o["customer_id"] == customer_id and not o.get("redeemed_at")]
        for o in raw_offers:
            play = _play(ctx, o["play_id"])
            if not play or play.get("status") not in ("approved", "running"):
                continue
            if arms.get(o["play_id"]) != "treated" or assign_arm(customer_id, play["holdout"]["seed"], float(play["holdout"]["fraction"])) != "treated":
                continue
            offers.append({"play_id": o["play_id"], "text": o["text"], "best_before_date": o.get("best_before_date"), "sku": o.get("sku"), "mechanic": o.get("mechanic"), "mechanic_params": o.get("mechanic_params", {})})
    return {"customer_id": customer_id, "home_node_id": c["home_node_id"], "language": c.get("language", "en"), "display_name": c.get("display_name"), "pending_offers": offers, "arms": arms, "consent_marketing": consent, "memory": _customer_memory(ctx, customer_id)}


def context_summary(context: dict, turn_language: str | None = None) -> str:
    """A one-line, plain-prose rendering of get_customer_context's result, meant to be folded
    straight into a chat turn's text. Deliberately NOT the raw dict: a model handed a JSON blob
    plus a "never quote this" instruction inline in its own turn text will sometimes quote it
    anyway (observed live -- the whole bracketed block leaked into a real reply); a short sentence
    with no JSON syntax in it removes the thing there is to quote, rather than asking the model
    not to. Sensitive per-play internals (play_id, mechanic_params) are dropped -- the model only
    ever needs the offer's own customer-facing text, not the mechanics behind it.

    `turn_language` (agents.chat_runtime.detect_lang's result for this exact turn) renders as a
    per-turn directive rather than an ambient fact about the customer -- live-observed: a plain
    "writes in Kannada" fact stated every turn outweighs the prompt's own "match the incoming
    message's script" instruction, so a Kannada-preference customer typing English still got a
    Kannada reply. Callers on the deterministic stub path (no live model to steer) can omit it;
    it then falls back to the stored preference alone, same as before."""
    lang = "Kannada" if (turn_language or context.get("language")) == "kn" else "English"
    bits = [f"home store {context['home_node_id']}", f"reply in {lang} for this turn"]
    if context.get("consent_marketing"):
        offers = context.get("pending_offers") or []
        if offers:
            bits.append(f'one pending offer to deliver now, exact wording: "{offers[0]["text"]}"')
        else:
            bits.append("no pending offers right now")
    else:
        bits.append("marketing consent withdrawn -- never mention any offer")
    memory = context.get("memory") or []
    if memory:
        m = memory[0]
        what = m.get("name") or m.get("query_text") or "something"
        status = "back in stock now" if m.get("now_in_stock") else "still not in stock"
        bits.append(f"previously asked about {what} ({status})")
    return "; ".join(bits)


def offer_summary_en(offer: dict[str, Any], names: dict[str, str]) -> str:
    """One English sentence for an offer row (sku, mechanic, mechanic_params, best_before_date),
    from its structured fields alone -- the gloss template for a reply that delivers the offer."""
    params = offer.get("mechanic_params") or {}
    name = names.get(offer.get("sku") or "", offer.get("sku") or "this item")
    mechanic = offer.get("mechanic")
    if mechanic == "bundle":
        what = f"{name} with {names.get(params.get('bundle_sku') or '', 'a partner item')} for ₹{float(params.get('bundle_price') or 0):g}"
    elif mechanic == "coupon":
        what = f"{float(params.get('discount_pct') or 0):g}% off {name}"
    elif mechanic == "outlet_markdown":
        what = f"{float(params.get('markdown_pct') or 0):g}% off {name} in store"
    else:
        what = f"{name} offer"
    bb = offer.get("best_before_date")
    when = f" Best before {date.fromisoformat(bb).strftime('%d %b %Y')}." if bb else ""
    return f"Offer: {what}.{when}"


def _stock_info(ctx, sku: str, node_id: str) -> dict:
    """Pure lookup, no side effects. Shared by get_stock (which records the demand signal on top),
    find_substitutes and _customer_memory, so checking on a customer's behalf internally never
    itself counts as a customer asking. Tries the Firestore serving cache first (a pre-aggregated
    doc, not a per-turn scan of every inventory_batches row) when ServingReads says it is safe for
    this visitor; anything else (no cache, an overlaid inventory_batches/order_lines, a doc from
    another date or snapshot, a miss) falls through to the store scan below."""
    if ctx.cache is not None:
        cached = ctx.cache.stock(sku, node_id)
        if cached is not None:
            return cached
    qty, sellby, expiry, batch = 0, None, None, None
    today = ctx.as_of.isoformat()
    for b in ctx.store.read("inventory_batches"):
        if b["sku"] != sku or b["node_id"] != node_id or int(b["qty_on_hand"]) <= 0:
            continue
        if b["expiry_date"] and b["expiry_date"] < today:
            continue
        qty += int(b["qty_on_hand"])
        if b.get("online_sellby_date") and (sellby is None or b["online_sellby_date"] < sellby):
            sellby, batch = b["online_sellby_date"], b["batch_id"]
        if b.get("expiry_date") and (expiry is None or b["expiry_date"] < expiry):
            expiry = b["expiry_date"]
    online_ok = sellby is None or sellby >= today
    return {"sku": sku, "node_id": node_id, "qty": qty if online_ok else 0, "online_sellby_date": sellby, "expiry_date": expiry, "batch_id": batch, "name": ctx.products.get(sku, {}).get("name", sku), "list_price": ctx.products.get(sku, {}).get("list_price")}


LOW_STOCK_THRESHOLD = 5  # "few_left" below this; the exact count never leaves the tool layer


def _availability(qty: int) -> str:
    """Customers get a band, never the on-hand number: an internal inventory position is not
    something a shopper needs, and a live model will happily repeat whatever number it is given."""
    return "out_of_stock" if qty <= 0 else ("few_left" if qty <= LOW_STOCK_THRESHOLD else "in_stock")


def get_stock(sku: str, node_id: str) -> dict:
    """Availability at the node (unexpired lots), nearest online sell-by and expiry. A customer
    asking directly and finding nothing is a demand signal: recorded deterministically, read back
    by Sense (unmet_demand gaps) and by this customer's own memory next session."""
    ctx = current()
    node_id = _resolve_node(ctx, node_id)
    info = _stock_info(ctx, sku, node_id)
    if info["qty"] == 0:
        _record_request(ctx, node_id, "out_of_stock", sku=sku)
    return {k: v for k, v in info.items() if k != "qty"} | {"availability": _availability(info["qty"])}


def find_substitutes(sku: str, node_id: str) -> list[dict]:
    """Precomputed same-category candidates filtered by stock at the node right now; top 5."""
    ctx = current()
    node_id = _resolve_node(ctx, node_id)
    rows = ctx.store.find("substitutes", sku=sku)
    cands = rows[-1]["candidates"] if rows else []
    out = []
    for c in cands:
        st = _stock_info(ctx, c, node_id)
        if st["qty"] > 0:
            out.append({"sku": c, "name": st["name"], "availability": _availability(st["qty"]), "list_price": st["list_price"]})
        if len(out) == 5:
            break
    return out


def _resolve_pending_play_id(ctx, customer_id: str) -> str | None:
    """This customer's own single undelivered, unredeemed offer's play_id, if there is exactly
    one. `context_summary` (this module) deliberately never tells the model the real play_id
    behind an offer -- only its customer-facing text -- so a model asked to act on an "add:<sku>"
    button click (the sku is all the click carries) sometimes invents a play_id from the sku
    instead (observed live: "PLAY-SKU-..." for a real id like "play_chips_ds07_v1"). Falling back
    to the customer's own real pending offer here, rather than failing the order, is a pure
    lookup with no guardrail bypass: apply_offer's own arm/consent/cap/no-stacking checks below
    still run against whatever play_id this resolves to."""
    redeemed = {ln["play_id"] for ln in ctx.store.read("order_lines") if ln["customer_id"] == customer_id and ln.get("play_id")}
    candidates = {o["play_id"] for o in ctx.store.read("offers") if o["customer_id"] == customer_id and not o.get("redeemed_at") and o["play_id"] not in redeemed}
    return next(iter(candidates)) if len(candidates) == 1 else None


REFUSAL = {
    "en": {
        "not_treated": "This offer is not available on your account.",
        "no_consent": "You have opted out of offers on chat, so I can't apply this one.",
        "frequency_cap": "You have reached this week's limit on offers, so I can't apply this one.",
        "already_redeemed": "This offer has already been used on your account.",
    },
    "kn": {
        "not_treated": "ಈ ಆಫರ್ ನಿಮ್ಮ ಖಾತೆಗೆ ಲಭ್ಯವಿಲ್ಲ.",
        "no_consent": "ನೀವು ಚಾಟ್‌ನಲ್ಲಿ ಆಫರ್‌ಗಳನ್ನು ನಿಲ್ಲಿಸಿದ್ದೀರಿ, ಹಾಗಾಗಿ ಈ ಆಫರ್ ಅನ್ವಯಿಸಲು ಆಗುವುದಿಲ್ಲ.",
        "frequency_cap": "ಈ ವಾರದ ಆಫರ್ ಮಿತಿ ತಲುಪಿದೆ, ಹಾಗಾಗಿ ಈ ಆಫರ್ ಅನ್ವಯಿಸಲು ಆಗುವುದಿಲ್ಲ.",
        "already_redeemed": "ಈ ಆಫರ್ ನಿಮ್ಮ ಖಾತೆಯಲ್ಲಿ ಈಗಾಗಲೇ ಬಳಕೆಯಾಗಿದೆ.",
    },
}


def _reply_lang(ctx, customer_id: str) -> str:
    return ctx.reply_lang or (_customer_profile(ctx, customer_id) or {}).get("language", "en")


def _refused(ctx, customer_id: str, code: str, reason: str) -> dict:
    """A refusal with its customer-facing text composed here (`reply`), never by the model."""
    return {"ok": False, "code": code, "reason": reason, "reply": REFUSAL.get(_reply_lang(ctx, customer_id), REFUSAL["en"])[code], "reply_en": REFUSAL["en"][code]}


def apply_offer(play_id: str, customer_id: str) -> dict:
    """Whether this customer may redeem the play now: arm, consent, frequency cap, no stacking.
    A refusal carries a `code` and, for the customer-facing ones, the `reply` text to show."""
    ctx = current()
    play = _play(ctx, play_id)
    if not play or play.get("status") not in ("approved", "running"):
        fallback_id = _resolve_pending_play_id(ctx, customer_id)
        if fallback_id and fallback_id != play_id:
            play_id, play = fallback_id, _play(ctx, fallback_id)
    if not play or play.get("status") not in ("approved", "running"):
        return {"ok": False, "code": "not_active", "reason": "play is not active"}
    arms = _arms(ctx, customer_id)
    if arms.get(play_id) != "treated" or assign_arm(customer_id, play["holdout"]["seed"], float(play["holdout"]["fraction"])) != "treated":
        return _refused(ctx, customer_id, "not_treated", "customer is not in the treated arm of this play")
    if not _consent_ok(ctx, customer_id):
        return _refused(ctx, customer_id, "no_consent", "no marketing consent on this channel")
    if any(ln.get("play_id") == play_id and ln["customer_id"] == customer_id for ln in ctx.store.read("order_lines")):
        return _refused(ctx, customer_id, "already_redeemed", "offer already redeemed; coupons do not stack")
    cap = int(ctx.tenant.thresholds.get("frequency_cap_per_7d", 2))
    cutoff = (ctx.as_of - timedelta(days=7)).isoformat()
    recent = defaultdict(int)
    for a in ctx.store.read("play_assignments"):
        if a["customer_id"] == customer_id and a["arm"] == "treated" and a["assigned_at"][:10] >= cutoff:
            recent[a["play_id"]] += 1
    if len(recent) > cap:
        return _refused(ctx, customer_id, "frequency_cap", f"frequency cap {cap} plays per 7 days reached")
    params = play.get("mechanic_params") or {}
    out: dict[str, Any] = {"ok": True, "reason": "eligible", "play_id": play_id, "mechanic": play["mechanic"], "sku": play["target"]["sku"], "node_ids": play["target"]["node_ids"]}
    if play["mechanic"] == "coupon":
        out["discount_pct"] = float(params.get("discount_pct") or 0)
    if play["mechanic"] == "bundle":
        out["bundle_sku"], out["bundle_price"] = params.get("bundle_sku"), float(params.get("bundle_price") or 0)
    return out


_VOLUME_FRIENDLY_CATEGORIES = {"snacks", "beverages", "staples", "personal_care", "household"}


def _typical_qty(ctx, customer_id: str, sku: str, category: str) -> float | None:
    """The median units-per-order this customer actually buys of this sku, so a volume nudge asks
    for more than their own habit rather than an arbitrary flat number -- e.g. a customer who
    always buys 1 gets asked to buy a few more than that; a customer already buying several at a
    time isn't offered a discount on volume they were always going to buy anyway.

    Direct-sku history first; same-category history as a fallback (same sku-then-category order
    as get_candidate_audiences' affinity lookup). Median, not mean: robust to a single bulk order
    skewing the target. None with no history at all in either -- a customer this tool knows
    nothing about gets negotiate_offer's flat default, not a guessed number."""
    lines = ctx.store.read("order_lines")
    direct = sorted(line_["qty"] for line_ in lines if line_["customer_id"] == customer_id and line_["sku"] == sku)
    if direct:
        return statistics.median(direct)
    cat_skus = {s for s, p in ctx.products.items() if p["category"] == category}
    cat = sorted(line_["qty"] for line_ in lines if line_["customer_id"] == customer_id and line_["sku"] in cat_skus)
    return statistics.median(cat) if cat else None


def negotiate_offer(customer_id: str, sku: str) -> dict:
    """A live, ad-hoc concession for a sku with no approved play targeting this customer -- the
    customer asked directly ("what offer can I get"), so unlike apply_offer (which only redeems
    an already planner-drafted, holdout-measured play) there is no pre-approved play to check.
    Every number here is still deterministic, never an LLM decision: the category margin floor,
    the tenant's separate (more conservative) ad-hoc discount ceiling, the frequency cap shared
    with played offers, and whether this customer has ordered from Kutumb Mart before. Gemini
    only decides how to phrase whatever this returns; it never invents a percentage or a
    quantity threshold.

    Returns one of two mechanics, chosen deterministically by category, never by the model:
    `volume_discount` (buy `min_qty` units, get the full ceiling off) for everyday multi-buy
    categories where committing to a bigger basket justifies the maximum concession; otherwise
    `flat_discount` (half the ceiling, no purchase commitment).

    `min_qty` on a volume_discount is personalized from `_typical_qty`, not a flat number: it asks
    for more than this customer's own median order size (`ad_hoc_volume_nudge_step` more), so the
    offer targets an actual behaviour change. A customer already ordering at or above
    `ad_hoc_volume_already_loyal_qty` on their own gets no offer at all on this path -- discounting
    a purchase they were always going to make is pure margin given away for no incremental sale."""
    ctx = current()
    product = ctx.products.get(sku)
    if not product:
        return {"ok": False, "reason": f"unknown sku {sku}"}
    if not _consent_ok(ctx, customer_id):
        return {"ok": False, "reason": "no marketing consent on this channel"}

    cap = int(ctx.tenant.thresholds.get("frequency_cap_per_7d", 2))
    cutoff = (ctx.as_of - timedelta(days=7)).isoformat()
    recent_plays = {a["play_id"] for a in ctx.store.read("play_assignments") if a["customer_id"] == customer_id and a["arm"] == "treated" and a["assigned_at"][:10] >= cutoff}
    recent_ad_hoc = [o for o in ctx.store.read("ad_hoc_offers") if o["customer_id"] == customer_id and o["ts"][:10] >= cutoff]
    if len(recent_plays) + len(recent_ad_hoc) >= cap:
        return {"ok": False, "reason": f"frequency cap {cap} offers per 7 days reached"}

    floor = float(product.get("margin_floor_pct") or ctx.tenant.margin_floor(product["category"]))
    list_price, unit_cost = float(product["list_price"]), float(product["unit_cost"])
    current_margin_pct = (list_price - unit_cost) / list_price * 100.0
    headroom_pct = max(0.0, current_margin_pct - floor)
    ceiling = min(float(ctx.tenant.thresholds.get("ad_hoc_max_discount_pct", 8.0)), headroom_pct)
    if ceiling <= 0:
        return {"ok": False, "reason": "margin floor leaves no room for a discount on this item"}

    # "Customer's previous behaviour": the simplest deterministic signal available -- has this
    # customer ordered from Kutumb Mart before at all. A repeat customer's flat-discount base
    # gets a loyalty bonus (still capped at the ceiling); a volume commitment already earns the
    # full ceiling regardless, so the bonus has nothing left to add there.
    is_repeat = any(o["customer_id"] == customer_id for o in ctx.store.read("orders"))
    loyalty_bonus = float(ctx.tenant.thresholds.get("ad_hoc_loyalty_bonus_pct", 3.0)) if is_repeat else 0.0

    if product["category"] in _VOLUME_FRIENDLY_CATEGORIES:
        typical = _typical_qty(ctx, customer_id, sku, product["category"])
        already_loyal_qty = float(ctx.tenant.thresholds.get("ad_hoc_volume_already_loyal_qty", 4))
        if typical is not None and typical >= already_loyal_qty:
            return {"ok": False, "reason": f"already orders about {typical:g} units of this at a time on their own -- no incremental offer needed"}
        nudge_step = float(ctx.tenant.thresholds.get("ad_hoc_volume_nudge_step", 3))
        mechanic, discount_pct = "volume_discount", round(ceiling, 1)
        if typical is not None:
            min_qty = int(round(typical)) + int(nudge_step)
            reason = f"orders about {typical:g} at a time on average, so buying {min_qty} unlocks {discount_pct:g}% off -- above their usual, not a discount on what they'd buy anyway"
        else:
            min_qty = 4
            reason = "no order history for this category yet, so this is the standard multi-buy offer"
    else:
        mechanic, min_qty, discount_pct = "flat_discount", None, round(min(ceiling, ceiling / 2.0 + loyalty_bonus), 1)
        reason = "returning customer, so this includes a small loyalty bonus" if is_repeat else "eligible"

    offer_id = f"adhoc_{customer_id}_{sku}_{uuid.uuid4().hex[:8]}"
    ctx.store.append("ad_hoc_offers", [{
        "tenant_id": ctx.tenant.tenant_id, "offer_id": offer_id, "customer_id": customer_id, "sku": sku, "mechanic": mechanic,
        "discount_pct": discount_pct, "min_qty": min_qty, "session_id": f"{customer_id}:{ctx.channel}",
        "ts": ctx.now_iso, "redeemed_at": None,
    }])
    out: dict[str, Any] = {"ok": True, "reason": reason, "sku": sku, "mechanic": mechanic, "discount_pct": discount_pct}
    if min_qty is not None:
        out["min_qty"] = min_qty
    return out


def _pending_ad_hoc_offer(ctx, customer_id: str, sku: str) -> dict[str, Any] | None:
    """The most recent un-redeemed negotiate_offer result for this customer and sku, if any."""
    rows = [o for o in ctx.store.read("ad_hoc_offers") if o["customer_id"] == customer_id and o["sku"] == sku and not o.get("redeemed_at")]
    return rows[-1] if rows else None


ORDER_CONFIRMATION = {
    "en": "Your order for {items} has been placed. Your order ID is {order_id} and the total is ₹{total}.",
    "kn": "ಆರ್ಡರ್ {order_id} ಆಗಿದೆ: {items}. ಒಟ್ಟು ₹{total}. ಧನ್ಯವಾದಗಳು!",
}


def _confirmation(ctx, customer_id: str, order_id: str, total: float, lines: list[dict[str, Any]], lang: str | None = None) -> str:
    """The customer-facing receipt, composed here from the order record (never by the model) so it
    can never disagree with what was placed. The runtime shows it verbatim (agents/chat_runtime.py)."""
    items = " + ".join(f"{ln['qty']} x {ln['name']}" if ln["qty"] > 1 else ln["name"] for ln in lines)
    return ORDER_CONFIRMATION.get(lang or _reply_lang(ctx, customer_id), ORDER_CONFIRMATION["en"]).format(items=items, order_id=order_id, total=f"{total:.2f}".rstrip("0").rstrip("."))


def _offer_play(ctx, customer_id: str, play_id: str, skus: set[str]) -> str | None:
    """The active play whose offer an order for `skus` is accepting, or None for a plain order: the
    play the model named, this customer's own pending offer, or one they redeemed earlier today (a
    repeat click). Matched on the play's target sku, so the model's lines and play_id are only hints.
    NOTE: "today" bounds how long a redeemed offer keeps refusing re-orders of its sku; a later
    day buys at list price as usual."""
    mine = [o for o in ctx.store.read("offers") if o["customer_id"] == customer_id]
    today = ctx.now_iso[:10]
    cands = [play_id] + [o["play_id"] for o in mine if not o.get("redeemed_at")] + [o["play_id"] for o in mine if today and (o.get("redeemed_at") or "")[:10] == today]
    for pid in dict.fromkeys(c for c in cands if c):
        play = _play(ctx, pid)
        if play and play.get("status") in ("approved", "running") and play["target"]["sku"] in skus:
            return pid
    return None


async def place_order(customer_id: str, node_id: str, lines: list[dict], play_id: str) -> dict:
    """Place the order through the MCP order mock. lines: [{sku, qty}], priced here from the
    catalogue, the play (if any) and any pending negotiate_offer for a line's sku (checked
    per-line, independently of the play offer, since a negotiated concession has no play_id).

    The model's `play_id` and `lines` are hints, not the order. The customer's own pending offer is
    resolved server-side (`_offer_play`, whatever id the model sent) whenever the order contains
    the offer's target sku -- an `add:<sku>` click carries only that one sku --
    and a bundle offer then yields exactly the bundle: target x1 + partner x1 totalling the
    play's `bundle_price`, whatever lines the model sent. Units beyond the bundle, and any other
    sku, are priced as before. The result carries the receipt text (`reply`).

    If the order touches the target sku of this customer's offer (pending, or redeemed earlier today:
    a repeat click) or of the play the model named, it is an offer acceptance: when apply_offer
    refuses, no order is placed and the result is a refusal (`refused` code + `reply`), never a
    silent list-price order. An order with no offer context is a plain order, as before."""
    ctx = current()
    offer: dict[str, Any] = {"ok": False}
    if pid := _offer_play(ctx, customer_id, play_id, {ln["sku"] for ln in lines}):
        offer = apply_offer(pid, customer_id)
        if not offer["ok"]:
            return {"order_id": "", "total_inr": 0.0, "refused": offer["code"], "error": offer["reason"], "reply": offer["reply"], "reply_en": offer["reply_en"]}
    play_id = offer.get("play_id")
    priced = []
    if offer.get("mechanic") == "bundle" and offer.get("bundle_sku"):
        target, partner = offer["sku"], offer["bundle_sku"]
        if target not in ctx.products or partner not in ctx.products:
            return {"order_id": "", "total_inr": 0.0, "error": f"unknown sku {partner if target in ctx.products else target}"}
        full = float(ctx.products[target]["list_price"]) + float(ctx.products[partner]["list_price"])
        off = round(max(0.0, full - float(offer["bundle_price"])), 2)
        priced = [{"sku": target, "qty": 1, "price": float(ctx.products[target]["list_price"]), "discount": off}, {"sku": partner, "qty": 1, "price": float(ctx.products[partner]["list_price"]), "discount": 0.0}]
        lines = [{**ln, "qty": int(ln["qty"]) - (ln["sku"] in (target, partner))} for ln in lines]  # the bundle already holds one of each
        lines = [ln for ln in lines if ln["qty"] > 0]
    redeemed_ad_hoc: list[dict[str, Any]] = []
    for ln in lines:
        p = ctx.products.get(ln["sku"])
        if not p:
            return {"order_id": "", "total_inr": 0.0, "error": f"unknown sku {ln['sku']}"}
        price = float(p["list_price"])
        disc = 0.0
        if offer.get("ok") and ln["sku"] == offer.get("sku") and offer.get("discount_pct"):
            disc = round(price * float(offer["discount_pct"]) / 100.0, 2)
        else:
            ad_hoc = _pending_ad_hoc_offer(ctx, customer_id, ln["sku"])
            if ad_hoc and (ad_hoc["mechanic"] != "volume_discount" or int(ln["qty"]) >= int(ad_hoc["min_qty"])):
                disc = round(price * float(ad_hoc["discount_pct"]) / 100.0, 2)
                redeemed_ad_hoc.append(ad_hoc)
        priced.append({"sku": ln["sku"], "qty": int(ln["qty"]), "price": price, "discount": disc})
    base_dir = str(ctx.store.base.root) if hasattr(ctx.store, "base") else None
    async with Client(orders_server) as client:
        res = await client.call_tool("place_order", {"customer_id": customer_id, "node_id": node_id, "lines": priced, "play_id": play_id, "data_dir": str(ctx.store.root), "base_dir": base_dir, "ts": ctx.now_iso})
    data = res.structured_content or json.loads(res.content[0].text)
    data["lines"] = [{"sku": ln["sku"], "name": ctx.products[ln["sku"]]["name"], "qty": ln["qty"], "price": ln["price"], "discount": ln["discount"]} for ln in priced]
    if play_id and offer.get("ok"):
        for o in ctx.store.read("offers"):
            if o["customer_id"] == customer_id and o["play_id"] == play_id and not o.get("redeemed_at"):
                o["redeemed_at"] = ctx.now_iso
                ctx.store.upsert("offers", "offer_id", o)
    for ad_hoc in redeemed_ad_hoc:
        ad_hoc["redeemed_at"] = ctx.now_iso
        ctx.store.upsert("ad_hoc_offers", "offer_id", ad_hoc)
    return {"order_id": data["order_id"], "total_inr": float(data["total_inr"]), "lines": data["lines"], "reply": _confirmation(ctx, customer_id, data["order_id"], float(data["total_inr"]), data["lines"]), "reply_en": _confirmation(ctx, customer_id, data["order_id"], float(data["total_inr"]), data["lines"], lang="en")}


def record_stop(customer_id: str, channel: str) -> dict:
    """STOP: withdraw marketing consent on the channel and drop pending offers."""
    ctx = current()
    rows = ctx.store.read("consent")
    hit = False
    for r in rows:
        if r["customer_id"] == customer_id and r["channel"] == channel and r["purpose"] == "marketing" and not r.get("withdrawn_at"):
            r["withdrawn_at"] = ctx.now_iso
            hit = True
    if not hit:
        rows.append({"tenant_id": ctx.tenant.tenant_id, "customer_id": customer_id, "channel": channel, "purpose": "marketing", "source": "stop", "ts": ctx.now_iso, "withdrawn_at": ctx.now_iso})
    ctx.store.write("consent", rows)
    offers = [o for o in ctx.store.read("offers") if o["customer_id"] != customer_id]
    ctx.store.write("offers", offers)
    return {"ok": True}


STOPWORDS = {"have", "there", "what", "with", "your", "some", "want", "need", "tell", "give", "show", "does", "store", "today", "please", "about"}


def _tokens(text: str) -> list[str]:
    return [t for t in re.findall(r"[a-z]+", text.lower()) if len(t) >= 4 and t not in STOPWORDS]


def list_products(query: str, node_id: str) -> dict:
    """Browse: up to 10 in-stock products at the node whose name or category matches the query
    words; with an empty query, the categories on the shelf. Never lists items with zero stock."""
    ctx = current()
    node_id = _resolve_node(ctx, node_id)
    today = ctx.as_of.isoformat()
    stock: dict[str, int] = defaultdict(int)
    for b in ctx.store.read("inventory_batches"):
        if b["node_id"] == node_id and int(b["qty_on_hand"]) > 0 and (not b["expiry_date"] or b["expiry_date"] >= today) and (not b.get("online_sellby_date") or b["online_sellby_date"] >= today):
            stock[b["sku"]] += int(b["qty_on_hand"])
    in_stock = [p for sku, p in ctx.products.items() if stock.get(sku, 0) > 0]
    categories = sorted({p["category"] for p in in_stock})
    words = _tokens(query)
    if not words:
        return {"query": query, "node_id": node_id, "categories": categories, "products": []}
    hits = []
    for p in in_stock:
        hay = (p["name"] + " " + p["category"].replace("_", " ")).lower()
        score = sum(1 for w in words if w in hay or (w.endswith("s") and w[:-1] in hay))
        if score:
            hits.append((score, -stock[p["sku"]], p["sku"], p))
    hits.sort(key=lambda h: (-h[0], h[1], h[2]))
    if not hits:
        _record_request(ctx, node_id, "no_match", query_text=query)
    return {"query": query, "node_id": node_id, "categories": categories, "products": [{"sku": h[3]["sku"], "name": h[3]["name"], "category": h[3]["category"], "availability": _availability(stock[h[3]["sku"]]), "list_price": float(h[3]["list_price"])} for h in hits[:10]]}


TOOLS = [get_customer_context, get_stock, find_substitutes, apply_offer, negotiate_offer, place_order, record_stop, list_products]
