# API Guide

Interactive OpenAPI is available at `/docs`; ReDoc is at `/redoc`. All business endpoints use `/api/v1`. Validation errors return a stable `error.code`, user-safe message, optional details, and request ID. Responses include `X-Request-ID` and `X-Response-Time-Ms`.

Recommendation requests accept a mission, preferences, and context. `include_comparison=true` additionally runs alternative basket optimization and may cost more latency. The primary response includes model/strategy version, basket feasibility, item-level recommendations, explanations, alternatives, limitations, and diagnostics.

The API limits payload size, pagination, budget, merchant count, top-k, and event types. `/analytics/summary` is aggregate-only. The in-memory rate limiter is suitable only for the single-process demo.
