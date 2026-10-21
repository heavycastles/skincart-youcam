# YouCam live API proof — SkinCart

**Status:** SUCCESS (first live call)  
**When:** 2026-10-19 ~16:43:25 MSK (Europe/Moscow)  
**Elapsed:** ~12 seconds end-to-end (File upload + skin-analysis poll + makeup-vto poll)  
**Mode badge:** `live` (`YOUCAM_MOCK` unset; key present in local `.env`, not committed)

## Image

- Path: [`docs/stock-face/stock-face.jpg`](stock-face/stock-face.jpg)
- Attribution / license: [`docs/stock-face/ATTRIBUTION.txt`](stock-face/ATTRIBUTION.txt)
- Source: Unsplash photo by **Jake Nackos** (@jakenackos), Unsplash License  
  https://unsplash.com/photos/IF9TK5Uy-KI
- Local file is a face-centered crop so the face occupies >60% of image width
  (YouCam Skin Analysis requirement; see Perfect Corp file specs).

## Endpoints exercised

| Step | Endpoint | Result |
|------|----------|--------|
| Upload | `POST /s2s/v2.0/file` + presigned PUT | OK → `file_id` |
| Skin analysis | `POST /s2s/v2.0/task/skin-analysis` + poll GET | OK — 15 output items |
| Makeup VTO | `POST /s2s/v2.0/task/makeup-vto` (SKU `SC-LIP-10`) + poll GET | OK — result JPEG URL on `yce-us.s3-accelerate.amazonaws.com` |

Base URL: `https://yce-api-01.makeupar.com` · Auth: Bearer (key not logged).

## Skin analysis summary (ui_score, higher = healthier)

| Concern | ui_score |
|---------|----------|
| oiliness | 95 |
| radiance | 93 |
| redness | 88 |
| age_spot | 85 |
| texture | 85 |
| firmness | 78 |
| eye_bag | 76 |
| pore | 70 |
| (+ wrinkle, dark_circle_v2, acne, moisture, all, skin_age, resize_image) | see JSON |

Full sanitized response (signed S3 query strings stripped):  
[`docs/live-proof-response.json`](live-proof-response.json)

## Script

```bash
PYTHONPATH=. .venv/bin/python scripts/live_smoke.py docs/stock-face/stock-face.jpg
```

Earlier attempts with the uncropped Unsplash download returned `error_src_face_too_small`
(face width must be >60% of image width). After the face crop, both skin-analysis and
makeup-vto succeeded on the first valid upload.

## Live web UI run (screenshots + video source)

**When:** 2026-10-19 ~20:45 MSK · server `uvicorn app.main:app` with the key from local `.env`, `YOUCAM_MOCK` unset
(badge "YouCam API · LIVE"). Browser: Chrome driven by Playwright on a private virtual display.

| Step | Result |
|------|--------|
| "Use sample photo" → `POST /analyze` | 1 File API upload + 1 `skin-analysis` task, ~5 s. Same scores as the 16:43 smoke run (pore 70, moisture 73, eye_bag 76, wrinkle 77, firmness 78 … acne 99); skin score 84; focus areas visible pores / dryness / puffy eyes (mild) |
| Overlay masks | 3 mask images from the API response shown under "Where YouCam sees it" |
| Try-on `SC-LIP-10` (Velvet Matte Rose) | 1 `makeup-vto` task, ~7 s, reused the scan's `file_id` (no second upload) |
| Try-on `SC-LIP-11` (Glossy Tint Coral) | 1 `makeup-vto` task, ~7 s |
| Order | Lead #1, 7 items, $114.00, skin profile attached |
| Total | 16 HTTP requests to the YouCam API (incl. presigned PUT and status polls); `/version` → `api_calls: 16` |

Outputs: `docs/screenshots/*.png` (real page screenshots) and `docs/demo-live-draft.mp4` (built from the screen
recording of this run). Later re-reads of the same photo were served from the in-process cache (0 extra requests).

Fixes found by the live data (in code, with tests): the response's helper items `all` / `skin_age` /
`resize_image` (ui_score 0) are no longer treated as concerns; scores below 80 now get a "mild" tier so a healthy
face still gets a useful routine.

## Notes

- Default app mode remains mock when `YOUCAM_MOCK=1` or no key (tests stay offline).
- The older `docs/demo-draft.mp4` is the mock draft; the live draft is `docs/demo-live-draft.mp4`.
- Do not commit `.env` or API keys. Signed result/mask URLs expire and are not stored in the repo.

## Hosted demo run (Vercel) — 2026-10-21 ~00:30 MSK

URL: https://skincart-youcam.vercel.app (`/healthz` → `{"status":"ok","youcam":"live"}`)

Flow on the deployed app with the licensed stock face (`/sample.jpg`):

| Step | YouCam HTTP requests | Time (client) | Result |
|---|---|---|---|
| `/analyze` (File API upload + Skin Analysis task + status polls) | 6 | ~6.2 s | skin score 84, focus: visible pores, dryness, puffy eyes |
| `/tryon` `SC-LIP-10` (Makeup VTO task + polls, reusing the file_id) | 5 | ~8.1 s | rendered image (signed URL, not stored) |
| `/orders` | 0 | <1 s | lead created with the skin profile |

Paid tasks: 1 skin analysis + 1 makeup VTO.

## Judge audit run (Vercel) — 2026-10-21 ~16:40 MSK

Edge cases checked on https://skincart-youcam.vercel.app after the input-handling update:

| Case | Result |
|---|---|
| Uncropped photo (face ~20% of width), sent directly to `/analyze` | 422 "Move closer: your face should fill most of the photo…" (`error_src_face_too_small`), ~4 s |
| Photo without a face | 422 "We couldn't find a face in this photo…" (`error_no_face`), ~3.7 s |
| Same uncropped photo through the web framing step (zoom 2.5×) | Skin Analysis OK: 6 requests, 5.7 s, skin score 85 (visible pores, dryness, puffy eyes) |
| Makeup VTO `SC-LIP-10` Rose on that scan | rendered, 8 requests, ~15 s |
| Text file / WebP / 300×457 JPEG / empty basket / bad email / invalid JSON | plain-language 415/422 messages, no YouCam call |
| 375 px viewport | no horizontal scroll, 0 JS errors |

Paid tasks in this run: 3 skin analyses (2 intentionally rejected by YouCam) + 1 makeup VTO.

## Demo video v2 recording (Vercel) — 2026-10-22 ~00:50 MSK

Recorded `docs/demo-v2.mp4` on https://skincart-youcam.vercel.app with the sample photo (licensed stock face):

| Step | YouCam HTTP requests | Time (client) | Result |
|---|---|---|---|
| `/analyze` (File API upload + Skin Analysis task + polls) | 6 | 5.8 s | skin score 84: visible pores 70 · dryness 73 · puffy eyes 76 |
| `/tryon` `SC-LIP-10` Rose (reuses file_id) | 6 | ~10.3 s | rendered |
| `/tryon` `SC-LIP-11` Coral (reuses file_id) | 5 | ~8.5 s | rendered |
| `/orders` (Demo Shopper · +1 000 000 0000 · demo@example.com) | 0 | <1 s | receipt: lead #1 · score 65 · 7 items · $114.00 |

17 YouCam requests in that session. Two more takes of the same photo were served from the in-memory cache
(0 requests, "Loaded from cache · 0 units used"); one of them supplies the checkout and framing scenes of the video.
Paid tasks in this run: 1 skin analysis + 2 makeup VTO.
