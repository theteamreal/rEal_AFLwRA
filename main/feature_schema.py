"""
feature_schema.py — Global Feature Schema Store
================================================
Persists the canonical 20-feature schema (names + per-feature Z-score stats)
to disk so the harmonization layer survives server restarts.

File on disk:  weights_bank/feature_schema.json
Schema format:
    {
        "features":  ["col_a", "col_b", ...],   # ordered, exactly 20
        "means":     [mean_a, mean_b, ...],
        "stds":      [std_a,  std_b,  ...],
        "registered_at": "2026-02-22T02:50:00"
    }

Public API
----------
set_schema(features, means, stds) -> dict
    Register/overwrite the canonical schema.  Persists to disk atomically.

get_schema() -> dict | None
    Return the stored schema or None if not yet registered.

align_features(rows, schema) -> (aligned_rows, report)
    Harmonise a list-of-dicts (CSV rows) to match the canonical schema.
    Returns (list[dict], report_dict).

report keys:
    added   : list[str]  — columns that were missing and padded with mean
    dropped : list[str]  — columns that were extra and removed
    reordered: bool      — True when column order differed
    ok      : bool       — True when no changes were needed
"""

import json
import os
from datetime import datetime, timezone

# ── Path resolution ──────────────────────────────────────────────────────────
_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SCHEMA_DIR = os.path.join(_BASE_DIR, "weights_bank")
_SCHEMA_FILE = os.path.join(_SCHEMA_DIR, "feature_schema.json")

# ── In-memory cache ──────────────────────────────────────────────────────────
_cached_schema: dict | None = None


# ── Helpers ──────────────────────────────────────────────────────────────────

def _ensure_dir() -> None:
    os.makedirs(_SCHEMA_DIR, exist_ok=True)


def _load_from_disk() -> dict | None:
    if not os.path.exists(_SCHEMA_FILE):
        return None
    try:
        with open(_SCHEMA_FILE, "r") as f:
            schema = json.load(f)
        print(f"[FeatureSchema] Loaded from disk — {len(schema.get('features', []))} features")
        return schema
    except Exception as e:
        print(f"[FeatureSchema] Load error: {e}")
        return None


def _save_to_disk(schema: dict) -> None:
    _ensure_dir()
    try:
        with open(_SCHEMA_FILE, "w") as f:
            json.dump(schema, f, indent=2)
        print(f"[FeatureSchema] Saved — {len(schema['features'])} features")
    except Exception as e:
        print(f"[FeatureSchema] Save error: {e}")


# ── Bootstrap on import ──────────────────────────────────────────────────────
_cached_schema = _load_from_disk()


# ── Public API ───────────────────────────────────────────────────────────────

def set_schema(
    features: list[str],
    means: list[float] | None = None,
    stds: list[float] | None = None,
    overwrite: bool = False,
) -> dict:
    """
    Register the canonical feature schema.
    If a schema is already registered and overwrite=False, the existing schema
    is returned unchanged (idempotent — first-register wins).
    """
    global _cached_schema
    if _cached_schema is not None and not overwrite:
        return _cached_schema

    n = len(features)
    schema = {
        "features": list(features),
        "means":    list(means)  if means  is not None else [0.0] * n,
        "stds":     list(stds)   if stds   is not None else [1.0] * n,
        "registered_at": datetime.now(timezone.utc).isoformat(),
    }
    _cached_schema = schema
    _save_to_disk(schema)
    return schema


def get_schema() -> dict | None:
    """Return the current canonical schema, or None if not yet registered."""
    return _cached_schema


def align_features(
    rows: list[dict],
    schema: dict,
) -> tuple[list[dict], dict]:
    """
    Harmonise a list-of-dicts (one dict per CSV row) to match the canonical schema.

    1. For each row, keep only schema columns (in schema order).
    2. Missing columns  → filled with the schema's stored column mean (fallback 0.0).
    3. Extra columns    → silently dropped.
    4. Result always has exactly len(schema['features']) columns in schema order.

    Returns (aligned_rows, report)
    """
    if not rows:
        return rows, {"added": [], "dropped": [], "reordered": False, "ok": True}

    canonical  = schema["features"]
    means_map  = dict(zip(canonical, schema.get("means", [0.0] * len(canonical))))
    uploaded   = list(rows[0].keys())

    uploaded_set  = set(uploaded)
    canonical_set = set(canonical)

    added   = [c for c in canonical if c not in uploaded_set]
    dropped = [c for c in uploaded  if c not in canonical_set]
    reordered = (
        [c for c in uploaded if c in canonical_set] !=
        [c for c in canonical if c in uploaded_set]
    )

    aligned = []
    for row in rows:
        new_row = {}
        for col in canonical:
            if col in row:
                new_row[col] = row[col]
            else:
                new_row[col] = means_map.get(col, 0.0)
        aligned.append(new_row)

    report = {
        "added":     added,
        "dropped":   dropped,
        "reordered": reordered,
        "ok":        len(added) == 0 and len(dropped) == 0 and not reordered,
    }
    return aligned, report


def reset_schema() -> None:
    """Delete the persisted schema (for testing / admin resets)."""
    global _cached_schema
    _cached_schema = None
    if os.path.exists(_SCHEMA_FILE):
        os.remove(_SCHEMA_FILE)
        print("[FeatureSchema] Schema deleted.")
