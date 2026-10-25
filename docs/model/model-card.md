# Model Card — hybrid-v1

## System

RASA is a staged decision system, not one monolithic model. Candidate retrieval filters mission categories and feasibility attributes. Ranking combines collaborative, content, mission, quality, and affinity components. The selected validation weights are 0,20 / 0,20 / 0,30 / 0,20 / 0,10. Basket selection uses integer linear programming with a checked beam-search fallback.

## Evaluation

Primary test metrics for EXP-006: NDCG@10 0,0758; Recall@10 0,1127; Hit Rate@10 0,3661. EXP-007 evaluates 120 simulated missions: 98,33% budget feasibility, 100% required coverage among feasible outcomes, and 100% hard-constraint validity. Full confidence intervals, baselines, ablation, cold-start, diversity, and exposure results are in the benchmark report.

## Intended use and limitations

Intended for a public portfolio demo on synthetic Indonesian commerce data. Not intended for real purchasing decisions, calibrated purchase probability, ads, credit, pricing, or merchant adjudication. Quality can degrade for missing metadata, unseen language, constraint combinations outside generated data, and domains unlike the simulation.

## Explainability and fairness

Reason codes only reflect features/rules used in ranking and optimization. Controlled exposure is bounded and guarded by quality/relevance, but synthetic evaluation cannot establish real-world fairness. Monitor popularity dominance, new-item exposure, and merchant concentration before any real deployment.
