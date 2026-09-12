"""The six Customer Agent tools (DECISIONS §5.5). Contracts: docs/schemas/tools/customer.*.

Holdout customers never see an offer: `get_customer_context` returns no pending offers for them,
`apply_offer` refuses, and proactive delivery (services/api) checks the arm before writing offers.
`place_order` goes through the MCP order mock over an in-memory MCP session.
"""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import timedelta
from typing import Any

from mcp.client import Client

from agents.gate.assignment import assign_arm
from agents.mcp_orders.server import server as orders_server

from .context import current


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
    rows = [r for r in ctx.store.read("consent") if r["customer_id"] == customer_id and r["purpose"] == "marketing" and r["channel"] == ctx.channel]
    return bool(rows) and not rows[-1].get("withdrawn_at")


def get_customer_context(customer_id: str) -> dict:
    """Home node, language, pending offers (treated arm only), arms per play and marketing consent."""
    ctx = current()
    cust = ctx.store.find("customers", customer_id=customer_id)
    if not cust:
        return {"customer_id": customer_id, "home_node_id": "DS-01", "language": "en", "pending_offers": [], "arms": {}, "consent_marketing": False}
    c = cust[-1]
    arms = _arms(ctx, customer_id)
    consent = _consent_ok(ctx, customer_id)
    offers = []
    if consent:
        for o in ctx.store.read("offers"):
            if o["customer_id"] != customer_id or o.get("redeemed_at"):
                continue
            play = _play(ctx, o["play_id"])
            if not play or play.get("status") not in ("approved", "running"):
                continue
            if arms.get(o["play_id"]) != "treated" or assign_arm(customer_id, play["holdout"]["seed"], float(play["holdout"]["fraction"])) != "treated":
                continue
            offers.append({"play_id": o["play_id"], "text": o["text"], "best_before_date": o.get("best_before_date"), "sku": o.get("sku"), "mechanic": o.get("mechanic"), "mechanic_params": o.get("mechanic_params", {})})
    return {"customer_id": customer_id, "home_node_id": c["home_node_id"], "language": c.get("language", "en"), "display_name": c.get("display_name"), "pending_offers": offers, "arms": arms, "consent_marketing": consent}


def get_stock(sku: str, node_id: str) -> dict:
    """Units on hand at the node (unexpired lots), nearest online sell-by and expiry."""
    ctx = current()
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


def find_substitutes(sku: str, node_id: str) -> list[dict]:
    """Precomputed same-category candidates filtered by stock at the node right now; top 5."""
    ctx = current()
    rows = ctx.store.find("substitutes", sku=sku)
    cands = rows[-1]["candidates"] if rows else []
    out = []
    for c in cands:
        st = get_stock(c, node_id)
        if st["qty"] > 0:
            out.append({"sku": c, "name": st["name"], "qty": st["qty"], "list_price": st["list_price"]})
        if len(out) == 5:
            break
    return out


def apply_offer(play_id: str, customer_id: str) -> dict:
    """Whether this customer may redeem the play now: arm, consent, frequency cap, no stacking."""
    ctx = current()
    play = _play(ctx, play_id)
    if not play or play.get("status") not in ("approved", "running"):
        return {"ok": False, "reason": "play is not active"}
    arms = _arms(ctx, customer_id)
    if arms.get(play_id) != "treated" or assign_arm(customer_id, play["holdout"]["seed"], float(play["holdout"]["fraction"])) != "treated":
        return {"ok": False, "reason": "customer is not in the treated arm of this play"}
    if not _consent_ok(ctx, customer_id):
        return {"ok": False, "reason": "no marketing consent on this channel"}
    if any(ln.get("play_id") == play_id and ln["customer_id"] == customer_id for ln in ctx.store.read("order_lines")):
        return {"ok": False, "reason": "offer already redeemed; coupons do not stack"}
    cap = int(ctx.tenant.thresholds.get("frequency_cap_per_7d", 2))
    cutoff = (ctx.as_of - timedelta(days=7)).isoformat()
    recent = defaultdict(int)
    for a in ctx.store.read("play_assignments"):
        if a["customer_id"] == customer_id and a["arm"] == "treated" and a["assigned_at"][:10] >= cutoff:
            recent[a["play_id"]] += 1
    if len(recent) > cap:
        return {"ok": False, "reason": f"frequency cap {cap} plays per 7 days reached"}
    params = play.get("mechanic_params") or {}
    out: dict[str, Any] = {"ok": True, "reason": "eligible", "mechanic": play["mechanic"], "sku": play["target"]["sku"], "node_ids": play["target"]["node_ids"]}
    if play["mechanic"] == "coupon":
        out["discount_pct"] = float(params.get("discount_pct") or 0)
    if play["mechanic"] == "bundle":
        out["bundle_sku"], out["bundle_price"] = params.get("bundle_sku"), float(params.get("bundle_price") or 0)
    return out


async def place_order(customer_id: str, node_id: str, lines: list[dict], play_id: str) -> dict:
    """Place the order through the MCP order mock. lines: [{sku, qty}], priced here from the catalogue and the play."""
    ctx = current()
    priced = []
    offer = apply_offer(play_id, customer_id) if play_id else {"ok": False}
    for ln in lines:
        p = ctx.products.get(ln["sku"])
        if not p:
            return {"order_id": "", "total_inr": 0.0, "error": f"unknown sku {ln['sku']}"}
        price = float(p["list_price"])
        disc = 0.0
        if offer.get("ok") and ln["sku"] == offer.get("sku") and offer.get("discount_pct"):
            disc = round(price * float(offer["discount_pct"]) / 100.0, 2)
        priced.append({"sku": ln["sku"], "qty": int(ln["qty"]), "price": price, "discount": disc})
    if offer.get("ok") and offer.get("mechanic") == "bundle" and offer.get("bundle_sku"):
        skus = {ln["sku"] for ln in priced}
        if offer["sku"] in skus and offer["bundle_sku"] in skus:
            full = sum(float(ctx.products[s]["list_price"]) for s in (offer["sku"], offer["bundle_sku"]))
            off = max(0.0, full - float(offer["bundle_price"]))
            for ln in priced:
                if ln["sku"] == offer["sku"]:
                    ln["discount"] = round(off, 2)
    base_dir = str(ctx.store.base.root) if hasattr(ctx.store, "base") else None
    async with Client(orders_server) as client:
        res = await client.call_tool("place_order", {"customer_id": customer_id, "node_id": node_id, "lines": priced, "play_id": play_id or None, "data_dir": str(ctx.store.root), "base_dir": base_dir, "ts": ctx.now_iso})
    data = res.structured_content or json.loads(res.content[0].text)
    if play_id and offer.get("ok"):
        for o in ctx.store.read("offers"):
            if o["customer_id"] == customer_id and o["play_id"] == play_id and not o.get("redeemed_at"):
                o["redeemed_at"] = ctx.now_iso
                ctx.store.upsert("offers", "offer_id", o)
    return {"order_id": data["order_id"], "total_inr": float(data["total_inr"])}


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


TOOLS = [get_customer_context, get_stock, find_substitutes, apply_offer, place_order, record_stop]
