# Problem Validation Notes

## Hypotheses, not market facts

The project tests four hypotheses: mission-aware ranking is more relevant than popularity-only ranking; constraint-aware construction is more feasible than independent top-1 selection; combined ranking and basket metrics are more informative than a single click metric; and controlled exposure can support low-history items with a relevance guardrail.

The synthetic benchmark supports two technical hypotheses: EXP-006 has higher NDCG@10 than category popularity, and EXP-007 raises budget feasibility from 56.67% to 98.33% compared with ranking without basket optimization. These results do not validate real user demand or business impact.

## Further research required

Before making product claims, conduct five to eight problem interviews per persona, usability testing on the mission builder, and a prior-art review of products, publications, and patents. Measure task completion time, trade-off comprehension, infeasible-mission frequency, and whether explanations improve decisions. Do not collect personal data; use test scenarios and catalogs.
