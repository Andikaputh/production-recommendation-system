# Test Report

Date: 25 October 2026 · Python 3.11.9 · Node/Vite production build

| Gate | Result |
| --- | --- |
| Python Ruff | Passed |
| Pytest unit/integration/data | 15 passed |
| Python coverage | 51% (gate: 50%) |
| Local API benchmark | p95 369,6 ms over 10 measured requests after warm-up (target ≤ 2.500 ms) |
| Frontend oxlint | Passed |
| Frontend production build | Passed, 241 kB JS / 14,6 kB CSS before gzip |
| npm audit | 0 vulnerabilities |
| Critical data quality | 0 failures (18/18 checks passed) |

Covered critical paths: mission validation/conflicts, ranking metrics, deterministic bootstrap, parser confirmation, explanation provenance, budget/category/merchant constraints, infeasible suggestions, API schemas/errors/OpenAPI, catalog/database integration, recommendation persistence, feedback ingestion, analytics, and processed-data integrity.
