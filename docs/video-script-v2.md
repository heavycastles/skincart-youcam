# SkinCart — demo video v2

`docs/demo-v2.mp4` · 2:03 · 1920×1080 · 30 fps · burned-in subtitles (`docs/demo-v2.srt`) · cover `docs/demo-v2-cover.png`

Recorded from the production deployment https://skincart-youcam.vercel.app on 22 Oct 2026 (live YouCam API).
Face: licensed stock portrait (Jake Nackos / Unsplash License, `docs/stock-face/`), the app's "Use sample photo"; the
framing scene uses the uncropped original of the same Unsplash photo. Order uses test details only
(Demo Shopper · +1 000 000 0000 · demo@example.com).
Voice: text-to-speech (natural en-US voice). Music: synthesized for this video (no third-party tracks).

Live run: 1 File API upload + 1 Skin Analysis task (5.8 s, skin score 84: visible pores 70 · dryness 73 · puffy eyes 76)
+ 2 Makeup VTO tasks (Rose ~10 s, Coral ~8.5 s), 17 YouCam HTTP requests in total. The checkout and framing scenes
come from a second take of the same scan, served from the in-memory cache (0 extra YouCam units; labelled on screen).

| Time | Scene | Narration |
|---|---|---|
| 0:00 | Hook: scanning frame → YouCam overlay masks → before/after lipstick try-on → title "SkinCart · Selfie in. Basket out." | One selfie. A whole skincare routine, and a lipstick you've already tried on. This is SkinCart, built on the YouCam AI APIs. |
| 0:09 | Problem: shop chat illustration | Shoppers can't tell what actually suits their skin. So they message the shop, and the owner guesses by hand, one chat at a time. |
| 0:17 | Live: Use sample photo → File API upload + Skin Analysis (real time, "Analyzed in 5.8 s · live YouCam API") | This is the live app. One tap on the sample photo, a licensed stock portrait. It goes up to the YouCam File API, and straight into Skin Analysis. |
| 0:27 | Skin snapshot: score ring 84, focus zones | Under six seconds later: twelve real scores. A skin score of eighty-four, with three focus areas: visible pores, dryness, and puffy eyes. |
| 0:37 | 12 concern tiles + YouCam overlay masks | Every concern gets a score, and these overlays come straight from YouCam, showing exactly where it sees each one. |
| 0:44 | Routine from the shop catalog (5 steps, SPF) | Each focus area maps to the shop's own catalog. One product per step, always with SPF. |
| 0:51 | Makeup VTO Rose, real-time ~10 s render, before/after slider | Now the fun part. Pick a lipstick, and YouCam Makeup VTO renders it on the same photo, reusing the uploaded file. That's a real ten-second render. Drag to compare, before and after. |
| 1:06 | Makeup VTO Coral (render wait at 2×, labelled) | Switch to the coral gloss, and it renders again. Every shade you try lands in the basket. |
| 1:14 | Checkout: 7 items $114 → test name/phone/email → "Order received · Lead #1 · score 65" | Happy with it? Name, phone or email, and place the order. These are test details. The basket becomes a scored lead, with the skin profile attached, straight into the shop's lead inbox. |
| 1:27 | Own selfie: framing step (zoom + drag into the oval), no YouCam call | Using your own selfie? YouCam needs the face to fill most of the frame. So SkinCart lets you zoom and frame it first, before a single call is spent. |
| 1:36 | How it uses YouCam: POST /s2s/v2.0/file → task/skin-analysis (src_file_id, poll) → task/makeup-vto (same file_id, poll) | Under the hood, it's three YouCam calls. The File API uploads the photo once and returns a file ID. A Skin Analysis task scores twelve concerns, and we poll until it's done. Then Makeup VTO tasks reuse that same file ID, so there's no second upload. And results are cached per image. |
| 1:55 | Close: skincart-youcam.vercel.app | SkinCart. Selfie in, basket out. Try it live at skincart-youcam dot vercel dot app. |

Everything is real time except the coral render wait (2×, labelled on screen); calm moments are held with slow zooms
on the last frame. No repository URL is shown (the repo is not public yet).

Checks done on the final file: OCR of every frame at 0.5 s (246 frames) — only the demo domain and example.com appear,
no personal names/emails, localhost, keys or signed URLs; speech-to-text matches the narration line by line, no extra
speech; container metadata is the title only.
