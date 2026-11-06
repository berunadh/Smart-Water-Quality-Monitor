"""AI Chatbot Advisor API endpoints."""

from typing import Dict, Any
from fastapi import APIRouter, Depends, Body
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

from app.database.session import get_db
from app.chatbot.agent import WaterChatbotAgent

router = APIRouter()
agent = WaterChatbotAgent()


class ChatbotQueryRequest(BaseModel):
    query: str = Field(..., min_length=2, max_length=1000, description="User question or water concern")


@router.post("/query")
async def chat_with_advisor(
    request: ChatbotQueryRequest,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Interacts with the AI Water Quality Advisor."""
    response = await agent.answer_query(request.query, db)
    return response
