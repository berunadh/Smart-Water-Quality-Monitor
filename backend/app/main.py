"""FastAPI main application entrypoint."""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.logging import logger
from app.database.session import engine
from app.database.base import Base
from app.api.v1.api import api_router

# Ensure all models are imported before creating tables
import app.models  # noqa: F401


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Ensure database schema exists
    logger.info(f"Starting {settings.PROJECT_NAME} v{settings.VERSION} [{settings.ENVIRONMENT}]")
    Base.metadata.create_all(bind=engine)
    logger.info("Database schema initialized.")
    yield
    # Shutdown
    logger.info("Application shutting down.")


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description=(
        "Production-grade REST API backend for the Smart Apartment Water Quality Monitor. "
        "Provides sensor data validation, ThingSpeak cloud ingestion, machine learning "
        "anomaly detection, and AI water quality advisory services."
    ),
    lifespan=lifespan,
)

# CORS configuration for Phase 3 React frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Restrict to frontend origin in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount API v1 router
app.include_router(api_router, prefix="/api/v1")


@app.get("/", tags=["Root"])
def read_root():
    return {
        "project": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "status": "online",
        "docs_url": "/docs",
        "health_check": "/api/v1/health",
    }
