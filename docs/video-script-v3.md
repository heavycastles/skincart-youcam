# SkinCart — demo video v3

`docs/demo-v3.mp4` · 2:10 · 1920×1080 · 30 fps · burned-in subtitles (`docs/demo-v3.srt`) in a band below the app window (they never cover buttons) · cover `docs/demo-v3-cover.png`

Recorded from the production deployment https://skincart-youcam.vercel.app on 22 Oct 2026 ~17:05 MSK (live YouCam API), in one take.
Face: licensed stock portrait (Jake Nackos / Unsplash License, `docs/stock-face/`), the app's “Use sample photo”. Order uses test details only.
Music: synthesized for this video (no third-party tracks).

Live run (one session, 26 YouCam HTTP requests, **40 units**; balance 808 → 768): 1 File API upload + Skin Analysis (5.8 s, score 84) · Skin Simulation (8.5 s, 4 units) · Facial Color Tones (7.6 s, 20 units → 180 Natural, ΔE 6.1) · Makeup VTO foundation 180 Natural (1) · Makeup VTO lip Petal Nude (1).
Speed-ups (all labelled on screen): Skin Simulation and Facial Color Tones waits 2×, the two VTO render waits 3×; everything else is real time (calm moments are held with slow zooms on the last frame). No repository URL is shown (the repo is not public).

| Time | Scene | Narration |
|---|---|---|
| 0:00 | Hook: scanning frame → skin snapshot → shade match → Skin Simulation before/after → title “SkinCart · Selfie in. Basket out.” | One selfie. Your skin, your shade, and a preview of what the basket will do. This is SkinCart, built on four YouCam AI APIs. |
| 0:09 | Problem: shop chat illustration | Shoppers can't tell what suits their skin, and a wrong foundation shade is one of the top reasons it gets sent back. So they ask in chat, and the owner guesses by hand. |
| 0:18 | Live: Use sample photo → File API upload + Skin Analysis, real time (“Analyzed in 5.8 s · live YouCam API”) | This is the live app. One tap on the sample photo, a licensed stock portrait. It's uploaded once to the YouCam File API, and Skin Analysis starts. |
| 0:28 | Skin snapshot: score 84, focus areas visible pores 70 · dryness 73 · puffy eyes 76, 12 concern tiles, YouCam overlay masks | About six seconds later: twelve real scores, a skin score of eighty-four, and YouCam's own overlays showing where it sees each concern. |
| 0:37 | Routine from the shop catalog → morning / evening plan with clash rules (retinal at night, salicylic cleanser in the morning, SPF) | Each focus area maps to the shop's catalog, then into a morning and evening plan. Retinal only at night, so the salicylic cleanser moves to the morning, and SPF every day. |
| 0:48 | **New:** Skin Simulation “Preview on my photo” (8.5 s, 4 units; wait shown 2×, labelled) → Today / Simulated slider; chips visible pores · moderate, dryness · moderate, fine lines · light, loss of firmness · light | Now, Skin Simulation. YouCam renders this photo with only the concerns in the basket softened: pores, dryness, fine lines. Drag to compare. It's a preview, not a promise. |
| 1:01 | **New:** “Find my shade” → Facial Color Tones (7.6 s, 20 units; wait shown 2×, labelled): skin #bf9c83, warm, light, eyes brown, lip #d1877d → 12-shade range, match **180 Natural** (ΔE 6.1), neighbours 160 Rose Beige / 220 Sand, dewy finish, sheer-to-light coverage | Next, the foundation shade. Facial Color Tones reads skin, lip and eye color from the same photo. Warm undertone, light depth. The closest of twelve shades is 180 Natural, with a lighter and a deeper neighbour, and a dewy finish, because dryness scored seventy-three. |
| 1:19 | **New:** “Try it on my photo” → Makeup VTO of 180 Natural (wait shown 3×, labelled), before/after slider | One tap, and Makeup VTO tries that exact shade on the same photo. |
| 1:27 | Lip shades re-ranked “for warm” → Petal Nude Makeup VTO (wait shown 3×, labelled) | Lip shades are re-ranked for a warm undertone. Petal Nude, tried on in seconds. |
| 1:33 | Matched shade added to the basket → checkout with test details (Demo Shopper · +1 000 000 0000 · demo@example.com) → “Order received · Lead #1 · score 65 · 7 items · $120.00” | Add the matched shade, enter test details, and place the order. The shop gets a scored lead with the full skin profile. |
| 1:41 | How it uses YouCam: POST /s2s/v2.0/file → task/skin-analysis → task/skin-simulation + task/skin-tone-analysis → task/makeup-vto, all with the same file_id (poll task_id); cached per photo | Under the hood: one upload to the YouCam File API returns a file ID. Skin Analysis scores twelve concerns. Skin Simulation and Facial Color Tones run on that same file ID, and Makeup VTO renders the foundation and the lipstick. Four AI APIs, one upload, and every result is cached per photo. |
| 2:03 | Close: skincart-youcam.vercel.app | SkinCart. Selfie in, basket out. Try it live at skincart-youcam dot vercel dot app. |

Checks done on the final file: OCR of every frame at 0.5 s (262 frames, tesseract eng+rus) — only skincart-youcam.vercel.app and example.com appear; no personal names/emails, localhost, keys, webhook URLs or signed URLs; speech-to-text matches the narration sentence by sentence (overall word similarity 0.92; differences are spellings like “U-CAM” and the spoken domain), no extra speech in pauses; container metadata is the title only.
