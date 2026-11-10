"""AI Water Quality Advisor agent with mode-aware grounding, LLM adapter, and domain fallback."""

import os
from typing import Dict, Any, Optional, List
from datetime import datetime
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging import logger
from app.models.chat_message import ChatMessageModel
from app.models.water_reading import WaterReadingModel
from app.schemas.chat import ChatResponse
from app.chatbot.tools import WaterChatbotTools
from app.chatbot.llm_adapter import GeminiRESTAdapter, OpenAIRESTAdapter
from app.ml.insights import InsightsGenerator
from app.ml.trend_analyzer import TrendAnalyzer
import pandas as pd


SYSTEM_PROMPT = """You are AquaAdvisor, an intelligent Water Quality & IoT Diagnostics Consultant for HydroSense.

Hardware Architecture:
- Edge MCU: ESP32-D0WD-V3 monitoring municipal/apartment water supply.
- Sensors:
  1. pH Probe (E201-C + Green Board) on GPIO34 with 15kΩ/10kΩ voltage divider (÷2.5 step-down).
  2. Turbidity Optical Probe (Red Board) on GPIO32 with 15kΩ/10kΩ voltage divider (÷2.5 step-down).
  3. TDS Probe (3.3V Direct Module) on GPIO35 with NO voltage divider (V_ADC directly, 0–3.3V safe).
- Local Alerts: 128×64 SSD1306 OLED + Smart Buzzer on GPIO25 (sounds ONLY for calibrated threshold breaches).

Water Quality Modes:
1. DRINKING MODE: Evaluated strictly against Indian Standard BIS IS 10500:2012 Acceptable Limits (pH 6.5–8.5, Turbidity ≤ 1.0 NTU, TDS ≤ 500 mg/L unless user customized). Note that pH, turbidity, and TDS alone provide only preliminary screening and DO NOT certify potability against pathogens or heavy metals.
2. REGULAR USAGE MODE: Evaluated against separate user-configurable non-drinking operational settings (no universal regulatory limit applies).

Mandatory Rules:
1. Base all answers strictly on the telemetry, active mode, active thresholds, calibration state, trends, and alerts provided below. Never fabricate sensor numbers.
2. Always evaluate against the CURRENTLY SELECTED MODE and explicitly reference its thresholds.
3. Never treat missing, null, or uncalibrated readings as 0 or normal. Never confuse raw voltage (V) with calibrated pH, NTU, or ppm.
4. If sensors are pending calibration, explain that raw voltages are healthy diagnostic inputs and guide user calibration without basing water safety conclusions on uncalibrated data.
5. If telemetry is stale (>5 minutes old), explicitly warn the user.
6. NEVER claim water is completely safe to drink solely from pH, turbidity, and TDS; always note certified lab testing is needed for pathogens/heavy metals.
7. Explain specifically WHICH parameter caused a warning/alert when violations occur, and recommend concise, actionable next steps.
8. Distinguish DEMO/SIMULATED telemetry from REAL hardware streams.
9. Track conversation history naturally to resolve follow-up questions.
"""


class WaterChatbotAgent:
    """Orchestrates multi-turn conversations, dual-mode context retrieval, LLM generation, and fallback logic."""

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
            return GeminiRESTAdapter(api_key=api_key, model=settings.LLM_MODEL, timeout=25.0)
        elif provider == "openai":
            return OpenAIRESTAdapter(api_key=api_key, model=settings.LLM_MODEL)
        return None

    def _get_recent_trends(self, db: Session) -> Dict[str, Any]:
        readings = (
            db.query(WaterReadingModel)
            .filter(WaterReadingModel.is_valid == True)
            .order_by(WaterReadingModel.timestamp.asc())
            .limit(100)
            .all()
        )
        if not readings:
            return {}
        df = pd.DataFrame([
            {
                "timestamp": r.timestamp,
                "ph": r.ph,
                "turbidity": r.turbidity,
                "tds": r.tds,
            }
            for r in readings
        ])
        tr = TrendAnalyzer.evaluate_water_trends(df, operating_mode=settings.DATA_MODE)
        return {
            "ph_trend": f"{tr.ph_drift.trend_direction} ({tr.ph_drift.slope_per_hour:+.3f}/hr)",
            "turbidity_trend": f"{tr.turbidity_drift.trend_direction} ({tr.turbidity_drift.slope_per_hour:+.2f} NTU/hr)",
            "tds_trend": (
                f"{tr.tds_drift.trend_direction} ({tr.tds_drift.slope_per_hour:+.1f} ppm/hr)"
                if tr.tds_drift else "INSUFFICIENT_DATA"
            ),
        }

    def _format_context_prompt(
        self,
        query: str,
        current_status: Dict[str, Any],
        history_24h: Dict[str, Any],
        recent_alerts: List[Dict[str, Any]],
        ml_summary: Any,
        trends: Dict[str, Any],
        chat_history: List[Dict[str, str]],
    ) -> str:
        """Formats grounding telemetry, dual-mode rules, trends, and conversation history."""
        mode_str = "DEMO / SIMULATED TELEMETRY" if settings.DATA_MODE == "demo" else "REAL ESP32 HARDWARE STREAM"
        th = current_status.get("active_thresholds", {})
        param_evals = current_status.get("parameter_evaluations", {})
        violated = current_status.get("violated_parameters", [])

        tds_v = current_status.get("tds_voltage")
        tds_v_str = f"{tds_v:.3f} V (GPIO35 Direct 3.3V, NO divider)" if tds_v is not None else "N/A"
        ph_val = current_status.get("ph")
        turb_val = current_status.get("turbidity_ntu")
        tds_val = current_status.get("tds_ppm")

        lines = [
            f"=== ACTIVE WATER QUALITY MODE & THRESHOLDS ===",
            f"- Selected Mode: {th.get('mode_label', 'Drinking Mode')} ({th.get('mode', 'drinking')})",
            f"- Mode Reference: {th.get('reference_note', 'BIS IS 10500:2012')}",
            f"- Allowed pH Range: {th.get('ph_min', 6.5)} – {th.get('ph_max', 8.5)}",
            f"- Maximum Turbidity Limit: {th.get('turbidity_max', 1.0)} NTU",
            f"- Maximum TDS Limit: {th.get('tds_max', 500.0)} mg/L (ppm)",
            "",
            f"=== CURRENT SYSTEM TELEMETRY [{mode_str}] ===",
            f"- Overall Status: {current_status.get('overall_evaluation_status', 'UNKNOWN')} | Severity: {current_status.get('alert_severity', 0)}",
            f"- Reading Timestamp: {current_status.get('timestamp', 'N/A')} (Stale >5m: {'YES - ' + str(current_status.get('age_minutes')) + 'm old' if current_status.get('is_stale') else 'NO'})",
            f"- Calibrated pH: {f'{ph_val:.2f}' if ph_val is not None else 'NULL / Calibration Pending'} | Calibrated: {current_status.get('ph_calibrated')} | Status: {param_evals.get('ph', {}).get('status', 'unknown')} | Board Voltage: {current_status.get('ph_voltage', 'N/A')} V (÷2.5 divider)",
            f"- Calibrated Turbidity: {f'{turb_val:.2f} NTU' if turb_val is not None else 'NULL / Calibration Pending'} | Calibrated: {current_status.get('turbidity_calibrated')} | Status: {param_evals.get('turbidity', {}).get('status', 'unknown')} | Board Voltage: {current_status.get('turbidity_voltage', 'N/A')} V (÷2.5 divider)",
            f"- Calibrated TDS: {f'{tds_val:.0f} mg/L' if tds_val is not None else 'NULL / Calibration Pending'} | Calibrated: {current_status.get('tds_calibrated')} | Status: {param_evals.get('tds', {}).get('status', 'unknown')} | ADC Voltage: {tds_v_str}",
            f"- Violated Parameters Under Active Mode: {', '.join(violated) if violated else 'None'}",
            f"- Hardware Health Summary: {current_status.get('health_summary', 'OPERATIONAL')} ({current_status.get('health_code', '0x0000')}) | Electrical Safe: {current_status.get('is_valid', True)}",
            "",
            "=== 24-HOUR HISTORICAL STATS & TRENDS ===",
            f"- Analyzed Samples: {history_24h.get('total_samples', 0)}",
            f"- pH Avg/Min/Max: {history_24h.get('ph_average', 'N/A')} / {history_24h.get('ph_min', 'N/A')} / {history_24h.get('ph_max', 'N/A')} | Trend: {trends.get('ph_trend', 'N/A')}",
            f"- Turbidity Avg/Max: {history_24h.get('turbidity_average', 'N/A')} / {history_24h.get('turbidity_max', 'N/A')} NTU | Trend: {trends.get('turbidity_trend', 'N/A')}",
            f"- TDS Avg/Min/Max: {history_24h.get('tds_average', 'N/A')} / {history_24h.get('tds_min', 'N/A')} / {history_24h.get('tds_max', 'N/A')} mg/L | Trend: {trends.get('tds_trend', 'N/A')}",
            f"- Active ML Anomalies Count: {getattr(ml_summary, 'active_anomalies_count', 0)}",
            "",
        ]

        ml_insights = getattr(ml_summary, "insights", [])
        if ml_insights:
            lines.append("=== KEY ML & DIAGNOSTIC INSIGHTS ===")
            for ins in ml_insights[:4]:
                lines.append(f"- [{ins.get('category', ins.get('type', 'INFO'))}] {ins.get('message')}")
            lines.append("")

        if recent_alerts:
            lines.append("=== RECENT INCIDENTS ===")
            for a in recent_alerts[:3]:
                lines.append(f"- [Severity {a.get('severity')}] {a.get('title')}: {a.get('message')} (Resolved: {a.get('resolved')})")
            lines.append("")

        if chat_history:
            lines.append("=== PREVIOUS CONVERSATION TURNS ===")
            for turn in chat_history:
                role = "User" if turn.get("role") == "user" else "AquaAdvisor"
                lines.append(f"{role}: {turn.get('content')}")
            lines.append("")

        lines.append("=== CURRENT USER INQUIRY ===")
        lines.append(query)

        return "\n".join(lines)

    async def answer_query(
        self,
        query: str,
        db: Session,
        session_id: str = "default_session",
    ) -> ChatResponse:
        """Processes an inquiry with full dual-mode telemetry grounding and conversation history."""
        current_status = WaterChatbotTools.get_current_water_status(db)
        history_24h = WaterChatbotTools.get_historical_metrics(db, hours=24)
        recent_alerts = WaterChatbotTools.get_recent_alerts(db, limit=3)
        ml_summary = InsightsGenerator.generate_summary(db, operating_mode=settings.DATA_MODE)
        trends = self._get_recent_trends(db)
        chat_history = WaterChatbotTools.get_recent_conversation_history(db, session_id=session_id, limit=6)

        context_payload = {
            "current_status": current_status,
            "history_24h": history_24h,
            "trends": trends,
            "recent_alerts": recent_alerts,
            "ml_dominant_trend": getattr(ml_summary, "dominant_trend", "STABLE"),
            "ml_insights_count": len(getattr(ml_summary, "insights", [])),
            "operating_mode": settings.DATA_MODE,
            "water_quality_mode": current_status.get("active_thresholds", {}).get("mode", "drinking"),
        }

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
                trends=trends,
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

        if not response_text:
            response_text = self._domain_rule_based_response(
                query=query,
                status=current_status,
                history=history_24h,
                alerts=recent_alerts,
                ml_summary=ml_summary,
                trends=trends,
                chat_history=chat_history,
            )
            source = "fallback_rule_advisor"
            model_name = "fallback_rule_advisor"

        try:
            db.add(ChatMessageModel(
                session_id=session_id,
                role="user",
                content=query,
                model_used=model_name,
                source=source,
            ))
            db.add(ChatMessageModel(
                session_id=session_id,
                role="assistant",
                content=response_text,
                model_used=model_name,
                source=source,
            ))
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
        trends: Optional[Dict[str, Any]] = None,
        chat_history: Optional[List[Dict[str, str]]] = None,
    ) -> str:
        """Mode-aware domain rule engine used cleanly when offline or if LLM fails."""
        q = query.lower().strip()
        th = status.get("active_thresholds", {})
        mode_label = th.get("mode_label", "Drinking Mode")
        violated = status.get("violated_parameters", [])
        ph = status.get("ph")
        turb = status.get("turbidity_ntu")
        tds = status.get("tds_ppm")
        ph_v = status.get("ph_voltage")
        turb_v = status.get("turbidity_voltage")
        tds_v = status.get("tds_voltage")
        stale_note = f"\n\n⚠️ *Note: Telemetry is stale ({status.get('age_minutes')} min old).*" if status.get("is_stale") else ""

        if q in ("hello", "hi", "hey", "greetings") or q.startswith(("hello", "hi ", "hey ")):
            return (
                f"Hello! I am **AquaAdvisor**. We are currently monitoring in **{mode_label}** "
                f"(pH {th.get('ph_min', 6.5)}–{th.get('ph_max', 8.5)}, Turbidity ≤ {th.get('turbidity_max', 1.0)} NTU, "
                f"TDS ≤ {th.get('tds_max', 500):.0f} mg/L). Ask me about current quality, alerts, trends, or calibration!"
            )

        if "mode" in q or "difference" in q:
            return (
                f"**Active Evaluation Profile: {mode_label}**\n"
                f"- **Drinking Mode**: Evaluates against BIS IS 10500:2012 acceptable limits (pH 6.5–8.5, Turbidity ≤ 1.0 NTU, TDS ≤ 500 mg/L).\n"
                f"- **Regular Usage Mode**: Uses separate configurable operational limits (currently pH {th.get('ph_min')}–{th.get('ph_max')}, Turbidity ≤ {th.get('turbidity_max')} NTU, TDS ≤ {th.get('tds_max'):.0f} mg/L for non-drinking tasks).\n"
                f"Switching modes immediately recalculates alert severity and dashboard status without discarding stored measurements."
            )

        if "safe" in q or "drink" in q or "potable" in q:
            issue_str = f" Currently flagging: **{'; '.join(violated)}**." if violated else ""
            return (
                f"**Preliminary Assessment [{mode_label}]:**\n"
                f"Even if pH, turbidity, and TDS meet BIS IS 10500:2012 acceptable limits, **normal sensor readings DO NOT prove or certify water as safe to drink**.{issue_str}\n\n"
                "- Physical probes cannot detect microbiological pathogens (*E. coli*, bacteria, viruses) or dissolved heavy metals.\n"
                f"- Laboratory bacteriological and chemical testing is required to confirm potability.{stale_note}"
            )

        if "warning" in q or "alert" in q or "why" in q or "what should i do" in q or "next step" in q:
            if violated:
                return (
                    f"**Active Threshold Violation(s) [{mode_label}]:**\n"
                    + "\n".join(f"- {v}" for v in violated)
                    + "\n\n**Recommended Actions:** Check tank/filter cartridges, flush tap lines, retest water after stabilization, and verify sensor calibration."
                    + stale_note
                )
            if not status.get("is_valid", True):
                return "**Electrical / Hardware Fault Active:** Check probe connections and voltage divider outputs before trusting readings."
            if status.get("overall_evaluation_status") == "CALIBRATION_PENDING":
                return (
                    "**Calibration Pending:** At least one probe is uncalibrated (reporting raw ADC/board voltages only). "
                    "Complete calibration via Serial Monitor (`ph cal 7.00`/`4.01`, `turb cal clear`/`<ntu>`, `tds cal <ppm>`) before evaluating water safety."
                )
            if alerts and not alerts[0].get("resolved"):
                return f"**Recent Incident:** {alerts[0].get('title')} — {alerts[0].get('message')}.{stale_note}"
            return f"No active threshold violations under **{mode_label}**. All calibrated sensors are within configured limits.{stale_note}"

        if "tds" in q:
            if tds is not None:
                return (
                    f"**TDS Reading:** {tds:.0f} mg/L (Direct ADC: {f'{tds_v:.3f} V' if tds_v is not None else 'N/A'}). "
                    f"Active {mode_label} limit: ≤ {th.get('tds_max', 500):.0f} mg/L.{stale_note}"
                )
            return (
                f"**TDS Status:** Calibration Pending (`null`, never 0 ppm). "
                f"GPIO35 ADC Voltage: {f'{tds_v:.3f} V (direct 3.3V, no divider)' if tds_v is not None else 'Awaiting reading'}. "
                "Calibrate using a certified standard (`tds cal <ppm>` then `tds confirm`)."
            )

        if "ph" in q:
            if ph is not None:
                return f"**pH Reading:** {ph:.2f} (Board Voltage: {ph_v:.3f} V ÷2.5 divider). Active {mode_label} range: {th.get('ph_min')}–{th.get('ph_max')}.{stale_note}"
            return f"**pH Status:** Calibration Pending (`null`). Board Voltage: {ph_v:.3f} V. Perform two-point buffer calibration (`pH 7.00` & `pH 4.01`)."

        if "turbid" in q:
            if turb is not None:
                return f"**Turbidity Reading:** {turb:.2f} NTU (Board Voltage: {turb_v:.3f} V ÷2.5 divider). Active {mode_label} limit: ≤ {th.get('turbidity_max')} NTU.{stale_note}"
            return f"**Turbidity Status:** Calibration Pending (`null`). Board Voltage: {turb_v:.3f} V. Calibrate using 0 NTU distilled water and a known NTU standard."

        return (
            f"**HydroSense Summary [{mode_label} • {'DEMO' if settings.DATA_MODE == 'demo' else 'LIVE'}]:**\n"
            f"- pH: {f'{ph:.2f}' if ph is not None else 'Calibration Pending'} (Limit: {th.get('ph_min')}–{th.get('ph_max')})\n"
            f"- Turbidity: {f'{turb:.2f} NTU' if turb is not None else 'Calibration Pending'} (Limit: ≤ {th.get('turbidity_max')} NTU)\n"
            f"- TDS: {f'{tds:.0f} mg/L' if tds is not None else 'Calibration Pending'} (Limit: ≤ {th.get('tds_max', 500):.0f} mg/L)\n"
            f"- Violations: {', '.join(violated) if violated else 'None'}"
            f"{stale_note}"
        )
