from fastapi import APIRouter, HTTPException, BackgroundTasks, UploadFile, File, Query
from pydantic import BaseModel
from typing import Dict, Any, Optional, List
import asyncio
import io
import csv
import json
from main.federated_engine import get_latest_model, process_update
from asgiref.sync import sync_to_async

router = APIRouter()


class UpdateSubmission(BaseModel):
    client_id: str
    weights: Dict[str, Any]
    base_version: int = 0
    local_rmse: Optional[float] = None
    local_mae: Optional[float] = None


@router.get("/health")
async def health_check():
    return {"status": "ok", "platform": "Fedora", "mode": "Unified"}


@router.get("/model")
async def fetch_model():
    try:
        model_info = await get_latest_model()
        return model_info
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/submit-update")
async def submit_weight_update(submission: UpdateSubmission):
    try:
        result = await process_update(
            submission.client_id,
            submission.weights,
            base_version=submission.base_version,
            local_rmse=submission.local_rmse,
            local_mae=submission.local_mae,
        )
        return result
    except Exception as e:
        print(f"Error processing update: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


_CANONICAL_COLUMNS: List[str] = []

def _get_canonical_columns() -> List[str]:
    global _CANONICAL_COLUMNS
    if _CANONICAL_COLUMNS:
        return _CANONICAL_COLUMNS
    return _CANONICAL_COLUMNS

def _set_canonical_columns(cols: List[str]) -> None:
    global _CANONICAL_COLUMNS
    if not _CANONICAL_COLUMNS:
        _CANONICAL_COLUMNS = [c for c in cols]


@router.get("/schema")
async def get_schema():
    cols = _get_canonical_columns()
    return {"columns": cols, "count": len(cols)}


def _clean_csv_data(raw_bytes: bytes, canonical_cols: List[str]) -> str:
    """Clean a CSV in-place: convert non-numeric values to 0, fill blanks with 0.
    Uses the file's OWN columns — canonical schema is only for weight submission."""
    content = raw_bytes.decode("utf-8", errors="replace")
    reader = csv.DictReader(io.StringIO(content))
    rows = list(reader)
    if not rows:
        return content

    file_cols = list(reader.fieldnames or [])

    out_rows = []
    for row in rows:
        cleaned_row = {}
        for col in file_cols:
            raw_val = row.get(col, "")
            try:
                v = float(str(raw_val).strip()) if str(raw_val).strip() != "" else 0.0
                cleaned_row[col] = v
            except (ValueError, AttributeError):
                cleaned_row[col] = 0.0
        out_rows.append(cleaned_row)

    # Drop rows that are entirely empty
    out_rows = [r for r in out_rows if any(v != 0.0 for v in r.values())]

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=file_cols)
    writer.writeheader()
    writer.writerows(out_rows)
    return output.getvalue()


@router.post("/clean-csv")
async def clean_csv(file: UploadFile = File(...)):
    try:
        raw = await file.read()
        canonical = _get_canonical_columns()
        cleaned = _clean_csv_data(raw, canonical)
        from fastapi.responses import Response
        return Response(
            content=cleaned,
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="cleaned_{file.filename}"'},
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"CSV cleaning failed: {str(e)}")


@router.post("/register-schema")
async def register_schema(body: Dict[str, Any]):
    cols = body.get("columns", [])
    if cols:
        _set_canonical_columns(cols)
    return {"status": "ok", "canonical_columns": _get_canonical_columns()}


@router.delete("/model/latest")
async def delete_latest_model():
    """Delete the current latest model version and revert to the previous one."""
    try:
        from main.models import GlobalModel

        def _fetch_top_two():
            versions = list(GlobalModel.objects.all().order_by('-version')[:2])
            return versions

        versions = await sync_to_async(_fetch_top_two)()

        if not versions:
            raise HTTPException(status_code=404, detail="No model versions exist")

        latest = versions[0]
        previous = versions[1] if len(versions) > 1 else None

        # Delete weight file from disk
        if os.path.exists(latest.weights_path):
            os.remove(latest.weights_path)

        # Delete DB record
        await sync_to_async(latest.delete)()

        # Clear in-memory buffer so next submissions go against the reverted model
        from main.federated_engine import _update_buffer
        _update_buffer.clear()

        print(f"[Engine] Deleted v{latest.version}. Active version: {previous.version if previous else 'none'}")
        return {
            "status": "deleted",
            "deleted_version": latest.version,
            "active_version": previous.version if previous else None,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))



@router.get("/versions")
async def list_versions():
    try:
        from main.models import GlobalModel

        def _fetch():
            return list(
                GlobalModel.objects.all().order_by('-version').values(
                    'version', 'weights_path', 'created_at', 'best_rmse', 'best_mae',
                    'accepted_count', 'rejected_count'
                )
            )

        rows = await sync_to_async(_fetch)()
        result = []
        for r in rows:
            result.append({
                "version": r["version"],
                "weights_path": r["weights_path"],
                "created_at": r["created_at"].isoformat() if r["created_at"] else None,
                "best_rmse": round(r["best_rmse"], 4) if r["best_rmse"] is not None else None,
                "best_mae": round(r["best_mae"], 4) if r["best_mae"] is not None else None,
                "accepted_count": r["accepted_count"],
                "rejected_count": r["rejected_count"],
            })
        return {"versions": result, "count": len(result)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/rollback/{target_version}")
async def rollback_to_version(target_version: int):
    try:
        from main.models import GlobalModel
        import shutil

        def _fetch_target_and_latest():
            target = GlobalModel.objects.filter(version=target_version).first()
            latest = GlobalModel.objects.all().order_by('-version').first()
            return target, latest

        target, latest = await sync_to_async(_fetch_target_and_latest)()

        if not target:
            raise HTTPException(status_code=404, detail=f"Version {target_version} not found")
        if not os.path.exists(target.weights_path):
            raise HTTPException(status_code=404, detail=f"Weight file for v{target_version} missing on disk")

        new_version = (latest.version if latest else 0) + 1
        weights_dir = "weights_bank"
        os.makedirs(weights_dir, exist_ok=True)
        new_path = os.path.join(weights_dir, f"unified_v{new_version}.json")
        shutil.copy2(target.weights_path, new_path)

        from main.federated_engine import _update_buffer
        _update_buffer.clear()

        await sync_to_async(GlobalModel.objects.create)(
            version=new_version,
            weights_path=new_path,
            best_rmse=target.best_rmse,
            best_mae=target.best_mae,
            accepted_count=0,
            rejected_count=0,
        )

        print(f"[Engine] Rollback: v{target_version} → new v{new_version}")
        return {
            "status": "rolled_back",
            "from_version": target_version,
            "new_version": new_version,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/metrics-history")
async def metrics_history(client_id: str = Query(...), limit: int = Query(10)):
    try:
        from main.models import ModelUpdateLog, Client, GlobalModel

        def _fetch():
            try:
                client = Client.objects.get(client_id=client_id)
            except Client.DoesNotExist:
                return None, []
            logs = (
                ModelUpdateLog.objects
                .filter(client=client)
                .order_by("-timestamp")[:limit]
            )
            latest_model = GlobalModel.objects.first()
            return latest_model, list(logs)

        latest_model, logs = await sync_to_async(_fetch)()
        if logs is None:
            raise HTTPException(status_code=404, detail="Client not found")

        history = []
        for log in logs:
            history.append({
                "id": log.id,
                "accepted": log.accepted,
                "norm": round(log.norm, 4),
                "local_rmse": round(log.local_rmse, 4) if log.local_rmse is not None else None,
                "local_mae": round(log.local_mae, 4) if log.local_mae is not None else None,
                "base_version": log.base_version,
                "staleness": log.staleness,
                "timestamp": log.timestamp.isoformat(),
            })

        return {
            "client_id": client_id,
            "global_version": latest_model.version if latest_model else 0,
            "global_best_rmse": round(latest_model.best_rmse, 4) if latest_model and latest_model.best_rmse is not None else None,
            "global_best_mae": round(latest_model.best_mae, 4) if latest_model and latest_model.best_mae is not None else None,
            "history": history,
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
