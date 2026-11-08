import React from 'react';
import {
  Zap,
  Info,
} from 'lucide-react';
import { SensorReading } from '../types';

interface SensorCardProps {
  reading: SensorReading | null;
}

export const SensorCards: React.FC<SensorCardProps> = ({ reading }) => {
  const phVal = reading?.ph ?? null;
  const turbVal = reading?.turbidity ?? null;
  const tdsVal = reading?.tds ?? null; // STRICT: MUST BE NULL, NEVER ZERO

  const phVoltage = reading?.ph_voltage ?? (reading?.ph_board_voltage ?? 0);
  const turbVoltage = reading?.turbidity_voltage ?? (reading?.turbidity_board_voltage ?? 0);

  // pH Status Evaluation
  let phStatus: 'normal' | 'warning' | 'critical' | 'uncalibrated' = 'uncalibrated';
  if (phVal !== null) {
    if (phVal >= 6.5 && phVal <= 8.5) {
      phStatus = 'normal';
    } else if ((phVal >= 6.0 && phVal < 6.5) || (phVal > 8.5 && phVal <= 9.0)) {
      phStatus = 'warning';
    } else {
      phStatus = 'critical';
    }
  }

  // Turbidity Status Evaluation (< 5 NTU is acceptable per WHO / EPA drinking standard)
  let turbStatus: 'normal' | 'warning' | 'critical' | 'uncalibrated' = 'uncalibrated';
  if (turbVal !== null) {
    if (turbVal <= 5.0) {
      turbStatus = 'normal';
    } else if (turbVal <= 10.0) {
      turbStatus = 'warning';
    } else {
      turbStatus = 'critical';
    }
  }

  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
      {/* 1. pH Sensor Card */}
      <div className="bg-white rounded-xl border border-slate-200/90 p-5 shadow-xs hover:shadow-md transition-shadow relative overflow-hidden">
        <div className="flex items-center justify-between pb-3 border-b border-slate-100">
          <div className="flex items-center space-x-2">
            <div className="h-8 w-8 rounded-lg bg-sky-50 text-sky-600 flex items-center justify-center font-bold text-xs">
              pH
            </div>
            <div>
              <h3 className="text-sm font-semibold text-slate-800">pH Electrode</h3>
              <p className="text-[11px] text-slate-400 font-mono">E201-C BNC • GPIO34</p>
            </div>
          </div>
          <span
            className={`text-[11px] px-2 py-0.5 rounded-full font-semibold border ${
              phStatus === 'normal'
                ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
                : phStatus === 'warning'
                ? 'bg-amber-50 text-amber-700 border-amber-200'
                : phStatus === 'critical'
                ? 'bg-rose-50 text-rose-700 border-rose-200'
                : 'bg-slate-100 text-slate-600 border-slate-200'
            }`}
          >
            {phStatus === 'normal'
              ? 'SAFE RANGE'
              : phStatus === 'warning'
              ? 'SLIGHT DRIFT'
              : phStatus === 'critical'
              ? 'ABNORMAL'
              : 'UNCALIBRATED'}
          </span>
        </div>

        <div className="mt-4 flex items-baseline justify-between">
          <div>
            <div className="text-3xl font-extrabold text-slate-900 tracking-tight">
              {phVal !== null ? phVal.toFixed(2) : '--'}
            </div>
            <p className="text-xs text-slate-500 mt-0.5">
              Target Standard: <span className="font-semibold text-slate-700">6.5 - 8.5 pH</span>
            </p>
          </div>
          <div className="text-right">
            <div className="text-xs font-mono font-medium text-slate-600 flex items-center justify-end space-x-1">
              <Zap className="h-3 w-3 text-amber-500" />
              <span>{phVoltage.toFixed(3)} V</span>
            </div>
            <p className="text-[10px] text-slate-400">Board Output (÷2.5)</p>
          </div>
        </div>

        {/* Technical Subtext & Safety Bounds */}
        <div className="mt-4 pt-3 border-t border-slate-100 text-xs text-slate-500 space-y-1.5">
          <div className="flex items-center justify-between">
            <span className="text-slate-400">Calibration State:</span>
            <span className={reading?.ph_calibrated ? 'font-medium text-emerald-600' : 'font-medium text-amber-600'}>
              {reading?.ph_calibrated ? 'Two-Point Calibrated' : 'Factory Linear (pH 7.00 Reference)'}
            </span>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-slate-400">ESP32 ADC Input:</span>
            <span className="font-mono text-slate-700 font-medium">
              {(phVoltage / 2.5).toFixed(3)} V (Safe &lt;3.3V)
            </span>
          </div>
        </div>
      </div>

      {/* 2. Turbidity Sensor Card */}
      <div className="bg-white rounded-xl border border-slate-200/90 p-5 shadow-xs hover:shadow-md transition-shadow relative overflow-hidden">
        <div className="flex items-center justify-between pb-3 border-b border-slate-100">
          <div className="flex items-center space-x-2">
            <div className="h-8 w-8 rounded-lg bg-cyan-50 text-cyan-600 flex items-center justify-center font-bold text-xs">
              NTU
            </div>
            <div>
              <h3 className="text-sm font-semibold text-slate-800">Turbidity Probe</h3>
              <p className="text-[11px] text-slate-400 font-mono">Optical Sensor • GPIO32</p>
            </div>
          </div>
          <span
            className={`text-[11px] px-2 py-0.5 rounded-full font-semibold border ${
              turbStatus === 'normal'
                ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
                : turbStatus === 'warning'
                ? 'bg-amber-50 text-amber-700 border-amber-200'
                : turbStatus === 'critical'
                ? 'bg-rose-50 text-rose-700 border-rose-200'
                : 'bg-slate-100 text-slate-600 border-slate-200'
            }`}
          >
            {turbStatus === 'normal'
              ? 'CLEAR WATER'
              : turbStatus === 'warning'
              ? 'MODERATE CLOUD'
              : turbStatus === 'critical'
              ? 'HIGH TURBIDITY'
              : 'UNCALIBRATED'}
          </span>
        </div>

        <div className="mt-4 flex items-baseline justify-between">
          <div>
            <div className="text-3xl font-extrabold text-slate-900 tracking-tight">
              {turbVal !== null ? `${turbVal.toFixed(1)}` : '--'}
              <span className="text-sm font-normal text-slate-500 ml-1">NTU</span>
            </div>
            <p className="text-xs text-slate-500 mt-0.5">
              WHO Clean Limit: <span className="font-semibold text-slate-700">&lt; 5.0 NTU</span>
            </p>
          </div>
          <div className="text-right">
            <div className="text-xs font-mono font-medium text-slate-600 flex items-center justify-end space-x-1">
              <Zap className="h-3 w-3 text-amber-500" />
              <span>{turbVoltage.toFixed(3)} V</span>
            </div>
            <p className="text-[10px] text-slate-400">Board Output (÷2.5)</p>
          </div>
        </div>

        {/* Technical Subtext & Safety Bounds */}
        <div className="mt-4 pt-3 border-t border-slate-100 text-xs text-slate-500 space-y-1.5">
          <div className="flex items-center justify-between">
            <span className="text-slate-400">Optical Response:</span>
            <span className="font-medium text-slate-700">
              {turbVoltage > 3.0 ? 'High Transmission (Clear)' : 'High Scattering (Turbid)'}
            </span>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-slate-400">ESP32 ADC Input:</span>
            <span className="font-mono text-slate-700 font-medium">
              {(turbVoltage / 2.5).toFixed(3)} V (Safe &lt;3.3V)
            </span>
          </div>
        </div>
      </div>

      {/* 3. TDS Sensor Card — STRICTLY NOT INSTALLED / RESERVED */}
      <div className="bg-slate-50/70 rounded-xl border border-dashed border-slate-300 p-5 shadow-2xs relative overflow-hidden">
        <div className="flex items-center justify-between pb-3 border-b border-slate-200">
          <div className="flex items-center space-x-2">
            <div className="h-8 w-8 rounded-lg bg-slate-200/80 text-slate-500 flex items-center justify-center font-bold text-xs">
              TDS
            </div>
            <div>
              <h3 className="text-sm font-semibold text-slate-700">TDS Probe (Future)</h3>
              <p className="text-[11px] text-slate-400 font-mono">Reserved: GPIO35</p>
            </div>
          </div>
          <span className="text-[11px] px-2 py-0.5 rounded-full font-semibold bg-slate-200 text-slate-700 border border-slate-300">
            NOT CONNECTED
          </span>
        </div>

        <div className="mt-4">
          <div className="flex items-baseline space-x-2">
            <div className="text-2xl font-extrabold text-slate-400 tracking-tight">
              {tdsVal !== null ? `${tdsVal} ppm` : 'NULL (N/A)'}
            </div>
          </div>
          <p className="text-xs text-slate-500 mt-1">
            Sensor has not arrived. Value is strictly kept <code className="font-mono font-semibold text-slate-700">null</code>, never zero.
          </p>
        </div>

        {/* Future Architecture Explanation */}
        <div className="mt-4 pt-3 border-t border-slate-200/70 text-xs text-slate-500 space-y-1">
          <div className="flex items-start space-x-1.5">
            <Info className="h-3.5 w-3.5 text-slate-400 shrink-0 mt-0.5" />
            <p className="text-[11px] leading-relaxed">
              Pin GPIO35 is architected in firmware and backend for drop-in activation once physical hardware is delivered and calibrated.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
};
