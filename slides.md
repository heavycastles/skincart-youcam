---
marp: true
theme: default
paginate: true
size: 16:9
style: |
  section { font-family: Inter, Helvetica, Arial, sans-serif; font-size: 26px; }
  h1 { color: #c2185b; }
  h2 { color: #1a1a1a; }
  footer { color: #666; font-size: 14px; }
  table { font-size: 20px; }
  code { background: #f4f4f4; }
  strong { color: #c2185b; }
  img[alt~="shot"] { border: 1px solid #ddd; border-radius: 8px; }
footer: SkinCart · YouCam API Skin AI & eCommerce VTO Hackathon · MIT · skincart-youcam.vercel.app
---

<!-- _class: lead -->
# SkinCart 💄
## Selfie in. Basket out.

Skin analysis → routine you can preview on your face → foundation shade matched and tried on → one-tap order

**Live demo:** https://skincart-youcam.vercel.app (no login, "Use sample photo")
**Code:** https://github.com/heavycastles/skincart-youcam (MIT) · **Video:** https://youtu.be/NIFuCn8lOT0

---

# Problem

Small cosmetics shops in **Central Asia / CIS** sell through Telegram & Instagram DMs.

- "What should I buy for my skin?" is answered **by hand**, all day
- Customers **can't test** a foundation or a lipstick in a chat
- The wrong foundation shade is one of the top reasons it gets **sent back**

> Give a one-person shop the scan → recommend → try on → buy flow of a big beauty brand.

---

# Who it's for

| Who | What they get |
|---|---|
| **Small beauty shops** selling in Telegram / Instagram chats (one owner, no web team) | Answers from their **own catalog**, and an order with the skin profile attached instead of "hi, how much?" |
| **Their customers**, who can't test products through a chat | A plain-language skin snapshot, a short routine, a preview of what it targets, their **foundation shade** and a try-on **before paying** |

Why it matters: fewer wrong-shade returns, fewer chats that go nowhere, a scored lead with context.

---

# What SkinCart does — one upload, four YouCam AI APIs

1. **Skin Analysis** scores 12 concerns → top 3 focus areas + YouCam overlay masks
2. Routine from the shop's **own catalog** (always SPF) + **morning / evening plan** with clash rules
3. **Skin Simulation**: the customer's photo with only what the basket targets softened (0.25–0.7 by score)
4. **Facial Color Tones**: undertone + depth → nearest of 12 foundation shades (ΔE), neighbours, finish
5. **Makeup VTO**: the matched foundation and lip shades ranked for the undertone, before/after slider
6. **Order** → scored, de-duplicated lead with skin profile + basket (optional n8n owner alert + day-14 re-scan)

---

# Live: analysis, routine, preview

![shot h:330](docs/screenshots/03-skin-analysis.png) ![shot h:330](docs/screenshots/10-skin-simulation.png)

Score 84 · visible pores, dryness, puffy eyes · Skin Simulation of the basket (4 units)

---

# Live: shade match and try-on

![shot h:400](docs/screenshots/11-shade-match.png) ![shot h:400](docs/screenshots/12-foundation-tryon.png)

Skin #bf9c83 · warm · light → **180 Natural** (ΔE 6.1) · dewy finish because dryness scored 73

---

# YouCam APIs used

| Step | Endpoint | Units |
|---|---|---|
| Upload once | `POST /s2s/v2.0/file` → presigned PUT → `file_id` | 0 |
| Skin Analysis | `POST /s2s/v2.0/task/skin-analysis` (12 SD actions) → poll | 14 |
| Skin Simulation | `POST /s2s/v2.0/task/skin-simulation` (basket concerns) → poll | 4–6 |
| Facial Color Tones | `POST /s2s/v2.0/task/skin-tone-analysis` → poll | 20 |
| Makeup VTO | `POST /s2s/v2.0/task/makeup-vto` (lip / foundation) → poll | 1 |

Same `file_id` for every task · results cached per photo (repeat = **0 units**) · the page shows units per step

---

# Architecture

```
Web page ──────┐
               ├──► FastAPI  /analyze · /simulate · /shade · /tryon · /orders
Telegram bot ──┘         │
                         ├─ YouCam client (File API → 4 async tasks, polling, cache)
                         ├─ recommend.py + catalog.json (routine, AM/PM plan, simulation plan)
                         ├─ shade.py (CIELAB / ITA, delta-E, undertone-aware, lip ranking)
                         ├─ LeadStore (normalize / de-dupe / score + skin profile)
                         └─ n8n webhook (owner alert + day-14 re-scan), optional
```

Vercel (serverless FastAPI) · Docker Compose · 134 pytest cases incl. headless-browser runs at 1280 and 375 px

---

# Built for real shoppers

- Photo checks **before** any API call (format, size, framing step); YouCam errors become plain advice
- Honest UI: "simulation, not a promise", units shown, mock mode clearly labelled
- Accessible: AA contrast, live announcements, keyboard sliders · Lighthouse 100 on mobile and desktop
- Private by default: contacts never echoed back, lead list is admin-only

---

# Impact & what's next

**Impact:** a beauty counter for every small shop — the right shade and a realistic preview before buying,
and an order with context instead of "hi, how much?".

**Next:**
1. CSV catalog onboarding for any shop
2. Uzbek / Russian replies
3. Progress chart from the 14-day re-scans
4. More try-on categories and Instagram DMs

**Built with:** Python · FastAPI · YouCam AI · JavaScript · n8n · Docker · Vercel · pytest
