from app.services.region_match import RegionMatcher, norm, split_kab

KOTA_BANDUNG = ["JAWA BARAT", "KOTA BANDUNG"]
ANDIR = ["JAWA BARAT", "KOTA BANDUNG", "ANDIR"]
DISTRICTS = {"andir": "3273010", "cicendo": "3273020"}


def m(names, **kw):
    return RegionMatcher(level=len(names), names=names, districts=kw.get("districts", {}))


def test_norm_and_split_kab():
    assert norm("KOTA ADM. JAKARTA PUSAT") == "kota jakarta pusat"
    assert split_kab("KOTA BANDUNG") == ("kota", "bandung")
    assert split_kab("KABUPATEN BANDUNG BARAT") == ("kabupaten", "bandung barat")
    assert split_kab("KAB. SUMBA TIMUR") == ("kabupaten", "sumba timur")


def test_empty_address_is_unknown():
    assert m(ANDIR).evaluate(None) == (None, None)
    assert m(ANDIR).evaluate("  ") == (None, None)


def test_short_address_is_unknown():
    assert m(ANDIR).evaluate("Jl. Astina No.23") == (None, None)


def test_kecamatan_match_is_true():
    r, _ = m(ANDIR).evaluate("Jl. Ence Azis, Kb. Jeruk, Kec. Andir, Kota Bandung, Jawa Barat 40181")
    assert r is True


def test_other_kecamatan_is_false():
    # fakta dari scraping nyata: query Andir mengembalikan toko di Kec. Cicendo
    r, _ = m(ANDIR).evaluate("Jl. Astina No.23, Pamoyanan, Kec. Cicendo, Kota Bandung, Jawa Barat 40173")
    assert r is False


def test_kota_vs_kabupaten_same_base_name_conflict():
    r, _ = m(KOTA_BANDUNG).evaluate("Jl. Raya, Kec. Soreang, Kabupaten Bandung, Jawa Barat 40911")
    assert r is False


def test_kabupaten_bandung_barat_is_not_kabupaten_bandung():
    names = ["JAWA BARAT", "KABUPATEN BANDUNG"]
    r, _ = m(names).evaluate("Jl. X, Kec. Lembang, Kabupaten Bandung Barat, Jawa Barat")
    assert r is False


def test_level2_match_with_district_detection():
    r, kode = m(KOTA_BANDUNG, districts=DISTRICTS).evaluate(
        "Jl. Astina No.23, Pamoyanan, Kec. Cicendo, Kota Bandung, Jawa Barat 40173"
    )
    assert r is True
    assert kode == "3273020"


def test_level2_unknown_district_name_gives_no_kode():
    r, kode = m(KOTA_BANDUNG, districts=DISTRICTS).evaluate("Jl. Y, Kec. Antah, Kota Bandung")
    assert r is True and kode is None


def test_abbreviation_without_space_after_dot():
    r, _ = m(ANDIR).evaluate("Jl. A,Kec.Andir,Kota Bandung")
    assert r is True


def test_level4_desa_conflict():
    names = ["JAWA BARAT", "KOTA BANDUNG", "ANDIR", "CAMPAKA"]
    assert m(names).evaluate("Jl. A, Kel. Garuda, Kec. Andir, Kota Bandung")[0] is False
    assert m(names).evaluate("Jl. A, Kel. Campaka, Kec. Andir, Kota Bandung")[0] is True


def test_province_level_substring_match():
    assert m(["JAWA BARAT"]).evaluate("Jl. A, Bandung, Jawa Barat 40111")[0] is True
    assert m(["JAWA BARAT"]).evaluate("Jl. A, Surabaya, Jawa Timur")[0] is None


def test_fallback_word_match_in_plain_address():
    assert m(KOTA_BANDUNG).evaluate("Pasar Baru Trade Centre, Bandung")[0] is True
