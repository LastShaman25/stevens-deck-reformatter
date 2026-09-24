import { useEffect, useRef, useState } from "react";
import { UploadStep } from "./steps/UploadStep";
import { FindingsList, findingSource } from './components/FindingsList';
import type { AIConfiguration, Generation, Revision, SessionInfo } from "./types";

async function request<T>(path: string, body?: unknown, method = "POST"): Promise<T> {
  const res = await fetch(`/api${path}`, body === undefined ? undefined : {
    method, headers: {"Content-Type": "application/json"}, body: JSON.stringify(body)
  });
  const value = await res.json();
  if (!res.ok) throw new Error(typeof value.detail === 'string' ? value.detail : JSON.stringify(value.detail));
  return value;
}
const empty: Revision = {tags: [], instruction: "", reset_emphasis: false};

function Preview({url, label}: {url: string | null; label: string}) {
  const [failed, setFailed] = useState(false);
  useEffect(() => setFailed(false), [url]);
  return <figure className="min-w-0 flex-1"><figcaption className="mb-2 text-xs font-bold text-stevens-gray">{label}</figcaption>
    {url && !failed ? <img className="w-full rounded border border-stevens-lightgray" src={url} alt={label} onError={() => setFailed(true)} /> :
      <div className="grid min-h-48 place-items-center rounded border border-stevens-lightgray bg-white p-5 text-sm text-stevens-gray">Rendered preview unavailable</div>}
  </figure>;
}

export default function App() {
  const [session, setSession] = useState<SessionInfo | null>(null);
  const [generation, setGeneration] = useState<Generation | null>(null);
  const [current, setCurrent] = useState(0);
  const [output, setOutput] = useState(0);
  const [revs, setRevs] = useState<Record<number, Revision>>({});
  const [selectedAi, setSelectedAi] = useState<number[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>();
  const [notice, setNotice] = useState('');
  const [saved, setSaved] = useState(false);
  const [mode,setMode] = useState<'preserve'|'ai'>('preserve');
  const [aiConfig,setAiConfig] = useState<AIConfiguration>();
  const [connection,setConnection] = useState<Record<string,{status:string; message?:string}>>();
  const [generating,setGenerating] = useState(false);
  const modeChosen = useRef(false);
  const generationPending = useRef(false);
  const scope = useRef(0);
  const dirty = useRef(new Set<number>());

  function restore(info: SessionInfo) {
    setSession(info); setGeneration(info.generation ?? null); setRevs(info.revisions ?? {});
    setSelectedAi(info.ai_check ?? []); setCurrent(0); setOutput(0); setSaved(!!info.benchmarked);
    setAiConfig(info.capabilities.ai);
    setMode(info.generation?.mode ?? (info.capabilities.ai?.configured ? 'ai' : 'preserve'));
    modeChosen.current=true;
    dirty.current.clear();
  }
  useEffect(() => {
    request<{capabilities:{ai?:AIConfiguration}}>('/health').then(h=>{
      setAiConfig(h.capabilities.ai);
      if (!modeChosen.current) setMode(h.capabilities.ai?.configured ? 'ai' : 'preserve');
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
      const res = await fetch('/api/sessions', {method:'POST', body:data});
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
      const res = await request<{generation: Generation}>(`/sessions/${sid}/generate`, {mode,repair_passes:1});
      if (token !== scope.current) return;
      generationPending.current=false;
      setGeneration(res.generation); setSaved(false);
      setOutput(res.generation.source_to_output_slides[String(current)]?.[0] ?? 0);
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
  async function toggleAi() {
    if (!session) return;
    const token = scope.current;
    const enabled = !selectedAi.includes(current);
    await operation(async () => {
      const res = await request<{generation: Generation | null}>(`/sessions/${session.session_id}/slides/${current}/ai-check`, {enabled});
      if (token !== scope.current) return;
      setSelectedAi(a => enabled ? [...a, current] : a.filter(i => i !== current));
      setGeneration(res.generation);
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
  async function download(draft: boolean) {
    if (!session || !generation) return;
    await operation(async () => {
      const res = await fetch(`/api/sessions/${session.session_id}/download?generation_id=${generation.generation_id}&draft=${draft}`);
      if (!res.ok) {const err = await res.json(); throw new Error(err.detail);}
      const url = URL.createObjectURL(await res.blob());
      const a = document.createElement('a'); a.href = url;
      a.download = draft ? 'Stevens-unverified-draft.pptx' : 'Stevens-verified.pptx'; a.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    });
  }
  async function saveBenchmark() {
    if (!session || !generation) return;
    const token = scope.current;
    await operation(async () => {
      await request(`/sessions/${session.session_id}/benchmark`, {generation_id:generation.generation_id});
      if (token === scope.current) setSaved(true);
    });
  }
  async function startOver() {
    const old = session;
    ++scope.current;
    setSession(null); setGeneration(null); setRevs({}); setSelectedAi([]); setError(undefined);
    setNotice(''); setSaved(false); setBusy(false); setCurrent(0); setOutput(0); dirty.current.clear();
    generationPending.current=false;setGenerating(false);setMode(aiConfig?.configured?'ai':'preserve');modeChosen.current=false;
    window.history.replaceState({}, '', window.location.pathname);
    if (old) await fetch(`/api/sessions/${old.session_id}`, {method:'DELETE'}).catch(() => {});
  }
  function navigateSlide(index: number) {
    if (busy || !session || index < 0 || index >= session.slide_count) return;
    setCurrent(index);
    setOutput(generation?.source_to_output_slides[String(index)]?.[0] ?? 0);
  }
  const rev = revs[current] ?? empty;
  const resolved = new Set(generation?.human_decisions.flatMap(d => d.finding_ids) ?? []);
  const outputs = generation?.source_to_output_slides[String(current)] ?? [];
  const pageFindings = generation?.findings.filter(f => f.output_slide != null
    ? outputs.includes(output) && f.output_slide === output : findingSource(f) === current) ?? [];
  const deckFindings = generation?.findings.filter(f => f.output_slide == null && findingSource(f) == null) ?? [];
  const reviewScope = `${session?.session_id}:${generation?.generation_id}:${generation?.candidate_sha256}`;
  const sid = session?.session_id;
  return <div className="min-h-screen bg-[#f5f7fa] text-stevens-ink">
    <header className="flex items-center justify-between border-b border-stevens-lightgray bg-white px-6 py-4">
      <div><h1 className="text-xl font-extrabold">Stevens Slide Studio</h1><p className="text-xs text-stevens-gray">Preserve content. Verify the exported deck.</p></div>
      {session && <button className="btn-ghost" onClick={startOver} disabled={busy}>Start a new deck</button>}
    </header>
    <section className="mx-5 mt-4 rounded border border-stevens-lightgray bg-white p-4 text-sm" aria-label="AI configuration">
      <div className="flex flex-wrap items-center gap-3"><b>AI redesign and review</b>
        <button className="btn-ghost" disabled={busy} onClick={()=>refreshAI(false)}>Refresh AI configuration</button>
        <button className="btn-ghost" disabled={busy || !aiConfig?.configured} onClick={()=>refreshAI(true)}>Test AI connection</button></div>
      <p className="mt-2">Planner: {aiConfig?.planner.model || 'not configured'} · Reviewer: {aiConfig?.reviewer.model || 'not configured'}</p>
      {!aiConfig?.configured ? <p className="mt-1 text-stevens-gray">{aiConfig?.planner.provider==='openai' && aiConfig?.reviewer.provider==='openai' ? 'Add OPENAI_API_KEY to backend/.env locally, then refresh.' : 'Configure the provider keys in backend/.env locally, then refresh.'} Never paste keys into reviewer notes.</p> :
        <p className="mt-1 text-stevens-gray">{aiConfig.independent_providers ? 'Separate providers plan and review.' : 'One provider performs separate planning and review calls.'} AI mode sends slide content and rendered images to these providers. API usage may incur charges.</p>}
      {connection && Object.entries(connection).map(([role,result])=><p role="status" key={role}>{role}: {result.status}{result.message ? ` — ${result.message}` : ''}</p>)}
    </section>
    {error && <div role="alert" className="m-5 rounded border border-stevens-red bg-red-50 p-4 text-stevens-red">{error}</div>}
    {notice && <div role="status" className="mx-5 mt-4 rounded bg-stevens-lightblue p-3 text-sm">{notice}</div>}
    {!session ? <UploadStep onFile={upload} busy={busy} /> : <main className="mx-auto max-w-7xl p-5">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3"><div><h2 className="text-lg font-bold">{session.name}</h2>
        <p className="text-sm text-stevens-gray">{session.slide_count} source slides{generation ? ` → ${generation.built_slides} output slides` : ''}</p></div>
        <div className="flex flex-wrap items-center gap-3"><label>Generation mode <select aria-label="Generation mode" value={mode} disabled={busy} className="ml-2 rounded border p-2" onChange={e=>{
          modeChosen.current=true;setMode(e.target.value as 'ai'|'preserve');setGeneration(null);setSaved(false);
        }}><option value="ai">AI redesign + full check</option><option value="preserve">Preserve + deterministic check</option></select></label>
        <button className="btn-red" disabled={busy || (mode==='ai' && !aiConfig?.configured)} onClick={generate}>{busy ? 'Working…' : 'Generate and verify'}</button></div></div>
      <div className="grid gap-5 lg:grid-cols-[1fr_330px]">
        <section className="card p-5">
          <nav aria-label="Slide navigation" className="mb-4 flex flex-wrap items-center justify-between gap-2">
            <button aria-label="Previous slide" className="btn-ghost disabled:cursor-not-allowed disabled:opacity-40" disabled={busy || current === 0} onClick={() => navigateSlide(current-1)}>
              <span aria-hidden="true">←</span> Previous slide
            </button>
            <span className="text-sm text-stevens-gray" aria-live="polite">Slide {current+1} of {session.slide_count}</span>
            <button aria-label="Next slide" className="btn-ghost disabled:cursor-not-allowed disabled:opacity-40" disabled={busy || current >= session.slide_count-1} onClick={() => navigateSlide(current+1)}>
              Next slide <span aria-hidden="true">→</span>
            </button>
          </nav>
          <label className="block text-sm font-bold">Source slide <select aria-label="Source slide" className="mt-1 w-full min-w-0 rounded border p-2" value={current} disabled={busy} onChange={e => navigateSlide(Number(e.target.value))}>
            {session.slides.map(s => <option key={s.index} value={s.index}>{s.index+1}: {s.title}</option>)}</select></label>
          {outputs.length > 1 && <label className="ml-3 text-sm">Output part <select aria-label="Output part" value={output} disabled={busy} onChange={e => setOutput(Number(e.target.value))}>
            {outputs.map((o,i) => <option key={o} value={o}>{i+1}</option>)}</select></label>}
          <div className="mt-4 flex flex-col gap-4 md:flex-row">
            <Preview url={`/api/sessions/${sid}/slides/${current}/preview?variant=before`} label="Original source" />
            <Preview url={generation && generation.state!=='checking' && !generating && outputs.length ? `/api/sessions/${sid}/slides/${output}/preview?variant=after&generation_id=${generation.generation_id}` : null} label="Generated candidate" />
          </div>
          <p className="mt-3 text-xs text-stevens-gray">Previews show real renders when available. Review decisions apply to a specific generated file.</p>
          <fieldset disabled={busy} className="mt-5"><legend className="text-sm font-bold">Corrections</legend>
            <div className="mt-2 flex flex-wrap gap-2">{[['split','Split slide'],['dense','Too dense'],['layout','Layout'],['overlap','Overlap'],['diagram','Preserve diagram'],['emphasis','Source emphasis']].map(([id,label]) =>
              <button key={id} aria-pressed={rev.tags.includes(id)} className={rev.tags.includes(id) ? 'btn-red' : 'btn-ghost'} onClick={() => changeRevision({...rev, tags:rev.tags.includes(id) ? rev.tags.filter(x => x !== id) : [...rev.tags,id], reset_emphasis: id === 'emphasis' ? true : rev.reset_emphasis})}>{label}</button>)}</div>
            <label className="mt-4 block text-sm">{mode==='ai' ? 'Redesign instructions' : 'Reviewer note — does not automatically edit the slide'}
              <textarea aria-label="Reviewer note" className="mt-1 w-full rounded border p-3" rows={3} value={rev.instruction} onChange={e => changeRevision({...rev,instruction:e.target.value})} /></label>
            <p className="mt-1 text-xs text-stevens-gray">In AI mode, notes guide layout and styling. Original wording, chart data, notes, and links remain protected.</p>
            <button className="btn-ghost mt-2" onClick={apply}>Save revision</button>
          </fieldset>
          <label className="mt-4 flex items-center gap-2 text-sm"><input type="checkbox" checked={selectedAi.includes(current)} disabled={busy || mode==='ai'} onChange={toggleAi} />Optional AI visual check for this source slide</label>
          {mode==='ai' && <p className="mt-1 text-xs">AI redesign already includes mandatory visual review of every output slide and one repair pass.</p>}
          <p className="mt-1 text-xs text-stevens-gray">Selecting this check sends its rendered output to the configured provider. It cannot replace required verification.</p>
          {generation?.corrections.filter(c => c.index === current).flatMap(c => c.actions).map((a,i) => <p className="mt-2 text-sm" key={i}>{a.action}: <b>{a.status}</b> — {a.message}</p>)}
        </section>
        <aside className="card p-5"><h2 className="text-lg font-bold">Verification</h2>
          <p role="status" className="mt-2 font-semibold">{busy ? 'Processing…' : generation ? generation.state.replace('_',' ') : 'Not yet generated'}</p>
          {generating && generation?.progress && <p role="status" className="mt-2 text-sm">{generation.progress.stage.replace(/_/g,' ')}{generation.progress.output_slide!==undefined ? ` · output slide ${generation.progress.output_slide+1}` : ''}{generation.progress.completed_calls!==undefined ? ` · ${generation.progress.completed_calls} AI calls completed` : ''}</p>}
          {!generation && <p className="mt-2 text-sm text-stevens-gray">Generate a candidate to check content, formatting, and rendered output.</p>}
          {generation && <><ul className="mt-3 space-y-2 text-sm">{Object.entries(generation.checks).map(([name,result]) => <li key={name}><b>{name.replace(/_/g,' ')}</b>: {result.status.replace(/_/g,' ')}</li>)}</ul>
            <div className="mt-4 flex flex-col gap-2"><button className="btn-red" disabled={busy || generation.state !== 'ready'} onClick={() => download(false)}>Download verified PowerPoint</button>
              <button className="btn-ghost" disabled={busy || !generation.candidate_sha256} onClick={() => download(true)}>Download unverified draft</button>
              <button className="btn-ghost" disabled={busy || generation.state !== 'ready' || saved} onClick={saveBenchmark}>{saved ? 'Approved benchmark saved' : 'Save approved benchmark'}</button></div>
            <p className="mt-2 text-xs text-stevens-gray">Benchmark save is your explicit approval of this ready artifact. Saved benchmarks remain on this computer.</p></>}
          {generation?.ai_pipeline && <div className="mt-4 text-sm"><b>AI pipeline: {generation.ai_pipeline.status}</b>
            <p>{generation.ai_pipeline.calls.length} calls · {generation.ai_pipeline.changed_objects} object edits</p>
            {generation.ai_pipeline.attempts.map((a,i)=><p key={i}>Pass {a.attempt+1}: {a.accepted?'accepted':'rejected'}{a.reason?` — ${a.reason}`:''}</p>)}
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
        <p className="mt-1 text-sm text-stevens-gray">Source slide {current+1}{outputs.length > 1 ? ` · Output part ${outputs.indexOf(output)+1} of ${outputs.length}` : ''} · {pageFindings.length} findings</p>
        <FindingsList key={`${reviewScope}:${current}:${output}`} findings={pageFindings} resolved={resolved} busy={busy} onApprove={approve} />
      </section>}
    </main>}
  </div>;
}
