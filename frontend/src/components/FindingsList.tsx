import {useState} from 'react';
import type {Finding, Generation} from '../types';

export function findingSource(finding: Finding) {
  return finding.source_slide ?? finding.ai_source_slide ?? finding.slide;
}
export function FindingsList({findings, resolved, busy, onApprove, deckWide=false, slideTargets, onNavigate, currentSlide, decisions=[]}: {
  findings: Finding[]; resolved: Set<string>; busy: boolean;
  onApprove: (ids: string[], rationale: string, slide?: number) => Promise<boolean>;
  deckWide?: boolean; slideTargets?: (finding: Finding) => number[];
  onNavigate?: (slide: number) => void; currentSlide?: number;
  decisions?: Generation['human_decisions'];
}) {
  const [showLow,setShowLow]=useState(false);
  const [showDismissed,setShowDismissed]=useState(false);
  const [accepting,setAccepting]=useState<number | 'deck'>();
  const [reason,setReason]=useState('');
  const low=(f:Finding)=>f.priority==='low' || (!f.priority && f.severity==='warning');
  const targets=(f:Finding)=>slideTargets?.(f) ?? f.affected_slides ?? (f.output_slide!=null?[f.output_slide]:[]);
  const accepted=(f:Finding,slide:number|'deck')=>resolved.has(f.id) || decisions.some(d=>d.output_slide===slide && d.finding_ids.includes(f.id));
  const groups=new Map<number|'deck',Finding[]>();
  findings.forEach(f=>{
    const slides: (number|'deck')[]=deckWide?['deck']:currentSlide!=null?[currentSlide]:targets(f);
    for(const slide of slides) groups.set(slide,[...(groups.get(slide)??[]),f]);
  });
  const dismissed=[...groups].reduce((n,[slide,items])=>n+items.filter(f=>accepted(f,slide)).length,0);
  const lowCount=findings.filter(low).length;
  const visibleGroups=[...groups].map(([slide,items])=>({slide,items,visible:items.filter(f=>(showLow || !low(f)) && (showDismissed || !accepted(f,slide)))})).filter(g=>g.visible.length);
  return <div>
    <div className="mt-3 flex flex-wrap gap-3 text-sm">
      <span className="self-center text-stevens-gray">{showLow?'All priorities':'High priority only'}</span>
      {lowCount>0 && <button className="btn-ghost" aria-pressed={showLow} onClick={()=>setShowLow(!showLow)}>{showLow?'Hide':'Show'} low-priority findings ({lowCount})</button>}
      {dismissed>0 && <button className="btn-ghost" aria-pressed={showDismissed} onClick={()=>setShowDismissed(!showDismissed)}>{showDismissed?'Hide':'Show'} human-reviewed findings ({dismissed})</button>}
    </div>
    {!visibleGroups.length && <p className="mt-3 text-sm text-stevens-gray">{showLow?'No unresolved findings in this view.':'No unresolved high-priority findings in this view.'}</p>}
    {visibleGroups.map(({slide,items,visible})=>{
      const pending=items.filter(f=>!accepted(f,slide));
      const canDismiss=pending.length>0 && pending.every(f=>f.can_approve!==false && f.severity!=='optional_pending');
      const label=slide==='deck'?'Deck-wide findings':`Slide ${slide+1}`;
      return <section key={slide} className="mt-3 rounded-lg border p-3" aria-label={`${label} findings`}>
        <div className="flex flex-wrap items-center justify-between gap-3">
          {typeof slide==='number' && onNavigate?<button className="font-bold text-stevens-blue underline" disabled={busy} onClick={()=>onNavigate(slide)}>{label}</button>:<h3 className="font-bold">{label}</h3>}
          {pending.length>0 && <button className="btn-ghost" disabled={busy || !canDismiss} onClick={()=>{setAccepting(slide);setReason('');}}>{slide==='deck'?'Dismiss deck-wide findings':`Dismiss all findings for slide ${slide+1}`}</button>}
        </div>
        {!canDismiss && pending.length>0 && <p className="mt-2 text-xs text-stevens-gray">Incomplete QA and system errors cannot be dismissed. Complete the checks first.</p>}
        {accepting===slide && <div className="mt-3 rounded border bg-slate-50 p-3">
          <p className="text-sm">Accept all {pending.length} remaining findings for {slide==='deck'?'the deck':`slide ${slide+1}`}, including hidden low-priority suggestions. Findings on other slides remain open.</p>
          <label className="mt-2 block text-sm">Reason for accepting this slide<textarea className="mt-1 w-full rounded border p-2" value={reason} maxLength={2000} onChange={e=>setReason(e.target.value)}/></label>
          <div className="mt-2 flex gap-2"><button className="btn-red" disabled={busy || !reason.trim() || !canDismiss} onClick={async()=>{
            if(await onApprove(slide==='deck'?pending.map(f=>f.id):[],reason.trim(),typeof slide==='number'?slide:undefined)) setAccepting(undefined);
          }}>Accept and dismiss {slide==='deck'?'deck findings':'slide findings'}</button><button className="btn-ghost" disabled={busy} onClick={()=>setAccepting(undefined)}>Cancel dismissal</button></div>
        </div>}
        <ul aria-label={deckWide?'Deck-wide findings list':'Findings for this page'} className="mt-3 max-h-[28rem] divide-y overflow-y-auto">
          {visible.map(f=><li key={f.id} className="py-3 text-sm">
            <div className="flex flex-wrap justify-between gap-2"><b>{f.code?.replace(/_/g,' ')}</b><span className={low(f)?'text-stevens-gray':'text-stevens-red'}>{accepted(f,slide)?'Accepted by human review':low(f)?'Low priority · does not block download':'High priority · blocks download'}</span></div>
            {typeof slide==='number' && onNavigate?<button className="mt-1 block text-left hover:underline focus-visible:underline" disabled={busy} onClick={()=>onNavigate(slide)}>{f.message}</button>:<p className="mt-1">{f.message}</p>}
          </li>)}
        </ul>
      </section>;
    })}
  </div>;
}
