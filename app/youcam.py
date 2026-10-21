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
import re
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass

DEFAULT_BASE = "https://yce-api-01.makeupar.com"
SD_ACTIONS = ["acne", "pore", "wrinkle", "texture", "moisture", "oiliness", "redness", "radiance",
              "dark_circle_v2", "age_spot", "eye_bag", "firmness"]


class YouCamError(RuntimeError):
    """``code`` is YouCam's machine-readable error (e.g. ``error_src_face_too_small``), ``timeout``,
    ``network`` or ``http_<status>``; the message keeps the raw detail for server logs only."""

    def __init__(self, message: str, code: str = "unknown") -> None:
        super().__init__(message)
        self.code = code


_ERR_CODE = re.compile(r"\b(?!error_code\b|error_message\b)(error_[a-z_0-9]+|exceed_[a-z_0-9]+|invalid_parameter"
                       r"|unknown_internal_error)\b")


def _error_code(text: str, default: str) -> str:
    m = _ERR_CODE.search(text or "")
    return m.group(1) if m else default


@dataclass
class SkinConcern:
    type: str
    ui_score: int  # 0-100, higher = healthier skin for that concern
    raw_score: float
    mask_urls: list[str]


class YouCamClient:
    def __init__(self, api_key: str | None = None, base_url: str | None = None, mock: bool | None = None,
                 poll_interval: float = 2.0, timeout: float | None = None) -> None:
        self.api_key = api_key if api_key is not None else os.getenv("YOUCAM_API_KEY", "")
        self.base_url = (base_url or os.getenv("YOUCAM_BASE_URL", DEFAULT_BASE)).rstrip("/")
        env_mock = os.getenv("YOUCAM_MOCK", "").lower() in {"1", "true", "yes"}
        self.mock = (not self.api_key) or env_mock if mock is None else mock
        if timeout is None:  # serverless hosts (Vercel sets VERCEL=1) stop a function at 60 s: fail cleanly first
            timeout = float(os.getenv("YOUCAM_TIMEOUT") or (45 if os.getenv("VERCEL") else 120))
        self.poll_interval, self.timeout = poll_interval, timeout
        self.calls = 0
        self._local = threading.local()  # per-request deadline (sync routes run in a thread pool)

    # ---------- time budget ----------
    def begin(self) -> None:
        """Start one time budget shared by every call of a user action (upload + task + polls), so a slow
        upload can't push the whole action past the host's function limit."""
        self._local.deadline = time.monotonic() + self.timeout

    def end(self) -> None:
        self._local.deadline = None

    def _remaining(self) -> float:
        deadline = getattr(self._local, "deadline", None)
        return self.timeout if deadline is None else deadline - time.monotonic()

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
        remaining = self._remaining()
        if remaining <= 0:
            raise YouCamError("time budget used up before the request", "timeout")
        try:
            with urllib.request.urlopen(req, timeout=max(1.0, min(60.0, remaining))) as resp:  # noqa: S310
                raw = resp.read()
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode(errors="replace")[:500]
            raise YouCamError(f"{method} {url.split('?')[0]} -> {exc.code}: {detail}",
                              _error_code(detail, f"http_{exc.code}")) from exc
        except TimeoutError as exc:
            raise YouCamError(f"{method} {url.split('?')[0]} timed out", "timeout") from exc
        except urllib.error.URLError as exc:
            code = "timeout" if isinstance(exc.reason, TimeoutError) else "network"
            raise YouCamError(f"{method} {url.split('?')[0]} failed: {exc.reason}", code) from exc
        except OSError as exc:  # connection reset mid-read etc.
            raise YouCamError(f"{method} {url.split('?')[0]} failed: {exc}", "network") from exc
        self.calls += 1
        if not raw.strip().startswith(b"{"):
            return {}
        try:
            return json.loads(raw)
        except ValueError as exc:
            raise YouCamError(f"{method} {url.split('?')[0]} returned invalid JSON", "bad_response") from exc

    def upload(self, image: bytes, content_type: str = "image/jpeg", file_name: str = "selfie.jpg") -> str:
        """File API: register the file, PUT the bytes to the presigned URL, return file_id."""
        resp = self._request("POST", f"{self.base_url}/s2s/v2.0/file", {
            "files": [{"content_type": content_type, "file_name": file_name, "file_size": len(image)}]})
        try:
            f = resp["data"]["files"][0]
            put = f["requests"][0]
            put_url, file_id = put["url"], f["file_id"]
        except (KeyError, IndexError, TypeError) as exc:
            raise YouCamError("file upload: unexpected response", "bad_response") from exc
        self._request(put.get("method", "PUT"), put_url, image, put.get("headers") or {})
        return file_id

    def _run_task(self, task: str, payload: dict) -> dict:
        resp = self._request("POST", f"{self.base_url}/s2s/v2.0/task/{task}", payload)
        try:
            task_id = resp["data"]["task_id"]
        except (KeyError, TypeError) as exc:
            raise YouCamError(f"{task}: no task_id in response", "bad_response") from exc
        deadline = time.monotonic() + min(self.timeout, self._remaining())
        while True:
            data = (self._request("GET", f"{self.base_url}/s2s/v2.0/task/{task}/{task_id}") or {}).get("data") or {}
            status = data.get("task_status")
            if status == "success":
                return data
            if status == "error":
                err = str(data.get("error") or data.get("failure_reason") or "")
                raise YouCamError(f"{task} failed: {err} {data.get('error_message') or ''}".strip(),
                                  _error_code(err, "task_error"))
            if time.monotonic() + self.poll_interval > deadline:
                raise YouCamError(f"{task} timed out (last status {status})", "timeout")
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
                      actions: list[str] | None = None, content_type: str = "image/jpeg",
                      file_id: str | None = None) -> list[SkinConcern]:
        """Score each requested concern. Pass ``file_id`` to reuse an uploaded image (no second upload).

        The live API also returns helper items (``all``, ``skin_age``, ``resize_image``) next to the
        concerns; only the requested concern types are kept so they never show up as 0/100 "concerns".
        """
        actions = actions or SD_ACTIONS
        if self.mock:
            return _mock_skin(image or (url or "").encode(), actions)
        if not file_id and image and not url:
            file_id = self.upload(image, content_type)
        data = self._run_task("skin-analysis", {**self._src(file_id, url), "dst_actions": actions,
                                                "miniserver_args": {"enable_mask_overlay": True},
                                                "format": "json"})
        out = (data.get("results") or {}).get("output") or []
        return [SkinConcern(o["type"], int(o.get("ui_score", 0)), float(o.get("raw_score", 0)),
                            list(o.get("mask_urls") or [])) for o in out if o.get("type") in actions]

    def makeup_vto(self, effects: list[dict], image: bytes | None = None, url: str | None = None,
                   content_type: str = "image/jpeg", file_id: str | None = None) -> str:
        """Apply makeup effects (lip_color, foundation, blush, ...); returns result image URL (or data URI in mock)."""
        if self.mock:
            return _mock_vto(effects)
        if not file_id and image and not url:
            file_id = self.upload(image, content_type)
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
