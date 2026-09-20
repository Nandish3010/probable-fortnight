import json

from agents.gate.store import LocalStore
from agents.stylist.colour import family_of
from data.generator.apparel import GARMENTS, PLANTED_APPAREL
from data.generator.catalog import FORBIDDEN_WORDS


def test_manifest_counts_and_stylist_anchor(base_store: LocalStore):
    m = json.loads((base_store.root / "manifest.json").read_text())
    assert m["counts"]["apparel_products"] >= 300
    assert m["planted"]["stylist_anchor"] == {"sku": "APP-KURTA-MUSTARD-W", "node_id": "DS-07"}


def test_every_garment_type_has_at_least_four_skus_and_every_role_and_section_present(base_store: LocalStore):
    products = base_store.read("apparel_products")
    by_type: dict[str, int] = {}
    roles: set[str] = set()
    sections: set[str] = set()
    for p in products:
        by_type[p["garment_type"]] = by_type.get(p["garment_type"], 0) + 1
        roles.add(p["role"])
        sections.add(p["section"])
    for garment in GARMENTS:
        assert by_type.get(garment, 0) >= 4, garment
    assert roles == {"top", "bottom", "dress", "layer", "footwear", "accessory"}
    assert sections == {"women", "men", "unisex"}


def test_planted_apparel_rows_present_with_stated_roles_and_colours(base_store: LocalStore):
    products = {p["sku"]: p for p in base_store.read("apparel_products")}
    for sku, spec in PLANTED_APPAREL.items():
        assert sku in products, sku
        row = products[sku]
        assert row["garment_type"] == spec["garment_type"]
        assert row["colour_family"] == family_of(spec.get("metal") or spec["colour"])


def test_apparel_stock_only_at_dark_stores(base_store: LocalStore):
    nodes = {n["node_id"]: n for n in base_store.read("nodes")}
    stock = base_store.read("apparel_stock")
    assert stock
    for row in stock:
        assert nodes[row["node_id"]]["type"] == "dark_store"


def test_black_blazer_zero_at_ds07_and_in_stock_at_ds04(base_store: LocalStore):
    stock = [r for r in base_store.read("apparel_stock") if r["sku"] == "APP-BLAZER-BLACK-U"]
    assert not any(r["node_id"] == "DS-07" for r in stock)
    assert any(r["node_id"] == "DS-04" and r["qty_on_hand"] > 0 for r in stock)


def test_every_apparel_colour_resolves_and_no_forbidden_words(base_store: LocalStore):
    for p in base_store.read("apparel_products"):
        assert family_of(p.get("metal") or p["colour"]) is not None, p
        low = p["name"].lower()
        assert not any(w in low for w in FORBIDDEN_WORDS), p


def test_apparel_generation_does_not_perturb_grocery_tables(base_store: LocalStore):
    """The apparel RNG stream is separate from the grocery generator's; grocery row counts must
    match the pre-apparel values exactly."""
    m = json.loads((base_store.root / "manifest.json").read_text())
    assert m["counts"]["products"] == 300
    assert m["counts"]["nodes"] == 16
    assert m["counts"]["customers"] == 4000
