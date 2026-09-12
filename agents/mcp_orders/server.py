"""In-process MCP order mock (mcp 2.x MCPServer, the renamed FastMCP) (DECISIONS §5.5): the Customer Agent's `place_order` goes through
MCP so the order system is a swappable endpoint, not a function in the agent.

Two transports:
  * in-process (default): `place_order_impl` is called through the FastMCP server object over an
    in-memory MCP session (tests/agents/test_mcp_orders.py) or directly by the ADK FunctionTool;
  * stdio: `python -m agents.mcp_orders` serves the same tool for `McpToolset` when
    TAAL_MCP_TRANSPORT=stdio (used against a real order system later).
"""
from __future__ import annotations

import hashlib
import os
from datetime import UTC, datetime
from typing import Any

from mcp.server.mcpserver import MCPServer

from agents.gate.store import LocalStore, OverlayStore

server = MCPServer("taal-orders")


def _store(data_dir: str | None, base_dir: str | None = None) -> LocalStore:
    if base_dir and data_dir:
        return OverlayStore(base_dir, data_dir)
    return LocalStore(data_dir or os.environ.get("TAAL_DATA_DIR", ".local/data"))


def place_order_impl(customer_id: str, node_id: str, lines: list[dict[str, Any]], play_id: str | None, data_dir: str | None = None, ts: str | None = None, base_dir: str | None = None) -> dict[str, Any]:
    """Write orders + order_lines. Each line: {sku, qty, price, discount}. Deterministic order ids.
    data_dir/base_dir select the store (a judge-mode sandbox is an overlay over the base tenant)."""
    store = _store(data_dir, base_dir)
    ts = ts or datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
    existing = len(store.find("orders", customer_id=customer_id))
    order_id = "ORD-" + hashlib.sha256(f"{customer_id}|{existing}|{ts}".encode()).hexdigest()[:10].upper()
    tenant = (store.read("nodes") or [{"tenant_id": "unknown"}])[0]["tenant_id"]
    total = 0.0
    rows = []
    for i, ln in enumerate(lines, start=1):
        qty, price, disc = int(ln["qty"]), float(ln["price"]), float(ln.get("discount") or 0.0)
        total += qty * (price - disc)
        rows.append({"tenant_id": tenant, "order_id": order_id, "line_no": i, "customer_id": customer_id, "node_id": node_id, "sku": ln["sku"], "qty": qty, "price": price, "discount": disc, "play_id": play_id, "ts": ts})
    store.append("orders", [{"tenant_id": tenant, "order_id": order_id, "customer_id": customer_id, "node_id": node_id, "channel": "web_chat", "ts": ts, "total_inr": round(total, 2)}])
    store.append("order_lines", rows)
    return {"order_id": order_id, "total_inr": round(total, 2)}


@server.tool()
def place_order(customer_id: str, node_id: str, lines: list[dict[str, Any]], play_id: str | None = None, data_dir: str | None = None, base_dir: str | None = None, ts: str | None = None) -> dict[str, Any]:
    """Place an order for a customer at a node. lines: [{sku, qty, price, discount}]."""
    return place_order_impl(customer_id, node_id, lines, play_id, data_dir, ts, base_dir)


def main() -> None:
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
