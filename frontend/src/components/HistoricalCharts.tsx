import React, { useState } from 'react';
import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ReferenceLine,
  Legend,
} from 'recharts';
import { Clock, TrendingUp } from 'lucide-react';
import { SensorReading, ModeThresholdProfile } from '../types';

interface HistoricalChartsProps {
  readings: SensorReading[];
  onRangeChange: (hours: number) => void;
  selectedRange: number;
  activeProfile?: ModeThresholdProfile;
}

export const HistoricalCharts: React.FC<HistoricalChartsProps> = ({
  readings,
  onRangeChange,
  selectedRange,
  activeProfile,
}) => {
  const [metricMode, setMetricMode] = useState<'all' | 'ph' | 'turbidity' | 'tds'>('all');

  const phMin = activeProfile?.ph_min ?? 6.5;
  const phMax = activeProfile?.ph_max ?? 8.5;
  const turbLimit = activeProfile?.turbidity_max ?? 1.0;
  const tdsLimit = activeProfile?.tds_max ?? 500.0;

  const chartData = [...readings].reverse().map((r) => {
    const d = new Date(r.timestamp);
    return {
      time: d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      fullTime: d.toLocaleString(),
      ph: r.ph !== null ? Number(r.ph.toFixed(2)) : null,
      turbidity: r.turbidity !== null ? Number(r.turbidity.toFixed(2)) : null,
      tds: r.tds !== null ? Number(r.tds.toFixed(0)) : null,
      phVoltage: Number(r.ph_voltage.toFixed(3)),
      turbidityVoltage: Number(r.turbidity_voltage.toFixed(3)),
      tdsVoltage: r.tds_voltage !== null && r.tds_voltage !== undefined ? Number(r.tds_voltage.toFixed(3)) : null,
      alertSeverity: r.alert_severity,
    };
  });

  return (
    <div className="bg-white rounded-xl border border-slate-200/90 p-5 shadow-xs">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between pb-3 mb-3 border-b border-slate-100 gap-3">
        <div className="flex items-center space-x-2">
          <TrendingUp className="h-4 w-4 text-sky-600" />
          <h3 className="font-semibold text-slate-800 text-sm">
            Historical Telemetry
          </h3>
          <span className="text-xs text-slate-400 font-mono">({chartData.length})</span>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <div className="flex rounded-lg border border-slate-200 p-0.5 bg-slate-50 text-xs">
            {[
              { id: 'all', label: 'All' },
              { id: 'ph', label: 'pH' },
              { id: 'turbidity', label: 'Turbidity' },
              { id: 'tds', label: 'TDS' },
            ].map((m) => (
              <button
                key={m.id}
                onClick={() => setMetricMode(m.id as any)}
                className={`px-2.5 py-1 rounded-md font-medium transition-colors ${
                  metricMode === m.id
                    ? 'bg-white text-slate-900 shadow-2xs font-semibold'
                    : 'text-slate-500 hover:text-slate-700'
                }`}
              >
                {m.label}
              </button>
            ))}
          </div>

          <div className="flex rounded-lg border border-slate-200 p-0.5 bg-slate-50 text-xs">
            {[
              { label: '1h', hours: 1 },
              { label: '6h', hours: 6 },
              { label: '24h', hours: 24 },
              { label: '7d', hours: 168 },
            ].map((range) => (
              <button
                key={range.hours}
                onClick={() => onRangeChange(range.hours)}
                className={`px-2.5 py-1 rounded-md font-medium transition-colors ${
                  selectedRange === range.hours
                    ? 'bg-sky-600 text-white shadow-2xs'
                    : 'text-slate-500 hover:text-slate-700'
                }`}
              >
                {range.label}
              </button>
            ))}
          </div>
        </div>
      </div>

      {chartData.length === 0 ? (
        <div className="h-72 flex flex-col items-center justify-center text-slate-400 text-sm">
          <Clock className="h-7 w-7 mb-2 text-slate-300" />
          <p>No readings in selected window.</p>
        </div>
      ) : (
        <div className="h-72 w-full">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={chartData} margin={{ top: 8, right: 16, left: -12, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" vertical={false} />
              <XAxis dataKey="time" stroke="#94a3b8" fontSize={11} tickLine={false} />

              {(metricMode === 'all' || metricMode === 'ph') && (
                <YAxis
                  yAxisId="phAxis"
                  domain={[4, 10]}
                  stroke="#0284c7"
                  fontSize={11}
                  tickLine={false}
                  orientation="left"
                />
              )}

              {(metricMode === 'all' || metricMode === 'turbidity') && (
                <YAxis
                  yAxisId="turbAxis"
                  domain={[0, 'auto']}
                  stroke="#0891b2"
                  fontSize={11}
                  tickLine={false}
                  orientation="right"
                />
              )}

              {metricMode === 'tds' && (
                <YAxis
                  yAxisId="tdsAxis"
                  domain={[0, 'auto']}
                  stroke="#059669"
                  fontSize={11}
                  tickLine={false}
                  orientation="left"
                />
              )}

              {metricMode === 'all' && (
                <YAxis yAxisId="tdsAxis" hide domain={[0, 'auto']} />
              )}

              {metricMode === 'ph' && (
                <>
                  <ReferenceLine yAxisId="phAxis" y={phMin} stroke="#10b981" strokeDasharray="4 4" label={{ value: `Min ${phMin}`, fill: '#059669', fontSize: 10 }} />
                  <ReferenceLine yAxisId="phAxis" y={phMax} stroke="#10b981" strokeDasharray="4 4" label={{ value: `Max ${phMax}`, fill: '#059669', fontSize: 10 }} />
                </>
              )}

              {metricMode === 'turbidity' && (
                <ReferenceLine yAxisId="turbAxis" y={turbLimit} stroke="#f59e0b" strokeDasharray="4 4" label={{ value: `Limit ${turbLimit} NTU`, fill: '#d97706', fontSize: 10 }} />
              )}

              {metricMode === 'tds' && (
                <ReferenceLine yAxisId="tdsAxis" y={tdsLimit} stroke="#059669" strokeDasharray="4 4" label={{ value: `Limit ${tdsLimit} mg/L`, fill: '#059669', fontSize: 10 }} />
              )}

              <Tooltip
                content={({ active, payload }) => {
                  if (active && payload && payload.length) {
                    const data = payload[0].payload;
                    return (
                      <div className="bg-white/95 backdrop-blur p-2.5 rounded-lg border border-slate-200 shadow-md text-xs space-y-1">
                        <div className="font-semibold text-slate-700 border-b pb-1">{data.fullTime}</div>
                        <div className="text-sky-700 flex justify-between gap-4">
                          <span>pH:</span>
                          <span className="font-bold">
                            {data.ph !== null ? `${data.ph}` : 'Pending'} ({data.phVoltage}V)
                          </span>
                        </div>
                        <div className="text-cyan-700 flex justify-between gap-4">
                          <span>Turbidity:</span>
                          <span className="font-bold">
                            {data.turbidity !== null ? `${data.turbidity} NTU` : 'Pending'} ({data.turbidityVoltage}V)
                          </span>
                        </div>
                        <div className="text-emerald-700 flex justify-between gap-4">
                          <span>TDS:</span>
                          <span className="font-bold">
                            {data.tds !== null ? `${data.tds} mg/L` : 'Pending'}
                            {data.tdsVoltage !== null ? ` (${data.tdsVoltage}V)` : ''}
                          </span>
                        </div>
                      </div>
                    );
                  }
                  return null;
                }}
              />

              <Legend verticalAlign="top" height={32} iconType="circle" />

              {(metricMode === 'all' || metricMode === 'ph') && (
                <Line
                  yAxisId="phAxis"
                  type="monotone"
                  dataKey="ph"
                  name="pH"
                  stroke="#0284c7"
                  strokeWidth={2}
                  dot={false}
                  activeDot={{ r: 4 }}
                  connectNulls={false}
                />
              )}

              {(metricMode === 'all' || metricMode === 'turbidity') && (
                <Line
                  yAxisId="turbAxis"
                  type="monotone"
                  dataKey="turbidity"
                  name="Turbidity (NTU)"
                  stroke="#0891b2"
                  strokeWidth={2}
                  dot={false}
                  activeDot={{ r: 4 }}
                  connectNulls={false}
                />
              )}

              {(metricMode === 'all' || metricMode === 'tds') && (
                <Line
                  yAxisId="tdsAxis"
                  type="monotone"
                  dataKey="tds"
                  name="TDS (mg/L)"
                  stroke="#059669"
                  strokeWidth={2}
                  dot={{ r: 2.5 }}
                  activeDot={{ r: 4 }}
                  connectNulls={false}
                />
              )}
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
};
