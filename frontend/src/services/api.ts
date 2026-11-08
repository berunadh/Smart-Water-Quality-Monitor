/**
 * Centralized API Service for Smart Apartment Water Quality Monitor.
 * Interacts solely with the local FastAPI backend.
 * Never accesses ThingSpeak or LLM APIs directly.
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
  /** Check backend health, operating mode, and cloud link */
  async getHealth(): Promise<BackendHealth> {
    const res = await fetch(`${API_BASE}/health`);
    return handleResponse<BackendHealth>(res);
  },

  /** Get 16-bit hardware status bitmask and component states */
  async getSystemStatus(): Promise<SystemHealth> {
    const res = await fetch(`${API_BASE}/system/status`);
    return handleResponse<SystemHealth>(res);
  },

  /** Get the single latest water quality telemetry packet */
  async getLatestReading(): Promise<SensorReading | null> {
    const res = await fetch(`${API_BASE}/readings/latest`);
    return handleResponse<SensorReading | null>(res);
  },

  /** Fetch paginated historical readings */
  async getReadingsHistory(hours = 24, limit = 100): Promise<SensorReading[]> {
    const params = new URLSearchParams({
      hours: hours.toString(),
      limit: limit.toString(),
    });
    const res = await fetch(`${API_BASE}/readings/history?${params.toString()}`);
    return handleResponse<SensorReading[]>(res);
  },

  /** Fetch calculated statistics */
  async getStatistics(hours = 24): Promise<SensorStatistics> {
    const res = await fetch(`${API_BASE}/readings/statistics?hours=${hours}`);
    return handleResponse<SensorStatistics>(res);
  },

  /** Fetch active alerts and recent incidents */
  async getAlerts(): Promise<AlertSummary> {
    const res = await fetch(`${API_BASE}/alerts`);
    return handleResponse<AlertSummary>(res);
  },

  /** Mark an alert as acknowledged / resolved */
  async resolveAlert(alertId: number): Promise<AlertItem> {
    const res = await fetch(`${API_BASE}/alerts/${alertId}/resolve`, {
      method: 'POST',
    });
    return handleResponse<AlertItem>(res);
  },

  /** Fetch multi-tier anomaly detection results */
  async getMLAnomalies(limit = 100): Promise<AnomalyResponse> {
    const res = await fetch(`${API_BASE}/ml/anomalies?limit=${limit}`);
    return handleResponse<AnomalyResponse>(res);
  },

  /** Fetch linear trend drift rates and R-squared fit */
  async getMLTrends(limit = 100): Promise<TrendResponse> {
    const res = await fetch(`${API_BASE}/ml/trends?limit=${limit}`);
    return handleResponse<TrendResponse>(res);
  },

  /** Fetch synthesized, categorized AI insights summary */
  async getMLSummary(): Promise<MLSummary> {
    const res = await fetch(`${API_BASE}/ml/summary`);
    return handleResponse<MLSummary>(res);
  },

  /** Trigger retraining of anomaly detection models */
  async trainMLModel(): Promise<{ status: string; message: string; samples?: number }> {
    const res = await fetch(`${API_BASE}/ml/train`, { method: 'POST' });
    return handleResponse<{ status: string; message: string; samples?: number }>(res);
  },

  /** Query AI Water Advisor Chatbot */
  async askChatbot(message: string, sessionId = 'default_session'): Promise<ChatResponse> {
    const res = await fetch(`${API_BASE}/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message, session_id: sessionId }),
    });
    return handleResponse<ChatResponse>(res);
  },

  /** Trigger a ThingSpeak cloud fetch sync */
  async syncThingSpeak(results = 50): Promise<{ channel_id: string; new_records_saved: number }> {
    const res = await fetch(`${API_BASE}/thingspeak/sync?results=${results}`, {
      method: 'POST',
    });
    return handleResponse<{ channel_id: string; new_records_saved: number }>(res);
  },

  /** Inject a demo scenario for live testing */
  async injectDemo(scenario: 'normal' | 'warning' | 'critical' | 'sensor_fault' | 'stale'): Promise<SensorReading> {
    const res = await fetch(`${API_BASE}/demo/inject/${scenario}`, {
      method: 'POST',
    });
    return handleResponse<SensorReading>(res);
  },
};
