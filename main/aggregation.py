import numpy as np

def trimmed_mean(updates: list[dict], trim_ratio: float = 0.1) -> dict:
    """
    Performs Trimmed Mean aggregation on a list of weight updates.
    
    Args:
        updates: List of state_dicts (as JSON-serializable dicts of lists)
        trim_ratio: % of top and bottom values to remove (default 10%)
        
    Returns:
        Aggregated weight dict.
    """
    if not updates:
        return {}
    
    # Use keys from first update
    aggregated = {}
    keys = updates[0].keys()
    
    for k in keys:
        # Stack all values for this layer across all updates
        # e.g. shape (num_updates, layer_shape...)
        layer_updates = np.array([u[k] for u in updates])
        
        # Sort along the update dimension
        sorted_updates = np.sort(layer_updates, axis=0)
        
        # Calculate number of elements to trim
        n = len(updates)
        trim_count = int(n * trim_ratio)
        
        # Trim and mean
        if n - 2 * trim_count > 0:
            trimmed = sorted_updates[trim_count : n - trim_count]
        else:
            # Fallback if too few updates to trim (just mean)
            trimmed = sorted_updates
            
        aggregated[k] = np.mean(trimmed, axis=0).tolist()
        
    return aggregated
