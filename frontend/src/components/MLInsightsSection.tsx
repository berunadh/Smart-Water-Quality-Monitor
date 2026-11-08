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
        return {
          bg: 'bg-blue-50 text-blue-700 border-blue-200',
          label: 'MEASURED FACT',
        };
      case 'STATISTICAL_ANOMALY':
        return {
          bg: 'bg-purple-50 text-purple-700 border-purple-200',
          label: 'STATISTICAL ANOMALY',
        };
      case 'ML_PREDICTION':
        return {
          bg: 'bg-emerald-50 text-emerald-700 border-emerald-200',
          label: 'ML PREDICTION',
        };
      case 'RULE_BASED_WARNING':
        return {
          bg: 'bg-amber-50 text-amber-700 border-amber-200',
          label: 'RULE WARNING',
        };
      default:
        return {
          bg: 'bg-slate-100 text-slate-700 border-slate-200',
          label: category,
        };
    }
  };

  return (
    <div className="space-y-6">
      {/* Top Banner & Retraining */}
      <div className="bg-white rounded-xl border border-slate-200/90 p-5 shadow-xs flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div className="flex items-start space-x-3">
          <div className="p-2.5 rounded-xl bg-purple-50 text-purple-600 border border-purple-100">
            <BrainCircuit className="h-6 w-6" />
          </div>
          <div>
            <div className="flex items-center space-x-2">
              <h3 className="font-bold text-slate-900 text-base">
                Machine Learning &amp; AI Analytics Suite
              </h3>
              <span className="text-xs px-2 py-0.5 rounded-full font-medium bg-purple-100 text-purple-800">
                {summary?.status || 'Active'}
              </span>
            </div>
            <p className="text-xs text-slate-500 mt-1">
              Multi-tier engine running Median Absolute Deviation (MAD), Scikit-Learn Isolation Forest, and ordinary least-squares regression.
            </p>
          </div>
        </div>

        <button
          onClick={onRetrain}
          disabled={isRetraining}
          className="inline-flex items-center space-x-2 px-4 py-2 rounded-lg bg-sky-600 hover:bg-sky-700 text-white font-medium text-xs shadow-xs transition-colors disabled:opacity-50 self-start md:self-center"
        >
          <RefreshCw className={`h-3.5 w-3.5 ${isRetraining ? 'animate-spin' : ''}`} />
          <span>{isRetraining ? 'Retraining...' : 'Retrain Anomaly Model'}</span>
        </button>
      </div>

      {/* Structured Categorized Insights */}
      <div className="bg-white rounded-xl border border-slate-200/90 p-5 shadow-xs">
        <h4 className="font-semibold text-slate-800 text-sm mb-3 flex items-center space-x-2">
          <Sparkles className="h-4 w-4 text-purple-600" />
          <span>Synthesized Diagnostic Insights</span>
        </h4>

        {insights.length === 0 ? (
          <p className="text-xs text-slate-400 py-3">No insights generated yet.</p>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {insights.map((ins, idx) => {
              const cat = getCategoryBadge(ins.category);
              return (
                <div
                  key={idx}
                  className="p-3.5 rounded-lg border border-slate-200/80 bg-slate-50/50 flex flex-col justify-between"
                >
                  <p className="text-xs text-slate-700 leading-relaxed font-normal">
                    {ins.message}
                  </p>
                  <div className="mt-2.5 pt-2 border-t border-slate-200/60 flex items-center justify-between">
                    <span className={`text-[10px] font-bold px-2 py-0.5 rounded border uppercase ${cat.bg}`}>
                      {cat.label}
                    </span>
                    {ins.parameter && (
                      <span className="text-[11px] font-mono text-slate-500 uppercase">
                        Target: {ins.parameter}
                      </span>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Trend Drift Analysis */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* pH Drift Card */}
        <div className="bg-white rounded-xl border border-slate-200/90 p-5 shadow-xs">
          <div className="flex items-center justify-between pb-3 border-b border-slate-100">
            <h4 className="font-semibold text-slate-800 text-sm flex items-center space-x-2">
              <LineChart className="h-4 w-4 text-sky-600" />
              <span>pH Drift Degradation Rate</span>
            </h4>
            <span className="text-xs font-semibold px-2 py-0.5 rounded bg-sky-50 text-sky-700 border border-sky-200">
              {trends?.ph_drift.trend_direction || 'STABLE'}
            </span>
          </div>

          <div className="mt-4 space-y-2 text-xs">
            <div className="flex justify-between">
              <span className="text-slate-500">Drift Slope:</span>
              <span className="font-mono font-bold text-slate-800">
                {trends?.ph_drift.slope_per_hour !== undefined
                  ? `${trends.ph_drift.slope_per_hour.toFixed(4)} pH / hr`
                  : '--'}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-500">Linear Fit (R²):</span>
              <span className="font-mono font-medium text-slate-700">
                {trends?.ph_drift.r_squared !== undefined
                  ? trends.ph_drift.r_squared.toFixed(3)
                  : '--'}
              </span>
            </div>
            <p className="text-slate-600 pt-2 border-t border-slate-100 text-[11px] leading-relaxed">
              {trends?.ph_drift.explanation || 'Collecting telemetry baseline to calculate slope...'}
            </p>
          </div>
        </div>

        {/* Turbidity Drift Card */}
        <div className="bg-white rounded-xl border border-slate-200/90 p-5 shadow-xs">
          <div className="flex items-center justify-between pb-3 border-b border-slate-100">
            <h4 className="font-semibold text-slate-800 text-sm flex items-center space-x-2">
              <LineChart className="h-4 w-4 text-cyan-600" />
              <span>Turbidity Slope Analysis</span>
            </h4>
            <span className="text-xs font-semibold px-2 py-0.5 rounded bg-cyan-50 text-cyan-700 border border-cyan-200">
              {trends?.turbidity_drift.trend_direction || 'STABLE'}
            </span>
          </div>

          <div className="mt-4 space-y-2 text-xs">
            <div className="flex justify-between">
              <span className="text-slate-500">Change Slope:</span>
              <span className="font-mono font-bold text-slate-800">
                {trends?.turbidity_drift.slope_per_hour !== undefined
                  ? `${trends.turbidity_drift.slope_per_hour.toFixed(3)} NTU / hr`
                  : '--'}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-500">Linear Fit (R²):</span>
              <span className="font-mono font-medium text-slate-700">
                {trends?.turbidity_drift.r_squared !== undefined
                  ? trends.turbidity_drift.r_squared.toFixed(3)
                  : '--'}
              </span>
            </div>
            <p className="text-slate-600 pt-2 border-t border-slate-100 text-[11px] leading-relaxed">
              {trends?.turbidity_drift.explanation || 'Collecting telemetry baseline to calculate slope...'}
            </p>
          </div>
        </div>
      </div>

      {/* Detected Anomalies Table */}
      <div className="bg-white rounded-xl border border-slate-200/90 shadow-xs overflow-hidden">
        <div className="p-4 border-b border-slate-100 flex items-center justify-between">
          <div className="flex items-center space-x-2">
            <AlertOctagon className="h-5 w-5 text-purple-600" />
            <h4 className="font-semibold text-slate-800 text-sm">
              Recent Anomaly Detections ({anomalyList.length})
            </h4>
          </div>
          <span className="text-xs text-slate-400">
            Engine: MAD + Isolation Forest
          </span>
        </div>

        {anomalyList.length === 0 ? (
          <div className="p-6 text-center text-slate-400 text-xs">
            <CheckCircle2 className="h-8 w-8 mx-auto text-emerald-500/80 mb-2" />
            <p className="font-medium text-slate-700">No Statistical or ML Outliers</p>
            <p className="mt-0.5">Telemetry aligns closely with typical variance distributions.</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-slate-50 border-b border-slate-200 text-slate-500 uppercase tracking-wider font-semibold">
                <tr>
                  <th className="px-4 py-2.5">Time</th>
                  <th className="px-4 py-2.5">Parameter</th>
                  <th className="px-4 py-2.5">Detector</th>
                  <th className="px-4 py-2.5">Anomaly Type</th>
                  <th className="px-4 py-2.5">Score / Dev</th>
                  <th className="px-4 py-2.5">Explanation</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {anomalyList.slice(0, 10).map((anom, i) => (
                  <tr key={i} className="hover:bg-slate-50/80">
                    <td className="px-4 py-2.5 font-mono text-slate-500 whitespace-nowrap">
                      {anom.timestamp ? new Date(anom.timestamp).toLocaleTimeString() : 'N/A'}
                    </td>
                    <td className="px-4 py-2.5 font-bold uppercase text-slate-700">
                      {anom.parameter}
                    </td>
                    <td className="px-4 py-2.5 font-mono text-slate-600 uppercase">
                      {anom.detector_type}
                    </td>
                    <td className="px-4 py-2.5">
                      <span className="px-2 py-0.5 rounded bg-purple-50 text-purple-700 font-semibold border border-purple-200">
                        {anom.anomaly_type}
                      </span>
                    </td>
                    <td className="px-4 py-2.5 font-mono font-bold text-slate-800">
                      {anom.anomaly_score.toFixed(2)}
                    </td>
                    <td className="px-4 py-2.5 text-slate-600 max-w-xs truncate" title={anom.human_explanation}>
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
