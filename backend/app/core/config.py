"""Application settings and runtime environment configuration for Phase 2."""

import os
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = "Smart Apartment Water Quality Monitor"
    VERSION: str = "2.0.0-phase2"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True

    # Operating Mode: "demo" (simulated realistic streams) or "real" (ThingSpeak cloud)
    DATA_MODE: str = "demo"
    DEVICE_ID: str = "esp32-water-monitor-01"

    # Database
    DATABASE_URL: str = "sqlite:///./water_quality.db"

    # ThingSpeak Cloud Telemetry Settings
    THINGSPEAK_CHANNEL_ID: str = "0"
    THINGSPEAK_READ_API_KEY: Optional[str] = None
    POLL_INTERVAL_SECONDS: int = 20

    # Sensor Guidelines (EPA / WHO Standards)
    THRESHOLD_PH_MIN: float = 6.5
    THRESHOLD_PH_MAX: float = 8.5
    THRESHOLD_TURBIDITY_NTU_MAX: float = 5.0
    THRESHOLD_TDS_PPM_MAX: float = 500.0

    # Electrical Invariant Thresholds
    ADC_SAFE_VOLTAGE_MAX: float = 3.05
    VOLTAGE_DIVIDER_RATIO: float = 0.40
    VOLTAGE_RECONSTRUCT_FACTOR: float = 2.50

    # Machine Learning Settings
    ML_MODEL_DIR: str = os.path.join(os.path.dirname(os.path.dirname(__file__)), "ml", "models")
    ML_CONTAMINATION_RATE: float = 0.05
    ML_ZSCORE_THRESHOLD: float = 3.0

    # AI Chatbot & LLM Settings
    LLM_PROVIDER: str = "fallback"  # Options: "gemini", "openai", "fallback"
    LLM_MODEL: str = "gemini-3.1-flash-lite"
    LLM_API_KEY: Optional[str] = None
    GEMINI_API_KEY: Optional[str] = None
    GOOGLE_API_KEY: Optional[str] = None
    LLM_REQUEST_TIMEOUT: float = 20.0

    model_config = SettingsConfigDict(
        env_file=(".env", "backend/.env", "../.env"),
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )


settings = Settings()
