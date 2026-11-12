"""FastAPI main application entrypoint for Phase 2."""

import asyncio
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.logging import logger
from app.database.session import engine, SessionLocal
from app.database.base import Base
from app.database.migrations import run_safe_migrations
from app.api.routes import api_router
from app.services.demo_service import DemoService
from app.services.mode_service import ModeService
from app.services.thingspeak_service import ThingSpeakService
from app.ml.trainer import ModelTrainer

# Ensure all models are imported before creating tables
import app.models  # noqa: F401

# Ensure SQLite schema exists and run safe column migrations upon import
run_safe_migrations(engine)


async def _thingspeak_poll_loop():
    """Periodically synchronizes ThingSpeak feeds into SQLite in real mode."""
    poll_interval = max(15, int(getattr(settings, "POLL_INTERVAL_SECONDS", 20)))
    while True:
        try:
            db = SessionLocal()
            try:
                res = await ThingSpeakService.sync_latest_to_db(db, results=50)
                if res and res.new_records_saved > 0:
                    logger.info(
                        f"[AutoSync] Synced {res.new_records_saved} new ThingSpeak entries "
                        f"(latest entry_id={res.latest_entry_id})."
                    )
            finally:
                db.close()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning(f"[AutoSync] Periodic ThingSpeak sync error: {exc}")
        await asyncio.sleep(poll_interval)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup Initialization
    logger.info(f"=== Starting {settings.PROJECT_NAME} v{settings.VERSION} [{settings.ENVIRONMENT}] ===")
    logger.info(f"[Config] Operating Mode: {settings.DATA_MODE.upper()}")
    
    # 1. Initialize & Migrate Database Schema
    run_safe_migrations(engine)
    logger.info("[Database] SQLite database schema initialized and migrated safely.")

    # Ensure persistent Water Quality Mode config exists
    db = SessionLocal()
    try:
        ModeService.get_or_create_config(db)
        if settings.DATA_MODE == "demo":
            DemoService.seed_demo_history(db, count=60)
    finally:
        db.close()

    # 3. Ensure Baseline ML Model Exists
    try:
        ModelTrainer.train_baseline_model()
    except Exception as exc:
        logger.warning(f"[ML] Baseline model initialization note: {exc}")

    # 4. Start automatic ThingSpeak periodic polling in real mode (never under pytest)
    poll_task = None
    channel_id = str(getattr(settings, "THINGSPEAK_CHANNEL_ID", "0"))
    disable_sync = (
        os.environ.get("DISABLE_BACKGROUND_SYNC") == "1"
        or bool(os.environ.get("PYTEST_CURRENT_TEST"))
    )
    if settings.DATA_MODE == "real" and channel_id not in ("", "0", "YOUR_CHANNEL_ID") and not disable_sync:
        poll_task = asyncio.create_task(_thingspeak_poll_loop())
        logger.info(f"[AutoSync] Started ThingSpeak Channel {channel_id} background sync every {max(15, int(settings.POLL_INTERVAL_SECONDS))}s.")

    yield

    if poll_task is not None:
        poll_task.cancel()
        try:
            await poll_task
        except asyncio.CancelledError:
            pass

    # Shutdown
    logger.info("Application shutting down.")


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description=(
        "Production-grade REST API backend for the Smart Apartment Water Quality Monitor. "
        "Provides real-time sensor ingestion, ThingSpeak cloud synchronization, robust "
        "machine learning anomaly detection, trend drift analysis, and an AI Water Advisor chatbot."
    ),
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS configuration for Phase 3 React frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Restrict to frontend origin in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount primary API router under /api as specified
app.include_router(api_router, prefix="/api")

# Mount /api/v1 alias for backwards compatibility
app.include_router(api_router, prefix="/api/v1")


@app.get("/", tags=["Root"])
def read_root():
    return {
        "project": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "operating_mode": settings.DATA_MODE,
        "status": "online",
        "docs_url": "/docs",
        "health_check": "/api/health",
        "system_status": "/api/system/status",
        "latest_readings": "/api/readings/latest",
        "ml_summary": "/api/ml/summary",
        "chat_endpoint": "/api/chat",
    }
