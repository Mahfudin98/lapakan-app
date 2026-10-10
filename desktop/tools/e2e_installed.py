"""Uji end-to-end aplikasi Windows yang SUDAH TERPASANG dan berjalan: alur pengguna sungguhan lewat browser.

    python e2e_installed.py http://127.0.0.1:8765 <folder-screenshot>

Memakai Playwright (Edge) sebagai "pengguna". Melakukan scraping nyata kecil ke Google Maps.
"""
import re
import sys
import time

from playwright.sync_api import expect, sync_playwright

BASE, OUT = sys.argv[1].rstrip("/"), sys.argv[2]


def pick(page, label, typed, option):
    box = page.get_by_role("combobox", name=label, exact=True)
    box.click()
    box.fill(typed)
    page.get_by_role("option", name=option, exact=True).click()


with sync_playwright() as p:
    b = p.chromium.launch(channel="msedge")
    page = b.new_context(viewport={"width": 1300, "height": 900}).new_page()
    problems = []
    page.on("pageerror", lambda e: problems.append(f"pageerror: {e}"))
    page.on("console", lambda m: problems.append(f"console: {m.text}") if m.type == "error" and "tile.openstreetmap" not in m.text else None)
    page.on("response", lambda r: problems.append(f"HTTP {r.status} {r.url}") if r.status >= 400 and "openstreetmap" not in r.url else None)

    page.goto(BASE + "/")
    expect(page.get_by_text("Cari toko di Google Maps")).to_be_visible()
    print("OK beranda tampil dari server lokal; judul:", page.title())

    pick(page, "Provinsi", "jawa b", "Jawa Barat")
    pick(page, "Kabupaten / Kota", "bandung", "Kota Bandung")
    pick(page, "Kecamatan", "coblong", "Coblong")
    page.get_by_role("button", name="Toko Kosmetik", exact=True).click()
    page.get_by_text("Opsi lanjutan").click()
    page.get_by_label("Lengkapi detail tiap toko").uncheck()
    page.get_by_label("Batas jumlah toko").fill("8")
    expect(page.get_by_test_id("plan")).to_contain_text("1 pencarian", timeout=10000)
    page.screenshot(path=f"{OUT}/e2e_1_form.png")
    page.get_by_role("button", name="Mulai cari toko").click()
    expect(page).to_have_url(re.compile(r"#/job/"))
    t0 = time.time()
    print("OK job dibuat; menunggu worker + Edge mengambil hasil nyata...")

    first = None
    deadline = time.time() + 240
    status = ""
    while time.time() < deadline:
        panel = page.get_by_test_id("job-panel").inner_text()
        n = page.get_by_test_id("place-card").count()
        if n and first is None:
            first = time.time() - t0
        if re.search(r"\bSelesai\b", panel) and "Berjalan" not in panel and "Antre" not in panel:
            status = "done"
            break
        if "Gagal" in panel or "Diblokir" in panel or "Dibatalkan" in panel:
            status = panel.replace("\n", " | ")[:300]
            break
        page.wait_for_timeout(1500)
    page.wait_for_timeout(2000)
    n = page.get_by_test_id("place-card").count()
    print(f"status: {status!r} | kartu: {n} | kartu pertama muncul setelah {first and round(first)} dtk | total {round(time.time() - t0)} dtk")
    page.screenshot(path=f"{OUT}/e2e_2_results.png")
    assert status == "done", f"job tidak selesai: {status}"
    assert n >= 1

    # data benar-benar tersimpan di database lokal + ekspor
    r = page.request.get(BASE + "/places?page_size=3")
    total = r.json()["total"]
    print("OK /places total:", total)
    assert total >= 1
    csv = page.request.get(BASE + "/places/export?format=csv")
    assert csv.ok and csv.body().startswith(b"\xef\xbb\xbfNama")
    print("OK ekspor CSV:", len(csv.text().strip().splitlines()) - 1, "baris")
    xlsx = page.request.get(BASE + "/places/export?format=xlsx")
    assert xlsx.ok and xlsx.body()[:2] == b"PK"
    print("OK ekspor XLSX:", len(xlsx.body()), "byte")

    # peta + interaksi
    page.get_by_test_id("place-card").first.hover()
    page.wait_for_timeout(600)
    print("OK marker peta:", page.locator(".leaflet-container path.leaflet-interactive, .marker-cluster").count() > 0)

    print("MASALAH BROWSER:", problems or "tidak ada")
    assert not problems, problems
    b.close()
    print("E2E SELESAI")
