import React from 'react';
import {
  Cpu,
  Zap,
  CheckCircle2,
  XCircle,
  Info,
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
    {
      bit: '0x0001',
      label: 'Wi-Fi Link Active',
      active: system?.wifi_connected ?? false,
      desc: 'ESP32 connected to local 802.11 b/g/n access point',
    },
    {
      bit: '0x0002',
      label: 'Cloud Telemetry Synced',
      active: system?.cloud_synced ?? false,
      desc: 'Telemetry posted to ThingSpeak or local REST database',
    },
    {
      bit: '0x0004',
      label: 'pH Circuit Operational',
      active: system?.ph_sensor_healthy ?? true,
      desc: 'Analog input within physical probe bounds (0.05V - 3.25V)',
    },
    {
      bit: '0x0008',
      label: 'Turbidity Circuit Operational',
      active: system?.turbidity_sensor_healthy ?? true,
      desc: 'Optical receiver diode transmitting valid signal (0.10V - 3.25V)',
    },
    {
      bit: '0x0010',
      label: 'Electrical Safety Pass',
      active: system?.electrical_safe ?? true,
      desc: 'ADC junction voltage safely clamped below ESP32 3.3V limit',
    },
    {
      bit: '0x0020',
      label: 'TDS Reserved (Uninstalled)',
      active: !(system?.tds_installed ?? false),
      desc: 'GPIO35 reserved for future probe; never reported as 0.0 ppm',
    },
    {
      bit: '0x0040',
      label: 'Calibration Pending',
      active: system?.calibration_pending ?? false,
      desc: 'Factory default calibration reference active; two-point recommended',
    },
    {
      bit: '0x0080',
      label: 'Demo / Synthetic Mode',
      active: system?.demo_mode ?? (health?.operating_mode === 'demo'),
      desc: 'Simulated data generation active for offline verification',
    },
  ];

  const phBoardVolt = reading?.ph_voltage ?? (reading?.ph_board_voltage ?? 0);
  const turbBoardVolt = reading?.turbidity_voltage ?? (reading?.turbidity_board_voltage ?? 0);
  const phAdcVolt = phBoardVolt / 2.5;
  const turbAdcVolt = turbBoardVolt / 2.5;

  return (
    <div className="space-y-6">
      {/* Hardware Bitmask Decoder */}
      <div className="bg-white rounded-xl border border-slate-200/90 p-5 shadow-xs">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between pb-4 border-b border-slate-100 gap-2">
          <div className="flex items-center space-x-2">
            <Cpu className="h-5 w-5 text-sky-600" />
            <h3 className="font-semibold text-slate-800 text-base">
              ESP32 16-Bit Health Bitmask Decoder
            </h3>
          </div>
          <div className="flex items-center space-x-2">
            <span className="text-xs text-slate-400">Raw Register:</span>
            <span className="font-mono font-bold text-sm bg-slate-100 text-slate-800 px-2.5 py-1 rounded border border-slate-200">
              {hexCode}
            </span>
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mt-4">
          {bitmaskItems.map((item, idx) => (
            <div
              key={idx}
              className={`p-3 rounded-lg border flex items-start space-x-3 transition-colors ${
                item.active
                  ? 'bg-emerald-50/50 border-emerald-200/80 text-emerald-950'
                  : 'bg-slate-50 border-slate-200/60 text-slate-500'
              }`}
            >
              <div className="mt-0.5">
                {item.active ? (
                  <CheckCircle2 className="h-4 w-4 text-emerald-600" />
                ) : (
                  <XCircle className="h-4 w-4 text-slate-400" />
                )}
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-bold text-slate-800">
                    {item.label}
                  </span>
                  <span className="font-mono text-[10px] text-slate-400">
                    {item.bit}
                  </span>
                </div>
                <p className="text-[11px] text-slate-600 mt-0.5 leading-tight">
                  {item.desc}
                </p>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Electrical Voltage Divider Verification Card */}
      <div className="bg-white rounded-xl border border-slate-200/90 p-5 shadow-xs">
        <div className="flex items-center space-x-2 pb-3 border-b border-slate-100">
          <Zap className="h-5 w-5 text-amber-500" />
          <h3 className="font-semibold text-slate-800 text-base">
            Electrical Safety &amp; Voltage Divider Circuit Analysis
          </h3>
        </div>

        <div className="mt-4 grid grid-cols-1 md:grid-cols-2 gap-4">
          {/* pH Circuit */}
          <div className="p-4 rounded-lg bg-slate-50 border border-slate-200 text-xs space-y-2">
            <div className="flex justify-between items-center">
              <span className="font-bold text-slate-700">pH Signal Conditioning Circuit</span>
              <span className="font-mono text-slate-500">GPIO34 (ADC1_CH6)</span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-500">Sensor Board Output (V_sensor):</span>
              <span className="font-mono font-bold text-slate-800">{phBoardVolt.toFixed(3)} V</span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-500">Divider Ratio:</span>
              <span className="font-mono text-slate-700">10kΩ / (15kΩ + 10kΩ) = 0.400 (÷2.5)</span>
            </div>
            <div className="flex justify-between border-t border-slate-200 pt-2">
              <span className="text-slate-700 font-semibold">ESP32 ADC Input Voltage:</span>
              <span className="font-mono font-bold text-emerald-600">
                {phAdcVolt.toFixed(3)} V (Max: 3.300 V)
              </span>
            </div>
          </div>

          {/* Turbidity Circuit */}
          <div className="p-4 rounded-lg bg-slate-50 border border-slate-200 text-xs space-y-2">
            <div className="flex justify-between items-center">
              <span className="font-bold text-slate-700">Turbidity Optical Circuit</span>
              <span className="font-mono text-slate-500">GPIO32 (ADC1_CH4)</span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-500">Sensor Board Output (V_sensor):</span>
              <span className="font-mono font-bold text-slate-800">{turbBoardVolt.toFixed(3)} V</span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-500">Divider Ratio:</span>
              <span className="font-mono text-slate-700">10kΩ / (15kΩ + 10kΩ) = 0.400 (÷2.5)</span>
            </div>
            <div className="flex justify-between border-t border-slate-200 pt-2">
              <span className="text-slate-700 font-semibold">ESP32 ADC Input Voltage:</span>
              <span className="font-mono font-bold text-emerald-600">
                {turbAdcVolt.toFixed(3)} V (Max: 3.300 V)
              </span>
            </div>
          </div>
        </div>

        {/* Electrical Notes */}
        <div className="mt-4 p-3 bg-amber-50/70 border border-amber-200/80 rounded-lg text-xs text-amber-900 flex items-start space-x-2">
          <Info className="h-4 w-4 text-amber-600 shrink-0 mt-0.5" />
          <p className="leading-relaxed">
            <strong>Protective Sizing:</strong> With a 15kΩ/10kΩ divider, sensor outputs up to 8.25 V are safely stepped down to 3.30 V.
            The firmware and FastAPI validation service reject any input where <code className="font-mono font-bold">V_ADC &gt; 3.25 V</code>,
            preventing internal clamping diode conduction and protecting the ESP32 silicon.
          </p>
        </div>
      </div>

      {/* Backend & Database Telemetry Metrics */}
      <div className="bg-white rounded-xl border border-slate-200/90 p-5 shadow-xs">
        <h4 className="font-semibold text-slate-800 text-sm mb-3 flex items-center space-x-2">
          <Server className="h-4 w-4 text-slate-600" />
          <span>System Environment &amp; Storage Architecture</span>
        </h4>

        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 text-xs">
          <div className="p-3 rounded-lg bg-slate-50 border border-slate-200">
            <span className="text-slate-400">Backend Server</span>
            <p className="font-semibold text-slate-800 mt-1">FastAPI + Uvicorn</p>
          </div>
          <div className="p-3 rounded-lg bg-slate-50 border border-slate-200">
            <span className="text-slate-400">Database Engine</span>
            <p className="font-semibold text-slate-800 mt-1">SQLite (Local ACID)</p>
          </div>
          <div className="p-3 rounded-lg bg-slate-50 border border-slate-200">
            <span className="text-slate-400">Total Stored Records</span>
            <p className="font-mono font-bold text-slate-800 mt-1">{health?.database_records_count ?? '--'}</p>
          </div>
          <div className="p-3 rounded-lg bg-slate-50 border border-slate-200">
            <span className="text-slate-400">Operating Mode</span>
            <p className="font-semibold text-sky-700 uppercase mt-1">{health?.operating_mode ?? 'REAL'}</p>
          </div>
        </div>
      </div>
    </div>
  );
};
