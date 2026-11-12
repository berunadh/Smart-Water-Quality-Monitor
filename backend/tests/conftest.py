"""Global pytest configuration providing complete SQLite & ML artifact isolation."""

import os
import shutil
import tempfile
import pytest

_TEST_TEMP_DIR = None


def pytest_configure(config):
    """Redirect DATABASE_URL and ML_MODEL_DIR to a temporary directory before app imports."""
    global _TEST_TEMP_DIR
    _TEST_TEMP_DIR = tempfile.mkdtemp(prefix="hydrosense_pytest_")
    test_db_path = os.path.join(_TEST_TEMP_DIR, "test_water_quality.db")
    test_ml_dir = os.path.join(_TEST_TEMP_DIR, "ml_models")
    os.makedirs(test_ml_dir, exist_ok=True)

    os.environ["DATABASE_URL"] = f"sqlite:///{test_db_path}"
    os.environ["DISABLE_BACKGROUND_SYNC"] = "1"

    from app.core.config import settings
    settings.DATABASE_URL = f"sqlite:///{test_db_path}"
    settings.ML_MODEL_DIR = test_ml_dir


def pytest_unconfigure(config):
    """Remove temporary test directory after pytest session completes."""
    global _TEST_TEMP_DIR
    if _TEST_TEMP_DIR and os.path.exists(_TEST_TEMP_DIR):
        shutil.rmtree(_TEST_TEMP_DIR, ignore_errors=True)
        _TEST_TEMP_DIR = None


@pytest.fixture
def isolated_app_db():
    """Clears rows inside the temporary test SQLite database for deterministic endpoint tests."""
    from app.database.session import engine, SessionLocal
    from app.database.migrations import run_safe_migrations
    from app.models.water_reading import WaterReadingModel
    from app.models.alert_log import AlertLogModel
    from app.models.calibration import CalibrationRecordModel
    from app.models.chat_message import ChatMessageModel
    from app.models.water_quality_config import WaterQualityConfigModel

    run_safe_migrations(engine)
    db = SessionLocal()
    try:
        db.query(WaterReadingModel).delete()
        db.query(AlertLogModel).delete()
        db.query(CalibrationRecordModel).delete()
        db.query(ChatMessageModel).delete()
        db.query(WaterQualityConfigModel).delete()
        db.commit()
        yield db
    finally:
        db.close()
