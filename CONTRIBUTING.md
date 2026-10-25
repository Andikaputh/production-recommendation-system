# Contributing

Gunakan Python 3.11+ dan Node.js 22+. Buat branch kecil (`feat/*`, `fix/*`, `docs/*`), lalu gunakan Conventional Commits.

Sebelum membuka pull request:

```bash
ruff check .
pytest --cov=rasa --cov-fail-under=50
cd frontend && npm audit && npm run lint && npm run build
```

Perubahan model harus mencatat seed, versi dataset, konfigurasi, dan metrik pembanding. Jangan commit secret, database runtime, data pribadi, atau klaim dampak bisnis yang tidak didukung eksperimen.
