"""Basket edge cases from the Oct 23 judge audit: repeated SKUs, SKU naming, try-on basket behaviour in the browser."""

import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import recommend as rec
from app.main import app

client = TestClient(app)
ROOT = Path(__file__).resolve().parent.parent
HTML = (ROOT / "app" / "static" / "index.html").read_text()


def test_repeated_sku_is_one_order_line():
    o = client.post("/orders", json={"name": "Repeat", "phone": "+998901110022",
                                     "skus": ["SC-SPF-09", "SC-SPF-09", "SC-LIP-15"]})
    assert o.status_code == 201
    extra = o.json()["lead"]["extra"]
    assert [b["sku"] for b in extra["basket"]] == ["SC-SPF-09", "SC-LIP-15"]
    assert extra["total"] == round(rec.get_product("SC-SPF-09")["price"] + rec.get_product("SC-LIP-15")["price"], 2)


def test_repeated_sku_is_one_simulation_product():
    scores = {"pores": 60, "moisture": 55}
    once = rec.simulation_plan(scores, ["SC-SPF-09", "SC-SER-01"])
    twice = rec.simulation_plan(scores, ["SC-SPF-09", "SC-SER-01", "SC-SER-01", "SC-SPF-09"])
    assert twice == once


def test_foundation_skus_follow_the_shade_number():
    for p in rec.CATALOG:
        if p["sku"].startswith("SC-FND-"):
            assert p["sku"] == "SC-FND-" + re.match(r"\d+", p["shade"]["name"]).group(0), p


def test_page_keeps_basket_and_previews_in_sync():
    # a remove button per basket line, makeup-only changes don't stale the skin preview,
    # rendered try-ons / previews are reused, and late answers for an older photo are dropped
    for needle in ('class="rm"', "function removeItem", "const simKey", "vtoCache", "simCache",
                   "function addTried", "function cartChanged", "scan_id!==sid"):
        assert needle in HTML, needle


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _node_path() -> str | None:
    for d in (os.environ.get("NODE_PATH", ""), str(Path.home() / ".local/lib/node_modules"),
              "/usr/lib/node_modules", "/usr/local/lib/node_modules"):
        if d and (Path(d) / "puppeteer-core").exists():
            return d
    return None


@pytest.mark.skipif(not (shutil.which("node") and _node_path()
                         and Path(os.environ.get("CHROME_PATH", "/usr/bin/google-chrome")).exists()),
                    reason="needs node, puppeteer-core and Chrome")
@pytest.mark.parametrize("width", [1280, 375])
def test_browser_flow(width):
    port = _free_port()
    env = {**os.environ, "YOUCAM_MOCK": "1", "YOUCAM_API_KEY": ""}
    cmd = [sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(port)]
    srv = subprocess.Popen(cmd,  # noqa: S603
                           cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(50):
            try:
                socket.create_connection(("127.0.0.1", port), 0.2).close()
                break
            except OSError:
                time.sleep(0.2)
        cmd = [shutil.which("node"), str(ROOT / "tests" / "e2e" / "ui_flow.js"), f"http://127.0.0.1:{port}", str(width)]
        r = subprocess.run(cmd,  # noqa: S603
                           env={**os.environ, "NODE_PATH": _node_path()}, capture_output=True, text=True, timeout=120)
        out = json.loads(r.stdout.strip().splitlines()[-1])
        assert out["ok"], out
    finally:
        srv.terminate()
        srv.wait(10)
