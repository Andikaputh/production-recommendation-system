# Contributing

Use Python 3.11+ and Node.js 22+. Keep branches focused (`feat/*`, `fix/*`, `docs/*`) and use Conventional Commits.

Before opening a pull request:

```bash
ruff check .
pytest --cov=rasa --cov-fail-under=50
cd frontend && npm audit && npm run lint && npm run build
```

Model changes must record the seed, dataset version, configuration, and comparison metrics. Never commit secrets, runtime databases, personal data, or business-impact claims unsupported by experiments.
