# Benchmark Report : RASA

- Generated: 2026-10-26T01:21:23Z
- Dataset: `rasa-synth-1.0.0` (synthetic)
- Model: `hybrid-v1`
- Seed: 42
- Holdout: 451 users, 2615 events
- Relevance definition: Products with positive events in the temporal holdout after excluding products already seen in training.

## 1. Ranking (k = 10)

| Exp | Model | NDCG@10 | Recall@10 | Precision@10 | MAP@10 | MRR | HitRate@10 | NDCG 95% CI |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| EXP-001 | Global Popularity | 0.0505 | 0.0762 | 0.0290 | 0.0221 | 0.0741 | 0.2545 | [0.0414, 0.0594] |
| EXP-002 | Category Popularity | 0.0520 | 0.0790 | 0.0288 | 0.0227 | 0.0786 | 0.2545 | [0.0427, 0.0615] |
| EXP-003 | Content-Based | 0.0640 | 0.0944 | 0.0371 | 0.0287 | 0.0914 | 0.3103 | [0.0547, 0.0749] |
| EXP-004 | Collaborative Filtering | 0.0539 | 0.0761 | 0.0304 | 0.0245 | 0.0823 | 0.2634 | [0.0444, 0.0641] |
| EXP-005 | Hybrid | 0.0645 | 0.0921 | 0.0350 | 0.0296 | 0.0998 | 0.2991 | [0.0534, 0.0754] |
| EXP-006 | Hybrid + Mission Ranking | 0.0709 | 0.1023 | 0.0379 | 0.0332 | 0.1077 | 0.3326 | [0.0597, 0.0831] |
| EXP-008 | Hybrid + Controlled Exposure | 0.0660 | 0.0996 | 0.0377 | 0.0293 | 0.0949 | 0.3237 | [0.0551, 0.0777] |

## 2. Basket

| Exp | Configuration | Feasibility | Required coverage | Avg merchant | Budget utilization | Basket relevance |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| EXP-002 | Category-popularity baseline without optimization | 0.5833 | 1.0000 | 1.6 | 0.6595 | 0.9476 |
| EXP-006 | Hybrid plus mission without basket optimization | 0.5417 | 1.0000 | 1.55 | 0.7068 | 0.7853 |
| EXP-007 | Hybrid + basket optimization (ILP) | 0.9917 | 1.0000 | 1.63 | 0.7707 | 0.6675 |
| EXP-008 | Hybrid + controlled exposure + optimization | 0.9917 | 1.0000 | 1.63 | 0.7647 | 0.6946 |
| SIMPLE-CHEAPEST | Cheapest eligible item per category, no joint optimization | 0.6083 | 1.0000 | 1.68 | 0.4319 | 0.4877 |
| SIMPLE-FIXED | Fixed highest-rating catalog curation per category, no test-label selection | 0.2083 | 1.0000 | 1.4 | 0.7833 | 0.5955 |

## 3. Ablation

| Variant | NDCG@10 | Recall@10 |
| --- | ---: | ---: |
| base_all_signals | 0.0739 | 0.1058 |
| no_collaborative_signal | 0.0710 | 0.1036 |
| no_content_signal | 0.0549 | 0.0823 |
| no_mission_signal | 0.0697 | 0.0962 |
| no_quality_signal | 0.0843 | 0.1194 |
| no_affinity_signal | 0.0739 | 0.1058 |
| no_exposure_adjustment | - | - |
| no_basket_constraints | - | - |

## 4. Cold-Start Simulation

| Scenario | NDCG@10 | Recall@10 | HitRate@10 | Users |
| --- | ---: | ---: | ---: | ---: |
| known_user | 0.0872 | 0.1124 | 0.4333 | 60 |
| session_2_items | 0.0979 | 0.1385 | 0.4167 | 60 |
| no_history | 0.0902 | 0.1242 | 0.4167 | 60 |

## 5. A/B Simulation

- Status: **simulation_only**
- Absolute lift (simulation): 0.006373495535714271
- Note: OFFLINE SIMULATION. Assignment is not randomized across live sessions and does not establish causality.

## 6. Limitations

- All data is synthetic; the values do not represent a real marketplace.
- Ranking metrics use a per-user temporal holdout.
- EXP-007 uses basket metrics because its objective is combination optimization.
- Confidence intervals use user-level bootstrapping.
- The A/B simulation is not an online experiment and must not be presented as causal evidence.
