"""Complexion match: YouCam Facial Color Tones -> undertone, depth and the nearest foundation shade.

Pure functions (stdlib only) so they are deterministic and testable offline. Colors are compared in
CIELAB (D65): depth from L* and the Individual Typology Angle (ITA), undertone from the hue angle h_ab
(more yellow = warm, more pink = cool). Finish and coverage come from the Skin Analysis scores.
"""

from __future__ import annotations

import math
import re

from app import recommend as rec

_HEX = re.compile(r"#?([0-9a-fA-F]{6})")
COOL_BELOW, WARM_FROM = 55.0, 62.0  # hue angle h_ab in degrees
UNDERTONE_PENALTY = 3.0  # delta-E points added when a shade's undertone differs from the customer's


OUT_OF_RANGE_DE = 8.0  # beyond this delta-E the end-of-range shade is a visible mismatch
OUT_OF_RANGE_L = 3.0  # ...and only when the skin is actually lighter / deeper than that shade (not just a hue miss)


def hex_to_rgb(value: str) -> tuple[int, int, int]:
    m = _HEX.fullmatch(str(value or "").strip())
    if not m:
        raise ValueError(f"not a hex color: {value!r}")
    h = m.group(1)
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def rgb_to_hex(rgb: tuple[float, float, float]) -> str:
    return "#" + "".join(f"{max(0, min(255, round(c))):02x}" for c in rgb)


def hex_to_lab(value: str) -> tuple[float, float, float]:
    def lin(c: float) -> float:
        c /= 255
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (lin(c) for c in hex_to_rgb(value))
    x = (r * 0.4124 + g * 0.3576 + b * 0.1805) / 0.95047
    y = r * 0.2126 + g * 0.7152 + b * 0.0722
    z = (r * 0.0193 + g * 0.1192 + b * 0.9505) / 1.08883

    def f(t: float) -> float:
        return t ** (1 / 3) if t > 0.008856 else 7.787 * t + 16 / 116

    fx, fy, fz = f(x), f(y), f(z)
    return 116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)


def delta_e(a: str, b: str) -> float:
    return math.dist(hex_to_lab(a), hex_to_lab(b))


def hue_angle(value: str) -> float:
    _, a, b = hex_to_lab(value)
    return math.degrees(math.atan2(b, a))


def undertone(value: str) -> str:
    h = hue_angle(value)
    return "cool" if h < COOL_BELOW else "warm" if h >= WARM_FROM else "neutral"


def depth(value: str) -> dict:
    """ITA-based depth band (Chardon et al.): very light > 55 > light > 41 > medium > 28 > tan > 10 > brown > -30."""
    lum, _, b = hex_to_lab(value)
    ita = math.degrees(math.atan2(lum - 50, b))
    label = ("very light" if ita > 55 else "light" if ita > 41 else "medium" if ita > 28 else "tan" if ita > 10
             else "deep" if ita > -30 else "very deep")
    return {"label": label, "ita": round(ita, 1), "lightness": round(lum, 1)}


def foundation_shades() -> list[dict]:
    return [p for p in rec.CATALOG if p.get("shade")]


def lip_shades() -> list[dict]:
    return [p for p in rec.CATALOG if p.get("vto", {}).get("category") == "lip_color"]


def finish_and_coverage(scores: list[dict] | None) -> dict:
    """Pick the formula, not just the color: dry skin -> dewy, oily -> matte; visible redness/spots -> more coverage."""
    by = {s.get("type"): int(s.get("ui_score", 100)) for s in (scores or []) if isinstance(s, dict)}
    dry, oily = by.get("moisture", 100) < 75, by.get("oiliness", 100) < 75
    finish = "satin" if dry and oily else "dewy" if dry else "matte" if oily else "natural"
    why_finish = {"satin": "combination skin: hydrated but shine-controlled",
                  "dewy": f"dryness scored {by.get('moisture')} - a hydrating, luminous formula won't cling "
                          "to dry patches",
                  "matte": f"oiliness scored {by.get('oiliness')} - a matte formula controls shine",
                  "natural": "balanced skin - a natural finish keeps your texture"}[finish]
    cover_for = [rec.LABELS[t] for t in ("redness", "age_spot", "acne", "dark_circle_v2") if by.get(t, 100) < 70]
    coverage = "medium, buildable" if cover_for else "sheer to light"
    why_cover = (f"to even out {', '.join(cover_for)}" if cover_for else "your skin is even - let it show through")
    return {"finish": finish, "finish_why": why_finish, "coverage": coverage, "coverage_why": why_cover}


def match(tones: dict, scores: list[dict] | None = None) -> dict:
    """Nearest foundation shade (CIELAB delta-E, undertone-aware) + lighter/darker neighbors + ranked lip shades."""
    skin = tones["skin_color"]
    tone = undertone(skin)
    shades = sorted(foundation_shades(), key=lambda p: hex_to_lab(p["shade"]["hex"])[0], reverse=True)

    def cost(p: dict) -> float:
        return delta_e(skin, p["shade"]["hex"]) + (0 if p["shade"]["undertone"] == tone else UNDERTONE_PENALTY)

    best = min(shades, key=cost)
    i = shades.index(best)
    neighbors = [shades[j] for j in (i - 1, i + 1) if 0 <= j < len(shades)]
    lip = tones.get("lip_color")
    out_of_range = None  # skin clearly beyond the deepest / lightest shade we stock: say so instead of a "match"
    if delta_e(skin, best["shade"]["hex"]) > OUT_OF_RANGE_DE:
        skin_l = hex_to_lab(skin)[0]
        if skin_l < hex_to_lab(shades[-1]["shade"]["hex"])[0] - OUT_OF_RANGE_L:
            out_of_range = "deeper"
        elif skin_l > hex_to_lab(shades[0]["shade"]["hex"])[0] + OUT_OF_RANGE_L:
            out_of_range = "lighter"
    return {
        "skin_hex": skin.lower(), "lip_hex": (lip or "").lower() or None,
        "eye_color": tones.get("eye_color_name"),
        "undertone": tone, "hue_angle": round(hue_angle(skin), 1), "depth": depth(skin),
        "match": _shade_card(best, skin), "out_of_range": out_of_range,
        "neighbors": [_shade_card(p, skin) for p in neighbors],
        "range": [_shade_card(p, skin) | {"is_match": p is best} for p in shades],
        "formula": finish_and_coverage(scores),
        "lips": rank_lips(tone, lip),
    }


def _shade_card(p: dict, skin: str) -> dict:
    return {"sku": p["sku"], "name": p["name"], "shade": p["shade"]["name"], "hex": p["shade"]["hex"],
            "undertone": p["shade"]["undertone"], "price": p["price"],
            "delta_e": round(delta_e(skin, p["shade"]["hex"]), 1)}


LIP_FAMILY_FIT = {"warm": {"coral": 3, "brick": 3, "nude": 2, "rose": 1, "berry": 0},
                  "cool": {"berry": 3, "rose": 3, "nude": 2, "coral": 0, "brick": 1},
                  "neutral": {"rose": 2, "nude": 3, "coral": 2, "brick": 2, "berry": 2}}


def rank_lips(tone: str, natural_lip: str | None) -> list[dict]:
    """Undertone first; the nude is boosted when it sits close to the customer's own lip color."""
    out = []
    for p in lip_shades():
        family = p.get("family", "rose")
        score = LIP_FAMILY_FIT[tone].get(family, 1)
        color = p["vto"]["palettes"][0]["color"]
        if natural_lip and family == "nude" and delta_e(natural_lip, color) < 20:
            score += 1
        why = {"coral": "warm coral flatters golden undertones", "brick": "earthy red-brown for warm undertones",
               "rose": "soft rose works on cool and neutral undertones",
               "berry": "deep berry makes cool undertones pop",
               "nude": "close to your natural lip color - an everyday \"your lips but better\""}.get(family, "")
        out.append({"sku": p["sku"], "name": p["name"], "swatch": color, "family": family, "fit": score,
                    "price": p["price"], "why": why})
    out.sort(key=lambda r: (-r["fit"], r["price"]))
    for i, r in enumerate(out):
        r["best"] = i < 2
    return out
