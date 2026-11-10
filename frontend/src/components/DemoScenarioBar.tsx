import React, { useState } from 'react';
import {
  CheckCircle,
  AlertTriangle,
  AlertOctagon,
  Wrench,
  Clock,
  Sliders,
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
    id: 'normal' | 'warning' | 'critical' | 'uncalibrated' | 'sensor_fault' | 'stale';
    label: string;
    icon: React.ComponentType<{ className?: string }>;
    color: string;
    description: string;
  }> = [
    {
      id: 'normal',
      label: 'Normal',
      icon: CheckCircle,
      color: 'hover:bg-emerald-50 hover:text-emerald-700 hover:border-emerald-300 text-emerald-800 bg-white',
      description: 'pH ~7.28, Turbidity ~0.55 NTU, TDS ~220 mg/L',
    },
    {
      id: 'warning',
      label: 'Drift Alert',
      icon: AlertTriangle,
      color: 'hover:bg-amber-50 hover:text-amber-700 hover:border-amber-300 text-amber-800 bg-white',
      description: 'Turbidity ~2.85 NTU & TDS ~620 mg/L (triggers Drinking alert, normal in Regular)',
    },
    {
      id: 'critical',
      label: 'Critical',
      icon: AlertOctagon,
      color: 'hover:bg-rose-50 hover:text-rose-700 hover:border-rose-300 text-rose-800 bg-white',
      description: 'pH ~5.15, Turbidity ~18.5 NTU, TDS ~1350 mg/L',
    },
    {
      id: 'uncalibrated',
      label: 'Uncalibrated',
      icon: Sliders,
      color: 'hover:bg-sky-50 hover:text-sky-700 hover:border-sky-300 text-sky-800 bg-white',
      description: 'Null calibrated readings with raw ADC voltages (1.897V, 0.586V, 1.876V)',
    },
    {
      id: 'sensor_fault',
      label: 'Fault',
      icon: Wrench,
      color: 'hover:bg-purple-50 hover:text-purple-700 hover:border-purple-300 text-purple-800 bg-white',
      description: 'Over-range / disconnected probe fault',
    },
    {
      id: 'stale',
      label: 'Stale',
      icon: Clock,
      color: 'hover:bg-slate-100 hover:text-slate-800 hover:border-slate-300 text-slate-700 bg-white',
      description: 'Timestamp 45 minutes in the past',
    },
  ];

  const handleInject = async (
    scenarioId: 'normal' | 'warning' | 'critical' | 'uncalibrated' | 'sensor_fault' | 'stale'
  ) => {
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
    <div className="bg-slate-100/70 border border-slate-200/80 rounded-xl px-3.5 py-2.5 flex flex-col md:flex-row md:items-center justify-between gap-2">
      <span className="text-[11px] font-bold text-slate-600 uppercase tracking-wider shrink-0">
        Demo Test Scenarios:
      </span>
      <div className="grid grid-cols-3 sm:grid-cols-6 gap-1.5 w-full md:w-auto">
        {scenarios.map((sc) => {
          const Icon = sc.icon;
          const isLoading = injecting === sc.id;
          return (
            <button
              key={sc.id}
              onClick={() => handleInject(sc.id)}
              disabled={injecting !== null}
              title={sc.description}
              className={`flex items-center justify-center space-x-1.5 px-2.5 py-1.5 rounded-lg border border-slate-200 text-xs font-medium transition-all disabled:opacity-50 ${sc.color}`}
            >
              <Icon className={`h-3.5 w-3.5 shrink-0 ${isLoading ? 'animate-spin' : ''}`} />
              <span>{sc.label}</span>
            </button>
          );
        })}
      </div>
    </div>
  );
};
