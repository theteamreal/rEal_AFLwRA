"""
Outlier Detection + Robust Aggregation Algorithms — Phase 4
-------------------------------------------------------------
Two independent checks flag suspicious updates BEFORE they touch the queue.
Three aggregation algorithms are available, selected by AGG_ALGO config.
"""

import numpy as np
from fedguard.config import NORM_RATIO, COS_THRESHOLD, AGG_ALGO, TRIM_RATIO


# ── Helpers ──────────────────────────────────────────────────────────────────

def _flatten(weights: dict) -> np.ndarray:
    """Flatten a weights dict to a single 1-D numpy array for geometric ops."""
    parts = []
    for k in sorted(weights.keys()):
        v = np.array(weights[k], dtype=np.float64).flatten()
        parts.append(v)
    return np.concatenate(parts)


def _unflatten(flat: np.ndarray, template: dict) -> dict:
    """Reconstruct a weights dict from a flat array using a template for shapes."""
    result = {}
    offset = 0
    for k in sorted(template.keys()):
        arr = np.array(template[k], dtype=np.float64)
        size = arr.size
        result[k] = flat[offset:offset + size].reshape(arr.shape).tolist()
        offset += size
    return result


def _cosine_sim(a: np.ndarray, b: np.ndarray) -> float:
    """Cosine similarity between two vectors."""
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a < 1e-12 or norm_b < 1e-12:
        return 1.0  # treat zero vectors as aligned (no signal)
    return float(np.dot(a, b) / (norm_a * norm_b))


# ── Outlier Detection ────────────────────────────────────────────────────────

def is_outlier(update: dict, all_updates: list[dict]) -> tuple[bool, str]:
    """
    Two independent Byzantine-resilience checks.

    Args:
        update:      The specific update to evaluate {'weights': ..., 'client_id': ...}
        all_updates: All updates in the current batch (including `update`)

    Returns:
        (True, reason_string) if flagged, (False, 'clean') otherwise.
    """
    if len(all_updates) < 2:
        # Cannot compute median with < 2 updates — pass through
        return False, "clean"

    deltas = [_flatten(u['weights']) for u in all_updates]
    my_delta = _flatten(update['weights'])

    norms = [np.linalg.norm(d) for d in deltas]
    median_norm = float(np.median(norms))
    my_norm = np.linalg.norm(my_delta)

    # ── Check 1: Norm Ratio ──────────────────────────────────────────────────
    if my_norm / (median_norm + 1e-9) > NORM_RATIO:
        return True, f"norm_ratio:{my_norm / (median_norm + 1e-9):.2f}"

    # ── Check 2: Cosine Similarity with Coordinate-Wise Median Direction ─────
    stacked = np.stack(deltas, axis=0)          # shape: (n_clients, n_params)
    median_dir = np.median(stacked, axis=0)     # coordinate-wise median
    cos = _cosine_sim(my_delta, median_dir)
    if cos < COS_THRESHOLD:
        return True, f"cosine_sim:{cos:.3f}"

    return False, "clean"


def filter_outliers(updates: list[dict]) -> list[dict]:
    """
    Remove flagged updates from a batch.  Runs is_outlier for each update
    against the FULL batch (not filtered batch) so the median isn't poisoned.
    Returns the clean list.
    """
    clean = []
    for u in updates:
        flagged, reason = is_outlier(u, updates)
        if not flagged:
            clean.append(u)
        else:
            # Caller (aggregator) handles DB logging
            u['_flagged'] = True
            u['_flag_reason'] = reason
    return clean


# ── Aggregation Algorithms ───────────────────────────────────────────────────

def _trimmed_mean(updates: list[dict], template: dict) -> dict:
    """
    Trimmed Mean: drop top TRIM_RATIO and bottom TRIM_RATIO fraction of each
    coordinate, then average the middle.  Tolerates up to TRIM_RATIO malicious clients.
    """
    stacked = np.stack([_flatten(u['weights']) for u in updates], axis=0)
    k = max(1, int(len(updates) * TRIM_RATIO))
    stacked_sorted = np.sort(stacked, axis=0)
    trimmed = stacked_sorted[k: len(updates) - k]
    if len(trimmed) == 0:
        trimmed = stacked_sorted  # fall back if trim removes everything
    result_flat = np.mean(trimmed, axis=0)
    return _unflatten(result_flat, template)


def _coordinate_median(updates: list[dict], template: dict) -> dict:
    """
    Coordinate-Wise Median: take the median of each parameter independently.
    Theoretically tolerates up to 50% malicious clients.
    """
    stacked = np.stack([_flatten(u['weights']) for u in updates], axis=0)
    result_flat = np.median(stacked, axis=0)
    return _unflatten(result_flat, template)


def _fedavg(updates: list[dict], template: dict) -> dict:
    """
    Weighted FedAvg: weighted average by n_samples.
    Classic baseline — fast but not Byzantine-robust.
    """
    total_samples = sum(u.get('n_samples', 1) for u in updates)
    stacked = np.stack([_flatten(u['weights']) for u in updates], axis=0)
    weights_arr = np.array([u.get('n_samples', 1) / total_samples for u in updates])
    result_flat = np.sum(stacked * weights_arr[:, np.newaxis], axis=0)
    return _unflatten(result_flat, template)


def aggregate(updates: list[dict], template: dict, algo: str = None) -> dict:
    """
    Dispatch to the configured aggregation algorithm.

    Args:
        updates:  List of clean update dicts (already outlier-filtered)
        template: Weight dict with the correct shapes (used for unflattening)
        algo:     Override AGG_ALGO if provided

    Returns:
        New aggregated weights dict (NaN/Inf sanitized — safe for JSON).
    """
    algo = algo or AGG_ALGO
    if algo == "median":
        result = _coordinate_median(updates, template)
    elif algo == "fedavg":
        result = _fedavg(updates, template)
    else:  # default: trimmed_mean
        result = _trimmed_mean(updates, template)

    # Sanitize: replace any NaN / Inf that slipped through numerical ops
    sanitized = {}
    for k, v in result.items():
        arr = np.array(v, dtype=np.float64)
        arr = np.nan_to_num(arr, nan=0.0, posinf=1e6, neginf=-1e6)
        sanitized[k] = arr.tolist()
    return sanitized
