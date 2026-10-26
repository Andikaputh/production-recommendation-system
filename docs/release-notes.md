# Release Notes

## v1.0.0 : RASA MVP

- Replaced the legacy movie recommender with mission-aware commerce recommendation.
- Added reproducible synthetic dataset, temporal splits, content/collaborative/popularity models, validation-tuned hybrid ranking, cold-start handling, and controlled exposure.
- Added hard-constraint basket optimization, actionable infeasibility, explanations, alternatives, anonymous feedback, experiment catalog, and analytics.
- Added a responsive English React demo with clearly labelled live and static sources.
- Added FastAPI schemas, relational persistence, safe errors, request IDs, payload/rate/timeout controls, tests, CI, Docker, cards, benchmark, and deployment documentation.


## Persiapan pilot, 26 Oktober 2026

Builder utama Bahasa Indonesia untuk awal kuliah/kos; satu merchant; impor CSV atomik, TTL dan checksum; biaya barang/ongkir terpisah; penggantian dan pemeriksaan ulang seluruh paket; penerimaan serta ringkasan lokal tanpa pengiriman. Funnel tersimpan per sesi/misi/revisi, source demo/test/pilot terpisah, akses admin dibatasi. Evaluasi beku memiliki provenance, baseline murah/kurasi dan paired ablation. Pruning, fallback, metrik inventory dan keselarasan validation/inference diperbaiki. Lihat docs/reports/pilot-verification.md untuk bukti dan batas verifikasi. Model bisnis dan manfaat pengguna belum tervalidasi.


## English-first bilingual builder

The primary kit builder now defaults to English, with a persistent English / Bahasa Indonesia selector. Preset goals, controls, currency, basket status, explanations, suggestions and local summary labels follow the selected language. Custom goals, merchant product names and basket state are preserved when switching. The technical demo remains English. README, the generated metric summaries and the pilot runbook now provide English entry points; local Indonesian research materials remain available.
