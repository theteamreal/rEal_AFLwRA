"""
FastAPI Application — Phase 1
-------------------------------
Single FastAPI instance with lifespan that starts the aggregation worker.
The ASGI router in asgi.py mounts this at /api/.
"""

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from main.api.endpoints import router

logger = logging.getLogger("fedguard.app")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start the background aggregation worker when the server starts up."""
    from main.api.aggregator import aggregation_worker
    task = asyncio.create_task(aggregation_worker())
    logger.info("🟢 FedGuard server online — aggregation worker running")
    yield
    # Graceful shutdown
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    logger.info("🔴 FedGuard server shutting down")


api_app = FastAPI(
    title="FedGuard Network API",
    description="Real-Device Federated Learning System",
    version="1.0.0",
    lifespan=lifespan,
    root_path="/api",   # Because Django mounts us at /api
    docs_url="/docs",
    redoc_url="/redoc",
)

# Allow all origins during LAN demo (clients connect from different IPs)
api_app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# Register all endpoint routes
api_app.include_router(router)
