FROM node:22-alpine AS frontend-build
WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.11-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    RASA_ENV=production \
    PORT=8000
WORKDIR /app

RUN addgroup --system rasa && adduser --system --ingroup rasa rasa
COPY pyproject.toml README.md ./
COPY src/ src/
COPY apps/ apps/
COPY configs/ configs/
COPY scripts/ scripts/
COPY data/raw/ data/raw/
COPY data/processed/ data/processed/
COPY artifacts/ artifacts/
COPY --from=frontend-build /build/frontend/dist frontend/dist

RUN pip install . && python scripts/seed_db.py --no-events && chown -R rasa:rasa /app
USER rasa
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3)"
CMD ["sh", "-c", "uvicorn apps.api.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]
