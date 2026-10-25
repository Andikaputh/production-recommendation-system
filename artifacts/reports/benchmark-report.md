# Benchmark Report — RASA

- Dibuat: 2026-10-25T04:44:45Z
- Dataset: `rasa-synth-1.0.0` (sintetis)
- Model: `hybrid-v1`
- Seed: 42
- Holdout: 451 pengguna, 2615 event
- Definisi relevansi: Produk dengan event positif pada holdout temporal, setelah produk yang sudah pernah berinteraksi di training dikeluarkan.

## 1. Ranking (k = 10)

| Exp | Model | NDCG@10 | Recall@10 | Precision@10 | MAP@10 | MRR | HitRate@10 | NDCG 95% CI |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| EXP-001 | Global Popularity | 0.0505 | 0.0762 | 0.0290 | 0.0221 | 0.0741 | 0.2545 | [0.0414, 0.0594] |
| EXP-002 | Category Popularity | 0.0520 | 0.0790 | 0.0288 | 0.0227 | 0.0786 | 0.2545 | [0.0427, 0.0615] |
| EXP-003 | Content-Based | 0.0639 | 0.0909 | 0.0359 | 0.0299 | 0.0946 | 0.3036 | [0.0539, 0.0753] |
| EXP-004 | Collaborative Filtering | 0.0539 | 0.0761 | 0.0304 | 0.0245 | 0.0823 | 0.2634 | [0.0444, 0.0641] |
| EXP-005 | Hybrid | 0.0630 | 0.0894 | 0.0348 | 0.0288 | 0.0960 | 0.3013 | [0.0527, 0.0745] |
| EXP-006 | Hybrid + Mission Ranking | 0.0758 | 0.1127 | 0.0420 | 0.0340 | 0.1115 | 0.3661 | [0.0643, 0.0876] |
| EXP-008 | Hybrid + Controlled Exposure | 0.0701 | 0.1074 | 0.0406 | 0.0302 | 0.1010 | 0.3549 | [0.0595, 0.0807] |

## 2. Basket

| Exp | Konfigurasi | Feasibility | Required coverage | Avg merchant | Budget utilization | Basket relevance |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| EXP-002 | Baseline popularitas kategori tanpa optimasi | 0.5833 | 1.0000 | 1.6 | 0.6595 | 0.9476 |
| EXP-006 | Hybrid + misi tanpa optimasi keranjang | 0.5667 | 1.0000 | 1.54 | 0.6558 | 0.7096 |
| EXP-007 | Hybrid + optimasi keranjang (ILP) | 0.9833 | 1.0000 | 1.61 | 0.7485 | 0.6216 |
| EXP-008 | Hybrid + eksposur terkontrol + optimasi | 0.9833 | 1.0000 | 1.64 | 0.7526 | 0.6457 |

## 3. Ablation

| Varian | NDCG@10 | Recall@10 |
| --- | ---: | ---: |
| base_all_signals | 0.0796 | 0.1207 |
| no_collaborative_signal | 0.0887 | 0.1292 |
| no_content_signal | 0.0899 | 0.1292 |
| no_mission_signal | 0.0581 | 0.0902 |
| no_quality_signal | 0.0806 | 0.1202 |
| no_affinity_signal | 0.0844 | 0.1239 |
| no_exposure_adjustment | - | - |
| no_basket_constraints | - | - |

## 4. Simulasi Cold-Start

| Skenario | NDCG@10 | Recall@10 | HitRate@10 | Pengguna |
| --- | ---: | ---: | ---: | ---: |
| known_user | 0.0921 | 0.1384 | 0.4667 | 60 |
| session_2_items | 0.0971 | 0.1275 | 0.3667 | 60 |
| no_history | 0.0946 | 0.1270 | 0.4667 | 60 |

## 5. Simulasi A/B

- Status: **simulation_only**
- Lift absolut (simulasi): 0.012791727678571424
- Catatan: SIMULASI OFFLINE. Pembagian bukan randomisasi sesi live dan tidak membuktikan kausalitas.

## 6. Batasan

- Semua data bersifat sintetis; angka tidak merepresentasikan marketplace nyata.
- Metrik ranking memakai holdout temporal per pengguna.
- EXP-007 dievaluasi pada metrik basket karena tujuannya optimasi kombinasi.
- Interval kepercayaan memakai bootstrap pada level pengguna.
- Simulasi A/B bukan eksperimen online dan tidak boleh diklaim sebagai bukti kausal.
