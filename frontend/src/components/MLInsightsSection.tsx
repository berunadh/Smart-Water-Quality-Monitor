import React from 'react';
import {
  BrainCircuit,
  AlertOctagon,
  Sparkles,
  RefreshCw,
  CheckCircle2,
  LineChart,
} from 'lucide-react';
import { MLSummary, AnomalyResponse, TrendResponse } from '../types';

interface MLInsightsSectionProps {
  summary: MLSummary | null;
  anomalies: AnomalyResponse | null;
  trends: TrendResponse | null;
  onRetrain: () => void;
  isRetraining: boolean;
}

export const MLInsightsSection: React.FC<MLInsightsSectionProps> = ({
  summary,
  anomalies,
  trends,
  onRetrain,
  isRetraining,
}) => {
  const insights = summary?.insights ?? [];
  const anomalyList = anomalies?.anomalies ?? [];

  const getCategoryBadge = (category: string) => {
    switch (category) {
      case 'MEASURED_FACT':
        return { bg: 'bg-blue-50 text-blue-700 border-blue-200', label: 'MEASURED' };
      case 'STATISTICAL_ANOMALY':
        return { bg: 'bg-purple-50 text-purple-700 border-purple-200', label: 'ANOMALY' };
      case 'ML_PREDICTION':
        return { bg: 'bg-emerald-50 text-emerald-700 border-emerald-200', label: 'ISOLATION FOREST' };
      case 'RULE_BASED_WARNING':
        return { bg: 'bg-amber-50 text-amber-700 border-amber-200', label: 'NOTE' };
      default:
        return { bg: 'bg-slate-100 text-slate-700 border-slate-200', label: category };
    }
  };

  const trendCards = [
    { title: 'pH Drift', unit: 'pH/hr', data: trends?.ph_drift, color: 'text-sky-600 bg-sky-50 border-sky-200' },
    { title: 'Turbidity Drift', unit: 'NTU/hr', data: trends?.turbidity_drift, color: 'text-cyan-600 bg-cyan-50 border-cyan-200' },
    { title: 'TDS Drift', unit: 'ppm/hr', data: trends?.tds_drift, color: 'text-emerald-600 bg-emerald-50 border-emerald-200' },
  ];

  return (
    <div className="space-y-5">
      {/* Header & Retrain */}
      <div className="bg-white rounded-xl border border-slate-200/90 p-4 shadow-xs flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div className="flex items-center space-x-2.5">
          <BrainCircuit className="h-5 w-5 text-purple-600" />
          <h3 className="font-bold text-slate-900 text-sm">
            Anomaly Detection &amp; Trend Analysis
          </h3>
          <span className="text-[11px] px-2 py-0.5 rounded-full font-semibold bg-purple-50 text-purple-800 border border-purple-200">
            {summary?.status || 'OPERATIONAL'}
          </span>
        </div>

        <button
          onClick={onRetrain}
          disabled={isRetraining}
          className="inline-flex items-center space-x-2 px-3.5 py-1.5 rounded-lg bg-sky-600 hover:bg-sky-700 text-white font-medium text-xs shadow-2xs transition-colors disabled:opacity-50 self-start sm:self-center"
        >
          <RefreshCw className={`h-3.5 w-3.5 ${isRetraining ? 'animate-spin' : ''}`} />
          <span>{isRetraining ? 'Retraining...' : 'Retrain Model'}</span>
        </button>
      </div>

      {/* Diagnostic Insights */}
      <div className="bg-white rounded-xl border border-slate-200/90 p-4 shadow-xs">
        <h4 className="font-semibold text-slate-800 text-xs uppercase tracking-wider mb-3 flex items-center space-x-1.5">
          <Sparkles className="h-3.5 w-3.5 text-purple-600" />
          <span>System Insights</span>
        </h4>

        {insights.length === 0 ? (
          <p className="text-xs text-slate-400">No insights available.</p>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {insights.map((ins, idx) => {
              const cat = getCategoryBadge(ins.category || ins.type || 'INFO');
              return (
                <div
                  key={idx}
                  className="p-3 rounded-lg border border-slate-200/80 bg-slate-50/50 flex flex-col justify-between gap-2"
                >
                  <p className="text-xs text-slate-700 leading-relaxed">{ins.message}</p>
                  <div className="flex items-center justify-between">
                    <span className={`text-[10px] font-bold px-2 py-0.5 rounded border uppercase ${cat.bg}`}>
                      {cat.label}
                    </span>
                    {ins.parameter && (
                      <span className="text-[10px] font-mono text-slate-500 uppercase">
                        {ins.parameter}
                      </span>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* 3-Sensor Trend Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {trendCards.map((tc, i) => (
          <div key={i} className="bg-white rounded-xl border border-slate-200/90 p-4 shadow-xs">
            <div className="flex items-center justify-between pb-2.5 border-b border-slate-100">
              <h4 className="font-semibold text-slate-800 text-sm flex items-center space-x-1.5">
                <LineChart className="h-4 w-4 text-slate-500" />
                <span>{tc.title}</span>
              </h4>
              <span className={`text-[10px] font-bold px-2 py-0.5 rounded border ${tc.color}`}>
                {tc.data?.trend_direction || 'INSUFFICIENT_DATA'}
              </span>
            </div>
            <div className="mt-3 space-y-1.5 text-xs">
              <div className="flex justify-between">
                <span className="text-slate-500">Slope:</span>
                <span className="font-mono font-bold text-slate-800">
                  {tc.data?.slope_per_hour !== undefined ? `${tc.data.slope_per_hour.toFixed(3)} ${tc.unit}` : '--'}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-500">R² Fit:</span>
                <span className="font-mono text-slate-700">
                  {tc.data?.r_squared !== undefined ? tc.data.r_squared.toFixed(3) : '--'}
                </span>
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* Anomalies Table */}
      <div className="bg-white rounded-xl border border-slate-200/90 shadow-xs overflow-hidden">
        <div className="p-4 border-b border-slate-100 flex items-center justify-between">
          <div className="flex items-center space-x-2">
            <AlertOctagon className="h-4 w-4 text-purple-600" />
            <h4 className="font-semibold text-slate-800 text-sm">
              Detected Anomalies ({anomalyList.length})
            </h4>
          </div>
        </div>

        {anomalyList.length === 0 ? (
          <div className="p-6 text-center text-slate-400 text-xs">
            <CheckCircle2 className="h-7 w-7 mx-auto text-emerald-500/80 mb-1.5" />
            <p className="font-medium text-slate-700">No Outliers Detected</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-slate-50 border-b border-slate-200 text-slate-500 uppercase font-semibold">
                <tr>
                  <th className="px-4 py-2">Time</th>
                  <th className="px-4 py-2">Sensor</th>
                  <th className="px-4 py-2">Detector</th>
                  <th className="px-4 py-2">Details</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {anomalyList.slice(0, 10).map((anom, i) => (
                  <tr key={i} className="hover:bg-slate-50/80">
                    <td className="px-4 py-2 font-mono text-slate-500 whitespace-nowrap">
                      {anom.timestamp ? new Date(anom.timestamp).toLocaleTimeString() : 'N/A'}
                    </td>
                    <td className="px-4 py-2 font-bold uppercase text-slate-700">
                      {anom.parameter}
                    </td>
                    <td className="px-4 py-2 font-mono text-slate-600 uppercase">
                      {anom.detector_type}
                    </td>
                    <td className="px-4 py-2 text-slate-700">
                      {anom.human_explanation}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
};
