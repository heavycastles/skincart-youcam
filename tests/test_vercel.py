"""Guards for the Vercel deployment (hosted judge demo)."""

import json
from pathlib import Path

from app.youcam import YouCamClient

ROOT = Path(__file__).resolve().parent.parent


def test_vercel_config_targets_fastapi_entry():
    cfg = json.loads((ROOT / "vercel.json").read_text())
    fn = cfg["functions"]["app/main.py"]
    assert 30 <= fn["maxDuration"] <= 300  # Hobby plan limit; a live scan takes ~10-20 s
    assert (ROOT / "app" / "main.py").exists()
    assert (ROOT / ".python-version").read_text().strip().startswith("3.")


def test_vercelignore_ships_runtime_files_but_never_secrets():
    rules = (ROOT / ".vercelignore").read_text().splitlines()
    assert rules[rules.index("/*") + 1:].count("!/app") == 1
    for needed in ("!/requirements.txt", "!/VERSION", "!/docs/stock-face/stock-face.jpg"):
        assert needed in rules
    for secret in (".env", ".env.*", "**/.env"):
        assert secret in rules
    assert not any(r.startswith("!") and ".env" in r for r in rules)
    assert ".vercel/" in (ROOT / ".gitignore").read_text()


def test_youcam_timeout_fits_serverless_limit(monkeypatch):
    monkeypatch.delenv("YOUCAM_TIMEOUT", raising=False)
    monkeypatch.delenv("VERCEL", raising=False)
    assert YouCamClient(api_key="").timeout == 120
    monkeypatch.setenv("VERCEL", "1")
    assert YouCamClient(api_key="").timeout < json.loads((ROOT / "vercel.json").read_text())[
        "functions"]["app/main.py"]["maxDuration"]
    from app.main import PHOTO_LINK_TIMEOUT
    limit = json.loads((ROOT / "vercel.json").read_text())["functions"]["app/main.py"]["maxDuration"]
    # worst case: download a photo link, then the whole YouCam budget, plus cold start and response
    assert PHOTO_LINK_TIMEOUT + YouCamClient(api_key="").timeout + 8 <= limit
    monkeypatch.setenv("YOUCAM_TIMEOUT", "30")
    assert YouCamClient(api_key="").timeout == 30
