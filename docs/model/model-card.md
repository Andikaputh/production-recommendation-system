# Model Card: hybrid-v1

## System

RASA is a staged decision system, not one monolithic model. Candidate retrieval filters mission categories and feasibility attributes. Ranking combines collaborative, content, mission, quality, and affinity components. The validation-selected weights are 0.1667 collaborative, 0.3333 content, 0.1667 mission, 0.3333 quality, and 0 affinity. Basket selection uses integer linear programming with a checked beam-search fallback.

## Evaluation

Primary test metrics for EXP-006 are NDCG@10 0.0709, Recall@10 0.1023, and Hit Rate@10 0.3326. EXP-007 evaluates 120 simulated missions with 97.50% budget feasibility, 100% required coverage among feasible outcomes, and 100% hard-constraint validity. Full confidence intervals, baselines, ablation, cold-start, diversity, and exposure results are in the benchmark report.

## Intended use and limitations

Intended for a public portfolio demo on synthetic retail data denominated in IDR. Not intended for real purchasing decisions, calibrated purchase probability, ads, credit, pricing, or merchant adjudication. Quality can degrade for missing metadata, unseen language, constraint combinations outside generated data, and domains unlike the simulation.

## Explainability and fairness

Reason codes only reflect features/rules used in ranking and optimization. Controlled exposure is bounded and guarded by quality/relevance, but synthetic evaluation cannot establish real-world fairness. Monitor popularity dominance, new-item exposure, and merchant concentration before any real deployment.
