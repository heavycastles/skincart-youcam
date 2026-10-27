"""Minimal Telegram bot (webhook or long polling) on top of the SkinCart core functions.

Flow: /start -> send selfie -> scores + basket with inline buttons [Try on] [Order] -> share contact -> lead.
Without TELEGRAM_BOT_TOKEN the bot still processes updates and returns the replies it *would* send (tests/demo).
"""

from __future__ import annotations

import json
import os
import urllib.request

from fastapi import HTTPException

API = "https://api.telegram.org"


MAX_SIDE = 1919  # same limit as app.main.MAX_SIDE: YouCam Makeup VTO takes a long side below 1920 px


def pick_photo_size(photos: list[dict]) -> dict:
    """Telegram sends each photo in several sizes (smallest first); take the largest one YouCam accepts."""
    fitting = [p for p in photos if max(p.get("width") or 0, p.get("height") or 0) <= MAX_SIDE]
    return fitting[-1] if fitting else photos[0]


class TelegramBot:
    def __init__(self, analyze, tryon, order, order_model) -> None:
        self.token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        self.analyze, self.tryon, self.order, self.Order = analyze, tryon, order, order_model
        self.last_scan: dict[int, dict] = {}  # chat_id -> analysis result

    @property
    def enabled(self) -> bool:
        return bool(self.token)

    def _api(self, method: str, payload: dict) -> dict:
        if not self.token:
            return {"ok": True, "offline": True}
        req = urllib.request.Request(  # noqa: S310
            f"{API}/bot{self.token}/{method}", json.dumps(payload).encode(), {"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as r:  # noqa: S310
            return json.loads(r.read())

    def _download_photo(self, file_id: str) -> bytes:
        info = self._api("getFile", {"file_id": file_id})
        with urllib.request.urlopen(f"{API}/file/bot{self.token}/{info['result']['file_path']}", timeout=30) as r:  # noqa: S310
            return r.read()

    def send(self, chat_id: int, text: str, **extra) -> dict:
        msg = {"chat_id": chat_id, "text": text, "parse_mode": "HTML", **extra}
        self._api("sendMessage", msg)
        return msg

    def handle(self, update: dict) -> dict:
        sent: list[dict] = []
        if cb := update.get("callback_query"):
            chat_id = cb["message"]["chat"]["id"]
            action, _, arg = cb.get("data", "").partition(":")
            scan = self.last_scan.get(chat_id)
            if not scan:
                sent.append(self.send(chat_id, "Send me a selfie first 📸"))
            elif action == "try":
                try:
                    url = self.tryon(scan["scan_id"], arg)["image_url"]
                except HTTPException as exc:
                    sent.append(self.send(chat_id, f"😕 {exc.detail}"))
                    return {"ok": True, "sent": sent}
                if url.startswith("http"):
                    self._api("sendPhoto", {"chat_id": chat_id, "photo": url, "caption": "Your try-on ✨"})
                sent.append(self.send(chat_id, f"Try-on ready: {arg}", reply_markup=self._order_kb()))
            elif action == "order":
                sent.append(self.send(chat_id, "Share your phone number so the shop can confirm the order:",
                                      reply_markup={"keyboard": [[{"text": "📱 Share phone", "request_contact": True}]],
                                                    "one_time_keyboard": True, "resize_keyboard": True}))
            return {"ok": True, "sent": sent}
        msg = update.get("message") or {}
        chat_id = (msg.get("chat") or {}).get("id")
        if chat_id is None:
            return {"ok": True, "sent": sent}
        if photos := msg.get("photo"):
            photo = pick_photo_size(photos)
            image = self._download_photo(photo["file_id"]) if self.token else photo["file_id"].encode()
            try:
                res = self.analyze(image, None, "image/jpeg")
            except HTTPException as exc:  # e.g. face too small: tell the customer how to retake it
                sent.append(self.send(chat_id, f"😕 {exc.detail}"))
                return {"ok": True, "sent": sent}
            self.last_scan[chat_id] = res
            sent.append(self.send(chat_id, self.format_result(res), reply_markup=self._result_kb(res)))
        elif contact := msg.get("contact"):
            scan = self.last_scan.get(chat_id)
            if not scan:
                sent.append(self.send(chat_id, "Send me a selfie first 📸"))
            else:
                name = " ".join(filter(None, [contact.get("first_name"), contact.get("last_name")])) or "Telegram user"
                lead, _ = self.order(self.Order(scan_id=scan["scan_id"], name=name, phone=contact["phone_number"],
                                                skus=[b["sku"] for b in scan["basket"]], source="telegram",
                                                telegram_chat_id=chat_id))
                sent.append(self.send(chat_id, f"✅ Order #{lead['id']} received - total ${lead['extra']['total']}. "
                                      "The shop will message you shortly.", reply_markup={"remove_keyboard": True}))
        else:
            sent.append(self.send(chat_id, "Hi! I'm <b>SkinCart</b> 💄 Send a well-lit selfie (no filters) and I'll "
                                  "analyze your skin with YouCam AI and build a routine from our shop."))
        return {"ok": True, "sent": sent}

    @staticmethod
    def format_result(res: dict) -> str:
        lines = ["<b>Your skin snapshot</b> (YouCam AI Skin Analysis)"]
        found = [f"• {c['label']}: {c['ui_score']}/100 ({c['severity']})" for c in res["concerns"]]
        lines += found or ["• Looking great!"]
        lines.append("\n<b>Suggested routine</b>")
        lines += [f"• {b['name']} - ${b['price']}" for b in res["basket"]]
        lines.append(f"\nTotal: ${sum(b['price'] for b in res['basket']):.2f}")
        return "\n".join(lines)

    @staticmethod
    def _order_kb() -> dict:
        return {"inline_keyboard": [[{"text": "🛒 Order routine", "callback_data": "order:"}]]}

    def _result_kb(self, res: dict) -> dict:
        rows = [[{"text": f"💋 Try {p['name'].split(' - ')[-1]}", "callback_data": f"try:{p['sku']}"}]
                for p in res["tryon"]]
        return {"inline_keyboard": rows + self._order_kb()["inline_keyboard"]}


def poll_forever() -> None:  # pragma: no cover - `python -m app.telegram` for local runs without a public URL
    from app.main import bot
    offset = 0
    while True:
        resp = bot._api("getUpdates", {"offset": offset, "timeout": 30})
        for upd in resp.get("result", []):
            offset = upd["update_id"] + 1
            try:
                bot.handle(upd)
            except Exception as exc:  # noqa: BLE001
                print("update failed:", exc)


if __name__ == "__main__":  # pragma: no cover
    poll_forever()
