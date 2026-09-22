"""The Stylist Agent's tools (DECISIONS §5.9). Contracts: docs/schemas/tools/stylist.*.

Colour theory, role pairing, the stock filter and every demand-signal write are deterministic
Python (agents/stylist/colour.py, this module); the LLM only decides how to talk about a look.
`_record_style_ask` is never itself a tool -- it is called from inside `find_apparel` and
`suggest_pairings`, exactly as `agents/customer/tools.py::_record_request` is, so a demand signal
is written whether or not the model decides to comment on it.
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

from .colour import pairing_rules, skin_adjustment, skin_tone_rules
from .context import current
from .parse import ParsedGarment, parse_description

ROLE_PAIRS: dict[str, list[str]] = {
    "top": ["bottom", "layer", "footwear", "accessory"],
    "bottom": ["top", "layer", "footwear", "accessory"],
    "dress": ["layer", "footwear", "accessory"],
    "layer": ["top", "bottom", "footwear", "accessory"],
    "footwear": ["bottom", "top", "dress", "accessory"],
    "accessory": ["top", "dress", "bottom", "footwear"],
}
_FACE_ADJACENT_ACCESSORIES = {"scarf", "earrings", "necklace"}
STOPWORDS = {"have", "there", "what", "with", "your", "some", "want", "need", "tell", "give", "show", "does", "store", "today", "please", "about", "goes", "pair", "match", "outfit"}


def _tokens(text: str) -> list[str]:
    return [t for t in re.findall(r"[a-z]+", text.lower()) if len(t) >= 3 and t not in STOPWORDS]


def _resolve_node(ctx, node_id: str | None) -> str:
    """The node to search at: the model's own `node_id`/`home_node_id` argument if it names a
    node that actually exists (a deliberate cross-node check, e.g. "is it at the outlet"), else
    the customer's real home node. Found live: neither find_apparel's nor suggest_pairings's tool
    schema gives `node_id` a description, and the prompt inconsistently calls the same schema
    field "home_node_id" in prose -- with no strong signal to reuse the value get_style_context
    already returned, a live Gemini call fabricated a plausible-looking but nonexistent id
    ("NODE-KUTUMB-MART-HYD-1") instead, so every apparel search silently matched zero stock
    regardless of what was actually on the shelf. A real, different node id is trusted (the model
    may legitimately mean a specific other store); a fabricated one is not."""
    if node_id and ctx.store.find("nodes", node_id=node_id):
        return node_id
    cust = ctx.store.find("customers", customer_id=ctx.customer_id)
    return cust[-1]["home_node_id"] if cust else "DS-01"


def _in_stock_at(ctx, node_id: str) -> dict[str, list[str]]:
    """sku -> sizes in stock at the node, right now."""
    out: dict[str, list[str]] = defaultdict(list)
    for r in ctx.store.read("apparel_stock"):
        if r["node_id"] == node_id and int(r["qty_on_hand"]) > 0:
            out[r["sku"]].append(r["size"])
    return out


def _record_style_ask(ctx, node_id: str, source: str, garment_type: str | None, colour: str | None, colour_family: str | None, occasion: str | None, query_text: str | None, matched_sku: str | None, fulfilled: bool) -> None:
    """Deterministic instrumentation, never an LLM decision. Never carries a skin-tone field: the
    style profile is a separate, consent-gated concept and must never leak into the demand signal
    that Sense aggregates into style_trends."""
    ctx.store.append("style_requests", [{
        "tenant_id": ctx.tenant.tenant_id, "customer_id": ctx.customer_id, "node_id": node_id,
        "session_id": f"{ctx.customer_id}:{ctx.channel}", "ts": ctx.now_iso, "source": source,
        "garment_type": garment_type, "colour": colour, "colour_family": colour_family,
        "occasion": occasion, "query_text": query_text, "matched_sku": matched_sku, "fulfilled": fulfilled,
    }])


def _recent_asks(ctx, customer_id: str, limit: int = 5) -> list[dict[str, Any]]:
    rows = [r for r in ctx.store.read("style_requests") if r["customer_id"] == customer_id]
    grouped: dict[tuple[str | None, str | None, str | None], dict[str, Any]] = {}
    for r in sorted(rows, key=lambda r: r["ts"]):
        key = (r.get("garment_type"), r.get("colour_family"), r.get("occasion"))
        g = grouped.setdefault(key, {"garment_type": r.get("garment_type"), "colour_family": r.get("colour_family"), "occasion": r.get("occasion"), "times_asked": 0, "fulfilled": r.get("fulfilled", False)})
        g["times_asked"] += 1
        g["last_asked_at"] = r["ts"]
        g["fulfilled"] = r.get("fulfilled", False)
    return sorted(grouped.values(), key=lambda g: g["last_asked_at"], reverse=True)[:limit]


def get_style_context(customer_id: str) -> dict:
    """Home node, language, past asks and the customer's own confirmed skin-tone profile, if any."""
    ctx = current()
    cust = ctx.store.find("customers", customer_id=customer_id)
    profile = None
    if ctx.profile and ctx.customer_id == customer_id:
        profile = {"undertone": ctx.profile["undertone"], "depth": ctx.profile["depth"], "source": ctx.profile["source"], "confirmed": bool(ctx.profile["confirmed"])}
    if not cust:
        return {"customer_id": customer_id, "home_node_id": "DS-01", "language": "en", "recent_asks": _recent_asks(ctx, customer_id), "style_profile": profile}
    c = cust[-1]
    return {"customer_id": customer_id, "home_node_id": c["home_node_id"], "language": c.get("language", "en"), "display_name": c.get("display_name"), "recent_asks": _recent_asks(ctx, customer_id), "style_profile": profile}


def find_apparel(query: str, node_id: str) -> dict:
    """Search in-stock apparel at the node by garment, colour and occasion words in the query;
    records the ask whether or not anything matched, so a genuine miss is a real demand signal.
    `node_id` is validated against real nodes, not trusted blindly -- see `_resolve_node`."""
    ctx = current()
    node_id = _resolve_node(ctx, node_id)
    stock = _in_stock_at(ctx, node_id)
    parsed = parse_description(query)
    words = _tokens(query)
    hits: list[tuple[float, str, dict]] = []
    for sku in stock:
        item = ctx.apparel.get(sku)
        if not item:
            continue
        score = 0.0
        if parsed.garment_type and item["garment_type"] == parsed.garment_type:
            score += 3
        if parsed.colour_family and item["colour_family"] == parsed.colour_family:
            score += 2
        if parsed.pattern and item["pattern"] == parsed.pattern:
            score += 1
        if parsed.occasion and parsed.occasion in (item.get("occasions") or []):
            score += 1
        hay = (item["name"] + " " + item["garment_type"] + " " + item["colour"]).lower()
        score += sum(1 for w in words if w in hay)
        if score > 0:
            hits.append((score, sku, item))
    hits.sort(key=lambda h: (-h[0], h[1]))
    items = [{"sku": h[1], "name": h[2]["name"], "garment_type": h[2]["garment_type"], "role": h[2]["role"], "colour": h[2]["colour"], "colour_family": h[2]["colour_family"], "pattern": h[2]["pattern"], "list_price": float(h[2]["list_price"]), "sizes_in_stock": sorted(stock[h[1]])} for h in hits[:10]]
    matched_sku = items[0]["sku"] if items else None
    _record_style_ask(ctx, node_id, "find_apparel", parsed.garment_type, parsed.colour, parsed.colour_family, parsed.occasion, query, matched_sku, bool(items))
    return {"query": query, "node_id": node_id, "parsed": {"garment_type": parsed.garment_type, "colour_family": parsed.colour_family, "occasion": parsed.occasion, "pattern": parsed.pattern}, "items": items}


def describe_item(sku: str) -> dict:
    """Attributes of a named catalogue item; a lookup, not an ask, so it records no demand signal."""
    ctx = current()
    item = ctx.apparel.get(sku)
    if not item:
        return {"sku": sku, "found": False}
    return {"sku": sku, "found": True, "name": item["name"], "garment_type": item["garment_type"], "role": item["role"], "colour": item["colour"], "colour_family": item["colour_family"], "pattern": item["pattern"], "fabric": item["fabric"], "fit": item["fit"], "occasions": item.get("occasions") or [], "section": item["section"], "list_price": float(item["list_price"]), "season": item["season"]}


def _resolve_anchor(ctx, anchor: str) -> tuple[dict[str, Any], bool]:
    """(anchor description dict, is_known_sku)."""
    if anchor.upper().startswith("APP-") and anchor.upper() in ctx.apparel:
        item = ctx.apparel[anchor.upper()]
        return {"sku": anchor.upper(), "description": item["name"], "garment_type": item["garment_type"], "role": item["role"], "colour": item["colour"], "colour_family": item["colour_family"], "pattern": item["pattern"], "known_colour": True}, True
    parsed: ParsedGarment = parse_description(anchor)
    return {"sku": None, "description": parsed.describe(), "garment_type": parsed.garment_type, "role": parsed.role, "colour": parsed.colour, "colour_family": parsed.colour_family, "pattern": parsed.pattern, "known_colour": parsed.unknown_colour is None}, False


def suggest_pairings(anchor: str, node_id: str, occasion: str | None = None) -> dict:
    """Deterministic colour-theory + role pairing over in-stock apparel at the node. Gemini never
    scores a pairing; it only decides how to present these rows. The `reason` a row carries always
    comes from agents/stylist/colour.py; `skin_note` (if any) is a separate, additive annotation
    from the customer's own confirmed style profile, applied only to face-adjacent items.
    `node_id` is validated against real nodes, not trusted blindly -- see `_resolve_node`."""
    ctx = current()
    node_id = _resolve_node(ctx, node_id)
    anchor_info, anchor_is_sku = _resolve_anchor(ctx, anchor)
    occasion = occasion or (parse_description(anchor).occasion if not anchor_is_sku else None)
    garment_type, colour, role = anchor_info["garment_type"], anchor_info["colour"], anchor_info["role"]

    if not garment_type or not role:
        _record_style_ask(ctx, node_id, "suggest_pairings", garment_type, colour, anchor_info["colour_family"], occasion, anchor if not anchor_is_sku else None, None, False)
        return {"anchor": anchor_info, "occasion": occasion, "node_id": node_id, "profile_applied": False, "pairings": [], "fulfilled": False}

    rules = pairing_rules(colour, garment_type, occasion)
    score_by_family = {p["family"]: (p["score"], p["reason"]) for p in rules["pairs"]}
    allowed_roles = ROLE_PAIRS.get(role, [])
    anchor_patterned = bool(anchor_info.get("pattern") and anchor_info["pattern"] != "solid")

    profile_rules = None
    if ctx.profile and ctx.profile.get("confirmed"):
        profile_rules = skin_tone_rules(ctx.profile["undertone"], ctx.profile["depth"])

    stock = _in_stock_at(ctx, node_id)
    anchor_sku = anchor_info.get("sku")
    section = None
    if anchor_is_sku:
        section = ctx.apparel[anchor_sku]["section"]

    candidates: list[dict[str, Any]] = []
    for sku, sizes in stock.items():
        if sku == anchor_sku:
            continue
        item = ctx.apparel.get(sku)
        if not item or item["role"] not in allowed_roles:
            continue
        if section and section != "unisex" and item["section"] not in (section, "unisex"):
            continue
        if occasion and occasion not in (item.get("occasions") or []):
            continue
        fam = item["colour_family"]
        if fam not in score_by_family:
            continue
        score, reason = score_by_family[fam]
        if anchor_patterned and item["pattern"] and item["pattern"] != "solid":
            score -= 0.20
        if occasion and occasion in (item.get("occasions") or []):
            score += 0.05
        skin_note = None
        if profile_rules is not None:
            adj, skin_note = skin_adjustment(fam, item["role"], profile_rules, metal=item.get("metal"), garment_type=item["garment_type"], depth=ctx.profile["depth"])
            score += adj
        candidates.append({"sku": sku, "name": item["name"], "garment_type": item["garment_type"], "role": item["role"], "colour": item["colour"], "colour_family": fam, "pattern": item["pattern"], "reason": reason, "skin_note": skin_note, "score": round(max(0.0, min(1.0, score)), 3), "list_price": float(item["list_price"]), "sizes_in_stock": sorted(sizes)})

    candidates.sort(key=lambda c: (-c["score"], allowed_roles.index(c["role"]), c["list_price"], c["sku"]))

    picked: list[dict[str, Any]] = []
    per_role: dict[str, int] = defaultdict(int)
    for c in candidates:
        if len(picked) >= 10:
            break
        if per_role[c["role"]] >= 2:
            continue
        picked.append(c)
        per_role[c["role"]] += 1
    if len(picked) < 10:
        picked_skus = {c["sku"] for c in picked}
        for c in candidates:
            if len(picked) >= 10:
                break
            if c["sku"] not in picked_skus:
                picked.append(c)
                picked_skus.add(c["sku"])

    fulfilled = bool(picked)
    _record_style_ask(ctx, node_id, "suggest_pairings", garment_type, colour, anchor_info["colour_family"], occasion, anchor if not anchor_is_sku else None, anchor_sku or (picked[0]["sku"] if picked else None), fulfilled)
    return {"anchor": anchor_info, "occasion": occasion, "node_id": node_id, "profile_applied": profile_rules is not None, "pairings": picked, "fulfilled": fulfilled}


def set_style_profile(customer_id: str, undertone: str, depth: str, source: str, confidence: float | None = None) -> dict:
    """Save a confirmed skin-tone profile. Only ever called after the customer picked or confirmed
    a reading with a button -- never straight off a selfie read."""
    if undertone not in ("warm", "cool", "neutral"):
        raise ValueError(f"unknown undertone {undertone!r}")
    if depth not in ("light", "medium", "deep"):
        raise ValueError(f"unknown depth {depth!r}")
    ctx = current()
    row = {"tenant_id": ctx.tenant.tenant_id, "customer_id": customer_id, "undertone": undertone, "depth": depth, "source": source, "confidence": confidence, "confirmed": True, "ts": ctx.now_iso, "withdrawn_at": None}
    ctx.store.upsert("customer_style_profile", "customer_id", row)
    consent_rows = [r for r in ctx.store.read("consent") if r["customer_id"] == customer_id and r["purpose"] == "style_profile" and not r.get("withdrawn_at")]
    if not consent_rows:
        ctx.store.append("consent", [{"tenant_id": ctx.tenant.tenant_id, "customer_id": customer_id, "channel": ctx.channel, "purpose": "style_profile", "source": "chat", "ts": ctx.now_iso, "withdrawn_at": None}])
    if ctx.customer_id == customer_id:
        ctx.profile = row
    return {"customer_id": customer_id, "undertone": undertone, "depth": depth, "source": source, "confirmed": True}


def forget_style_profile(customer_id: str) -> dict:
    """Withdraw consent and delete the profile row. 'forget my skin tone' / 'delete my profile'."""
    ctx = current()
    profiles = [r for r in ctx.store.read("customer_style_profile") if r["customer_id"] != customer_id]
    ctx.store.write("customer_style_profile", profiles)
    consent_rows = ctx.store.read("consent")
    for r in consent_rows:
        if r["customer_id"] == customer_id and r["purpose"] == "style_profile" and not r.get("withdrawn_at"):
            r["withdrawn_at"] = ctx.now_iso
    ctx.store.write("consent", consent_rows)
    if ctx.customer_id == customer_id:
        ctx.profile = None
    return {"ok": True}


def _play(ctx, play_id: str) -> dict[str, Any] | None:
    rows = ctx.store.find("plays", play_id=play_id)
    if not rows:
        return None
    r = rows[-1]
    return json.loads(r["play_json"]) if isinstance(r.get("play_json"), str) else r.get("play_json")


def _consent_ok(ctx, customer_id: str) -> bool:
    rows = [r for r in ctx.store.read("consent") if r["customer_id"] == customer_id and r["purpose"] == "marketing" and r["channel"] == ctx.channel]
    return bool(rows) and not rows[-1].get("withdrawn_at")


def apply_offer(play_id: str, customer_id: str) -> dict:
    """Whether this customer may redeem an assortment_gap play now: arm, consent, frequency cap,
    no stacking. Same rules as agents/customer/tools.py::apply_offer -- the play_assignments,
    consent and offers tables are shared across specialists, not stylist-scoped."""
    ctx = current()
    play = _play(ctx, play_id)
    if not play or play.get("status") not in ("approved", "running"):
        return {"ok": False, "reason": "play is not active"}
    arm = next((a["arm"] for a in ctx.store.read("play_assignments") if a["play_id"] == play_id and a["customer_id"] == customer_id), None)
    if arm != "treated" or assign_arm(customer_id, play["holdout"]["seed"], float(play["holdout"]["fraction"])) != "treated":
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
    return {"ok": True, "reason": "eligible", "mechanic": play["mechanic"], "sku": play["target"]["sku"], "node_ids": play["target"]["node_ids"]}


async def place_order(customer_id: str, node_id: str, lines: list[dict], play_id: str | None = None) -> dict:
    """Place an apparel order through the same MCP order mock the grocery Customer Agent uses.
    lines: [{sku, qty}], priced here from the apparel catalogue. Only meaningful once an
    assortment_gap play has been approved for this customer; otherwise sold at list price with no
    play_id, same as a walk-in purchase."""
    ctx = current()
    offer = apply_offer(play_id, customer_id) if play_id else {"ok": False}
    priced = []
    for ln in lines:
        p = ctx.apparel.get(ln["sku"])
        if not p:
            return {"order_id": "", "total_inr": 0.0, "error": f"unknown sku {ln['sku']}"}
        priced.append({"sku": ln["sku"], "qty": int(ln["qty"]), "price": float(p["list_price"]), "discount": 0.0})
    base_dir = str(ctx.store.base.root) if hasattr(ctx.store, "base") else None
    async with Client(orders_server) as client:
        res = await client.call_tool("place_order", {"customer_id": customer_id, "node_id": node_id, "lines": priced, "play_id": play_id or None, "data_dir": str(ctx.store.root), "base_dir": base_dir, "ts": ctx.now_iso})
    data = res.structured_content or json.loads(res.content[0].text)
    data["lines"] = [{"sku": ln["sku"], "name": ctx.apparel[ln["sku"]]["name"], "qty": ln["qty"], "price": ln["price"], "discount": ln["discount"]} for ln in priced]
    if play_id and offer.get("ok"):
        for o in ctx.store.read("offers"):
            if o["customer_id"] == customer_id and o["play_id"] == play_id and not o.get("redeemed_at"):
                o["redeemed_at"] = ctx.now_iso
                ctx.store.upsert("offers", "offer_id", o)
    return {"order_id": data["order_id"], "total_inr": float(data["total_inr"]), "lines": data["lines"]}


TOOLS = [get_style_context, find_apparel, describe_item, suggest_pairings, set_style_profile, forget_style_profile, apply_offer, place_order]
