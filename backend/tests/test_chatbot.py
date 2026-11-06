"""Unit tests for the AI Water Quality Advisor Chatbot."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.base import Base
from app.chatbot.agent import WaterChatbotAgent
from app.chatbot.tools import WaterChatbotTools
from app.services.demo_service import DemoService


@pytest.fixture
def chat_db():
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        # Seed 10 records for context
        DemoService.seed_demo_history(session, count=10)
        yield session
    finally:
        session.close()


@pytest.mark.asyncio
async def test_chatbot_current_status_query(chat_db):
    """Chatbot answers status questions with real database context."""
    agent = WaterChatbotAgent()
    resp = await agent.answer_query("What is the current water status?", chat_db)

    assert resp.response is not None
    assert "pH" in resp.response
    assert "Turbidity" in resp.response
    assert resp.source == "fallback_rule_advisor"
    assert "current_status" in resp.context_used


@pytest.mark.asyncio
async def test_chatbot_drinking_safety_guardrail(chat_db):
    """Chatbot must NEVER claim water is completely safe based solely on basic sensors."""
    agent = WaterChatbotAgent()
    resp = await agent.answer_query("Is this water completely safe to drink?", chat_db)

    # Must include warning about microbes / laboratory testing
    assert "safe" in resp.response.lower()
    assert "pathogen" in resp.response.lower() or "microbiolog" in resp.response.lower() or "laboratory" in resp.response.lower()
    assert "DO NOT prove water is" in resp.response or "not prove" in resp.response.lower()


@pytest.mark.asyncio
async def test_chatbot_tds_explanation(chat_db):
    """Chatbot clarifies that TDS is uninstalled (reserved) and not 0 ppm."""
    agent = WaterChatbotAgent()
    resp = await agent.answer_query("What does TDS measure and what is our reading?", chat_db)

    assert "TDS" in resp.response
    assert "Reserved" in resp.response or "Not Installed" in resp.response or "N/A" in resp.response


@pytest.mark.asyncio
async def test_chatbot_turbidity_diagnostic(chat_db):
    """Chatbot explains realistic causes of rising turbidity."""
    agent = WaterChatbotAgent()
    resp = await agent.answer_query("Why is turbidity increasing?", chat_db)

    assert "Turbidity" in resp.response
    assert "Flushing" in resp.response or "Corrosion" in resp.response or "Tank" in resp.response


@pytest.mark.asyncio
async def test_chatbot_llm_failure_graceful_fallback(chat_db, monkeypatch):
    """If hosted LLM provider fails (e.g. timeout/HTTP 500), agent must degrade cleanly to fallback."""
    from app.chatbot.llm_adapter import BaseLLMAdapter

    class FailingAdapter(BaseLLMAdapter):
        async def generate_response(self, prompt: str, system_prompt: str):
            return None  # Simulates provider failure or HTTP 500

    agent = WaterChatbotAgent()
    monkeypatch.setattr(agent, "_get_llm_adapter", lambda: FailingAdapter())

    resp = await agent.answer_query("What is the current pH level?", chat_db)
    assert resp.response is not None
    assert resp.source == "fallback_rule_advisor"
    assert "pH" in resp.response
