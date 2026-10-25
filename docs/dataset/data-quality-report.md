# Data Quality Report

- Dataset: `rasa-synth-1.0.0`
- Generated: 2026-10-25T13:06:15Z
- Total pemeriksaan: 18
- Lulus: 18
- Warnings: 0
- Critical failures: 0

| Pemeriksaan | Status | Severity | Detail |
| --- | --- | --- | --- |
| `primary_key_duplicates:products` | pass | critical | duplicates=0, rows=600 |
| `primary_key_duplicates:merchants` | pass | critical | duplicates=0, rows=30 |
| `primary_key_duplicates:categories` | pass | critical | duplicates=0, rows=10 |
| `primary_key_duplicates:users` | pass | critical | duplicates=0, rows=500 |
| `primary_key_duplicates:interactions` | pass | critical | duplicates=0, rows=52174 |
| `price_validity` | pass | critical | non_positive=0, above_10m=0, min=4000, max=636000 |
| `required_missing_values` | pass | critical | missing_counts={'product_id': 0, 'product_name': 0, 'category_id': 0, 'price': 0, 'merchant_id': 0, 'availability_status': 0} |
| `unknown_categories` | pass | critical | unknown=[], known=['bag', 'book', 'desk', 'drinkware', 'electronics', 'organizer', 'personal_care', 'snack', 'stationery', 'umbrella'] |
| `referential_integrity:product_merchant` | pass | critical | unknown_merchant_ids=[] |
| `referential_integrity:interaction_product` | pass | critical | orphan_events=0 |
| `timestamp_validity` | pass | critical | null_timestamps=0, future_events=0, min=2026-04-03 07:07:13, max=2026-07-31 22:54:59 |
| `duplicate_interactions` | pass | warning | duplicates=0 |
| `user_item_distribution` | pass | warning | n_users_with_positives=500, n_items_with_positives=600, interactions_per_user={'min': 1, 'median': 28.0, 'max': 41}, interactions_per_item={'min': 2, 'median': 22.0, 'max': 45}, matrix_sparsity=0.9562 |
| `temporal_leakage` | pass | critical | users_with_leakage=0, n_test_users=451 |
| `train_test_isolation` | pass | critical | overlapping_event_ids=0, train_rows=8985, test_rows=2615 |
| `enum_validity` | pass | critical | invalid_availability=[], invalid_event_types=[] |
| `available_products_per_category` | pass | critical | missing_available_categories=[], min_available_per_category=49 |
| `schema_manifest_consistency` | pass | warning | manifest_n_products=600, actual_n_products=600, dataset_version=rasa-synth-1.0.0 |

## Limitations

- The dataset is entirely synthetic and does not represent a real marketplace.
- Prices and inventory are not real-time.
- Relevance labels come from simulated interactions, not real user preferences.
