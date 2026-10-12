"""SkinCart API: selfie -> YouCam Skin Analysis -> basket -> optional makeup VTO -> order as LeadFlow lead."""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import os
import threading
import urllib.request
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app import recommend as rec
from app.leads import LeadStore
from app.telegram import TelegramBot
from app.youcam import YouCamClient, YouCamError

VERSION = (Path(__file__).parent.parent / "VERSION").read_text().strip() if (
    Path(__file__).parent.parent / "VERSION").exists() else "dev"
MAX_IMAGE = 10 * 1024 * 1024

app = FastAPI(title="SkinCart", version=VERSION)
youcam = YouCamClient()
store = LeadStore()
scans: dict[str, dict] = {}  # scan_id -> {image, content_type, url, result}; also a cache so re-scans cost 0 units


class AnalyzeIn(BaseModel):
    image_base64: str | None = None
    image_url: str | None = None
    content_type: str = "image/jpeg"


class TryOnIn(BaseModel):
    scan_id: str
    sku: str


class OrderIn(BaseModel):
    scan_id: str | None = None
    name: str = Field(min_length=1, max_length=120)
    phone: str | None = None
    email: str | None = None
    skus: list[str] = Field(min_length=1)
    source: str = "web"
    telegram_chat_id: int | None = None


def _notify_n8n(payload: dict) -> None:
    url = os.getenv("N8N_WEBHOOK_URL")
    if not url:
        return
    def send() -> None:
        try:
            req = urllib.request.Request(url, json.dumps(payload).encode(), {"Content-Type": "application/json"})  # noqa: S310
            urllib.request.urlopen(req, timeout=10).close()  # noqa: S310
        except OSError:
            pass
    threading.Thread(target=send, daemon=True).start()


def analyze_image(image: bytes | None, url: str | None, content_type: str = "image/jpeg") -> dict:
    if image is not None and len(image) > MAX_IMAGE:
        raise HTTPException(413, "image larger than 10 MB")
    scan_id = hashlib.sha256(image or url.encode()).hexdigest()[:16]
    if scan_id in scans and scans[scan_id].get("result"):
        return scans[scan_id]["result"] | {"cached": True}
    try:
        scores = youcam.skin_analysis(image=image, url=url, content_type=content_type)
    except YouCamError as exc:
        raise HTTPException(502, f"YouCam: {exc}") from exc
    result = {"scan_id": scan_id, "mode": "mock" if youcam.mock else "live",
              "scores": [s.__dict__ for s in scores], "concerns": rec.concerns(scores),
              "basket": rec.recommend(scores), "tryon": rec.vto_products(), "cached": False}
    scans[scan_id] = {"image": image, "url": url, "content_type": content_type, "result": result}
    return result


def tryon(scan_id: str, sku: str) -> dict:
    scan, product = scans.get(scan_id), rec.get_product(sku)
    if not scan:
        raise HTTPException(404, "unknown scan_id, analyze first")
    if not product or not product.get("vto"):
        raise HTTPException(400, "product has no try-on effect")
    key = f"vto:{sku}"
    if key not in scan:
        try:
            scan[key] = youcam.makeup_vto([product["vto"]], image=scan["image"], url=scan["url"],
                                          content_type=scan["content_type"])
        except YouCamError as exc:
            raise HTTPException(502, f"YouCam: {exc}") from exc
    return {"scan_id": scan_id, "sku": sku, "image_url": scan[key]}


def create_order(order: OrderIn) -> tuple[dict, bool]:
    items = [rec.get_product(s) for s in order.skus]
    if any(i is None for i in items):
        raise HTTPException(400, "unknown sku")
    basket = [{"sku": i["sku"], "name": i["name"], "price": i["price"]} for i in items]
    total = round(sum(i["price"] for i in items), 2)
    scan = scans.get(order.scan_id or "", {}).get("result") or {}
    extra = {"basket": basket, "total": total, "skin_profile": scan.get("concerns", []),
             "scan_id": order.scan_id, "telegram_chat_id": order.telegram_chat_id}
    msg = f"SkinCart order: {', '.join(b['name'] for b in basket)} (total ${total})"
    try:
        lead, created = store.add(order.name, order.source, order.email, order.phone, msg, extra=extra)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    out = lead.__dict__.copy()
    _notify_n8n({"event": "order", "lead": out})
    return out, created


bot = TelegramBot(analyze_image, tryon, create_order, OrderIn)


@app.get("/healthz")
def healthz() -> dict:
    return {"status": "ok"}


@app.get("/version")
def version() -> dict:
    return {"version": VERSION, "commit": os.getenv("GIT_COMMIT", "unknown"),
            "youcam": {"mode": "mock" if youcam.mock else "live", "base_url": youcam.base_url,
                       "api_calls": youcam.calls}, "telegram": bot.enabled}


@app.get("/")
def index() -> FileResponse:
    return FileResponse(Path(__file__).parent / "static" / "index.html")


@app.get("/catalog")
def catalog() -> dict:
    return {"products": rec.CATALOG}


@app.post("/analyze")
def analyze(body: AnalyzeIn) -> dict:
    if not body.image_base64 and not body.image_url:
        raise HTTPException(422, "send image_base64 or image_url")
    image = None
    if body.image_base64:
        raw = body.image_base64.split(",", 1)[-1]  # accept data: URIs
        try:
            image = base64.b64decode(raw, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise HTTPException(422, "image_base64 is not valid base64") from exc
    return analyze_image(image, body.image_url if not image else None, body.content_type)


@app.post("/tryon")
def tryon_endpoint(body: TryOnIn) -> dict:
    return tryon(body.scan_id, body.sku)


@app.post("/orders", status_code=201)
def orders(body: OrderIn) -> dict:
    lead, created = create_order(body)
    return {"created": created, "lead": lead}


@app.get("/leads")
def leads(min_score: int = 0) -> dict:
    items = [lead.__dict__ for lead in store.list(min_score)]
    return {"count": len(items), "leads": items}


@app.get("/leads/{lead_id}")
def lead(lead_id: int) -> dict:
    found = store.get(lead_id)
    if not found:
        raise HTTPException(404, "lead not found")
    return found.__dict__


@app.post("/telegram/webhook")
async def telegram_webhook(request: Request) -> dict:
    secret = os.getenv("TELEGRAM_WEBHOOK_SECRET")
    if secret and request.headers.get("X-Telegram-Bot-Api-Secret-Token") != secret:
        raise HTTPException(403, "bad secret")
    return bot.handle(await request.json())
