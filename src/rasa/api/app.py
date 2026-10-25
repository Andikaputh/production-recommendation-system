"""FastAPI application RASA.

Fitur sesuai PRD bagian 13:
* schema request/response terdokumentasi (OpenAPI),
* validasi input dan error 4xx yang jelas,
* batas ukuran payload dan rate limit sederhana,
* timeout pada endpoint rekomendasi,
* mode degradasi ketika artifact model belum tersedia,
* tidak membocorkan stack trace ke pengguna.
"""

from __future__ import annotations

import logging
import time
import uuid
from collections import deque
from contextlib import asynccontextmanager
from contextvars import ContextVar
from typing import Any

import anyio
from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from rasa.api.deps import get_db
from rasa.api.schemas import (
    BasketOptimizeIn,
    ErrorBody,
    ErrorResponse,
    FeedbackIn,
    MissionIn,
    ParseMissionIn,
    RecommendationIn,
)
from rasa.config import settings
from rasa.db.models import Product
from rasa.db.session import healthcheck, init_db, session_scope
from rasa.missions.parser import parse_mission_text
from rasa.missions.validation import validate_mission
from rasa.services.analytics import analytics_summary, experiment_catalog
from rasa.services.catalog import catalog_service
from rasa.services.feedback import (
    FeedbackValidationError,
    session_summary,
    submit_feedback,
)
from rasa.services.missions import create_mission, mission_to_payload
from rasa.services.model_registry import ModelRegistry, registry
from rasa.utils import iso_now, json_safe, read_json

logger = logging.getLogger("rasa.api")

API_PREFIX = "/api/v1"


class RateLimiter:
    """Sliding-window in-memory rate limiter (cukup untuk demo single-process)."""

    def __init__(self, limit: int, window_seconds: float = 60.0) -> None:
        self.limit = max(1, int(limit))
        self.window = window_seconds
        self._hits: dict[str, deque[float]] = {}

    def allow(self, key: str) -> tuple[bool, int]:
        now = time.monotonic()
        bucket = self._hits.setdefault(key, deque())
        while bucket and now - bucket[0] > self.window:
            bucket.popleft()
        if len(bucket) >= self.limit:
            return False, 0
        bucket.append(now)
        return True, self.limit - len(bucket)


rate_limiter = RateLimiter(int(settings.get("api.rate_limit_per_minute", 120)))
request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)


def _client_key(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "anonymous"


def _error(status: int, code: str, message: str, details: dict[str, Any] | None = None) -> JSONResponse:
    body = ErrorResponse(
        error=ErrorBody(code=code, message=message, details=details),
        request_id=request_id_var.get(),
    )
    return JSONResponse(status_code=status, content=json_safe(body.model_dump()))


def _load_catalog() -> str:
    """Muat katalog dari database; fallback ke file processed jika DB kosong."""
    try:
        with session_scope() as session:
            count = int(session.scalar(select(func.count()).select_from(Product)) or 0)
            if count:
                catalog_service.load(session)
                return "database"
    except Exception as exc:  # pragma: no cover - bergantung lingkungan
        logger.warning("Gagal memuat katalog dari database: %s", exc)
    from rasa.data.schema import load_processed_dataset

    bundle = load_processed_dataset()
    catalog_service.load_from_bundle(bundle)
    return "file"


@asynccontextmanager
async def lifespan(app: FastAPI):
    started = time.perf_counter()
    try:
        init_db()
    except Exception as exc:  # pragma: no cover - bergantung lingkungan
        logger.warning("Inisialisasi database gagal: %s", exc)

    registry.load()
    try:
        app.state.catalog_source = _load_catalog()
    except Exception as exc:  # pragma: no cover
        app.state.catalog_source = "unavailable"
        logger.error("Katalog tidak dapat dimuat: %s", exc)

    app.state.started_at = iso_now()
    app.state.startup_ms = round((time.perf_counter() - started) * 1000.0, 1)
    logger.info(
        "RASA siap: model=%s katalog=%s (%.1f ms)",
        registry.model_version if registry.ready else "unavailable",
        app.state.catalog_source,
        app.state.startup_ms,
    )
    yield
    logger.info("RASA berhenti.")


def create_app(model_registry: ModelRegistry | None = None) -> FastAPI:
    global registry
    if model_registry is not None:
        registry = model_registry

    web_dist = settings.root_dir / "frontend" / "dist"
    application = FastAPI(
        title="RASA API",
        version=str(settings.get("project.version", "1.0.0")),
        description=(
            "Relevance-Aware Shopping Assistant — rekomendasi berbasis misi dengan "
            "optimasi keranjang. Seluruh katalog, harga, stok, dan interaksi adalah data "
            "simulasi dan tidak merepresentasikan marketplace nyata."
        ),
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        responses={500: {"model": ErrorResponse}, 429: {"model": ErrorResponse}},
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type", "X-Request-ID"],
        expose_headers=["X-Request-ID", "X-Response-Time-Ms"],
    )

    @application.middleware("http")
    async def guard(request: Request, call_next):
        request_id = request.headers.get("x-request-id") or f"req_{uuid.uuid4().hex[:12]}"
        request_id_var.set(request_id)
        request.state.request_id = request_id

        max_bytes = int(settings.get("api.max_payload_bytes", 65536))
        declared = request.headers.get("content-length")
        if declared and int(declared) > max_bytes:
            return _error(413, "payload_too_large", f"Payload melebihi batas {max_bytes} byte.")

        if request.url.path not in {"/health", "/"}:
            allowed, remaining = rate_limiter.allow(_client_key(request))
            if not allowed:
                return _error(
                    429,
                    "rate_limited",
                    "Terlalu banyak permintaan. Coba lagi beberapa saat lagi.",
                )
            request.state.rate_limit_remaining = remaining

        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            logger.exception("Unhandled error pada %s %s", request.method, request.url.path)
            response = _error(500, "internal_error", "Terjadi kesalahan internal.")
        elapsed = (time.perf_counter() - started) * 1000.0
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Response-Time-Ms"] = f"{elapsed:.1f}"
        return response

    @application.exception_handler(RequestValidationError)
    async def validation_handler(request: Request, exc: RequestValidationError):
        return _error(
            422,
            "validation_error",
            "Input tidak valid. Periksa field yang ditandai.",
            {"issues": json_safe(exc.errors())},
        )

    @application.exception_handler(HTTPException)
    async def http_handler(request: Request, exc: HTTPException):
        detail = exc.detail
        if isinstance(detail, dict):
            message = str(detail.get("message") or "Permintaan tidak dapat diproses.")
            details = detail
        else:
            message = str(detail)
            details = None
        return _error(exc.status_code, "http_error", message[:300], details)

    # ------------------------------------------------------------------
    @application.get("/", tags=["meta"])
    def index() -> Any:
        if (web_dist / "index.html").exists():
            return FileResponse(web_dist / "index.html")
        return {
            "name": "RASA — Relevance-Aware Shopping Assistant",
            "version": str(settings.get("project.version", "1.0.0")),
            "language": "id",
            "docs": "/docs",
            "health": "/health",
            "api_prefix": API_PREFIX,
            "data_mode": "synthetic",
            "notice": "Semua produk, harga, stok, merchant, dan interaksi adalah data simulasi.",
        }

    @application.get("/health", tags=["meta"])
    def health() -> dict[str, Any]:
        db_ok, db_error = healthcheck()
        if not registry.ready:
            status = "degraded"
        elif not db_ok or catalog_service.catalog.empty:
            status = "degraded"
        else:
            status = "ok"
        return {
            "status": status,
            "timestamp": iso_now(),
            "startup_ms": getattr(application.state, "startup_ms", None),
            "model": registry.status(),
            "catalog": {
                "source": getattr(application.state, "catalog_source", "unknown"),
                "loaded": catalog_service.loaded,
                "products": int(len(catalog_service.catalog)),
            },
            "database": {"ok": db_ok, "error": db_error},
            "environment": settings.environment,
        }

    @application.get(f"{API_PREFIX}/model", tags=["meta"])
    def model_status() -> dict[str, Any]:
        return {
            "model": registry.status(),
            "hybrid_config": read_json(settings.models_dir / "hybrid_config.json", {}) or {},
            "data_mode": "synthetic",
        }

    @application.get(f"{API_PREFIX}/scenarios", tags=["meta"])
    def scenarios() -> dict[str, Any]:
        payload = read_json(settings.scenarios_path, {}) or {}
        payload.setdefault("note", "Harga, stok, dan merchant adalah data simulasi.")
        return payload

    @application.get("/api/v1/benchmark", tags=["meta"])
    def benchmark() -> dict[str, Any]:
        evaluation = read_json(settings.reports_dir / "evaluation.json", {}) or {}
        return {
            "evaluation": evaluation,
            "experiments": read_json(settings.reports_dir / "experiments.json", {}) or {},
            "data_quality": read_json(settings.reports_dir / "data_quality.json", {}) or {},
            "notice": (
                "Metrik offline pada data sintetis. Bukan bukti dampak bisnis nyata dan bukan "
                "hasil eksperimen online."
            ),
        }

    # ------------------------------------------------------------------
    @application.get(f"{API_PREFIX}/catalog/categories", tags=["catalog"])
    def categories() -> dict[str, Any]:
        return {
            "items": catalog_service.categories_payload(),
            "note": "Katalog dan ketersediaan bersifat simulasi.",
        }

    @application.get(f"{API_PREFIX}/catalog/products", tags=["catalog"])
    def products(
        query: str | None = Query(default=None, max_length=120),
        category: list[str] | None = Query(default=None),
        merchant_id: str | None = Query(default=None, max_length=50),
        min_rating: float | None = Query(default=None, ge=0, le=5),
        min_price: float | None = Query(default=None, ge=0),
        max_price: float | None = Query(default=None, ge=0),
        availability: str | None = Query(default=None, pattern="^(available|unavailable|unknown)$"),
        sort_by: str = Query(default="rating", pattern="^(rating|price_asc|price_desc|newest)$"),
        limit: int = Query(default=20, ge=1, le=int(settings.get("api.pagination_max_limit", 100))),
        offset: int = Query(default=0, ge=0),
    ) -> dict[str, Any]:
        return catalog_service.search_products(
            query=query,
            category_ids=category,
            merchant_id=merchant_id,
            min_rating=min_rating,
            max_price=max_price,
            min_price=min_price,
            availability=availability,
            sort_by=sort_by,
            limit=limit,
            offset=offset,
        )

    @application.get(f"{API_PREFIX}/catalog/products/{{product_id}}", tags=["catalog"])
    def product_detail(product_id: str) -> dict[str, Any]:
        payload = catalog_service.get_product(product_id)
        if payload is None:
            raise HTTPException(status_code=404, detail=f"Produk '{product_id}' tidak ditemukan.")
        return payload

    @application.get(f"{API_PREFIX}/catalog/merchants", tags=["catalog"])
    def merchants() -> dict[str, Any]:
        return {
            "items": catalog_service.merchants_payload(),
            "note": "Merchant dan stok bersifat simulasi.",
        }

    # ------------------------------------------------------------------
    @application.post(f"{API_PREFIX}/missions/parse", tags=["missions"])
    def parse_mission(payload: ParseMissionIn) -> dict[str, Any]:
        parsed = parse_mission_text(payload.text)
        parsed["category_suggestions"] = catalog_service.categories_payload()
        return parsed

    @application.post(f"{API_PREFIX}/missions", tags=["missions"])
    def create_mission_endpoint(
        payload: MissionIn,
        session_id: str = Query(default="api-session", min_length=3, max_length=80),
        db: Session = Depends(get_db),
    ) -> dict[str, Any]:
        mission = payload.to_domain()
        result = validate_mission(mission, catalog_service.catalog, catalog_service.categories)
        if not result.valid or result.normalized is None:
            return _error(
                422,
                "invalid_mission",
                "Misi tidak valid.",
                {"errors": [issue.__dict__ for issue in result.errors]},
            )
        record = create_mission(
            db,
            result.normalized,
            session_id=session_id,
            warnings=[issue.__dict__ for issue in result.warnings],
        )
        return {
            "mission": mission_to_payload(db, record.mission_id),
            "validation": result.to_dict(),
        }

    @application.get(f"{API_PREFIX}/missions/{{mission_id}}", tags=["missions"])
    def mission_detail(mission_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
        payload = mission_to_payload(db, mission_id)
        if payload is None:
            raise HTTPException(status_code=404, detail=f"Misi '{mission_id}' tidak ditemukan.")
        return payload

    # ------------------------------------------------------------------
    def _recommend_sync(payload: RecommendationIn) -> dict[str, Any]:
        from rasa.services.recommendation import RecommendationService

        if not registry.ready:
            raise HTTPException(
                status_code=503,
                detail="Model belum siap. Jalankan `python scripts/train.py` lalu coba lagi.",
            )
        mission = payload.mission.to_domain(payload.preferences)
        validation = validate_mission(
            mission, catalog_service.catalog, catalog_service.categories
        )
        if not validation.valid or validation.normalized is None:
            raise HTTPException(
                status_code=422,
                detail={
                    "message": "Misi tidak valid.",
                    "errors": [issue.__dict__ for issue in validation.errors],
                },
            )
        service = RecommendationService(registry.ranker, registry.model_version)
        with session_scope() as db:
            response = service.recommend(
                db,
                mission=validation.normalized,
                session_id=payload.context.session_id,
                strategy=payload.context.strategy,
                user_id=payload.context.user_id,
                top_k=payload.context.top_k,
                include_comparison=payload.context.include_comparison,
                experiment_id=payload.context.experiment_id,
                search_text=payload.context.search_text,
            )
        response["validation"] = validation.to_dict()
        return response

    @application.post(f"{API_PREFIX}/recommendations", tags=["recommendations"])
    async def recommendations(payload: RecommendationIn) -> dict[str, Any]:
        timeout = float(settings.get("api.recommendation_timeout_seconds", 2.5))
        started = time.perf_counter()
        try:
            with anyio.fail_after(timeout):
                result = await anyio.to_thread.run_sync(
                    _recommend_sync, payload, abandon_on_cancel=True
                )
        except TimeoutError:
            return _error(
                504,
                "recommendation_timeout",
                f"Rekomendasi melebihi batas waktu {timeout:.1f} detik. Coba sederhanakan misi.",
            )
        result.setdefault("meta", {})["server_latency_ms"] = round(
            (time.perf_counter() - started) * 1000.0, 2
        )
        return result

    @application.post(f"{API_PREFIX}/baskets/optimize", tags=["recommendations"])
    async def optimize_basket_endpoint(payload: BasketOptimizeIn) -> dict[str, Any]:
        recommendation_payload = RecommendationIn(
            mission=payload.mission,
            preferences=payload.preferences,
            context=payload.context.model_copy(update={"include_comparison": True}),
        )
        timeout = float(settings.get("api.recommendation_timeout_seconds", 2.5))
        try:
            with anyio.fail_after(timeout):
                result = await anyio.to_thread.run_sync(
                    _recommend_sync, recommendation_payload, abandon_on_cancel=True
                )
        except TimeoutError:
            return _error(504, "optimization_timeout", "Optimasi keranjang melebihi batas waktu.")
        return {
            "basket": result["basket"],
            "comparison": result.get("comparison"),
            "explanations": result.get("explanations", []),
            "alternatives": result.get("alternatives", {}),
            "mission": result.get("mission"),
            "status": result.get("status"),
            "request_id": result.get("request_id"),
            "limitations": result.get("limitations", []),
        }

    # ------------------------------------------------------------------
    @application.post(f"{API_PREFIX}/feedback", tags=["feedback"])
    def feedback(payload: FeedbackIn, db: Session = Depends(get_db)) -> dict[str, Any]:
        try:
            return submit_feedback(
                db,
                session_id=payload.session_id,
                product_id=payload.product_id,
                event_type=payload.event_type,
                user_id=payload.user_id,
                experiment_variant=payload.experiment_variant,
                metadata=payload.metadata,
            )
        except FeedbackValidationError as exc:
            return _error(422, "invalid_feedback", str(exc))

    @application.get(f"{API_PREFIX}/feedback/session/{{session_id}}", tags=["feedback"])
    def feedback_session(
        session_id: str,
        limit: int = Query(default=50, ge=1, le=200),
        db: Session = Depends(get_db),
    ) -> dict[str, Any]:
        return session_summary(db, session_id, limit=limit)

    @application.get(f"{API_PREFIX}/experiments", tags=["analytics"])
    def experiments(db: Session = Depends(get_db)) -> dict[str, Any]:
        return experiment_catalog(db)

    @application.get(f"{API_PREFIX}/analytics/summary", tags=["analytics"])
    def analytics(
        days: int = Query(default=30, ge=1, le=365),
        model_version: str | None = Query(default=None, max_length=80),
        strategy: str | None = Query(default=None, max_length=60),
        db: Session = Depends(get_db),
    ) -> dict[str, Any]:
        return analytics_summary(
            db, days=days, model_version=model_version, strategy=strategy
        )

    # Pada image deployment, hasil build React disajikan oleh proses yang sama.
    # Semua route API didaftarkan lebih dulu sehingga mount ini hanya menangani
    # aset frontend dan fallback dokumen statis.
    if web_dist.exists():
        application.mount("/", StaticFiles(directory=web_dist, html=True), name="web")

    return application


app = create_app()
