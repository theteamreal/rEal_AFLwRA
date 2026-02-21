import torch
import numpy as np

def calculate_update_norm(update_weights: dict) -> float:
    """Calculates the L2 norm of the weight update (difference from 0)."""
    total_norm = 0.0
    for val in update_weights.values():
        arr = np.array(val)
        total_norm += np.sum(np.square(arr))
    return float(np.sqrt(total_norm))

def validate_update(update_weights: dict, threshold: float = 1000.0) -> tuple[bool, str]:
    """
    Validates a weight update based on its L2 norm.
    Rejects updates that exceed the norm threshold (potential malicious/exploding gradients).
    """
    norm = calculate_update_norm(update_weights)
    if norm > threshold:
        return False, f"L2 norm {norm:.2f} exceeds threshold {threshold}"
    
    # Check for NaN/Inf
    for k, v in update_weights.items():
        if np.any(np.isnan(v)) or np.any(np.isinf(v)):
            return False, f"Update contains NaN or Inf values in layer {k}"
            
    return True, "Valid"

def update_client_trust(client, accepted: bool):
    """
    Updates a client's trust score based on whether their update was accepted.
    Decreases score on rejection, maintains or slowly rewards on acceptance.
    """
    if accepted:
        # Slowly recover trust if it was low
        client.trust_score = min(1.0, client.trust_score + 0.01)
    else:
        # Sharp penalty for rejection
        client.trust_score = max(0.0, client.trust_score - 0.2)
        client.rejected_count += 1
    client.save()
