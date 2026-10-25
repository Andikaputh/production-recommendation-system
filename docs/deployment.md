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

`render.yaml` menyediakan konfigurasi one-click untuk Docker Web Service di region Singapore dengan health check dan auto-deploy dari branch `main`. Pada plan gratis, filesystem bersifat ephemeral: katalog akan kembali ke seed image setelah restart dan event feedback demo tidak dijamin persisten. Gunakan paid persistent disk atau PostgreSQL untuk retensi jangka panjang.
