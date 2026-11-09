"""Prometheus metrics endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Response

from app.core.metrics import metrics_payload

router = APIRouter(tags=["metrics"])


@router.get("/metrics")
async def metrics() -> Response:
    return Response(content=metrics_payload(), media_type="text/plain; version=0.0.4")
