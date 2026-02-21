from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import Dict, Any
import asyncio
from main.federated_engine import get_latest_model, process_update

router = APIRouter()

class UpdateSubmission(BaseModel):
    client_id: str
    weights: Dict[str, Any]

@router.get("/health")
async def health_check():
    return {"status": "ok", "platform": "Antigravity", "mode": "Unified"}

@router.get("/model")
async def fetch_model():
    """Returns the latest global model weights and metadata."""
    try:
        model_info = await get_latest_model()
        return model_info
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/submit-update")
async def submit_weight_update(submission: UpdateSubmission):
    """
    Unified entry point for weight submissions.
    Processes the update asynchronously and returns the status.
    """
    try:
        # We now process the update immediately to provide feedback on rejection/acceptance
        result = await process_update(submission.client_id, submission.weights)
        return result
    except Exception as e:
        print(f"Error processing update: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
