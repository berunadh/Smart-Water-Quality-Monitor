/**
 * TypeScript Interfaces for HydroSense Smart Water Quality Monitor.
 */

export type WaterQualityMode = 'drinking' | 'regular_usage';
export type CalibrationConfidence =
  | 'VERIFIED_CALIBRATION'
  | 'MODEL_BASED_PROVISIONAL'
  | 'DEMONSTRATION_ESTIMATE'
  | 'UNCALIBRATED'
  | 'SENSOR_FAULT';

export interface SensorReading {
  id: number;
  entry_id?: number | null;
  device_id: string;
  ph: number | null;
  ph_sensor_estimate?: number | null;
  ph_demo_estimate?: number | null;
  ph_display_source?: 'SENSOR_ESTIMATE' | 'DEMO_ESTIMATE' | string;
  turbidity: number | null;
  tds: number | null; // STRICT: null when uncalibrated or unavailable, NEVER 0
  ph_voltage: number;
  turbidity_voltage: number;
  tds_voltage?: number | null;
  ph_board_voltage?: number | null;
  turbidity_board_voltage?: number | null;
  ph_calibrated: boolean;
  turbidity_calibrated: boolean;
  tds_calibrated: boolean;
  ph_calibration_status?: CalibrationConfidence;
  turbidity_calibration_status?: CalibrationConfidence;
  tds_calibration_status?: CalibrationConfidence;
  alert_severity: number; // 0=Normal, 1=Warning, 2=Critical, 3=Fault
  alert_messages: string;
  sensor_health_summary: string;
  health_code: number;
  data_source: string;
  operating_mode: string;
  water_quality_mode?: WaterQualityMode | string;
  sample_profile?: 'live' | 'kent_ro' | 'household_tap' | 'contaminated_demo' | string;
  is_valid: boolean;
  is_stale: boolean;
  timestamp: string;
  validation_notes?: string | null;
}

export interface SampleProfileState {
  selected_profile: 'kent_ro' | 'household_tap' | 'contaminated_demo';
  contaminated_demo_ph: number;
  updated_at: string;
  control_note: string;
}

export interface BackendHealth {
  status: string;
  service: string;
  version: string;
  operating_mode: 'real' | 'demo' | string;
  water_quality_mode?: WaterQualityMode | string;
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
  tds_sensor_healthy?: boolean;
  tds_dry?: boolean;
  tds_provisional?: boolean;
  ph_provisional?: boolean;
  turb_provisional?: boolean;
  electrical_safe: boolean;
  tds_installed: boolean;
  calibration_pending: boolean;
  demo_mode: boolean;
  overall_status: string;
  operating_mode: string;
  water_quality_mode?: WaterQualityMode | string;
  data_freshness: string;
  last_cloud_sync: string | null;
}

export interface ModeThresholdProfile {
  ph_min: number;
  ph_max: number;
  turbidity_max: number;
  tds_max: number;
  label: string;
  reference_note: string;
  is_regulatory_reference: boolean;
}

export interface ParameterEvaluation {
  parameter: string;
  status: 'acceptable' | 'warning' | 'exceeded' | 'uncalibrated' | 'unavailable' | 'fault' | string;
  value: number | null;
  unit: string;
  limit_text: string;
  message: string;
}

export interface WaterQualityEvaluation {
  active_mode: WaterQualityMode;
  mode_label: string;
  overall_status: string;
  alert_severity: number;
  violated_parameters: string[];
  parameter_evaluations: Record<string, ParameterEvaluation>;
  preliminary_disclaimer: string;
  wqs?: number | null;
  q_ph?: number | null;
  q_turb?: number | null;
  q_tds?: number | null;
  water_status_code?: number;
  water_status_label?: string;
  critical_hazard?: boolean;
  hazard_reasons?: string[];
}

export interface WaterQualitySettings {
  active_mode: WaterQualityMode;
  active_profile: ModeThresholdProfile;
  drinking_profile: ModeThresholdProfile;
  regular_usage_profile: ModeThresholdProfile;
  preliminary_disclaimer: string;
  updated_at: string;
  latest_evaluation: WaterQualityEvaluation | null;
}

export interface CalibrationRecord {
  id: number;
  timestamp: string;
  sensor_type: string;
  point_name: string;
  reference_value: number;
  measured_voltage: number;
  operator_notes?: string | null;
}

export interface CalibrationStatusDetail {
  ph_calibrated: boolean;
  turbidity_calibrated: boolean;
  tds_calibrated: boolean;
  ph_provisional?: boolean;
  turbidity_provisional?: boolean;
  tds_provisional?: boolean;
  calibration_pending: boolean;
  ph_voltage: number;
  turbidity_voltage: number;
  tds_voltage?: number | null;
  ph_reference_standards: string[];
  turbidity_reference_standards: string[];
  tds_reference_standards: string[];
  recent_records: CalibrationRecord[];
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
  severity: number;
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
  detector_type: string;
  anomaly_type: string;
  human_explanation: string;
  category: string;
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
  trend_direction: 'INCREASING' | 'DECREASING' | 'STABLE' | 'INSUFFICIENT_DATA' | 'NO_DATA';
  explanation: string;
}

export interface TrendResponse {
  status: string;
  operating_mode: string;
  ph_drift: TrendItem;
  turbidity_drift: TrendItem;
  tds_drift?: TrendItem | null;
  total_samples: number;
}

export interface InsightDetail {
  type?: string;
  category?: string;
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
