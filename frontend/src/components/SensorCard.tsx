import React from 'react';
import { CalibrationConfidence, WaterQualityEvaluation, WaterQualitySettings, SensorReading } from '../types';

interface SensorCardsProps {
  reading: SensorReading | null;
  evaluation: WaterQualityEvaluation | null;
  settings: WaterQualitySettings | null;
}

const getBadgeStyle = (status: string, provisional = false) => {
  switch (status) {
    case 'acceptable':
      return {
        cls: provisional ? 'bg-sky-50 text-sky-700 border-sky-200' : 'bg-emerald-50 text-emerald-700 border-emerald-200',
        label: provisional ? 'PROVISIONAL' : 'VALID',
      };
    case 'warning':
      return {
        cls: 'bg-amber-50 text-amber-700 border-amber-200',
        label: provisional ? 'WARNING (PROV)' : 'WARNING',
      };
    case 'exceeded':
      return {
        cls: 'bg-rose-50 text-rose-700 border-rose-200',
        label: provisional ? 'EXCEEDED (PROV)' : 'EXCEEDED',
      };
    case 'disconnected':
      return { cls: 'bg-purple-50 text-purple-700 border-purple-200', label: 'DISCONNECTED' };
    case 'dry':
      return { cls: 'bg-amber-50 text-amber-800 border-amber-200', label: 'DRY / NOT IMMERSED' };
    case 'fault':
      return { cls: 'bg-purple-50 text-purple-700 border-purple-200', label: 'FAULT' };
    case 'unavailable':
      return { cls: 'bg-slate-100 text-slate-600 border-slate-200', label: 'UNAVAILABLE' };
    case 'provisional':
      return { cls: 'bg-sky-50 text-sky-700 border-sky-200', label: 'MODEL PROV' };
    default:
      return { cls: 'bg-amber-50/70 text-amber-700 border-amber-200', label: 'CAL PENDING' };
  }
};

const confidenceLabel = (status?: CalibrationConfidence) => {
  switch (status) {
    case 'VERIFIED_CALIBRATION': return 'VERIFIED';
    case 'MODEL_BASED_PROVISIONAL': return 'MODEL PROV';
    case 'DEMONSTRATION_ESTIMATE': return 'DEMO ESTIMATE';
    case 'SENSOR_FAULT': return 'SENSOR FAULT';
    default: return 'UNCALIBRATED';
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

  const turbVoltage = reading?.turbidity_voltage ?? reading?.turbidity_board_voltage ?? 0;
  const tdsVoltage = reading?.tds_voltage ?? null;

  const phProvisional = Boolean(reading && ((reading.health_code & (1 << 12)) !== 0 || (!reading.ph_calibrated && phVal !== null)));
  const turbProvisional = Boolean(reading && ((reading.health_code & (1 << 13)) !== 0 || (!reading.turbidity_calibrated && turbVal !== null)));
  const tdsProvisional = Boolean(reading && ((reading.health_code & (1 << 11)) !== 0 || (!reading.tds_calibrated && tdsVal !== null)));

  const phPhysicalFault = phEval?.status === 'disconnected' || phEval?.status === 'fault' || phEval?.status === 'unavailable';
  const phCanDisplay = phVal !== null && !phPhysicalFault;
  const phBadge = phCanDisplay
    ? { cls: 'bg-sky-50 text-sky-700 border-sky-200', label: 'DISPLAY' }
    : phPhysicalFault
    ? getBadgeStyle(phEval?.status, phProvisional)
    : { cls: 'bg-slate-100 text-slate-600 border-slate-200', label: 'WAITING' };
  const turbBadge = getBadgeStyle(turbEval?.status ?? (turbVal !== null ? 'acceptable' : 'uncalibrated'), turbProvisional);
  const tdsBadge = getBadgeStyle(tdsEval?.status ?? (tdsVal !== null ? 'acceptable' : 'uncalibrated'), tdsProvisional);

  const turbConfidence = reading?.turbidity_calibration_status;
  const tdsConfidence = reading?.tds_calibration_status;

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
                <h3 className="text-sm font-semibold text-slate-800">pH</h3>
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
                {phCanDisplay
                  ? `${phVal.toFixed(2)}`
                  : phEval?.status === 'disconnected'
                  ? 'Disconnected'
                  : phEval?.status === 'fault' || phEval?.status === 'unavailable'
                  ? 'Unavailable'
                  : phEval?.message?.toLowerCase().includes('outside provisional')
                  ? 'Out of Range'
                  : '--'}
              </div>
              <div className="text-xs text-slate-500 mt-1">
                Limit: <span className="font-semibold text-slate-700">{phEval?.limit_text || `${profile?.ph_min.toFixed(1) ?? '6.5'}–${profile?.ph_max.toFixed(1) ?? '8.5'} pH`}</span>
                {evaluation?.q_ph !== null && evaluation?.q_ph !== undefined && (
                  <span className="ml-2 font-mono text-[11px] text-slate-500">(q={evaluation.q_ph.toFixed(0)})</span>
                )}
              </div>
            </div>
            <span className="text-xs font-mono text-slate-500">pH</span>
          </div>
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
                {turbVal !== null
                  ? `${turbVal.toFixed(2)}`
                  : turbEval?.status === 'disconnected'
                  ? 'Disconnected'
                  : turbEval?.status === 'fault' || turbEval?.status === 'unavailable'
                  ? 'Unavailable'
                  : turbEval?.message?.toLowerCase().includes('outside provisional')
                  ? 'Out of Range'
                  : 'Cal Pending'}
              </div>
              <div className="text-xs text-slate-500 mt-1">
                Limit: <span className="font-semibold text-slate-700">{turbEval?.limit_text || `≤ ${profile?.turbidity_max.toFixed(1) ?? '1.0'} NTU`}</span>
                {evaluation?.q_turb !== null && evaluation?.q_turb !== undefined && (
                  <span className="ml-2 font-mono text-[11px] text-slate-500">(q={evaluation.q_turb.toFixed(0)})</span>
                )}
              </div>
            </div>
            <span className="text-xs font-mono text-slate-500">NTU</span>
          </div>
        </div>

        <div className="mt-3 pt-2.5 border-t border-slate-100 flex items-center justify-between text-[11px] font-mono text-slate-500">
          <span>Board: {turbVoltage.toFixed(3)} V</span>
          <span>ADC: {(turbVoltage / 2.5).toFixed(3)} V</span>
        </div>
          <div className="mt-1 text-[10px] font-mono text-slate-400">Confidence: {confidenceLabel(turbConfidence)}</div>
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
                <p className="text-[11px] text-slate-400 font-mono">GPIO35 • Direct 3.3V • ~25°C nom.</p>
              </div>
            </div>
            <span className={`text-[10px] px-2 py-0.5 rounded-full font-bold border ${tdsBadge.cls}`}>
              {tdsBadge.label}
            </span>
          </div>

          <div className="mt-3 flex items-baseline justify-between">
            <div>
              <div className={`font-extrabold tracking-tight ${tdsVal !== null ? 'text-3xl text-slate-900' : 'text-xl text-slate-500'}`}>
                {tdsVal !== null
                  ? `${tdsVal.toFixed(0)}`
                  : tdsEval?.status === 'dry'
                  ? 'DRY / NOT IMMERSED'
                  : tdsEval?.status === 'disconnected'
                  ? 'Disconnected'
                  : tdsEval?.status === 'fault' || tdsEval?.status === 'unavailable'
                  ? 'Unavailable'
                  : 'Cal Pending'}
              </div>
              <div className="text-xs text-slate-500 mt-1">
                Limit: <span className="font-semibold text-slate-700">{tdsEval?.limit_text || `≤ ${profile?.tds_max.toFixed(0) ?? '500'} mg/L`}</span>
                {evaluation?.q_tds !== null && evaluation?.q_tds !== undefined && (
                  <span className="ml-2 font-mono text-[11px] text-slate-500">(q={evaluation.q_tds.toFixed(0)})</span>
                )}
              </div>
            </div>
            <span className="text-xs font-mono text-slate-500">mg/L</span>
          </div>
        </div>

        <div className="mt-3 pt-2.5 border-t border-slate-100 flex items-center justify-between text-[11px] font-mono text-slate-500">
          <span>ADC: {tdsVoltage !== null ? `${tdsVoltage.toFixed(3)} V` : 'N/A'}</span>
          <span>Multiplier: 1.0x (Direct)</span>
        </div>
          <div className="mt-1 text-[10px] font-mono text-slate-400">Confidence: {confidenceLabel(tdsConfidence)}</div>
      </div>
    </div>
  );
};
