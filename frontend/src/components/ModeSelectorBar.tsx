import React from 'react';
import { GlassWater, Droplets, SlidersHorizontal } from 'lucide-react';
import { WaterQualityMode, WaterQualitySettings } from '../types';

interface ModeSelectorBarProps {
  settings: WaterQualitySettings | null;
  onModeChange: (mode: WaterQualityMode) => void;
  isSwitching: boolean;
  onOpenSettings: () => void;
}

export const ModeSelectorBar: React.FC<ModeSelectorBarProps> = ({
  settings,
  onModeChange,
  isSwitching,
  onOpenSettings,
}) => {
  const activeMode: WaterQualityMode = settings?.active_mode ?? 'drinking';
  const activeProfile = settings?.active_profile;

  return (
    <div className="bg-white rounded-xl border border-slate-200/90 p-3.5 shadow-xs flex flex-col lg:flex-row lg:items-center justify-between gap-3">
      {/* Mode Toggle Buttons */}
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider mr-1">
          Evaluation Mode:
        </span>

        <button
          onClick={() => onModeChange('drinking')}
          disabled={isSwitching}
          className={`flex items-center space-x-2 px-3.5 py-2 rounded-lg text-xs font-semibold border transition-all ${
            activeMode === 'drinking'
              ? 'bg-sky-600 text-white border-sky-700 shadow-xs'
              : 'bg-slate-50 text-slate-700 border-slate-200 hover:bg-slate-100'
          }`}
        >
          <GlassWater className="h-4 w-4" />
          <span>Drinking Mode (IS 10500:2012)</span>
        </button>

        <button
          onClick={() => onModeChange('regular_usage')}
          disabled={isSwitching}
          className={`flex items-center space-x-2 px-3.5 py-2 rounded-lg text-xs font-semibold border transition-all ${
            activeMode === 'regular_usage'
              ? 'bg-teal-600 text-white border-teal-700 shadow-xs'
              : 'bg-slate-50 text-slate-700 border-slate-200 hover:bg-slate-100'
          }`}
        >
          <Droplets className="h-4 w-4" />
          <span>Regular Usage Mode</span>
        </button>
      </div>

      {/* Active Limits Summary & Settings Shortcut */}
      <div className="flex flex-wrap items-center gap-3 text-xs">
        {activeProfile && (
          <div className="flex items-center space-x-2.5 bg-slate-50 px-3 py-1.5 rounded-lg border border-slate-200 font-mono text-slate-700">
            <span>
              pH: <strong>{activeProfile.ph_min.toFixed(1)}–{activeProfile.ph_max.toFixed(1)}</strong>
            </span>
            <span className="text-slate-300">|</span>
            <span>
              Turb: <strong>≤ {activeProfile.turbidity_max.toFixed(1)} NTU</strong>
            </span>
            <span className="text-slate-300">|</span>
            <span>
              TDS: <strong>≤ {activeProfile.tds_max.toFixed(0)} mg/L</strong>
            </span>
          </div>
        )}

        <button
          onClick={onOpenSettings}
          className="inline-flex items-center space-x-1.5 px-3 py-1.5 rounded-lg bg-slate-100 hover:bg-slate-200 text-slate-700 font-medium border border-slate-200 transition-colors"
        >
          <SlidersHorizontal className="h-3.5 w-3.5" />
          <span>Thresholds</span>
        </button>
      </div>
    </div>
  );
};
