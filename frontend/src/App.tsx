import {QaExecution} from './components/QaExecution';
import { useEffect, useRef, useState } from "react";
import { UploadStep } from "./steps/UploadStep";
import { FindingsList, findingSource } from './components/FindingsList';
import type { AIConfiguration, Generation, Revision, SessionInfo } from "./types";
import {apiFetch} from './http';
import {ExpandablePreview} from './components/ExpandablePreview';

async function request<T>(path: string, body?: unknown, method = "POST"): Promise<T> {
  const res = await apiFetch(`/api${path}`, body === undefined ? undefined : {
    method, headers: {"Content-Type": "application/json"}, body: JSON.stringify(body)
  });
  const value = await res.json();
  if (!res.ok) throw new Error(typeof value.detail === 'string' ? value.detail : JSON.stringify(value.detail));
  return value;
}
const empty: Revision = {tags: [], instruction: "", reset_emphasis: false};

function Preview({url, label, placeholder}: {url: string | null; label: string; placeholder?: string}) {
  const [failed, setFailed] = useState(false);
  useEffect(() => setFailed(false), [url]);
  return <figure className="min-w-0 flex-1"><figcaption className="mb-2 text-xs font-bold text-stevens-gray">{label}</figcaption>
    {url && !failed ? <ExpandablePreview className="w-full rounded border border-stevens-lightgray" src={url} alt={label} onError={() => setFailed(true)} /> :
      <div className="grid aspect-video min-h-48 place-items-center rounded border border-stevens-lightgray bg-white p-5 text-center text-sm text-stevens-gray">{placeholder || 'Rendered preview unavailable'}</div>}
  </figure>;
}

export default function App({onHome}: {onHome?:()=>void} = {}) {
  const [session, setSession] = useState<SessionInfo | null>(null);
  const [generation, setGeneration] = useState<Generation | null>(null);
  const [previewGeneration, setPreviewGeneration] = useState<Generation | null>(null);
  const [current, setCurrent] = useState(0);
  const [output, setOutput] = useState(0);
  const [revs, setRevs] = useState<Record<number, Revision>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>();
  const [notice, setNotice] = useState('');
  const [saved, setSaved] = useState(false);
  const [aiConfig,setAiConfig] = useState<AIConfiguration>();
  const [connection,setConnection] = useState<Record<string,{status:string; message?:string}>>();
  const [generating,setGenerating] = useState(false);
  const generationPending = useRef(false);
  const scope = useRef(0);
  const dirty = useRef(new Set<number>());

  function restore(info: SessionInfo) {
    setSession(info); setGeneration(info.generation ?? null); setRevs(info.revisions ?? {});
    setPreviewGeneration(info.generation?.state !== 'checking' && info.generation?.candidate_sha256 ? info.generation : info.preview_generation ?? null);
    setCurrent(0); setOutput(0); setSaved(!!info.benchmarked);
    setAiConfig(info.capabilities.ai);
    dirty.current.clear();
  }
  useEffect(() => {
    request<{capabilities:{ai?:AIConfiguration}}>('/health').then(h=>{
      setAiConfig(h.capabilities.ai);
    }).catch(()=>{});
    const sid = new URLSearchParams(window.location.search).get('session');
    if (!sid) return;
    let active = true;
    setBusy(true);
    request<SessionInfo>(`/sessions/${sid}`).then(info => {if (active) restore(info);})
      .catch(e => {if (active) setError(e.message);}).finally(() => {if (active) setBusy(false);});
    return () => {active = false;};
  }, []);

  useEffect(()=>{
    if (!generating || !session) return;
    let active=true;
    const token=scope.current;
    const timer=window.setInterval(()=>{
      request<SessionInfo>(`/sessions/${session.session_id}`).then(info=>{
        // Polling reports progress only. The generation response owns final
        // mapping/previews so an in-flight render cannot cache a missing image.
        const next=info.generation;
        if(active && generationPending.current && scope.current===token && next) setGeneration(previous=>
          previous && previous.generation_id===next.generation_id
            ? {...previous,progress:next.progress}
            : {...next,state:'checking',built_slides:0,source_to_output_slides:{},candidate_sha256:null});
      }).catch(()=>{});
    },1500);
    return ()=>{active=false;window.clearInterval(timer);};
  },[generating,session?.session_id]);

  async function operation(work: () => Promise<void>) {
    const token = scope.current;
    setBusy(true); setError(undefined); setNotice('');
    try { await work(); } catch (e) { if (scope.current === token) setError((e as Error).message); }
    finally { if (scope.current === token) setBusy(false); }
  }
  async function upload(file: File) {
    const token = ++scope.current;
    await operation(async () => {
      const data = new FormData(); data.append('file', file);
      const res = await apiFetch('/api/sessions', {method:'POST', body:data});
      const info = await res.json();
      if (!res.ok) throw new Error(info.detail || 'Upload failed');
      if (token !== scope.current) return;
      restore(info); setNotice('Review the source, then generate a checked candidate.');
      window.history.replaceState({}, '', `?session=${info.session_id}`);
    });
  }
  async function saveRevisions(sid: string) {
    for (const i of [...dirty.current]) {
      await request(`/sessions/${sid}/slides/${i}/revise`, revs[i] ?? empty);
      dirty.current.delete(i);
    }
  }
  async function generate() {
    if (!session) return;
    const token = scope.current, sid = session.session_id;
    generationPending.current=true;setGenerating(true);setGeneration(null);
    await operation(async () => {
      await saveRevisions(sid);
      const res = await request<{generation: Generation}>(`/sessions/${sid}/generate`, {mode:'ai',repair_passes:1});
      if (token !== scope.current) return;
      generationPending.current=false;
      setGeneration(res.generation); setSaved(false);
      if (res.generation.candidate_sha256) {
        setPreviewGeneration(res.generation);
        const nextOutput=res.generation.source_to_output_slides[String(current)]?.[0] ?? Math.min(output,Math.max(0,res.generation.built_slides-1));
        setOutput(nextOutput);
        setCurrent(Number(Object.entries(res.generation.source_to_output_slides).find(([,parts])=>parts.includes(nextOutput))?.[0] ?? -1));
      }
    });
    generationPending.current=false;setGenerating(false);
  }

  async function refreshAI(test=false) {
    await operation(async()=>{
      if(test){
        const response=await request<{configuration:AIConfiguration;results:Record<string,{status:string;message?:string}>}>('/ai/test',{});
        setAiConfig(response.configuration);setConnection(response.results);
      } else {
        const response=await request<{capabilities:{ai:AIConfiguration}}>('/health');
        setAiConfig(response.capabilities.ai);setConnection(undefined);
      }
    });
  }
  function changeRevision(value: Revision) {
    dirty.current.add(current); setRevs(r => ({...r, [current]: value}));
    setGeneration(null); setSaved(false);
  }
  async function apply() {
    if (!session) return;
    const token = scope.current;
    await operation(async () => {
      await saveRevisions(session.session_id);
      if (token === scope.current) setNotice('Revision saved. Generate to apply and verify the result.');
    });
  }
  async function approve(ids: string[], rationale: string) {
    if (!session || !generation) return false;
    const token = scope.current;
    let approved = false;
    await operation(async () => {
      const res = await request<{generation: Generation}>(`/sessions/${session.session_id}/decisions`, {
        generation_id:generation.generation_id, candidate_sha256:generation.candidate_sha256,
        finding_ids:ids, rationale
      });
      if (token === scope.current) {setGeneration(res.generation); approved = true;}
    });
    return approved;
  }
  async function download(draft: boolean, format: 'pptx' | 'pdf' = 'pptx') {
    if (!session || !generation) return;
    await operation(async () => {
      const res = await apiFetch(`/api/sessions/${session.session_id}/download?generation_id=${generation.generation_id}&draft=${draft}&format=${format}`);
      if (!res.ok) {const err = await res.json(); throw new Error(err.detail);}
      const url = URL.createObjectURL(await res.blob());
      const a = document.createElement('a'); a.href = url;
      a.download = (draft ? 'Stevens-unverified-draft.' : 'Stevens-verified.') + format; a.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      if (!draft) {await request(`/sessions/${session.session_id}/finalize`, {}); await startOver(); onHome?.();}
    });
  }
  async function startOver() {
    const old = session;
    ++scope.current;
    setSession(null); setGeneration(null); setRevs({}); setError(undefined);
    setPreviewGeneration(null);
    setNotice(''); setSaved(false); setBusy(false); setCurrent(0); setOutput(0); dirty.current.clear();
    generationPending.current=false;setGenerating(false);
    window.history.replaceState({}, '', window.location.pathname);
    if (old) {
      try { const response=await apiFetch(`/api/sessions/${old.session_id}`, {method:'DELETE'});
        if(!response.ok)throw new Error('Could not confirm deletion; retry or sign out.');
        const value=await response.json();if(value.deleted===false)setNotice('Access revoked. Deletion is pending while the current operation releases its files.');
      } catch(e){setError((e as Error).message);}
    }
  }
  function navigateSlide(index: number) {
    if (busy || !session || index < 0 || index >= reviewSlides.length) return;
    setCurrent(reviewSlides[index].source);
    setOutput(index);
  }
  const reviewingOutput=!!previewGeneration?.built_slides;
  const reviewSlides=Array.from({length:reviewingOutput ? previewGeneration!.built_slides : session?.slide_count ?? 0},(_,index)=>{
    const source=reviewingOutput ? Number(Object.entries(previewGeneration!.source_to_output_slides).find(([,parts])=>parts.includes(index))?.[0] ?? -1) : index;
    const parts=previewGeneration?.source_to_output_slides[String(source)] ?? [];
    const added=previewGeneration?.added_slides?.find(slide=>slide.output_slide===index);
    const title=source>=0 ? session?.slides.find(slide=>slide.index===source)?.title || '(untitled)' : added?.text || 'Added slide';
    const origin=source>=0 ? `Source ${source+1}${parts.length>1 ? ` · Part ${parts.indexOf(index)+1} of ${parts.length}` : ''}` : 'No original';
    return {source,label:reviewingOutput ? `${index+1}: ${title} · ${origin}` : `${index+1}: ${title}`};
  });
  const reviewIndex=reviewingOutput ? output : current;
  const rev = revs[current] ?? empty;
  const resolved = new Set(generation?.human_decisions.flatMap(d => d.finding_ids) ?? []);
  const outputs = previewGeneration?.source_to_output_slides[String(current)] ?? [];
  const previewIsPrevious = !!previewGeneration && (generating || !generation || generation.generation_id !== previewGeneration.generation_id);
  const pageFindings = generation?.findings.filter(f => f.affected_slides?.length ? f.affected_slides.includes(output) : f.output_slide != null
    ? f.output_slide === output : current>=0 && findingSource(f) === current) ?? [];
  const deckFindings = generation?.findings.filter(f => f.output_slide == null && !f.affected_slides?.length && findingSource(f) == null) ?? [];
  const reviewScope = `${session?.session_id}:${generation?.generation_id}:${generation?.candidate_sha256}`;
  const sid = session?.session_id;
  return <div className="min-h-screen bg-[#f5f7fa] text-stevens-ink">
    <header className="flex items-center justify-between border-b border-stevens-lightgray bg-white px-6 py-4">
      <div><h1 className="text-xl font-extrabold">Stevens Slide Studio</h1><p className="text-xs text-stevens-gray">Preserve content. Verify the exported deck.</p></div>
      {session && <button className="btn-ghost" onClick={startOver}>Start a new deck</button>}
    </header>
    <section className="mx-5 mt-4 rounded border border-stevens-lightgray bg-white p-4 text-sm" aria-label="AI configuration">
      <div className="flex flex-wrap items-center gap-3"><b>AI redesign and review</b>
        <button className="btn-ghost" disabled={busy} onClick={()=>refreshAI(false)}>Refresh AI configuration</button>
        <button className="btn-ghost" disabled={busy || !aiConfig?.configured} onClick={()=>refreshAI(true)}>Test AI connection</button></div>
      <p className="mt-2">Planner: {aiConfig?.planner.model || 'not configured'} · Reviewer: {aiConfig?.reviewer.model || 'not configured'}</p>
      {!aiConfig?.configured ? <p className="mt-1 text-stevens-gray">{aiConfig?.planner.provider==='openai' && aiConfig?.reviewer.provider==='openai' ? 'Add OPENAI_API_KEY to backend/.env locally, then refresh.' : 'Configure the provider keys in backend/.env locally, then refresh.'} Never paste keys into reviewer notes.</p> :
        <p className="mt-1 text-stevens-gray">{aiConfig.independent_providers ? 'Separate providers plan and review.' : 'One provider performs separate planning and review calls.'} Redesign sends slide content and rendered images to these providers. API usage may incur charges.</p>}
      {connection && Object.entries(connection).map(([role,result])=><p role="status" key={role}>{role}: {result.status}{result.message ? ` — ${result.message}` : ''}</p>)}
    </section>
    {error && <div role="alert" className="m-5 rounded border border-stevens-red bg-red-50 p-4 text-stevens-red">{error}</div>}
    {notice && <div role="status" className="mx-5 mt-4 rounded bg-stevens-lightblue p-3 text-sm">{notice}</div>}
    {!session ? <UploadStep onFile={upload} busy={busy} /> : <main className="mx-auto max-w-7xl p-5">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3"><div><h2 className="text-lg font-bold">{session.name}</h2>
        <p className="text-sm text-stevens-gray">{session.slide_count} source slides{previewGeneration ? ` → ${previewGeneration.built_slides} output slides` : ''}</p>{previewGeneration?.added_slides?.map(slide=><a key={slide.output_slide} className="text-sm underline" href="#slide-review" onClick={()=>navigateSlide(slide.output_slide)}>View added Thank you closing · slide {slide.output_slide+1}</a>)}</div>
        <button className="btn-red" disabled={busy || !aiConfig?.configured} onClick={generate}>{busy ? 'Working…' : 'Redesign + QA'}</button></div>
      <div className="grid gap-5 lg:grid-cols-[1fr_330px]">
        <section id="slide-review" className="card p-5">
          <nav aria-label="Slide navigation" className="mb-4 flex flex-wrap items-center justify-between gap-2">
            <button aria-label="Previous slide" className="btn-ghost disabled:cursor-not-allowed disabled:opacity-40" disabled={busy || reviewIndex === 0} onClick={() => navigateSlide(reviewIndex-1)}>
              <span aria-hidden="true">←</span> Previous slide
            </button>
            <span className="text-sm text-stevens-gray" aria-live="polite">{reviewingOutput ? 'Output slide' : 'Slide'} {reviewIndex+1} of {reviewSlides.length}</span>
            <button aria-label="Next slide" className="btn-ghost disabled:cursor-not-allowed disabled:opacity-40" disabled={busy || reviewIndex >= reviewSlides.length-1} onClick={() => navigateSlide(reviewIndex+1)}>
              Next slide <span aria-hidden="true">→</span>
            </button>
          </nav>
          <label className="block text-sm font-bold">{reviewingOutput ? 'Review slide' : 'Source slide'} <select aria-label={reviewingOutput ? 'Review slide' : 'Source slide'} className="mt-1 w-full min-w-0 rounded border p-2" value={reviewIndex} disabled={busy} onChange={e => navigateSlide(Number(e.target.value))}>
            {reviewSlides.map((slide,index) => <option key={index} value={index}>{slide.label}</option>)}</select></label>
          {outputs.length>1 && <p className="mt-2 text-sm text-stevens-gray">Part {outputs.indexOf(output)+1} of {outputs.length} from source slide {current+1}. Each part is shown beside the same original.</p>}
          <div className="mt-4 flex flex-col gap-4 md:flex-row">
            <Preview url={current>=0 ? `/api/sessions/${sid}/slides/${current}/preview?variant=before` : null} label="Original source" placeholder={current<0 ? 'No original slide — this page was added during redesign.' : undefined} />
            <Preview url={reviewingOutput ? `/api/sessions/${sid}/slides/${output}/preview?variant=after&generation_id=${previewGeneration!.generation_id}` : null} label="Generated candidate" />
          </div>
          {previewIsPrevious && <p role="status" className="mt-3 text-sm text-amber-800">Showing the previous candidate. Your latest instructions are not applied yet; generate again to update and verify it.</p>}
          {!previewIsPrevious && previewGeneration && !previewGeneration.download_allowed && <p className="mt-3 text-sm text-amber-800">Deck download blocked. Open findings on the affected slides below; this message does not mean the displayed slide failed.</p>}
          <p className="mt-3 text-xs text-stevens-gray">Previews show real renders when available. Review decisions apply to a specific generated file.</p>
          {current>=0 ? <fieldset disabled={busy} className="mt-5"><legend className="text-sm font-bold">Corrections</legend>
            <div className="mt-2 flex flex-wrap gap-2">{[['split','Split slide'],['dense','Too dense'],['layout','Layout'],['overlap','Overlap'],['diagram','Preserve diagram'],['emphasis','Source emphasis']].map(([id,label]) =>
              <button key={id} aria-pressed={rev.tags.includes(id)} className={rev.tags.includes(id) ? 'btn-red' : 'btn-ghost'} onClick={() => changeRevision({...rev, tags:rev.tags.includes(id) ? rev.tags.filter(x => x !== id) : [...rev.tags,id], reset_emphasis: id === 'emphasis' ? true : rev.reset_emphasis})}>{label}</button>)}</div>
            <label className="mt-4 block text-sm">Redesign instructions
              <textarea aria-label="Reviewer note" className="mt-1 w-full rounded border p-3" rows={3} value={rev.instruction} onChange={e => changeRevision({...rev,instruction:e.target.value})} /></label>
            <p className="mt-1 text-xs text-stevens-gray">Instructions guide layout and styling. Original wording, chart data, notes, and links remain protected.</p>
            <button className="btn-ghost mt-2" onClick={apply}>Save revision</button>
          </fieldset> : <p className="mt-5 text-sm text-stevens-gray">This added page is included in mandatory QA. Its findings appear below.</p>}
          <p className="mt-4 text-xs text-stevens-gray">Redesign includes mandatory visual review of every output slide and one repair pass.</p>
          {generation?.corrections.filter(c => c.index === current).flatMap(c => c.actions).map((a,i) => <p className="mt-2 text-sm" key={i}>{a.action}: <b>{a.status}</b> — {a.message}</p>)}
        </section>
        <aside className="card p-5"><h2 className="text-lg font-bold">Verification</h2>{generation&&<QaExecution generation={generation}/>}
          <p role="status" className="mt-2 font-semibold">{busy ? 'Processing…' : generation ? generation.state === 'ready' && generation.findings.some(f => f.severity === 'warning') ? 'Ready with suggestions' : generation.state.replace('_',' ') : previewGeneration ? 'Regeneration required' : 'Not yet generated'}</p>
          {generating && generation?.progress && <p role="status" className="mt-2 text-sm">{generation.progress.stage.replace(/_/g,' ')}{generation.progress.output_slide!==undefined ? ` · output slide ${generation.progress.output_slide+1}` : ''}{generation.progress.completed_calls!==undefined ? ` · ${generation.progress.completed_calls} AI calls completed` : ''}</p>}
          {!generation && <p className="mt-2 text-sm text-stevens-gray">Generate a candidate to check content, formatting, and rendered output.</p>}
          {generation && <><ul className="mt-3 space-y-2 text-sm">{Object.entries(generation.checks).map(([name,result]) => <li key={name}><b>{name.replace(/_/g,' ')}</b>: {result.status === 'passed' && generation.findings.some(f => f.check === name && f.severity === 'warning') ? 'passed with suggestions' : result.status.replace(/_/g,' ')}</li>)}</ul>
            <div className="mt-4 flex flex-col gap-2"><button className="btn-red" disabled={busy || !generation.download_allowed} onClick={() => download(false)}>Download verified PowerPoint and finish</button>
              <button className="btn-red" disabled={busy || !generation.download_allowed || !generation.pdf_available} onClick={() => download(false, 'pdf')}>Download verified PDF and finish</button>
              <button className="btn-ghost" onClick={async()=>{await startOver();onHome?.();}}>Finish and delete</button></div>
            <p className="mt-2 text-xs text-stevens-gray">QA must complete and all material issues must be resolved. Cosmetic suggestions do not block downloads. Download and finish deletes processing files.</p></>}
          {generation?.ai_pipeline && <div className="mt-4 text-sm"><b>AI pipeline: {generation.ai_pipeline.status}</b>
            {generation.ai_pipeline.failure_message && <p className="mt-2 text-stevens-red">{generation.ai_pipeline.failure_message}</p>}
            {generation.source_decisions?.[String(current)] && <p className="mt-2">This slide: {generation.source_decisions[String(current)].action==='keep_original'?'kept unchanged':'redesigned'} · {generation.source_decisions[String(current)].removed_artwork} artwork elements removed. {!!generation.source_decisions[String(current)].extracted_logos && <>{generation.source_decisions[String(current)].extracted_logos} embedded logos preserved. </>}{generation.source_decisions[String(current)].reason}</p>}
            <p>{generation.ai_pipeline.calls.length} pipeline steps · {generation.ai_pipeline.changed_objects} object edits</p>
            {generation.usage && <p>Upload total: {generation.usage.upload_requests} requests · {generation.usage.upload_tokens.toLocaleString()} recorded tokens{generation.usage.token_limit?` of ${generation.usage.token_limit.toLocaleString()} allowed`:''} (includes retries and QA).{generation.usage.token_limit===null ? ' No cumulative token limit.' : ''}</p>}
            {generation.ai_pipeline.attempts.map((a,i)=><p key={i}>Pass {a.attempt+1}: {a.accepted?'accepted':'rejected'}{a.reason?` — ${a.reason}`:''}</p>)}
            {generation.output_qa_repairs?.map(a=><p key={`qa-${a.attempt}`}>Final QA repair {a.attempt} · slides {a.targets.map(i=>i+1).join(', ')}: {a.accepted?'accepted after recheck':'previous candidate retained'}{a.reason?` — ${a.reason}`:''}</p>)}
            {generation.repair_stop_reason && <p className="text-stevens-red">{generation.repair_stop_reason}</p>}
            {generation.ai_pipeline.calls.filter(c=>c.status!=='completed').map((c,i)=><p className="text-stevens-red" key={i}>{c.role}: {c.status} — {c.message}</p>)}
          </div>}
          {generation && deckFindings.length > 0 && <details className="mt-5 border-t pt-4">
            <summary className="cursor-pointer text-sm font-bold">Deck-wide findings ({deckFindings.length})</summary>
            <p className="mt-2 text-xs text-stevens-gray">These checks apply to the whole presentation.</p>
            <FindingsList key={`${reviewScope}:deck`} findings={deckFindings} resolved={resolved} busy={busy} onApprove={approve} deckWide />
          </details>}
        </aside>
      </div>
      {generation && !generating && generation.state !== 'checking' && <section className="card mt-5 p-5">
        <h2 className="font-bold">Findings for this page</h2>
        <p className="mt-1 text-sm text-stevens-gray">Output slide {output+1} · {current>=0 ? `Source slide ${current+1}` : 'No original slide'}{outputs.length > 1 ? ` · Part ${outputs.indexOf(output)+1} of ${outputs.length}` : ''} · {pageFindings.length} findings</p>
        <FindingsList key={`${reviewScope}:${current}:${output}`} findings={pageFindings} resolved={resolved} busy={busy} onApprove={approve} />
      </section>}
    </main>}
  </div>;
}
