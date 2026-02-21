"""
FedGuard Configuration Constants
---------------------------------
All tunable hyperparameters for the federated learning system.
Edit these values to change system behaviour without touching logic code.
"""

# ── Aggregation Trigger ──────────────────────────────────────────────────────
N_MIN_UPDATES = 3        # Minimum updates received before aggregation fires
MAX_WAIT_SECONDS = 30    # Max seconds to wait before aggregating with whatever is available

# ── Staleness Control ────────────────────────────────────────────────────────
STALENESS_WINDOW = 3     # An update older than (current_round - STALENESS_WINDOW) is rejected

# ── Outlier Detection ────────────────────────────────────────────────────────
NORM_RATIO = 5.0         # Flag if an update's L2 norm > NORM_RATIO × median norm of the batch
COS_THRESHOLD = -0.3     # Flag if cosine similarity with median direction < COS_THRESHOLD

# ── Aggregation Algorithm ────────────────────────────────────────────────────
# Options: "trimmed_mean" | "median" | "fedavg"
AGG_ALGO = "trimmed_mean"

# ── Trimmed Mean ─────────────────────────────────────────────────────────────
TRIM_RATIO = 0.2         # Fraction clipped from each side (0.2 → clip bottom 20% and top 20%)

# ── Model Architecture ───────────────────────────────────────────────────────
INPUT_DIM = 20
OUTPUT_DIM = 10
MODEL_TYPE = "softmax"   # "softmax" or "mlp"
