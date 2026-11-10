import React from 'react';
import { WaterQualityEvaluation, WaterQualitySettings, SensorReading } from '../types';

interface SensorCardsProps {
  reading: SensorReading | null;
  evaluation: WaterQualityEvaluation | null;
  settings: WaterQualitySettings | null;
}

const getBadgeStyle = (status: string) => {
  switch (status) {
    case 'acceptable':
      return { cls: 'bg-emerald-50 text-emerald-700 border-emerald-200', label: 'ACCEPTABLE' };
    case 'warning':
      return { cls: 'bg-amber-50 text-amber-700 border-amber-200', label: 'WARNING' };
    case 'exceeded':
      return { cls: 'bg-rose-50 text-rose-700 border-rose-200', label: 'EXCEEDED' };
    case 'fault':
      return { cls: 'bg-purple-50 text-purple-700 border-purple-200', label: 'FAULT' };
    case 'unavailable':
      return { cls: 'bg-slate-100 text-slate-600 border-slate-200', label: 'UNAVAILABLE' };
    default:
      return { cls: 'bg-amber-50/70 text-amber-700 border-amber-200', label: 'NOT CALIBRATED' };
  }
};

export const SensorCards: React.FC<SensorCardsProps> = ({
  reading,
  evaluation,
  settings,
}) => {
  const profile = settings?.active_profile;
  const phEval = evaluation?.parameter_evaluations?.ph;
  const turbEval = evaluation?.parameter_evaluations?.turbidity;
  const tdsEval = evaluation?.parameter_evaluations?.tds;

  const phVal = reading?.ph ?? null;
  const turbVal = reading?.turbidity ?? null;
  const tdsVal = reading?.tds ?? null;

  const phVoltage = reading?.ph_voltage ?? reading?.ph_board_voltage ?? 0;
  const turbVoltage = reading?.turbidity_voltage ?? reading?.turbidity_board_voltage ?? 0;
  const tdsVoltage = reading?.tds_voltage ?? null;

  const phBadge = getBadgeStyle(phEval?.status ?? (phVal !== null ? 'acceptable' : 'uncalibrated'));
  const turbBadge = getBadgeStyle(turbEval?.status ?? (turbVal !== null ? 'acceptable' : 'uncalibrated'));
  const tdsBadge = getBadgeStyle(tdsEval?.status ?? (tdsVal !== null ? 'acceptable' : 'uncalibrated'));

  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
      {/* 1. pH Sensor */}
      <div className="bg-white rounded-xl border border-slate-200/90 p-4 shadow-xs flex flex-col justify-between">
        <div>
          <div className="flex items-center justify-between pb-2.5 border-b border-slate-100">
            <div className="flex items-center space-x-2">
              <div className="h-7 w-7 rounded-lg bg-sky-50 text-sky-700 flex items-center justify-center font-bold text-xs">
                pH
              </div>
              <div>
                <h3 className="text-sm font-semibold text-slate-800">pH Level</h3>
                <p className="text-[11px] text-slate-400 font-mono">GPIO34 • ÷2.5 Divider</p>
              </div>
            </div>
            <span className={`text-[10px] px-2 py-0.5 rounded-full font-bold border ${phBadge.cls}`}>
              {phBadge.label}
            </span>
          </div>

          <div className="mt-3 flex items-baseline justify-between">
            <div>
              <div className="text-3xl font-extrabold text-slate-900 tracking-tight">
                {phVal !== null ? `${phVal.toFixed(2)}` : 'Not Calibrated'}
              </div>
              <div className="text-xs text-slate-500 mt-1">
                Limit: <span className="font-semibold text-slate-700">{phEval?.limit_text || `${profile?.ph_min.toFixed(1) ?? '6.5'}–${profile?.ph_max.toFixed(1) ?? '8.5'} pH`}</span>
              </div>
            </div>
            <span className="text-xs font-mono text-slate-500">pH</span>
          </div>
        </div>

        <div className="mt-3 pt-2.5 border-t border-slate-100 flex items-center justify-between text-[11px] font-mono text-slate-500">
          <span>Board: {phVoltage.toFixed(3)} V</span>
          <span>ADC: {(phVoltage / 2.5).toFixed(3)} V</span>
        </div>
      </div>

      {/* 2. Turbidity Sensor */}
      <div className="bg-white rounded-xl border border-slate-200/90 p-4 shadow-xs flex flex-col justify-between">
        <div>
          <div className="flex items-center justify-between pb-2.5 border-b border-slate-100">
            <div className="flex items-center space-x-2">
              <div className="h-7 w-7 rounded-lg bg-cyan-50 text-cyan-700 flex items-center justify-center font-bold text-xs">
                NTU
              </div>
              <div>
                <h3 className="text-sm font-semibold text-slate-800">Turbidity</h3>
                <p className="text-[11px] text-slate-400 font-mono">GPIO32 • ÷2.5 Divider</p>
              </div>
            </div>
            <span className={`text-[10px] px-2 py-0.5 rounded-full font-bold border ${turbBadge.cls}`}>
              {turbBadge.label}
            </span>
          </div>

          <div className="mt-3 flex items-baseline justify-between">
            <div>
              <div className="text-3xl font-extrabold text-slate-900 tracking-tight">
                {turbVal !== null ? `${turbVal.toFixed(2)}` : 'Not Calibrated'}
              </div>
              <div className="text-xs text-slate-500 mt-1">
                Limit: <span className="font-semibold text-slate-700">{turbEval?.limit_text || `≤ ${profile?.turbidity_max.toFixed(1) ?? '1.0'} NTU`}</span>
              </div>
            </div>
            <span className="text-xs font-mono text-slate-500">NTU</span>
          </div>
        </div>

        <div className="mt-3 pt-2.5 border-t border-slate-100 flex items-center justify-between text-[11px] font-mono text-slate-500">
          <span>Board: {turbVoltage.toFixed(3)} V</span>
          <span>ADC: {(turbVoltage / 2.5).toFixed(3)} V</span>
        </div>
      </div>

      {/* 3. TDS Sensor (GPIO35 Direct 3.3V) */}
      <div className="bg-white rounded-xl border border-slate-200/90 p-4 shadow-xs flex flex-col justify-between">
        <div>
          <div className="flex items-center justify-between pb-2.5 border-b border-slate-100">
            <div className="flex items-center space-x-2">
              <div className="h-7 w-7 rounded-lg bg-emerald-50 text-emerald-700 flex items-center justify-center font-bold text-xs">
                TDS
              </div>
              <div>
                <h3 className="text-sm font-semibold text-slate-800">Total Dissolved Solids</h3>
                <p className="text-[11px] text-slate-400 font-mono">GPIO35 • Direct 3.3V</p>
              </div>
            </div>
            <span className={`text-[10px] px-2 py-0.5 rounded-full font-bold border ${tdsBadge.cls}`}>
              {tdsBadge.label}
            </span>
          </div>

          <div className="mt-3 flex items-baseline justify-between">
            <div>
              <div className={`font-extrabold tracking-tight ${tdsVal !== null ? 'text-3xl text-slate-900' : 'text-2xl text-slate-500'}`}>
                {tdsVal !== null ? `${tdsVal.toFixed(0)}` : 'Not Calibrated'}
              </div>
              <div className="text-xs text-slate-500 mt-1">
                Limit: <span className="font-semibold text-slate-700">{tdsEval?.limit_text || `≤ ${profile?.tds_max.toFixed(0) ?? '500'} mg/L`}</span>
              </div>
            </div>
            <span className="text-xs font-mono text-slate-500">mg/L</span>
          </div>
        </div>

        <div className="mt-3 pt-2.5 border-t border-slate-100 flex items-center justify-between text-[11px] font-mono text-slate-500">
          <span>ADC: {tdsVoltage !== null ? `${tdsVoltage.toFixed(3)} V` : 'N/A'}</span>
          <span>Multiplier: 1.0x (Direct)</span>
        </div>
      </div>
    </div>
  );
};
