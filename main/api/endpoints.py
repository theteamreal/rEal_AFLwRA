from fastapi import APIRouter, HTTPException, BackgroundTasks, UploadFile, File, Query
from pydantic import BaseModel
from typing import Dict, Any, Optional, List
import asyncio
import io
import csv
import json
import os
from main.federated_engine import get_latest_model, process_update
from main import feature_schema as fs
from main import vt_scanner
from asgiref.sync import sync_to_async

router = APIRouter()


# ── VirusTotal Scan ─────────────────────────────────────────────────────────

@router.post("/scan-file")
async def scan_file(file: UploadFile = File(...)):
    """
    Scan an uploaded file with VirusTotal before processing.
    Returns: { safe, malicious, suspicious, engines_total, verdict, cached }
    If VT_API_KEY is not configured the endpoint returns safe=True with a warning.
    """
    try:
        data = await file.read()
        result = await vt_scanner.scan_bytes(data, file.filename or "upload.csv")
        return result
    except RuntimeError as e:
        # API key not configured — warn but don't block the user
        print(f"[VTScanner] {e}")
        return {
            "safe": True, "malicious": 0, "suspicious": 0,
            "undetected": 0, "engines_total": 0,
            "verdict": "SCAN SKIPPED — VT_API_KEY not configured",
            "cached": False, "warning": str(e),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"VirusTotal scan failed: {str(e)}")




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


# ── Schema helpers ──────────────────────────────────────────────────────────

@router.get("/schema")
async def get_schema():
    """Return canonical feature schema (names + scaler stats)."""
    schema = fs.get_schema()
    if schema is None:
        return {"columns": [], "means": [], "stds": [], "count": 0, "registered": False}
    return {
        "columns": schema["features"],
        "means":   schema["means"],
        "stds":    schema["stds"],
        "count":   len(schema["features"]),
        "registered": True,
        "registered_at": schema.get("registered_at"),
    }


@router.post("/register-schema")
async def register_schema(body: Dict[str, Any]):
    """
    Register the canonical feature schema.
    Body: {columns: [...], means: [...], stds: [...], overwrite: false}
    If a schema already exists and overwrite=false, the existing schema is returned.
    """
    cols      = body.get("columns", [])
    means     = body.get("means")     # optional
    stds      = body.get("stds")      # optional
    overwrite = body.get("overwrite", False)
    if not cols:
        raise HTTPException(status_code=400, detail="'columns' list is required")
    schema = fs.set_schema(cols, means=means, stds=stds, overwrite=overwrite)
    return {
        "status":        "registered" if overwrite or means else "ok",
        "features":      schema["features"],
        "count":         len(schema["features"]),
        "registered_at": schema.get("registered_at"),
    }


@router.delete("/schema")
async def delete_schema():
    """Admin: delete the persisted canonical schema (for resets / testing)."""
    fs.reset_schema()
    return {"status": "deleted"}


# ── CSV helpers ──────────────────────────────────────────────────────────────

def _clean_csv_rows(rows: list[dict], file_cols: list[str]) -> list[dict]:
    """Coerce all values to float, fill blanks with 0, drop all-zero rows."""
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
    return [r for r in out_rows if any(v != 0.0 for v in r.values())]


def _rows_to_csv(rows: list[dict], fieldnames: list[str]) -> str:
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue()


@router.post("/clean-csv")
async def clean_csv(file: UploadFile = File(...)):
    """Clean a raw CSV (coerce types, drop empties) then optionally harmonise to global schema."""
    try:
        raw = await file.read()
        content = raw.decode("utf-8", errors="replace")
        reader = csv.DictReader(io.StringIO(content))
        rows = list(reader)
        file_cols = list(reader.fieldnames or [])

        # Step 1: clean values
        cleaned_rows = _clean_csv_rows(rows, file_cols)

        # Step 2: harmonise schema features (if registered)
        schema = fs.get_schema()
        if schema:
            aligned_rows, report = fs.align_features(cleaned_rows, schema)
            schema_cols = schema["features"]
            canonical_set = set(schema_cols)
            # Keep extra cols (e.g. price / target) that are not schema features
            extra_cols = [c for c in file_cols if c not in canonical_set]
            final_cols = schema_cols + extra_cols

            # Re-attach extra col values to the aligned rows
            if extra_cols:
                orig_map = {i: cleaned_rows[i] for i in range(len(cleaned_rows))}
                for i, row in enumerate(aligned_rows):
                    src = orig_map.get(i, {})
                    for col in extra_cols:
                        row[col] = src.get(col, "")

            print(f"[align] added={report['added']} dropped={len(report['dropped'])} reordered={report['reordered']} extra={extra_cols}")
        else:
            aligned_rows = cleaned_rows
            final_cols   = file_cols

        cleaned_csv = _rows_to_csv(aligned_rows, final_cols)
        from fastapi.responses import Response
        return Response(
            content=cleaned_csv,
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="cleaned_{file.filename}"'},
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"CSV cleaning failed: {str(e)}")


@router.post("/align-csv")
async def align_csv(file: UploadFile = File(...)):
    """
    Harmonise an uploaded CSV to the canonical feature schema.
    Returns a JSON report + the aligned CSV as a string.
    If no schema is registered, the file is returned unchanged.
    """
    try:
        raw = await file.read()
        content = raw.decode("utf-8", errors="replace")
        reader = csv.DictReader(io.StringIO(content))
        rows = list(reader)
        file_cols = list(reader.fieldnames or [])

        schema = fs.get_schema()
        if schema is None:
            return {
                "schema_registered": False,
                "report": {"added": [], "dropped": [], "reordered": False, "ok": True},
                "rows": len(rows),
                "columns": file_cols,
                "csv": content,
            }

        # Clean then align
        cleaned = _clean_csv_rows(rows, file_cols)
        aligned, report = fs.align_features(cleaned, schema)
        csv_out = _rows_to_csv(aligned, schema["features"])

        return {
            "schema_registered": True,
            "report":  report,
            "rows":    len(aligned),
            "columns": schema["features"],
            "csv":     csv_out,
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Alignment failed: {str(e)}")


@router.delete("/model/latest")
async def delete_latest_model():
    """Delete the current latest model version and revert to the previous one."""
    try:
        from main.models import GlobalModel

        def _fetch_top_two():
            return list(GlobalModel.objects.all().order_by('-version')[:2])

        versions = await sync_to_async(_fetch_top_two)()

        if not versions:
            raise HTTPException(status_code=404, detail="No model versions exist")

        latest   = versions[0]
        previous = versions[1] if len(versions) > 1 else None

        if os.path.exists(latest.weights_path):
            os.remove(latest.weights_path)

        await sync_to_async(latest.delete)()

        from main.federated_engine import _update_buffer
        _update_buffer.clear()

        print(f"[Engine] Deleted v{latest.version}. Active version: {previous.version if previous else 'none'}")
        return {
            "status":          "deleted",
            "deleted_version": latest.version,
            "active_version":  previous.version if previous else None,
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
                "version":        r["version"],
                "weights_path":   r["weights_path"],
                "created_at":     r["created_at"].isoformat() if r["created_at"] else None,
                "best_rmse":      round(r["best_rmse"], 4) if r["best_rmse"] is not None else None,
                "best_mae":       round(r["best_mae"],  4) if r["best_mae"]  is not None else None,
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
            "status":       "rolled_back",
            "from_version": target_version,
            "new_version":  new_version,
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
                "id":           log.id,
                "accepted":     log.accepted,
                "norm":         round(log.norm, 4),
                "local_rmse":   round(log.local_rmse, 4) if log.local_rmse is not None else None,
                "local_mae":    round(log.local_mae,  4) if log.local_mae  is not None else None,
                "base_version": log.base_version,
                "staleness":    log.staleness,
                "timestamp":    log.timestamp.isoformat(),
            })

        return {
            "client_id":       client_id,
            "global_version":  latest_model.version if latest_model else 0,
            "global_best_rmse": round(latest_model.best_rmse, 4) if latest_model and latest_model.best_rmse is not None else None,
            "global_best_mae":  round(latest_model.best_mae,  4) if latest_model and latest_model.best_mae  is not None else None,
            "history":         history,
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/versions")
async def list_versions():
    """Return a summary list of all saved GlobalModel checkpoints, newest first."""
    from main.models import GlobalModel

    def _fetch():
        return list(GlobalModel.objects.all().order_by("-version"))

    models = await sync_to_async(_fetch)()
    return {
        "versions": [
            {
                "version":        m.version,
                "created_at":     m.created_at.isoformat() if m.created_at else None,
                "best_rmse":      round(m.best_rmse, 4) if m.best_rmse is not None else None,
                "best_mae":       round(m.best_mae,  4) if m.best_mae  is not None else None,
                "accepted_count": m.accepted_count,
                "rejected_count": m.rejected_count,
                "weights_available": os.path.exists(m.weights_path),
            }
            for m in models
        ]
    }


@router.get("/version-detail/{version}")
async def version_detail(version: int):
    """Return metrics + per-contributor breakdown for one saved model version."""
    try:
        from main.models import GlobalModel, ModelUpdateLog

        def _fetch(ver):
            model = GlobalModel.objects.filter(version=ver).first()
            if not model:
                return None, []
            logs = list(
                ModelUpdateLog.objects.filter(base_version=ver)
                .order_by("timestamp")
                .select_related("client")
            )
            return model, logs

        model, logs = await sync_to_async(_fetch)(version)
        if not model:
            raise HTTPException(status_code=404, detail=f"Version {version} not found")

        contributors = []
        for log in logs:
            contributors.append({
                "client_id":  log.client.client_id,
                "local_rmse": round(log.local_rmse, 4) if log.local_rmse is not None else None,
                "staleness":  log.staleness,
                "norm":       round(log.norm, 4),
                "accepted":   log.accepted,
            })

        return {
            "version":        model.version,
            "created_at":     model.created_at.isoformat() if model.created_at else None,
            "best_rmse":      round(model.best_rmse, 4) if model.best_rmse is not None else None,
            "best_mae":       round(model.best_mae,  4) if model.best_mae  is not None else None,
            "accepted_count": model.accepted_count,
            "rejected_count": model.rejected_count,
            "weights_available": os.path.exists(model.weights_path),
            "contributors":   contributors,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/download/{version}")
async def download_model(version: int):
    """Stream the model weights JSON file as a downloadable attachment."""
    from fastapi.responses import FileResponse
    from main.models import GlobalModel

    def _get_model(ver):
        return GlobalModel.objects.filter(version=ver).first()

    model = await sync_to_async(_get_model)(version)
    if not model:
        raise HTTPException(status_code=404, detail=f"Version {version} not found in database")
    if not os.path.exists(model.weights_path):
        raise HTTPException(status_code=404, detail=f"Weight file for v{version} not found on disk")

    return FileResponse(
        path=model.weights_path,
        filename=f"fedora_global_v{version}.json",
        media_type="application/json",
    )
