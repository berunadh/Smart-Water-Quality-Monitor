import React from 'react';
import {
  AlertTriangle,
  AlertCircle,
  ShieldCheck,
  Clock,
  Check,
} from 'lucide-react';
import { AlertSummary, AlertItem } from '../types';

interface AlertsSectionProps {
  alerts: AlertSummary | null;
  onResolve: (id: number) => void;
  isResolving: boolean;
}

export const AlertsSection: React.FC<AlertsSectionProps> = ({
  alerts,
  onResolve,
  isResolving,
}) => {
  const activeCount = alerts?.total_active ?? 0;
  const criticalCount = alerts?.critical_count ?? 0;
  const warningCount = alerts?.warning_count ?? 0;
  const faultCount = alerts?.fault_count ?? 0;
  const recentAlerts = alerts?.recent_alerts ?? [];

  const getSeverityBadge = (severity: number) => {
    switch (severity) {
      case 1:
        return {
          bg: 'bg-amber-100 text-amber-800 border-amber-300',
          label: 'WARNING',
          icon: AlertTriangle,
        };
      case 2:
        return {
          bg: 'bg-rose-100 text-rose-800 border-rose-300',
          label: 'CRITICAL',
          icon: AlertCircle,
        };
      case 3:
        return {
          bg: 'bg-purple-100 text-purple-800 border-purple-300',
          label: 'HARDWARE FAULT',
          icon: AlertCircle,
        };
      default:
        return {
          bg: 'bg-slate-100 text-slate-800 border-slate-300',
          label: 'INFO',
          icon: ShieldCheck,
        };
    }
  };

  return (
    <div className="space-y-4">
      {/* Overview Stat Counters */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        <div className="bg-white p-4 rounded-xl border border-slate-200/90 shadow-2xs">
          <p className="text-xs font-medium text-slate-500">Active Incidents</p>
          <p className="text-2xl font-bold text-slate-900 mt-1">{activeCount}</p>
        </div>
        <div className="bg-white p-4 rounded-xl border border-rose-100 shadow-2xs">
          <p className="text-xs font-medium text-rose-600">Critical Alerts</p>
          <p className="text-2xl font-bold text-rose-700 mt-1">{criticalCount}</p>
        </div>
        <div className="bg-white p-4 rounded-xl border border-amber-100 shadow-2xs">
          <p className="text-xs font-medium text-amber-600">Warnings</p>
          <p className="text-2xl font-bold text-amber-700 mt-1">{warningCount}</p>
        </div>
        <div className="bg-white p-4 rounded-xl border border-purple-100 shadow-2xs">
          <p className="text-xs font-medium text-purple-600">Hardware Faults</p>
          <p className="text-2xl font-bold text-purple-700 mt-1">{faultCount}</p>
        </div>
      </div>

      {/* Alert Feed */}
      <div className="bg-white rounded-xl border border-slate-200/90 shadow-xs overflow-hidden">
        <div className="p-4 border-b border-slate-100 flex items-center justify-between">
          <div className="flex items-center space-x-2">
            <AlertTriangle className="h-5 w-5 text-slate-700" />
            <h3 className="font-semibold text-slate-800 text-sm">
              Incident &amp; Alarm Log
            </h3>
          </div>
          <span className="text-xs text-slate-400">
            Total records: {recentAlerts.length}
          </span>
        </div>

        {recentAlerts.length === 0 ? (
          <div className="p-8 text-center text-slate-400">
            <ShieldCheck className="h-10 w-10 mx-auto text-emerald-500/80 mb-2" />
            <p className="text-sm font-medium text-slate-700">All Systems Normal</p>
            <p className="text-xs text-slate-400 mt-1">
              No unresolved alerts or active parameter excursions recorded.
            </p>
          </div>
        ) : (
          <div className="divide-y divide-slate-100">
            {recentAlerts.map((alert: AlertItem) => {
              const badge = getSeverityBadge(alert.severity);
              const Icon = badge.icon;
              return (
                <div
                  key={alert.id}
                  className={`p-4 transition-colors flex flex-col sm:flex-row sm:items-center justify-between gap-3 ${
                    alert.resolved ? 'bg-slate-50/50 opacity-70' : 'bg-white hover:bg-slate-50/80'
                  }`}
                >
                  <div className="flex items-start space-x-3">
                    <span className={`p-1.5 rounded-lg border mt-0.5 shrink-0 ${badge.bg}`}>
                      <Icon className="h-4 w-4" />
                    </span>
                    <div>
                      <div className="flex items-center space-x-2">
                        <span className={`text-[10px] font-bold px-2 py-0.5 rounded border uppercase tracking-wider ${badge.bg}`}>
                          {badge.label}
                        </span>
                        <h4 className="text-sm font-semibold text-slate-900">
                          {alert.title}
                        </h4>
                        {alert.resolved && (
                          <span className="text-[10px] font-medium px-2 py-0.2 rounded bg-slate-200 text-slate-600">
                            RESOLVED
                          </span>
                        )}
                      </div>
                      <p className="text-xs text-slate-600 mt-1">
                        {alert.message}
                      </p>
                      <div className="flex items-center space-x-3 text-[11px] text-slate-400 mt-1.5">
                        <span className="flex items-center space-x-1">
                          <Clock className="h-3 w-3" />
                          <span>
                            Triggered: {new Date(/([zZ]|[+-]\d{2}:?\d{2})$/.test(alert.timestamp) ? alert.timestamp : `${alert.timestamp}Z`).toLocaleString()}
                          </span>
                        </span>
                        {alert.resolved_at && (
                          <span>
                            • Resolved: {new Date(/([zZ]|[+-]\d{2}:?\d{2})$/.test(alert.resolved_at) ? alert.resolved_at : `${alert.resolved_at}Z`).toLocaleTimeString()}
                          </span>
                        )}
                      </div>
                    </div>
                  </div>

                  {!alert.resolved && (
                    <button
                      onClick={() => onResolve(alert.id)}
                      disabled={isResolving}
                      className="inline-flex items-center space-x-1.5 px-3 py-1.5 text-xs font-semibold rounded-lg bg-slate-100 hover:bg-slate-200 text-slate-700 transition-colors border border-slate-300 shrink-0 self-start sm:self-center"
                    >
                      <Check className="h-3.5 w-3.5 text-emerald-600" />
                      <span>Acknowledge</span>
                    </button>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
};
