/**
 * TypeScript Interfaces and Data Types for Smart Water Quality Monitor.
 * All schemas mirror the Phase 2 FastAPI backend models.
 */

export interface SensorReading {
  id: number;
  entry_id?: number | null;
  device_id: string;
  ph: number | null;
  turbidity: number | null;
  tds: number | null; // STRICT: null when uninstalled, NEVER 0
  ph_voltage: number;
  turbidity_voltage: number;
  ph_board_voltage?: number | null;
  turbidity_board_voltage?: number | null;
  ph_calibrated: boolean;
  turbidity_calibrated: boolean;
  tds_calibrated: boolean;
  alert_severity: number; // 0=Normal, 1=Warning, 2=Critical, 3=Fault
  alert_messages: string;
  sensor_health_summary: string;
  health_code: number;
  data_source: string;
  operating_mode: string;
  is_valid: boolean;
  is_stale: boolean;
  timestamp: string;
  validation_notes?: string | null;
}

export interface BackendHealth {
  status: string;
  service: string;
  version: string;
  operating_mode: 'real' | 'demo' | string;
  cloud_connectivity: string;
  last_successful_telemetry: string | null;
  data_freshness: string;
  database_records_count: number;
}

export interface SystemHealth {
  raw_code: number;
  wifi_connected: boolean;
  cloud_synced: boolean;
  ph_sensor_healthy: boolean;
  turbidity_sensor_healthy: boolean;
  electrical_safe: boolean;
  tds_installed: boolean;
  calibration_pending: boolean;
  demo_mode: boolean;
  overall_status: string;
  operating_mode: string;
  data_freshness: string;
  last_cloud_sync: string | null;
}

export interface SensorStatistics {
  count: number;
  operating_mode: string;
  data_source: string;
  ph_mean: number | null;
  ph_min: number | null;
  ph_max: number | null;
  turbidity_mean: number | null;
  turbidity_max: number | null;
  tds_mean: number | null;
  last_updated: string | null;
}

export interface AlertItem {
  id: number;
  timestamp: string;
  severity: number; // 1=Warning, 2=Critical, 3=Fault
  title: string;
  message: string;
  resolved: boolean;
  resolved_at: string | null;
}

export interface AlertSummary {
  total_active: number;
  critical_count: number;
  warning_count: number;
  fault_count: number;
  recent_alerts: AlertItem[];
}

export interface AnomalyItem {
  timestamp: string | null;
  parameter: string;
  measured_value: number | null;
  baseline_mean: number | null;
  baseline_std: number | null;
  anomaly_score: number;
  detector_type: 'zscore' | 'isolation_forest' | 'mad' | string;
  anomaly_type: string;
  human_explanation: string;
  category: 'MEASURED_FACT' | 'STATISTICAL_ANOMALY' | 'ML_PREDICTION' | 'RULE_BASED_WARNING' | string;
}

export interface AnomalyResponse {
  analyzed_samples: number;
  anomaly_count: number;
  operating_mode: string;
  anomalies: AnomalyItem[];
}

export interface TrendItem {
  parameter: string;
  slope_per_hour: number;
  intercept: number | null;
  r_squared: number;
  trend_direction: 'INCREASING' | 'DECREASING' | 'STABLE' | 'INSUFFICIENT_DATA';
  explanation: string;
}

export interface TrendResponse {
  status: string;
  operating_mode: string;
  ph_drift: TrendItem;
  turbidity_drift: TrendItem;
  total_samples: number;
}

export interface InsightDetail {
  category: 'MEASURED_FACT' | 'STATISTICAL_ANOMALY' | 'ML_PREDICTION' | 'RULE_BASED_WARNING' | string;
  message: string;
  parameter?: string;
}

export interface MLSummary {
  status: string;
  operating_mode: string;
  total_records: number;
  active_anomalies_count: number;
  dominant_trend: string;
  insights: InsightDetail[];
  model_metadata: Record<string, any>;
}

export interface ChatRequest {
  message: string;
  session_id?: string;
}

export interface ChatResponse {
  response: string;
  source: 'gemini_llm' | 'openai_llm' | 'fallback_rule_advisor' | string;
  model_used?: string | null;
  session_id: string;
  timestamp: string;
  context_used: Record<string, any>;
  operating_mode: string;
  provider_status?: string | null;
}

export interface ChatbotStatus {
  configured_provider: string;
  model: string;
  api_key_configured: boolean;
  status: string;
  details: string;
}

export interface ChatMessage {
  id: string;
  sender: 'user' | 'assistant';
  text: string;
  timestamp: string;
  source?: string;
  model?: string | null;
  provider_status?: string | null;
}
