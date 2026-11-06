"""Application settings and runtime environment configuration."""

import os
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = "Smart Apartment Water Quality Monitor"
    VERSION: str = "1.0.0-phase1"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True

    # Database
    DATABASE_URL: str = "sqlite:///./water_quality.db"

    # ThingSpeak Telemetry Settings (Phase 2 Ingestion)
    THINGSPEAK_CHANNEL_ID: str = "0"
    THINGSPEAK_READ_API_KEY: Optional[str] = None
    THINGSPEAK_FETCH_INTERVAL_SECONDS: int = 30

    # Sensor Guidelines (EPA / WHO Standards)
    THRESHOLD_PH_MIN: float = 6.5
    THRESHOLD_PH_MAX: float = 8.5
    THRESHOLD_TURBIDITY_NTU_MAX: float = 5.0
    THRESHOLD_TDS_PPM_MAX: float = 500.0

    # Electrical Invariant Thresholds
    ADC_SAFE_VOLTAGE_MAX: float = 3.05
    VOLTAGE_DIVIDER_RATIO: float = 0.40
    VOLTAGE_RECONSTRUCT_FACTOR: float = 2.50

    # AI Chatbot (Phase 2)
    GEMINI_API_KEY: Optional[str] = None
    AI_MODEL_NAME: str = "gemini-2.5-flash"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )


settings = Settings()
