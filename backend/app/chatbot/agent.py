"""AI Water Quality Advisor agent implementation with LLM adapter and fallback domain engine."""

from typing import Dict, Any, Optional
from datetime import datetime
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging import logger
from app.models.chat_message import ChatMessageModel
from app.schemas.chat import ChatResponse
from app.chatbot.tools import WaterChatbotTools
from app.chatbot.llm_adapter import GeminiRESTAdapter, OpenAIRESTAdapter
from app.ml.insights import InsightsGenerator

SYSTEM_PROMPT = """You are AquaAdvisor, an expert AI Water Quality Consultant and IoT Systems Diagnostic Assistant.
You specialize in municipal and apartment drinking water analysis, EPA/WHO standards, sensor interpretation, and plumbing diagnostics.

Your system context:
- Physical Hardware: ESP32 IoT node monitoring municipal apartment water.
- Active Sensors: pH probe (GPIO34) and Optical Turbidity probe (GPIO32).
- TDS Sensor: Reserved for future hardware expansion (currently uninstalled / N/A).
- Reference Standards: EPA Secondary Drinking Water Regulations (pH 6.5-8.5, Turbidity <5.0 NTU, TDS <500 ppm).

Safety & Response Rules:
1. Base all advice strictly on physical and chemical engineering facts provided in the telemetry context.
2. CRITICAL SAFETY RULE: NEVER claim water is completely safe to drink solely based on basic pH and turbidity sensors. Biological pathogens (E. coli, viruses) and dissolved heavy metals require certified laboratory testing.
3. If turbidity spikes, suspect municipal main flushing, plumbing corrosion, or filter breakthrough.
4. When uncalibrated or pending calibration, explain that the sensor shows raw electrical voltage and advise buffer calibration.
5. Explain clearly that TDS is not yet physically installed and is not 0 ppm.
6. Provide concise, actionable advice for apartment residents.
"""


class WaterChatbotAgent:
    """Orchestrates multi-turn conversations, context retrieval, LLM generation, and fallback logic."""

    def __init__(self):
        self.system_prompt = SYSTEM_PROMPT

    def _get_llm_adapter(self):
        api_key = settings.LLM_API_KEY or settings.GEMINI_API_KEY
        provider = (settings.LLM_PROVIDER or "fallback").lower()

        if not api_key or api_key in ("YOUR_LLM_API_KEY", "YOUR_GEMINI_API_KEY", ""):
            return None

        if provider == "gemini":
            return GeminiRESTAdapter(api_key=api_key, model=settings.LLM_MODEL)
        elif provider == "openai":
            return OpenAIRESTAdapter(api_key=api_key, model=settings.LLM_MODEL)
        return None

    async def answer_query(
        self,
        query: str,
        db: Session,
        session_id: str = "default_session",
    ) -> ChatResponse:
        """Processes a resident or engineer inquiry with full telemetry context."""
        # 1. Retrieve current live context and ML insights
        current_status = WaterChatbotTools.get_current_water_status(db)
        history_24h = WaterChatbotTools.get_historical_metrics(db, hours=24)
        recent_alerts = WaterChatbotTools.get_recent_alerts(db, limit=3)
        ml_summary = InsightsGenerator.generate_summary(db, operating_mode=settings.DATA_MODE)

        context_payload = {
            "current_status": current_status,
            "history_24h": history_24h,
            "recent_alerts": recent_alerts,
            "ml_dominant_trend": ml_summary.dominant_trend,
            "ml_insights_count": len(ml_summary.insights),
            "operating_mode": settings.DATA_MODE,
        }

        # 2. Check if a valid hosted LLM adapter is configured
        adapter = self._get_llm_adapter()
        response_text: Optional[str] = None
        source = "fallback_rule_advisor"
        model_name = "fallback_rule_advisor"

        if adapter:
            prompt = (
                f"Current Water Telemetry Context:\n{current_status}\n\n"
                f"24-Hour Historical Statistics:\n{history_24h}\n\n"
                f"Recent Alerts:\n{recent_alerts}\n\n"
                f"User Question: {query}"
            )
            llm_text = await adapter.generate_response(prompt=prompt, system_prompt=self.system_prompt)
            if llm_text:
                response_text = llm_text
                source = f"{settings.LLM_PROVIDER.lower()}_llm"
                model_name = settings.LLM_MODEL
            else:
                logger.warning("[Chatbot] LLM provider failed to generate answer; degrading gracefully to rule-based engine.")

        # 3. If LLM not configured or failed, use the expert rule-based advisor
        if not response_text:
            response_text = self._domain_rule_based_response(query, current_status, history_24h, recent_alerts, ml_summary)
            source = "fallback_rule_advisor"
            model_name = "fallback_rule_advisor"

        # 4. Save message history to SQLite
        try:
            user_msg = ChatMessageModel(
                session_id=session_id,
                role="user",
                content=query,
                model_used=model_name,
                source=source,
            )
            bot_msg = ChatMessageModel(
                session_id=session_id,
                role="assistant",
                content=response_text,
                model_used=model_name,
                source=source,
            )
            db.add(user_msg)
            db.add(bot_msg)
            db.commit()
        except Exception as exc:
            logger.warning(f"[Chatbot] Could not persist chat record: {exc}")

        return ChatResponse(
            response=response_text,
            source=source,
            model_used=model_name,
            session_id=session_id,
            timestamp=datetime.utcnow(),
            context_used=context_payload,
            operating_mode=settings.DATA_MODE,
        )

    def _domain_rule_based_response(
        self,
        query: str,
        status: Dict[str, Any],
        history: Dict[str, Any],
        alerts: list,
        ml_summary: Any,
    ) -> str:
        """Domain rule-based response generator using actual database readings."""
        q = query.lower()

        # Is water safe to drink?
        if "safe" in q or "drink" in q or "potable" in q:
            return (
                "**Drinking Water Safety Guidance:**\n"
                "While current sensors monitor physical parameters (pH and turbidity), "
                "**normal readings DO NOT prove water is microbiologically safe to drink**. "
                "Chemical toxins (lead, arsenic) and biological pathogens (E. coli, coliform bacteria) "
                "require laboratory microbiological assays. If water has high turbidity (>5.0 NTU), an unusual odor, "
                "or discoloration, boil it or use bottled drinking water."
            )

        # What is current pH?
        elif "ph" in q and ("what" in q or "current" in q or "level" in q or "value" in q):
            ph = status.get("ph")
            ph_v = status.get("ph_voltage")
            is_cal = status.get("ph_calibrated")
            if ph is not None:
                eval_str = "Optimal (Normal)" if (6.5 <= ph <= 8.5) else "OUT OF RANGE"
                return (
                    f"**Current pH Level:** {ph:.2f} ({eval_str})\n"
                    f"- Signal Board Output: {ph_v} V\n"
                    f"- EPA Guideline: 6.5 to 8.5\n"
                    f"- Calibration Status: {'Calibrated' if is_cal else 'Pending Buffer Calibration'}"
                )
            else:
                return (
                    f"**Current pH:** Calibration Pending.\n"
                    f"- Measured Board Voltage: {ph_v} V\n"
                    "The sensor probe requires two-point calibration using standard pH 7.00 and pH 4.01 buffer solutions."
                )

        # Why is turbidity increasing?
        elif "turbid" in q and ("why" in q or "increase" in q or "rising" in q or "high" in q):
            turb = status.get("turbidity_ntu")
            return (
                f"**Turbidity Assessment:** Current level is {turb if turb is not None else 'N/A'} NTU.\n"
                "Rising turbidity typically occurs due to:\n"
                "1. **Municipal Water Main Flushing**: Sediment stirred up by street-level maintenance.\n"
                "2. **Apartment Piping Corrosion**: Iron rust or scale detachment inside aging building riser pipes.\n"
                "3. **Rooftop Storage Tank Disturbance**: Sediments shifting in residential header tanks.\n"
                "4. **Filter Exhaustion**: Sediment cartridge requires replacement if post-filter turbidity exceeds 1.0 NTU."
            )

        # What does TDS measure?
        elif "tds" in q:
            tds = status.get("tds_ppm")
            return (
                "**Total Dissolved Solids (TDS) Status:**\n"
                f"- Current Value: {tds if tds is not None else 'N/A (Sensor Not Installed)'}\n"
                "- **Measurement Principle**: TDS measures total dissolved mineral ions (calcium, magnesium, chlorides, sulfates) in parts per million (ppm).\n"
                "- **Hardware Note**: In this system, GPIO 35 is reserved for future TDS expansion. The system reports N/A and strictly avoids false zero readings."
            )

        # What does current warning mean / explain last alert?
        elif "warning" in q or "alert" in q or "critical" in q:
            if alerts:
                last_alert = alerts[0]
                return (
                    f"**Active Alert Analysis:**\n"
                    f"- Title: **{last_alert.get('title')}**\n"
                    f"- Severity: Level {last_alert.get('severity')}\n"
                    f"- Details: {last_alert.get('message')}\n"
                    f"- Timestamp: {last_alert.get('timestamp')}\n"
                    "Recommended action: Inspect physical filter cartridges, verify electrical connections, and check if water discoloration is visible from the faucet."
                )
            else:
                return "✅ **No Active Alerts**: All monitored water quality parameters and hardware boundaries are currently normal."

        # Show trends / historical status
        elif "trend" in q or "history" in q or "average" in q:
            avg_ph = history.get("ph_average")
            avg_turb = history.get("turbidity_average")
            dominant_trend = ml_summary.dominant_trend if ml_summary else "STABLE"
            return (
                f"**24-Hour Water Quality Trends:**\n"
                f"- Average pH: {avg_ph if avg_ph else 'N/A'}\n"
                f"- Average Turbidity: {avg_turb if avg_turb else 'N/A'} NTU\n"
                f"- Dominant Trend: **{dominant_trend}**\n"
                f"- Samples Analyzed: {history.get('total_samples', 0)}\n"
                "Parameters indicate standard residential baseline behavior."
            )

        # Sensor fault / calibration
        elif "fault" in q or "calibrat" in q:
            h_code = status.get("health_code", "0x0000")
            h_sum = status.get("health_summary", "OPERATIONAL")
            return (
                f"**Sensor Health & Calibration Report:**\n"
                f"- Health Summary: **{h_sum}** (Code: {h_code})\n"
                f"- pH Calibrated: {'Yes' if status.get('ph_calibrated') else 'Pending (Buffer calibration needed)'}\n"
                f"- Turbidity Calibrated: {'Yes' if status.get('turbidity_calibrated') else 'Pending (0 NTU reference needed)'}\n"
                f"- TDS Installed: No (Reserved on GPIO 35)\n"
                "If the system reports a sensor fault, check breadboard common ground wiring and verify divider voltages with a multimeter."
            )

        # Default overview response
        else:
            ph = status.get("ph")
            turb = status.get("turbidity_ntu")
            tds = status.get("tds_ppm")
            mode = status.get("operating_mode", "real").upper()
            return (
                f"**AquaAdvisor Assistant [{mode} MODE]:**\n"
                f"- pH: {ph if ph is not None else 'Cal Pend'}\n"
                f"- Turbidity: {turb if turb is not None else 'Cal Pend'} NTU\n"
                f"- TDS: {tds if tds is not None else 'N/A (Uninstalled)'}\n"
                f"- Status: {status.get('health_summary', 'NORMAL')}\n\n"
                "You can ask me questions such as:\n"
                "- *'What is the current pH?'*\n"
                "- *'Why is turbidity increasing?'*\n"
                "- *'What does the current warning mean?'*\n"
                "- *'Is the water safe to drink?'*\n"
                "- *'Show me recent water quality trends.'*"
            )
