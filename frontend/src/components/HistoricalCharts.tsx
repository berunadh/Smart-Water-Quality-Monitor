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
import { SensorReading } from '../types';

interface HistoricalChartsProps {
  readings: SensorReading[];
  onRangeChange: (hours: number) => void;
  selectedRange: number;
}

export const HistoricalCharts: React.FC<HistoricalChartsProps> = ({
  readings,
  onRangeChange,
  selectedRange,
}) => {
  const [metricMode, setMetricMode] = useState<'both' | 'ph' | 'turbidity'>('both');

  // Format data chronologically (oldest to newest for chart display)
  const chartData = [...readings].reverse().map((r) => {
    const d = new Date(r.timestamp);
    const timeStr = d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    return {
      time: timeStr,
      fullTime: d.toLocaleString(),
      ph: r.ph !== null ? Number(r.ph.toFixed(2)) : null,
      turbidity: r.turbidity !== null ? Number(r.turbidity.toFixed(2)) : null,
      phVoltage: Number(r.ph_voltage.toFixed(3)),
      turbidityVoltage: Number(r.turbidity_voltage.toFixed(3)),
      alertSeverity: r.alert_severity,
    };
  });

  return (
    <div className="bg-white rounded-xl border border-slate-200/90 p-5 shadow-xs">
      {/* Chart Header & Controls */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between pb-4 mb-4 border-b border-slate-100 gap-3">
        <div className="flex items-center space-x-2">
          <TrendingUp className="h-5 w-5 text-sky-600" />
          <h3 className="font-semibold text-slate-800 text-base">
            Telemetry &amp; Trend Analytics
          </h3>
          <span className="text-xs text-slate-400 font-mono">({chartData.length} data points)</span>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {/* Metric Selector */}
          <div className="flex rounded-lg border border-slate-200 p-0.5 bg-slate-50 text-xs">
            <button
              onClick={() => setMetricMode('both')}
              className={`px-2.5 py-1 rounded-md font-medium transition-colors ${
                metricMode === 'both' ? 'bg-white text-slate-800 shadow-2xs font-semibold' : 'text-slate-500 hover:text-slate-700'
              }`}
            >
              All Sensors
            </button>
            <button
              onClick={() => setMetricMode('ph')}
              className={`px-2.5 py-1 rounded-md font-medium transition-colors ${
                metricMode === 'ph' ? 'bg-white text-sky-700 shadow-2xs font-semibold' : 'text-slate-500 hover:text-slate-700'
              }`}
            >
              pH Only
            </button>
            <button
              onClick={() => setMetricMode('turbidity')}
              className={`px-2.5 py-1 rounded-md font-medium transition-colors ${
                metricMode === 'turbidity' ? 'bg-white text-cyan-700 shadow-2xs font-semibold' : 'text-slate-500 hover:text-slate-700'
              }`}
            >
              Turbidity Only
            </button>
          </div>

          {/* Time Range Selector */}
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

      {/* Main Responsive Recharts View */}
      {chartData.length === 0 ? (
        <div className="h-72 flex flex-col items-center justify-center text-slate-400 text-sm">
          <Clock className="h-8 w-8 mb-2 text-slate-300" />
          <p>No telemetry recorded in the selected time range.</p>
        </div>
      ) : (
        <div className="h-80 w-full">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={chartData} margin={{ top: 10, right: 20, left: -10, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" vertical={false} />
              <XAxis dataKey="time" stroke="#94a3b8" fontSize={11} tickLine={false} />
              
              {/* Dual Y-Axes: Left for pH (0-14), Right for Turbidity (NTU) */}
              {(metricMode === 'both' || metricMode === 'ph') && (
                <YAxis
                  yAxisId="phAxis"
                  domain={[4, 10]}
                  stroke="#0284c7"
                  fontSize={11}
                  tickLine={false}
                  orientation="left"
                  tickFormatter={(v) => `${v.toFixed(1)}`}
                />
              )}

              {(metricMode === 'both' || metricMode === 'turbidity') && (
                <YAxis
                  yAxisId="turbAxis"
                  domain={[0, 25]}
                  stroke="#0891b2"
                  fontSize={11}
                  tickLine={false}
                  orientation="right"
                  tickFormatter={(v) => `${v} NTU`}
                />
              )}

              {/* Reference Threshold Lines */}
              {(metricMode === 'both' || metricMode === 'ph') && (
                <>
                  <ReferenceLine
                    yAxisId="phAxis"
                    y={6.5}
                    stroke="#10b981"
                    strokeDasharray="4 4"
                    label={{ value: 'pH Min (6.5)', fill: '#059669', fontSize: 10, position: 'insideTopLeft' }}
                  />
                  <ReferenceLine
                    yAxisId="phAxis"
                    y={8.5}
                    stroke="#10b981"
                    strokeDasharray="4 4"
                    label={{ value: 'pH Max (8.5)', fill: '#059669', fontSize: 10, position: 'insideTopLeft' }}
                  />
                </>
              )}

              {(metricMode === 'both' || metricMode === 'turbidity') && (
                <ReferenceLine
                  yAxisId="turbAxis"
                  y={5.0}
                  stroke="#f59e0b"
                  strokeDasharray="4 4"
                  label={{ value: 'Turbidity Limit (5 NTU)', fill: '#d97706', fontSize: 10, position: 'insideTopRight' }}
                />
              )}

              <Tooltip
                content={({ active, payload }) => {
                  if (active && payload && payload.length) {
                    const data = payload[0].payload;
                    return (
                      <div className="bg-white/95 backdrop-blur p-3 rounded-lg border border-slate-200 shadow-md text-xs space-y-1">
                        <div className="font-semibold text-slate-700 border-b pb-1">
                          {data.fullTime}
                        </div>
                        {data.ph !== null && (
                          <div className="text-sky-700 flex justify-between gap-4">
                            <span>pH:</span>
                            <span className="font-bold">{data.ph} ({data.phVoltage}V)</span>
                          </div>
                        )}
                        {data.turbidity !== null && (
                          <div className="text-cyan-700 flex justify-between gap-4">
                            <span>Turbidity:</span>
                            <span className="font-bold">{data.turbidity} NTU ({data.turbidityVoltage}V)</span>
                          </div>
                        )}
                        <div className="text-slate-500 flex justify-between gap-4 text-[10px] pt-1 border-t">
                          <span>Severity:</span>
                          <span className={data.alertSeverity > 0 ? 'text-rose-600 font-bold' : 'text-emerald-600'}>
                            {data.alertSeverity === 0 ? 'Normal' : `Level ${data.alertSeverity}`}
                          </span>
                        </div>
                      </div>
                    );
                  }
                  return null;
                }}
              />

              <Legend verticalAlign="top" height={36} iconType="circle" />

              {(metricMode === 'both' || metricMode === 'ph') && (
                <Line
                  yAxisId="phAxis"
                  type="monotone"
                  dataKey="ph"
                  name="pH"
                  stroke="#0284c7"
                  strokeWidth={2}
                  dot={false}
                  activeDot={{ r: 5 }}
                  connectNulls={false}
                />
              )}

              {(metricMode === 'both' || metricMode === 'turbidity') && (
                <Line
                  yAxisId="turbAxis"
                  type="monotone"
                  dataKey="turbidity"
                  name="Turbidity (NTU)"
                  stroke="#0891b2"
                  strokeWidth={2}
                  dot={false}
                  activeDot={{ r: 5 }}
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
