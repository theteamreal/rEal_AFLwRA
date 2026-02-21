import numpy as np

def calculate_update_norm(update_weights: dict) -> float:
    total_norm = 0.0
    for val in update_weights.values():
        arr = np.array(val, dtype=np.float32)
        total_norm += float(np.sum(np.square(arr)))
    return float(np.sqrt(total_norm))

def validate_update(update_weights: dict, threshold: float = 10000.0) -> tuple[bool, str]:
    norm = calculate_update_norm(update_weights)
    if norm > threshold:
        return False, f"L2 norm {norm:.2f} exceeds threshold {threshold}"
    for k, v in update_weights.items():
        arr = np.array(v, dtype=np.float32)
        if np.any(np.isnan(arr)) or np.any(np.isinf(arr)):
            return False, f"NaN/Inf in layer {k}"
    return True, "Valid"

def cosine_similarity_check(delta: dict, reference: dict, threshold: float = 0.0) -> tuple[bool, str]:
    if not reference:
        return True, "No reference yet"
    keys = [k for k in delta if k in reference]
    if not keys:
        return True, "No common keys"
    flat_delta = np.concatenate([np.array(delta[k], dtype=np.float32).ravel() for k in keys])
    flat_ref = np.concatenate([np.array(reference[k], dtype=np.float32).ravel() for k in keys])
    norm_d = np.linalg.norm(flat_delta)
    norm_r = np.linalg.norm(flat_ref)
    if norm_d < 1e-9 or norm_r < 1e-9:
        return True, "Zero vector — skip cosine check"
    sim = float(np.dot(flat_delta, flat_ref) / (norm_d * norm_r))
    if sim < threshold:
        return False, f"Cosine similarity {sim:.4f} below threshold {threshold} (stealth poisoning detected)"
    return True, f"Cosine similarity {sim:.4f} OK"

def update_client_trust(client, accepted: bool):
    if accepted:
        client.trust_score = min(1.0, client.trust_score + 0.01)
    else:
        client.trust_score = max(0.0, client.trust_score - 0.2)
        client.rejected_count += 1
    client.save()
