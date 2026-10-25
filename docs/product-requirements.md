# RASA Product Requirements & Traceability

Implementation version: 1.0.0 · Product language: English · Data: synthetic · Status: MVP implemented

## Objective

RASA helps users complete shopping missions with relevant product combinations while respecting budget, availability, required categories, minimum rating, and merchant-count constraints. The system separates preference ranking from feasibility checks and never changes hard constraints silently.

## Scope MVP

Primary flow: select or write a mission → confirm categories and preferences → generate candidates → apply hybrid ranking → optimize the basket → show cost, coverage, explanations, and alternatives → submit anonymous feedback → view aggregated metrics.

Out of scope: permanent accounts, checkout, payments, real marketplace data, real-time prices or inventory, dynamic pricing, sponsored ranking, and causal impact claims.

## Functional requirements

| ID | Requirement | Status | Implementation / evidence |
| --- | --- | --- | --- |
| FR-001 | Mission builder | Complete | React builder + `POST /missions` |
| FR-002 | Budget constraint | Complete | Pydantic, domain validation, optimizer hard constraint |
| FR-003 | Preference input | Complete | rating, style, color, brand, max item price schema |
| FR-004 | Catalog retrieval | Complete | category/attribute/search candidate service |
| FR-005 | Popularity baseline | Complete | EXP-001/002 and evaluation report |
| FR-006 | Content model | Complete | TF-IDF artifact + EXP-003 |
| FR-007 | Collaborative filtering | Complete | item similarity artifact + EXP-004 |
| FR-008 | Hybrid ranking | Complete | versioned weights + EXP-005/006 |
| FR-009 | Basket optimizer | Complete | ILP CBC + checked greedy fallback |
| FR-010 | Cold start | Complete | mission/content/category popularity fallback |
| FR-011 | Explanation | Complete | reason codes derived from used features/rules |
| FR-012 | Feedback events | Complete | anonymous append-oriented event endpoint |
| FR-013 | Alternative products | Complete | top alternatives per mission category |
| FR-014 | Analytics dashboard | Complete | UI insight view + aggregate endpoint filters |
| FR-015 | Experiment comparison | Complete | configs + experiment and benchmark reports |
| FR-016 | A/B simulation | Complete | deterministic assignment, explicitly non-causal |
| FR-017 | Admin catalog import | Partial/Should | validated CSV pipeline; no admin UI in MVP |
| FR-018 | User account | Not implemented | Explicit non-goal MVP |
| FR-019 | Checkout | Not implemented | Explicit non-goal MVP |
| FR-020 | Natural language parsing | Complete/Could | deterministic parser + mandatory review |

## Non-functional requirements

- Performance: 2.5-second API timeout; 88.41 ms offline solver p95. Runtime latency is measured per deployment.
- Reliability: artifact, database, and catalog health checks are available; the frontend static fallback is clearly labeled.
- Reproducibility: seed, dataset and model versions, checksums, configuration, splits, and results are stored.
- Security/privacy: payload limit, validation, safe errors, CORS, demo rate limit, anonymous session, no PII fields.
- Accessibility: semantic controls, keyboard focus, contrast, responsive states, reduced-motion support.
- Portability: local Python and Node workflow plus one-command Docker Compose.

## Acceptance summary

All acceptance criteria that can be demonstrated in the repository are complete: product flow, model families, temporal metrics, basket metrics, ablation, schema and OpenAPI, relational storage, tests, CI, Docker, static fallback, visible simulation notices, dependency and data licensing notes, and explicit limitations. Public deployment and video recording are release activities supported by the deployment guide and walkthrough script.
