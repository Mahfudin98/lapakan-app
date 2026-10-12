## Peta Toko untuk Windows

Aplikasi untuk mengumpulkan dan menelusuri data toko dari Google Maps berdasarkan wilayah dan jenis toko. Dipasang seperti
program biasa: **database dibuat otomatis saat instalasi**, tanpa Docker dan tanpa hak administrator.

### Cara memasang
1. Unduh **{{FILE}}** di bawah (bagian *Assets*).
2. Klik dua kali. Ikuti langkahnya (Maju → Maju → Pasang), tunggu 1–2 menit saat database disiapkan, lalu **Selesai**.
3. Buka lewat **Start Menu → Peta Toko**.

Persyaratan: Windows 10/11 64-bit, ± 1,5 GB ruang disk, koneksi internet, dan Microsoft Edge atau Google Chrome
(Edge sudah ada di Windows).

### Jika Windows menampilkan peringatan
{{SIGNATURE}}

Windows SmartScreen memperingatkan setiap program baru yang belum dikenal. Ini **bukan** berarti berkasnya berbahaya.
Untuk melanjutkan: klik **More info** (Info lebih lanjut) → **Run anyway** (Tetap jalankan).

Ingin memastikan berkas tidak diubah orang lain? Bandingkan checksum-nya (PowerShell):

```powershell
Get-FileHash .\{{FILE}} -Algorithm SHA256
```
Harus sama dengan:

```
{{SHA256}}
```

Berkas ini dibangun otomatis oleh GitHub Actions dari kode di repositori ini (lihat tab *Actions* dan *Attestations*), dan seluruh
kode sumbernya terbuka sehingga dapat diperiksa. Jika antivirus Anda menandai berkas ini, itu kemungkinan *false positive*;
silakan laporkan ke vendor antivirus tersebut (untuk Microsoft Defender:
https://www.microsoft.com/en-us/wdsi/filesubmission).

### Data dan privasi
Semua data tersimpan di komputer Anda (`%LOCALAPPDATA%\PetaToko`). Database hanya menerima koneksi dari komputer ini.
Pengambilan data dari Google Maps tunduk pada Ketentuan Layanan Google; gunakan secara wajar dan atas tanggung jawab sendiri.

Dokumentasi lengkap: [desktop/README.md](https://github.com/Mahfudin98/lapakan-app/blob/main/desktop/README.md)
