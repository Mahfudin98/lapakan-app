from app.services import planner
from app.services.planner import Target, build_plan, dedupe_keywords, pretty


def test_pretty_strips_adm_and_titlecases():
    assert pretty("KOTA ADM. JAKARTA PUSAT") == "Kota Jakarta Pusat"
    assert pretty("JAWA BARAT") == "Jawa Barat"
    assert pretty("KABUPATEN BANDUNG BARAT") == "Kabupaten Bandung Barat"


def test_query_text_goes_from_specific_to_general():
    t = Target("3273010", ["Jawa Barat", "Kota Bandung", "Andir"])
    (q,) = build_plan(["toko kosmetik"], [t])
    assert q.query == "toko kosmetik di Andir, Kota Bandung, Jawa Barat"
    assert q.region_kode == "3273010"


def test_plan_is_cross_product_region_outer():
    ts = [Target("a", ["P", "K", "A"]), Target("b", ["P", "K", "B"])]
    plan = build_plan(["salon", "spa"], ts)
    assert [(p.region_kode, p.keyword) for p in plan] == [
        ("a", "salon"), ("a", "spa"), ("b", "salon"), ("b", "spa"),
    ]


def test_dedupe_keywords_case_and_whitespace():
    assert dedupe_keywords(["Salon", " salon ", "spa", "", "  "]) == ["Salon", "spa"]


def test_village_query_has_four_levels():
    t = Target("x", ["Jawa Barat", "Kota Bandung", "Andir", "Campaka"])
    assert build_plan(["apotek"], [t])[0].query == "apotek di Campaka, Andir, Kota Bandung, Jawa Barat"


def test_plan_error_type():
    assert issubclass(planner.PlanError, ValueError)
