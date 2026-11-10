"""Safe, non-destructive SQLite schema migration helper."""

from sqlalchemy import text
from sqlalchemy.engine import Engine
from app.core.logging import logger
from app.database.base import Base


def run_safe_migrations(db_engine: Engine) -> None:
    """
    Safely adds missing columns to existing SQLite tables without dropping
    or overwriting existing telemetry records.
    """
    Base.metadata.create_all(bind=db_engine)

    with db_engine.begin() as conn:
        # Check existing columns on water_readings
        rows = conn.execute(text("PRAGMA table_info(water_readings)")).fetchall()
        existing_cols = {row[1] for row in rows}

        if "tds_voltage" not in existing_cols:
            conn.execute(text("ALTER TABLE water_readings ADD COLUMN tds_voltage FLOAT"))
            logger.info("[Migration] Added 'tds_voltage' column to water_readings.")

        if "water_quality_mode" not in existing_cols:
            conn.execute(
                text(
                    "ALTER TABLE water_readings "
                    "ADD COLUMN water_quality_mode VARCHAR(32) NOT NULL DEFAULT 'drinking'"
                )
            )
            logger.info("[Migration] Added 'water_quality_mode' column to water_readings.")
