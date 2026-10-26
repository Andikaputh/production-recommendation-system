# RASA: single-merchant pilot runbook

[Bahasa Indonesia](README.id.md). The product defaults to **English**. Use the persistent **English / Bahasa Indonesia** selector in the kit builder; language changes preserve your custom goal, budget, and current basket. Preset goals, labels, currency formatting, explanations, recovery suggestions, and local summary labels follow the selected language. Merchant product names and custom user text are preserved. The optional technical model demo remains in English.

First-time visitors see a welcome popup and an optional four-step guide: scenario, required needs, budget, and results. Skip, close, Escape, or finish dismisses it and remembers the choice in this browser. Use **How to use / Cara pakai** to replay it. The guide can switch language, keeps keyboard focus inside the popup, restores focus when closed, and preserves shopping inputs. If browser storage is disabled, dismissal still works but cannot be remembered after a reload.

Status: local portfolio and limited-pilot implementation, not a validated business. No merchant, interviews, transactions, or testimonials are claimed.

## Start in this order

1. Install Python 3.11/3.12 and Node 22+. Run `pip install -e ".[dev]"`, `npm ci --prefix frontend`, and `npm run build --prefix frontend`.
2. Configure a **separate new pilot database**, a random admin secret, the merchant ID, costs, and CORS. Keep secrets out of Git and the frontend. The database parent directory must exist and be writable.
3. With that database URL already configured, run `python scripts/seed_db.py --no-events` once to provide categories and isolated synthetic demo items. Do not reseed an imported pilot database: default seeding drops tables. Start one process with `uvicorn apps.api.main:app --port 8000`. Use HTTPS and restricted network access at the pilot location.
4. Prepare a complete catalog snapshot from the template. Validate with a dry run, fix all row/field errors, then apply. Start with synthetic samples; actual merchant data requires permission and explicit real-data labeling.
5. Check `/readyz`, build a kit, replace an item, accept, and prepare a summary. Confirm that synthetic sessions do not enter `source=pilot` analytics.
6. Agree on responsibilities, consent, retention, catalog refreshes, costs, and continue/stop criteria before opening a real participant pilot. The merchant must review the local summary before ordering through its own process.

```dotenv
RASA_MODE=pilot
RASA_ENV=production
RASA_DATABASE_URL=sqlite:///D:/rasa-pilot/rasa.db
RASA_PILOT_MERCHANT=pilot-store
RASA_PILOT_MERCHANT_NAME=Agreed merchant name
RASA_ADMIN_TOKEN=generate-a-long-random-secret-locally
RASA_CATALOG_TTL_HOURS=24
RASA_CORS_ORIGINS=http://localhost:8000
RASA_HANDOFF_LABEL=Merchant ordering process (manual)
# Optional: unset means unknown shipping; 0 means agreed free shipping.
# RASA_PILOT_SHIPPING_IDR=10000
```

## Catalog import and freshness

Use `data/templates/pilot-catalog.csv`; `pilot-catalog-synthetic.csv` is entirely synthetic. The example has fixed timestamps and will expire. Only update timestamps after checking the underlying data; do not refresh them simply to bypass validation.

`POST /api/v1/pilot/catalog/import` requires `Authorization: Bearer <admin token>` and JSON `{ "csv_text": "...", "synthetic": true, "dry_run": true }`. Set `dry_run=false` only after validation succeeds. The body limit is 64 KB, with up to about 60 KB of CSV. Required columns: product_id, product_name, category_id, merchant_id, price, stock, updated_at. Categories must already exist. Prices are positive whole rupiah; stock is a nonnegative integer; IDs must be unique and cannot overwrite another merchant's SKU. Errors identify the row, field, and remedy. Invalid imports write nothing.

Imports replace the complete merchant snapshot: omitted SKUs are retired, not deleted from history. Batches store a SHA-256 checksum, import time, and synthetic flag in the database. Both the batch and each row have a 24-hour default TTL. Timestamps require an ISO 8601 timezone; future timestamps beyond five minutes are rejected. Imported ratings are unavailable rather than invented; the primary pilot flow does not require a rating.

Local operator alternative, using OS access to the database:

```bash
python scripts/import_pilot_catalog.py data/templates/pilot-catalog-synthetic.csv
python scripts/import_pilot_catalog.py data/templates/pilot-catalog-synthetic.csv --apply
```

`--real` declares permitted real merchant data and requires `RASA_MODE=pilot`. The CLI does not send data to an external service. Never use the synthetic sample with `--real`.

## Basket and measurement API

All mission requests use a random `X-Session-ID` of at least 16 characters. Treat it as a session secret, not a verified identity.

| Endpoint under `/api/v1/pilot` | Purpose |
| --- | --- |
| `GET /config` | Mode, merchant, shipping, TTL, local-only handoff |
| `POST /missions` | Client-generated mission_id, mission, preferences; same ID and input are idempotent |
| `GET /missions/{id}` | Restore a stored mission for the same session |
| `POST /missions/{id}/replace` | Current revision, product_id, replacement_id |
| `POST /missions/{id}/accept` | Recheck the current revision before acceptance |
| `POST /missions/{id}/handoff` | Prepare local text after accepting the same revision; returns sent=false |
| `GET /analytics?source=pilot` | Admin-only aggregate funnel; source can be demo, test, or pilot |

Every replacement checks the entire basket and increments its revision. Acceptance of an older revision is rejected. Before accept/handoff, prices, shipping, availability, stock quantity, freshness, required categories, exclusions, and budget are rechecked against the database. Changed prices or fees require rebuilding and review. There is no live stock reservation.

Unknown shipping produces `total=null` and `final_budget_confirmed=false`. Configured fixed shipping is reserved before optimization. The fixed-fee setup assumes no other charges; the merchant must confirm that assumption. No logistics integration, checkout, payment, message, or order submission is implemented.

Mission and event data survive server restarts. The browser restores the current mission while the same tab session remains available. Closing the tab loses its session secret. Data sources remain separate: synthetic imports are demo data even in pilot mode. UI acceptance and prepared summaries are not confirmed orders or revenue. See [measurement definitions](measurement.md) for denominators, missing metrics, and experiment planning; [business validation materials](business-validation.md) include local Indonesian interview/usability scripts and explicit assumptions.

## Operations and limits

Use a persistent database volume, one worker, and coordinated imports for this pilot. Docker Compose has a named volume; do not delete it. Free hosting without persistent disk is demo-only. `/health` is diagnostic; `/readyz` returns 503 when required dependencies or the pilot catalog are not ready. Configure backups and test restoring the database with the application stopped before a real pilot.

Admin tokens protect imports and analytics. Legacy demo catalog/mission/recommendation/feedback endpoints return 409 in pilot mode to keep data sources separate; use `/api/v1/pilot`. Payload validation includes actual body size and non-finite numeric inputs. The rate limiter is process-local. The UI shows an explicit API error instead of inventing a pilot result; labeled static examples remain in the technical demo.

Outstanding production work includes multi-instance/concurrent-import testing, direct inventory reservations, verified order reconciliation, merchant authentication and tenant isolation, formal schema migrations, automated backups/retention, and centralized monitoring. A proposed 30-day retention period requires participant/merchant agreement; deletion is not automated. Never enter personal identities, addresses, or phone numbers in free-text goals.

No public deployment was performed. Read the [verification report](../reports/pilot-verification.md) for tests actually run and remaining limits.
