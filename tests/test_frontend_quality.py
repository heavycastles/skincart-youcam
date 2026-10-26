"""Accessibility, mobile and load-speed guarantees of the single-page UI (no browser needed)."""
import re
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app

c = TestClient(app)
STATIC = Path(__file__).resolve().parent.parent / "app" / "static"
HTML = (STATIC / "index.html").read_text()


def _media(width: int) -> str:
    return " ".join(re.findall(r"@media\(max-width:" + str(width) + r"px\)\{(.+)\}", HTML))


def test_page_is_edge_cacheable_and_compressed():
    for r in (c.get("/"), c.head("/")):
        assert r.status_code == 200
        cc = r.headers["cache-control"]
        assert "s-maxage=" in cc and "max-age=0" in cc and "stale-while-revalidate" in cc
    r = c.get("/", headers={"Accept-Encoding": "gzip"})
    assert r.headers.get("content-encoding") == "gzip"
    assert "s-maxage" not in c.get("/healthz").headers.get("cache-control", "")


def test_static_images_are_long_cached():
    for path in ("/sample.jpg", "/og.jpg"):
        for r in (c.get(path), c.head(path)):
            assert r.status_code == 200
            assert r.headers["content-type"] == "image/jpeg"
            assert "s-maxage=604800" in r.headers["cache-control"]


def test_social_preview_meta_and_image():
    for tag in ('name="theme-color"', 'property="og:title"', 'property="og:description"',
                'property="og:image" content="https://skincart-youcam.vercel.app/og.jpg"',
                'property="og:image:alt"', 'name="twitter:card" content="summary_large_image"'):
        assert tag in HTML, tag
    jpg = (STATIC / "og.jpg").read_bytes()
    assert jpg[:2] == b"\xff\xd8" and len(jpg) < 150_000
    # SOF0/SOF2 header carries height then width: must be the 1200x630 social size.
    m = re.search(rb"\xff[\xc0\xc2]..\x08(..)(..)", jpg, re.S)
    assert m and int.from_bytes(m.group(2), "big") == 1200 and int.from_bytes(m.group(1), "big") == 630


def test_focus_ring_is_high_contrast_everywhere():
    assert ":focus-visible{outline:3px solid var(--rose)" in HTML
    assert "#f08aac" not in HTML  # old 2.2:1 pink ring
    # The matched / neighbour swatches already wear an outline, so focus must override it
    # and come after those rules in the cascade.
    focus = HTML.index(".range button:focus-visible{outline:3px solid var(--ink)")
    assert focus > HTML.index(".range button.match{outline:")
    assert focus > HTML.index(".range button.nb{outline:")
    assert ".cmp:has(input:focus-visible){outline:3px solid var(--rose)" in HTML


def test_mobile_inputs_do_not_zoom_and_taps_are_big_enough():
    m = _media(640)
    assert "input.f{font-size:16px;min-height:48px}" in m
    assert ".rm{width:40px;height:40px" in m and ".add{min-height:40px" in m
    assert ".btn.sm,.alts button{min-height:44px}" in m
    m = _media(520)
    assert ".range{grid-template-columns:repeat(6,1fr)" in m
    assert ".range{gap:3px}" not in m  # 12 slivers on one row were ~22px wide
    assert ".navlink{" in HTML and "padding:12px 4px" in HTML


def test_live_badge_reserves_width_so_layout_does_not_shift():
    badge = re.search(r"\.badge\{([^}]+)\}", HTML).group(1)
    assert "min-width:158px" in badge and "justify-content:center" in badge


def test_photo_drop_zone_has_matching_accessible_name():
    drop = HTML[HTML.index('id="drop"'):]
    drop = drop[:drop.index('<div class="chip"')]
    # #drop (whose opening "<div" is cut off above) is closed before the chip starts.
    assert drop.count("<div") + 1 == drop.count("</div>")
    assert ".drop.scanning~.chip" in HTML
    # While framing, the visible hint must start the accessible name (WCAG 2.5.3).
    hint = re.search(r'id="ghint"[^>]*>([^<]+)', HTML).group(1).strip()
    label = re.search(r"d\.setAttribute\('aria-label','([^']+)'\)", HTML).group(1)
    assert label.lower().startswith(hint.lower().rstrip(".")), (hint, label)


def test_overlay_images_are_lazy_and_failures_hide_the_section():
    assert 'loading="lazy" decoding="async" onerror="maskFailed(this)"' in HTML
    fn = re.search(r"function maskFailed\(img\)\{(.+?)\}\n", HTML).group(1)
    assert "img.parentNode.remove()" in fn and "$('maskWrap').hidden=true" in fn


def test_reduced_motion_is_respected():
    assert "@media(prefers-reduced-motion:reduce)" in HTML
    assert "let n=calm.matches?sc:0" in HTML  # score count-up skipped
    assert "calm.matches?'auto':'smooth'" in HTML


def test_no_third_party_runtime_assets():
    srcs = re.findall(r'<(?:script|link)[^>]+(?:src|href)="(https?://[^"]+)"', HTML)
    assert srcs == []
