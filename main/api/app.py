"""
Fedora API Application
---------------------------
FastAPI instance for robust asynchronous federated learning.
"""

import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from main.api.endpoints import router

logger = logging.getLogger("fedora.app")

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🟢 Fedora FL Server Online")
    yield
    logger.info("🔴 Fedora FL Server Shutting Down")

api_app = FastAPI(
    title="Fedora FL Platform",
    description="Privacy-Preserving Asynchronous Robust Federated Learning",
    version="2.2.0",
    lifespan=lifespan,
    root_path="/api",
)

api_app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

api_app.include_router(router)
