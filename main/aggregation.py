import numpy as np

def trimmed_mean(updates: list[dict], trim_ratio: float = 0.1) -> dict:
    if not updates:
        return {}
    aggregated = {}
    keys = updates[0].keys()
    for k in keys:
        layer_updates = np.array([u[k] for u in updates], dtype=np.float32)
        sorted_updates = np.sort(layer_updates, axis=0)
        n = len(updates)
        trim_count = int(n * trim_ratio)
        if n - 2 * trim_count > 0:
            trimmed = sorted_updates[trim_count: n - trim_count]
        else:
            trimmed = sorted_updates
        aggregated[k] = np.mean(trimmed, axis=0).tolist()
    return aggregated

def mean_delta(deltas: list[dict]) -> dict:
    if not deltas:
        return {}
    result = {}
    keys = deltas[0].keys()
    for k in keys:
        stacked = np.array([d[k] for d in deltas], dtype=np.float32)
        result[k] = np.mean(stacked, axis=0).tolist()
    return result

def get_buffer_stats(buffer: list) -> dict:
    return {
        "buffer_depth": len(buffer),
        "buffer_capacity": 5,
    }
