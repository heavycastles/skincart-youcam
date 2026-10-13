# Demo video script (~2:00–2:30, English)

**Visual style:** title cards + mock-mode UI frames. Synthetic / illustrative face only
(no real person's photo). On-screen badge: `YouCam: mock · synthetic demo face`.
Narration: gTTS draft in `docs/demo-draft.mp4`; replace with recorded voice + live selfie for final submit.
No copyrighted music.

---

### 0:00–0:18 — Hook
**Visual:** Cover / title — "SkinCart" · YouCam API Skin AI & eCommerce VTO Hackathon.

**Say:** "Thousands of small beauty shops sell through Telegram. Every day they answer one question by hand:
what should I buy for my skin? SkinCart answers it with YouCam AI — selfie to basket, inside the chat."

---

### 0:18–0:40 — Problem → idea
**Visual:** Problem card — DMs vs scan → recommend → try-on → order.

**Say:** "Customers can't test lipstick in a chat, and shops lose sales to guesswork. SkinCart gives a one-person
shop the same scan, recommend, try-on and buy flow as a big beauty brand — on Telegram or the web."

---

### 0:40–1:15 — Demo: analyze + routine (mock)
**Visual:** Web UI mock — synthetic face, skin scores, routine with SPF. Badge `YouCam: mock`.

**Say:** "This draft runs in mock mode with a clearly synthetic face — no real selfie. We upload through the
YouCam File API and run AI Skin Analysis, which scores twelve concerns. SkinCart explains the top three and
builds a routine from this shop's own catalog: one product per step, ranked by need, always with SPF."

---

### 1:15–1:35 — Try-on
**Visual:** Mock VTO preview — lipstick Rose on synthetic face.

**Say:** "Can't test lipstick in a chat? Now you can. YouCam's Makeup VTO puts the shop's real shades on the
customer's face. Here: Velvet Matte Lipstick, Rose."

---

### 1:35–1:55 — Order + owner
**Visual:** Order confirmation + LeadFlow lead with skin_profile + basket; n8n alert card.

**Say:** "One tap and a phone number later, the order is a scored LeadFlow lead with the skin profile and basket
attached. The shop owner gets an n8n alert instantly, and in fourteen days the bot asks for a re-scan to show progress."

---

### 1:55–2:15 — Close
**Visual:** Architecture slide → tagline.

**Say:** "SkinCart is FastAPI, the YouCam API, Telegram, n8n and Docker — open source under MIT.
A beauty counter for every small shop. Link in the description."

---

## Shot list checklist
- [x] Cover card
- [x] Problem → idea
- [x] Mock analyze + scores + routine (synthetic face)
- [x] Mock VTO try-on
- [x] Order / LeadFlow / n8n
- [x] Architecture + tagline
