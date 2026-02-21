import json
import os
import numpy as np
from asgiref.sync import sync_to_async
from django.utils import timezone

from main.models import GlobalModel, Client, ModelUpdateLog
from main.model_factory import create_unified_model, get_state_dict_serializable, load_state_dict_from_json
from main.trust_engine import validate_update, update_client_trust, calculate_update_norm, cosine_similarity_check
from main.aggregation import trimmed_mean, mean_delta

INPUT_SIZE = 20
OUTPUT_SIZE = 1
BUFFER_SIZE = 5
NORM_THRESHOLD = 10000.0
COSINE_THRESHOLD = 0.0

_update_buffer: list[dict] = []
_reference_direction: dict = {}
_session_accepted: int = 0
_session_rejected: int = 0


def _load_global_weights(model_obj) -> dict:
    if model_obj and os.path.exists(model_obj.weights_path):
        try:
            with open(model_obj.weights_path, 'r') as f:
                return json.load(f)
        except Exception as e:
            print(f"[Engine] Failed to load weights from {model_obj.weights_path}: {e}")
    model = create_unified_model(input_dim=INPUT_SIZE, out_dim=OUTPUT_SIZE)
    return get_state_dict_serializable(model)


def _compute_delta(client_weights: dict, base_weights: dict) -> dict:
    delta = {}
    for k in base_weights:
        w_base = np.array(base_weights[k], dtype=np.float32)
        if k in client_weights:
            w_client = np.array(client_weights[k], dtype=np.float32)
            if w_base.shape == w_client.shape:
                delta[k] = (w_client - w_base).tolist()
            else:
                delta[k] = np.zeros_like(w_base).tolist()
        else:
            delta[k] = np.zeros_like(w_base).tolist()
    return delta


def _apply_delta(global_weights: dict, agg_delta: dict) -> dict:
    new_weights = {}
    for k in global_weights:
        w_glob = np.array(global_weights[k], dtype=np.float32)
        if k in agg_delta:
            new_weights[k] = (w_glob + np.array(agg_delta[k], dtype=np.float32)).tolist()
        else:
            new_weights[k] = global_weights[k]
    return new_weights


async def get_latest_model():
    try:
        latest = await sync_to_async(lambda: GlobalModel.objects.all().order_by('-version').first())()
    except Exception:
        latest = None

    model = create_unified_model(input_dim=INPUT_SIZE, out_dim=OUTPUT_SIZE)

    if latest and os.path.exists(latest.weights_path):
        try:
            with open(latest.weights_path, 'r') as f:
                weights = json.load(f)
            load_state_dict_from_json(model, weights)
            version = latest.version
        except Exception as e:
            print(f"[Engine] Failed to load weights: {e}")
            weights = get_state_dict_serializable(model)
            version = 0
    else:
        weights = get_state_dict_serializable(model)
        version = 0

    return {
        "version": version,
        "input_shape": [INPUT_SIZE],
        "num_classes": OUTPUT_SIZE,
        "weights": weights,
        "best_rmse": latest.best_rmse if latest else None,
        "best_mae": latest.best_mae if latest else None,
    }


async def process_update(
    client_id: str,
    client_weights: dict,
    base_version: int = 0,
    local_rmse: float = None,
    local_mae: float = None,
):
    global _update_buffer, _reference_direction, _session_accepted, _session_rejected

    try:
        client = await sync_to_async(Client.objects.get)(client_id=client_id)
    except Client.DoesNotExist:
        return {"status": "rejected", "reason": "Unauthorized Node: Please sign in to Fedora Hub."}

    latest = await sync_to_async(lambda: GlobalModel.objects.all().order_by('-version').first())()
    current_version = latest.version if latest else 0
    base_weights = _load_global_weights(latest)

    staleness = max(0, current_version - base_version)
    scale = 1.0 / (1.0 + staleness)

    delta = _compute_delta(client_weights, base_weights)

    is_valid, reason = validate_update(delta, threshold=NORM_THRESHOLD)
    norm = calculate_update_norm(delta)

    if not is_valid:
        _session_rejected += 1
        print(f"[Engine] Norm rejection from {client_id}: {reason}")
        await sync_to_async(ModelUpdateLog.objects.create)(
            client=client, norm=norm, accepted=False,
            local_rmse=local_rmse, local_mae=local_mae,
            base_version=base_version, staleness=staleness,
        )
        await sync_to_async(update_client_trust)(client, accepted=False)
        return {"status": "rejected", "reason": reason}

    cos_ok, cos_reason = cosine_similarity_check(delta, _reference_direction, threshold=COSINE_THRESHOLD)
    if not cos_ok:
        _session_rejected += 1
        print(f"[Engine] Cosine rejection from {client_id}: {cos_reason}")
        await sync_to_async(ModelUpdateLog.objects.create)(
            client=client, norm=norm, accepted=False,
            local_rmse=local_rmse, local_mae=local_mae,
            base_version=base_version, staleness=staleness,
        )
        await sync_to_async(update_client_trust)(client, accepted=False)
        return {"status": "rejected", "reason": cos_reason}

    scaled_delta = {k: (np.array(v, dtype=np.float32) * scale).tolist() for k, v in delta.items()}

    _update_buffer.append(scaled_delta)
    _session_accepted += 1

    await sync_to_async(ModelUpdateLog.objects.create)(
        client=client, norm=norm, accepted=True,
        local_rmse=local_rmse, local_mae=local_mae,
        base_version=base_version, staleness=staleness,
    )
    await sync_to_async(update_client_trust)(client, accepted=True)

    print(f"[Engine] Buffered update from {client_id} | staleness={staleness} scale={scale:.3f} | buffer={len(_update_buffer)}/{BUFFER_SIZE}")

    if len(_update_buffer) >= BUFFER_SIZE:
        _reference_direction = mean_delta(_update_buffer)
        agg_delta = trimmed_mean(_update_buffer, trim_ratio=0.1)
        new_weights = _apply_delta(base_weights, agg_delta)
        _update_buffer.clear()

        new_version = current_version + 1
        weights_dir = "weights_bank"
        os.makedirs(weights_dir, exist_ok=True)
        weights_path = os.path.join(weights_dir, f"unified_v{new_version}.json")
        with open(weights_path, 'w') as f:
            json.dump(new_weights, f)

        await sync_to_async(GlobalModel.objects.create)(
            version=new_version,
            weights_path=weights_path,
            best_rmse=local_rmse,
            best_mae=local_mae,
            accepted_count=_session_accepted,
            rejected_count=_session_rejected,
        )

        print(f"[Engine] Trimmed-mean aggregation complete → v{new_version} (accepted={_session_accepted} rejected={_session_rejected})")
        return {"status": "accepted", "new_version": new_version, "aggregation": "trimmed_mean"}

    return {
        "status": "buffered",
        "buffer_depth": len(_update_buffer),
        "buffer_capacity": BUFFER_SIZE,
        "staleness": staleness,
        "scale": round(scale, 4),
    }
