import React from 'react';
import {
  Droplets,
  Activity,
  Wifi,
  WifiOff,
  Cloud,
  RefreshCw,
  AlertTriangle,
  Bot,
  BarChart3,
  Cpu,
  Layers,
  SlidersHorizontal,
} from 'lucide-react';
import { BackendHealth, SystemHealth, WaterQualityMode } from '../types';

interface HeaderProps {
  health: BackendHealth | null;
  system: SystemHealth | null;
  activeWaterMode: WaterQualityMode;
  activeTab: string;
  setActiveTab: (tab: string) => void;
  onRefresh: () => void;
  isRefreshing: boolean;
}

export const Header: React.FC<HeaderProps> = ({
  health,
  system,
  activeWaterMode,
  activeTab,
  setActiveTab,
  onRefresh,
  isRefreshing,
}) => {
  const isDemo = health?.operating_mode === 'demo';
  const isLive = health?.data_freshness === 'LIVE';
  const isCloudConnected =
    health?.cloud_connectivity === 'CONNECTED' ||
    (isDemo && health?.cloud_connectivity?.includes('DEMO'));

  const navItems = [
    { id: 'dashboard', label: 'Dashboard', icon: Activity },
    { id: 'analytics', label: 'Analytics', icon: BarChart3 },
    { id: 'ml', label: 'ML Insights', icon: Layers },
    { id: 'alerts', label: 'Alerts', icon: AlertTriangle },
    { id: 'chatbot', label: 'AI Advisor', icon: Bot },
    { id: 'settings', label: 'Thresholds & Cal', icon: SlidersHorizontal },
    { id: 'diagnostics', label: 'Diagnostics', icon: Cpu },
  ];

  return (
    <header className="sticky top-0 z-40 bg-white/95 backdrop-blur border-b border-slate-200 shadow-xs">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-14">
          {/* Brand Identity */}
          <div className="flex items-center space-x-2.5">
            <div className="h-9 w-9 rounded-lg bg-gradient-to-tr from-sky-600 to-cyan-500 flex items-center justify-center text-white shadow-xs">
              <Droplets className="h-5 w-5" />
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <h1 className="text-base sm:text-lg font-bold text-slate-900 tracking-tight">
                HydroSense
              </h1>
              <span
                className={`text-[11px] px-2 py-0.5 rounded-full font-semibold border ${
                  activeWaterMode === 'drinking'
                    ? 'bg-sky-50 text-sky-700 border-sky-200'
                    : 'bg-teal-50 text-teal-700 border-teal-200'
                }`}
              >
                {activeWaterMode === 'drinking' ? 'DRINKING MODE' : 'REGULAR USAGE'}
              </span>
              <span
                className={`text-[11px] px-2 py-0.5 rounded-full font-semibold border ${
                  isDemo
                    ? 'bg-amber-50 text-amber-800 border-amber-200'
                    : 'bg-emerald-50 text-emerald-800 border-emerald-200'
                }`}
              >
                {isDemo ? 'DEMO STREAM' : 'HARDWARE LIVE'}
              </span>
            </div>
          </div>

          {/* Connectivity & Refresh */}
          <div className="flex items-center space-x-2.5">
            <div className="hidden md:flex items-center space-x-2 px-3 py-1 rounded-lg bg-slate-50 border border-slate-200 text-xs">
              <span className="flex items-center space-x-1.5 text-slate-600">
                <Cloud className="h-3.5 w-3.5 text-sky-500" />
                <span className={isCloudConnected ? 'font-semibold text-emerald-600' : 'font-semibold text-amber-600'}>
                  {isDemo ? 'Simulated' : health?.cloud_connectivity || 'Checking'}
                </span>
              </span>
              <span className="text-slate-300">|</span>
              <span className="flex items-center space-x-1.5">
                {system?.wifi_connected ? (
                  <Wifi className="h-3.5 w-3.5 text-emerald-500" />
                ) : (
                  <WifiOff className="h-3.5 w-3.5 text-slate-400" />
                )}
                <span
                  className={`inline-block w-2 h-2 rounded-full ${
                    isLive ? 'bg-emerald-500 animate-pulse' : 'bg-amber-400'
                  }`}
                />
                <span className="text-slate-600 font-mono text-[11px]">
                  {health?.data_freshness || 'SYNC'}
                </span>
              </span>
            </div>

            <button
              onClick={onRefresh}
              disabled={isRefreshing}
              title="Refresh telemetry"
              className="p-1.5 rounded-lg text-slate-600 hover:text-sky-600 hover:bg-slate-100 transition-colors border border-slate-200 disabled:opacity-50"
            >
              <RefreshCw className={`h-4 w-4 ${isRefreshing ? 'animate-spin text-sky-600' : ''}`} />
            </button>
          </div>
        </div>

        {/* Navigation Tabs */}
        <div className="flex space-x-1 overflow-x-auto py-1.5 -mb-px border-t border-slate-100">
          {navItems.map((item) => {
            const Icon = item.icon;
            const isActive = activeTab === item.id;
            return (
              <button
                key={item.id}
                onClick={() => setActiveTab(item.id)}
                className={`flex items-center space-x-1.5 px-3 py-1.5 text-xs sm:text-sm font-medium rounded-lg transition-all whitespace-nowrap ${
                  isActive
                    ? 'bg-sky-50 text-sky-700 shadow-2xs border border-sky-200/80'
                    : 'text-slate-600 hover:text-slate-900 hover:bg-slate-100/70 border border-transparent'
                }`}
              >
                <Icon className={`h-4 w-4 ${isActive ? 'text-sky-600' : 'text-slate-400'}`} />
                <span>{item.label}</span>
              </button>
            );
          })}
        </div>
      </div>
    </header>
  );
};
