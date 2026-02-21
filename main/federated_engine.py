import json
import os
import torch
from asgiref.sync import sync_to_async
from django.utils import timezone

from main.models import GlobalModel, Client, ModelUpdateLog
from main.model_factory import create_unified_model, get_state_dict_serializable, load_state_dict_from_json
from main.trust_engine import validate_update, update_client_trust, calculate_update_norm

# Default architecture parameters for the unified environment
DEFAULT_INPUT_DIM = 20  # Matches common tabular tasks
DEFAULT_OUT_DIM = 1    # Regression/Probabilistic default

async def get_latest_model():
    """Fetches the latest global model architecture and weights."""
    try:
        latest = await sync_to_async(lambda: GlobalModel.objects.all().order_by('-version').first())()
    except:
        latest = None
    
    # Create the base model
    model = create_unified_model(input_dim=DEFAULT_INPUT_DIM, out_dim=DEFAULT_OUT_DIM)
    
    if latest and os.path.exists(latest.weights_path):
        try:
            with open(latest.weights_path, 'r') as f:
                weights = json.load(f)
            load_state_dict_from_json(model, weights)
            version = latest.version
        except Exception as e:
            print(f"[Engine] Failed to load weights from {latest.weights_path}: {e}")
            weights = get_state_dict_serializable(model)
            version = 0
    else:
        # Initial weights if no model exists
        weights = get_state_dict_serializable(model)
        version = 0
        
    return {
        "version": version,
        "input_shape": [DEFAULT_INPUT_DIM],
        "num_classes": DEFAULT_OUT_DIM,
        "weights": weights
    }

async def process_update(client_id: str, client_weights: dict):
    """
    Unified asynchronous pipeline for processing incoming weights.
    1. Validate client
    2. Check norm (Anti-Adversarial)
    3. Aggregate (Weighted Blend)
    4. Save version
    """
    client, _ = await sync_to_async(Client.objects.get_or_create)(client_id=client_id)
    
    # Validation (Malicious Mitigation)
    is_valid, reason = validate_update(client_weights)
    norm = calculate_update_norm(client_weights)
    
    if not is_valid:
        print(f"[Engine] Rejecting update from {client_id}: {reason}")
        await sync_to_async(ModelUpdateLog.objects.create)(
            client=client, norm=norm, accepted=False
        )
        await sync_to_async(update_client_trust)(client, accepted=False)
        return {"status": "rejected", "reason": reason}

    # Fetch current state
    latest_info = await get_latest_model()
    current_weights = latest_info["weights"]
    new_version = latest_info["version"] + 1
    
    # Adaptive alpha based on client trust
    alpha = 0.3 * client.trust_score  # conservative blend
    
    aggregated_weights = {}
    for k in current_weights.keys():
        w_glob = torch.tensor(current_weights[k], dtype=torch.float32)
        if k not in client_weights:
            aggregated_weights[k] = current_weights[k]
            continue
            
        w_upd = torch.tensor(client_weights[k], dtype=torch.float32)
        
        # Shape safety
        if w_glob.shape != w_upd.shape:
            reason = f"Shape mismatch layer {k}: {list(w_glob.shape)} vs {list(w_upd.shape)}"
            print(f"[Engine] Rejecting: {reason}")
            return {"status": "rejected", "reason": reason}
            
        # Aggregation: Weighted Async Blend
        w_new = (w_glob * (1.0 - alpha)) + (w_upd * alpha)
        aggregated_weights[k] = w_new.tolist()

    # Persist
    weights_dir = "weights_bank"
    if not os.path.exists(weights_dir):
        os.makedirs(weights_dir)
        
    weights_path = os.path.join(weights_dir, f"unified_v{new_version}.json")
    with open(weights_path, 'w') as f:
        json.dump(aggregated_weights, f)
        
    await sync_to_async(GlobalModel.objects.create)(
        version=new_version,
        weights_path=weights_path
    )
    
    await sync_to_async(ModelUpdateLog.objects.create)(
        client=client, norm=norm, accepted=True
    )
    await sync_to_async(update_client_trust)(client, accepted=True)
    
    print(f"[Engine] Global model incremented to v{new_version}")
    return {"status": "accepted", "new_version": new_version}
