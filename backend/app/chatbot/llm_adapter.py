"""Provider-agnostic LLM adapter with resilient HTTP REST implementations."""

import re
import httpx
from abc import ABC, abstractmethod
from typing import Optional, Tuple, List
from app.core.config import settings
from app.core.logging import logger

ACTIVE_GEMINI_FALLBACK_MODELS = [
    "gemini-3.1-flash-lite",
    "gemini-3.5-flash-lite",
    "gemini-3.5-flash",
    "gemini-3.8-flash",
]


class BaseLLMAdapter(ABC):
    @abstractmethod
    async def generate_response(
        self, prompt: str, system_prompt: str
    ) -> Tuple[Optional[str], Optional[str], str]:
        """
        Generates text response from LLM provider.
        Returns: (generated_text, error_reason_if_failed, model_used)
        """
        pass


def _mask_sensitive(text: str, secret: Optional[str]) -> str:
    """Safely scrubs API key from logs or error messages."""
    if not text:
        return ""
    if secret and len(secret) > 6 and secret in text:
        text = text.replace(secret, "[REDACTED_API_KEY]")
    # Also scrub standard pattern
    text = re.sub(r'key=[A-Za-z0-9_\-\.]{10,}', 'key=[REDACTED]', text)
    return text


class GeminiRESTAdapter(BaseLLMAdapter):
    """
    Direct REST integration with Google Gemini API.
    Supports Google AI Studio Interactions API with automated fallback to generateContent
    and graceful adaptation if deprecated/retired model names are configured.
    """

    def __init__(
        self,
        api_key: str,
        model: Optional[str] = None,
        timeout: Optional[float] = None,
    ):
        self.api_key = api_key.strip() if api_key else ""
        self.configured_model = (model or settings.LLM_MODEL or "gemini-3.1-flash-lite").strip()
        self.timeout = timeout or getattr(settings, "LLM_REQUEST_TIMEOUT", 20.0)

    def _extract_interaction_text(self, data: dict) -> Optional[str]:
        """Parses output text from Gemini Interactions API response."""
        # 1. Check steps for model_output
        for step in reversed(data.get("steps", [])):
            if step.get("type") == "model_output":
                content = step.get("content", [])
                text_parts = [c.get("text", "") for c in content if c.get("type") == "text"]
                if text_parts:
                    return "".join(text_parts).strip()

        # 2. Check output_text or direct outputs
        if "output_text" in data and isinstance(data["output_text"], str):
            return data["output_text"].strip()

        outputs = data.get("outputs", [])
        if outputs and isinstance(outputs, list):
            first_out = outputs[0]
            if isinstance(first_out, dict) and "text" in first_out:
                return first_out["text"].strip()

        return None

    def _extract_generate_content_text(self, data: dict) -> Optional[str]:
        """Parses output text from standard generateContent response."""
        candidates = data.get("candidates", [])
        if candidates and isinstance(candidates, list):
            content = candidates[0].get("content", {})
            parts = content.get("parts", [])
            text_parts = [p.get("text", "") for p in parts if "text" in p]
            if text_parts:
                return "".join(text_parts).strip()
        return None

    def _classify_http_error(self, status_code: int, error_body: str) -> str:
        """Classifies HTTP error into human-readable, safe status."""
        body_lower = error_body.lower()
        if status_code in (401, 403) or "api_key_invalid" in body_lower or "invalid api key" in body_lower:
            return "INVALID_API_KEY"
        if status_code == 429 or "quota" in body_lower or "resource_exhausted" in body_lower:
            return "QUOTA_EXCEEDED"
        if status_code == 404 or "not found" in body_lower or "no longer available" in body_lower:
            return "MODEL_DEPRECATED_OR_NOT_FOUND"
        return f"HTTP_{status_code}"

    async def _call_interactions_api(
        self, client: httpx.AsyncClient, model_name: str, prompt: str, system_prompt: str
    ) -> Tuple[Optional[str], Optional[str]]:
        """Calls https://generativelanguage.googleapis.com/v1beta/interactions."""
        endpoint = "https://generativelanguage.googleapis.com/v1beta/interactions"
        headers = {
            "Content-Type": "application/json",
            "x-goog-api-key": self.api_key,
        }
        
        full_input = f"System Instructions:\n{system_prompt}\n\nUser Inquiry:\n{prompt}"
        payload = {
            "model": model_name,
            "input": full_input,
        }

        res = await client.post(endpoint, json=payload, headers=headers)
        if res.status_code == 200:
            text = self._extract_interaction_text(res.json())
            if text:
                return text, None
            return None, "EMPTY_MODEL_OUTPUT"
        
        err_type = self._classify_http_error(res.status_code, res.text)
        return None, err_type

    async def _call_generate_content_api(
        self, client: httpx.AsyncClient, model_name: str, prompt: str, system_prompt: str
    ) -> Tuple[Optional[str], Optional[str]]:
        """Calls https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent."""
        endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent"
        headers = {"Content-Type": "application/json"}
        params = {"key": self.api_key}
        payload = {
            "system_instruction": {"parts": [{"text": system_prompt}]},
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.3, "maxOutputTokens": 800},
        }

        res = await client.post(endpoint, params=params, json=payload, headers=headers)
        if res.status_code == 200:
            text = self._extract_generate_content_text(res.json())
            if text:
                return text, None
            return None, "EMPTY_MODEL_OUTPUT"

        err_type = self._classify_http_error(res.status_code, res.text)
        return None, err_type

    async def generate_response(
        self, prompt: str, system_prompt: str
    ) -> Tuple[Optional[str], Optional[str], str]:
        """
        Executes generation with automatic model adaptation and fallback hierarchy.
        Returns: (text, error_reason, model_used)
        """
        if not self.api_key:
            return None, "MISSING_API_KEY", self.configured_model

        # Build candidate models list: start with configured model, then active fallbacks
        models_to_try: List[str] = [self.configured_model]
        for m in ACTIVE_GEMINI_FALLBACK_MODELS:
            if m not in models_to_try:
                models_to_try.append(m)

        last_error = "UNKNOWN_ERROR"
        active_model = self.configured_model

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                for idx, model in enumerate(models_to_try):
                    active_model = model

                    # 1. Try Interactions API first
                    try:
                        text, err = await self._call_interactions_api(
                            client, model_name=model, prompt=prompt, system_prompt=system_prompt
                        )
                        if text:
                            if idx > 0:
                                logger.info(
                                    f"[GeminiAdapter] Configured model '{self.configured_model}' was unavailable; "
                                    f"successfully adapted to active model '{active_model}'."
                                )
                            return text, None, active_model
                        last_error = err or "INTERACTIONS_API_ERROR"
                    except httpx.TimeoutException:
                        logger.warning(f"[GeminiAdapter] Interactions API timed out for model {model}")
                        last_error = "TIMEOUT"
                    except Exception as e:
                        logger.warning(f"[GeminiAdapter] Interactions API error for {model}: {_mask_sensitive(str(e), self.api_key)}")
                        last_error = "NETWORK_ERROR"

                    # 2. Try generateContent endpoint as fallback for this model
                    try:
                        text, err = await self._call_generate_content_api(
                            client, model_name=model, prompt=prompt, system_prompt=system_prompt
                        )
                        if text:
                            if idx > 0:
                                logger.info(
                                    f"[GeminiAdapter] Successfully generated response via generateContent using '{active_model}'."
                                )
                            return text, None, active_model
                        last_error = err or last_error
                    except httpx.TimeoutException:
                        logger.warning(f"[GeminiAdapter] generateContent timed out for model {model}")
                        last_error = "TIMEOUT"
                    except Exception as e:
                        logger.warning(f"[GeminiAdapter] generateContent error for {model}: {_mask_sensitive(str(e), self.api_key)}")
                        last_error = "NETWORK_ERROR"

                    # If error is invalid API key or quota exceeded, trying another model won't help
                    if last_error in ("INVALID_API_KEY", "QUOTA_EXCEEDED"):
                        break
                    logger.warning(f"[GeminiAdapter] Model '{model}' unavailable ({last_error}); trying fallback if available.")

            return None, last_error, active_model

        except Exception as exc:
            safe_msg = _mask_sensitive(str(exc), self.api_key)
            logger.warning(f"[GeminiAdapter] Unexpected execution error: {safe_msg}")
            return None, "UNEXPECTED_ERROR", active_model


class OpenAIRESTAdapter(BaseLLMAdapter):
    """Direct REST integration with OpenAI API."""

    def __init__(self, api_key: str, model: str = "gpt-4o-mini", timeout: float = 20.0):
        self.api_key = api_key.strip() if api_key else ""
        self.model = model
        self.endpoint = "https://api.openai.com/v1/chat/completions"
        self.timeout = timeout

    async def generate_response(
        self, prompt: str, system_prompt: str
    ) -> Tuple[Optional[str], Optional[str], str]:
        if not self.api_key:
            return None, "MISSING_API_KEY", self.model

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
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                res = await client.post(self.endpoint, json=payload, headers=headers)
                if res.status_code == 200:
                    data = res.json()
                    text = data["choices"][0]["message"]["content"].strip()
                    return text, None, self.model
                
                body_lower = res.text.lower()
                if res.status_code in (401, 403):
                    err_type = "INVALID_API_KEY"
                elif res.status_code == 429:
                    err_type = "QUOTA_EXCEEDED"
                else:
                    err_type = f"HTTP_{res.status_code}"
                return None, err_type, self.model
        except httpx.TimeoutException:
            return None, "TIMEOUT", self.model
        except Exception as exc:
            safe_err = _mask_sensitive(str(exc), self.api_key)
            logger.warning(f"[OpenAIAdapter] Network/API error: {safe_err}")
            return None, "NETWORK_ERROR", self.model
