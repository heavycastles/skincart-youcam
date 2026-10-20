# SkinCart 💄 — selfie-to-basket beauty assistant on YouCam AI

**YouCam API Skin AI & eCommerce VTO Hackathon** · MIT · Built by heavycastles

**Live demo:** https://skincart-youcam.vercel.app (no login; press "Use sample photo")

Small cosmetics shops in Central Asia/CIS sell mostly through Telegram and Instagram DMs, and answer
"what should I buy for my skin?" by hand. **SkinCart** turns that into a bot:

1. Customer sends a selfie to the shop's **Telegram bot** (or the web page).
2. **YouCam AI Skin Analysis API** scores 12 concerns (acne, pores, wrinkles, texture, moisture, oiliness,
   redness, radiance, dark circles, spots, eye bags, firmness).
3. A matcher builds a routine from the shop's **catalog** (one product per category, weighted by need, always SPF).
4. Optional **YouCam AI Makeup VTO**: try the shop's lipstick / foundation on the same selfie.
5. "Order" → contact → saved as a **LeadFlow lead** (normalized, de-duplicated, scored, with `skin_profile` + `basket`)
   → **n8n** notifies the shop owner and sends a 14-day "re-scan your skin" follow-up.

## Screenshots (live YouCam API, 19 Oct 2026)

Taken from the running app with a real `YOUCAM_API_KEY` and a licensed stock portrait
(Jake Nackos / Unsplash, see `docs/stock-face/`).

| Skin snapshot | YouCam overlay masks |
|---|---|
| ![Skin analysis](docs/screenshots/03-skin-analysis.png) | ![Overlays](docs/screenshots/04-analysis-overlays.png) |
| **Makeup try-on (before / after)** | **Routine + basket** |
| ![Try-on](docs/screenshots/06-tryon-rose.png) | ![Routine](docs/screenshots/05-routine-basket.png) |
| **Upload + scan** | **Order saved as a lead** |
| ![Upload](docs/screenshots/02-upload-scanning.png) | ![Order](docs/screenshots/08-order-placed.png) |

## Architecture

```
Telegram bot ──┐
               ├──► FastAPI  POST /analyze · /tryon · /orders
Web demo ──────┘         │
                         ├─ YouCam client   File API → Skin Analysis → Makeup VTO
                         ├─ recommend.py + catalog.json
                         ├─ LeadStore (normalize / de-dupe / score + extra)
                         └─ n8n webhook (owner alert + day-14 re-scan)
```

Without `YOUCAM_API_KEY` (or with `YOUCAM_MOCK=1`) the client returns deterministic mock scores and a synthetic
SVG try-on preview — tests and demos run offline. Results are cached per image hash so re-scans cost 0 units, and
each photo is uploaded once: its `file_id` is reused by every try-on. `GET /sample.jpg` serves the licensed stock
portrait behind the "Use sample photo" button.

## Run

```bash
cp .env.example .env               # optional: YOUCAM_API_KEY, TELEGRAM_BOT_TOKEN
python -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
.venv/bin/pytest -q                # 19 tests (offline mock)
.venv/bin/python serve.py          # http://localhost:8080  (mock mode if no key)
docker compose up --build          # app :8080 + n8n :5678 (import n8n/skincart-orders.json)
```

Live mode: put `YOUCAM_API_KEY` (from https://yce.makeupar.com/api-console/en/api-keys/) into `.env`.
Smoke-test one real call: `YOUCAM_API_KEY=... PYTHONPATH=. python scripts/live_smoke.py selfie.jpg`
(use only your own or consented / licensed photos).

Telegram: set `TELEGRAM_BOT_TOKEN` and either register a webhook to `https://<host>/telegram/webhook`
(optionally with `TELEGRAM_WEBHOOK_SECRET`) or run long polling: `python -m app.telegram`.

Never commit `.env` or the API key.

## YouCam API usage (`app/youcam.py`)

| Step | Call |
|---|---|
| Auth | `Authorization: Bearer $YOUCAM_API_KEY`, server `https://yce-api-01.makeupar.com` |
| Upload | `POST /s2s/v2.0/file` → `file_id` + presigned `PUT` URL → upload bytes (key is never sent to the bucket) |
| Skin analysis | `POST /s2s/v2.0/task/skin-analysis` `{src_file_id, dst_actions[12 SD], format:"json"}` → poll `GET …/{task_id}` → `results.output[].ui_score` |
| Makeup VTO | `POST /s2s/v2.0/task/makeup-vto` `{src_file_id, effects:[lip_color/foundation], version:"1.0"}` → poll → result URL |

## API

| Method | Path | |
|---|---|---|
| GET | `/` | web demo |
| POST | `/analyze` | `{image_base64\|image_url}` → scores, basket, try-on SKUs |
| POST | `/tryon` | `{scan_id, sku}` → VTO image URL |
| POST | `/orders` | `{scan_id, name, phone\|email, skus}` → LeadFlow lead |
| GET | `/leads` | `/catalog` | `/healthz` | `/version` |
| POST | `/telegram/webhook` | Bot API updates |

## Layout

`app/youcam.py` client · `app/recommend.py` + `app/catalog.json` matcher · `app/leads.py` LeadFlow store
(extended with `extra`) · `app/telegram.py` bot · `app/static/index.html` web UI · `n8n/` workflow · `tests/`.

## Submission pack (local)

- Devpost write-up: [`SUBMISSION.md`](SUBMISSION.md)
- Demo script: [`docs/video-script.md`](docs/video-script.md)
- Slides PDF: [`docs/slides.pdf`](docs/slides.pdf) · cover: [`docs/cover.png`](docs/cover.png)
- Demo video draft (live run): [`docs/demo-live-draft.mp4`](docs/demo-live-draft.mp4) (1:42; script [`docs/video-script-live.md`](docs/video-script-live.md)). Older mock draft: `docs/demo-draft.mp4`
- Screenshots of the live run: [`docs/screenshots/`](docs/screenshots/)
- Live YouCam proof: [`docs/live-proof.md`](docs/live-proof.md) (2026-10-19, licensed Unsplash stock face)


## Preflight / publish (local)

```bash
./scripts/preflight_submit.sh
# VISIBILITY=private ./scripts/publish_github.sh
```

## Deploy demo (Vercel)

Hosted on Vercel (Python runtime, FastAPI preset): https://skincart-youcam.vercel.app

- `vercel.json` sets the FastAPI framework and `maxDuration: 60` for `app/main.py`; on Vercel the YouCam
  client stops polling at 45 s (`YOUCAM_TIMEOUT`) so a slow task fails cleanly instead of being killed.
- `.vercelignore` is an allow-list (app, requirements, VERSION, stock face); `.env`, `.venv`, tests, scripts
  and videos are never uploaded.
- `YOUCAM_API_KEY` is a sensitive project env var, `YOUCAM_MOCK=0`.
- Serverless instances don't share memory, so the browser re-sends the photo / `file_id` with `/tryon` and the
  skin profile with `/orders`; no second skin analysis is needed. Large phone photos are scaled to 2048 px
  in the browser to stay under the request-size limit.

```bash
vercel deploy --prod
curl https://skincart-youcam.vercel.app/healthz   # {"status":"ok","youcam":"live"}
```

`render.yaml` / `Dockerfile` remain as an alternative container deploy.

## License

Built on our earlier LeadFlow FastAPI service (lead normalize/de-dup/scoring); the YouCam client, recommender,
try-on, Telegram bot, web UI and n8n follow-up are new for this hackathon. Not medical advice. MIT License — see `LICENSE`.
