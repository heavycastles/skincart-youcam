# SkinCart — demo video v4

`docs/demo-v4.mp4` · 2:30 · 1920×1080 · 30 fps · burned-in subtitles (`docs/demo-v4.srt`) in a band below the app window (they never cover buttons) · cover `docs/demo-v4-cover.png`

Recorded from the production deployment https://skincart-youcam.vercel.app on 23 Oct 2026 ~08:31 MSK (live YouCam API), in one take, on the current UI (basket remove buttons, lip try-ons that replace each other, one foundation at most, cached repeat previews).
Face: licensed stock portrait (Jake Nackos / Unsplash License, `docs/stock-face/`), the app's “Use sample photo”. Order uses test details only.
Music: synthesized for this video (no third-party tracks).

Live run (one session, 30 YouCam HTTP requests, **41 units**; balance 687 → 646): 1 File API upload + Skin Analysis (5.8 s, score 84) · Skin Simulation (5.1 s, 4 units) · Facial Color Tones (7.5 s, 20 units → 180 Natural, ΔE 6.1) · Makeup VTO foundation 180 Natural (1) · Makeup VTO lip Petal Nude (1) · Makeup VTO lip Coral (1) · re-tap Petal Nude (cached, 0).
Speed-ups (all labelled on screen): Skin Simulation and Facial Color Tones waits 2×, the three VTO render waits 3×, short non-wait tails of the try-on scenes 1.3–1.6×; everything else is real time. No repository URL is shown (the repo is not public).
Previous cut: `docs/demo-v3.mp4` (2:10, 22 Oct) — predates the basket remove button and lip swap.

| Time | Scene | Narration |
|---|---|---|
| 0:00 | Hook: scanning frame → skin snapshot → shade match → Skin Simulation before/after → title “SkinCart · Selfie in. Basket out.” | One selfie. Your skin, your shade, and a preview of what the basket will do. This is SkinCart, built on four YouCam AI APIs. |
| 0:09 | Problem: shop chat illustration | Shoppers can't tell what suits their skin, and a wrong foundation shade is one of the top reasons it gets sent back. So they ask in chat, and the owner guesses by hand. |
| 0:18 | Live: Use sample photo → File API upload + Skin Analysis, real time (“Analyzed in 5.8 s · live YouCam API”) | This is the live app. One tap on the sample photo, a licensed stock portrait. It's uploaded once to the YouCam File API, and Skin Analysis starts. |
| 0:30 | Skin snapshot: score 84, focus areas visible pores · dryness · puffy eyes, 12 concern tiles, YouCam overlay masks | About six seconds later: twelve real scores, a skin score of eighty-four, and YouCam's own overlays showing where it sees each concern. |
| 0:39 | Routine from the shop catalog → morning / evening plan with clash rules | Each focus area maps to the shop's catalog, then into a morning and evening plan. Retinal only at night, so the salicylic cleanser moves to the morning, and SPF every day. |
| 0:50 | Skin Simulation “Preview on my photo” (5.1 s, 4 units; wait 2×) → Today / Simulated slider; chips pores, dryness, fine lines, firmness | Now, Skin Simulation. YouCam renders this photo with only the concerns in the basket softened: pores, dryness, fine lines. Drag to compare. It's a preview, not a promise. |
| 1:03 | “Find my shade” → Facial Color Tones (7.5 s, 20 units; wait 2×): skin #bf9c83, warm, light → **180 Natural** (ΔE 6.1), neighbours 160 Rose Beige / 220 Sand, dewy finish | Next, the foundation shade. Facial Color Tones reads skin, lip and eye color from the same photo. Warm undertone, light depth. The closest of twelve shades is 180 Natural, with a lighter and a deeper neighbour, and a dewy finish, because dryness scored seventy-three. |
| 1:21 | “Try it on my photo” → Makeup VTO of 180 Natural (wait 3×) → foundation line appears in the basket (total $109) | One tap, and Makeup VTO tries that exact shade on the same photo. It goes straight into the basket, and there's only ever one foundation. |
| 1:31 | Lip shades re-ranked “for warm” → Petal Nude VTO (wait 3×) → basket $120 | Lip shades are re-ranked for a warm undertone. Petal Nude, tried on in seconds, and added to the basket. |
| 1:39 | **New:** Coral VTO (wait 3×) replaces Petal Nude in the basket ($121, no stacking) → re-tap Petal Nude: instant, cached, 0 units ($120) | Try Coral instead, and it replaces Petal Nude rather than stacking up. Going back to Petal Nude is instant: it's cached, so no new API call. |
| 1:49 | **New:** “×” removes Retinal 0.05% Night Cream → total $92.00 → checkout with test details (Demo Shopper · +1 000 000 0000 · demo@example.com) → “Order received · Lead #1 · score 65 · 6 items · $92.00” | Prefer to skip the retinal? One tap on the cross, and the total drops to ninety-two dollars. Enter test details and place the order. The shop gets a scored lead with the full skin profile. |
| 2:01 | How it uses YouCam: POST /s2s/v2.0/file → task/skin-analysis → task/skin-simulation + task/skin-tone-analysis → task/makeup-vto (foundation 180 Natural, lips Petal Nude / Coral), same file_id; cached per photo, re-tap = 0 units | Under the hood: one upload to the YouCam File API returns a file ID. Skin Analysis scores twelve concerns. Skin Simulation and Facial Color Tones run on that same file ID, and Makeup VTO renders the foundation and the lipstick. Four AI APIs, one upload, and every result is cached per photo. |
| 2:22 | Close: skincart-youcam.vercel.app | SkinCart. Selfie in, basket out. Try it live at skincart-youcam dot vercel dot app. |

Not shown: the one-row mobile shade scale (“Tap any shade to try it on”) — the video is the desktop 1280 px layout.

Checks done on the final file: OCR of every frame at 1 fps (150 frames, tesseract eng+rus) — only skincart-youcam.vercel.app and example.com appear; no personal names/emails, localhost, keys, webhook URLs or signed URLs; speech-to-text matches the narration sentence by sentence (overall word similarity 0.93; differences are spellings like “UCAM”, digits vs words and the spoken domain), no extra speech in pauses; container metadata is the title only.
