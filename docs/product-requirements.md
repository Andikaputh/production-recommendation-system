# RASA Product Requirements & Traceability

Versi implementasi: 1.0.0 · Bahasa produk: Indonesia · Data: sintetis · Status: MVP implemented

## Tujuan

RASA membantu pengguna menyelesaikan misi belanja dengan kombinasi produk yang relevan sekaligus mematuhi anggaran, ketersediaan, kategori wajib, rating minimum, dan batas jumlah toko. Sistem memisahkan ranking preferensi dari pemeriksaan feasibility dan tidak mengganti batasan keras secara diam-diam.

## Scope MVP

Alur utama: pilih/tulis misi → konfirmasi kategori dan preferensi → generate kandidat → hybrid ranking → optimasi keranjang → tampilkan biaya, coverage, explanation, alternative products → kirim feedback anonim → lihat metrik agregat.

Out of scope: akun permanen, checkout, pembayaran, data marketplace nyata, harga/stok real-time, dynamic pricing, sponsored ranking, dan klaim dampak kausal.

## Functional requirements

| ID | Requirement | Status | Implementasi / bukti |
| --- | --- | --- | --- |
| FR-001 | Mission builder | Selesai | React builder + `POST /missions` |
| FR-002 | Budget constraint | Selesai | Pydantic, domain validation, optimizer hard constraint |
| FR-003 | Preference input | Selesai | rating, style, color, brand, max item price schema |
| FR-004 | Catalog retrieval | Selesai | category/attribute/search candidate service |
| FR-005 | Popularity baseline | Selesai | EXP-001/002 dan evaluation report |
| FR-006 | Content model | Selesai | TF-IDF artifact + EXP-003 |
| FR-007 | Collaborative filtering | Selesai | item similarity artifact + EXP-004 |
| FR-008 | Hybrid ranking | Selesai | versioned weights + EXP-005/006 |
| FR-009 | Basket optimizer | Selesai | ILP CBC + checked greedy fallback |
| FR-010 | Cold start | Selesai | mission/content/category popularity fallback |
| FR-011 | Explanation | Selesai | reason codes derived from used features/rules |
| FR-012 | Feedback events | Selesai | anonymous append-oriented event endpoint |
| FR-013 | Alternative products | Selesai | top alternatives per mission category |
| FR-014 | Analytics dashboard | Selesai | UI insight view + aggregate endpoint filters |
| FR-015 | Experiment comparison | Selesai | configs + experiment and benchmark reports |
| FR-016 | A/B simulation | Selesai | deterministic assignment, explicitly non-causal |
| FR-017 | Admin catalog import | Parsial/Should | validated CSV pipeline; no admin UI in MVP |
| FR-018 | User account | Tidak dikerjakan | Explicit non-goal MVP |
| FR-019 | Checkout | Tidak dikerjakan | Explicit non-goal MVP |
| FR-020 | Natural language parsing | Selesai/Could | deterministic parser + mandatory review |

## Non-functional requirements

- Performance: API timeout 2,5 s; offline p95 solver 88,41 ms. Runtime latency tetap diukur per deployment.
- Reliability: artifact, DB, dan catalog health tersedia; frontend static fallback diberi label.
- Reproducibility: seed, dataset/model version, checksums, configuration, splits, dan results disimpan.
- Security/privacy: payload limit, validation, safe errors, CORS, demo rate limit, anonymous session, no PII fields.
- Accessibility: semantic controls, keyboard focus, contrast, responsive states, reduced-motion support.
- Portability: local Python/Node workflow dan one-command Docker Compose.

## Acceptance summary

Semua acceptance criteria yang dapat dibuktikan di repository telah ditutup: product flow, model families, temporal metrics, basket metrics, ablation, schema/OpenAPI, relational storage, tests, CI, Docker, static fallback, visible simulation notice, dependency/data license notes, and explicit limitations. Public URL dan video recording adalah release/distribution activities di luar source repository; tersedia deployment guide dan walkthrough script.
