"""
Async Aggregation Worker + Queue — Phase 3
-------------------------------------------
Runs as a long-lived background task started during FastAPI lifespan.
Drains the asyncio queue when N_MIN updates arrive OR MAX_WAIT_SECONDS elapses.
"""

import asyncio
import time
import logging

from fedguard.config import N_MIN_UPDATES, MAX_WAIT_SECONDS
from main.api import model_store
from main.api.detector import filter_outliers, aggregate, is_outlier

logger = logging.getLogger("fedguard.aggregator")

# Shared queue — imported by endpoints.py so both sides use the same object
update_queue: asyncio.Queue = asyncio.Queue()

# Live stats readable by /api/status
_stats = {
    "queue_depth": 0,
    "last_aggregation": None,
    "total_rounds_aggregated": 0,
    "total_updates_received": 0,
    "total_flagged": 0,
}


def get_stats() -> dict:
    return {**_stats, "queue_depth": update_queue.qsize()}


async def _save_round_to_db(round_id: int, n_updates: int, n_flagged: int,
                             flagged_info: list[dict]) -> None:
    """
    Persist round data to Django DB asynchronously via sync_to_async.
    Wrapped in try/except so a DB failure never crashes the aggregation worker.
    """
    try:
        import django
        from asgiref.sync import sync_to_async

        @sync_to_async
        def _write():
            from main.models import RoundHistory, ClientRecord
            RoundHistory.objects.create(
                round_id=round_id,
                n_updates=n_updates,
                n_flagged=n_flagged,
                global_loss=None,
            )
            for info in flagged_info:
                record, _ = ClientRecord.objects.get_or_create(
                    client_id=info['client_id']
                )
                record.total_updates += 1
                record.flagged_count += 1
                record.flag_reason = info.get('reason', '')
                record.save()

        await _write()
    except Exception as e:
        logger.warning(f"DB write failed (non-fatal): {e}")


async def _update_client_stats_in_db(updates: list[dict]) -> None:
    """Record clean updates in ClientRecord for dashboard display."""
    try:
        from asgiref.sync import sync_to_async

        @sync_to_async
        def _write():
            from main.models import ClientRecord
            for u in updates:
                record, _ = ClientRecord.objects.get_or_create(
                    client_id=u.get('client_id', 'unknown')
                )
                record.total_updates += 1
                record.save()

        await _write()
    except Exception as e:
        logger.warning(f"DB client stat write failed (non-fatal): {e}")


async def aggregation_worker() -> None:
    """
    Long-running background coroutine.
    Blocks on queue, collects updates, triggers aggregation.
    """
    logger.info("🚀 Aggregation worker started")

    while True:
        updates: list[dict] = []
        deadline = time.monotonic() + MAX_WAIT_SECONDS

        # ── Drain queue until N_MIN or timeout ───────────────────────────────
        while len(updates) < N_MIN_UPDATES:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            try:
                update = await asyncio.wait_for(update_queue.get(), timeout=remaining)
                updates.append(update)
                update_queue.task_done()
                _stats["total_updates_received"] += 1
                logger.info(
                    f"📥 Queued update from {update.get('client_id', '?')} "
                    f"(batch size now {len(updates)})"
                )
            except asyncio.TimeoutError:
                break

        if not updates:
            await asyncio.sleep(1)
            continue

        # ── Outlier filtering ─────────────────────────────────────────────────
        clean = filter_outliers(updates)
        flagged = [u for u in updates if u.get('_flagged')]
        n_flagged = len(flagged)
        flagged_info = [
            {'client_id': u.get('client_id', 'unknown'),
             'reason': u.get('_flag_reason', '')}
            for u in flagged
        ]

        if not clean:
            logger.warning("⚠️  All updates in batch were flagged — skipping round")
            _stats["total_flagged"] += n_flagged
            continue

        # ── Aggregate ─────────────────────────────────────────────────────────
        _, current_weights = await model_store.get_weights()
        try:
            new_weights = aggregate(clean, current_weights)
        except Exception as e:
            logger.error(f"Aggregation failed: {e}")
            continue

        new_round_id = await model_store.set_weights(new_weights)

        # ── Persist to DB ─────────────────────────────────────────────────────
        await _save_round_to_db(new_round_id, len(clean), n_flagged, flagged_info)
        await _update_client_stats_in_db(clean)

        # ── Update live stats ─────────────────────────────────────────────────
        _stats["last_aggregation"] = time.time()
        _stats["total_rounds_aggregated"] += 1
        _stats["total_flagged"] += n_flagged

        logger.info(
            f"✅ Round {new_round_id} complete — "
            f"{len(clean)} clean, {n_flagged} flagged"
        )
