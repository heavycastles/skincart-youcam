from app import recommend as rec
from app.youcam import SkinConcern


def s(t, v):
    return SkinConcern(t, v, 0.0, [])


def test_acne_skin_gets_acne_products_and_spf():
    basket = rec.recommend([s("acne", 30), s("oiliness", 40), s("moisture", 90), s("wrinkle", 95)])
    skus = [b["sku"] for b in basket]
    assert skus[0] in {"SC-CLN-01", "SC-SER-02"}
    assert "SC-SPF-09" in skus and len({b["category"] for b in basket}) == len(basket)


def test_healthy_skin_still_gets_spf_only():
    assert [b["sku"] for b in rec.recommend([s("acne", 95)])] == ["SC-SPF-09"]


def test_concerns_sorted_worst_first():
    c = rec.concerns([s("acne", 60), s("pore", 45), s("redness", 90)])
    assert [x["type"] for x in c] == ["pore", "acne"] and c[0]["severity"] == "high"
