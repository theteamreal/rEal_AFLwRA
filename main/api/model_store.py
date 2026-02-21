"""
Global Model Store — Phase 2
------------------------------
Module-level singleton that holds the global federated model weights.

Thread-safety:
  - Reads:  safe without lock (Python GIL + we replace dict atomically)
  - Writes: protected by asyncio.Lock() — only the aggregation worker writes

Persistence:
  - Weights are saved to weights.json after every aggregation round.
  - On startup the file is loaded so server restarts / hot-reloads
    do NOT reset training progress.
"""

import asyncio
import json
import os
import numpy as np
from fedguard.config import INPUT_DIM, OUTPUT_DIM, MODEL_TYPE

_lock = asyncio.Lock()

# Path for persisted weights — sits next to manage.py
_WEIGHTS_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    "weights.json"
)

_model_config = {
    "type": MODEL_TYPE,
    "input_dim": INPUT_DIM,
    "output_dim": OUTPUT_DIM,
}


def _default_weights() -> dict:
    return {
        "W": (np.random.randn(INPUT_DIM, OUTPUT_DIM) * 0.01).tolist(),
        "b": np.zeros(OUTPUT_DIM).tolist(),
    }


def _load_from_disk() -> tuple[int, dict]:
    """Load weights and round_id from disk. Returns (0, default_weights) if not found."""
    if os.path.exists(_WEIGHTS_FILE):
        try:
            with open(_WEIGHTS_FILE, "r") as f:
                data = json.load(f)
            print(f"[model_store] Restored round {data['round_id']} from weights.json")
            return data["round_id"], data["weights"]
        except Exception as e:
            print(f"[model_store] Could not load weights.json: {e} — using defaults")
    return 0, _default_weights()


def _save_to_disk(round_id: int, weights: dict) -> None:
    """Save weights and round_id to disk. Errors are non-fatal."""
    try:
        with open(_WEIGHTS_FILE, "w") as f:
            json.dump({"round_id": round_id, "weights": weights}, f)
    except Exception as e:
        print(f"[model_store] Could not save weights.json: {e}")


# ── Bootstrap from disk on module import ─────────────────────────────────────
_round_id, _weights = _load_from_disk()


async def get_weights() -> tuple[int, dict]:
    """Return (round_id, weights_copy). Safe to call without lock."""
    return _round_id, {k: list(v) for k, v in _weights.items()}


async def set_weights(new_weights: dict) -> int:
    """Atomically replace global weights, increment round_id, persist to disk. Returns new round_id."""
    global _weights, _round_id
    async with _lock:
        _weights = {k: list(v) if not isinstance(v, list) else v
                    for k, v in new_weights.items()}
        _round_id += 1
        _save_to_disk(_round_id, _weights)
        return _round_id


def get_model_config() -> dict:
    """Return immutable model architecture config."""
    return dict(_model_config)


def get_round_id() -> int:
    """Synchronous read of current round (safe for status checks)."""
    return _round_id
