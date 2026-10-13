---
marp: true
theme: default
paginate: true
size: 16:9
style: |
  section { font-family: Inter, Helvetica, Arial, sans-serif; }
  h1 { color: #c2185b; }
  h2 { color: #1a1a1a; }
  footer { color: #666; font-size: 14px; }
  table { font-size: 18px; }
  code { background: #f4f4f4; }
  strong { color: #c2185b; }
footer: SkinCart · YouCam API Skin AI & eCommerce VTO Hackathon · MIT
---

<!-- _class: lead -->
# SkinCart 💄
## Selfie → skin analysis → routine → try-on → order

**heavycastles** · YouCam API Skin AI & eCommerce VTO Hackathon  
A Telegram beauty-shop assistant on YouCam AI · mock-mode demos welcome

---

# Problem

Small cosmetics shops in **Central Asia / CIS** sell through Telegram & Instagram DMs.

- "What should I buy for my skin?" answered **by hand** every day
- Customers **can't try** lipstick or foundation in a chat
- Guesswork → lost sales and wrong products

> Give a one-person shop the same scan → recommend → try on → buy flow as a big beauty brand.

---

# What SkinCart does

1. Customer sends a **selfie** (Telegram bot or web)
2. **YouCam AI Skin Analysis** scores **12** concerns
3. Matcher builds a **routine** from the shop's catalog (always SPF)
4. **YouCam Makeup VTO** previews lipstick / foundation on their face
5. **Order** → LeadFlow lead (`skin_profile` + `basket`) → **n8n** owner alert + 14-day re-scan

```
selfie → File API → Skin Analysis → recommend → Makeup VTO → order → n8n
```

---

# YouCam APIs used

| Step | Endpoint |
|---|---|
| Upload | `POST /s2s/v2.0/file` → presigned PUT |
| Skin | `POST /s2s/v2.0/task/skin-analysis` → poll |
| VTO | `POST /s2s/v2.0/task/makeup-vto` → poll |

Auth: `Authorization: Bearer $YOUCAM_API_KEY` · server `yce-api-01.makeupar.com`

**Cache per image hash** → re-scans & repeat try-ons cost **0 units**.  
**Mock mode** (no key / `YOUCAM_MOCK=1`) → deterministic offline demos & CI.

---

# Demo (mock mode)

Synthetic illustrative face · **no real selfie** · badge `YouCam: mock`

- Top concerns e.g. puffy eyes / breakouts / dryness
- Routine: cleanser + eye gel + treatment + **SPF 50**
- Try-on: Velvet Matte Lipstick – Rose (mock SVG preview)
- Order → LeadFlow lead with `skin_profile` + `basket`

Screenshots + draft video: `docs/`

---

# Architecture

```
Telegram bot ──┐
               ├──► FastAPI (SkinCart)
Web demo ──────┘         │
                         ├─ YouCam client (File / Skin / VTO)
                         ├─ recommend.py + catalog.json
                         ├─ LeadStore (normalize / de-dupe / score)
                         └─ n8n webhook (owner alert + day-14 re-scan)
```

Docker Compose: app `:8080` + n8n `:5678` · MIT · pytest green

---

# Impact & what's next

**Impact:** every small beauty shop gets a beauty counter inside Telegram — scan, try, order, follow up.

**Next:**
1. Live selfie (consented) + public demo deploy
2. Multi-shop CSV catalog onboarding
3. Uzbek / Russian replies
4. Progress charts from re-scans
5. More VTO categories (eyeshadow, hair)

**Built with:** Python · FastAPI · YouCam AI · Telegram Bot API · n8n · Docker · pytest (12)

MIT · Link in description
