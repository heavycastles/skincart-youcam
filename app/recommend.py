"""Map YouCam skin scores to a catalog basket. Pure functions, deterministic for tests."""

from __future__ import annotations

import json
from pathlib import Path

from app.youcam import SkinConcern

CATALOG: list[dict] = json.loads((Path(__file__).parent / "catalog.json").read_text())
LABELS = {
    "acne": "breakouts",
    "pore": "visible pores",
    "wrinkle": "fine lines",
    "texture": "uneven texture",
    "moisture": "dryness",
    "oiliness": "oiliness",
    "redness": "redness",
    "radiance": "dullness",
    "dark_circle_v2": "dark circles",
    "age_spot": "spots",
    "eye_bag": "puffy eyes",
    "firmness": "loss of firmness",
}
CONCERN_THRESHOLD = 80  # ui_score below this = worth caring for (<50 high, <70 medium, <80 mild / maintenance)


def severity(ui_score: int) -> str:
    return "high" if ui_score < 50 else "medium" if ui_score < 70 else "mild"


def concerns(scores: list[SkinConcern], top: int = 3) -> list[dict]:
    worst = sorted((s for s in scores if s.ui_score < CONCERN_THRESHOLD), key=lambda s: s.ui_score)[:top]
    return [
        {
            "type": s.type,
            "label": LABELS.get(s.type, s.type),
            "ui_score": s.ui_score,
            "severity": severity(s.ui_score),
        }
        for s in worst
    ]


def skin_score(scores: list[SkinConcern]) -> int:
    """Overall 0-100 score: mean ui_score over the analysed concerns."""
    vals = [s.ui_score for s in scores if s.type in LABELS]
    return round(sum(vals) / len(vals)) if vals else 0


def recommend(scores: list[SkinConcern], limit: int = 4) -> list[dict]:
    """Weight each product by how badly it's needed: sum of (threshold - ui_score) over the concerns it targets."""
    need = {s.type: max(0, CONCERN_THRESHOLD - s.ui_score) for s in scores}
    ranked = []
    for p in CATALOG:
        weight = sum(need.get(t, 0) for t in p["targets"])
        if weight:
            hits = [LABELS.get(t, t) for t in p["targets"] if need.get(t)]
            ranked.append(
                {
                    **{k: p[k] for k in ("sku", "name", "category", "price")},
                    "match": weight,
                    "reason": f"{p['why']} - helps with {', '.join(hits)}",
                }
            )
    ranked.sort(key=lambda r: (-r["match"], r["price"]))
    basket, seen = [], set()
    for r in ranked:  # one product per category keeps the routine sane
        if r["category"] not in seen:
            basket.append(r)
            seen.add(r["category"])
        if len(basket) == limit:
            break
    if not any(r["category"] == "spf" for r in basket):
        spf = next(p for p in CATALOG if p["category"] == "spf")
        basket.append(
            {
                **{k: spf[k] for k in ("sku", "name", "category", "price")},
                "match": 0,
                "reason": "every routine needs daily SPF",
            }
        )
    return basket


def vto_products() -> list[dict]:
    return [{"sku": p["sku"], "name": p["name"], "price": p["price"], "kind": p["vto"]["category"],
             "swatch": (p["vto"].get("palettes") or [{}])[0].get("color", "#c2185b")}
            for p in CATALOG if p.get("vto")]


def get_product(sku: str) -> dict | None:
    return next((p for p in CATALOG if p["sku"] == sku), None)
