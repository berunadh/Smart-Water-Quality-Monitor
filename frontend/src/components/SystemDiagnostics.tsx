import React from 'react';
import {
  Cpu,
  Zap,
  CheckCircle2,
  XCircle,
  Server,
} from 'lucide-react';
import { SystemHealth, BackendHealth, SensorReading } from '../types';

interface SystemDiagnosticsProps {
  system: SystemHealth | null;
  health: BackendHealth | null;
  reading: SensorReading | null;
}

export const SystemDiagnostics: React.FC<SystemDiagnosticsProps> = ({
  system,
  health,
  reading,
}) => {
  const rawCode = system?.raw_code ?? reading?.health_code ?? 0x0000;
  const hexCode = `0x${rawCode.toString(16).padStart(4, '0').toUpperCase()}`;

  const bitmaskItems = [
    { bit: '0x0001', label: 'Wi-Fi Link Active', active: system?.wifi_connected ?? false },
    { bit: '0x0002', label: 'Cloud Telemetry Synced', active: system?.cloud_synced ?? false },
    { bit: '0x0004', label: 'pH Circuit Healthy', active: system?.ph_sensor_healthy ?? true },
    { bit: '0x0008', label: 'Turbidity Circuit Healthy', active: system?.turbidity_sensor_healthy ?? true },
    { bit: '0x0010', label: 'ADC Voltage Safe (<3.05V)', active: system?.electrical_safe ?? true },
    { bit: '0x0020', label: 'TDS Hardware Connected', active: system?.tds_installed ?? true },
    { bit: '0x0040', label: 'Calibration Pending', active: system?.calibration_pending ?? false },
    { bit: '0x0100', label: 'TDS Circuit Healthy', active: system?.tds_sensor_healthy ?? true },
    { bit: '0x0400', label: 'TDS Dry / Not Immersed', active: system?.tds_dry ?? false },
    { bit: '0x0800', label: 'TDS Provisional 25°C Model', active: system?.tds_provisional ?? false },
    { bit: '0x1000', label: 'pH Provisional Estimate', active: system?.ph_provisional ?? false },
    { bit: '0x2000', label: 'Turb Provisional Estimate', active: system?.turb_provisional ?? false },
  ];

  const phBoardVolt = reading?.ph_voltage ?? reading?.ph_board_voltage ?? 0;
  const turbBoardVolt = reading?.turbidity_voltage ?? reading?.turbidity_board_voltage ?? 0;
  const phAdcVolt = phBoardVolt / 2.5;
  const turbAdcVolt = turbBoardVolt / 2.5;
  const tdsAdcVolt = reading?.tds_voltage ?? null;

  return (
    <div className="space-y-5">
      {/* 1. Hardware Health Bitmask */}
      <div className="bg-white rounded-xl border border-slate-200/90 p-5 shadow-xs">
        <div className="flex items-center justify-between pb-3 border-b border-slate-100">
          <div className="flex items-center space-x-2">
            <Cpu className="h-4 w-4 text-sky-600" />
            <h3 className="font-semibold text-slate-800 text-sm">
              Hardware Health Bitmask
            </h3>
          </div>
          <span className="font-mono font-bold text-xs bg-slate-100 text-slate-800 px-2.5 py-1 rounded border border-slate-200">
            {hexCode}
          </span>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-3 mt-4">
          {bitmaskItems.map((item, idx) => (
            <div
              key={idx}
              className={`p-3 rounded-lg border flex items-center space-x-2.5 ${
                item.active
                  ? 'bg-emerald-50/50 border-emerald-200/80 text-emerald-950'
                  : 'bg-slate-50 border-slate-200/60 text-slate-500'
              }`}
            >
              {item.active ? (
                <CheckCircle2 className="h-4 w-4 text-emerald-600 shrink-0" />
              ) : (
                <XCircle className="h-4 w-4 text-slate-400 shrink-0" />
              )}
              <div className="min-w-0">
                <div className="text-xs font-semibold text-slate-800 truncate">{item.label}</div>
                <div className="font-mono text-[10px] text-slate-400">{item.bit}</div>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* 2. Electrical Voltage Verification (All 3 ADC Channels) */}
      <div className="bg-white rounded-xl border border-slate-200/90 p-5 shadow-xs">
        <div className="flex items-center space-x-2 pb-3 border-b border-slate-100">
          <Zap className="h-4 w-4 text-amber-500" />
          <h3 className="font-semibold text-slate-800 text-sm">
            Raw Sensor Voltage &amp; ADC Safety
          </h3>
        </div>

        <div className="mt-4 grid grid-cols-1 md:grid-cols-3 gap-4 text-xs">
          {/* pH */}
          <div className="p-3.5 rounded-lg bg-slate-50 border border-slate-200 space-y-1.5">
            <div className="flex justify-between font-bold text-slate-700">
              <span>pH Sensor</span>
              <span className="font-mono text-slate-500">GPIO34</span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-500">Board Out:</span>
              <span className="font-mono font-bold text-slate-800">{phBoardVolt.toFixed(3)} V</span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-500">Divider:</span>
              <span className="font-mono">15kΩ / 10kΩ (÷2.5)</span>
            </div>
            <div className="flex justify-between border-t border-slate-200 pt-1.5 font-semibold">
              <span>ESP32 ADC:</span>
              <span className={`font-mono ${phAdcVolt >= 3.05 ? 'text-rose-600' : 'text-emerald-600'}`}>
                {phAdcVolt.toFixed(3)} V
              </span>
            </div>
          </div>

          {/* Turbidity */}
          <div className="p-3.5 rounded-lg bg-slate-50 border border-slate-200 space-y-1.5">
            <div className="flex justify-between font-bold text-slate-700">
              <span>Turbidity Sensor</span>
              <span className="font-mono text-slate-500">GPIO32</span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-500">Board Out:</span>
              <span className="font-mono font-bold text-slate-800">{turbBoardVolt.toFixed(3)} V</span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-500">Divider:</span>
              <span className="font-mono">15kΩ / 10kΩ (÷2.5)</span>
            </div>
            <div className="flex justify-between border-t border-slate-200 pt-1.5 font-semibold">
              <span>ESP32 ADC:</span>
              <span className={`font-mono ${turbAdcVolt >= 3.05 ? 'text-rose-600' : 'text-emerald-600'}`}>
                {turbAdcVolt.toFixed(3)} V
              </span>
            </div>
          </div>

          {/* TDS */}
          <div className="p-3.5 rounded-lg bg-slate-50 border border-slate-200 space-y-1.5">
            <div className="flex justify-between font-bold text-slate-700">
              <span>TDS Sensor</span>
              <span className="font-mono text-slate-500">GPIO35</span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-500">Supply:</span>
              <span className="font-mono font-semibold text-slate-700">3V3 / GND</span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-500">Divider:</span>
              <span className="font-mono">None (Direct 1.0x)</span>
            </div>
            <div className="flex justify-between border-t border-slate-200 pt-1.5 font-semibold">
              <span>ESP32 ADC:</span>
              <span className={`font-mono ${tdsAdcVolt !== null && tdsAdcVolt >= 3.05 ? 'text-rose-600' : 'text-emerald-600'}`}>
                {tdsAdcVolt !== null ? `${tdsAdcVolt.toFixed(3)} V` : 'N/A'}
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* 3. Storage & Runtime Summary */}
      <div className="bg-white rounded-xl border border-slate-200/90 p-4 shadow-xs">
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
          <div className="p-3 rounded-lg bg-slate-50 border border-slate-200">
            <span className="text-slate-400 flex items-center space-x-1"><Server className="h-3 w-3" /><span>Backend</span></span>
            <p className="font-semibold text-slate-800 mt-1">FastAPI + SQLite</p>
          </div>
          <div className="p-3 rounded-lg bg-slate-50 border border-slate-200">
            <span className="text-slate-400">Stored Records</span>
            <p className="font-mono font-bold text-slate-800 mt-1">{health?.database_records_count ?? '--'}</p>
          </div>
          <div className="p-3 rounded-lg bg-slate-50 border border-slate-200">
            <span className="text-slate-400">Telemetry Source</span>
            <p className="font-semibold text-sky-700 uppercase mt-1">{health?.operating_mode ?? 'REAL'}</p>
          </div>
          <div className="p-3 rounded-lg bg-slate-50 border border-slate-200">
            <span className="text-slate-400">Water Quality Mode</span>
            <p className="font-semibold text-teal-700 uppercase mt-1">
              {health?.water_quality_mode === 'regular_usage' ? 'Regular Usage' : 'Drinking (IS 10500)'}
            </p>
          </div>
        </div>
      </div>
    </div>
  );
};
