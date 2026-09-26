# Taal: one command decides "demo-ready". Green `make verify` is the only definition of done.
SHELL := /bin/bash
export TAAL_MODEL_BACKEND ?= stub
export TAAL_DATA_DIR ?= .local/data
export TAAL_TENANT_CONFIG ?= config/tenant.demo.toml
# The demo tenant is a snapshot frozen at 2026-09-12 (data/generator AS_OF); pin the API clock to
# it so play windows and the approve -> re-forecast beat do not go stale as real days pass.
export TAAL_NOW ?= 2026-09-12T03:30:00Z

.PHONY: feedback-summary live-test setup verify secrets lint schemas generate fixtures mocks openapi sense measure unit sql agents api-test web-test docs status demo api web eval deploy clean

setup:            ## install python + web deps
	uv sync --group dev
	cd web && npm ci --no-audit --no-fund

verify: secrets lint schemas generate unit sql agents api-test web-test docs status  ## full harness; stops at first red
	@echo "VERIFY: green"

secrets:          ## no credentials, no attribution trailers, no raw data
	@python3 harness/checks/secrets.py

lint:
	uv run ruff check .

schemas:          ## schema validity, golden/mutated plays, model<->schema sync
	uv run pytest tests/contract -q

generate:         ## seeded tenant -> Sense -> demo plays into $(TAAL_DATA_DIR); determinism checked in tests
	uv run python -m data.generator --out $(TAAL_DATA_DIR) --seed 20260912
	uv run python -m jobs.sense
	uv run python -m harness.seed_plays

fixtures:         ## rebuild committed fixtures (golden plays, mutations, golden runs, evalsets) from the tenant
	uv run python -m harness.build_fixtures

mocks:            ## regenerate web/mocks/*.json from the API (after make generate)
	uv run python -m harness.build_mocks

openapi:          ## regenerate docs/openapi.yaml from the FastAPI app
	uv run python -m harness.openapi

sense:            ## nightly job locally
	uv run python -m jobs.sense

backtest:         ## rolling-origin forecast backtest on the sample slice -> eval_forecast
	uv run python -m jobs.sense.backtest

measure:          ## measure job locally
	uv run python -m jobs.measure

unit:             ## gate, estimator, assignment, sellby (unit + property tests)
	uv run pytest tests/unit -q

sql:              ## DDL + assertions on a local DuckDB built from generated data
	uv run pytest tests/sql -q

agents:           ## stub-mode planner evalset + scripted customer conversations
	uv run pytest tests/agents -q

api-test:         ## FastAPI contract tests against openapi.yaml
	uv run pytest tests/api -q

web-test:         ## typecheck + Playwright judge-mode tests in mock mode (skips if web/node_modules missing)
	@if [ -d web/node_modules ]; then cd web && npm run typecheck && npm test -- --reporter=line; else echo "web-test: skipped (run make setup)"; fi

docs:             ## README/docs lint: links, quick-start card first, required sections
	@python3 harness/checks/docs_lint.py

status:           ## regenerate STATUS.md from checklists + test results
	uv run python -m harness.status

feedback-summary: ## real practitioner feedback -> eval/raw/feedback_summary_<date>.{json,md} (TAAL_FEEDBACK_STORE picks the store)
	uv run python -m harness.feedback_summary

eval-table:       ## regenerate eval/evaluation_table.md from eval/evaluation.md + eval/raw/ (never typed by hand)
	uv run python -m harness.build_eval_table

api:              ## run the local API against fixtures
	uv run uvicorn services.api.main:app --port 8080 --reload

web:
	cd web && npm run dev

live-test:        ## persona walkthrough against a running `make api` + `make web` (screenshots in eval/runs/screens)
	cd web && npx playwright test -c playwright.live.config.ts

sweep:            ## every API endpoint, one line each, against API (default local; pass API=https://... for Cloud Run)
	uv run python -m harness.sweep_live $(or $(API),http://localhost:8080)

demo: generate    ## local demo = api + web against generated data
	@echo "Run 'make api' and 'make web' in two terminals; open http://localhost:3000"

eval:             ## planner evalset (stub or vertex per TAAL_MODEL_BACKEND)
	uv run python -m harness.run_evals

deploy:           ## gcloud scripts under infra/ (require GOOGLE_CLOUD_PROJECT)
	@bash infra/deploy.sh

clean:
	rm -rf .local .pytest_cache .ruff_cache .hypothesis
