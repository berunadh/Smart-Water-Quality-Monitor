import React, { useState } from 'react';
import { Droplets, FlaskConical } from 'lucide-react';
import { SampleProfileState } from '../types';

interface Props { state: SampleProfileState | null; onChange: (profile: SampleProfileState['selected_profile'], ph?: number) => Promise<void>; }

const labels = { kent_ro: 'Kent RO Water', household_tap: 'Household Tap Water', contaminated_demo: 'Contaminated Demonstration Sample' };

export const SampleProfileSelector: React.FC<Props> = ({ state, onChange }) => {
  const [busy, setBusy] = useState(false);
  const [ph, setPh] = useState(state?.contaminated_demo_ph ?? 6.2);
  const select = async (profile: SampleProfileState['selected_profile']) => { setBusy(true); try { await onChange(profile, profile === 'contaminated_demo' ? ph : undefined); } finally { setBusy(false); } };
  const applyPh = async () => { setBusy(true); try { await onChange('contaminated_demo', ph); } finally { setBusy(false); } };
  return <section className="bg-sky-50 border border-sky-200 rounded-xl p-4 space-y-3">
    <div className="flex items-center gap-2 text-sky-950"><Droplets className="h-4 w-4" /><h2 className="text-sm font-bold">Presentation Sample Profile</h2><span className="text-[10px] px-2 py-0.5 rounded-full bg-sky-100 font-mono">DEMO CONTROL</span></div>
    <div className="grid grid-cols-1 md:grid-cols-3 gap-2">
      {(Object.keys(labels) as SampleProfileState['selected_profile'][]).map((profile) => <button key={profile} disabled={busy} onClick={() => select(profile)} className={`text-left rounded-lg border p-3 text-xs font-semibold disabled:opacity-50 ${state?.selected_profile === profile ? 'bg-sky-700 text-white border-sky-700' : 'bg-white text-slate-700 border-sky-200 hover:border-sky-500'}`}>
        {labels[profile]}
      </button>)}
    </div>
    {state?.selected_profile === 'contaminated_demo' && <div className="flex flex-wrap items-center gap-2 text-xs"><FlaskConical className="h-4 w-4 text-sky-700" /><span className="font-semibold">Demonstration pH estimate</span><input aria-label="Demonstration pH estimate" type="number" min="0" max="14" step="0.1" value={ph} onChange={(e) => setPh(Number(e.target.value))} className="w-20 rounded border border-sky-300 px-2 py-1" /><button disabled={busy} onClick={applyPh} className="rounded bg-sky-700 px-3 py-1 text-white font-semibold disabled:opacity-50">Apply DEMO_ESTIMATE</button></div>}
    <p className="text-[11px] text-sky-900">{state?.control_note ?? 'Loading profile state…'} Sensor voltages remain visible; salt and dirt do not infer pH.</p>
  </section>;
};
