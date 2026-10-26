# Deployment Guide

## Local production image

```bash
docker build -t rasa-recommender .
docker run --rm -p 8000:8000 rasa-recommender
```

The multi-stage image builds React, installs only runtime Python dependencies, seeds a portable SQLite catalog, runs as a non-root user, and exposes `/health`.

## Cloud container

Deploy the Dockerfile to a container platform, set `PORT`, and optionally provide `RASA_DATABASE_URL` (PostgreSQL recommended for durable/multi-instance use) plus `RASA_CORS_ORIGINS`. Attach persistent storage when using SQLite. Do not train during startup. Keep one worker while using the current in-memory limiter.

After deployment, verify `/health`, `/docs`, a feasible scenario, the intentionally infeasible scenario, feedback ingestion, analytics aggregation, and frontend fallback by temporarily blocking the API. Free-tier cold starts and quotas are not an SLA.

## Render Blueprint

`render.yaml` provides one-click configuration for a Docker Web Service in the Singapore region, including health checks and automatic deployment from `main`. On the free plan, the filesystem is ephemeral: the catalog returns to its image seed after a restart and demo feedback events are not guaranteed to persist. Use a paid persistent disk or PostgreSQL for long-term retention.


## Pilot satu merchant

Gunakan `docs/pilot/README.md` untuk database persisten terpisah, token admin, katalog bertimestamp dan biaya pilot. Hosting tanpa persistent disk hanya untuk demo. `/readyz` mengembalikan 503 bila katalog pilot belum diimpor atau kedaluwarsa; gunakan sebagai readiness gate, `/health` tetap diagnostik. Aplikasi tidak mengirim ringkasan ke pihak luar. Deploy publik tidak dilakukan dalam pengembangan ini.
