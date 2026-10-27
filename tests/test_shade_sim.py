"""Shade match (Facial Color Tones), Skin Simulation of the basket, AM/PM plan."""

import base64
import json
import re
import struct
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import main, shade
from app import recommend as rec
from app import youcam as yc
from app.main import app
from tests.test_youcam import FakeHTTP

client = TestClient(app)
def jpeg(tag: bytes, w: int = 600, h: int = 800) -> bytes:
    """Smallest structurally complete JPEG: SOI, SOF0 (size), SOS, payload, EOI."""
    sof = b"\xff\xc0\x00\x11\x08" + struct.pack(">HH", h, w) + b"\x03" + b"\x01\x11\x00" * 3
    return b"\xff\xd8" + sof + b"\xff\xda\x00\x02" + tag + b"\xff\xd9"


IMG = base64.b64encode(jpeg(b"shade sim selfie")).decode()
# Real Skin Analysis scores of the licensed stock face (docs/live-proof-response.json)
LIVE = [{"type": c["type"], "ui_score": c["ui_score"]}
        for c in json.loads(Path("docs/live-proof-response.json").read_text())["skin_concerns"]
        if c["type"] in rec.LABELS]
ROUTINE = ["SC-CLN-01", "SC-SER-02", "SC-MST-07", "SC-NGT-05", "SC-SPF-09"]


# ---------- shade math ----------
def test_catalog_shade_range_is_consistent():
    shades = shade.foundation_shades()
    assert len(shades) == 12 and len({p["sku"] for p in shades}) == 12
    for p in shades:  # every label agrees with the hue-angle rule the matcher uses
        assert shade.undertone(p["shade"]["hex"]) == p["shade"]["undertone"], p["sku"]
        assert p["vto"]["category"] == "foundation" and p["vto"]["palettes"][0]["color"] == p["shade"]["hex"]
    assert {p["shade"]["undertone"] for p in shades} == {"cool", "neutral", "warm"}
    depths = {shade.depth(p["shade"]["hex"])["label"] for p in shades}
    assert {"very light", "deep", "very deep"} <= depths  # inclusive range, light to deep


def test_live_stock_face_color_matches_natural_with_neighbors():
    # skin/lip colors returned by the live Facial Color Tones Analyzer for the stock face (22 Oct 2026)
    r = shade.match({"skin_color": "#bf9c83", "lip_color": "#d1877d", "eye_color_name": "Brown"}, LIVE)
    assert r["undertone"] == "warm" and r["depth"]["label"] == "light"
    assert r["match"]["sku"] == "SC-FND-180" and r["match"]["delta_e"] < 10
    assert [n["sku"] for n in r["neighbors"]] == ["SC-FND-160", "SC-FND-220"]  # lighter, deeper
    assert sum(x["is_match"] for x in r["range"]) == 1 and len(r["range"]) == 12
    assert r["formula"]["finish"] == "dewy" and "dryness scored 73" in r["formula"]["finish_why"]
    best = [x["family"] for x in r["lips"] if x["best"]]
    assert best == ["nude", "coral"] and r["lips"][-1]["family"] == "berry"  # nude ~ own lip color, warm coral


def test_deep_and_cool_skin_get_deep_and_cool_options():
    deep = shade.match({"skin_color": "#5a3b2c"})
    assert deep["match"]["sku"] in {"SC-FND-410", "SC-FND-380"} and deep["depth"]["label"] in {"deep", "very deep"}
    cool = shade.match({"skin_color": "#f1d4c8"})
    assert cool["undertone"] == "cool" and cool["match"]["sku"] == "SC-FND-110"
    assert [x["family"] for x in cool["lips"][:2]] in (["rose", "berry"], ["berry", "rose"])


def test_bad_color_raises():
    with pytest.raises(ValueError):
        shade.match({"skin_color": "not-a-color"})


@pytest.mark.parametrize("scores,finish,coverage", [
    ([{"type": "moisture", "ui_score": 60}], "dewy", "sheer to light"),
    ([{"type": "oiliness", "ui_score": 60}], "matte", "sheer to light"),
    ([{"type": "moisture", "ui_score": 60}, {"type": "oiliness", "ui_score": 60}], "satin", "sheer to light"),
    ([{"type": "redness", "ui_score": 55}], "natural", "medium, buildable"),
])
def test_formula_from_skin_scores(scores, finish, coverage):
    f = shade.finish_and_coverage(scores)
    assert (f["finish"], f["coverage"]) == (finish, coverage)


def test_nude_lip_boosted_when_close_to_natural_lip():
    plain = {r["sku"]: r["fit"] for r in shade.rank_lips("warm", None)}
    near = {r["sku"]: r["fit"] for r in shade.rank_lips("warm", "#c48a7e")}
    assert near["SC-LIP-15"] == plain["SC-LIP-15"] + 1


# ---------- Skin Simulation plan ----------
def test_simulation_targets_only_what_the_basket_treats():
    plan = rec.simulation_plan(LIVE, ROUTINE)
    assert plan["params"] == {"pores": 0.4, "texture": 0.35, "wrinkle": 0.3}  # pores 70, dryness 73, lines 77/78
    assert set(plan["params"]) <= set(yc.SIM_KEYS)
    assert all(c["ui_score"] < rec.CONCERN_THRESHOLD and c["products"] for c in plan["concerns"])
    # caffeine eye gel added -> puffy eyes (76) joins the preview
    assert rec.simulation_plan(LIVE, ROUTINE + ["SC-EYE-06"])["params"]["eye_bags"] == 0.3
    # SPF alone targets lines/spots/redness/dullness; makeup never counts
    assert rec.simulation_plan(LIVE, ["SC-LIP-10", "SC-FND-180"])["params"] == {}


def test_simulation_intensity_is_capped_and_healthy_skin_gets_light_touch():
    assert rec.sim_intensity(10) == rec.SIM_MAX and rec.sim_intensity(79) == 0.25 and rec.sim_intensity(95) == 0.2
    healthy = [{"type": t, "ui_score": 92} for t in rec.LABELS]
    plan = rec.simulation_plan(healthy, ROUTINE)
    assert 0 < len(plan["concerns"]) <= 3 and set(plan["params"].values()) == {0.2}


# ---------- AM / PM plan ----------
def test_schedule_separates_exfoliants_and_flags_missing_spf():
    s = rec.schedule(ROUTINE + ["SC-LIP-10"])
    assert "Gentle Salicylic Cleanser 2%" in s["am"] and "Gentle Salicylic Cleanser 2%" not in s["pm"]
    assert "Retinal 0.05% Night Cream" in s["pm"] and "Invisible Fluid SPF 50" in s["am"]
    assert all("Lipstick" not in n for n in s["am"] + s["pm"])
    assert any("two exfoliants" in n for n in s["notes"])
    no_spf = rec.schedule(["SC-SER-03"])
    assert no_spf["am"] == no_spf["pm"] == ["Hyaluronic Acid Hydra Serum"] and "No SPF" in no_spf["notes"][-1]


def test_web_ui_uses_the_same_am_pm_rules():
    html = Path("app/static/index.html").read_text()
    when = json.loads(re.search(r"const WHEN=(\{.*?\});", html).group(1))
    assert when == rec.WHEN


# ---------- API ----------
def _scan():
    return client.post("/analyze", json={"image_base64": IMG}).json()


def test_shade_endpoint_and_cache():
    scan = _scan()
    r = client.post("/shade", json={"scan_id": scan["scan_id"]})
    assert r.status_code == 200
    body = r.json()
    assert body["match"]["sku"].startswith("SC-FND-") and body["mode"] == "mock" and body["cached"] is False
    again = client.post("/shade", json={"scan_id": scan["scan_id"]}).json()
    assert again["cached"] is True and again["units"] == 0 and again["match"] == body["match"]
    vto = client.post("/tryon", json={"scan_id": scan["scan_id"], "sku": body["match"]["sku"]})
    assert vto.status_code == 200 and vto.json()["image_url"]


def test_simulate_endpoint_cache_and_basket_changes():
    scan = _scan()
    skus = [b["sku"] for b in scan["basket"]]
    first = client.post("/simulate", json={"scan_id": scan["scan_id"], "skus": skus}).json()
    assert first["image_url"] and first["params"] and first["cached"] is False
    assert client.post("/simulate", json={"scan_id": scan["scan_id"], "skus": skus}).json()["cached"] is True
    assert client.post("/simulate", json={"scan_id": scan["scan_id"], "skus": ["SC-LIP-10"]}).status_code == 422
    assert client.post("/simulate", json={"scan_id": scan["scan_id"], "skus": ["NOPE"]}).status_code == 400
    assert client.post("/simulate", json={"scan_id": "gone", "skus": skus}).status_code == 404
    assert client.post("/simulate", json={"scan_id": scan["scan_id"], "skus": []}).status_code == 422


def test_fresh_instance_uses_resent_file_id_and_scores(monkeypatch):
    """Serverless: a new instance never saw /analyze -> the browser re-sends file_id + scores, no re-analysis."""
    scan = _scan()
    main.scans.clear()
    seen = {}

    def fake_sim(params, **kw):
        seen.update(kw, params=params)
        return "https://cdn/sim.png"

    monkeypatch.setattr(main.youcam, "skin_simulation", fake_sim)
    r = client.post("/simulate", json={"scan_id": scan["scan_id"], "file_id": "FID", "skus": ROUTINE,
                                       "scores": LIVE})
    assert r.status_code == 200 and seen["file_id"] == "FID" and seen["params"] == r.json()["params"]
    bad = client.post("/simulate", json={"scan_id": "x2", "file_id": "F", "skus": ROUTINE,
                                         "scores": [{"type": "pore", "ui_score": 400}]})
    assert bad.status_code == 422 and "skin scores" in bad.json()["detail"]


def test_live_client_tone_and_simulation_requests(monkeypatch):
    c = yc.YouCamClient(api_key="k", mock=False, poll_interval=0)
    fake = FakeHTTP({"color": {"skin_color": "#bf9c83", "lip_color": "#d1877d", "eye_color_name": "Brown"},
                     "face_quality": {"has_face": True}})
    monkeypatch.setattr(c, "_request", fake)
    tones = c.skin_tone(file_id="FID")
    assert tones["skin_color"] == "#bf9c83" and fake.calls[0][1].endswith("/s2s/v2.0/task/skin-tone-analysis")
    assert fake.calls[0][2] == {"src_file_id": "FID", "face_angle_strictness_level": "medium"}
    c2 = yc.YouCamClient(api_key="k", mock=False, poll_interval=0)
    fake2 = FakeHTTP({"url": "https://cdn/sim.png"})
    monkeypatch.setattr(c2, "_request", fake2)
    assert c2.skin_simulation({"pores": 0.4, "oiliness": 0.9, "acne": 0}, file_id="FID") == "https://cdn/sim.png"
    assert fake2.calls[0][2] == {"src_file_id": "FID", "pores": 0.4}  # oiliness (adds shine) and zeros dropped
    with pytest.raises(ValueError):
        c2.skin_simulation({"acne": 0})


def test_live_tone_without_skin_color_is_an_error(monkeypatch):
    c = yc.YouCamClient(api_key="k", mock=False, poll_interval=0)
    monkeypatch.setattr(c, "_request", FakeHTTP({"color": {}}))
    with pytest.raises(yc.YouCamError):
        c.skin_tone(file_id="FID")
