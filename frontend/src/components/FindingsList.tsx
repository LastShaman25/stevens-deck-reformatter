import { useEffect, useRef, useState } from 'react';
import type { Finding } from '../types';

export function findingSource(finding: Finding) {
  return finding.source_slide ?? finding.ai_source_slide ?? finding.slide;
}

export function FindingsList({findings, resolved, busy, onApprove, deckWide=false}: {
  findings: Finding[];
  resolved: Set<string>;
  busy: boolean;
  onApprove: (ids: string[], rationale: string) => Promise<boolean>;
  deckWide?: boolean;
}) {
  const [selected, setSelected] = useState<string[]>([]);
  const [rationale, setRationale] = useState('');
  const selectAll = useRef<HTMLInputElement>(null);
  const eligible = findings.filter(f => f.severity === 'review' && f.can_approve !== false && !resolved.has(f.id));
  const selectedIds = eligible.filter(f => selected.includes(f.id)).map(f => f.id);
  const allSelected = eligible.length > 0 && selectedIds.length === eligible.length;
  useEffect(() => {
    if (selectAll.current) selectAll.current.indeterminate = selectedIds.length > 0 && !allSelected;
  }, [selectedIds.length, allSelected]);

  async function approve() {
    if (!selectedIds.length || !rationale.trim() || busy) return;
    if (await onApprove(selectedIds, rationale.trim())) {setSelected([]); setRationale('');}
  }

  return <div>
    {eligible.length > 0 && <div className="mt-3 flex flex-wrap items-center justify-between gap-3 text-sm">
      <label className="flex items-center gap-2 font-semibold"><input ref={selectAll} type="checkbox"
        className="h-4 w-4 accent-stevens-red" disabled={busy} checked={allSelected}
        onChange={() => setSelected(allSelected ? [] : eligible.map(f => f.id))} />
        {deckWide ? 'Select all deck-wide review findings' : 'Select all review findings on this page'}</label>
      <span className="text-stevens-gray" aria-live="polite">{selectedIds.length} of {eligible.length} selected</span>
    </div>}
    {findings.length === 0 ? <p className="mt-3 text-sm text-stevens-gray">No findings for this page.</p> :
      <ul aria-label={deckWide ? 'Deck-wide findings list' : 'Findings for this page'} className="mt-3 max-h-[28rem] divide-y overflow-y-auto rounded-lg border border-stevens-lightgray">
        {findings.map(f => {
          const approved = resolved.has(f.id);
          const reviewable = f.severity === 'review' && f.can_approve !== false && !approved;
          return <li key={f.id} className="flex items-start gap-3 p-3 text-sm">
            <input type="checkbox" className="mt-1 h-4 w-4 shrink-0 accent-stevens-red"
              aria-label={`${approved ? 'Approved' : 'Select'} finding: ${f.message}`} checked={approved || selectedIds.includes(f.id)}
              disabled={busy || !reviewable} onChange={() => setSelected(ids => ids.includes(f.id) ? ids.filter(id => id !== f.id) : [...ids, f.id])} />
            <div className="min-w-0 flex-1"><div className="flex flex-wrap items-center justify-between gap-2">
              <b className="break-words">{f.code?.replace(/_/g, ' ')}</b>
              <span className={approved ? 'text-stevens-blue' : f.severity === 'blocking' ? 'font-semibold text-stevens-red' : 'text-stevens-gray'}>
                {approved ? 'Approved' : f.severity === 'warning' ? 'Suggestion · does not block download' : f.severity === 'review' ? 'Needs review' : f.severity === 'blocking' ? 'Blocking' : 'AI check pending'}
              </span></div>
              <p className="mt-1 break-words">{f.message}</p>
              {!approved && f.severity !== 'warning' && (f.severity !== 'review' || f.can_approve === false) && <p className="mt-1 text-xs text-stevens-gray">
                {f.can_approve === false ? 'QA must pass after repair. Manual approval cannot clear this finding.' : f.severity === 'optional_pending' ? 'Rerun or deselect the optional AI check.' : 'Repair and regenerate to resolve this finding.'}
              </p>}
            </div>
          </li>;
        })}
      </ul>}
    {eligible.length > 0 && <div className="mt-4 flex flex-col items-start gap-3">
      <label className="w-full text-sm">{deckWide ? 'Deck-wide review rationale' : 'Review rationale'}
        <input disabled={busy} value={rationale} onChange={e => setRationale(e.target.value)} maxLength={2000}
          className="mt-1 w-full rounded border p-2" placeholder="What you inspected and accepted for the selected findings" /></label>
      <button className="btn-red" disabled={busy || !selectedIds.length || !rationale.trim()} onClick={approve}>
        Approve selected ({selectedIds.length})
      </button>
    </div>}
  </div>;
}
