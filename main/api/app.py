"""
Antigravity API Application
---------------------------
FastAPI instance for robust asynchronous federated learning.
"""

import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from main.api.endpoints import router

logger = logging.getLogger("antigravity.app")

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🟢 Antigravity FL Server Online")
    yield
    logger.info("🔴 Antigravity FL Server Shutting Down")

api_app = FastAPI(
    title="Antigravity FL Platform",
    description="Privacy-Preserving Asynchronous Robust Federated Learning",
    version="2.0.0",
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
