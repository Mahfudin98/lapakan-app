# Peta Toko

Mengumpulkan dan menelusuri data toko dari Google Maps berdasarkan wilayah administratif Indonesia dan jenis toko.
100% gratis dan self-hosted (Playwright, tanpa Google Places API).

> Status: **Selesai**: database, seed wilayah, scraper, antrean job + API, frontend, halaman hasil, dan **installer Windows**.
>
> **Pengguna awam (Windows):** unduh installer terbaru dari [Releases](https://github.com/Mahfudin98/lapakan-app/releases/latest), klik dua kali, selesai.
> Panduan lengkap: [desktop/README.md](desktop/README.md).
> Bagian di bawah ini untuk pengembang / yang menjalankan dengan Docker.

## Setup

```bash
cp .env.example .env
docker compose up -d --build
```

`api` otomatis menjalankan `alembic upgrade head` saat start.

## Seed data

```bash
# kategori preset (cepat)
docker compose exec api python -m app.scripts.seed_categories

# wilayah Kemendagri (mengunduh ~7.500 file JSON dari GitHub Pages, di-cache di ./data/wilayah_cache)
docker compose exec api python -m app.scripts.seed_regions
# opsi cepat tanpa desa/kelurahan:
docker compose exec api python -m app.scripts.seed_regions --max-level 3
```

Script bisa dijalankan ulang kapan saja (upsert, cache dipakai ulang).

## Endpoint (Tahap 1)

| Endpoint | Keterangan |
|---|---|
| `GET /health` | cek API + versi PostGIS |
| `GET /regions?level=&parent=&q=&limit=` | level 1=provinsi, 2=kab/kota, 3=kecamatan, 4=desa |
| `GET /categories` | kategori preset |

Dokumentasi interaktif: http://localhost:8000/docs

## Scraper CLI (Tahap 2)

Satu query, tanpa DB. Lewat Docker:

```bash
docker compose --profile scraper run --rm scraper \
  python -m app.scraper.cli "toko kosmetik di Andir, Kota Bandung" --max-results 20
# mode detail (klik tiap hasil: alamat lengkap, website, jam buka) + simpan JSON
docker compose --profile scraper run --rm scraper \
  python -m app.scraper.cli "salon di Coblong, Kota Bandung" --max-results 10 --detail --json /data/out.json
```

Atau lokal (tanpa Docker):

```bash
cd backend
python -m venv .venv && .venv/Scripts/pip install -r requirements.txt   # Linux/Mac: .venv/bin/pip
.venv/Scripts/python -m playwright install chromium
DEBUG_DIR=../data/debug .venv/Scripts/python -m app.scraper.cli "salon di Coblong, Kota Bandung"
```

Exit code: `0` sukses, `1` gagal (screenshot + HTML disimpan di `DEBUG_DIR`), `2` **blocked** (captcha/unusual traffic; tidak ada upaya bypass).

Tes parser (fixture HTML nyata di `backend/tests/fixtures`):

```bash
cd backend && python -m pytest
```

**Keterbatasan data (diamati 2026-10-10):** Google Maps tanpa login menampilkan "tampilan terbatas". Di mode ini
*jumlah ulasan tidak dirender* (hanya rating), dan jam buka hanya baris hari ini. Parser tetap membaca jumlah
ulasan bila ada (`aria-label` "N ulasan" atau token "(N)"), selain itu bernilai `NULL`.
Struktur Google bisa berubah kapan saja. Semua selector ada di `backend/app/scraper/selectors.py`.

## Job scraping (Tahap 3)

`docker compose up -d` menjalankan `api`, `worker` (**1 job / 1 browser** pada satu waktu), `db`, dan `web`.
Tidak ada Redis: antrean job adalah tabel `scrape_jobs` di PostgreSQL. API membuat job `queued`, worker
(`python -m app.workers.runner`) mengambilnya; pembatalan lewat kolom `cancel_requested`. Worker dijaga satu saja
dengan advisory lock PostgreSQL.

| Endpoint | Keterangan |
|---|---|
| `POST /jobs/preview` | daftar query yang akan dijalankan (tanpa membuat job) |
| `POST /jobs` | buat job → status `queued` |
| `GET /jobs`, `GET /jobs/{id}` | status + progres (polling) |
| `POST /jobs/{id}/cancel` | batalkan (antre: langsung; berjalan: dihentikan di antara aksi) |

```bash
curl -X POST localhost:8000/jobs -H 'content-type: application/json' -d '{
  "region_kode": "3273180",            # level 1-4; level 1/2 dipecah per kecamatan
  "category_ids": [2], "keywords": ["toko skincare"],
  "max_results": 200, "detail": false, "force_refresh": false }'
curl localhost:8000/jobs/<id>
```

Aturan:
- `max_results` = batas **total** tempat unik per job (bukan per query). Default 200.
- Wilayah level 1/2 dipecah per kecamatan; batas `SCRAPE_MAX_QUERIES` (300) menolak rencana yang terlalu besar.
- Cache: query yang sama (dan `detail` yang cukup) dalam `SCRAPE_CACHE_DAYS` (7) hari tidak di-scrape ulang. `force_refresh` melewatinya.
- Status: `queued` → `running` → `done` | `failed` | `blocked` | `cancelled`. `blocked` = captcha/unusual traffic, job berhenti (tidak ada bypass), pesan di field `error`.
- Upsert berdasar `google_place_key`; nilai lama tidak ditimpa `NULL` (data mode detail tidak hilang). `last_scraped_at` diperbarui.
- `in_region` (true/false/NULL=unknown) dihitung dari teks alamat (tidak ada poligon wilayah). Alamat pendek tanpa nama
  kecamatan hasilnya `NULL`; mode `detail` memberi alamat lengkap sehingga lebih akurat.
- Job `running` yang tertinggal saat worker mati ditandai `failed` ketika worker start lagi.

Tes (termasuk integrasi DB, jalankan di container): `docker compose exec api python -m pytest`.
Tes yang menyentuh database otomatis memakai database terpisah `<nama>_test` (dibuat otomatis), supaya job uji tidak
diambil worker sungguhan dan data asli aman.

## Antarmuka

`docker compose up -d` menjalankan `web` (Vite) di http://localhost:5173 (port: `WEB_PORT`; alamat API: `VITE_API_URL`, harus ada di `CORS_ORIGINS`).
Pengembangan tanpa Docker: `cd frontend && npm install && npm run dev`; cek tipe + build: `npm run build`.

Alur satu halaman:
1. **Beranda** (`#/`): pilih wilayah (level muncul bertahap, boleh berhenti di mana pun) dan jenis toko (chip + kata kunci bebas),
   lalu **Mulai cari toko**. Di bawahnya: riwayat pencarian dan tautan ke semua toko tersimpan (`#/semua`).
2. **Hasil pencarian** (`#/job/<id>`): panel progres langsung (pencarian ke-N dari M, jumlah toko, tahap yang sedang berjalan, Batalkan)
   dan **hasil muncul selagi scraping berjalan** (daftar tersimpan segera setelah di-scrape, sebelum mode detail selesai).
   Daftar menampilkan **seluruh hasil scraping** job itu; toko yang alamatnya jelas di wilayah lain diberi lencana "Di luar wilayah"
   dan bisa disembunyikan dengan satu klik. Tombol **Perbarui data** mengulang pencarian tanpa cache.
3. Tampilan **Daftar** (kartu + peta berdampingan), **Peta**, atau **Tabel**. Hover kartu menyorot marker (oranye), klik kartu/marker
   memilihnya (merah) dan membuka detail. Kartu punya tautan telepon (`tel:`), website, dan Google Maps (hanya http/https yang dijadikan tautan).
4. Pencarian nama, urutan (skor terbaik, terdekat dari saya, rating, ulasan, nama, terbaru), filter cepat (★ 4+, ada telepon, ada website, kategori), dan **Unduh** CSV/Excel mengikuti filter yang aktif.

## API hasil: sorting, filter, ekspor

| Endpoint | Keterangan |
|---|---|
| `GET /places` | daftar (pagination server-side: `page`, `page_size` ≤ 200) + `meta` |
| `GET /places/map` | titik ringan untuk peta (maks 5.000) |
| `GET /places/facets` | kategori Google + jumlah, mengikuti filter lain |
| `GET /places/export?format=csv\|xlsx` | ekspor hasil yang sedang difilter & diurutkan (maks 50.000 baris) |
| `GET /places/{id}` | satu tempat |

Filter (query string, sama untuk semua endpoint di atas): `q`, `job_id`, `region_kode` (termasuk wilayah di bawahnya),
`kategori` (boleh berulang), `min_rating`, `min_reviews`, `has_phone`, `has_website`, `hide_closed`,
`region_filter=all|hide_outside|inside_only`.

Pengurutan `sort=`:
- `skor` (default): rata-rata Bayesian `(v/(v+m))·R + (m/(v+m))·C`. `C` = rata-rata rating **hasil yang sedang
  difilter** (jadi berubah mengikuti filter), `m` = 20 (`BAYESIAN_M` atau `?m=`). 5,0 dari 2 ulasan tidak mengalahkan 4,8 dari 900 ulasan.
- `terdekat`: butuh `lat` & `lng`; jarak `ST_Distance` (geography) dalam km. `distance_km` juga dikembalikan untuk sort lain bila titik acuan diberikan.
- `terpopuler` (ulasan terbanyak), `rating`, `nama` (A–Z), `terbaru` (terakhir di-scrape).

**Toko tanpa jumlah ulasan** (hampir semua, lihat keterbatasan di atas): skor Bayesian-nya `NULL` dan mereka diurutkan
di bawah; UI menampilkan "n/a" dan catatan jumlahnya. Jumlah ulasan baru berguna bila Google menampilkannya.

Ekspor CSV memakai UTF-8 + BOM (terbuka benar di Excel) dan sel yang diawali `= + - @` diberi apostrof untuk mencegah formula injection.

Titik acuan jarak: geolokasi browser (otomatis saat memilih "Terdekat dari saya") atau klik di peta. Peta memakai tile OpenStreetMap + marker clustering.

## Lisensi

Gratis dan open source, dilisensikan di bawah [MIT](LICENSE): boleh dipakai, diubah, dan dibagikan tanpa biaya.

## Struktur

```
backend/app/{api,models,services,scraper,workers,scripts}
backend/alembic/versions
```
