import React, { useState, useEffect, useCallback } from 'react';
import { Header } from './components/Header';
import { OverallStatusBanner } from './components/OverallStatusBanner';
import { SensorCards } from './components/SensorCard';
import { HistoricalCharts } from './components/HistoricalCharts';
import { AlertsSection } from './components/AlertsSection';
import { MLInsightsSection } from './components/MLInsightsSection';
import { SystemDiagnostics } from './components/SystemDiagnostics';
import { ChatbotPanel } from './components/ChatbotPanel';
import { DemoScenarioBar } from './components/DemoScenarioBar';
import { api } from './services/api';
import {
  BackendHealth,
  SystemHealth,
  SensorReading,
  AlertSummary,
  MLSummary,
  AnomalyResponse,
  TrendResponse,
} from './types';
import { AlertCircle } from 'lucide-react';

export const App: React.FC = () => {
  const [activeTab, setActiveTab] = useState<string>('dashboard');
  const [health, setHealth] = useState<BackendHealth | null>(null);
  const [system, setSystem] = useState<SystemHealth | null>(null);
  const [reading, setReading] = useState<SensorReading | null>(null);
  const [history, setHistory] = useState<SensorReading[]>([]);
  const [alerts, setAlerts] = useState<AlertSummary | null>(null);
  const [mlSummary, setMlSummary] = useState<MLSummary | null>(null);
  const [mlAnomalies, setMlAnomalies] = useState<AnomalyResponse | null>(null);
  const [mlTrends, setMlTrends] = useState<TrendResponse | null>(null);

  const [selectedRange, setSelectedRange] = useState<number>(24);
  const [isRefreshing, setIsRefreshing] = useState<boolean>(false);
  const [isResolving, setIsResolving] = useState<boolean>(false);
  const [isRetraining, setIsRetraining] = useState<boolean>(false);
  const [connectionError, setConnectionError] = useState<string | null>(null);

  const fetchAllData = useCallback(async () => {
    try {
      setConnectionError(null);
      const [
        healthRes,
        systemRes,
        latestRes,
        historyRes,
        alertsRes,
        mlSumRes,
        mlAnomRes,
        mlTrendRes,
      ] = await Promise.allSettled([
        api.getHealth(),
        api.getSystemStatus(),
        api.getLatestReading(),
        api.getReadingsHistory(selectedRange, 100),
        api.getAlerts(),
        api.getMLSummary(),
        api.getMLAnomalies(100),
        api.getMLTrends(100),
      ]);

      if (healthRes.status === 'fulfilled') setHealth(healthRes.value);
      if (systemRes.status === 'fulfilled') setSystem(systemRes.value);
      if (latestRes.status === 'fulfilled') setReading(latestRes.value);
      if (historyRes.status === 'fulfilled') setHistory(historyRes.value);
      if (alertsRes.status === 'fulfilled') setAlerts(alertsRes.value);
      if (mlSumRes.status === 'fulfilled') setMlSummary(mlSumRes.value);
      if (mlAnomRes.status === 'fulfilled') setMlAnomalies(mlAnomRes.value);
      if (mlTrendRes.status === 'fulfilled') setMlTrends(mlTrendRes.value);

      // If health failed, flag connection warning
      if (healthRes.status === 'rejected') {
        setConnectionError('Backend server is not responding at http://127.0.0.1:8000. Ensure FastAPI is running.');
      }
    } catch (err: any) {
      setConnectionError(err.message || 'Error connecting to backend services.');
    }
  }, [selectedRange]);

  const handleManualRefresh = async () => {
    setIsRefreshing(true);
    await fetchAllData();
    setIsRefreshing(false);
  };

  const handleResolveAlert = async (alertId: number) => {
    setIsResolving(true);
    try {
      await api.resolveAlert(alertId);
      const updatedAlerts = await api.getAlerts();
      setAlerts(updatedAlerts);
    } catch (err: any) {
      console.error('Error resolving alert:', err);
    } finally {
      setIsResolving(false);
    }
  };

  const handleRetrainML = async () => {
    setIsRetraining(true);
    try {
      await api.trainMLModel();
      const [newSum, newAnom] = await Promise.all([
        api.getMLSummary(),
        api.getMLAnomalies(),
      ]);
      setMlSummary(newSum);
      setMlAnomalies(newAnom);
    } catch (err: any) {
      console.error('Retraining error:', err);
    } finally {
      setIsRetraining(false);
    }
  };

  // Initial load and auto-refresh polling interval (every 15s)
  useEffect(() => {
    fetchAllData();
    const interval = setInterval(() => {
      fetchAllData();
    }, 15000);
    return () => clearInterval(interval);
  }, [fetchAllData]);

  return (
    <div className="min-h-screen bg-slate-50 flex flex-col font-sans">
      {/* Top Header */}
      <Header
        health={health}
        system={system}
        activeTab={activeTab}
        setActiveTab={setActiveTab}
        onRefresh={handleManualRefresh}
        isRefreshing={isRefreshing}
      />

      {/* Main Container */}
      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-6 space-y-6">
        {/* Backend Connection Warning */}
        {connectionError && (
          <div className="p-4 rounded-xl bg-amber-50 border border-amber-300 text-amber-900 flex items-center justify-between shadow-xs">
            <div className="flex items-center space-x-3">
              <AlertCircle className="h-5 w-5 text-amber-600 shrink-0" />
              <div className="text-xs">
                <span className="font-bold">FastAPI Connection Note:</span> {connectionError}
              </div>
            </div>
            <button
              onClick={handleManualRefresh}
              className="text-xs px-3 py-1.5 rounded-lg bg-white border border-amber-300 hover:bg-amber-100 font-semibold transition-colors"
            >
              Retry
            </button>
          </div>
        )}

        {/* Tab 1: Dashboard Overview */}
        {activeTab === 'dashboard' && (
          <div className="space-y-6">
            <OverallStatusBanner reading={reading} system={system} />
            <DemoScenarioBar onScenarioInjected={fetchAllData} />
            <SensorCards reading={reading} />

            {/* Quick Historical Overview */}
            <HistoricalCharts
              readings={history}
              onRangeChange={(hours) => setSelectedRange(hours)}
              selectedRange={selectedRange}
            />
          </div>
        )}

        {/* Tab 2: Analytics & Trends */}
        {activeTab === 'analytics' && (
          <div className="space-y-6">
            <HistoricalCharts
              readings={history}
              onRangeChange={(hours) => setSelectedRange(hours)}
              selectedRange={selectedRange}
            />
            <SensorCards reading={reading} />
          </div>
        )}

        {/* Tab 3: Machine Learning & Anomaly Detection */}
        {activeTab === 'ml' && (
          <div className="space-y-6">
            <MLInsightsSection
              summary={mlSummary}
              anomalies={mlAnomalies}
              trends={mlTrends}
              onRetrain={handleRetrainML}
              isRetraining={isRetraining}
            />
          </div>
        )}

        {/* Tab 4: Alerts & Incidents */}
        {activeTab === 'alerts' && (
          <div className="space-y-6">
            <AlertsSection
              alerts={alerts}
              onResolve={handleResolveAlert}
              isResolving={isResolving}
            />
          </div>
        )}

        {/* Tab 5: AI Water Advisor Chatbot */}
        {activeTab === 'chatbot' && (
          <div className="space-y-6">
            <ChatbotPanel />
          </div>
        )}

        {/* Tab 6: Hardware & System Diagnostics */}
        {activeTab === 'diagnostics' && (
          <div className="space-y-6">
            <SystemDiagnostics
              system={system}
              health={health}
              reading={reading}
            />
          </div>
        )}
      </main>

      {/* Footer */}
      <footer className="mt-auto border-t border-slate-200 bg-white py-6">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 text-center text-xs text-slate-500 space-y-1.5">
          <p className="font-semibold text-slate-700">
            HydroSense • Smart Apartment Water Quality Monitor &amp; Anomaly Detection System
          </p>
          <p className="font-mono text-[11px] text-slate-400">
            Architecture: ESP32 (GPIO34, GPIO32, GPIO35-Reserved) ➔ OLED &amp; Buzzer ➔ ThingSpeak ➔ FastAPI ➔ SQLite / ML ➔ React
          </p>
          <p className="text-[10px] text-slate-400 pt-1">
            Compliant with WHO Guidelines &amp; EPA Standards for Domestic Drinking Water.
          </p>
        </div>
      </footer>
    </div>
  );
};

export default App;
