# Verifikasi dan serah-terima RASA

26 Oktober 2026. Implementasi lokal portfolio dan persiapan pilot terbatas selesai. Validasi pengguna, merchant, manfaat bisnis dan operasi nyata belum dilakukan. Tidak ada deployment publik, pembayaran, kontak mitra atau pesanan yang dikirim.

## Perubahan dan manfaat

- Alur utama English dengan pilihan Bahasa Indonesia untuk kuliah/kos; kebutuhan wajib/tambahan, gaya/warna dan budget. Dashboard teknis opsional. Mengubah input membatalkan hasil lama agar paket dengan budget sebelumnya tidak diterima secara keliru.
- SKU pilot baru memakai `pilot-rules-v1` yang transparan; hybrid sintetis tetap demo terpisah. Impor CSV atomik memeriksa baris/kolom/ID/harga/stok/merchant/waktu, dry run, checksum dan TTL; SKU hilang dinonaktifkan.
- Subtotal dan ongkir terpisah. Total null jika ongkir belum diketahui. Biaya tetap yang dikonfigurasi dicadangkan sebelum optimasi, tanpa mengarang integrasi logistik.
- Penggantian memeriksa seluruh paket, menaikkan revisi dan membatalkan penerimaan versi lama. Accept/handoff membaca ulang DB untuk harga, biaya, status/kuantitas stok dan data stale. Ringkasan hanya teks lokal dengan `sent=false`.
- Funnel tersimpan per sesi/misi/revisi, idempotency dan source demo/test/pilot terpisah. Analitik admin memakai denominator eksplisit; order, revenue, margin dan retur tetap null.
- Token admin, isolasi endpoint demo saat pilot, body size nyata, penyamaran error DB, client rate limit, penyimpanan persisten dan readiness. Fonts eksternal dihapus.
- Perbaikan pruning murah/per merchant, full retry, eksklusi dalam beam, fallback CBC, metrik inventory, dan keselarasan validation/inference untuk cold-start serta tie.
- Sumber tunggal evaluasi dengan provenance, baseline murah/kurasi, ablation berpasangan dan CI, sinkronisasi empat dokumen dan gate CI. Paket validasi bisnis dan kalkulator economics memakai asumsi eksplisit.

## Pemeriksaan yang benar-benar dijalankan

| Pemeriksaan | Hasil |
| --- | --- |
| `pytest --cov=rasa --cov-fail-under=50` | 33 passed, coverage 57,69%, satu deprecation warning Starlette/httpx |
| Integrasi pilot setelah penguatan terakhir | 13 passed, sudah termasuk 33 tes penuh |
| `ruff check .` | Lulus |
| `npm run lint --prefix frontend` | Lulus |
| `npm run build --prefix frontend` | Production build Vite lulus |
| `node --test frontend/scripts/i18n.test.mjs` | 3 pengujian bahasa lulus |
| `python scripts/evaluate.py` | 7 eksperimen ranking, 6 konfigurasi paket, 120 misi, ablation dan cold-start; bobot beku |
| `python scripts/audit_candidate_pruning.py` | 120 misi: policy lama 117 layak, baru 119, seluruh retrieved 119 |
| `python scripts/audit_validation_scoring.py` | 175 pengguna validation, 0 perbedaan urutan cache/inference, tidak memilih bobot baru |
| `python scripts/sync_evaluation_docs.py --check` | Lulus, ringkasan sesuai JSON |
| Onboarding browser smoke | Welcome kunjungan pertama, skip tersimpan, replay, empat langkah, navigasi kembali, English/Indonesia, Esc/tutup, fokus keyboard, input tetap, popup seluler dan budget tidak tertutup: lulus |
| Maximum budget pada demo teknis | Nilai rupiah bulat termasuk 250000 valid; nol/negatif/pecahan/melebihi batas ditolak; submit 250000 mencapai API dan menampilkan hasil langsung |
| Chrome headless lokal | Kedua bahasa: feasible, accept, ringkasan, infeasible, API gagal, pilihan bahasa tersimpan, input dan hasil terjaga saat berganti bahasa; 0 page errors; viewport 390 px tanpa horizontal overflow |
| `python scripts/pilot_economics.py` | Kalkulasi dasar dan sensitivitas selesai; semua nilai asumsi ilustratif |
| `python -m graphify update .` | AST diperbarui; statistik terbaru tersedia di graphify-out/GRAPH_REPORT.md |
| Integritas graph | 0 dangling edge; 1 self-loop adalah rekursi `json_safe()` yang diekstrak |
| `git diff --check` | Lulus; pemberitahuan konversi LF/CRLF pada Windows |

Lingkungan: Windows, Python 3.12.14 pada `.venv-pilot`, pandas 2.3.3, PuLP 3.3.2, scikit-learn 1.4.1.post1, Node 24.19.0, Chrome lokal. Launcher Python/graphify lama tidak dapat diakses dalam sandbox; virtual environment terpisah digunakan. Tes/CBC/socket browser dijalankan dengan izin eksekusi lokal di luar sandbox setelah temporary files/socket sandbox menghambat percobaan awal. Tidak ada penolakan approval yang masih menghambat pekerjaan.

Sumber hasil: `artifacts/reports/evaluation.json` beserta waktu run dan SHA-256. NDCG@10 EXP-006 0,0709 pada 448 pengguna eligible; feasibility EXP-007 99,17% pada 120 misi sintetis. Lihat [investigasi evaluasi](../model/evaluation-audit.md) untuk batas interpretasi.

Artefak tambahan: `candidate-pruning-audit.json`, `validation-scoring-audit.json`, `ui-smoke.json` di artifacts/reports. [Desktop](pilot-ui-desktop.png) dan [seluler](pilot-ui-mobile.png) adalah screenshot pengujian lokal pada data sintetis. Browser script `frontend/scripts/smoke.cjs` membutuhkan paket Playwright dan Chromium; `RASA_TEST_URL` menentukan localhost, `RASA_BROWSER_EXECUTABLE` opsional untuk Chrome yang sudah terpasang. Script membuat event, sehingga harus memakai database demo terpisah, bukan sesi pilot nyata.

## Skenario penerimaan

Misi layak memenuhi kebutuhan wajib dan budget barang. Budget tidak cukup memberi saran batas bawah/kategori tanpa stok. Penggantian berbeda kategori atau melanggar budget ditolak; penggantian sah menaikkan revisi. Katalog salah, duplikat ID, merchant lain, harga non-finite, stale, dan dry run diuji. Perubahan harga walau masih terjangkau memerlukan review. Kuantitas nol menolak konfirmasi walau status lama available. Ringkasan sebelum acceptance ditolak. Retry create/accept/handoff tidak menggandakan event; sesi lain tidak dapat membaca misi. Data dan snapshot tersimpan di DB melintasi sesi akses; UI dapat memulihkan misi selama sesi tab sama.

## Batas verifikasi

- Belum ada katalog merchant nyata, calon pengguna, wawancara, WTP, transaksi, margin, retur atau eksperimen pengguna.
- Docker build/run, backup-restore operasional, CI Linux/Python 3.11 dan deployment hosting belum dijalankan dari sesi ini; keberadaan konfigurasi bukan bukti lulus.
- Belum uji beban, fault injection disk/crash transaksi, atau konkurensi impor/accept multi-instance. Gunakan satu proses dan koordinasi operator. Stok belum direservasi langsung.
- Browser memeriksa alur dan responsif dasar; belum audit aksesibilitas screen reader atau semua perangkat/browser.
- Full search masih setelah filter/cap retrieval; beam/timeout bukan bukti infeasibility global. Model dan aturan belum diuji pada preferensi nyata.
- Retensi/penghapusan, backup otomatis, autentikasi merchant/tenant dan integrasi order belum otomatis. Secret/CORS/HTTPS/database persisten perlu konfigurasi lokasi pilot.
- Graph diperbarui AST tanpa biaya API. Semantic doc extraction tidak dijalankan; sebagian label komunitas dari hub. Graphify mencatat 8 file tanpa simbol dan 27 format tidak didukung termasuk notebook. Tidak ada klaim seluruh dokumen tercakup secara semantik.

## Urutan tindakan pengguna dan mitra

1. Ikuti [runbook pilot](../pilot/README.md): database terpisah, secret, biaya, katalog sintetis, readiness dan backup.
2. Jalankan [wawancara/usability](../pilot/business-validation.md) dengan persetujuan peserta untuk menguji masalah dan segmen.
3. Sepakati satu merchant: izin katalog, update harga/stok, pemesanan manual, biaya, retensi, tanggung jawab, dan kriteria lanjut/berhenti.
4. Impor katalog nyata yang diizinkan: dry run, perbaiki error, apply dan periksa kesiapan sebelum membuka sesi terbatas.
5. Jalankan pilot formatif dan baca funnel source=pilot. Tinjau ringkasan bersama merchant. Uji harga dan eksperimen berdaya cukup hanya setelah manfaat serta kelayakan operasional didukung bukti.


Bukti onboarding: `artifacts/reports/onboarding-smoke.json`; [welcome desktop](onboarding-desktop.png) dan [welcome mobile](onboarding-mobile.png). Pemeriksaan alur shopping dua bahasa dan regresi maximum budget juga dijalankan ulang setelah penambahan tutorial.
