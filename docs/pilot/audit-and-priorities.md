# Audit awal dan prioritas implementasi

Audit 26 Oktober 2026; penelusuran dimulai dengan graphify. Graph awal tidak memiliki importer merchant: FR-017 sebelumnya menyebut pipeline CSV tervalidasi, namun implementasi yang ditemukan adalah load/validasi dataset sintetis. Klaim tersebut diperbaiki melalui importer baru, bukan dianggap sudah tersedia.

| Area | Sebelumnya tersedia | Hambatan pilot / hipotesis | Tindakan |
| --- | --- | --- | --- |
| Ranking | Model content/CF/hybrid, tuning validation, test temporal | Data sintetis tidak mewakili preferensi nyata; bobot demo tidak cocok SKU baru | Pertahankan demo model; rule baseline transparan untuk pilot |
| Paket | ILP/beam fallback, validasi domain | Top-score pruning dapat kehilangan rute murah; penggantian belum menjadi alur utuh | Pertahankan murah/per merchant dan full retry; revisi dan validasi semua barang |
| UX | Builder Inggris, parser, dashboard, fallback | Fokus belum satu paket awal kuliah/kos; dashboard bukan kebutuhan belanja | Builder utama Indonesia; teknis opsional |
| Katalog | Dataset sintetis + cache database | Belum ada snapshot merchant, TTL, stok kuantitas, admin importer | CSV atomik + laporan baris, checksum, timestamp, batas satu merchant |
| Konfirmasi | Item feedback save/dismiss | Tidak memeriksa ulang harga/stok/ongkir pada acceptance | Snapshot versi, recheck DB, ringkasan lokal saja |
| Evaluasi | Ranking, basket, ablation, simulator | 97,50 vs 98,33 feasibility; p95 78,12 vs 88,41; subset 180 vs eligible utama | Run ulang bobot beku, provenance, paired ablation, dua baseline sederhana, generator ringkasan |
| Pengukuran | Event produk dan analitik demo | Belum ada funnel paket; klik bukan order | Tabel misi/event baru, source terpisah, idempotency, denominator eksplisit |
| Operasi | SQLAlchemy SQLite/Postgres, health, CORS, rate limit | Analytics publik, persistence deployment tergantung disk | Token admin, readiness, volume DB, panduan single process |
| Bisnis | Problem notes sintetis | Permintaan, segmen, merchant pembayar belum diuji | Interview, usability tiga kondisi, proposal, unit economics asumsi, pitch jujur |

Prioritas kerja: (1) kebenaran evaluasi dan batas klaim; (2) katalog/biaya/konfirmasi agar paket dapat dipertanggungjawabkan; (3) UX dan event; (4) verifikasi skenario gagal; (5) dokumen pilot dan validasi eksternal. Semua dipisah dari pembayaran, marketplace baru, deployment publik, dan kontak mitra.

Fitur demo/simulasi yang tetap ada: semua model dan benchmark sintetis, cold-start/A-B simulation, halaman teknis Inggris, contoh statis frontend. Fitur pilot repository: importer, satu merchant, rule ranking, optimasi, snapshot, penggantian, acceptance, teks ringkasan tanpa pengiriman. Yang membutuhkan bukti eksternal: kualitas rekomendasi pada katalog nyata, manfaat terhadap belanja biasa, update stok yang dapat diandalkan, kesediaan membayar dan unit economics aktual.
