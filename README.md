# SkinCart 💄 — selfie-to-basket beauty assistant on YouCam AI

Small cosmetics shops in Central Asia/CIS sell mostly through Telegram and Instagram DMs, and answer
"what should I buy for my skin?" by hand. **SkinCart** turns that into a bot:

1. Customer sends a selfie to the shop's **Telegram bot** (or the web page).
2. **YouCam AI Skin Analysis API** scores 12 concerns (acne, pores, wrinkles, texture, moisture, oiliness,
   redness, radiance, dark circles, spots, eye bags, firmness).
3. A matcher builds a routine from the shop's **catalog** (one product per category, weighted by need, always SPF).
4. Optional **YouCam AI Makeup VTO**: try the shop's lipstick / foundation on the same selfie.
5. "Order" → contact → saved as a **LeadFlow lead** (normalized, de-duplicated, scored, with `skin_profile` + `basket`)
   → **n8n** notifies the shop owner and sends a 14-day "re-scan your skin" follow-up.

## Run
```bash
python -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
.venv/bin/python serve.py            # http://localhost:8080  (mock mode, no key needed)
.venv/bin/pytest -q && .venv/bin/ruff check .
docker compose up --build            # app :8080 + n8n :5678 (import n8n/skincart-orders.json)
```
Live mode: put `YOUCAM_API_KEY` (from https://yce.makeupar.com/api-console/en/api-keys/) into `.env`.
Smoke-test one real call: `YOUCAM_API_KEY=... PYTHONPATH=. python scripts/live_smoke.py selfie.jpg`.

Telegram: set `TELEGRAM_BOT_TOKEN` and either register a webhook to `https://<host>/telegram/webhook`
(optionally with `TELEGRAM_WEBHOOK_SECRET`) or run long polling locally: `python -m app.telegram`.

## YouCam API usage (`app/youcam.py`)
| Step | Call |
|---|---|
| Auth | `Authorization: Bearer $YOUCAM_API_KEY`, server `https://yce-api-01.makeupar.com` |
| Upload | `POST /s2s/v2.0/file` → `file_id` + presigned `PUT` URL → upload bytes (key is never sent to the bucket) |
| Skin analysis | `POST /s2s/v2.0/task/skin-analysis` `{src_file_id, dst_actions[12 SD], format:"json"}` → poll `GET …/{task_id}` → `results.output[].ui_score` |
| Makeup VTO | `POST /s2s/v2.0/task/makeup-vto` `{src_file_id, effects:[lip_color/foundation], version:"1.0"}` → poll → result URL |

Unit budget: results are cached per image hash, so re-scans of the same photo and repeated try-ons cost 0 units.
Mock mode (no key or `YOUCAM_MOCK=1`) returns deterministic scores from the image hash — tests and demo run offline.

## API
`GET /` web demo · `POST /analyze {image_base64|image_url}` · `POST /tryon {scan_id, sku}` ·
`POST /orders {scan_id, name, phone|email, skus}` · `GET /leads` · `GET /catalog` · `POST /telegram/webhook` ·
`GET /healthz` · `GET /version`

## Layout
`app/youcam.py` client · `app/recommend.py` + `app/catalog.json` matcher · `app/leads.py` LeadFlow store (reused,
extended with `extra`) · `app/telegram.py` bot · `app/static/index.html` web UI · `n8n/` workflow · `tests/`.

Built on our earlier LeadFlow FastAPI service (lead normalize/de-dup/scoring); the YouCam client, recommender,
try-on, Telegram bot, web UI and n8n follow-up are new for this hackathon. Not medical advice. MIT License.
