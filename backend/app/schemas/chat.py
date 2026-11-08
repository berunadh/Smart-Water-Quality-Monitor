"""Pydantic schemas for the AI Water Advisor Chatbot."""

from datetime import datetime
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=1000, description="Resident or engineer query")
    session_id: Optional[str] = Field("default_session", description="Conversation session ID")


class ChatResponse(BaseModel):
    response: str
    source: str = Field(..., description="'gemini_llm', 'openai_llm', or 'fallback_rule_advisor'")
    model_used: Optional[str] = None
    session_id: str
    timestamp: datetime
    context_used: Dict[str, Any]
    operating_mode: str
    provider_status: Optional[str] = Field("active", description="Operational status or explanation if fallback engaged")


class ChatbotStatusResponse(BaseModel):
    configured_provider: str
    model: str
    api_key_configured: bool
    status: str
    details: str
