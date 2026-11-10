/**
 * Centralized API Service for HydroSense Smart Water Quality Monitor.
 */

import {
  BackendHealth,
  SystemHealth,
  SensorReading,
  SensorStatistics,
  AlertSummary,
  AlertItem,
  AnomalyResponse,
  TrendResponse,
  MLSummary,
  ChatResponse,
  ChatbotStatus,
  WaterQualitySettings,
  WaterQualityMode,
  CalibrationStatusDetail,
} from '../types';

const API_BASE = '/api';

async function handleResponse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let errorDetail = `HTTP Error ${res.status}: ${res.statusText}`;
    try {
      const data = await res.json();
      if (data && data.detail) {
        errorDetail = typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail);
      }
    } catch {
      // Body not JSON
    }
    throw new Error(errorDetail);
  }
  return res.json() as Promise<T>;
}

export const api = {
  async getHealth(): Promise<BackendHealth> {
    const res = await fetch(`${API_BASE}/health`);
    return handleResponse<BackendHealth>(res);
  },

  async getSystemStatus(): Promise<SystemHealth> {
    const res = await fetch(`${API_BASE}/system/status`);
    return handleResponse<SystemHealth>(res);
  },

  async getLatestReading(): Promise<SensorReading | null> {
    const res = await fetch(`${API_BASE}/readings/latest`);
    return handleResponse<SensorReading | null>(res);
  },

  async getReadingsHistory(hours = 24, limit = 100): Promise<SensorReading[]> {
    const params = new URLSearchParams({
      hours: hours.toString(),
      limit: limit.toString(),
    });
    const res = await fetch(`${API_BASE}/readings/history?${params.toString()}`);
    return handleResponse<SensorReading[]>(res);
  },

  async getStatistics(hours = 24): Promise<SensorStatistics> {
    const res = await fetch(`${API_BASE}/readings/statistics?hours=${hours}`);
    return handleResponse<SensorStatistics>(res);
  },

  async getAlerts(): Promise<AlertSummary> {
    const res = await fetch(`${API_BASE}/alerts`);
    return handleResponse<AlertSummary>(res);
  },

  async resolveAlert(alertId: number): Promise<AlertItem> {
    const res = await fetch(`${API_BASE}/alerts/${alertId}/resolve`, {
      method: 'POST',
    });
    return handleResponse<AlertItem>(res);
  },

  async getMLAnomalies(limit = 100): Promise<AnomalyResponse> {
    const res = await fetch(`${API_BASE}/ml/anomalies?limit=${limit}`);
    return handleResponse<AnomalyResponse>(res);
  },

  async getMLTrends(limit = 100): Promise<TrendResponse> {
    const res = await fetch(`${API_BASE}/ml/trends?limit=${limit}`);
    return handleResponse<TrendResponse>(res);
  },

  async getMLSummary(): Promise<MLSummary> {
    const res = await fetch(`${API_BASE}/ml/summary`);
    return handleResponse<MLSummary>(res);
  },

  async trainMLModel(): Promise<{ status: string; message: string; samples?: number }> {
    const res = await fetch(`${API_BASE}/ml/train`, { method: 'POST' });
    return handleResponse<{ status: string; message: string; samples?: number }>(res);
  },

  async askChatbot(message: string, sessionId = 'default_session'): Promise<ChatResponse> {
    const res = await fetch(`${API_BASE}/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message, session_id: sessionId }),
    });
    return handleResponse<ChatResponse>(res);
  },

  async getChatbotStatus(): Promise<ChatbotStatus> {
    const res = await fetch(`${API_BASE}/chatbot/status`);
    return handleResponse<ChatbotStatus>(res);
  },

  async syncThingSpeak(results = 50): Promise<{ channel_id: string; new_records_saved: number }> {
    const res = await fetch(`${API_BASE}/thingspeak/sync?results=${results}`, {
      method: 'POST',
    });
    return handleResponse<{ channel_id: string; new_records_saved: number }>(res);
  },

  async injectDemo(
    scenario: 'normal' | 'warning' | 'critical' | 'uncalibrated' | 'sensor_fault' | 'stale'
  ): Promise<SensorReading> {
    const res = await fetch(`${API_BASE}/demo/inject/${scenario}`, {
      method: 'POST',
    });
    return handleResponse<SensorReading>(res);
  },

  /** Water Quality Mode & Thresholds */
  async getWaterQualitySettings(): Promise<WaterQualitySettings> {
    const res = await fetch(`${API_BASE}/settings/mode`);
    return handleResponse<WaterQualitySettings>(res);
  },

  async switchWaterQualityMode(mode: WaterQualityMode): Promise<WaterQualitySettings> {
    const res = await fetch(`${API_BASE}/settings/mode`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ mode }),
    });
    return handleResponse<WaterQualitySettings>(res);
  },

  async updateModeThresholds(payload: {
    mode: WaterQualityMode;
    ph_min: number;
    ph_max: number;
    turbidity_max: number;
    tds_max: number;
  }): Promise<WaterQualitySettings> {
    const res = await fetch(`${API_BASE}/settings/thresholds`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    return handleResponse<WaterQualitySettings>(res);
  },

  async resetModeDefaults(mode: WaterQualityMode): Promise<WaterQualitySettings> {
    const res = await fetch(`${API_BASE}/settings/mode/reset/${mode}`, {
      method: 'POST',
    });
    return handleResponse<WaterQualitySettings>(res);
  },

  /** Calibration Status */
  async getCalibrationStatus(): Promise<CalibrationStatusDetail> {
    const res = await fetch(`${API_BASE}/calibration/status`);
    return handleResponse<CalibrationStatusDetail>(res);
  },
};
