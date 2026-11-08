"""AI Water Quality Advisor agent implementation with LLM adapter, conversation history, and fallback domain engine."""

import os
from typing import Dict, Any, Optional, List
from datetime import datetime
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging import logger
from app.models.chat_message import ChatMessageModel
from app.schemas.chat import ChatResponse
from app.chatbot.tools import WaterChatbotTools
from app.chatbot.llm_adapter import GeminiRESTAdapter, OpenAIRESTAdapter
from app.ml.insights import InsightsGenerator

SYSTEM_PROMPT = """You are AquaAdvisor, an expert AI Water Quality Consultant and IoT Systems Diagnostic Assistant for the HydroSense platform.
You specialize in municipal and apartment drinking water analysis, EPA/WHO standards, sensor interpretation, and plumbing diagnostics.

Your system context:
- Physical Hardware: ESP32 IoT node monitoring apartment water supply.
- Active Physical Sensors: E201-C pH probe (GPIO34) and Optical Turbidity probe (GPIO32) with 15kΩ/10kΩ voltage dividers (÷2.5 step-down).
- TDS Sensor: Reserved for future hardware expansion on GPIO35. It is currently UNINSTALLED and strictly reported as NULL / N/A (NEVER 0 ppm).
- Reference Standards: EPA Secondary Drinking Water Regulations (pH 6.5-8.5, Turbidity <5.0 NTU, TDS <500 ppm) and WHO Drinking Water Guidelines.

Conversational & Response Directives:
1. Conversational Style: Be polite, knowledgeable, clear, and articulate. Respond naturally to general greetings, project inquiries, and casual dialogue without dumping unnecessary raw sensor tables unless asked.
2. Follow-Up Understanding: Always track conversational context and resolve pronouns or follow-up references (e.g. if the user asks "why is it high?" followed by "how can I fix it?", answer about resolving the specific parameter previously discussed).
3. Grounding: When answering telemetry or diagnosis questions, base your analysis strictly on the provided real-time readings, historical statistics, active alerts, and ML insights.
4. CRITICAL SAFETY INVARIANT: NEVER declare water completely safe to drink based solely on basic physicochemical sensors (pH, turbidity, TDS). Physical sensors cannot detect microbiological pathogens (E. coli, Giardia, norovirus) or heavy metals (lead, arsenic). State clearly that certified laboratory testing is required for potable water certification.
5. Operating Mode Distinction: If the system is in DEMO MODE, clearly explain that telemetry is currently simulated for software and alarm verification, and does not reflect actual tap water until switched to REAL hardware mode.
6. Sensor Status: If a sensor is uncalibrated or pending calibration, explain that it displays raw electrical voltages and recommend standard buffer calibration (pH 7.00/4.01).
7. Missing TDS: Never treat missing TDS as zero. Explain that GPIO35 is reserved for drop-in hardware installation upon delivery.
"""


class WaterChatbotAgent:
    """Orchestrates multi-turn conversations, context retrieval, LLM generation, and fallback logic."""

    def __init__(self):
        self.system_prompt = SYSTEM_PROMPT

    def _resolve_api_key(self) -> Optional[str]:
        """Resolves API key from config settings or environment variables."""
        key = (
            settings.LLM_API_KEY
            or settings.GEMINI_API_KEY
            or settings.GOOGLE_API_KEY
            or os.getenv("LLM_API_KEY")
            or os.getenv("GEMINI_API_KEY")
            or os.getenv("GOOGLE_API_KEY")
        )
        if not key or key.strip() in (
            "YOUR_LLM_API_KEY",
            "YOUR_GEMINI_API_KEY",
            "MY_ACTUAL_GEMINI_API_KEY",
            "",
        ):
            return None
        return key.strip()

    def get_provider_status(self) -> Dict[str, Any]:
        """Returns safe provider operational status for diagnostics and UI."""
        provider = (settings.LLM_PROVIDER or "fallback").lower()
        api_key = self._resolve_api_key()
        has_key = bool(api_key and len(api_key) > 6)

        if provider == "gemini":
            status = "ready" if has_key else "fallback_active"
            details = "Gemini AI online and configured" if has_key else "Missing or placeholder Gemini API key; using rule engine"
        elif provider == "openai":
            status = "ready" if has_key else "fallback_active"
            details = "OpenAI model configured" if has_key else "Missing OpenAI API key; using rule engine"
        else:
            status = "fallback_active"
            details = "Deterministic rule engine active (local offline mode)"

        return {
            "configured_provider": provider,
            "model": settings.LLM_MODEL,
            "api_key_configured": has_key,
            "status": status,
            "details": details,
        }

    def _get_llm_adapter(self):
        """Constructs appropriate LLM adapter based on configuration."""
        provider = (settings.LLM_PROVIDER or "fallback").lower()
        api_key = self._resolve_api_key()

        if not api_key:
            return None

        if provider == "gemini":
            return GeminiRESTAdapter(api_key=api_key, model=settings.LLM_MODEL)
        elif provider == "openai":
            return OpenAIRESTAdapter(api_key=api_key, model=settings.LLM_MODEL)
        return None

    def _format_context_prompt(
        self,
        query: str,
        current_status: Dict[str, Any],
        history_24h: Dict[str, Any],
        recent_alerts: List[Dict[str, Any]],
        ml_summary: Any,
        chat_history: List[Dict[str, str]],
    ) -> str:
        """Formats grounding context and recent conversation history into structured prompt."""
        mode_str = "DEMO / SIMULATED TELEMETRY" if settings.DATA_MODE == "demo" else "REAL ESP32 HARDWARE STREAM"
        
        lines = [
            f"=== CURRENT SYSTEM TELEMETRY [{mode_str}] ===",
            f"- Device ID: {current_status.get('device_id', 'esp32-water-monitor-01')}",
            f"- Data Source: {current_status.get('data_source', 'simulated')}",
            f"- Calibrated pH: {current_status.get('ph', 'Uncalibrated / Pending')}",
            f"- pH Sensor Voltage: {current_status.get('ph_voltage', 'N/A')} V (GPIO34, Divider ÷2.5)",
            f"- Calibrated Turbidity: {current_status.get('turbidity_ntu', 'Uncalibrated / Pending')} NTU",
            f"- Turbidity Voltage: {current_status.get('turbidity_voltage', 'N/A')} V (GPIO32, Divider ÷2.5)",
            f"- TDS Sensor: {current_status.get('tds_ppm') if current_status.get('tds_ppm') is not None else 'NULL (Uninstalled, Reserved on GPIO35)'}",
            f"- Hardware Health Summary: {current_status.get('health_summary', 'OPERATIONAL')} (Code: {current_status.get('health_code', '0x0000')})",
            f"- Electrical Safety Status: {'NORMAL' if current_status.get('is_valid', True) else 'VOLTAGE HAZARD / OUT OF BOUNDS'}",
            f"- Alert Level: Severity {current_status.get('alert_severity', 0)} ({current_status.get('alert_message', 'NORMAL')})",
            "",
            "=== 24-HOUR HISTORICAL SUMMARY ===",
            f"- Analyzed Samples: {history_24h.get('total_samples', 0)}",
            f"- Average pH: {history_24h.get('ph_average', 'N/A')} (Min: {history_24h.get('ph_min', 'N/A')}, Max: {history_24h.get('ph_max', 'N/A')})",
            f"- Average Turbidity: {history_24h.get('turbidity_average', 'N/A')} NTU (Max: {history_24h.get('turbidity_max', 'N/A')} NTU)",
            f"- Dominant ML Trend: {getattr(ml_summary, 'dominant_trend', 'STABLE')}",
            f"- Active Anomalies Count: {getattr(ml_summary, 'active_anomalies_count', 0)}",
            "",
        ]

        if recent_alerts:
            lines.append("=== RECENT INCIDENTS ===")
            for a in recent_alerts[:3]:
                lines.append(f"- [{a.get('severity')}] {a.get('title')}: {a.get('message')}")
            lines.append("")

        if chat_history:
            lines.append("=== PREVIOUS CONVERSATION TURNS ===")
            for turn in chat_history:
                role = "User" if turn.get("role") == "user" else "AquaAdvisor"
                lines.append(f"{role}: {turn.get('content')}")
            lines.append("")

        lines.append(f"=== CURRENT USER INQUIRY ===")
        lines.append(query)

        return "\n".join(lines)

    async def answer_query(
        self,
        query: str,
        db: Session,
        session_id: str = "default_session",
    ) -> ChatResponse:
        """Processes an inquiry with full telemetry grounding and conversation history."""
        # 1. Retrieve telemetry, ML metrics, and past conversation history
        current_status = WaterChatbotTools.get_current_water_status(db)
        history_24h = WaterChatbotTools.get_historical_metrics(db, hours=24)
        recent_alerts = WaterChatbotTools.get_recent_alerts(db, limit=3)
        ml_summary = InsightsGenerator.generate_summary(db, operating_mode=settings.DATA_MODE)
        chat_history = WaterChatbotTools.get_recent_conversation_history(db, session_id=session_id, limit=6)

        context_payload = {
            "current_status": current_status,
            "history_24h": history_24h,
            "recent_alerts": recent_alerts,
            "ml_dominant_trend": getattr(ml_summary, "dominant_trend", "STABLE"),
            "ml_insights_count": len(getattr(ml_summary, "insights", [])),
            "operating_mode": settings.DATA_MODE,
        }

        # 2. Check if LLM adapter is configured
        adapter = self._get_llm_adapter()
        response_text: Optional[str] = None
        source = "fallback_rule_advisor"
        model_name = "fallback_rule_advisor"
        provider_status = "active"

        if adapter:
            prompt = self._format_context_prompt(
                query=query,
                current_status=current_status,
                history_24h=history_24h,
                recent_alerts=recent_alerts,
                ml_summary=ml_summary,
                chat_history=chat_history,
            )
            llm_text, err_reason, actual_model = await adapter.generate_response(
                prompt=prompt, system_prompt=self.system_prompt
            )

            if llm_text:
                response_text = llm_text
                source = f"{settings.LLM_PROVIDER.lower()}_llm"
                model_name = actual_model
                provider_status = "active"
            else:
                logger.warning(f"[Chatbot] LLM generation failed ({err_reason}); activating rule advisor fallback.")
                provider_status = f"fallback_engaged: {err_reason or 'UNKNOWN_ERROR'}"

        # 3. Fallback to expert domain rule advisor if LLM unavailable or failed
        if not response_text:
            response_text = self._domain_rule_based_response(
                query=query,
                status=current_status,
                history=history_24h,
                alerts=recent_alerts,
                ml_summary=ml_summary,
                chat_history=chat_history,
            )
            source = "fallback_rule_advisor"
            model_name = "fallback_rule_advisor"

        # 4. Save conversation turn to SQLite for audit and follow-ups
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
            provider_status=provider_status,
        )

    def _domain_rule_based_response(
        self,
        query: str,
        status: Dict[str, Any],
        history: Dict[str, Any],
        alerts: list,
        ml_summary: Any,
        chat_history: Optional[List[Dict[str, str]]] = None,
    ) -> str:
        """Domain rule-based response generator using actual database readings and context."""
        q = query.lower().strip()

        # 1. Greetings & general identity
        if q in ("hello", "hi", "hey", "greetings", "good morning", "good afternoon", "good evening") or q.startswith(("hello", "hi ", "hey ")):
            return (
                "Hello! I am **AquaAdvisor**, your AI Water Quality Consultant. "
                "I can analyze real-time sensor telemetry, explain pH and turbidity levels, "
                "interpret machine learning anomalies, and provide practical maintenance advice. "
                "How can I assist you today?"
            )

        # 2. What can you do / project explanation
        if "what can you do" in q or "explain my project" in q or "how does this work" in q or "how does this system work" in q:
            return (
                "**About HydroSense & AquaAdvisor:**\n"
                "- **Edge Microcontroller (ESP32)**: Reads analog signals from your pH electrode (GPIO34) and optical turbidity probe (GPIO32), scaled with 15kΩ/10kΩ protective voltage dividers.\n"
                "- **Local Alerts**: An I2C SSD1306 OLED displays live metrics and an acoustic buzzer sounds non-blocking alarms for critical conditions.\n"
                "- **Cloud Telemetry**: Publishes 7-field telemetry to ThingSpeak every 20 seconds.\n"
                "- **Backend & Machine Learning**: Python FastAPI stores historical records in SQLite, evaluates linear degradation trends, and runs Median Absolute Deviation (MAD) & Isolation Forest to detect sudden spikes or stuck sensors.\n"
                "- **AI Consultant**: I ground all answers in real-time measurements and EPA/WHO drinking water guidelines."
            )

        # 3. Practical water quality improvement advice
        if "improve" in q or "maintenance" in q or "maintain" in q or "clean tank" in q or "advice" in q:
            return (
                "**Practical Water Quality & Tank Maintenance Recommendations:**\n"
                "1. **Rooftop & Underground Tank Cleaning**: Schedule physical scrubbing and food-grade chlorination at least once every 6 months to prevent sediment buildup and biofilm proliferation.\n"
                "2. **Sediment Pre-Filtration**: Install a whole-apartment 5-micron spun polypropylene sediment filter at your inlet to capture rust flakes and seasonal pipeline silt before water enters your storage tanks.\n"
                "3. **Activated Carbon Filtration**: Use granular activated carbon (GAC) for point-of-use taps to remove residual chlorine taste, odors, and dissolved volatile organics.\n"
                "4. **Regular Sensor Calibration**: Recalibrate the pH glass probe every 30–60 days using pH 7.00 and 4.01 buffer solutions.\n"
                "5. **Certified Laboratory Testing**: For drinking water verification, periodically send tap samples to a certified lab for microbiological cultures (*E. coli*, coliforms) and heavy metal screening."
            )

        # 4. Is water safe to drink?
        if "safe" in q or "drink" in q or "potable" in q:
            turb = status.get("turbidity_ntu")
            turb_str = f"Current turbidity is {turb:.1f} NTU." if turb is not None else ""
            return (
                "**Drinking Water Safety Guidance:**\n"
                f"While current sensors monitor bulk physical parameters (pH and turbidity), **normal readings DO NOT prove water is microbiologically safe to drink**. {turb_str}\n\n"
                "Critical safety rules:\n"
                "- Physical sensors **cannot** detect microbiological pathogens (*E. coli*, norovirus, cysts) or dissolved heavy metals (lead, arsenic).\n"
                "- Always use point-of-use reverse osmosis (RO) or boiling if municipal contamination is suspected.\n"
                "- For complete drinking certification, mandatory laboratory bacteriological testing is required."
            )

        # 5. pH queries
        if "ph" in q and ("what" in q or "current" in q or "level" in q or "value" in q or "fluctuat" in q or "why" in q):
            ph = status.get("ph")
            ph_v = status.get("ph_voltage")
            is_cal = status.get("ph_calibrated")
            if "fluctuat" in q:
                return (
                    "**Why Does pH Fluctuate in Apartment Tanks?**\n"
                    "- **Municipal Dosing Variations**: City treatment plants adjust lime or alum dosing based on seasonal raw river chemistry.\n"
                    "- **Dissolved Atmospheric CO₂**: Standing water absorbs ambient carbon dioxide, forming mild carbonic acid (H₂CO₃) and lowering pH slightly.\n"
                    "- **Aging Concrete Tanks**: Fresh concrete or mortar leach calcium hydroxide, causing elevated alkaline pH (8.5–9.5).\n"
                    "- **Electrode Drift**: Glass bulb reference electrolytes deplete over time, which requires periodic buffer recalibration."
                )
            if ph is not None:
                eval_str = "Within EPA Safe Range (6.5–8.5)" if (6.5 <= ph <= 8.5) else "ABNORMAL / EXCURSION"
                return (
                    f"**Current pH Level:** {ph:.2f} ({eval_str})\n"
                    f"- Sensor Board Voltage: {ph_v:.3f} V (ADC Input: {ph_v/2.5:.3f} V)\n"
                    f"- EPA Recommended Standard: 6.5 to 8.5\n"
                    f"- Calibration: {'Two-Point Calibrated' if is_cal else 'Linear Default (Buffer calibration recommended)'}"
                )
            else:
                return (
                    f"**Current pH:** Calibration Pending.\n"
                    f"- Measured Board Output: {ph_v:.3f} V (Divided ADC: {ph_v/2.5:.3f} V)\n"
                    "The E201-C probe is currently operating in uncalibrated mode. Perform two-point calibration using standard pH 7.00 and pH 4.01 buffers."
                )

        # 6. Turbidity queries
        if "turbid" in q:
            turb = status.get("turbidity_ntu")
            turb_v = status.get("turbidity_voltage")
            return (
                f"**Turbidity Assessment:** Current level is {f'{turb:.1f} NTU' if turb is not None else 'Uncalibrated'} (Board Voltage: {turb_v:.3f} V).\n"
                "- **WHO Drinking Water Limit**: < 5.0 NTU (ideally < 1.0 NTU for effective disinfection).\n"
                "- **Causes of Turbidity Spikes**:\n"
                "  1. *Municipal Main Flushing*: Routine hydrant scouring suspends pipeline silt.\n"
                "  2. *Internal Riser Corrosion*: Galvanized or iron apartment risers flaking iron rust particles.\n"
                "  3. *Header Tank Silt Disturbance*: Refilling underground or overhead tanks stirs bottom sediments.\n"
                "  4. *Filter Breakthrough*: Saturated sediment filter cartridges passing particulates."
            )

        # 7. TDS queries
        if "tds" in q:
            return (
                "**Total Dissolved Solids (TDS) Status:**\n"
                "- **Current Reading**: NULL / N/A (Strictly not 0.0 ppm).\n"
                "- **Hardware Reason**: The physical TDS probe hardware has not arrived. Pin **GPIO 35** is reserved in firmware and backend for drop-in activation.\n"
                "- **EPA Standard**: < 500 ppm for domestic drinking supplies once the probe is installed."
            )

        # 8. ML and Anomalies queries
        if "ml" in q or "anomal" in q or "spike" in q or "trend" in q or "drift" in q or "isolation forest" in q:
            dominant_trend = getattr(ml_summary, "dominant_trend", "STABLE") if ml_summary else "STABLE"
            anom_count = getattr(ml_summary, "active_anomalies_count", 0) if ml_summary else 0
            return (
                f"**Machine Learning & Anomaly Summary:**\n"
                f"- **Dominant Drift Direction**: **{dominant_trend}**\n"
                f"- **Active Detected Outliers**: {anom_count} anomaly events.\n"
                "- **Isolation Forest**: Multi-dimensional tree ensemble that isolates abnormal combinations (e.g. normal calibrated pH with anomalous raw voltages).\n"
                "- **Robust MAD Detector**: Employs Median Absolute Deviation to detect abrupt step-changes and transient contamination spikes without Gaussian distortion."
            )

        # 9. Warnings and alerts queries
        if "warning" in q or "alert" in q or "critical" in q or "hazard" in q:
            if alerts:
                last_alert = alerts[0]
                return (
                    f"**Active Incident Analysis:**\n"
                    f"- Title: **{last_alert.get('title')}**\n"
                    f"- Severity: Level {last_alert.get('severity')}\n"
                    f"- Details: {last_alert.get('message')}\n"
                    f"- Time: {last_alert.get('timestamp')}\n\n"
                    "Recommended action: Check physical faucet output, inspect sediment filter cartridges, and verify circuit ground continuity."
                )
            return "✅ **No Active Alerts**: All monitored water quality parameters and hardware boundaries are operating within normal limits."

        # 10. Default contextual response
        ph = status.get("ph")
        turb = status.get("turbidity_ntu")
        mode = status.get("operating_mode", "real").upper()
        return (
            f"**AquaAdvisor Diagnostic Overview [{mode} MODE]:**\n"
            f"- pH: {f'{ph:.2f}' if ph is not None else 'Uncalibrated'}\n"
            f"- Turbidity: {f'{turb:.1f} NTU' if turb is not None else 'Uncalibrated'}\n"
            f"- TDS: NULL (Reserved GPIO35)\n"
            f"- System Health: {status.get('health_summary', 'NORMAL')}\n\n"
            "You can ask me questions such as:\n"
            "- *'Is the water currently safe to drink?'*\n"
            "- *'What causes high turbidity?'*\n"
            "- *'How can I improve apartment water quality?'*\n"
            "- *'Summarize recent ML anomaly detections and drift.'*\n"
            "- *'Why is the TDS sensor reporting null?'*"
        )
