# Peta Toko untuk Windows

Aplikasi desktop yang dipasang seperti program biasa: **sekali klik pasang, database dibuat otomatis**, tanpa Docker,
tanpa instalasi database terpisah, tanpa hak administrator.

---

## Untuk pengguna

### Persyaratan
- Windows 10 atau 11 (64-bit)
- ± 1,5 GB ruang disk, dan koneksi internet (untuk mengambil data dari Google Maps dan menampilkan peta)
- **Microsoft Edge** (sudah ada di Windows 10/11) **atau Google Chrome**. Jika keduanya tidak ada, aplikasi
  mengunduh Chromium sendiri saat pertama kali (± 150 MB).

### Memasang
1. Unduh `PetaToko-Setup-<versi>.exe` dari halaman **Releases** repositori ini.
2. Klik dua kali. Jika Windows menampilkan *"Windows protected your PC"* (SmartScreen), klik **More info → Run anyway**.
   Ini muncul karena installer belum ditandatangani sertifikat berbayar; lihat [Catatan keamanan](#catatan-keamanan).
3. Ikuti langkahnya (Berikutnya → Berikutnya). Di langkah **Lokasi data** biarkan bawaan kecuali Anda ingin data
   di drive lain.
4. Installer **membuat database secara otomatis** (1–2 menit, hanya sekali), lalu klik **Selesai**.

### Memakai
- Buka lewat **Start Menu → Peta Toko** (atau ikon desktop). Jendela aplikasi terbuka; sebuah **ikon pin biru**
  muncul di dekat jam (area notifikasi).
- Jendela aplikasi memakai profil browser terpisah (bukan profil Edge/Chrome harian Anda), tanpa sinkronisasi akun dan
  tanpa tawaran terjemahan. Riwayat dan sandi browser Anda tidak tersentuh.
- Menutup jendela **tidak** menghentikan pencarian yang sedang berjalan. Untuk benar-benar keluar: klik kanan ikon
  di dekat jam → **Keluar**. Klik ikon untuk membuka jendela kembali.
- Menu ikon: **Buka Peta Toko**, **Buka folder data**, **Lihat log**, **Keluar**.
- Opsi saat pemasangan: *jalankan di latar belakang saat Windows dimulai* (bawaan: mati).

### Data Anda
Disimpan di `%LOCALAPPDATA%\PetaToko` (atau folder yang Anda pilih saat pemasangan):

| Isi | Lokasi |
|---|---|
| Database toko & hasil pencarian | `pgdata\` |
| Log (untuk melaporkan masalah) | `logs\` |
| Screenshot/HTML saat scraping gagal | `debug\` |
| Pengaturan (port, kata sandi database acak) | `config.json` |

**Cadangan:** tutup aplikasi (ikon → Keluar), lalu salin seluruh folder data. Untuk memulihkan, letakkan kembali.
Database hanya menerima koneksi dari komputer ini (`127.0.0.1`) dengan kata sandi acak.

### Memperbarui
Jalankan installer versi baru; data lama dipertahankan. Aplikasi yang sedang berjalan dihentikan otomatis.

### Menghapus
*Settings → Apps → Peta Toko → Uninstall.* Anda akan ditanya apakah data juga dihapus (bawaan: **tidak**, supaya aman).

### Jika ada masalah
| Gejala | Yang dilakukan |
|---|---|
| Installer menampilkan "Database belum berhasil disiapkan" | Aplikasi akan mencoba lagi otomatis saat dibuka pertama kali. Jika tetap gagal, lihat `logs\setup.log` di folder data. |
| Jendela tidak terbuka / ikon tidak muncul | Buka ikon Peta Toko lagi; cek `logs\launcher.log`, `logs\api.log`, `logs\postgres.log`. |
| "Browser untuk scraping tidak ditemukan" | Pasang Microsoft Edge atau Google Chrome, lalu buka ulang aplikasi. |
| Pencarian berstatus **Diblokir** | Google menampilkan captcha. Aplikasi sengaja berhenti dan tidak mencoba melewatinya. Tunggu beberapa jam dan kurangi jumlah pencarian. |
| Antivirus menandai file | Lihat [Catatan keamanan](#catatan-keamanan). |
| Port bentrok | Tidak perlu tindakan: aplikasi memilih port kosong otomatis (bawaan 8765 dan 54329, bukan 5432). |
| Aplikasi/komputer mati mendadak | Buka lagi saja. Sisa proses lama dibersihkan otomatis dan database pulih sendiri. |
| Database hilang/rusak setelah instalasi | Buka aplikasi: setup dijalankan ulang otomatis (database baru; salinan lama folder `pgdata` dipindah, tidak dihapus). |
| Nama folder data berhuruf non-Latin (mis. Sirilik/Arab/Mandarin) | Didukung: PostgreSQL di Windows hanya menerima path dalam codepage ANSI, jadi aplikasi memetakan folder itu ke sebuah huruf drive sementara. Bila tetap gagal, pilih folder data berhuruf Latin (mis. `C:\PetaToko`). |

### Catatan keamanan
- Installer **belum ditandatangani** (sertifikat code-signing berbayar). Karena itu SmartScreen/antivirus bisa memberi
  peringatan pada program baru. Anda dapat memverifikasi berkas dengan checksum SHA-256 yang disertakan di halaman Releases:
  `Get-FileHash .\PetaToko-Setup-<versi>.exe -Algorithm SHA256`.
- Server hanya mendengarkan `127.0.0.1`; tidak dapat diakses dari komputer lain di jaringan.
- Data toko diambil dari halaman publik Google Maps. Penggunaannya tunduk pada Ketentuan Layanan Google; gunakan secara
  wajar dan atas tanggung jawab sendiri. Aplikasi membatasi kecepatan dan tidak mencoba melewati captcha.

---

## Untuk pengembang / pendistribusi

### Arsitektur (tanpa Docker, tanpa Redis)
```
PetaToko.exe (pythonw, ikon tray) ── peluncur: app/desktop/launcher.py
 ├─ pgsql\            PostgreSQL 16 + PostGIS 3.6 portabel (proses terpisah, 127.0.0.1:54329, scram-sha-256)
 ├─ uvicorn           API FastAPI + antarmuka React (satu alamat: 127.0.0.1:8765, tanpa CORS)
 └─ worker            python -m app.workers.runner  (antrean = tabel scrape_jobs di PostgreSQL)
Scraping: Playwright memakai Microsoft Edge / Chrome yang sudah terpasang (SCRAPE_BROWSER=auto).
```
Komponen terpasang di folder program (read-only); data pengguna terpisah di folder data. Python yang dipakai adalah
*embeddable* 3.12 (`runtime\`), sehingga tidak bergantung pada Python di komputer pengguna.

Modul: `backend/app/desktop/` — `paths.py`, `config.py`, `postgres.py` (initdb/start/stop), `setup.py` (dipanggil
installer dan peluncur; idempoten), `launcher.py`, `browser.py`. Installer: `desktop/installer/PetaToko.iss` (Inno Setup).

### Membangun installer
Prasyarat di mesin build: Windows 10/11 x64, Python 3.10+ (alat build), Node.js 20+, internet. Tanpa admin.

```powershell
powershell -ExecutionPolicy Bypass -File desktop\build.ps1
# hasil: desktop\dist\PetaToko-Setup-<versi>.exe  (+ .sha256)
# -Fast : pakai ulang runtime & pgsql dari build sebelumnya (jauh lebih cepat)
```
Skrip mengunduh komponen dari sumber resmi dan **memverifikasi SHA-256** terhadap `desktop/checksums.json`
(ubah berkas itu bila sengaja menaikkan versi komponen), memasang Inno Setup ke `desktop\.tools` bila belum ada, membangun
antarmuka, menguji bundel PostgreSQL+PostGIS (initdb → start → `CREATE EXTENSION postgis` → kueri jarak), menguji impor
seluruh modul, lalu mengompilasi installer.

Data wilayah (88 ribu desa) dibundel offline di `backend/app/desktop/data/regions.csv.gz`; dibuat ulang dari database
yang sudah ter-seed dengan `docker compose exec api python -m app.scripts.export_regions`.

### Menguji
```powershell
# uji instalasi nyata di folder terisolasi (path berspasi): pasang, setup DB, jalankan, stop, kill paksa + pulih,
# port bentrok, penyembuhan otomatis, perbarui, uninstall
powershell -ExecutionPolicy Bypass -File desktop\tools\test_install.ps1 -Installer desktop\dist\PetaToko-Setup-<versi>.exe
# skenario yang sama dengan folder data berhuruf Sirilik (path di luar codepage ANSI):
powershell -ExecutionPolicy Bypass -File desktop\tools\test_install.ps1 -Installer desktop\dist\PetaToko-Setup-<versi>.exe -UnicodeData
# uji alur pengguna + scraping nyata pada aplikasi yang sedang berjalan
python desktop\tools\e2e_installed.py http://127.0.0.1:8765 <folder-screenshot>
# tes unit
cd backend && python -m pytest tests/test_desktop.py
```

### Rilis
Naikkan `APP_VERSION` di `backend/app/desktop/__init__.py`, commit, lalu beri tag `vX.Y.Z` dan push. Workflow
`.github/workflows/windows-installer.yml` membangun installer di GitHub Actions dan melampirkannya ke Release
beserta checksum-nya. (Workflow ini belum pernah dijalankan di GitHub; periksa log run pertama.)

### Temuan teknis yang penting (agar tidak terulang)
- **PostgreSQL di Windows memakai argumen ANSI.** Path bernama non-Latin harus dialiaskan (`paths.ascii_alias`).
  *Directory junction tidak bisa dipakai*: Windows terbaru menolak melintasinya (galat 448, RedirectionGuard).
- **Pascal Script Inno:** `Copy`, `Trim`, `Lowercase` mengubah karakter non-Latin menjadi `?`. Gunakan pembantu di
  `PetaToko.iss` (`TrimUni`, `SubStr`, `PathStartsWith`). Kontrol input folder juga lossy; nilai sebenarnya dipegang di variabel.
- **`pg_ctl start` jangan memakai pipa** untuk stdout/stderr (postgres mewarisinya dan pemanggil menggantung).
- **Mode senyap tidak boleh menampilkan dialog:** `ShellExecuteEx` memakai `SEE_MASK_FLAG_NO_UI`; validasi dilakukan di
  `PrepareToInstall` (bukan hanya `NextButtonClick`).
- **Jendela Edge `--app`** dengan profil baru memunculkan dialog sinkronisasi akun dan tawaran terjemahan bila flag di
  `launcher.WINDOW_FLAGS` dihapus.
- PowerShell 5.1: `$env:X = ''` *menghapus* variabel; `-Filter` tidak mendukung `[0-9]`; `$PSScriptRoot` kosong di nilai
  bawaan parameter; `Start-Process -ArgumentList` tidak mengutip argumen berspasi; tanda kutip ganda di argumen `-c` Python hilang.

### Batasan yang diketahui
- Installer belum ditandatangani (SmartScreen akan memperingatkan). Tanda tangan butuh sertifikat berbayar.
- Hanya Windows 10/11 x64. Android belum tersedia.
- PostgreSQL berpindah *major version* (mis. 16 → 17) membutuhkan migrasi data (`pg_upgrade`); saat ini dikunci di 16.
- Lisensi: lihat `NOTICE.txt` (PostGIS berlisensi GPL; sumbernya ditautkan di sana).
