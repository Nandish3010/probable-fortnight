"""Three-CSV ingestion: a partner's products, batches and sales -> a LocalStore tenant -> Sense.

    python -m data.ingest --products products.csv --batches inventory_batches.csv --sales sales.csv \
        --tenant config/tenant.<name>.toml --out .local/data-<name> [--nodes nodes.csv] [--inbound inbound.csv]

See data/ingest/contract.py for the columns and docs/scale.md for the contract.
"""
