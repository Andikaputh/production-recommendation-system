# System Architecture

## Runtime flow

```text
Browser → FastAPI schemas → Mission validation → Candidate retrieval
       → Hybrid ranker → ILP/beam basket optimizer → Explanations
       → Persist request/basket/items → Anonymous feedback → Aggregate analytics
```

## Offline flow

```text
Synthetic generator → schema/data checks → temporal train/validation/test
→ content + collaborative + popularity artifacts → validation tuning
→ frozen hybrid config → test evaluation/ablation → versioned reports
```

FastAPI serves the built React application in production. SQLite is the default portable database; models are SQLAlchemy-compatible with PostgreSQL. A single worker is used for the in-memory demo rate limiter. Multi-instance production would require PostgreSQL, migrations, a distributed rate limiter/cache, centralized logs, and managed metrics.

The full relational schema is defined in `src/rasa/db/models.py`: categories, merchants, products, attributes, anonymous sessions, preferences, missions/categories, interaction events, recommendation requests/items, basket solutions/items, experiments/assignments, and model versions.
