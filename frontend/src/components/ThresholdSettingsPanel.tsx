import React, { useState, useEffect } from 'react';
import { SlidersHorizontal, RotateCcw, Save, CheckCircle2, AlertTriangle, Wrench } from 'lucide-react';
import {
  WaterQualitySettings,
  WaterQualityMode,
  CalibrationStatusDetail,
} from '../types';
import { api } from '../services/api';

interface ThresholdSettingsPanelProps {
  settings: WaterQualitySettings | null;
  calibration: CalibrationStatusDetail | null;
  onSettingsUpdated: (updated: WaterQualitySettings) => void;
}

export const ThresholdSettingsPanel: React.FC<ThresholdSettingsPanelProps> = ({
  settings,
  calibration,
  onSettingsUpdated,
}) => {
  const [drinkingForm, setDrinkingForm] = useState({
    ph_min: 6.5,
    ph_max: 8.5,
    turbidity_max: 1.0,
    tds_max: 500,
  });

  const [regularForm, setRegularForm] = useState({
    ph_min: 6.0,
    ph_max: 9.0,
    turbidity_max: 10.0,
    tds_max: 1000,
  });

  const [savingMode, setSavingMode] = useState<WaterQualityMode | null>(null);
  const [feedback, setFeedback] = useState<{ type: 'ok' | 'err'; text: string } | null>(null);

  useEffect(() => {
    if (settings) {
      setDrinkingForm({
        ph_min: settings.drinking_profile.ph_min,
        ph_max: settings.drinking_profile.ph_max,
        turbidity_max: settings.drinking_profile.turbidity_max,
        tds_max: settings.drinking_profile.tds_max,
      });
      setRegularForm({
        ph_min: settings.regular_usage_profile.ph_min,
        ph_max: settings.regular_usage_profile.ph_max,
        turbidity_max: settings.regular_usage_profile.turbidity_max,
        tds_max: settings.regular_usage_profile.tds_max,
      });
    }
  }, [settings]);

  const handleSave = async (mode: WaterQualityMode) => {
    const form = mode === 'drinking' ? drinkingForm : regularForm;
    if (form.ph_min >= form.ph_max) {
      setFeedback({ type: 'err', text: 'pH Min must be lower than pH Max.' });
      return;
    }
    setSavingMode(mode);
    setFeedback(null);
    try {
      const updated = await api.updateModeThresholds({ mode, ...form });
      onSettingsUpdated(updated);
      setFeedback({
        type: 'ok',
        text: `${mode === 'drinking' ? 'Drinking Mode' : 'Regular Usage Mode'} thresholds saved.`,
      });
    } catch (err: any) {
      setFeedback({ type: 'err', text: err.message || 'Failed to update thresholds.' });
    } finally {
      setSavingMode(null);
    }
  };

  const handleReset = async (mode: WaterQualityMode) => {
    setSavingMode(mode);
    setFeedback(null);
    try {
      const updated = await api.resetModeDefaults(mode);
      onSettingsUpdated(updated);
      setFeedback({
        type: 'ok',
        text: `${mode === 'drinking' ? 'IS 10500:2012 Drinking' : 'Regular Usage'} defaults restored.`,
      });
    } catch (err: any) {
      setFeedback({ type: 'err', text: err.message || 'Reset failed.' });
    } finally {
      setSavingMode(null);
    }
  };

  return (
    <div className="space-y-6">
      {feedback && (
        <div
          className={`p-3 rounded-lg border text-xs font-medium flex items-center space-x-2 ${
            feedback.type === 'ok'
              ? 'bg-emerald-50 border-emerald-200 text-emerald-800'
              : 'bg-rose-50 border-rose-200 text-rose-800'
          }`}
        >
          {feedback.type === 'ok' ? (
            <CheckCircle2 className="h-4 w-4 text-emerald-600" />
          ) : (
            <AlertTriangle className="h-4 w-4 text-rose-600" />
          )}
          <span>{feedback.text}</span>
        </div>
      )}

      {/* Configurable Mode Threshold Profiles */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Drinking Mode Profile */}
        <div className="bg-white rounded-xl border border-slate-200/90 p-5 shadow-xs space-y-4">
          <div className="flex items-center justify-between pb-3 border-b border-slate-100">
            <div className="flex items-center space-x-2">
              <SlidersHorizontal className="h-4 w-4 text-sky-600" />
              <h3 className="font-semibold text-slate-900 text-sm">
                Drinking Mode (BIS IS 10500:2012)
              </h3>
            </div>
            {settings?.active_mode === 'drinking' && (
              <span className="text-[10px] font-bold px-2 py-0.5 rounded bg-sky-100 text-sky-800 border border-sky-200">
                ACTIVE
              </span>
            )}
          </div>

          <div className="grid grid-cols-2 gap-3 text-xs">
            <div>
              <label className="block text-slate-500 font-medium mb-1">pH Minimum</label>
              <input
                type="number"
                step="0.1"
                min="0"
                max="14"
                value={drinkingForm.ph_min}
                onChange={(e) => setDrinkingForm({ ...drinkingForm, ph_min: parseFloat(e.target.value) || 0 })}
                className="w-full px-3 py-1.5 rounded-lg border border-slate-200 font-mono text-slate-800 focus:outline-none focus:ring-2 focus:ring-sky-500/20"
              />
            </div>
            <div>
              <label className="block text-slate-500 font-medium mb-1">pH Maximum</label>
              <input
                type="number"
                step="0.1"
                min="0"
                max="14"
                value={drinkingForm.ph_max}
                onChange={(e) => setDrinkingForm({ ...drinkingForm, ph_max: parseFloat(e.target.value) || 0 })}
                className="w-full px-3 py-1.5 rounded-lg border border-slate-200 font-mono text-slate-800 focus:outline-none focus:ring-2 focus:ring-sky-500/20"
              />
            </div>
            <div>
              <label className="block text-slate-500 font-medium mb-1">Max Turbidity (NTU)</label>
              <input
                type="number"
                step="0.1"
                min="0.1"
                max="1000"
                value={drinkingForm.turbidity_max}
                onChange={(e) => setDrinkingForm({ ...drinkingForm, turbidity_max: parseFloat(e.target.value) || 0 })}
                className="w-full px-3 py-1.5 rounded-lg border border-slate-200 font-mono text-slate-800 focus:outline-none focus:ring-2 focus:ring-sky-500/20"
              />
            </div>
            <div>
              <label className="block text-slate-500 font-medium mb-1">Max TDS (mg/L)</label>
              <input
                type="number"
                step="10"
                min="10"
                max="5000"
                value={drinkingForm.tds_max}
                onChange={(e) => setDrinkingForm({ ...drinkingForm, tds_max: parseFloat(e.target.value) || 0 })}
                className="w-full px-3 py-1.5 rounded-lg border border-slate-200 font-mono text-slate-800 focus:outline-none focus:ring-2 focus:ring-sky-500/20"
              />
            </div>
          </div>

          <p className="text-[11px] text-slate-500">
            Reference: BIS IS 10500:2012 Acceptable Limits (6.5–8.5 pH, ≤ 1.0 NTU, ≤ 500 mg/L). Preliminary screening only.
          </p>

          <div className="flex items-center justify-between pt-2 border-t border-slate-100">
            <button
              onClick={() => handleReset('drinking')}
              disabled={savingMode !== null}
              className="inline-flex items-center space-x-1 px-3 py-1.5 rounded-lg text-xs font-medium text-slate-600 hover:bg-slate-100 border border-slate-200"
            >
              <RotateCcw className="h-3.5 w-3.5" />
              <span>IS 10500 Defaults</span>
            </button>
            <button
              onClick={() => handleSave('drinking')}
              disabled={savingMode !== null}
              className="inline-flex items-center space-x-1.5 px-3.5 py-1.5 rounded-lg text-xs font-semibold bg-sky-600 hover:bg-sky-700 text-white"
            >
              <Save className="h-3.5 w-3.5" />
              <span>Save</span>
            </button>
          </div>
        </div>

        {/* Regular Usage Mode Profile */}
        <div className="bg-white rounded-xl border border-slate-200/90 p-5 shadow-xs space-y-4">
          <div className="flex items-center justify-between pb-3 border-b border-slate-100">
            <div className="flex items-center space-x-2">
              <SlidersHorizontal className="h-4 w-4 text-teal-600" />
              <h3 className="font-semibold text-slate-900 text-sm">
                Regular Usage Mode (Operational)
              </h3>
            </div>
            {settings?.active_mode === 'regular_usage' && (
              <span className="text-[10px] font-bold px-2 py-0.5 rounded bg-teal-100 text-teal-800 border border-teal-200">
                ACTIVE
              </span>
            )}
          </div>

          <div className="grid grid-cols-2 gap-3 text-xs">
            <div>
              <label className="block text-slate-500 font-medium mb-1">pH Minimum</label>
              <input
                type="number"
                step="0.1"
                min="0"
                max="14"
                value={regularForm.ph_min}
                onChange={(e) => setRegularForm({ ...regularForm, ph_min: parseFloat(e.target.value) || 0 })}
                className="w-full px-3 py-1.5 rounded-lg border border-slate-200 font-mono text-slate-800 focus:outline-none focus:ring-2 focus:ring-teal-500/20"
              />
            </div>
            <div>
              <label className="block text-slate-500 font-medium mb-1">pH Maximum</label>
              <input
                type="number"
                step="0.1"
                min="0"
                max="14"
                value={regularForm.ph_max}
                onChange={(e) => setRegularForm({ ...regularForm, ph_max: parseFloat(e.target.value) || 0 })}
                className="w-full px-3 py-1.5 rounded-lg border border-slate-200 font-mono text-slate-800 focus:outline-none focus:ring-2 focus:ring-teal-500/20"
              />
            </div>
            <div>
              <label className="block text-slate-500 font-medium mb-1">Max Turbidity (NTU)</label>
              <input
                type="number"
                step="0.5"
                min="0.1"
                max="3000"
                value={regularForm.turbidity_max}
                onChange={(e) => setRegularForm({ ...regularForm, turbidity_max: parseFloat(e.target.value) || 0 })}
                className="w-full px-3 py-1.5 rounded-lg border border-slate-200 font-mono text-slate-800 focus:outline-none focus:ring-2 focus:ring-teal-500/20"
              />
            </div>
            <div>
              <label className="block text-slate-500 font-medium mb-1">Max TDS (mg/L)</label>
              <input
                type="number"
                step="25"
                min="10"
                max="5000"
                value={regularForm.tds_max}
                onChange={(e) => setRegularForm({ ...regularForm, tds_max: parseFloat(e.target.value) || 0 })}
                className="w-full px-3 py-1.5 rounded-lg border border-slate-200 font-mono text-slate-800 focus:outline-none focus:ring-2 focus:ring-teal-500/20"
              />
            </div>
          </div>

          <p className="text-[11px] text-slate-500">
            Configurable operational limits for non-drinking tasks (bathing, laundry, gardening). Not a regulatory standard; adjust for intended use.
          </p>

          <div className="flex items-center justify-between pt-2 border-t border-slate-100">
            <button
              onClick={() => handleReset('regular_usage')}
              disabled={savingMode !== null}
              className="inline-flex items-center space-x-1 px-3 py-1.5 rounded-lg text-xs font-medium text-slate-600 hover:bg-slate-100 border border-slate-200"
            >
              <RotateCcw className="h-3.5 w-3.5" />
              <span>Restore Defaults</span>
            </button>
            <button
              onClick={() => handleSave('regular_usage')}
              disabled={savingMode !== null}
              className="inline-flex items-center space-x-1.5 px-3.5 py-1.5 rounded-lg text-xs font-semibold bg-teal-600 hover:bg-teal-700 text-white"
            >
              <Save className="h-3.5 w-3.5" />
              <span>Save</span>
            </button>
          </div>
        </div>
      </div>

      {/* Sensor Calibration Matrix & Serial Reference */}
      <div className="bg-white rounded-xl border border-slate-200/90 p-5 shadow-xs space-y-4">
        <div className="flex items-center justify-between pb-3 border-b border-slate-100">
          <div className="flex items-center space-x-2">
            <Wrench className="h-4 w-4 text-slate-700" />
            <h3 className="font-semibold text-slate-900 text-sm">
              Sensor Calibration Status &amp; Reference Standards
            </h3>
          </div>
          <span
            className={`text-xs font-semibold px-2.5 py-0.5 rounded-full border ${
              calibration?.calibration_pending
                ? 'bg-amber-50 text-amber-700 border-amber-200'
                : 'bg-emerald-50 text-emerald-700 border-emerald-200'
            }`}
          >
            {calibration?.calibration_pending ? 'Calibration Pending' : 'All Probes Calibrated'}
          </span>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-xs">
          {/* pH */}
          <div className="p-3.5 rounded-lg bg-slate-50 border border-slate-200 space-y-2">
            <div className="flex items-center justify-between">
              <span className="font-bold text-slate-800">pH (GPIO34)</span>
              <span className={
                calibration?.ph_calibrated
                  ? 'text-emerald-600 font-semibold'
                  : calibration?.ph_provisional
                  ? 'text-sky-600 font-semibold'
                  : 'text-amber-600 font-semibold'
              }>
                {calibration?.ph_calibrated ? 'Calibrated' : calibration?.ph_provisional ? 'Provisional' : 'Pending'}
              </span>
            </div>
            <div className="text-slate-600 font-mono">
              Board: {(calibration?.ph_voltage ?? 0).toFixed(3)} V
            </div>
            <div className="text-[11px] text-slate-500">
              CLI: <code>ph cal 4.01</code> / <code>7.00</code> / <code>9.18</code> → <code>ph confirm</code>
            </div>
          </div>

          {/* Turbidity */}
          <div className="p-3.5 rounded-lg bg-slate-50 border border-slate-200 space-y-2">
            <div className="flex items-center justify-between">
              <span className="font-bold text-slate-800">Turbidity (GPIO32)</span>
              <span className={
                calibration?.turbidity_calibrated
                  ? 'text-emerald-600 font-semibold'
                  : calibration?.turbidity_provisional
                  ? 'text-sky-600 font-semibold'
                  : 'text-amber-600 font-semibold'
              }>
                {calibration?.turbidity_calibrated ? 'Calibrated' : calibration?.turbidity_provisional ? 'Provisional' : 'Pending'}
              </span>
            </div>
            <div className="text-slate-600 font-mono">
              Board: {(calibration?.turbidity_voltage ?? 0).toFixed(3)} V
            </div>
            <div className="text-[11px] text-slate-500">
              CLI: <code>turb cal clear &lt;ntu&gt;</code> → <code>turb cal std &lt;ntu&gt;</code> → <code>turb confirm</code>
            </div>
          </div>

          {/* TDS */}
          <div className="p-3.5 rounded-lg bg-slate-50 border border-slate-200 space-y-2">
            <div className="flex items-center justify-between">
              <span className="font-bold text-slate-800">TDS (GPIO35)</span>
              <span className={calibration?.tds_calibrated ? 'text-emerald-600 font-semibold' : 'text-sky-600 font-semibold'}>
                {calibration?.tds_calibrated ? 'Calibrated' : 'Provisional'}
              </span>
            </div>
            <div className="text-slate-600 font-mono">
              ADC: {calibration?.tds_voltage !== null && calibration?.tds_voltage !== undefined
                ? `${calibration.tds_voltage.toFixed(3)} V (Direct)`
                : 'N/A'}
            </div>
            <div className="text-[11px] text-slate-500">
              CLI: <code>tds verify 342</code> → <code>tds confirm</code> (optional kFactor; 25°C nom.)
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
