"""Comprehensive Unit and Integration tests for the AquaAdvisor AI Chatbot."""

import pytest
import httpx
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.base import Base
from app.core.config import settings
from app.chatbot.agent import WaterChatbotAgent
from app.chatbot.tools import WaterChatbotTools
from app.chatbot.llm_adapter import GeminiRESTAdapter, BaseLLMAdapter
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


# ==============================================================================
# 1. GEMINI ADAPTER UNIT TESTS (MOCKED)
# ==============================================================================

def test_gemini_adapter_initialization():
    """Gemini adapter initializes with configured model and safe parameters."""
    adapter = GeminiRESTAdapter(api_key="test_key_12345", model="gemini-3.1-flash-lite")
    assert adapter.api_key == "test_key_12345"
    assert adapter.configured_model == "gemini-3.1-flash-lite"
    assert adapter.timeout == 20.0


def test_gemini_interactions_response_extraction():
    """Correctly extracts text from Interactions API response payload."""
    adapter = GeminiRESTAdapter(api_key="test_key")
    sample_interactions_payload = {
        "id": "v1_test_interaction",
        "status": "completed",
        "steps": [
            {"type": "thought", "signature": "sig123"},
            {
                "type": "model_output",
                "content": [{"type": "text", "text": "Water turbidity is currently normal at 1.8 NTU."}],
            },
        ],
    }
    extracted = adapter._extract_interaction_text(sample_interactions_payload)
    assert extracted == "Water turbidity is currently normal at 1.8 NTU."


def test_gemini_generate_content_extraction():
    """Correctly extracts text from legacy generateContent payload."""
    adapter = GeminiRESTAdapter(api_key="test_key")
    sample_payload = {
        "candidates": [
            {
                "content": {
                    "parts": [{"text": "pH is currently 7.35, within safe limits."}]
                }
            }
        ]
    }
    extracted = adapter._extract_generate_content_text(sample_payload)
    assert extracted == "pH is currently 7.35, within safe limits."


@pytest.mark.asyncio
async def test_gemini_adapter_model_deprecated_auto_fallback(monkeypatch):
    """If configured model returns 404 (deprecated), adapter automatically falls back to active model."""
    adapter = GeminiRESTAdapter(api_key="test_key", model="gemini-2.5-flash")

    # Mock client where gemini-2.5-flash returns 404, but gemini-3.1-flash-lite returns 200
    async def mock_post(self, url, **kwargs):
        json_body = kwargs.get("json", {})
        model = json_body.get("model", "")
        if "gemini-2.5-flash" in str(url) or model == "gemini-2.5-flash":
            req = httpx.Request("POST", url)
            return httpx.Response(404, text='{"error":{"message":"model is no longer available"}}', request=req)
        else:
            req = httpx.Request("POST", url)
            return httpx.Response(
                200,
                json={
                    "steps": [
                        {"type": "model_output", "content": [{"type": "text", "text": "Active model response"}]}
                    ]
                },
                request=req,
            )

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    text, err, model_used = await adapter.generate_response(prompt="Hello", system_prompt="You are an AI.")
    assert text == "Active model response"
    assert err is None
    assert model_used in ("gemini-3.1-flash-lite", "gemini-3.5-flash")


@pytest.mark.asyncio
async def test_gemini_adapter_invalid_key_error(monkeypatch):
    """Invalid API key returns classified error and does not loop forever."""
    adapter = GeminiRESTAdapter(api_key="bad_key")

    async def mock_post(self, url, **kwargs):
        req = httpx.Request("POST", url)
        return httpx.Response(400, text='{"error":{"message":"API_KEY_INVALID"}}', request=req)

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    text, err, _ = await adapter.generate_response(prompt="Test", system_prompt="Sys")
    assert text is None
    assert err == "INVALID_API_KEY"


@pytest.mark.asyncio
async def test_gemini_adapter_quota_exceeded_error(monkeypatch):
    """Rate limit / quota error returns QUOTA_EXCEEDED."""
    adapter = GeminiRESTAdapter(api_key="valid_key")

    async def mock_post(self, url, **kwargs):
        req = httpx.Request("POST", url)
        return httpx.Response(429, text='{"error":{"message":"RESOURCE_EXHAUSTED"}}', request=req)

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    text, err, _ = await adapter.generate_response(prompt="Test", system_prompt="Sys")
    assert text is None
    assert err == "QUOTA_EXCEEDED"


@pytest.mark.asyncio
async def test_gemini_adapter_timeout_handling(monkeypatch):
    """Network timeout gracefully reports TIMEOUT."""
    adapter = GeminiRESTAdapter(api_key="valid_key")

    async def mock_post(self, url, **kwargs):
        raise httpx.ReadTimeout("Timeout connecting to Google API")

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    text, err, _ = await adapter.generate_response(prompt="Test", system_prompt="Sys")
    assert text is None
    assert err == "TIMEOUT"


# ==============================================================================
# 2. CHATBOT AGENT INTEGRATION & CONVERSATION TESTS
# ==============================================================================

@pytest.mark.asyncio
async def test_agent_with_gemini_success(chat_db, monkeypatch):
    """When Gemini succeeds, agent returns gemini_llm source and model badge."""
    class MockGemini(BaseLLMAdapter):
        async def generate_response(self, prompt: str, system_prompt: str):
            return "This is a real-time Gemini AI water response.", None, "gemini-3.1-flash-lite"

    agent = WaterChatbotAgent()
    monkeypatch.setattr(agent, "_get_llm_adapter", lambda: MockGemini())

    resp = await agent.answer_query("Is my water quality normal?", chat_db)
    assert resp.source == "gemini_llm"
    assert resp.model_used == "gemini-3.1-flash-lite"
    assert resp.response == "This is a real-time Gemini AI water response."
    assert resp.provider_status == "active"


@pytest.mark.asyncio
async def test_agent_conversation_history_follow_up(chat_db, monkeypatch):
    """Agent passes past conversation turns to LLM so follow-up questions resolve context."""
    received_prompts = []

    class MockGemini(BaseLLMAdapter):
        async def generate_response(self, prompt: str, system_prompt: str):
            received_prompts.append(prompt)
            return "Turbidity explanation response.", None, "gemini-3.1-flash-lite"

    agent = WaterChatbotAgent()
    monkeypatch.setattr(agent, "_get_llm_adapter", lambda: MockGemini())

    # Turn 1
    session_id = "test_multi_turn_001"
    await agent.answer_query("Why is my turbidity high?", chat_db, session_id=session_id)

    # Turn 2: Follow-up question
    await agent.answer_query("How can I fix it?", chat_db, session_id=session_id)

    assert len(received_prompts) == 2
    turn_2_prompt = received_prompts[1]
    # Verify that Turn 2's prompt contains the previous question from Turn 1!
    assert "Why is my turbidity high?" in turn_2_prompt
    assert "How can I fix it?" in turn_2_prompt


@pytest.mark.asyncio
async def test_agent_telemetry_grounding(chat_db, monkeypatch):
    """Agent injects active mode thresholds, all 3 sensors (including GPIO35 TDS), and ML stats into prompt."""
    captured_prompt = []

    class MockGemini(BaseLLMAdapter):
        async def generate_response(self, prompt: str, system_prompt: str):
            captured_prompt.append(prompt)
            return "Grounding response", None, "gemini-3.1-flash-lite"

    agent = WaterChatbotAgent()
    monkeypatch.setattr(agent, "_get_llm_adapter", lambda: MockGemini())

    await agent.answer_query("Summarize current sensor status", chat_db)
    assert len(captured_prompt) == 1
    prompt_text = captured_prompt[0]
    assert "ACTIVE WATER QUALITY MODE & THRESHOLDS" in prompt_text
    assert "CURRENT SYSTEM TELEMETRY" in prompt_text
    assert "Calibrated pH" in prompt_text
    assert "Calibrated TDS" in prompt_text
    assert "GPIO35 Direct 3.3V" in prompt_text
    assert "24-HOUR HISTORICAL STATS & TRENDS" in prompt_text


@pytest.mark.asyncio
async def test_agent_missing_api_key_safe_fallback(chat_db, monkeypatch):
    """When API key is absent, agent safely falls back to domain rule engine without crashing."""
    agent = WaterChatbotAgent()
    monkeypatch.setattr(agent, "_resolve_api_key", lambda: None)

    resp = await agent.answer_query("Hello!", chat_db)
    assert resp.source == "fallback_rule_advisor"
    assert "AquaAdvisor" in resp.response
    assert "pH" not in resp.response or "AquaAdvisor" in resp.response


@pytest.mark.asyncio
async def test_agent_drinking_safety_guardrail(chat_db, monkeypatch):
    """Rule engine fallback strictly warns that sensors do NOT prove water is potable."""
    agent = WaterChatbotAgent()
    monkeypatch.setattr(agent, "_get_llm_adapter", lambda: None)

    resp = await agent.answer_query("Is this water completely safe to drink?", chat_db)
    assert "safe" in resp.response.lower()
    assert "not prove" in resp.response.lower() or "do not prove" in resp.response.lower()
    assert "pathogen" in resp.response.lower() or "laboratory" in resp.response.lower()


@pytest.mark.asyncio
async def test_agent_no_api_key_exposure_in_response(chat_db, monkeypatch):
    """Secret API key must never be exposed in ChatResponse, context, or logs."""
    secret = "AIzaSySecretTestKey999"
    class MockGemini(BaseLLMAdapter):
        async def generate_response(self, prompt: str, system_prompt: str):
            return "Safe answer without keys.", None, "gemini-3.1-flash-lite"

    agent = WaterChatbotAgent()
    monkeypatch.setattr(agent, "_resolve_api_key", lambda: secret)
    monkeypatch.setattr(agent, "_get_llm_adapter", lambda: MockGemini())

    resp = await agent.answer_query("Test query", chat_db)
    resp_dict = resp.model_dump()
    resp_str = str(resp_dict)
    assert secret not in resp_str


def test_chatbot_status_method():
    """Chatbot status method reports configured provider without exposing key."""
    agent = WaterChatbotAgent()
    status = agent.get_provider_status()
    assert "configured_provider" in status
    assert "model" in status
    assert "api_key_configured" in status
    assert "status" in status
    assert "api_key" not in status  # Secret key is never exposed


# ==============================================================================
# 3. LIVE GEMINI API TEST (RUNS ONLY IF VALID KEY PRESENT)
# ==============================================================================

@pytest.mark.asyncio
async def test_live_gemini_api_when_configured(chat_db):
    """
    If a real local API key is configured in backend/.env, executes a live call
    to verify real Google Gemini API connectivity.
    """
    agent = WaterChatbotAgent()
    key = agent._resolve_api_key()

    if not key or len(key) < 15 or key.startswith("YOUR_"):
        pytest.skip("No real local Gemini API key configured in .env; skipping live network test.")

    resp = await agent.answer_query("Hello AquaAdvisor, what are you?", chat_db, session_id="live_test_session")
    
    # Must succeed with live Gemini model
    assert resp.source == "gemini_llm"
    assert resp.model_used is not None
    assert "gemini" in resp.model_used.lower()
    assert len(resp.response) > 20
    assert resp.provider_status == "active"
