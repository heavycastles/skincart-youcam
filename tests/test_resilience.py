"""YouCam slow, busy or flaky; double clicks; slow photo links. None of it may waste a paid task or hang a request."""

import base64
import io
import threading
import time
import urllib.error
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import main
from app import youcam as yc
from app.main import app

client = TestClient(app)
FACE = (Path(__file__).resolve().parent.parent / "docs" / "stock-face" / "stock-face.jpg").read_bytes()
B64 = base64.b64encode(FACE).decode()


@pytest.fixture
def live(monkeypatch):
    monkeypatch.setattr(main.youcam, "mock", False)
    monkeypatch.setattr(main.youcam, "upload", lambda image, ct: "FID")
    main.scans.clear()
    main.rejected.clear()
    yield main.youcam
    main.scans.clear()
    main.rejected.clear()


def _task_api(poll_errors):
    """Fake _request: create succeeds, then the listed poll errors, then success."""
    errors, gets = list(poll_errors), []

    def fake(method, url, body=None, headers=None):
        if method == "POST":
            return {"data": {"task_id": "T"}}
        gets.append(url)
        if errors:
            raise yc.YouCamError("poll hiccup", errors.pop(0))
        return {"data": {"task_status": "success", "results": {"output": [{"type": "pore", "ui_score": 61}]}}}
    return fake, gets


@pytest.mark.parametrize("code", ["http_429", "http_503", "network", "timeout"])
def test_a_hiccup_while_polling_does_not_throw_away_the_queued_task(monkeypatch, code):
    c = yc.YouCamClient(api_key="k", mock=False, poll_interval=0, timeout=5)
    fake, gets = _task_api([code, code])
    monkeypatch.setattr(c, "_request", fake)
    assert [s.ui_score for s in c.skin_analysis(url="https://x/y.jpg")] == [61]
    assert len(gets) == 3


def test_a_real_poll_error_still_surfaces(monkeypatch):
    c = yc.YouCamClient(api_key="k", mock=False, poll_interval=0, timeout=5)
    fake, _ = _task_api(["http_404"])
    monkeypatch.setattr(c, "_request", fake)
    with pytest.raises(yc.YouCamError) as e:
        c.skin_analysis(url="https://x/y.jpg")
    assert e.value.code == "http_404"


def test_polling_through_hiccups_still_respects_the_time_budget(monkeypatch):
    c = yc.YouCamClient(api_key="k", mock=False, poll_interval=0.02, timeout=0.2)
    fake, _ = _task_api(["http_503"] * 10_000)
    monkeypatch.setattr(c, "_request", fake)
    started = time.monotonic()
    with pytest.raises(yc.YouCamError):
        c.skin_analysis(url="https://x/y.jpg")
    assert time.monotonic() - started < 1


class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _urlopen_429_then_ok(n429, retry_after="1"):
    calls = []

    def fake(req, timeout):
        calls.append(req.get_method())
        if len(calls) <= n429:
            raise urllib.error.HTTPError(req.full_url, 429, "Too Many Requests", {"Retry-After": retry_after},
                                         io.BytesIO(b'{"status":429}'))
        return _Resp(b'{"data":{"task_id":"T"}}')
    return fake, calls


def test_rate_limited_create_waits_briefly_and_resends(monkeypatch):
    fake, calls = _urlopen_429_then_ok(1, "2")
    slept = []
    monkeypatch.setattr(yc.urllib.request, "urlopen", fake)
    monkeypatch.setattr(yc.time, "sleep", slept.append)
    c = yc.YouCamClient(api_key="k", mock=False, timeout=40)
    assert c._request("POST", c.base_url + "/s2s/v2.0/task/skin-analysis", {})["data"]["task_id"] == "T"
    assert calls == ["POST", "POST"] and slept == [2.0]


def test_rate_limit_gives_up_when_the_budget_is_short_or_retries_run_out(monkeypatch):
    fake, calls = _urlopen_429_then_ok(99, "60")
    monkeypatch.setattr(yc.urllib.request, "urlopen", fake)
    monkeypatch.setattr(yc.time, "sleep", lambda s: None)
    c = yc.YouCamClient(api_key="k", mock=False, timeout=40)
    with pytest.raises(yc.YouCamError) as e:
        c._request("POST", c.base_url + "/x", {})
    assert e.value.code == "http_429" and len(calls) == 1 + yc.RATE_LIMIT_RETRIES  # Retry-After capped at 4 s
    short = yc.YouCamClient(api_key="k", mock=False, timeout=8)
    calls.clear()
    short.begin()
    try:
        with pytest.raises(yc.YouCamError):
            short._request("POST", short.base_url + "/x", {})
    finally:
        short.end()
    assert len(calls) == 1  # no time left to wait: answer "busy, try again" at once


@pytest.mark.parametrize(("code", "retried"), [
    ("http_429", False), ("http_503", False), ("network", False), ("timeout", False), ("bad_response", False),
    ("error_no_face", False), ("http_404", True), ("error_file_not_found", True),
])
def test_second_paid_attempt_only_when_the_uploaded_file_may_have_expired(live, monkeypatch, code, retried):
    monkeypatch.setattr(live, "skin_analysis", lambda **_: [yc.SkinConcern("pore", 70, 50.0, [])])
    scan = client.post("/analyze", json={"image_base64": B64}).json()
    tries = []

    def vto(effects, **kw):
        tries.append(kw.get("file_id"))
        if len(tries) == 1:
            raise yc.YouCamError("x", code)
        return "https://cdn/out.jpg"
    monkeypatch.setattr(live, "makeup_vto", vto)
    r = client.post("/tryon", json={"scan_id": scan["scan_id"], "sku": "SC-LIP-10"})
    assert (r.status_code == 200) is retried
    assert tries == (["FID", None] if retried else ["FID"])


def _together(n, fn):
    out, threads = [None] * n, []
    for i in range(n):
        threads.append(threading.Thread(target=lambda i=i: out.__setitem__(i, fn())))
    for t in threads:
        t.start()
    for t in threads:
        t.join(10)
    return out


def test_double_click_on_analyze_starts_only_one_paid_analysis(live, monkeypatch):
    calls = []
    monkeypatch.setattr(live, "skin_analysis", lambda **_: calls.append(1) or time.sleep(0.3) or [
        yc.SkinConcern("pore", 70, 50.0, [])])
    rs = _together(3, lambda: client.post("/analyze", json={"image_base64": B64}))
    assert [r.status_code for r in rs] == [200] * 3 and len(calls) == 1
    assert sorted(r.json()["cached"] for r in rs) == [False, True, True]
    assert sum(r.json()["units"] for r in rs) == main.UNITS["skin_analysis"]


@pytest.mark.parametrize(("path", "attr", "body"), [
    ("/tryon", "makeup_vto", {"sku": "SC-LIP-10"}),
    ("/shade", "skin_tone", {}),
    ("/simulate", "skin_simulation", {"skus": ["SC-SER-03"]}),
])
def test_double_click_on_paid_extras_starts_only_one_task(live, monkeypatch, path, attr, body):
    monkeypatch.setattr(live, "skin_analysis", lambda **_: [yc.SkinConcern("pore", 20, 50.0, []),
                                                            yc.SkinConcern("texture", 25, 50.0, [])])
    scan = client.post("/analyze", json={"image_base64": B64}).json()
    calls = []
    tones = {"skin_color": "#C89A7E", "lip_color": "#B5656A", "eye_color": "#4A3326", "hair_color": "#2B1D16"}
    result = tones if attr == "skin_tone" else "https://cdn/out.jpg"
    monkeypatch.setattr(live, attr, lambda *a, **k: calls.append(1) or time.sleep(0.3) or result)
    rs = _together(3, lambda: client.post(path, json={"scan_id": scan["scan_id"], **body}))
    assert [r.status_code for r in rs] == [200] * 3, [r.text for r in rs]
    assert len(calls) == 1 and sorted(r.json()["cached"] for r in rs) == [False, True, True]
    assert not main._inflight  # locks are cleaned up


def test_a_rejected_photo_is_not_sent_to_youcam_twice(live, monkeypatch):
    calls = []

    def no_face(**_):
        calls.append(1)
        raise yc.YouCamError("x", "error_no_face")
    monkeypatch.setattr(live, "skin_analysis", no_face)
    first = client.post("/analyze", json={"image_base64": B64})
    again = client.post("/analyze", json={"image_base64": B64})
    assert first.status_code == again.status_code == 422 and first.json() == again.json()
    assert again.headers["X-SkinCart-Error"] == "error_no_face" and len(calls) == 1


def test_busy_youcam_is_not_remembered_as_a_bad_photo(live, monkeypatch):
    calls = []

    def busy(**_):
        calls.append(1)
        raise yc.YouCamError("x", "http_429")
    monkeypatch.setattr(live, "skin_analysis", busy)
    for _ in range(2):
        r = client.post("/analyze", json={"image_base64": B64})
        assert r.status_code == 503 and "try again" in r.json()["detail"]
    assert len(calls) == 2


def test_a_trickling_photo_link_is_cut_off_at_the_deadline(live, monkeypatch):
    class Trickle:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self, n):
            time.sleep(0.05)
            return b"\xff" * 10

    monkeypatch.setattr(main, "_public_host", lambda url: True)
    monkeypatch.setattr(main, "_open_url", lambda url: Trickle())
    monkeypatch.setattr(main, "PHOTO_LINK_TIMEOUT", 0.3)
    started = time.monotonic()
    r = client.post("/analyze", json={"image_url": "https://example.com/slow.jpg"})
    assert r.status_code == 422 and "too slow" in r.json()["detail"]
    assert time.monotonic() - started < 2


def test_ui_offers_try_again_and_keeps_uploads_under_the_vercel_body_limit():
    html = (Path(main.__file__).parent / "static" / "index.html").read_text()
    assert 'id="retry"' in html and ">Try again</button>" in html
    assert "MAX_B64=3e6" in html and "run(encodeJpeg(c)" in html
    assert 3e6 * 1.01 < 4.5e6  # base64 JSON body stays under Vercel's 4.5 MB request limit
