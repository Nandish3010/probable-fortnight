# Bring your own data

Moved from the README.

- **Three files**: `products.csv`, `inventory_batches.csv`, `sales.csv` (columns in [`scale.md`](scale.md#the-three-csv-ingestion-contract); example in [`../data/samples/`](../data/samples/)); `nodes.csv` and `inbound.csv` are optional.
- **One command**: `uv run python -m data.ingest --products products.csv --batches inventory_batches.csv --sales sales.csv --tenant config/tenant.<name>.toml --out .local/data-<name>` (copy `config/tenant.demo.toml` to set your sell-by rule, margin floors and thresholds). It flags every lot under your online sell-by rule, with rupees at stake by gap type; errors name the file, line and column; nothing leaves the machine.
- **Pilot**: `TAAL_DATA_DIR=.local/data-<name> TAAL_TENANT_CONFIG=config/tenant.<name>.toml make api` serves those gaps over the same API. Planning a play returns `no_play` until customer and consent tables exist, because the three files carry no audience; that is the pilot's first step ([`pilot.md`](pilot.md)).
