# SkinCart demo video (~2:15). English voice-over, no copyrighted music. Use own/consented selfie only.

| Time | Screen | Voice-over |
|---|---|---|
| 0:00–0:15 | Telegram chats of a small Tashkent cosmetics shop | "Thousands of small beauty shops sell through Telegram. Every day they answer one question by hand: what should I buy for my skin? SkinCart answers it with YouCam AI." |
| 0:15–0:45 | Phone: /start → send selfie → bot replies with skin snapshot + routine | "The customer just sends a selfie. We upload it through the YouCam File API and run AI Skin Analysis, which scores twelve concerns. SkinCart explains the top three and builds a routine from this shop's own catalog: one product per step, ranked by need, always with SPF." |
| 0:45–1:10 | Tap "Try Rose" → try-on photo appears | "Can't test lipstick in a chat? Now you can. YouCam's Makeup VTO puts the shop's real shades on the customer's own face." |
| 1:10–1:30 | Tap Order → share phone → "Order #12 received" | "One tap and a phone number later, the order is in." |
| 1:30–1:50 | Owner's Telegram gets the n8n alert; /leads JSON with skin_profile + basket | "The shop owner gets the basket, total and skin profile instantly. Leads are de-duplicated and scored, and in fourteen days n8n asks the customer for a re-scan to show progress." |
| 1:50–2:05 | Web demo page in a laptop browser | "No Telegram? The same flow runs on the web for judges and Instagram links." |
| 2:05–2:15 | Architecture slide: Telegram/Web → FastAPI → YouCam Skin Analysis + VTO → LeadFlow → n8n | "SkinCart is FastAPI, the YouCam API, n8n and Docker, open source under MIT. A beauty counter for every small shop." |

Recording tips: show the YouCam mode tag reading "live" in the web UI. Record the phone through scrcpy or a screen recorder. Keep it under 3:00.
