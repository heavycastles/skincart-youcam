"""Judge-facing edge cases: bad uploads, YouCam failures, order validation, bounded caches."""

import base64
import struct
import urllib.error
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import main
from app import youcam as yc
from app.main import app

client = TestClient(app)
FACE = (Path(__file__).resolve().parent.parent / "docs" / "stock-face" / "stock-face.jpg").read_bytes()


def b64(data: bytes) -> str:
    return base64.b64encode(data).decode()


def png_header(w: int, h: int) -> bytes:
    return b"\x89PNG\r\n\x1a\n" + struct.pack(">I", 13) + b"IHDR" + struct.pack(">II", w, h) + b"\x08\x02\x00\x00\x00"


def test_image_sniffing_reads_real_format_and_size():
    assert main.image_info(FACE) == ("jpeg", 900, 1372)
    assert main.image_info(png_header(640, 800)) == ("png", 640, 800)
    assert main.image_info(b"RIFF\x00\x00\x00\x00WEBPVP8 ")[0] == "webp"
    assert main.image_info(b"\x00\x00\x00\x18ftypheic....")[0] == "heic"
    assert main.image_info(b"%PDF-1.7")[0] is None


@pytest.mark.parametrize(("data", "status", "words"), [
    (b"hello, I am a text file", 415, "isn't a photo"),
    (b"RIFF\x00\x00\x00\x00WEBPVP8 data", 415, "WEBP"),
    (b"\x00\x00\x00\x18ftypheic data", 415, "HEIC"),
    (png_header(300, 400), 422, "too small (300x400"),
])
def test_bad_uploads_rejected_before_any_youcam_call(data, status, words):
    calls = main.youcam.calls
    r = client.post("/analyze", json={"image_base64": b64(data)})
    assert r.status_code == status and words in r.json()["detail"]
    assert main.youcam.calls == calls


def test_empty_photo_and_missing_photo_messages():
    assert client.post("/analyze", json={"image_base64": ""}).json()["detail"] == "Please choose a photo first."
    r = client.post("/analyze", json={"image_url": None})
    assert r.status_code == 422 and isinstance(r.json()["detail"], str)


@pytest.fixture
def live(monkeypatch):
    """Pretend the deployed (live) client is configured; the YouCam calls themselves are faked per test."""
    monkeypatch.setattr(main.youcam, "mock", False)
    monkeypatch.setattr(main.youcam, "upload", lambda image, ct: "FID")
    main.scans.clear()
    yield main.youcam
    main.scans.clear()


@pytest.mark.parametrize(("code", "status", "words"), [
    ("error_src_face_too_small", 422, "fill most of the photo"),
    ("error_no_face", 422, "couldn't find a face"),
    ("error_lighting_dark", 422, "too dark"),
    ("timeout", 504, "longer than usual"),
    ("http_429", 503, "busy"),
    ("http_500", 502, "sample photo"),
])
def test_youcam_errors_become_plain_advice_without_raw_details(live, monkeypatch, code, status, words):
    raw = f"POST https://yce-api-01.makeupar.com/s2s/v2.0/task/skin-analysis -> 400: {{\"error\":\"{code}\"}}"

    def boom(**_):
        raise yc.YouCamError(raw, code)
    monkeypatch.setattr(live, "skin_analysis", boom)
    r = client.post("/analyze", json={"image_base64": b64(FACE)})
    assert r.status_code == status and words in r.json()["detail"]
    assert "makeupar" not in r.text and "s2s" not in r.text
    assert r.headers["X-SkinCart-Error"] == code


def test_tryon_errors_are_friendly_too(live, monkeypatch):
    monkeypatch.setattr(live, "skin_analysis", lambda **_: [yc.SkinConcern("pore", 70, 50.0, [])])
    scan = client.post("/analyze", json={"image_base64": b64(FACE)}).json()

    def slow(*_, **__):
        raise yc.YouCamError("makeup-vto timed out (last status running)", "timeout")
    monkeypatch.setattr(live, "makeup_vto", slow)
    r = client.post("/tryon", json={"scan_id": scan["scan_id"], "sku": "SC-LIP-10"})
    assert r.status_code == 504 and "longer than usual" in r.json()["detail"]
    assert client.post("/tryon", json={"scan_id": "gone", "sku": "SC-LIP-10"}).json()["detail"].startswith(
        "This analysis has expired")


def test_http_error_code_and_network_timeouts_are_classified(monkeypatch):
    c = yc.YouCamClient(api_key="k", mock=False)

    def http_err(req, timeout):
        raise urllib.error.HTTPError(req.full_url, 400, "bad", {}, __import__("io").BytesIO(
            b'{"status":400,"error_code":"error_below_min_image_size"}'))
    monkeypatch.setattr(yc.urllib.request, "urlopen", http_err)
    with pytest.raises(yc.YouCamError) as e:
        c._request("GET", c.base_url + "/x")
    assert e.value.code == "error_below_min_image_size"

    def slow(req, timeout):
        raise urllib.error.URLError(TimeoutError("timed out"))
    monkeypatch.setattr(yc.urllib.request, "urlopen", slow)
    with pytest.raises(yc.YouCamError) as e:
        c._request("GET", c.base_url + "/x")
    assert e.value.code == "timeout"


def test_one_time_budget_covers_upload_and_polling(monkeypatch):
    c = yc.YouCamClient(api_key="k", mock=False, poll_interval=0.01, timeout=0.2)
    monkeypatch.setattr(c, "_request", lambda m, u, b=None, h=None: {"data": {"task_id": "T"}} if m == "POST"
                        else {"data": {"task_status": "running"}})
    c.begin()
    try:
        with pytest.raises(yc.YouCamError) as e:
            c.skin_analysis(url="https://x/y.jpg")
    finally:
        c.end()
    assert e.value.code == "timeout"


def test_order_validation_messages_are_sentences():
    def order(**kw):
        return client.post("/orders", json={"name": "Ann", "skus": ["SC-SPF-09"]} | kw)
    r = order(skus=[])
    assert r.status_code == 422 and r.json()["detail"] == "Your basket is empty. Add at least one product."
    assert "phone number" in order(phone="12").json()["detail"]
    assert order(phone="+998901234567", email="nope@").json()["detail"].startswith("That email")
    assert order(name="").json()["detail"].startswith("Please enter your name")
    r = order(name="   ", email="ann@example.com")
    assert r.status_code == 201 and main.store.get(r.json()["lead"]["id"]).name == "Guest"
    bad = client.post("/orders", content=b"not json", headers={"Content-Type": "application/json"})
    assert bad.status_code == 422 and bad.json()["detail"] == "The request body must be valid JSON."


def test_scan_cache_is_bounded():
    main.scans.clear()
    for i in range(main.MAX_SCANS + 5):
        main.scans[f"s{i}"] = {"result": None}
    assert len(main.scans) == main.MAX_SCANS and "s0" not in main.scans and f"s{main.MAX_SCANS + 4}" in main.scans
    main.scans.clear()


def test_telegram_gets_advice_instead_of_a_crash(monkeypatch):
    def refuse(*_):
        raise main.HTTPException(422, "Move closer: your face should fill most of the photo.")
    monkeypatch.setattr(main.bot, "analyze", refuse)
    res = client.post("/telegram/webhook", json={"message": {"chat": {"id": 5}, "photo": [{"file_id": "x"}]}})
    assert res.status_code == 200 and "Move closer" in res.json()["sent"][0]["text"]


def test_ui_handles_non_json_errors_and_has_accessible_controls():
    html = client.get("/").text
    assert "FALLBACK" in html and "r.json()" in html  # host-level 413/504 pages are plain text
    for needed in ('for="phone"', 'for="email"', 'role="alert"', 'aria-label="Zoom photo"', "dragover",
                   "startFraming", "tryTok"):
        assert needed in html


def test_order_basket_errors_name_the_real_problem():
    def order(skus):
        return client.post("/orders", json={"name": "Ann", "phone": "+998901234567", "skus": skus}).json()["detail"]
    assert order(["SC-SPF-09"] * 31).startswith("That's too many products")
    assert "no longer in the catalog" in order("SC-SPF-09")
    assert "no longer in the catalog" in order([{"sku": 1}])
    assert order([]) == "Your basket is empty. Add at least one product."


def test_ui_accessibility_contract():
    html = client.get("/").text
    # the drop zone's accessible name starts with its visible text (WCAG 2.5.3)
    assert 'aria-label="Drop a selfie here, front-facing, good light, no filters.' in html and "<b>Drop a selfie here</b>" in html
    # polite live region for results, try-on and shade; reduced motion also stops JS smooth scrolling
    assert 'id="announce" class="sr" role="status" aria-live="polite"' in html
    assert "prefers-reduced-motion: reduce" in html and "behavior:'smooth'" not in html
    # card titles stay in heading order (h2 -> h3), no skipped levels
    assert "<h4" not in html
    # the sample button is locked before its photo is fetched, so a double-click is one paid analysis
    handler = html[html.index("$('sample').onclick"):]
    assert handler.index("setBusy(true)") < handler.index("fetch('/sample.jpg')")
