"""SkinCart API: selfie -> YouCam Skin Analysis -> basket -> optional makeup VTO -> order as LeadFlow lead."""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import os
import re
import struct
import threading
import time
import urllib.request
from collections import OrderedDict
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from app import recommend as rec
from app import shade as shade_mod
from app.leads import LeadStore
from app.telegram import TelegramBot
from app.youcam import YouCamClient, YouCamError

VERSION = (Path(__file__).parent.parent / "VERSION").read_text().strip() if (
    Path(__file__).parent.parent / "VERSION").exists() else "dev"
MAX_IMAGE = 10 * 1024 * 1024
MIN_SIDE = 480  # YouCam SD skin analysis: short side must be at least 480 px
MAX_SCANS = 24  # in-memory cache holds photos, so keep it bounded on long-lived instances

app = FastAPI(title="SkinCart", version=VERSION)

SECURITY_HEADERS = {"X-Content-Type-Options": "nosniff", "X-Frame-Options": "DENY",
                    "Referrer-Policy": "strict-origin-when-cross-origin"}


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    for key, value in SECURITY_HEADERS.items():
        response.headers.setdefault(key, value)
    return response
youcam = YouCamClient()
store = LeadStore()


class ScanCache(OrderedDict):
    """scan_id -> {image, content_type, url, result}; re-scans of the same photo cost 0 units. LRU-bounded."""

    def __getitem__(self, key):
        self.move_to_end(key)
        return super().__getitem__(key)

    def __setitem__(self, key, value):
        super().__setitem__(key, value)
        self.move_to_end(key)
        while len(self) > MAX_SCANS:
            self.popitem(last=False)

    def get(self, key, default=None):
        return self[key] if key in self else default

    def setdefault(self, key, default=None):
        if key not in self:
            self[key] = default
        return self[key]


scans: ScanCache = ScanCache()

# YouCam error code -> (HTTP status, what the visitor should do). Raw details go to the server log only.
FRIENDLY_ERRORS: dict[str, tuple[int, str]] = {
    "error_src_face_too_small": (422, "Move closer: your face should fill most of the photo (over 60% of its "
                                      "width). Zoom in so your face fits the oval and try again."),
    "error_no_face": (422, "We couldn't find a face in this photo. Use a front-facing selfie with your whole "
                           "face visible."),
    "error_pose": (422, "Please look straight at the camera - the face is turned too far for skin analysis."),
    "error_face_parsing": (422, "We couldn't read the face clearly. Try a sharper, front-facing selfie without "
                                "hands, hair or glasses covering it."),
    "error_src_face_out_of_bound": (422, "Part of your face is cut off. Center your face with a little space "
                                         "around it."),
    "error_lighting_dark": (422, "The photo is too dark. Face a window or a lamp and try again."),
    "error_below_min_image_size": (422, f"This photo is too small. Use one at least {MIN_SIDE} px on the short "
                                        "side."),
    "error_exceed_max_image_size": (413, "This photo is too large. Please use one under 10 MB."),
    "exceed_max_filesize": (413, "This photo is too large. Please use one under 10 MB."),
    "error_decode_image": (415, "YouCam couldn't read this image. Please use a JPG or PNG photo."),
    "error_nsfw_content_detected": (422, "This photo can't be processed. Please use a regular selfie."),
    "timeout": (504, "YouCam is taking longer than usual. Please try again in a moment."),
    "http_429": (503, "YouCam is busy right now. Please wait a few seconds and try again."),
}
GENERIC_ERROR = (502, "YouCam couldn't process this request right now. Please try again, or use the sample photo.")


def youcam_http_error(exc: YouCamError) -> HTTPException:
    status, message = FRIENDLY_ERRORS.get(exc.code, GENERIC_ERROR)
    print(f"[skincart] YouCam error {exc.code}: {exc}", flush=True)  # noqa: T201 - server log for debugging
    return HTTPException(status, message, headers={"X-SkinCart-Error": exc.code})


def image_info(data: bytes) -> tuple[str | None, int | None, int | None]:
    """Sniff the real format from the bytes (never trust the declared type) and read the pixel size
    from the JPEG SOF / PNG IHDR header, stdlib only."""
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        if len(data) >= 24 and data[12:16] == b"IHDR":
            w, h = struct.unpack(">II", data[16:24])
            return "png", w, h
        return "png", None, None
    if data[:2] == b"\xff\xd8":
        i = 2
        while i + 9 < len(data):
            if data[i] != 0xFF:
                i += 1
                continue
            marker = data[i + 1]
            if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7 or marker == 0xFF:
                i += 1 if marker == 0xFF else 2
                continue
            length = struct.unpack(">H", data[i + 2:i + 4])[0]
            if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
                h, w = struct.unpack(">HH", data[i + 5:i + 9])
                return "jpeg", w, h
            i += 2 + length
        return "jpeg", None, None
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp", None, None
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "gif", None, None
    if data[4:8] == b"ftyp" and data[8:12] in (b"heic", b"heix", b"mif1", b"msf1", b"hevc", b"avif"):
        return "heic", None, None
    return None, None, None


def check_image(image: bytes) -> str:
    """Reject what YouCam would refuse anyway, before spending any API units. Returns the content type."""
    if not image:
        raise HTTPException(422, "The photo is empty. Please choose a selfie.")
    if len(image) > MAX_IMAGE:
        raise HTTPException(413, "This photo is too large. Please use one under 10 MB.")
    fmt, w, h = image_info(image)
    if fmt in ("webp", "gif", "heic"):
        raise HTTPException(415, f"{fmt.upper()} photos aren't supported by YouCam Skin Analysis. Please use a "
                                 "JPG or PNG photo.")
    if fmt is None:
        raise HTTPException(415, "This file isn't a photo we can read. Please use a JPG or PNG selfie.")
    if w and h and min(w, h) < MIN_SIDE:
        raise HTTPException(422, f"This photo is too small ({w}x{h} px). Use one at least {MIN_SIDE} px on the "
                                 "short side.")
    return "image/png" if fmt == "png" else "image/jpeg"


class AnalyzeIn(BaseModel):
    image_base64: str | None = None
    image_url: str | None = None
    content_type: str = "image/jpeg"


class ScanRef(BaseModel):
    scan_id: str = Field(min_length=1, max_length=64)
    # Serverless hosts may route a follow-up call to a fresh instance that never saw /analyze.
    # The browser then re-sends what it already has, so no second skin analysis is needed.
    file_id: str | None = Field(default=None, max_length=512)
    image_base64: str | None = None
    image_url: str | None = None
    content_type: str = "image/jpeg"


class TryOnIn(ScanRef):
    sku: str


class ScoreIn(BaseModel):
    type: str = Field(max_length=40)
    ui_score: int = Field(ge=0, le=100)


class ShadeIn(ScanRef):
    scores: list[ScoreIn] | None = Field(default=None, max_length=20)  # used if the scan isn't in memory


class SimulateIn(ScanRef):
    skus: list[str] = Field(min_length=1, max_length=30)
    scores: list[ScoreIn] | None = Field(default=None, max_length=20)


class OrderIn(BaseModel):
    scan_id: str | None = None
    name: str = Field(min_length=1, max_length=120)
    phone: str | None = Field(default=None, max_length=40)
    email: str | None = Field(default=None, max_length=200)
    skus: list[str] = Field(min_length=1, max_length=30)
    source: str = "web"
    telegram_chat_id: int | None = None
    skin_profile: list[dict] | None = Field(default=None, max_length=20)  # used if the scan isn't in memory


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


def _decode_b64(data: str) -> bytes:
    raw = data.split(",", 1)[-1]  # accept data: URIs
    try:
        return base64.b64decode(raw, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise HTTPException(422, "This photo couldn't be read (the upload is not valid base64).") from exc


URL_RE = re.compile(r"https?://[^\s/?#]+\.[^\s/?#]+[^\s]*", re.IGNORECASE)


def _check_url(url: str | None) -> None:
    """A photo link must be a public http(s) URL; anything else would only time out at YouCam."""
    if url is not None and (len(url) > 2048 or not URL_RE.fullmatch(url.strip())):
        raise HTTPException(422, "That photo link doesn't look right. Use a full https:// link to a JPG or PNG.")


def _scan_id(image: bytes | None, url: str | None) -> str:
    return hashlib.sha256(image or (url or "").encode()).hexdigest()[:16]


def analyze_image(image: bytes | None, url: str | None, content_type: str = "image/jpeg") -> dict:
    if image is not None and len(image) > MAX_IMAGE:
        raise HTTPException(413, "This photo is too large. Please use one under 10 MB.")
    if image is not None and not youcam.mock:
        content_type = check_image(image)
    scan_id = _scan_id(image, url)
    if scan_id in scans and scans[scan_id].get("result"):
        return scans[scan_id]["result"] | {"cached": True, "api_calls": 0, "units": 0}
    started, file_id, calls0 = time.monotonic(), None, youcam.calls
    youcam.begin()
    try:
        if image is not None and not youcam.mock:
            file_id = youcam.upload(image, content_type)  # one upload, reused by every try-on of this scan
        scores = youcam.skin_analysis(image=image, url=url, content_type=content_type, file_id=file_id)
    except YouCamError as exc:
        raise youcam_http_error(exc) from exc
    finally:
        youcam.end()
    if not scores:
        raise HTTPException(502, "YouCam returned no skin scores for this photo. Please try another selfie.")
    result = {"scan_id": scan_id, "mode": "mock" if youcam.mock else "live",
              "scores": [s.__dict__ | {"label": rec.LABELS.get(s.type, s.type)} for s in scores],
              "skin_score": rec.skin_score(scores), "concerns": rec.concerns(scores),
              "basket": (basket := rec.recommend(scores)), "tryon": rec.vto_products(), "cached": False,
              "schedule": rec.schedule([b["sku"] for b in basket]), "units": _units("skin_analysis"),
              "file_id": file_id, "api_calls": youcam.calls - calls0,
              "elapsed_ms": round((time.monotonic() - started) * 1000)}
    scans[scan_id] = {"image": image, "url": url, "content_type": content_type, "file_id": file_id,
                      "result": result}
    return result


def resolve_scan(scan_id: str, fallback: ScanRef | None = None) -> dict:
    """The cached scan, or one rebuilt from what the browser re-sent (fresh serverless instance)."""
    scan = scans.get(scan_id)
    if not scan and fallback and (fallback.file_id or fallback.image_base64 or fallback.image_url):
        image = _decode_b64(fallback.image_base64) if fallback.image_base64 else None
        if image is not None and len(image) > MAX_IMAGE:
            raise HTTPException(413, "This photo is too large. Please use one under 10 MB.")
        url = None if image else fallback.image_url
        _check_url(url)
        if (image or url) and _scan_id(image, url) != scan_id:
            raise HTTPException(400, "This photo doesn't match the analyzed one. Please analyze it again.")
        scan = scans.setdefault(scan_id, {"image": image, "url": url, "content_type": fallback.content_type,
                                          "file_id": fallback.file_id, "result": None})
    if not scan:
        raise HTTPException(404, "This analysis has expired. Please analyze your photo again.")
    return scan


def run_on_scan(scan: dict, call):
    """Run one paid YouCam task on the scan's uploaded file; if the file_id expired, upload once more."""
    args = {"image": scan["image"], "url": scan["url"], "content_type": scan["content_type"]}
    youcam.begin()
    try:
        try:
            return call(file_id=scan.get("file_id"), **args)
        except YouCamError as exc:
            if not scan.get("file_id") or exc.code == "timeout" or not (scan["image"] or scan["url"]):
                raise
            return call(**args)  # file expired -> upload again
    except YouCamError as exc:
        raise youcam_http_error(exc) from exc
    finally:
        youcam.end()


def tryon(scan_id: str, sku: str, fallback: TryOnIn | None = None) -> dict:
    scan, product = resolve_scan(scan_id, fallback), rec.get_product(sku)
    if not product or not product.get("vto"):
        raise HTTPException(400, "This product has no virtual try-on.")
    key = f"vto:{sku}"
    calls0, started, cached = youcam.calls, time.monotonic(), key in scan
    if not cached:
        scan[key] = run_on_scan(scan, lambda **kw: youcam.makeup_vto([product["vto"]], **kw))
    return {"scan_id": scan_id, "sku": sku, "image_url": scan[key], "api_calls": youcam.calls - calls0,
            "cached": cached, "units": 0 if cached else _units("makeup_vto"),
            "elapsed_ms": round((time.monotonic() - started) * 1000)}


# YouCam unit price per successful task (GET /s2s/v2.0/credit/feature-cost, Oct 2026). Shown in the UI.
UNITS = {"skin_analysis": 14, "makeup_vto": 1, "skin_tone": 20, "skin_simulation_1_4": 4, "skin_simulation_5_10": 6}


def _units(task: str) -> int:
    return 0 if youcam.mock else UNITS[task]


def _scores_for(scan: dict, sent: list[ScoreIn] | None) -> list[dict]:
    result = scan.get("result") or {}
    if result.get("scores"):
        return [{"type": s["type"], "ui_score": s["ui_score"]} for s in result["scores"]]
    return [s.model_dump() for s in (sent or []) if s.type in rec.LABELS]


def shade_match(body: ShadeIn) -> dict:
    """Facial Color Tones Analyzer -> undertone, depth, nearest foundation shade, formula and lip ranking."""
    scan = resolve_scan(body.scan_id, body)
    calls0, started, cached = youcam.calls, time.monotonic(), "tones" in scan
    if not cached:
        scan["tones"] = run_on_scan(scan, youcam.skin_tone)
    try:
        result = shade_mod.match(scan["tones"], _scores_for(scan, body.scores))
    except ValueError as exc:
        raise HTTPException(502, "YouCam couldn't read a skin color from this photo. "
                                 "Please try another selfie.") from exc
    return result | {"scan_id": body.scan_id, "mode": "mock" if youcam.mock else "live", "cached": cached,
                     "api_calls": youcam.calls - calls0, "units": 0 if cached else _units("skin_tone"),
                     "elapsed_ms": round((time.monotonic() - started) * 1000)}


def simulate(body: SimulateIn) -> dict:
    """Skin Simulation of only the concerns the basket's skincare products target (cached per intensity set)."""
    if any(rec.get_product(s) is None for s in body.skus):
        raise HTTPException(400, "One of the products is no longer in the catalog. Please reload the page.")
    scan = resolve_scan(body.scan_id, body)
    scores = _scores_for(scan, body.scores)
    if not scores:
        raise HTTPException(422, "Please analyze your photo first, so we know what the routine should target.")
    plan = rec.simulation_plan(scores, body.skus)
    if not plan["params"]:
        raise HTTPException(422, "Add a skincare product to your basket to preview what it targets.")
    key = "sim:" + ",".join(f"{k}={v:.2f}" for k, v in plan["params"].items())
    calls0, started, cached = youcam.calls, time.monotonic(), key in scan
    if not cached:
        scan[key] = run_on_scan(scan, lambda **kw: youcam.skin_simulation(plan["params"], **kw))
    tier = "skin_simulation_1_4" if len(plan["params"]) <= 4 else "skin_simulation_5_10"
    return {"scan_id": body.scan_id, "image_url": scan[key], "params": plan["params"], "concerns": plan["concerns"],
            "mode": "mock" if youcam.mock else "live", "cached": cached, "api_calls": youcam.calls - calls0,
            "units": 0 if cached else _units(tier), "elapsed_ms": round((time.monotonic() - started) * 1000)}


EMAIL_RE = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")


def create_order(order: OrderIn) -> tuple[dict, bool]:
    items = [rec.get_product(s) for s in dict.fromkeys(order.skus)]  # a repeated SKU is one product, not two
    if any(i is None for i in items):
        raise HTTPException(400, "One of the products is no longer in the catalog. Please reload the page.")
    name = order.name.strip() or "Guest"
    if order.email and order.email.strip() and not EMAIL_RE.fullmatch(order.email.strip()):
        raise HTTPException(422, "That email doesn't look right. Please check it.")
    basket = [{"sku": i["sku"], "name": i["name"], "price": i["price"]} for i in items]
    total = round(sum(i["price"] for i in items), 2)
    scan = scans.get(order.scan_id or "", {}).get("result") or {}
    profile = scan.get("concerns") or (order.skin_profile or [])
    extra = {"basket": basket, "total": total, "skin_profile": profile,
             "scan_id": order.scan_id, "telegram_chat_id": order.telegram_chat_id}
    msg = f"SkinCart order: {', '.join(b['name'] for b in basket)} (total ${total})"
    try:
        lead, created = store.add(name, order.source, order.email, order.phone, msg, extra=extra)
    except ValueError as exc:
        raise HTTPException(422, "Please enter a phone number (at least 7 digits) or an email so the shop can "
                                 "confirm your order.") from exc
    _notify_n8n({"event": "order", "lead": lead.__dict__.copy()})  # full record stays server-side
    return order_receipt(lead, extra), created


def order_receipt(lead, extra: dict) -> dict:
    """What the customer sees: only this order. Never the stored lead, which on a de-duplicated
    phone/email belongs to an earlier customer (name, contacts, previous baskets)."""
    return {"id": lead.id, "score": lead.score, "source": lead.source,
            "extra": {"basket": extra["basket"], "total": extra["total"], "skin_profile": extra["skin_profile"]}}


def require_admin(request: Request) -> None:
    """Lead listing holds customers' phones/emails, so it is never public.
    No ADMIN_TOKEN configured -> the route does not exist (404); wrong/missing token -> 401."""
    token = os.getenv("ADMIN_TOKEN", "")
    if not token:
        raise HTTPException(404, "Not Found")
    given = request.headers.get("X-Admin-Token", "")
    if not hmac.compare_digest(given.encode(), token.encode()):
        raise HTTPException(401, "admin token required")


bot = TelegramBot(analyze_image, tryon, create_order, OrderIn)

_FIELD_MESSAGES = {
    "skus": "Your basket is empty. Add at least one product.",
    "name": "Please enter your name (up to 120 characters).",
    "phone": "That phone number is too long.",
    "email": "That email is too long.",
    "scan_id": "Please analyze a photo first.",
    "sku": "Please pick a shade to try on.",
    "scores": "The skin scores sent with this request are invalid. Please analyze your photo again.",
}


@app.exception_handler(RequestValidationError)
async def friendly_validation(_: Request, exc: RequestValidationError) -> JSONResponse:
    """422s as one plain sentence the UI can show as-is (FastAPI's default is a JSON list)."""
    messages = []
    for err in exc.errors():
        loc = [str(x) for x in err.get("loc", ()) if x != "body"]
        if err.get("type") == "json_invalid":
            msg = "The request body must be valid JSON."
        elif loc and loc[0] == "skus" and err.get("type") == "too_long":
            msg = "That's too many products for one order (30 at most)."
        elif loc and loc[0] == "skus" and err.get("type") != "too_short":
            msg = "One of the products is no longer in the catalog. Please reload the page."
        else:
            msg = next((_FIELD_MESSAGES[part] for part in loc if part in _FIELD_MESSAGES),
                       f"{'.'.join(loc) or 'request'}: {err.get('msg', 'invalid value')}")
        if msg not in messages:
            messages.append(msg)
    return JSONResponse({"detail": " ".join(messages) or "Invalid request."}, status_code=422)


@app.get("/healthz")
def healthz() -> dict:
    return {"status": "ok", "youcam": "mock" if youcam.mock else "live"}


@app.get("/version")
def version() -> dict:
    return {"version": VERSION, "commit": os.getenv("GIT_COMMIT", "unknown"),
            "youcam": {"mode": "mock" if youcam.mock else "live", "base_url": youcam.base_url,
                       "api_calls": youcam.calls}, "telegram": bot.enabled,
            "n8n": bool(os.getenv("N8N_WEBHOOK_URL"))}


@app.get("/")
def index() -> FileResponse:
    return FileResponse(Path(__file__).parent / "static" / "index.html")


SAMPLE_FACE = Path(__file__).parent.parent / "docs" / "stock-face" / "stock-face.jpg"


@app.get("/sample.jpg")
def sample_face() -> FileResponse:
    """Licensed stock portrait (Unsplash, Jake Nackos) so visitors can try the flow without a selfie."""
    if not SAMPLE_FACE.exists():
        raise HTTPException(404, "sample photo not bundled")
    return FileResponse(SAMPLE_FACE, media_type="image/jpeg")


@app.get("/catalog")
def catalog() -> dict:
    return {"products": rec.CATALOG}


@app.post("/analyze")
def analyze(body: AnalyzeIn) -> dict:
    if not body.image_base64 and not body.image_url:
        raise HTTPException(422, "Please choose a photo first.")
    image = _decode_b64(body.image_base64) if body.image_base64 else None
    if image is None:
        _check_url(body.image_url)
    content_type = check_image(image) if image is not None else body.content_type
    return analyze_image(image, body.image_url if not image else None, content_type)


@app.post("/tryon")
def tryon_endpoint(body: TryOnIn) -> dict:
    return tryon(body.scan_id, body.sku, body)


@app.post("/shade")
def shade_endpoint(body: ShadeIn) -> dict:
    return shade_match(body)


@app.post("/simulate")
def simulate_endpoint(body: SimulateIn) -> dict:
    return simulate(body)


@app.post("/orders", status_code=201)
def orders(body: OrderIn) -> dict:
    lead, created = create_order(body)
    return {"created": created, "lead": lead}


@app.get("/leads")
def leads(request: Request, min_score: int = 0) -> dict:
    require_admin(request)
    items = [lead.__dict__ for lead in store.list(min_score)]
    return {"count": len(items), "leads": items}


@app.get("/leads/{lead_id}")
def lead(lead_id: str, request: Request) -> dict:
    require_admin(request)  # before parsing, so a bad id can't reveal that the route exists
    found = store.get(int(lead_id)) if lead_id.isdigit() else None
    if not found:
        raise HTTPException(404, "lead not found")
    return found.__dict__


@app.post("/telegram/webhook")
async def telegram_webhook(request: Request) -> dict:
    secret = os.getenv("TELEGRAM_WEBHOOK_SECRET")
    if secret and request.headers.get("X-Telegram-Bot-Api-Secret-Token") != secret:
        raise HTTPException(403, "bad secret")
    try:
        update = await request.json()
    except ValueError:
        raise HTTPException(400, "update must be JSON") from None
    if not isinstance(update, dict):
        raise HTTPException(400, "update must be a JSON object")
    return bot.handle(update)
