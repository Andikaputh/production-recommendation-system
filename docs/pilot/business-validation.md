# Paket validasi bisnis RASA

Semua hipotesis dan angka perencanaan di sini belum tervalidasi. Tidak ada wawancara atau riset pasar eksternal yang diklaim. Proposal ini adalah rekomendasi kerja yang dapat diuji, bukan fakta permintaan pasar.

## Hipotesis dan bukti yang dibutuhkan

| Area | Hipotesis | Cara menguji dan bukti penyangkal |
| --- | --- | --- |
| Segmen | Mahasiswa awal kuliah/pindah kos belanja beberapa kategori dengan budget tetap | Cerita pembelian terakhir; tolak jika sebagian besar hanya butuh satu barang atau sudah memiliki barang |
| Masalah | Menyatukan kebutuhan dan biaya lebih sulit dari mencari satu produk | Observasi proses belanja manual; tolak jika kurasi toko menyelesaikan tugas sama cepat |
| Nilai | Paket layak dan penggantian mengurangi usaha dan salah hitung | Uji tugas manual/kurasi/RASA, ukur coverage, waktu dan pemahaman ongkir |
| Pembayar | Merchant bersedia membayar alat paket untuk katalog sendiri | Tawarkan pilot dengan biaya nyata yang diusulkan dan ruang lingkup tertulis; minat verbal saja tidak cukup |
| Distribusi | Merchant dapat membawa pengunjung melalui halaman katalog atau QR toko | Merchant memberi slot distribusi dan peserta ikut secara sukarela; ukur eligible exposure, jangan merekayasa traffic |
| Pembeda | Kebutuhan wajib, optimasi anggaran, dan validasi penggantian lebih berguna dari bundling tetap | Bandingkan dengan bundling toko, spreadsheet dan bantuan staf |

## Wawancara pengguna, 20-30 menit

Mulai dengan persetujuan, jelaskan tidak sedang menjual, tidak perlu informasi identitas. Minta cerita pembelian terakhir untuk kuliah/kos: kapan, pemicu, siapa memutuskan, barang yang sudah dimiliki, daftar kebutuhan, budget dan biaya di luar harga barang. Tanyakan langkah demi langkah mencari serta mengganti pilihan; bagian mana yang memakan waktu; apa yang batal dan mengapa. Minta contoh bukti nonpribadi seperti daftar yang telah dianonimkan, hanya bila peserta nyaman. Tanyakan solusi sekarang, biaya waktu, kepuasan dan kejadian pengecualian. Hindari pertanyaan "apakah Anda suka AI?" atau "bukankah paket otomatis membantu?". Baru setelah cerita, tunjukkan konsep dan minta peserta menjelaskan kapan ia tidak akan memakainya. Catat verbatim pendek dengan izin, pisahkan observasi dari interpretasi.

## Wawancara merchant, 30 menit

Minta contoh permintaan paket terakhir, cara staf menangani budget, waktu staf, pembaruan stok/harga, SKU yang sulit dibundel, penanganan ongkir, retur dan pemesanan. Siapa bertanggung jawab pada katalog, siapa memutuskan software dan siapa membayar? Alat apa yang sudah dipakai dan berapa biaya aktualnya jika bersedia berbagi? Bukti apa yang diperlukan agar merchant melanjutkan layanan? Uji penawaran konkret di akhir dengan harga, batas penggunaan, pekerjaan integrasi, dan pembatalan yang jelas. Jangan menyebut perkiraan margin sebagai margin merchant. Jangan meminta customer list, akun produksi, atau menghubungi calon mitra tanpa izin pengguna.

## Usability formatif: manual, kurasi, RASA

Rekrut usulan 5-8 peserta untuk menemukan masalah, bukan mengestimasi conversion. Gunakan tiga tugas setara dengan katalog dan budget sama; counterbalance urutan untuk mengurangi learning effect. Tugas: susun kebutuhan awal kuliah; hadapi budget tidak cukup; ganti botol setelah stok habis; jelaskan subtotal, ongkir dan total. Lengan manual memakai halaman kategori toko, kurasi memakai paket tetap yang ditetapkan sebelum sesi, RASA memakai builder. Jangan memberi petunjuk tombol kecuali peserta benar-benar tersangkut; catat bantuan sebagai bantuan. Think-aloud, rekam waktu, coverage, error biaya, permintaan bantuan, kompromi yang dipahami, alasan menolak, dan preferensi akhir dengan alasan. Jika belum ada toko mitra, gunakan prototipe manual pada katalog sintetis dan labeli seluruh sesi sebagai simulasi tugas, bukan belanja nyata.

## Proposal pilot terbatas

Usulan: satu merchant, 20-100 SKU terpelihara pada kategori yang sesuai, 2-4 minggu setelah pemeriksaan kesiapan, tanpa checkout dan tanpa integrasi logistik. Merchant menyediakan izin katalog, harga/stok bertimestamp, daftar biaya tetap atau status ongkir belum diketahui, SOP pemesanan, dan penanggung jawab pembaruan. Tim RASA menyiapkan impor, secret, backup, monitoring, penjelasan peserta dan analisis. Peserta menyusun dan menerima paket; staf merchant mengecek ulang ringkasan sebelum langkah pemesanan di sistem merchant sendiri. Belum ada partner atau peserta yang direkrut.

Kriteria lanjut usulan, ditetapkan bersama merchant sebelum mulai: tidak ada pelanggaran hard constraint pada paket yang diterima, minimal 90% peserta memahami batas biaya, katalog diperbarui sesuai SLA yang disepakati, minimal 80% sesi dapat menyelesaikan tugas tanpa bantuan kritis, dan merchant menyetujui langkah uji harga berikutnya. Hasil kecil bersifat formatif; tidak menyimpulkan uplift kausal. Berhenti/perbaiki jika biaya disalahpahami, data tidak dapat dipelihara, kurasi manual setara dengan usaha lebih rendah, peserta tidak menemukan manfaat, atau merchant menolak pekerjaan/pembayaran yang diperlukan. Satu insiden data atau pesanan terkirim tanpa izin menghentikan sesi.

## Monetisasi dan alternatif

Pilihan awal: biaya setup katalog + langganan tetap merchant; mudah dipahami tanpa tracking pembelian. Alternatif biaya per paket diterima memerlukan anti-duplikasi, batas volume dan definisi acceptance yang disepakati. Revenue share belum layak sampai order/margin bisa direkonsiliasi. Uji kesediaan membayar melalui pilihan harga berurutan antar merchant yang sebanding atau proposal berbayar terbatas dengan hak berhenti. Jangan memakai pertanyaan hipotetis "mau bayar berapa" sebagai validasi. Tidak ada tagihan atau layanan berbayar yang dibuat.

| Alternatif | Kekuatan | Batas yang harus diuji |
| --- | --- | --- |
| Kurasi manual staf | Fleksibel, sudah paham stok | Waktu staf, konsistensi hitung, skalabilitas |
| Paket bundling toko | Sangat sederhana, murah dioperasikan | Kebutuhan/budget bervariasi, barang sudah dimiliki |
| Filter dan keranjang toko biasa | Familiar, integrasi order sudah ada | Pengguna menjumlahkan sendiri lintas kategori |
| Spreadsheet/checklist | Transparan dan mudah dimulai | Harga/stok harus diperbarui dan dihitung manual |
| RASA | Kebutuhan wajib + batas biaya + penggantian diperiksa utuh | Perlu katalog bersih, aturan belum membuktikan preferensi nyata |

## Unit economics

`configs/pilot-economics.json` berisi asumsi ilustratif yang dapat diubah. `python scripts/pilot_economics.py` menghitung kontribusi bulanan merchant sebagai pelanggan software, break-even jumlah merchant dan sensitivitas volume. Bukan GMV, omzet produk, atau margin aktual. Biaya founder harus dihitung sebagai biaya waktu; jangan menyebut pilot gratis tanpa biaya. Data aktual untuk mengganti asumsi: jam onboarding/support, biaya hosting/logging, harga kontrak, churn, insentif, biaya akuisisi merchant, retur dan gross margin jika kelak memakai revenue share.

## Pitch 45 detik dan pertanyaan juri

RASA membantu menyusun satu paket kebutuhan awal kuliah atau kos sesuai daftar wajib dan anggaran. Pengguna dapat mengganti barang tanpa kehilangan pemeriksaan seluruh paket. Kami memulai dari satu katalog merchant dan ringkasan pemesanan manual, tanpa membangun marketplace atau pembayaran. Sistem hybrid dievaluasi pada data sintetis; alur pilot memakai aturan preferensi yang transparan untuk SKU baru. Itu membuktikan bagian rekayasa, belum membuktikan permintaan pasar. Langkah berikutnya adalah wawancara, perbandingan manual/kurasi/RASA, lalu pilot berbayar jika merchant memperoleh manfaat yang bisa diukur.

| Pertanyaan sulit | Jawaban berbasis bukti |
| --- | --- |
| Siapa yang sudah membayar? | Belum ada. Merchant calon pembayar adalah hipotesis; proposal harga adalah langkah validasi. |
| Mengapa memakai AI jika baseline cukup? | Optimasi batas paket adalah kemampuan inti. Baseline murah dan kurasi juga diuji; pilot SKU baru memakai rule baseline. Hybrid tetap demo riset sampai unggul pada data nyata yang diizinkan. |
| Mengapa tanpa collaborative justru lebih baik? | Bisa terjadi pada data sintetis, noise atau proxy objective. Lihat ablation berpasangan dan CI; hasil test tidak dipakai memilih bobot baru. |
| Apakah acceptance berarti pembelian? | Tidak. Itu aksi UI; order, revenue dan margin belum tersedia. |
| Total pasti sesuai anggaran? | Hanya jika seluruh biaya diketahui dan konfigurasi biaya benar. Jika ongkir belum diketahui, total akhir null dan pengguna diberi tahu. |
| Apakah feasible berarti optimal global? | Tidak selalu. Kandidat dipangkas dan fallback beam search bersifat heuristik; solusi dicek, jaminan optimalitas penuh tidak diklaim. |
| Apa keunggulan atas bundling merchant? | Fleksibilitas kebutuhan/budget dan penggantian utuh; manfaat relatif belum tervalidasi. |
| Berapa ukuran pasar? | Belum dihitung dengan sumber yang memadai; tidak ada angka TAM rekaan. Mulai dari kelayakan satu merchant. |
