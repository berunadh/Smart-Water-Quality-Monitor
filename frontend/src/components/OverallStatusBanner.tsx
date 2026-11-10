import React from 'react';
import {
  ShieldAlert,
  ShieldCheck,
  AlertTriangle,
  Info,
  Clock,
  Wrench,
} from 'lucide-react';
import { SensorReading, WaterQualityEvaluation } from '../types';

interface OverallStatusBannerProps {
  reading: SensorReading | null;
  evaluation: WaterQualityEvaluation | null;
}

export const OverallStatusBanner: React.FC<OverallStatusBannerProps> = ({
  reading,
  evaluation,
}) => {
  const overallStatus = evaluation?.overall_status ?? 'NO_DATA';
  const severity = evaluation?.alert_severity ?? reading?.alert_severity ?? 0;
  const violated = evaluation?.violated_parameters ?? [];
  const isStale = reading?.is_stale ?? false;
  const lastSync = reading?.timestamp
    ? new Date(reading.timestamp).toLocaleTimeString()
    : 'Awaiting telemetry';

  let bannerBg = 'bg-emerald-50 border-emerald-200 text-emerald-900';
  let badgeBg = 'bg-emerald-100 text-emerald-800 border-emerald-300';
  let statusHeading = 'All Calibrated Parameters Within Limits';
  let badgeLabel = 'ACCEPTABLE';
  let Icon = ShieldCheck;

  if (overallStatus === 'CALIBRATION_PENDING') {
    bannerBg = 'bg-amber-50/70 border-amber-200 text-amber-950';
    badgeBg = 'bg-amber-100 text-amber-800 border-amber-300';
    statusHeading = 'Calibration Pending — Raw Voltages Active';
    badgeLabel = 'CAL PENDING';
    Icon = Wrench;
  } else if (overallStatus === 'WARNING') {
    bannerBg = 'bg-amber-50 border-amber-200 text-amber-950';
    badgeBg = 'bg-amber-100 text-amber-800 border-amber-300';
    statusHeading = 'Approaching Mode Threshold Limits';
    badgeLabel = 'WARNING';
    Icon = AlertTriangle;
  } else if (overallStatus === 'EXCEEDED' || severity === 1) {
    bannerBg = 'bg-amber-50 border-amber-300 text-amber-950';
    badgeBg = 'bg-amber-200 text-amber-900 border-amber-400';
    statusHeading = 'Threshold Exceeded';
    badgeLabel = 'ALERT';
    Icon = AlertTriangle;
  } else if (overallStatus === 'CRITICAL' || severity === 2) {
    bannerBg = 'bg-rose-50 border-rose-300 text-rose-950';
    badgeBg = 'bg-rose-100 text-rose-800 border-rose-300';
    statusHeading = 'Critical Threshold Violation';
    badgeLabel = 'CRITICAL';
    Icon = ShieldAlert;
  } else if (overallStatus === 'SENSOR_FAULT' || severity >= 3) {
    bannerBg = 'bg-purple-50 border-purple-200 text-purple-950';
    badgeBg = 'bg-purple-100 text-purple-800 border-purple-300';
    statusHeading = reading?.alert_messages || 'Sensor Fault or Over-Range Detected';
    badgeLabel = 'HARDWARE FAULT';
    Icon = ShieldAlert;
  } else if (overallStatus === 'NO_DATA') {
    bannerBg = 'bg-slate-100 border-slate-200 text-slate-800';
    badgeBg = 'bg-slate-200 text-slate-700 border-slate-300';
    statusHeading = 'Awaiting Telemetry';
    badgeLabel = 'NO DATA';
    Icon = Clock;
  }

  return (
    <div className="space-y-2.5">
      <div className={`p-4 rounded-xl border shadow-xs transition-all ${bannerBg}`}>
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div className="flex items-start sm:items-center space-x-3">
            <div className="p-2 rounded-lg bg-white/80 shadow-2xs shrink-0">
              <Icon className="h-5 w-5" />
            </div>
            <div>
              <div className="flex flex-wrap items-center gap-2">
                <span className={`text-[11px] px-2 py-0.5 rounded font-bold border uppercase tracking-wide ${badgeBg}`}>
                  {badgeLabel}
                </span>
                <span className="text-xs font-medium opacity-80">
                  {evaluation?.mode_label || 'Drinking Mode'}
                </span>
                {isStale && (
                  <span className="text-[11px] font-semibold px-2 py-0.5 rounded bg-amber-200 text-amber-900 border border-amber-300">
                    STALE (&gt;5m)
                  </span>
                )}
              </div>
              <h2 className="text-base font-bold mt-0.5 tracking-tight">
                {statusHeading}
              </h2>
              {violated.length > 0 && (
                <ul className="mt-1.5 space-y-0.5 text-xs font-medium list-disc list-inside">
                  {violated.map((v, i) => (
                    <li key={i}>{v}</li>
                  ))}
                </ul>
              )}
            </div>
          </div>

          <div className="flex items-center space-x-2 text-xs shrink-0">
            <div className="flex items-center space-x-1.5 bg-white/80 px-2.5 py-1.5 rounded-lg border border-slate-200/70 font-mono text-slate-700">
              <Clock className="h-3.5 w-3.5 text-slate-400" />
              <span>{lastSync}</span>
            </div>
            <span className="bg-white/80 px-2.5 py-1.5 rounded-lg border border-slate-200/70 font-mono text-slate-700 uppercase">
              {reading?.data_source || 'SIMULATED'}
            </span>
          </div>
        </div>
      </div>

      {/* Concise Potability / Mode Advisory */}
      <div className="bg-slate-50 border border-slate-200/80 rounded-lg px-3 py-2 text-[11px] text-slate-600 flex items-center space-x-2">
        <Info className="h-3.5 w-3.5 text-sky-600 shrink-0" />
        <span>
          {evaluation?.preliminary_disclaimer ||
            'Preliminary physicochemical monitoring only (pH, turbidity, TDS). Does not certify microbiological potability or replace laboratory testing.'}
        </span>
      </div>
    </div>
  );
};
