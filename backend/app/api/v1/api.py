"""FastAPI v1 API router aggregation."""

from fastapi import APIRouter
from app.api.v1.endpoints import sensors, health, alerts, thingspeak, analytics, chatbot

api_router = APIRouter()

api_router.include_router(sensors.router, prefix="/sensors", tags=["Sensors"])
api_router.include_router(health.router, prefix="/health", tags=["Health & Diagnostics"])
api_router.include_router(alerts.router, prefix="/alerts", tags=["Alerts"])
api_router.include_router(thingspeak.router, prefix="/thingspeak", tags=["ThingSpeak Cloud"])
api_router.include_router(analytics.router, prefix="/analytics", tags=["ML & Analytics"])
api_router.include_router(chatbot.router, prefix="/chatbot", tags=["AI Advisor Chatbot"])
