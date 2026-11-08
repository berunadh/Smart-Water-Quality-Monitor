import React from 'react';
import {
  ShieldAlert,
  ShieldCheck,
  AlertTriangle,
  Info,
  Clock,
  Sparkles,
} from 'lucide-react';
import { SensorReading, SystemHealth } from '../types';

interface OverallStatusBannerProps {
  reading: SensorReading | null;
  system: SystemHealth | null;
}

export const OverallStatusBanner: React.FC<OverallStatusBannerProps> = ({
  reading,
  system,
}) => {
  const severity = reading?.alert_severity ?? 0;
  const isStale = reading?.is_stale ?? false;
  const lastSync = reading?.timestamp
    ? new Date(reading.timestamp).toLocaleTimeString()
    : 'Waiting for stream';

  // Config based on alert severity
  let bannerBg = 'bg-emerald-50 border-emerald-200 text-emerald-900';
  let badgeBg = 'bg-emerald-100 text-emerald-800 border-emerald-300';
  let statusText = 'SYSTEM NORMAL — WATER PARAMETERS WITHIN RANGE';
  let Icon = ShieldCheck;

  if (severity === 1) {
    bannerBg = 'bg-amber-50 border-amber-200 text-amber-900';
    badgeBg = 'bg-amber-100 text-amber-800 border-amber-300';
    statusText = `WARNING: ${reading?.alert_messages || 'ELEVATED READINGS DETECTED'}`;
    Icon = AlertTriangle;
  } else if (severity === 2) {
    bannerBg = 'bg-rose-50 border-rose-300 text-rose-950';
    badgeBg = 'bg-rose-100 text-rose-800 border-rose-300';
    statusText = `CRITICAL: ${reading?.alert_messages || 'WATER PARAMETERS EXCEED SAFETY LIMITS'}`;
    Icon = ShieldAlert;
  } else if (severity >= 3) {
    bannerBg = 'bg-purple-50 border-purple-200 text-purple-900';
    badgeBg = 'bg-purple-100 text-purple-800 border-purple-300';
    statusText = `HARDWARE FAULT: ${reading?.alert_messages || 'SENSOR OR DIVIDER DISCONNECTED'}`;
    Icon = ShieldAlert;
  }

  return (
    <div className="space-y-3">
      {/* Primary Status Banner */}
      <div className={`p-4 rounded-xl border shadow-sm transition-all ${bannerBg}`}>
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div className="flex items-start sm:items-center space-x-3">
            <div className="p-2 rounded-lg bg-white/80 shadow-xs shrink-0">
              <Icon className="h-6 w-6" />
            </div>
            <div>
              <div className="flex items-center space-x-2">
                <span className={`text-xs px-2 py-0.5 rounded font-bold border tracking-wide uppercase ${badgeBg}`}>
                  {severity === 0 ? 'Normal' : severity === 1 ? 'Warning' : severity === 2 ? 'Critical' : 'Fault'}
                </span>
                <span className="text-xs font-medium text-slate-500">
                  Node: {reading?.device_id || 'esp32-water-monitor-01'} • {system?.overall_status || 'ONLINE'}
                </span>
                {isStale && (
                  <span className="text-xs font-semibold px-2 py-0.5 rounded bg-amber-200 text-amber-900 border border-amber-300">
                    STALE DATA (&gt;5m)
                  </span>
                )}
              </div>
              <h2 className="text-base font-semibold mt-0.5 tracking-tight">
                {statusText}
              </h2>
            </div>
          </div>

          <div className="flex items-center space-x-4 text-xs shrink-0">
            <div className="flex items-center space-x-1.5 text-slate-600 bg-white/70 px-3 py-1.5 rounded-lg border border-slate-200/60 shadow-2xs">
              <Clock className="h-3.5 w-3.5 text-slate-400" />
              <span>Last Reading:</span>
              <span className="font-semibold text-slate-800 font-mono">{lastSync}</span>
            </div>

            <div className="flex items-center space-x-1.5 text-slate-600 bg-white/70 px-3 py-1.5 rounded-lg border border-slate-200/60 shadow-2xs">
              <Sparkles className="h-3.5 w-3.5 text-sky-500" />
              <span>Source:</span>
              <span className="font-semibold text-slate-800 uppercase font-mono">
                {reading?.data_source || 'SIMULATED'}
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* Mandatory Drinking Potability Disclaimer */}
      <div className="bg-slate-50 border border-slate-200/90 rounded-lg p-3 text-xs text-slate-600 flex items-start space-x-2.5">
        <Info className="h-4 w-4 text-sky-600 shrink-0 mt-0.5" />
        <div className="leading-relaxed">
          <span className="font-semibold text-slate-700">Health &amp; Drinking Safety Disclaimer:</span>{' '}
          Online physical sensors (pH, optical turbidity, TDS) measure bulk physical characteristics in real time.
          Normal readings do <strong className="text-slate-800">NOT</strong> certify water as microbiologically potable or free of pathogens, heavy metals, or toxic organic compounds.
          Never consume suspect water without certified laboratory bacteriological verification.
        </div>
      </div>
    </div>
  );
};
