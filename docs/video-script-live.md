# SkinCart — live demo video script (draft `docs/demo-live-draft.mp4`, 1:42)

Built from the real screen recording of the live run on 19 Oct 2026 ~20:45 MSK (see `docs/live-proof.md`).
1280×720, 30 fps. Voice-over: text-to-speech (draft voice, can be replaced by a human read). Burned-in subtitles.
Music: our own scripted synth track (no samples, no third-party audio). Sample face: Jake Nackos / Unsplash License.

| Start | Scene | Narration |
|---|---|---|
| 0:00.1 | Hook — before/after try-on, live overlay map, routine, logo | What if one selfie could sell a whole skincare routine? Meet SkinCart: live YouCam skin analysis, a basket from your own shop, and virtual try-on, in seconds. |
| 0:11.1 | Problem — shop chat | Small beauty shops sell through Telegram and Instagram chats. Every day, someone asks: what should I buy for my skin? And the owner answers by hand. |
| 0:20.9 | Live demo · upload | This is SkinCart, running live against the YouCam API. One tap on the sample photo, a licensed stock portrait, and it goes to the YouCam File API, then into Skin Analysis. |
| 0:32.1 | Live demo · skin snapshot + overlays | About five seconds later: twelve real scores. A skin score of eighty-four, with three focus areas: visible pores, dryness and puffy eyes. And these overlays come straight from YouCam, showing where the model sees each concern. |
| 0:47.0 | Live demo · routine | Each focus area maps to the shop's own catalog. One product per step, always with SPF. |
| 0:53.7 | Live demo · Makeup VTO (2 shades; render waits at 2.5×) | Now the fun part. Pick a lipstick, and YouCam Makeup VTO renders it on the same photo, reusing the uploaded file. Drag to compare. Switch to the coral gloss, and it re-renders in seconds. |
| 1:07.0 | Live demo · order → lead | Happy with it? Name, phone, place order. The basket becomes a scored, de-duplicated lead with the skin profile attached, and n8n pings the owner and books a re-scan in fourteen days. |
| 1:19.3 | Under the hood | Under the hood: a FastAPI service. One File API upload, then Skin Analysis and Makeup VTO tasks with polling. Results are cached per image, so a re-scan costs zero units. The same core powers a Telegram bot. |
| 1:34.5 | Close | SkinCart. Selfie in, basket out. Built on the YouCam AI APIs, and open source. |

Notes for the final cut:
- Two waits for the VTO render are shown at 2.5× and labelled on screen; everything else is real time.
- Swap the sample photo for a consented selfie if the owner prefers; re-record only after hosting (each new photo costs units).
- If a Telegram bot token is added, a 10–15 s phone clip of the same flow would strengthen the "device it was built for" point.
