import base64

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)
IMG = base64.b64encode(b"\xff\xd8 fake selfie bytes").decode()


def test_health_ui_version():
    assert client.get("/healthz").json() == {"status": "ok"}
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
    assert lead["phone"] == "+998901234567" and lead["extra"]["basket"] and lead["score"] >= 50
    assert lead["extra"]["total"] == round(sum(b["price"] for b in scan["basket"]), 2)
    assert client.get(f"/leads/{lead['id']}").json()["extra"]["scan_id"] == scan["scan_id"]
    again = client.post("/orders", json={"name": "D", "phone": "+998901234567", "skus": ["SC-SPF-09"]})
    assert again.json()["created"] is False  # LeadFlow de-dup


def test_validation():
    assert client.post("/analyze", json={}).status_code == 422
    assert client.post("/analyze", json={"image_base64": "%%%"}).status_code == 422
    assert client.post("/tryon", json={"scan_id": "nope", "sku": "SC-LIP-10"}).status_code == 404
    assert client.post("/orders", json={"name": "X", "phone": "+998901112233", "skus": ["BAD"]}).status_code == 400
    assert client.post("/orders", json={"name": "X", "skus": ["SC-SPF-09"]}).status_code == 422
    assert client.get("/leads/9999").status_code == 404


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
    leads = client.get("/leads").json()["leads"]
    assert any(x["source"] == "telegram" and x["extra"]["telegram_chat_id"] == 777 for x in leads)


def test_sample_photo_and_score_fields():
    r = client.get("/sample.jpg")
    assert r.status_code == 200 and r.headers["content-type"] == "image/jpeg" and r.content[:2] == b"\xff\xd8"
    scan = client.post("/analyze", json={"image_base64": base64.b64encode(r.content).decode()}).json()
    assert 0 < scan["skin_score"] <= 100 and all("label" in x for x in scan["scores"])
