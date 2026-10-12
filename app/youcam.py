"""YouCam API (Perfect Corp) client: File API upload -> async task -> poll.

Docs: https://docs.perfectcorp.com/develop/quick_start_guide
  * Auth: ``Authorization: Bearer <YOUCAM_API_KEY>``; server https://yce-api-01.makeupar.com
  * ``POST /s2s/v2.0/file`` -> data.files[0].{file_id, requests[0].{method,url,headers}}; PUT bytes there.
  * ``POST /s2s/v2.0/task/skin-analysis`` {src_file_id|src_file_url, dst_actions, format:"json"} -> data.task_id
  * ``GET  /s2s/v2.0/task/skin-analysis/{task_id}`` -> data.task_status,
    data.results.output[{type, ui_score, raw_score, mask_urls}]
  * ``POST /s2s/v2.0/task/makeup-vto`` {src_file_id|src_file_url, effects:[...], version:"1.0"}; GET .../{task_id}
    -> data.results.url (or results[0].download_url)

Mock mode (no key, or YOUCAM_MOCK=1) returns deterministic results derived from the image bytes, so
tests and the demo run offline without spending units. Stdlib-only HTTP to keep the image small.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass

DEFAULT_BASE = "https://yce-api-01.makeupar.com"
SD_ACTIONS = ["acne", "pore", "wrinkle", "texture", "moisture", "oiliness", "redness", "radiance",
              "dark_circle_v2", "age_spot", "eye_bag", "firmness"]


class YouCamError(RuntimeError):
    pass


@dataclass
class SkinConcern:
    type: str
    ui_score: int  # 0-100, higher = healthier skin for that concern
    raw_score: float
    mask_urls: list[str]


class YouCamClient:
    def __init__(self, api_key: str | None = None, base_url: str | None = None, mock: bool | None = None,
                 poll_interval: float = 2.0, timeout: float = 120.0) -> None:
        self.api_key = api_key if api_key is not None else os.getenv("YOUCAM_API_KEY", "")
        self.base_url = (base_url or os.getenv("YOUCAM_BASE_URL", DEFAULT_BASE)).rstrip("/")
        env_mock = os.getenv("YOUCAM_MOCK", "").lower() in {"1", "true", "yes"}
        self.mock = (not self.api_key) or env_mock if mock is None else mock
        self.poll_interval, self.timeout = poll_interval, timeout
        self.calls = 0

    # ---------- low-level HTTP ----------
    def _request(self, method: str, url: str, body: dict | bytes | None = None,
                 headers: dict | None = None) -> dict:
        hdrs = dict(headers or {})
        data = None
        if isinstance(body, dict):
            data = json.dumps(body).encode()
            hdrs.setdefault("Content-Type", "application/json")
        elif isinstance(body, bytes):
            data = body
        if url.startswith(self.base_url):
            hdrs["Authorization"] = f"Bearer {self.api_key}"
        req = urllib.request.Request(url, data=data, method=method, headers=hdrs)  # noqa: S310
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:  # noqa: S310
                raw = resp.read()
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode(errors="replace")[:500]
            raise YouCamError(f"{method} {url.split('?')[0]} -> {exc.code}: {detail}") from exc
        self.calls += 1
        return json.loads(raw) if raw.strip().startswith(b"{") else {}

    def upload(self, image: bytes, content_type: str = "image/jpeg", file_name: str = "selfie.jpg") -> str:
        """File API: register the file, PUT the bytes to the presigned URL, return file_id."""
        resp = self._request("POST", f"{self.base_url}/s2s/v2.0/file", {
            "files": [{"content_type": content_type, "file_name": file_name, "file_size": len(image)}]})
        f = resp["data"]["files"][0]
        put = f["requests"][0]
        self._request(put.get("method", "PUT"), put["url"], image, put.get("headers") or {})
        return f["file_id"]

    def _run_task(self, task: str, payload: dict) -> dict:
        resp = self._request("POST", f"{self.base_url}/s2s/v2.0/task/{task}", payload)
        task_id = resp["data"]["task_id"]
        deadline = time.monotonic() + self.timeout
        while True:
            data = self._request("GET", f"{self.base_url}/s2s/v2.0/task/{task}/{task_id}")["data"]
            status = data.get("task_status")
            if status == "success":
                return data
            if status == "error":
                raise YouCamError(f"{task} failed: {data.get('error') or data.get('failure_reason')}")
            if time.monotonic() > deadline:
                raise YouCamError(f"{task} timed out (last status {status})")
            time.sleep(self.poll_interval)

    @staticmethod
    def _src(file_id: str | None, url: str | None) -> dict:
        if url:
            return {"src_file_url": url}
        if file_id:
            return {"src_file_id": file_id}
        raise ValueError("need an image, file_id or url")

    # ---------- public API ----------
    def skin_analysis(self, image: bytes | None = None, url: str | None = None,
                      actions: list[str] | None = None, content_type: str = "image/jpeg") -> list[SkinConcern]:
        actions = actions or SD_ACTIONS
        if self.mock:
            return _mock_skin(image or (url or "").encode(), actions)
        file_id = self.upload(image, content_type) if image and not url else None
        data = self._run_task("skin-analysis", {**self._src(file_id, url), "dst_actions": actions,
                                                "miniserver_args": {"enable_mask_overlay": True},
                                                "format": "json"})
        out = (data.get("results") or {}).get("output") or []
        return [SkinConcern(o["type"], int(o.get("ui_score", 0)), float(o.get("raw_score", 0)),
                            list(o.get("mask_urls") or [])) for o in out]

    def makeup_vto(self, effects: list[dict], image: bytes | None = None, url: str | None = None,
                   content_type: str = "image/jpeg") -> str:
        """Apply makeup effects (lip_color, foundation, blush, ...); returns result image URL (or data URI in mock)."""
        if self.mock:
            return _mock_vto(effects)
        file_id = self.upload(image, content_type) if image and not url else None
        data = self._run_task("makeup-vto", {**self._src(file_id, url), "effects": effects, "version": "1.0"})
        res = data.get("results")
        if isinstance(res, dict) and res.get("url"):
            return res["url"]
        if isinstance(res, list) and res:
            return res[0].get("download_url") or res[0].get("url")
        raise YouCamError(f"makeup-vto: no result url in {data}")


def _mock_skin(seed: bytes, actions: list[str]) -> list[SkinConcern]:
    digest = hashlib.sha256(seed).digest()
    return [SkinConcern(a, 35 + digest[i % 32] % 61, round(20 + digest[(i + 7) % 32] / 3.2, 2), [])
            for i, a in enumerate(actions)]


def _mock_vto(effects: list[dict]) -> str:
    color = "#c2185b"
    for e in effects:
        if e.get("palettes"):
            color = e["palettes"][0].get("color", color)
            break
    svg = (f"<svg xmlns='http://www.w3.org/2000/svg' width='240' height='240'><rect width='240' height='240' "
           f"fill='#f6e3d4'/><ellipse cx='120' cy='110' rx='70' ry='90' fill='#e8bfa3'/><ellipse cx='120' cy='160' "
           f"rx='26' ry='10' fill='{color}'/><text x='120' y='230' font-size='14' text-anchor='middle'>"
           f"mock VTO {color}</text></svg>")
    return "data:image/svg+xml;utf8," + urllib.request.quote(svg)
