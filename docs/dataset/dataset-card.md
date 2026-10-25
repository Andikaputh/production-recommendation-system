# Dataset Card — rasa-synth-1.0.0

Dataset ini sepenuhnya sintetis dan dibuat oleh `scripts/generate_data.py` dengan seed 42. Isinya 10 kategori, 30 merchant, 600 produk, 500 profil pseudonymous, dan 52.174 event selama jendela simulasi 120 hari.

## Intended use

Pengembangan, reproducibility, offline evaluation, API demo, dan portfolio review. Bukan untuk melatih sistem komersial, mengestimasi demand, menilai merchant nyata, atau menyimpulkan perilaku manusia.

## Splitting and leakage

Interaksi diurutkan berdasarkan waktu per pengguna. Training, validation, dan test terpisah; validation memilih bobot, sedangkan test hanya melaporkan hasil. Quality checks memeriksa referential integrity, enum, missing value, duplicate, timestamp, temporal leakage, dan event isolation.

## License and limitations

Data sintetis dirilis CC BY 4.0. Nama produk/merchant bersifat fiktif. Bias simulasi berasal dari aturan generator; distribusi exposure, rating, kategori, dan preferensi tidak merepresentasikan marketplace nyata. Manifest checksum tersedia di `data/raw/dataset_manifest.json`.
