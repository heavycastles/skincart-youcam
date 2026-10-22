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
                    "reason": f"{p['why'][0].upper()}{p['why'][1:]} - helps with {', '.join(hits)}",
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
                "reason": "Every routine needs daily SPF",
            }
        )
    return basket


def vto_products() -> list[dict]:
    """Lip shades to try on. Foundation shades are not listed: the shade match picks the one that fits."""
    return [{"sku": p["sku"], "name": p["name"], "price": p["price"], "kind": p["vto"]["category"],
             "family": p.get("family"), "swatch": (p["vto"].get("palettes") or [{}])[0].get("color", "#c2185b")}
            for p in CATALOG if p.get("vto") and not p.get("shade")]


# ---------- AM / PM plan: how to use the basket, with the usual ingredient clashes handled ----------
STEP_ORDER = ["cleanser", "serum", "treatment", "eye", "moisturizer", "spf"]
WHEN = {"SC-CLN-01": "both", "SC-SER-02": "both", "SC-SER-03": "both", "SC-SER-04": "am", "SC-NGT-05": "pm",
        "SC-EYE-06": "both", "SC-MST-07": "both", "SC-CIC-08": "both", "SC-SPF-09": "am"}


def schedule(skus: list[str]) -> dict:
    """Morning / evening steps for the skincare items in the basket (makeup is ignored) + usage notes.
    Mirrors the rules the web UI applies when the basket changes."""
    items = [p for p in (get_product(s) for s in skus) if p and p["sku"] in WHEN]
    items.sort(key=lambda p: STEP_ORDER.index(p["category"]) if p["category"] in STEP_ORDER else 99)
    has = {p["sku"] for p in items}
    retinal, bha = "SC-NGT-05" in has, "SC-CLN-01" in has
    am, pm, notes = [], [], []
    for p in items:
        when = WHEN[p["sku"]]
        if p["sku"] == "SC-CLN-01" and retinal:
            when = "am"  # two exfoliants on the same night irritate; BHA moves to the morning
        if when in ("am", "both"):
            am.append(p["name"])
        if when in ("pm", "both"):
            pm.append(p["name"])
    if retinal and bha:
        notes.append("Salicylic cleanser in the morning, retinal at night - two exfoliants in one evening irritate. "
                     "In the evening just rinse, or use a gentle non-exfoliating cleanser.")
    if retinal:
        notes.append("Start retinal 2-3 nights a week, then build up; it makes skin sun-sensitive, "
                     "so SPF every morning.")
    if "SC-SER-04" in has:
        notes.append("Vitamin C in the morning, under SPF - it boosts UV protection.")
    if "SC-SPF-09" in has:
        notes.append("Reapply SPF every 2 hours when you're outdoors.")
    if items and "SC-SPF-09" not in has:
        notes.append("No SPF in the basket - add one, or the routine works against the sun.")
    return {"am": am, "pm": pm, "notes": notes}


# ---------- Skin Simulation plan: preview only what the basket actually targets ----------
CONCERN_TO_SIM = {"pore": "pores", "wrinkle": "wrinkle", "texture": "texture", "radiance": "radiance",
                  "acne": "acne", "eye_bag": "eye_bags", "dark_circle_v2": "dark_circle", "age_spot": "spots",
                  "redness": "redness", "firmness": "wrinkle", "moisture": "texture"}
SIM_MAX = 0.7  # never the full "airbrushed" 1.0: a routine softens concerns, it doesn't erase them


def sim_intensity(ui_score: int) -> float:
    """Worse score -> stronger (but capped) simulated improvement; healthy concerns get a light maintenance touch."""
    if ui_score >= CONCERN_THRESHOLD:
        return 0.2
    return round(min(SIM_MAX, 0.25 + (CONCERN_THRESHOLD - ui_score) * 0.015) * 20) / 20


def simulation_plan(scores: list[dict], skus: list[str]) -> dict:
    """Concerns targeted by the skincare products in the basket -> Skin Simulation intensities.
    Returns {"params": {sim_key: 0.2-0.7}, "concerns": [{type,label,ui_score,intensity,products}]}."""
    by = {s["type"]: int(s["ui_score"]) for s in scores if isinstance(s, dict) and "type" in s and "ui_score" in s}
    targeted: dict[str, list[str]] = {}
    for sku in skus:
        p = get_product(sku)
        if not p or p.get("vto"):
            continue
        for t in p["targets"]:
            if t in by and t in CONCERN_TO_SIM:
                targeted.setdefault(t, []).append(p["name"])
    needed = {t: v for t, v in targeted.items() if by[t] < CONCERN_THRESHOLD}
    if not needed:  # healthy skin: a light maintenance preview of the (up to) 3 lowest targeted concerns
        needed = dict(sorted(targeted.items(), key=lambda kv: by[kv[0]])[:3])
    params: dict[str, float] = {}
    concerns_out = []
    for t, products in sorted(needed.items(), key=lambda kv: by[kv[0]]):
        k, v = CONCERN_TO_SIM[t], sim_intensity(by[t])
        params[k] = max(params.get(k, 0), v)
        concerns_out.append({"type": t, "label": LABELS.get(t, t), "ui_score": by[t], "intensity": v,
                             "products": products})
    return {"params": dict(sorted(params.items())), "concerns": concerns_out}


def get_product(sku: str) -> dict | None:
    return next((p for p in CATALOG if p["sku"] == sku), None)
