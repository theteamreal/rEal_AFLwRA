"""
FastAPI Endpoints — Phase 2 + 3 + 6
--------------------------------------
All /api/* routes live here. Endpoints are async def everywhere.
No blocking calls — the aggregation worker does the slow work.
"""

import time
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from fedguard.config import STALENESS_WINDOW
from main.api import model_store, aggregator
from main.api.detector import is_outlier

logger = logging.getLogger("fedguard.endpoints")
router = APIRouter()

_server_start = time.time()


# ── Pydantic Models ───────────────────────────────────────────────────────────

class WeightUpdate(BaseModel):
    client_id: str
    round_id: int
    weights: dict          # { "W": [[...], ...], "b": [...] }
    n_samples: int = 1
    local_loss: Optional[float] = None


# ── GET /api/health ───────────────────────────────────────────────────────────

@router.get("/health")
async def health():
    """Liveness check. Returns 200 + basic uptime info."""
    return {
        "status": "ok",
        "uptime_seconds": round(time.time() - _server_start, 1),
        "current_round": model_store.get_round_id(),
    }


# ── GET /api/get-model ────────────────────────────────────────────────────────

@router.get("/get-model")
async def get_model(request: Request):
    """
    Returns current global model weights as JSON.
    Includes ETag based on round_id so clients can skip download if unchanged.
    """
    round_id, weights = await model_store.get_weights()
    etag = f'"{round_id}"'

    # Honour If-None-Match for efficient polling
    if request.headers.get("if-none-match") == etag:
        return JSONResponse(content=None, status_code=304)

    response_data = {
        "round_id": round_id,
        "model_config": model_store.get_model_config(),
        "weights": weights,
    }
    return JSONResponse(
        content=response_data,
        headers={"ETag": etag, "Cache-Control": "no-store"},
    )


# ── POST /api/submit-update ───────────────────────────────────────────────────

@router.post("/submit-update", status_code=202)
async def submit_update(update: WeightUpdate):
    """
    Accepts a weight update from a client after local training.
    Returns 202 instantly — never makes the client wait for aggregation.

    Rejects:
      - Stale updates (round too old) → 409
      - Updates with malformed weights → 422

    Flags (but still accepts):
      - Outlier updates detected by the two-check detector
    """
    current_round = model_store.get_round_id()

    # ── Staleness check ───────────────────────────────────────────────────────
    if update.round_id < current_round - STALENESS_WINDOW:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "stale_update",
                "message": f"Update is from round {update.round_id}, "
                           f"current is {current_round}. "
                           f"Staleness window is {STALENESS_WINDOW}.",
                "current_round": current_round,
            }
        )

    update_dict = {
        "client_id": update.client_id,
        "round_id": update.round_id,
        "weights": update.weights,
        "n_samples": update.n_samples,
        "local_loss": update.local_loss,
        "_flagged": False,
        "_flag_reason": "",
    }

    # ── Pre-queue outlier check (fast, synchronous) ───────────────────────────
    # We run a single-update check here for immediate feedback.
    # The aggregator runs a batch check again before aggregating.
    _, current_weights = await model_store.get_weights()
    flagged, reason = is_outlier(update_dict, [update_dict])
    if flagged:
        update_dict['_flagged'] = True
        update_dict['_flag_reason'] = reason
        logger.warning(
            f"⚠️  Pre-flagged update from {update.client_id}: {reason}"
        )

    # ── Enqueue — returns instantly ───────────────────────────────────────────
    await aggregator.update_queue.put(update_dict)

    status = "flagged" if flagged else "queued"
    return JSONResponse(
        status_code=202,
        content={
            "status": status,
            "message": "Update accepted. Aggregation will happen in background.",
            "current_round": current_round,
            "queue_depth": aggregator.update_queue.qsize(),
        }
    )


# ── GET /api/status ───────────────────────────────────────────────────────────

@router.get("/status")
async def status():
    """
    Polled by clients every 5 seconds.
    Returns current round, queue depth, and last aggregation timestamp.
    """
    stats = aggregator.get_stats()
    return {
        "current_round": model_store.get_round_id(),
        "queue_depth": stats["queue_depth"],
        "last_aggregation": stats["last_aggregation"],
        "total_rounds_aggregated": stats["total_rounds_aggregated"],
        "total_updates_received": stats["total_updates_received"],
        "total_flagged": stats["total_flagged"],
    }


# ── GET /api/metrics ─────────────────────────────────────────────────────────

@router.get("/metrics")
async def metrics():
    """
    Historical round data for dashboard charts.
    Returns last 50 rounds from Django DB.
    """
    try:
        from asgiref.sync import sync_to_async

        @sync_to_async
        def _query():
            from main.models import RoundHistory, ClientRecord
            rounds = list(
                RoundHistory.objects.order_by('-timestamp')[:50].values(
                    'round_id', 'timestamp', 'n_updates', 'n_flagged', 'global_loss'
                )
            )
            clients = list(
                ClientRecord.objects.order_by('-last_seen')[:20].values(
                    'client_id', 'last_seen', 'total_updates', 'flagged_count', 'flag_reason'
                )
            )
            # Convert datetimes to ISO strings for JSON serialisation
            for r in rounds:
                r['timestamp'] = r['timestamp'].isoformat() if r['timestamp'] else None
            for c in clients:
                c['last_seen'] = c['last_seen'].isoformat() if c['last_seen'] else None
            return {"rounds": rounds, "clients": clients}

        data = await _query()
        return data
    except Exception as e:
        logger.error(f"Metrics query failed: {e}")
        return {"rounds": [], "clients": [], "error": str(e)}


# ── GET /api/datasets ─────────────────────────────────────────────────────────

@router.get("/datasets")
async def list_datasets(q: str = "", tag: str = ""):
    """
    Returns JSON list of public datasets for live search.
    Optional query params: q (search name/description/tags), tag (filter by tag).
    """
    try:
        from asgiref.sync import sync_to_async

        @sync_to_async
        def _query():
            from main.models import Dataset
            qs = Dataset.objects.filter(is_public=True)
            if q:
                from django.db.models import Q
                qs = qs.filter(
                    Q(name__icontains=q) |
                    Q(description__icontains=q) |
                    Q(tags__icontains=q)
                )
            if tag:
                qs = qs.filter(tags__icontains=tag)
            return list(qs.values(
                'name', 'slug', 'description', 'tags',
                'created_by', 'created_at', 'row_count',
                'feature_count', 'num_classes', 'download_count'
            )[:50])

        datasets = await _query()
        # Convert datetimes
        for d in datasets:
            d['created_at'] = d['created_at'].isoformat() if d['created_at'] else None
        return JSONResponse(content={"datasets": datasets})
    except Exception as e:
        logger.error(f"Dataset list failed: {e}")
        return JSONResponse(content={"datasets": [], "error": str(e)})


# ── GET /api/datasets/{slug}/csv ──────────────────────────────────────────────

@router.get("/datasets/{slug}/csv")
async def dataset_csv(slug: str):
    """Returns raw CSV text for a dataset and increments download_count."""
    try:
        from asgiref.sync import sync_to_async

        @sync_to_async
        def _fetch():
            from main.models import Dataset
            ds = Dataset.objects.get(slug=slug, is_public=True)
            Dataset.objects.filter(pk=ds.pk).update(download_count=ds.download_count + 1)
            return ds.csv_data, ds.name

        csv_text, name = await _fetch()
        from fastapi.responses import PlainTextResponse
        return PlainTextResponse(
            content=csv_text,
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{slug}.csv"'}
        )
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))

