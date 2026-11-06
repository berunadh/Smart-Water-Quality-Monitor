"""AI Water Quality Advisor agent implementation."""

from typing import Dict, Any, Optional
from sqlalchemy.orm import Session
from app.core.config import settings
from app.core.logging import logger
from .tools import WaterChatbotTools

SYSTEM_PROMPT = """You are AquaAdvisor, an expert AI Water Quality Consultant and IoT Systems Diagnostic Assistant.
You specialize in municipal and apartment drinking water analysis, EPA/WHO standards, sensor interpretation, and plumbing diagnostics.

Your system context:
- Physical Hardware: ESP32 IoT node monitoring municipal apartment water.
- Active Sensors: pH probe (GPIO34) and Optical Turbidity probe (GPIO32).
- TDS Sensor: Reserved for future hardware expansion (currently uninstalled / N/A).
- Reference Standards: EPA Secondary Drinking Water Regulations (pH 6.5-8.5, Turbidity <5.0 NTU, TDS <500 ppm).

Guidelines:
1. Always base your advice on physical and chemical engineering facts.
2. NEVER claim water is completely safe to drink solely based on basic pH and turbidity sensors, as biological microbes (e.g. bacteria, viruses) or heavy metals require laboratory testing.
3. If turbidity spikes, suspect pipe rust, distribution main flushing, or filter breakthrough.
4. When uncalibrated or pending calibration, advise the user to perform two-point buffer calibration.
5. Provide clear, concise, actionable advice for apartment residents.
"""


class WaterChatbotAgent:
    """Orchestrates LLM conversations, tool calls, and water quality diagnostics."""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or settings.GEMINI_API_KEY
        self.system_prompt = SYSTEM_PROMPT

    async def answer_query(self, query: str, db: Session) -> Dict[str, Any]:
        """Processes a resident or engineer inquiry."""
        # 1. Retrieve current live context using tools
        current_status = WaterChatbotTools.get_current_water_status(db)
        recent_alerts = WaterChatbotTools.get_recent_alerts(db, limit=3)

        # 2. In Phase 1 without an external Gemini API key set, provide intelligent rule-based domain reasoning:
        if not self.api_key:
            return self._domain_rule_based_response(query, current_status, recent_alerts)

        # In Phase 2, connect to Google Gemini API using google-genai SDK
        try:
            from google import genai
            client = genai.Client(api_key=self.api_key)
            prompt = f"{self.system_prompt}\n\nCurrent Water Telemetry Context:\n{current_status}\n\nRecent Alerts:\n{recent_alerts}\n\nUser Question: {query}"
            response = client.models.generate_content(
                model=settings.AI_MODEL_NAME,
                contents=prompt,
            )
            return {
                "response": response.text,
                "model": settings.AI_MODEL_NAME,
                "context_used": {"status": current_status, "alerts": recent_alerts},
            }
        except Exception as exc:
            logger.warning(f"[Chatbot] External LLM call failed ({exc}); falling back to domain logic.")
            return self._domain_rule_based_response(query, current_status, recent_alerts)

    def _domain_rule_based_response(
        self, query: str, status: Dict[str, Any], alerts: list
    ) -> Dict[str, Any]:
        """Provides expert domain responses using local rules and database state."""
        q = query.lower()

        if "status" in q or "current" in q or "how is" in q:
            ph = status.get("ph")
            turb = status.get("turbidity_ntu")
            tds = status.get("tds_ppm")
            msg = (
                f"**Current Apartment Water Status:**\n"
                f"- **pH Level**: {ph if ph is not None else 'Calibration Pending / Unavailable'}\n"
                f"- **Turbidity**: {turb if turb is not None else 'Calibration Pending / Unavailable'} NTU\n"
                f"- **TDS**: {tds if tds is not None else 'N/A (Sensor not installed)'}\n\n"
            )
            if status.get("alert_severity", 0) > 0:
                msg += "⚠️ **Active Alert**: Water parameters deviate from normal baselines. Check filtration system."
            else:
                msg += "✅ **Parameters Normal**: All monitored parameters are within configured thresholds."
            return {"response": msg, "source": "rule_based_advisor"}

        elif "safe" in q or "drink" in q:
            return {
                "response": (
                    "**Safety Notice:** While the current monitored parameters (pH and turbidity) give "
                    "insight into acidity and particulate clarity, they **do not test for microbiological pathogens "
                    "(e.g., E. coli, Giardia) or dissolved chemical toxins**. Never rely solely on hobby/college "
                    "sensors to certify drinking water safety. If water is cloudy (>5 NTU) or tastes unusual, boil it "
                    "or use certified bottled water."
                ),
                "source": "rule_based_advisor",
            }

        elif "ph" in q:
            info = WaterChatbotTools.explain_parameter_standards("ph")
            return {
                "response": (
                    f"**pH Guidance ({info['safe_range']}):**\n"
                    f"{info['health_implications']}\n"
                    f"Standards: {info['standards']}."
                ),
                "source": "rule_based_advisor",
            }

        elif "turb" in q or "cloudy" in q:
            info = WaterChatbotTools.explain_parameter_standards("turbidity")
            return {
                "response": (
                    f"**Turbidity Guidance ({info['safe_limit']}):**\n"
                    f"{info['health_implications']}\n"
                    f"Standards: {info['standards']}."
                ),
                "source": "rule_based_advisor",
            }

        elif "tds" in q:
            info = WaterChatbotTools.explain_parameter_standards("tds")
            return {
                "response": (
                    f"**TDS Guidance ({info['safe_limit']}):**\n"
                    f"{info['health_implications']}\n"
                    f"Note: In this monitor, the TDS sensor is reserved for future hardware installation."
                ),
                "source": "rule_based_advisor",
            }

        else:
            return {
                "response": (
                    "Hello! I am AquaAdvisor. I can assist you with your apartment water quality readings, "
                    "explain EPA/WHO thresholds for pH, turbidity, and TDS, or help troubleshoot sensor calibration. "
                    "Ask me: 'What is the current water status?', 'Is the water safe to drink?', or 'Why is turbidity high?'"
                ),
                "source": "rule_based_advisor",
            }
