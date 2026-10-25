# Problem Validation Notes

## Hipotesis, bukan fakta pasar

Proyek menguji empat hipotesis: mission-aware ranking lebih relevan daripada popularity-only; constraint-aware construction lebih feasible daripada independent top-1; gabungan ranking dan basket metrics lebih informatif daripada satu metrik klik; controlled exposure dapat membantu low-history items dengan relevance guardrail.

Benchmark sintetis mendukung dua hipotesis teknis: EXP-006 memiliki NDCG@10 lebih tinggi dari category popularity, dan EXP-007 menaikkan budget feasibility dari 56,67% menjadi 98,33% dibanding ranking tanpa basket optimization. Hasil ini tidak memvalidasi demand pengguna atau dampak bisnis nyata.

## Riset yang masih diperlukan

Sebelum klaim produk, lakukan 5–8 problem interviews per persona, usability test pada mission builder, dan prior-art review produk/publikasi/paten. Ukur waktu penyelesaian tugas, kemampuan memahami trade-off, frekuensi misi infeasible, dan apakah explanation membantu keputusan. Jangan mengumpulkan PII; gunakan skenario dan katalog uji.
