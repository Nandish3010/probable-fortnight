"""The six Customer Agent tools (DECISIONS §5.5). Contracts: docs/schemas/tools/customer.*.

Holdout customers never see an offer: `get_customer_context` returns no pending offers for them,
`apply_offer` refuses, and proactive delivery (services/api) checks the arm before writing offers.
`place_order` goes through the MCP order mock over an in-memory MCP session.
"""
from __future__ import annotations

import json
import re
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
    return {"customer_id": customer_id, "home_node_id": c["home_node_id"], "language": c.get("language", "en"), "display_name": c.get("display_name"), "pending_offers": offers, "arms": arms, "consent_marketing": consent, "memory": _customer_memory(ctx, customer_id)}


def _stock_info(ctx, sku: str, node_id: str) -> dict:
    """Pure lookup, no side effects. Shared by get_stock (which records the demand signal on top),
    find_substitutes and _customer_memory, so checking on a customer's behalf internally never
    itself counts as a customer asking."""
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
    info = _stock_info(ctx, sku, node_id)
    if info["qty"] == 0:
        _record_request(ctx, node_id, "out_of_stock", sku=sku)
    return {k: v for k, v in info.items() if k != "qty"} | {"availability": _availability(info["qty"])}


def find_substitutes(sku: str, node_id: str) -> list[dict]:
    """Precomputed same-category candidates filtered by stock at the node right now; top 5."""
    ctx = current()
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
    data["lines"] = [{"sku": ln["sku"], "name": ctx.products[ln["sku"]]["name"], "qty": ln["qty"], "price": ln["price"], "discount": ln["discount"]} for ln in priced]
    if play_id and offer.get("ok"):
        for o in ctx.store.read("offers"):
            if o["customer_id"] == customer_id and o["play_id"] == play_id and not o.get("redeemed_at"):
                o["redeemed_at"] = ctx.now_iso
                ctx.store.upsert("offers", "offer_id", o)
    return {"order_id": data["order_id"], "total_inr": float(data["total_inr"]), "lines": data["lines"]}


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


TOOLS = [get_customer_context, get_stock, find_substitutes, apply_offer, place_order, record_stop, list_products]
