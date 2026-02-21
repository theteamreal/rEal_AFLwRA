"""
Global Model Store — Phase 2
------------------------------
Module-level singleton that holds the global federated model weights.

Thread-safety:
  - Reads:  safe without lock (Python GIL + we replace dict atomically)
  - Writes: protected by asyncio.Lock() — only the aggregation worker writes
"""

import asyncio
import numpy as np
from fedguard.config import INPUT_DIM, OUTPUT_DIM, MODEL_TYPE

_lock = asyncio.Lock()
_round_id: int = 0

# Initialize with small random weights (not zero — avoids symmetry breaking issues)
_weights: dict = {
    "W": (np.random.randn(INPUT_DIM, OUTPUT_DIM) * 0.01).tolist(),
    "b": np.zeros(OUTPUT_DIM).tolist(),
}

_model_config = {
    "type": MODEL_TYPE,
    "input_dim": INPUT_DIM,
    "output_dim": OUTPUT_DIM,
}


async def get_weights() -> tuple[int, dict]:
    """Return (round_id, weights_copy). Safe to call without lock."""
    return _round_id, {k: list(v) for k, v in _weights.items()}


async def set_weights(new_weights: dict) -> int:
    """Atomically replace global weights and increment round_id. Returns new round_id."""
    global _weights, _round_id
    async with _lock:
        _weights = {k: list(v) if not isinstance(v, list) else v
                    for k, v in new_weights.items()}
        _round_id += 1
        return _round_id


def get_model_config() -> dict:
    """Return immutable model architecture config."""
    return dict(_model_config)


def get_round_id() -> int:
    """Synchronous read of current round (safe for status checks)."""
    return _round_id
