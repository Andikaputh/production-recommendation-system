# Pengukuran dan rancangan eksperimen

## Event dan denominator

Sumber kebenaran alur paket adalah `pilot_missions` dan `pilot_events`, terpisah dari `interaction_events` demo lama. Identitas sesi acak di tab; identitas misi acak klien; revisi server. Waktu server UTC. Primary key event deterministik SHA-256 dari `(mission_id, event_type, revision)` plus unique constraint DB mencegah duplikasi pengiriman ulang. Retry create memakai mission_id sama; perubahan input memerlukan ID baru. Event tidak boleh dibuat dari klien sesuka hati: backend mencatat transisi setelah validasi. Tidak ada event frontend yang dianggap pesanan terkonfirmasi.

| Event | Pemicu | Deduplikasi |
| --- | --- | --- |
| mission_created | input sah dan snapshot pertama tersimpan | sekali per misi |
| basket_ready | hasil pertama layak | sekali per misi |
| mission_infeasible | hasil pertama tidak layak | sekali per misi |
| item_replaced | satu penggantian sah tersimpan | sekali per revisi baru |
| basket_accepted | pengguna menerima paket, pemeriksaan ulang lolos | sekali per revisi |
| handoff_prepared | ringkasan lokal dibuat setelah penerimaan versi sama | sekali per revisi |

Sumber `pilot` hanya katalog impor `synthetic=false` pada mode pilot. Impor `synthetic=true` selalu `demo`; mode nonpilot dalam test menggunakan `test`. Tidak menggabungkan ketiganya. Model hybrid teknis tetap memakai event demo lama yang bukan denominator funnel paket ini.

| Metrik endpoint | Numerator / denominator |
| --- | --- |
| mission_completion_rate | misi unik dengan basket_accepted / semua misi sumber terpilih |
| basket_acceptance_among_feasible | misi unik diterima / misi hasil pertama layak |
| mean_seconds_to_accept_among_accepted | rata-rata waktu server dari create ke penerimaan pertama, hanya misi diterima; laporkan juga completion agar survivor bias terlihat |
| replacement_events_per_mission | jumlah revisi penggantian sukses / semua misi; kegagalan mengganti belum dihitung |
| mean_required_coverage_latest | rata-rata coverage snapshot terakhir / semua misi, termasuk gagal dengan coverage nol |
| infeasible_rate | misi hasil pertama tak layak / semua misi |
| handoff_prepared_rate | misi unik dengan ringkasan lokal / semua misi |

Jika denominator nol, nilai `null`, bukan 0%. Funnel hanya mencakup create yang sah dan berhasil disimpan. Pengunjung yang keluar sebelum submit, parse/validation errors, API gagal sebelum persistence, dan pengguna yang tidak memberi persetujuan tidak tercakup; jangan menyebutnya visitor conversion. Retry dengan ID sama tidak menjadi misi baru. Perubahan kebutuhan sesudah hasil sukses menghasilkan misi baru; untuk eksperimen analisis utama gunakan satu misi pertama per peserta/sesi untuk menghindari overweight peserta aktif. Agregat API saat ini menghitung seluruh histori source tanpa rentang waktu; gunakan DB export dengan batas cohort yang ditetapkan sebelum analisis.

Orders, omzet, margin, retur, fulfillment, dan biaya akuisisi aktual masih `null`/belum tersedia. Diperlukan integrasi order_id terverifikasi dari merchant yang dikaitkan dengan mission_id, timestamps, order status, refund/retur, net sales, COGS, biaya fulfillment, diskon yang ditanggung pihak terkait, fee dan rekonsiliasi. Jangan mengisi nilai ini dengan click, save, purchase_proxy, atau handoff_prepared.

## Rancangan eksperimen pengguna, belum dijalankan

Hipotesis utama: RASA meningkatkan penyelesaian tugas paket lengkap yang layak dibanding pengalaman toko biasa, dengan biaya akhir yang dipahami peserta. Segmen awal mahasiswa yang sedang menyiapkan kuliah/kos dan katalog satu merchant adalah hipotesis rekrutmen.

Unit randomisasi: peserta baru, satu assignment persisten per peserta pada sesi studi; bukan item atau klik. Dua lengan utama: toko biasa (pencarian/kategori merchant) dan RASA; katalog, harga, anggaran, tugas, durasi dan fasilitator sama. Tugas pertama per peserta untuk analisis intention-to-treat; kegagalan API tetap masuk denominator treatment. Pengalaman paket kurasi digunakan sebagai pembanding ketiga pada usability formatif, jangan menambah lengan eksperimen tanpa menaikkan sampel dan mengoreksi multiple comparisons.

Primary: proporsi peserta menyelesaikan paket semua kebutuhan wajib dalam 10 menit, sesuai budget yang diketahui, dan mampu menyebut biaya belum diketahui. Secondary: waktu tugas termasuk censoring/dropout, penggantian, acceptance, handoff-prepared. Guardrail: nol pelanggaran batas biaya yang diklaim pasti, kesalahpahaman ongkir <10% (ambang usulan), error API <5%, abandonment tidak memburuk, tidak ada pengiriman pesanan tanpa persetujuan. Hentikan jika terjadi kebocoran data atau klaim biaya salah; investigasi sebelum lanjut.

Ukuran sampel: asumsi ilustratif control completion 50%, target 65%, alpha dua sisi 5%, power 80%, dua proporsi independen. Pendekatan normal: n per lengan = (1,96 sqrt(2 pbar(1-pbar)) + 0,84 sqrt(p0(1-p0)+p1(1-p1)))² / (p1-p0)² ≈ 169,3, dibulatkan ke atas menjadi 170; tambah cadangan kehilangan data 15% dengan membagi 0,85 => 200 per lengan. Ini perencanaan, bukan hasil. Ganti baseline/MDE berdasarkan studi formatif sebelum preregistrasi; 5-8 usability peserta tidak cukup membuktikan uplift 15 poin. Jangan menghentikan studi saat p-value pertama terlihat baik. Laporkan CI, denominator, attrition, error, ketidakseimbangan baseline, dan batas generalisasi satu merchant.
