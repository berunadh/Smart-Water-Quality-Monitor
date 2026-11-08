import React, { useState } from 'react';
import {
  CheckCircle,
  AlertTriangle,
  AlertOctagon,
  Wrench,
  Clock,
  Sparkles,
} from 'lucide-react';
import { api } from '../services/api';

interface DemoScenarioBarProps {
  onScenarioInjected: () => void;
}

export const DemoScenarioBar: React.FC<DemoScenarioBarProps> = ({
  onScenarioInjected,
}) => {
  const [injecting, setInjecting] = useState<string | null>(null);

  const scenarios: Array<{
    id: 'normal' | 'warning' | 'critical' | 'sensor_fault' | 'stale';
    label: string;
    icon: React.ComponentType<{ className?: string }>;
    color: string;
    description: string;
  }> = [
    {
      id: 'normal',
      label: 'Normal Water',
      icon: CheckCircle,
      color: 'hover:bg-emerald-50 hover:text-emerald-700 hover:border-emerald-300 text-emerald-800 bg-white',
      description: 'pH ~7.2, Turbidity ~1.8 NTU, Severity 0',
    },
    {
      id: 'warning',
      label: 'Warning (Drift)',
      icon: AlertTriangle,
      color: 'hover:bg-amber-50 hover:text-amber-700 hover:border-amber-300 text-amber-800 bg-white',
      description: 'pH ~6.3, Turbidity ~7.5 NTU, Severity 1',
    },
    {
      id: 'critical',
      label: 'Critical Excursion',
      icon: AlertOctagon,
      color: 'hover:bg-rose-50 hover:text-rose-700 hover:border-rose-300 text-rose-800 bg-white',
      description: 'pH ~9.4, Turbidity ~22.0 NTU, Severity 2 (Buzzer)',
    },
    {
      id: 'sensor_fault',
      label: 'Hardware Fault',
      icon: Wrench,
      color: 'hover:bg-purple-50 hover:text-purple-700 hover:border-purple-300 text-purple-800 bg-white',
      description: 'Disconnected divider or out-of-bounds voltage, Severity 3',
    },
    {
      id: 'stale',
      label: 'Stale Telemetry',
      icon: Clock,
      color: 'hover:bg-slate-100 hover:text-slate-800 hover:border-slate-300 text-slate-700 bg-white',
      description: 'Simulates 15m communication loss from sensor node',
    },
  ];

  const handleInject = async (scenarioId: 'normal' | 'warning' | 'critical' | 'sensor_fault' | 'stale') => {
    setInjecting(scenarioId);
    try {
      await api.injectDemo(scenarioId);
      onScenarioInjected();
    } catch (err: any) {
      console.error('Failed to inject scenario:', err);
    } finally {
      setInjecting(null);
    }
  };

  return (
    <div className="bg-slate-100/80 border border-slate-200/90 rounded-xl p-3.5 shadow-2xs">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 mb-2.5">
        <div className="flex items-center space-x-2">
          <Sparkles className="h-4 w-4 text-sky-600" />
          <span className="text-xs font-bold text-slate-800 uppercase tracking-wide">
            Live Demonstration Controller
          </span>
          <span className="text-[11px] text-slate-500">
            Inject scenarios to test dashboard alerts and ML detectors
          </span>
        </div>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-5 gap-2">
        {scenarios.map((sc) => {
          const Icon = sc.icon;
          const isLoading = injecting === sc.id;
          return (
            <button
              key={sc.id}
              onClick={() => handleInject(sc.id)}
              disabled={injecting !== null}
              title={sc.description}
              className={`flex items-center justify-center space-x-1.5 px-3 py-2 rounded-lg border border-slate-200 text-xs font-semibold transition-all shadow-2xs disabled:opacity-50 ${sc.color}`}
            >
              <Icon className="h-3.5 w-3.5 shrink-0" />
              <span>{isLoading ? 'Injecting...' : sc.label}</span>
            </button>
          );
        })}
      </div>
    </div>
  );
};
