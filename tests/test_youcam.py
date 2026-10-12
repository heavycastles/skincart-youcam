import json

import pytest

from app import youcam as yc


def test_mock_mode_when_no_key():
    c = yc.YouCamClient(api_key="")
    assert c.mock
    a, b = c.skin_analysis(image=b"face"), c.skin_analysis(image=b"face")
    assert [s.ui_score for s in a] == [s.ui_score for s in b]  # deterministic
    assert all(0 <= s.ui_score <= 100 for s in a) and {s.type for s in a} == set(yc.SD_ACTIONS)
    assert c.makeup_vto([{"category": "lip_color", "palettes": [{"color": "#ff0000"}]}]).startswith("data:image")


class FakeHTTP:
    """Records calls and replays the response shapes documented at docs.perfectcorp.com."""

    def __init__(self, task_results):
        self.calls, self.polls, self.task_results = [], 0, task_results

    def __call__(self, method, url, body=None, headers=None):
        self.calls.append((method, url, body, headers))
        if url.endswith("/s2s/v2.0/file"):
            return {"status": 200, "data": {"files": [{"file_id": "FID", "requests": [
                {"method": "PUT", "url": "https://s3.example/put?sig", "headers": {"Content-Type": "image/jpeg"}}]}]}}
        if url.startswith("https://s3.example"):
            return {}
        if method == "POST":
            return {"status": 200, "data": {"task_id": "TID"}}
        self.polls += 1
        if self.polls < 2:
            return {"status": 200, "data": {"task_status": "running"}}
        return {"status": 200, "data": {"task_status": "success", "results": self.task_results}}


def test_live_skin_flow_upload_task_poll(monkeypatch):
    c = yc.YouCamClient(api_key="k", mock=False, poll_interval=0)
    fake = FakeHTTP({"output": [{"type": "acne", "ui_score": 41, "raw_score": 60.1, "mask_urls": ["m"]}]})
    monkeypatch.setattr(c, "_request", fake)
    out = c.skin_analysis(image=b"\xff\xd8jpeg", actions=["acne"])
    assert out[0].type == "acne" and out[0].ui_score == 41
    methods = [(m, u.split("makeupar.com")[-1]) for m, u, *_ in fake.calls]
    assert methods[0] == ("POST", "/s2s/v2.0/file")
    assert methods[1][0] == "PUT" and fake.calls[1][2] == b"\xff\xd8jpeg"
    assert methods[2] == ("POST", "/s2s/v2.0/task/skin-analysis")
    assert fake.calls[2][2]["src_file_id"] == "FID" and fake.calls[2][2]["dst_actions"] == ["acne"]
    assert methods[-1] == ("GET", "/s2s/v2.0/task/skin-analysis/TID")


def test_live_vto_with_url(monkeypatch):
    c = yc.YouCamClient(api_key="k", mock=False, poll_interval=0)
    fake = FakeHTTP({"url": "https://cdn/out.jpg"})
    monkeypatch.setattr(c, "_request", fake)
    assert c.makeup_vto([{"category": "lip_color"}], url="https://img/s.jpg") == "https://cdn/out.jpg"
    body = fake.calls[0][2]
    assert body["src_file_url"] == "https://img/s.jpg" and body["version"] == "1.0"


def test_task_error_raises(monkeypatch):
    c = yc.YouCamClient(api_key="k", mock=False, poll_interval=0)
    monkeypatch.setattr(c, "_request", lambda m, u, b=None, h=None: {"data": {"task_id": "T"}} if m == "POST"
                        else {"data": {"task_status": "error", "error": "error_no_face"}})
    with pytest.raises(yc.YouCamError, match="no_face"):
        c.skin_analysis(url="https://x/y.jpg")


def test_auth_header_only_to_youcam(monkeypatch):
    sent = []

    class Resp:
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False
        def read(self):
            return json.dumps({"ok": 1}).encode()

    def fake_open(req, timeout):
        sent.append(req)
        return Resp()
    monkeypatch.setattr(yc.urllib.request, "urlopen", fake_open)
    c = yc.YouCamClient(api_key="secret", mock=False)
    c._request("GET", c.base_url + "/s2s/v2.0/x")
    c._request("PUT", "https://s3.example/put", b"x")
    assert sent[0].get_header("Authorization") == "Bearer secret"
    assert sent[1].get_header("Authorization") is None  # never leak the key to the presigned bucket
