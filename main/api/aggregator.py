import asyncio

_update_queue: list = []

async def aggregation_worker():
    while True:
        await asyncio.sleep(60)

def get_stats() -> dict:
    from main.federated_engine import _update_buffer, _session_accepted, _session_rejected, BUFFER_SIZE
    return {
        "buffer_depth": len(_update_buffer),
        "buffer_capacity": BUFFER_SIZE,
        "total_accepted": _session_accepted,
        "total_rejected": _session_rejected,
    }
