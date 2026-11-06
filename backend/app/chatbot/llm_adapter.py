"""Provider-agnostic LLM adapter with resilient HTTP REST implementations."""

import httpx
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any
from app.core.config import settings
from app.core.logging import logger


class BaseLLMAdapter(ABC):
    @abstractmethod
    async def generate_response(self, prompt: str, system_prompt: str) -> Optional[str]:
        pass


class GeminiRESTAdapter(BaseLLMAdapter):
    """Direct REST integration with Google Gemini API."""

    def __init__(self, api_key: str, model: str = "gemini-2.5-flash"):
        self.api_key = api_key
        self.model = model
        self.endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

    async def generate_response(self, prompt: str, system_prompt: str) -> Optional[str]:
        headers = {"Content-Type": "application/json"}
        params = {"key": self.api_key}
        payload = {
            "contents": [{"parts": [{"text": f"{system_prompt}\n\n{prompt}"}]}],
            "generationConfig": {"temperature": 0.3, "maxOutputTokens": 800},
        }

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                res = await client.post(self.endpoint, params=params, json=payload, headers=headers)
                if res.status_code == 200:
                    data = res.json()
                    candidates = data.get("candidates", [])
                    if candidates:
                        text = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                        return text.strip()
                logger.warning(f"[GeminiAdapter] API call returned HTTP {res.status_code}: {res.text}")
                return None
        except Exception as exc:
            logger.warning(f"[GeminiAdapter] Network/API error: {exc}")
            return None


class OpenAIRESTAdapter(BaseLLMAdapter):
    """Direct REST integration with OpenAI API."""

    def __init__(self, api_key: str, model: str = "gpt-4o-mini"):
        self.api_key = api_key
        self.model = model
        self.endpoint = "https://api.openai.com/v1/chat/completions"

    async def generate_response(self, prompt: str, system_prompt: str) -> Optional[str]:
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.3,
            "max_tokens": 800,
        }

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                res = await client.post(self.endpoint, json=payload, headers=headers)
                if res.status_code == 200:
                    data = res.json()
                    return data["choices"][0]["message"]["content"].strip()
                logger.warning(f"[OpenAIAdapter] API call returned HTTP {res.status_code}: {res.text}")
                return None
        except Exception as exc:
            logger.warning(f"[OpenAIAdapter] Network/API error: {exc}")
            return None
