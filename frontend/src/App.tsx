import React, { useState, useEffect, useCallback } from 'react';
import { Header } from './components/Header';
import { ModeSelectorBar } from './components/ModeSelectorBar';
import { OverallStatusBanner } from './components/OverallStatusBanner';
import { SensorCards } from './components/SensorCard';
import { HistoricalCharts } from './components/HistoricalCharts';
import { AlertsSection } from './components/AlertsSection';
import { MLInsightsSection } from './components/MLInsightsSection';
import { ThresholdSettingsPanel } from './components/ThresholdSettingsPanel';
import { SystemDiagnostics } from './components/SystemDiagnostics';
import { ChatbotPanel } from './components/ChatbotPanel';
import { DemoScenarioBar } from './components/DemoScenarioBar';
import { SampleProfileSelector } from './components/SampleProfileSelector';
import { api } from './services/api';
import {
  BackendHealth,
  SystemHealth,
  SensorReading,
  AlertSummary,
  MLSummary,
  AnomalyResponse,
  TrendResponse,
  WaterQualitySettings,
  WaterQualityMode,
  CalibrationStatusDetail,
  SampleProfileState,
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
  const [wqSettings, setWqSettings] = useState<WaterQualitySettings | null>(null);
  const [calibrationStatus, setCalibrationStatus] = useState<CalibrationStatusDetail | null>(null);
  const [sampleProfile, setSampleProfile] = useState<SampleProfileState | null>(null);

  const [selectedRange, setSelectedRange] = useState<number>(24);
  const [isRefreshing, setIsRefreshing] = useState<boolean>(false);
  const [isResolving, setIsResolving] = useState<boolean>(false);
  const [isRetraining, setIsRetraining] = useState<boolean>(false);
  const [isSwitchingMode, setIsSwitchingMode] = useState<boolean>(false);
  const [connectionError, setConnectionError] = useState<string | null>(null);

  const fetchAllData = useCallback(async (syncCloud = false) => {
    try {
      setConnectionError(null);
      if (syncCloud && health?.operating_mode !== 'demo') {
        try {
          await api.syncThingSpeak(50);
        } catch {
          // Keep dashboard responsive even if ThingSpeak API is temporarily unreachable
        }
      }
      const [
        healthRes,
        systemRes,
        latestRes,
        historyRes,
        alertsRes,
        mlSumRes,
        mlAnomRes,
        mlTrendRes,
        settingsRes,
        calRes,
        profileRes,
      ] = await Promise.allSettled([
        api.getHealth(),
        api.getSystemStatus(),
        api.getLatestReading(),
        api.getReadingsHistory(selectedRange, 100),
        api.getAlerts(),
        api.getMLSummary(),
        api.getMLAnomalies(100),
        api.getMLTrends(100),
        api.getWaterQualitySettings(),
        api.getCalibrationStatus(),
        api.getSampleProfile(),
      ]);

      if (healthRes.status === 'fulfilled') setHealth(healthRes.value);
      if (systemRes.status === 'fulfilled') setSystem(systemRes.value);
      if (latestRes.status === 'fulfilled') setReading(latestRes.value);
      if (historyRes.status === 'fulfilled') setHistory(historyRes.value);
      if (alertsRes.status === 'fulfilled') setAlerts(alertsRes.value);
      if (mlSumRes.status === 'fulfilled') setMlSummary(mlSumRes.value);
      if (mlAnomRes.status === 'fulfilled') setMlAnomalies(mlAnomRes.value);
      if (mlTrendRes.status === 'fulfilled') setMlTrends(mlTrendRes.value);
      if (settingsRes.status === 'fulfilled') setWqSettings(settingsRes.value);
      if (calRes.status === 'fulfilled') setCalibrationStatus(calRes.value);
      if (profileRes.status === 'fulfilled') setSampleProfile(profileRes.value);

      if (healthRes.status === 'rejected') {
        setConnectionError('Backend server not responding at http://127.0.0.1:8000.');
      }
    } catch (err: any) {
      setConnectionError(err.message || 'Error connecting to backend services.');
    }
  }, [selectedRange, health?.operating_mode]);

  const handleManualRefresh = async () => {
    setIsRefreshing(true);
    await fetchAllData(true);
    setIsRefreshing(false);
  };

  const handleModeSwitch = async (mode: WaterQualityMode) => {
    setIsSwitchingMode(true);
    try {
      const updated = await api.switchWaterQualityMode(mode);
      setWqSettings(updated);
      await fetchAllData();
    } catch (err: any) {
      console.error('Error switching water quality mode:', err);
    } finally {
      setIsSwitchingMode(false);
    }
  };

  const handleProfileChange = async (profile: SampleProfileState['selected_profile'], ph?: number) => {
    const updated = await api.setSampleProfile(profile, ph);
    setSampleProfile(updated);
    await fetchAllData(false);
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

  useEffect(() => {
    fetchAllData(true);
    const interval = setInterval(() => {
      fetchAllData(true);
    }, 20000);
    return () => clearInterval(interval);
  }, [fetchAllData]);

  const activeWaterMode: WaterQualityMode = wqSettings?.active_mode ?? 'drinking';
  const latestEval = wqSettings?.latest_evaluation ?? null;

  return (
    <div className="min-h-screen bg-slate-50 flex flex-col font-sans">
      <Header
        health={health}
        system={system}
        activeWaterMode={activeWaterMode}
        activeTab={activeTab}
        setActiveTab={setActiveTab}
        onRefresh={handleManualRefresh}
        isRefreshing={isRefreshing}
      />

      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-5 space-y-5">
        {connectionError && (
          <div className="p-3.5 rounded-xl bg-amber-50 border border-amber-300 text-amber-900 flex items-center justify-between shadow-2xs">
            <div className="flex items-center space-x-2.5 text-xs">
              <AlertCircle className="h-4 w-4 text-amber-600 shrink-0" />
              <span><strong>Backend Connection:</strong> {connectionError}</span>
            </div>
            <button
              onClick={handleManualRefresh}
              className="text-xs px-3 py-1 rounded-lg bg-white border border-amber-300 hover:bg-amber-100 font-semibold"
            >
              Retry
            </button>
          </div>
        )}

        {/* Mode Selector visible on Dashboard, Analytics, and Alerts */}
        {['dashboard', 'analytics', 'alerts'].includes(activeTab) && (
          <ModeSelectorBar
            settings={wqSettings}
            onModeChange={handleModeSwitch}
            isSwitching={isSwitchingMode}
            onOpenSettings={() => setActiveTab('settings')}
          />
        )}

        {/* Tab 1: Dashboard Overview */}
        {activeTab === 'dashboard' && (
          <div className="space-y-5">
            <OverallStatusBanner reading={reading} evaluation={latestEval} />
            {health?.operating_mode === 'demo' && (
              <><SampleProfileSelector state={sampleProfile} onChange={handleProfileChange} /><DemoScenarioBar onScenarioInjected={fetchAllData} /></>
            )}
            <SensorCards reading={reading} evaluation={latestEval} settings={wqSettings} />
            <HistoricalCharts
              readings={history}
              onRangeChange={(hours) => setSelectedRange(hours)}
              selectedRange={selectedRange}
              activeProfile={wqSettings?.active_profile}
            />
          </div>
        )}

        {/* Tab 2: Analytics */}
        {activeTab === 'analytics' && (
          <div className="space-y-5">
            <HistoricalCharts
              readings={history}
              onRangeChange={(hours) => setSelectedRange(hours)}
              selectedRange={selectedRange}
              activeProfile={wqSettings?.active_profile}
            />
            <SensorCards reading={reading} evaluation={latestEval} settings={wqSettings} />
          </div>
        )}

        {/* Tab 3: Machine Learning */}
        {activeTab === 'ml' && (
          <MLInsightsSection
            summary={mlSummary}
            anomalies={mlAnomalies}
            trends={mlTrends}
            onRetrain={handleRetrainML}
            isRetraining={isRetraining}
          />
        )}

        {/* Tab 4: Alerts */}
        {activeTab === 'alerts' && (
          <AlertsSection
            alerts={alerts}
            onResolve={handleResolveAlert}
            isResolving={isResolving}
          />
        )}

        {/* Tab 5: AI Advisor */}
        {activeTab === 'chatbot' && <ChatbotPanel />}

        {/* Tab 6: Thresholds & Calibration */}
        {activeTab === 'settings' && (
          <ThresholdSettingsPanel
            settings={wqSettings}
            calibration={calibrationStatus}
            onSettingsUpdated={(updated) => {
              setWqSettings(updated);
              fetchAllData();
            }}
          />
        )}

        {/* Tab 7: Diagnostics */}
        {activeTab === 'diagnostics' && (
          <SystemDiagnostics
            system={system}
            health={health}
            reading={reading}
          />
        )}
      </main>

      <footer className="mt-auto border-t border-slate-200 bg-white py-4">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 flex flex-col sm:flex-row items-center justify-between text-[11px] text-slate-500 gap-2">
          <span className="font-medium text-slate-700">HydroSense Smart Water Quality Monitor</span>
          <span className="font-mono text-slate-400">
            ESP32 (GPIO34/32/35) → ThingSpeak → FastAPI / SQLite / ML → React
          </span>
        </div>
      </footer>
    </div>
  );
};

export default App;
