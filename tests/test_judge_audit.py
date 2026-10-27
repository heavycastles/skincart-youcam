"""Fixes from a judge-style pass on prod with non-sample photos (Oct 27): resolution limits, cut-off uploads,
zoom-out reframing, every focus area covered by the basket, honest shade match at the ends of the range."""
import base64
import re
import struct
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import main, shade
from app import recommend as rec
from app.main import app
from app.telegram import pick_photo_size
from app.youcam import SkinConcern, YouCamError

client = TestClient(app)
HTML = (Path(__file__).resolve().parent.parent / "app" / "static" / "index.html").read_text()
FACE = (Path(__file__).resolve().parent.parent / "docs" / "stock-face" / "stock-face.jpg").read_bytes()


def jpeg(w: int, h: int, end: bool = True) -> bytes:
    sof = b"\xff\xc0\x00\x11\x08" + struct.pack(">HH", h, w) + b"\x03" + b"\x01\x11\x00" * 3
    return b"\xff\xd8" + sof + b"\xff\xda\x00\x02" + b"scan data" + (b"\xff\xd9" if end else b"")


def png(w: int, h: int, end: bool = True) -> bytes:
    head = b"\x89PNG\r\n\x1a\n" + struct.pack(">I", 13) + b"IHDR" + struct.pack(">II", w, h) + b"\x08\x02\x00\x00\x00"
    return head + b"IDAT data" + (b"\x00\x00\x00\x00IEND\xaeB`\x82" if end else b"")


def _post(data: bytes):
    calls = main.youcam.calls
    r = client.post("/analyze", json={"image_base64": base64.b64encode(data).decode()})
    assert main.youcam.calls == calls  # rejected before any YouCam call: no units spent
    return r


def test_real_face_photo_still_passes_the_checks():
    assert main.check_image(FACE) == "image/jpeg"
    assert main.check_image(jpeg(1600, 1067)) == "image/jpeg" and main.check_image(png(1080, 1919)) == "image/png"


@pytest.mark.parametrize("data", [jpeg(2048, 1365), jpeg(1365, 2048), png(1920, 1080), jpeg(4032, 3024)])
def test_photos_too_big_for_makeup_try_on_are_rejected_with_their_size(data):
    with pytest.raises(main.HTTPException) as e:
        main.check_image(data)
    assert e.value.status_code == 422 and "px" in e.value.detail and "1920" in e.value.detail
    assert "MB" not in e.value.detail


@pytest.mark.parametrize("data", [jpeg(800, 1000, end=False), png(800, 1000, end=False),
                                  b"\xff\xd8\xff\xe0\x00\x10JFIF\x00" + b"\x00" * 290, b"\x89PNG\r\n\x1a\n\x00\x00"])
def test_cut_off_or_headerless_uploads_fail_fast_instead_of_timing_out_at_youcam(data, monkeypatch):
    monkeypatch.setattr(main.youcam, "mock", False)
    r = _post(data)
    assert r.status_code == 415 and "damaged or only partly uploaded" in r.json()["detail"]


def test_youcam_resolution_error_talks_about_pixels_not_megabytes():
    e = main.youcam_http_error(YouCamError("too big", code="error_exceed_max_image_size"))
    assert e.status_code == 413 and "resolution" in e.detail and "1920" in e.detail and "MB" not in e.detail
    e = main.youcam_http_error(YouCamError("oob", code="error_src_face_out_of_bound"))
    assert "Zoom out" in e.detail


def test_telegram_uses_the_largest_photo_size_youcam_accepts():
    sizes = [{"file_id": "s", "width": 320, "height": 240}, {"file_id": "m", "width": 1280, "height": 960},
             {"file_id": "l", "width": 2560, "height": 1920}]
    assert pick_photo_size(sizes)["file_id"] == "m"
    assert pick_photo_size(sizes[:2])["file_id"] == "m"
    assert pick_photo_size([{"file_id": "only", "width": 4000, "height": 3000}])["file_id"] == "only"


def test_browser_crop_stays_under_the_try_on_limit_and_can_zoom_out():
    cap = int(re.search(r"MAX_SEND=(\d+)", HTML).group(1))
    assert cap < 1920 and "MAX_SEND/Math.max(sw,sh)" in HTML and "2048/" not in HTML
    zmin = float(re.search(r"ZMIN=([\d.]+)", HTML).group(1))
    slider_min = int(re.search(r'id="zoom" min="(\d+)"', HTML).group(1))
    assert zmin < 1 and slider_min == round(zmin * 100)
    assert "framing.zoom=Math.max(ZMIN," in HTML and "(W-w)/2" in HTML and "(H-h)/2" in HTML  # centered, no gray band


OLDER_DEEP_SKIN = {"texture": 56, "eye_bag": 57, "wrinkle": 58, "radiance": 59, "firmness": 63, "moisture": 64,
                   "pore": 72, "dark_circle_v2": 76, "age_spot": 95, "acne": 95, "oiliness": 98, "redness": 99}


def _scores(values: dict) -> list[SkinConcern]:
    return [SkinConcern(k, v, 0.0, []) for k, v in values.items()]


def test_puffy_eyes_focus_area_gets_the_eye_gel_without_dropping_the_moisturizer():
    basket = rec.recommend(_scores(OLDER_DEEP_SKIN))
    skus = [b["sku"] for b in basket]
    assert "SC-EYE-06" in skus and "SC-MST-07" in skus and "SC-SPF-09" in skus and len(basket) <= rec.MAX_BASKET


def test_every_focus_area_is_covered_one_product_per_step():
    import random
    rng = random.Random(7)  # noqa: S311 - reproducible test data
    targets = {p["sku"]: set(p["targets"]) for p in rec.CATALOG}
    for _ in range(1500):
        scores = _scores({k: rng.randint(20, 100) for k in OLDER_DEEP_SKIN})
        basket = rec.recommend(scores)
        assert len(basket) <= rec.MAX_BASKET and len({b["category"] for b in basket}) == len(basket)
        assert any(b["category"] == "spf" for b in basket)
        for c in rec.concerns(scores):
            assert any(c["type"] in targets[b["sku"]] for b in basket), (c, [b["sku"] for b in basket])


@pytest.mark.parametrize(("skin", "side"), [("#2f1613", "deeper"), ("#3e201d", "deeper"), ("#fff4ee", "lighter")])
def test_shade_match_says_when_skin_is_beyond_the_range(skin, side):
    m = shade.match({"skin_color": skin})
    assert m["out_of_range"] == side and m["match"]["delta_e"] > shade.OUT_OF_RANGE_DE


@pytest.mark.parametrize("skin", ["#e8b89a", "#8d5524", "#5a3a2a", "#f6e3d6"])
def test_shade_inside_the_range_is_not_flagged(skin):
    assert shade.match({"skin_color": skin})["out_of_range"] is None


def test_page_shows_out_of_range_honestly():
    assert "Closest we stock" in HTML and "than our ${r.out_of_range==='deeper'?'deepest':'lightest'} shade" in HTML
