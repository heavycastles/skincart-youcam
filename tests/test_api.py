import base64

from fastapi.testclient import TestClient

from app import main
from app.main import app

client = TestClient(app)
IMG = base64.b64encode(b"\xff\xd8 fake selfie bytes").decode()


def test_health_ui_version():
    assert client.get("/healthz").json() == {"status": "ok", "youcam": "mock"}
    assert "SkinCart" in client.get("/").text
    assert client.get("/version").json()["youcam"]["mode"] == "mock"
    assert len(client.get("/catalog").json()["products"]) >= 10


def test_version_reports_short_commit(monkeypatch):
    monkeypatch.delenv("GIT_COMMIT", raising=False)
    monkeypatch.delenv("VERCEL_GIT_COMMIT_SHA", raising=False)
    assert client.get("/version").json()["commit"] == "unknown"
    monkeypatch.setenv("VERCEL_GIT_COMMIT_SHA", "0123456789abcdef0123456789abcdef01234567")
    assert client.get("/version").json()["commit"] == "0123456"
    monkeypatch.setenv("GIT_COMMIT", "abc1234")  # set at deploy time, wins over Vercel's value
    assert client.get("/version").json()["commit"] == "abc1234"
    monkeypatch.setenv("GIT_COMMIT", "<script>")  # never echo arbitrary text
    monkeypatch.delenv("VERCEL_GIT_COMMIT_SHA")
    assert client.get("/version").json()["commit"] == "unknown"


def test_selfie_to_order_end_to_end():
    r = client.post("/analyze", json={"image_base64": "data:image/jpeg;base64," + IMG})
    assert r.status_code == 200
    scan = r.json()
    assert scan["scores"] and scan["basket"] and scan["tryon"] and scan["cached"] is False
    assert client.post("/analyze", json={"image_base64": IMG}).json()["cached"] is True
    vto = client.post("/tryon", json={"scan_id": scan["scan_id"], "sku": scan["tryon"][0]["sku"]})
    assert vto.status_code == 200 and vto.json()["image_url"]
    o = client.post("/orders", json={"scan_id": scan["scan_id"], "name": "Dilnoza", "phone": "+998 90 123 45 67",
                                     "skus": [b["sku"] for b in scan["basket"]], "source": "telegram"})
    assert o.status_code == 201
    lead = o.json()["lead"]
    assert lead["extra"]["basket"] and lead["score"] >= 50 and "phone" not in lead
    assert lead["extra"]["total"] == round(sum(b["price"] for b in scan["basket"]), 2)
    assert main.store.get(lead["id"]).phone == "+998901234567"
    assert main.store.get(lead["id"]).extra["scan_id"] == scan["scan_id"]
    again = client.post("/orders", json={"name": "D", "phone": "+998901234567", "skus": ["SC-SPF-09"]})
    assert again.json()["created"] is False  # LeadFlow de-dup


def test_validation():
    assert client.post("/analyze", json={}).status_code == 422
    assert client.post("/analyze", json={"image_base64": "%%%"}).status_code == 422
    assert client.post("/tryon", json={"scan_id": "nope", "sku": "SC-LIP-10"}).status_code == 404
    assert client.post("/orders", json={"name": "X", "phone": "+998901112233", "skus": ["BAD"]}).status_code == 400
    assert client.post("/orders", json={"name": "X", "skus": ["SC-SPF-09"]}).status_code == 422
    assert client.get("/leads/9999").status_code == 404
    assert client.get("/leads").status_code == 404  # no ADMIN_TOKEN -> listing does not exist


def test_telegram_flow_offline():
    chat = {"id": 777}
    start = client.post("/telegram/webhook", json={"message": {"chat": chat, "text": "/start"}}).json()
    assert "selfie" in start["sent"][0]["text"]
    res = client.post("/telegram/webhook", json={"message": {"chat": chat, "photo": [{"file_id": "abc"}]}}).json()
    kb = res["sent"][0]["reply_markup"]["inline_keyboard"]
    assert "Suggested routine" in res["sent"][0]["text"] and kb[0][0]["callback_data"].startswith("try:")
    cb = {"callback_query": {"data": kb[0][0]["callback_data"], "message": {"chat": chat}}}
    assert "Try-on ready" in client.post("/telegram/webhook", json=cb).json()["sent"][0]["text"]
    contact = {"message": {"chat": chat, "contact": {"first_name": "Aziz", "phone_number": "+998935556677"}}}
    done = client.post("/telegram/webhook", json=contact).json()["sent"][0]["text"]
    assert "Order #" in done
    leads = [x.__dict__ for x in main.store.list()]
    assert any(x["source"] == "telegram" and x["extra"]["telegram_chat_id"] == 777 for x in leads)


def test_sample_photo_and_score_fields():
    r = client.get("/sample.jpg")
    assert r.status_code == 200 and r.headers["content-type"] == "image/jpeg" and r.content[:2] == b"\xff\xd8"
    scan = client.post("/analyze", json={"image_base64": base64.b64encode(r.content).decode()}).json()
    assert 0 < scan["skin_score"] <= 100 and all("label" in x for x in scan["scores"])


def test_tryon_and_order_survive_a_fresh_serverless_instance(tmp_path, monkeypatch):
    # On Vercel /analyze and /tryon may land on different instances; the browser re-sends what it has.
    monkeypatch.chdir(tmp_path)  # hosts may start the app from another working directory
    img = base64.b64encode(b"\xff\xd8 another fake selfie").decode()
    scan = client.post("/analyze", json={"image_base64": img}).json()
    assert scan["api_calls"] == 0 and "file_id" in scan  # mock mode: no YouCam requests, no upload
    main.scans.clear()
    sku = scan["tryon"][0]["sku"]
    assert client.post("/tryon", json={"scan_id": scan["scan_id"], "sku": sku}).status_code == 404
    bad = client.post("/tryon", json={"scan_id": "0" * 16, "sku": sku, "image_base64": img})
    assert bad.status_code == 400  # image must match the scan id
    vto = client.post("/tryon", json={"scan_id": scan["scan_id"], "sku": sku, "image_base64": img})
    assert vto.status_code == 200 and vto.json()["image_url"] and vto.json()["api_calls"] == 0
    main.scans.clear()
    o = client.post("/orders", json={"scan_id": scan["scan_id"], "name": "Guest", "phone": "+998907770011",
                                     "skus": [sku], "skin_profile": scan["concerns"]})
    assert o.status_code == 201 and o.json()["lead"]["extra"]["skin_profile"] == scan["concerns"]
    assert "SkinCart" in client.get("/").text and client.get("/sample.jpg").status_code == 200


def test_leads_are_not_public(monkeypatch):
    client.post("/orders", json={"name": "Private", "phone": "+998901230000", "email": "p@example.com",
                                 "skus": ["SC-SPF-09"]})
    for path in ("/leads", "/leads/1"):
        assert client.get(path).status_code == 404  # ADMIN_TOKEN unset: route hidden
    monkeypatch.setenv("ADMIN_TOKEN", "s3cret-token")
    for path in ("/leads", "/leads/1"):
        assert client.get(path).status_code == 401
        assert client.get(path, headers={"X-Admin-Token": "wrong"}).status_code == 401
    ok = client.get("/leads", headers={"X-Admin-Token": "s3cret-token"})
    assert ok.status_code == 200 and any(x["phone"] == "+998901230000" for x in ok.json()["leads"])
    assert "+998901230000" not in client.get("/leads").text


def test_order_response_never_echoes_another_customers_data():
    first = client.post("/orders", json={"name": "Victim Name", "phone": "+998909998877",
                                         "email": "victim@example.com", "skus": ["SC-SPF-09"]})
    assert first.status_code == 201
    probe = client.post("/orders", json={"name": "Probe", "phone": "+998 90 999 88 77", "skus": ["SC-LIP-10"]})
    body = probe.json()
    assert body["created"] is False
    text = probe.text
    assert "Victim" not in text and "victim@example.com" not in text and "+998909998877" not in text
    assert [b["sku"] for b in body["lead"]["extra"]["basket"]] == ["SC-LIP-10"]  # only this order
    assert set(body["lead"]) == {"id", "score", "source", "extra"}


def test_version_reports_n8n_only_when_configured(monkeypatch):
    monkeypatch.delenv("N8N_WEBHOOK_URL", raising=False)
    assert client.get("/version").json()["n8n"] is False
    monkeypatch.setenv("N8N_WEBHOOK_URL", "https://n8n.example/webhook/x")
    assert client.get("/version").json()["n8n"] is True


def test_page_does_not_claim_unconfigured_integrations():
    html = client.get("/").text
    # the static markup must be honest by default; stronger wording is only swapped in from /version flags
    meta = html.split('id="leadNote">')[1].split("</div>")[0]
    assert "trigger an n8n alert" not in meta
    footer = html.split("<footer>")[1].split("</footer>")[0]
    assert "runs in the shop's Telegram bot" not in footer
    assert "if(v.n8n)" in html and "if(v.telegram)" in html


def test_security_headers_on_every_response():
    for path in ("/", "/healthz", "/nope"):
        r = client.get(path)
        assert r.headers["x-content-type-options"] == "nosniff"
        assert r.headers["x-frame-options"] == "DENY"
        assert r.headers["referrer-policy"] == "strict-origin-when-cross-origin"


def test_bad_photo_link_is_rejected_before_youcam():
    for url in ("not a url", "ftp://example.com/a.jpg", "javascript:alert(1)", "https://" + "a" * 2100 + ".com"):
        r = client.post("/analyze", json={"image_url": url})
        assert r.status_code == 422, url
        assert "photo link" in r.json()["detail"]
    r = client.post("/tryon", json={"scan_id": "abc", "sku": "x", "image_url": "nope"})
    assert r.status_code == 422


def test_telegram_webhook_rejects_non_object_json():
    assert client.post("/telegram/webhook", content=b"not json",
                       headers={"content-type": "application/json"}).status_code == 400
    assert client.post("/telegram/webhook", json=[1, 2]).status_code == 400


def test_lead_detail_hidden_even_with_bad_id(monkeypatch):
    monkeypatch.delenv("ADMIN_TOKEN", raising=False)
    assert client.get("/leads/abc").status_code == 404
    monkeypatch.setenv("ADMIN_TOKEN", "s3cret-token")
    assert client.get("/leads/abc").status_code == 401
    assert client.get("/leads/abc", headers={"X-Admin-Token": "s3cret-token"}).status_code == 404


def test_public_order_cannot_pose_as_telegram_or_inject_profile():
    r = client.post("/orders", json={"name": "Web", "phone": "+998901112233", "skus": ["SC-SPF-09"],
                                     "source": "telegram", "telegram_chat_id": 12345,
                                     "skin_profile": [{"x": "y"}, {"type": "acne", "ui_score": 999},
                                                      {"type": "moisture", "ui_score": 61, "label": "<b>x</b>"}]})
    assert r.status_code == 201
    lead = r.json()["lead"]
    assert lead["source"] == "web"
    assert lead["extra"]["skin_profile"] == [{"type": "moisture", "label": "dryness", "ui_score": 61,
                                              "severity": "medium"}]
    stored = main.store.get(lead["id"])
    assert stored.source == "web" and stored.extra["telegram_chat_id"] is None


def test_head_requests_on_public_pages():
    for path in ("/", "/healthz", "/version", "/sample.jpg", "/catalog"):
        r = client.head(path)
        assert r.status_code == 200, path
        assert r.headers["x-content-type-options"] == "nosniff"


def _live(monkeypatch):
    monkeypatch.setattr(main.youcam, "mock", False)
    called = []
    monkeypatch.setattr(main.youcam, "upload", lambda *a, **k: called.append("upload") or "f1")
    monkeypatch.setattr(main.youcam, "skin_analysis", lambda **k: called.append("analysis") or [])
    return called


def test_photo_link_to_private_address_is_never_fetched(monkeypatch):
    called = _live(monkeypatch)
    opened = []
    monkeypatch.setattr(main, "_open_url", lambda url: opened.append(url))
    for url in ("http://127.0.0.1/a.jpg", "http://169.254.169.254/latest/meta-data", "http://10.0.0.5/x.png",
                "http://localhost:8080/sample.jpg", "http://[::1]/a.jpg"):
        r = client.post("/analyze", json={"image_url": url})
        assert r.status_code == 422, url
        assert "publicly reachable" in r.json()["detail"] or "doesn't look right" in r.json()["detail"]
    assert opened == [] and called == []


def test_dead_or_non_image_photo_link_fails_fast_without_youcam(monkeypatch):
    import io
    import urllib.error
    called = _live(monkeypatch)
    monkeypatch.setattr(main, "_public_host", lambda url: True)

    def gone(url):
        raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)
    monkeypatch.setattr(main, "_open_url", gone)
    r = client.post("/analyze", json={"image_url": "https://example.com/missing.jpg"})
    assert r.status_code == 422 and "HTTP 404" in r.json()["detail"]

    monkeypatch.setattr(main, "_open_url", lambda url: io.BytesIO(b"<html>not a photo</html>"))
    r = client.post("/analyze", json={"image_url": "https://example.com/page.html"})
    assert r.status_code == 415 and "JPG or PNG" in r.json()["detail"]
    assert called == []


def test_photo_link_is_downloaded_once_and_analyzed_as_an_upload(monkeypatch):
    import io
    import struct
    _live(monkeypatch)
    monkeypatch.setattr(main, "_public_host", lambda url: True)
    png = b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\x0dIHDR" + struct.pack(">II", 800, 800) + b"rest"
    monkeypatch.setattr(main, "_open_url", lambda url: io.BytesIO(png))
    seen = {}
    monkeypatch.setattr(main, "analyze_image", lambda image, url, ct: seen.update(image=image, url=url, ct=ct) or {})
    assert client.post("/analyze", json={"image_url": "https://example.com/face.png"}).status_code == 200
    assert seen == {"image": png, "url": None, "ct": "image/png"}
