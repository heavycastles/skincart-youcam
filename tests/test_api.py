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
