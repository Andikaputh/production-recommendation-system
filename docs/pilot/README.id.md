[English runbook](README.md)

# RASA: panduan pilot satu merchant

Status: implementasi lokal untuk pilot terbatas, belum pilot bisnis yang tervalidasi. Tidak ada mitra, wawancara, transaksi, atau testimoni yang diklaim. Bahasa utama aplikasi adalah English. Pilihan English / Bahasa Indonesia tersedia pada builder dan disimpan saat halaman dimuat ulang. Demo model dan dashboard teknis tetap opsional dalam English.

## Urutan menjalankan

1. Instal Python 3.11+ dan Node 22+, `pip install -e ".[dev]"`, `npm ci --prefix frontend`, `npm run build --prefix frontend`.
2. Set variabel di bawah melalui environment proses, termasuk URL database pilot terpisah yang belum dipakai. Token admin hanya di server/operator, jangan dimasukkan ke frontend atau Git.
3. Pada database pilot baru tersebut jalankan `python scripts/seed_db.py --no-events` sekali untuk menyediakan kategori dan contoh demo yang terpisah dari merchant pilot. Jangan menjalankan seed ulang setelah impor karena default seeding menghapus tabel. Tabel baru dibuat saat startup; schema lama tidak dihapus. Jalankan satu proses `uvicorn apps.api.main:app --port 8000`. Akses melalui HTTPS pada jaringan pilot yang dibatasi.
4. Salin template katalog, minta merchant mengisi snapshot lengkap dengan waktu pengecekan sebenarnya. Jalankan impor dengan `dry_run=true`, perbaiki setiap `row`, `field`, `message`, lalu ulangi dengan `dry_run=false`. Semua baris harus valid sebelum satu pun ditulis.
5. Periksa `/readyz` (200 siap; 503 belum siap), susun misi, ganti barang, terima paket, buat ringkasan. Gunakan contoh sintetis lebih dahulu; pastikan analitik `source=pilot` tetap kosong.
6. Setelah kesepakatan pilot dan persetujuan peserta, impor katalog merchant dengan `synthetic=false`. Periksa harga/stok sebelum sesi. Bukti model sintetis tidak dipakai sebagai bukti kualitas katalog ini.
7. Operator meninjau ringkasan secara manual bersama merchant. Aplikasi hanya menyiapkan teks, tidak mengirim pesan, menempatkan pesanan, mereservasi stok, atau membayar.
8. Ekspor agregat melalui endpoint admin, tinjau kriteria lanjut/berhenti, lalu hapus atau arsipkan data sesuai persetujuan retensi.

```dotenv
RASA_MODE=pilot
RASA_ENV=production
RASA_DATABASE_URL=sqlite:///D:/rasa-pilot/rasa.db
RASA_PILOT_MERCHANT=pilot-store
RASA_PILOT_MERCHANT_NAME=Nama merchant yang disepakati
RASA_ADMIN_TOKEN=buat-token-acak-panjang-di-mesin-operator
RASA_CATALOG_TTL_HOURS=24
RASA_CORS_ORIGINS=http://localhost:8000
RASA_HANDOFF_LABEL=Proses pemesanan manual merchant
# Opsional: kosong berarti ongkir belum diketahui, 0 berarti gratis yang telah disepakati.
# RASA_PILOT_SHIPPING_IDR=10000
```

Path database harus ada, dapat ditulis, berada di penyimpanan persisten, dan dibatasi akses OS. Contoh di atas perlu disesuaikan. Compose memakai named volume persisten; jangan menghapus volumenya. Layanan Render free tanpa disk persisten hanya untuk demo, bukan pilot. Tidak ada deployment yang dipublikasikan dalam pekerjaan ini.

## Katalog dan impor

Template: `data/templates/pilot-catalog.csv`; contoh `data/templates/pilot-catalog-synthetic.csv` seluruhnya sintetis. Contoh bertanggal tetap akan kedaluwarsa; setelah verifikasi merchant, isi `updated_at` baru, jangan mengganti waktu hanya untuk melewati validasi. Waktu ISO 8601 wajib punya zona waktu. TTL default 24 jam berlaku untuk batch dan setiap produk; data di masa depan lebih dari lima menit ditolak.

`POST /api/v1/pilot/catalog/import` menerima JSON `{ "csv_text": "...", "synthetic": true, "dry_run": true }` dan `Authorization: Bearer <token>`. API menerima maksimal sekitar 60 KB CSV di payload 64 KB. Gunakan snapshot kecil untuk satu merchant. Kategori mengikuti kategori yang sudah ada, bukan kategori arbitrer. ID unik lintas merchant, harga rupiah bulat positif, stok bulat nonnegatif. Impor adalah penggantian snapshot lengkap: SKU merchant yang tidak dicantumkan dinonaktifkan; histori tidak dihapus. Rating tidak direka: produk impor berating 0/tidak tersedia, alur pilot tidak memakai rating sebagai preferensi bawaan.

Alternatif operator lokal dengan akses OS ke database: `python scripts/import_pilot_catalog.py data/templates/pilot-catalog-synthetic.csv` untuk dry run, tambahkan `--apply` untuk menulis. Gunakan `--real` hanya untuk data merchant nyata yang diizinkan dan setelah `RASA_MODE=pilot` diset. CLI tidak membuka akses jaringan atau mengirim data; otorisasinya mengikuti akses file database di OS.

Batch menyimpan checksum SHA-256 dan waktu impor di database. Kegagalan menulis membatalkan transaksi. Sesudah impor, permintaan pilot membaca database kembali sehingga tidak memakai cache katalog demo. Sebelum accept/handoff aplikasi mengecek semua barang, kebutuhan wajib, anggaran, merchant, grup eksklusif, metadata kedaluwarsa, dan perubahan harga. Perubahan harga/ongkir mengharuskan penyusunan dan penerimaan ulang. Penggantian mengubah hanya satu SKU di kategori yang sama dan menghasilkan revisi baru.

Ongkir kosong menghasilkan `total=null`, sisa sebelum ongkir, dan `final_budget_confirmed=false`. Jika dikonfigurasi, ongkir tetap dicadangkan sebelum optimasi. Pilot mengasumsikan tidak ada biaya tambahan lain; merchant wajib memastikan asumsi tersebut sebelum menggunakan nilai total. Tidak ada integrasi logistik atau reservasi stok; kesesuaian dengan stok sebenarnya tetap bergantung pada pembaruan merchant.

## Kontrak API alur

- `GET /api/v1/pilot/config`: mode, merchant, ongkir, TTL, mekanisme ringkasan lokal.
- `POST /api/v1/pilot/missions`: `mission_id` acak dari klien, `mission`, `preferences`; header `X-Session-ID` acak minimal 16 karakter. Input sama + ID sama mengembalikan hasil lama. ID sama + input berbeda ditolak.
- `GET /api/v1/pilot/missions/{id}`: memulihkan hasil tersimpan untuk sesi yang sama.
- `POST /api/v1/pilot/missions/{id}/replace`: revisi saat ini, `product_id`, `replacement_id`.
- `POST /api/v1/pilot/missions/{id}/accept`: revisi saat ini.
- `POST /api/v1/pilot/missions/{id}/handoff`: hanya setelah accept untuk revisi yang sama; mengembalikan teks dengan `sent=false`.
- `GET /api/v1/pilot/analytics?source=pilot`: token admin diperlukan; pilihan sumber `demo`, `test`, `pilot`.

Sesi acak adalah rahasia akses, bukan identitas terverifikasi. Jangan membagikan ID sesi atau mencatatnya ke log publik. SessionStorage dipisah per tab, hilang ketika tab ditutup. Snapshot dan event bertahan setelah restart server; pemulihan UI otomatis tersedia selama sesi tab masih ada. Revisi memakai optimistic locking; perubahan bersamaan yang bertabrakan ditolak. Gunakan satu worker dan operator impor terkoordinasi untuk pilot; isolasi transaksi impor dan aksi yang benar-benar bersamaan masih perlu pengujian beban sebelum multi-instance.

## Operasional

Token admin diperlukan untuk impor dan analitik pilot; analytics/experiments/session-feedback lama juga dilindungi pada production/pilot. Health tidak mengungkap data pelanggan; `/health` untuk diagnostik, `/readyz` untuk readiness gate. Timeout UI 20 detik menghasilkan kegagalan terlihat tanpa contoh palsu di alur pilot; demo model menyediakan fallback statis yang berlabel terpisah. Payload, enum, budget, input non-finite dan kategori divalidasi; batas request mencakup body sebenarnya. Rate limit proses tunggal belum merupakan gateway terdistribusi.

Pada mode pilot, endpoint katalog/misi/rekomendasi/feedback demo lama mengembalikan 409 agar data tidak tercampur. Gunakan keluarga `/api/v1/pilot` untuk alur aktif. Halaman teknis lama hanya contoh sintetis/fallback; hasil model langsung tersedia kembali pada mode demo.

Sebelum mulai: verifikasi backup/restore file SQLite saat aplikasi berhenti, akses file, HTTPS, secret acak, CORS domain tepat, jam server, dan `/readyz`. Jadwal tanggung jawab: merchant memperbarui katalog sebelum sesi dan saat harga/stok berubah; operator memeriksa readiness, error dan event; penanggung jawab riset menjelaskan persetujuan, menghapus PII dari input bebas, dan mengelola retensi. Usulan retensi 30 hari adalah asumsi yang harus disetujui, belum job penghapusan otomatis. Jangan merekam isi tujuan bebas di log.

Produksi berikutnya: integrasi inventori langsung + reservasi, konfirmasi pesanan terverifikasi, autentikasi merchant, rotasi secret, migrasi DB formal, backup otomatis, otorisasi per tenant, gateway rate limit, uji konkurensi dan beban, observabilitas terpusat. Semua itu di luar pilot satu merchant saat ini.
