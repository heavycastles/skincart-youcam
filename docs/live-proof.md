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

## Notes

- Default app mode remains mock when `YOUCAM_MOCK=1` or no key (tests stay offline).
- Demo video `docs/demo-draft.mp4` is still the older mock draft — re-record for Devpost
  with this live path once Render + public video are ready.
- Do not commit `.env` or API keys. Mask URLs in the JSON expire (~2h signed).
