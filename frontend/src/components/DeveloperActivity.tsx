import {useEffect,useState,useRef} from 'react';
import {jsonRequest} from '../http';

type Event={id:string;timestamp:string;job_id:string|null;agent:string;action:string;status:string;model?:string;provider?:string;duration_ms?:number;tokens?:number;input_tokens?:number;output_tokens?:number;attempt?:number;template_id?:string;http_status?:number;error_type?:string};
type Job={job_id:string|null;started_at:string;updated_at:string;status:string;workflow:string;input_category:string;output_category:string;template_id?:string;duration_ms:number|null;tokens:number|null;input_tokens:number|null;output_tokens:number|null;requests:number;event_count:number;usage_complete:boolean};
type Details={events:Event[];next_before:string|null};
const number=(value:number|null|undefined)=>value==null?'Not recorded':value.toLocaleString();
const duration=(ms:number|null|undefined)=>ms==null?'Not recorded':ms<60000?`${(ms/1000).toFixed(1)}s`:`${Math.floor(ms/60000)}m ${Math.floor(ms%60000/1000)}s`;
const time=(stamp:string)=><time dateTime={stamp} title={stamp}>{new Date(stamp).toLocaleString()}</time>;
const key=(job:Job)=>job.job_id??'unassigned';

export function DeveloperActivity(){
  const [jobs,setJobs]=useState<Job[]>([]),[selected,setSelected]=useState<string|null>(null),[events,setEvents]=useState<Event[]>([]);
  const [error,setError]=useState(''),[live,setLive]=useState(true),[cursor,setCursor]=useState<string|null>(null),[loading,setLoading]=useState(false);
  const keepOlder=useRef(false),selectionVersion=useRef(0);
  const job=jobs.find(j=>key(j)===selected);
  const endpoint=selected==='unassigned'?'/api/developer/activity?unassigned=true':`/api/developer/activity?job_id=${encodeURIComponent(selected||'')}`;
  useEffect(()=>{let disposed=false;let pending=false;
    const refresh=async()=>{if(pending)return;pending=true;try{
      const list=await jsonRequest<{jobs:Job[]}>('/api/developer/jobs');
      const detail=selected?await jsonRequest<Details>(endpoint):null;
      if(!disposed){setJobs(list.jobs);if(detail){setEvents(old=>keepOlder.current?[...old.filter(e=>!detail.events.some(n=>n.id===e.id)),...detail.events].sort((a,b)=>a.timestamp.localeCompare(b.timestamp)):detail.events);if(!keepOlder.current)setCursor(detail.next_before);}setError('');}
    }catch(e){if(!disposed)setError((e as Error).message);}finally{pending=false;}};
    refresh();const timer=live?setInterval(refresh,2000):undefined;
    return()=>{disposed=true;clearInterval(timer);};
  },[selected,live,endpoint]);
  const open=(j:Job)=>{selectionVersion.current++;setLoading(false);keepOlder.current=false;setEvents([]);setCursor(null);setSelected(key(j));};
  const older=async()=>{const version=selectionVersion.current;keepOlder.current=true;setLive(false);setLoading(true);try{const r=await jsonRequest<Details>(`${endpoint}&before=${encodeURIComponent(cursor||'')}`);if(version!==selectionVersion.current)return;setEvents(old=>[...r.events,...old.filter(e=>!r.events.some(n=>n.id===e.id))].sort((a,b)=>a.timestamp.localeCompare(b.timestamp)));setCursor(r.next_before);}catch(e){if(version===selectionVersion.current)setError((e as Error).message);}finally{if(version===selectionVersion.current)setLoading(false);}};
  return <section className="card mx-auto mt-6 max-w-6xl p-6"><h2 className="text-xl font-bold">Developer activity</h2>
    <p className="mt-2 text-sm text-stevens-gray">Jobs and agent activity from the last 24 hours. Timestamps use your local time. Prompts, deck content and credentials are excluded.</p>
    <div className="my-4 flex flex-wrap items-center gap-4">{selected&&<button className="btn-ghost" onClick={()=>{selectionVersion.current++;setLoading(false);setSelected(null);}}>Back to jobs</button>}<label><input type="checkbox" checked={live} onChange={e=>setLive(e.target.checked)}/> Live updates</label></div>
    {error&&<p role="alert" className="text-red-700">{error}</p>}
    {!selected?<><h3 className="font-bold">Jobs</h3>{!jobs.length&&!error&&<p>No jobs recorded yet. Start a deck to see its activity here.</p>}
      <div className="overflow-x-auto"><table className="w-full text-left text-sm"><thead><tr><th className="p-2">Job / workflow</th><th>Started</th><th>Status</th><th>Input → output</th><th>Processing time</th><th>Input tokens</th><th>Output tokens</th><th>Total tokens</th></tr></thead>
      <tbody>{jobs.map(j=><tr key={key(j)} className="border-t"><td className="p-2"><button className="underline" onClick={()=>open(j)} aria-label={`Open job ${j.job_id||'connection tests'}`}>{j.job_id?.slice(0,8)||'Connection tests'}</button><div>{j.workflow} · {j.template_id||'No template'}</div></td><td>{time(j.started_at)}</td><td>{j.status}</td><td>{j.input_category} → {j.output_category}</td><td>{duration(j.duration_ms)}</td><td>{number(j.input_tokens)}</td><td>{number(j.output_tokens)}</td><td>{number(j.tokens)}{!j.usage_complete&&j.requests>0&&<div className="text-xs">Usage incomplete</div>}</td></tr>)}</tbody></table></div></>:
      <><h3 className="font-bold break-all">{job?.job_id?`Job ${job.job_id}`:'Connection tests'}</h3>{job&&<div className="my-4 grid gap-2 text-sm sm:grid-cols-2 lg:grid-cols-3"><p>Status: {job.status}</p><p>Processing time: {duration(job.duration_ms)}</p><p>{job.input_category} → {job.output_category}</p><p>Input tokens: {number(job.input_tokens)}</p><p>Output tokens: {number(job.output_tokens)}</p><p>Total tokens: {number(job.tokens)} · {job.requests} requests</p><p>Started: {time(job.started_at)}</p><p>Last activity: {time(job.updated_at)}</p></div>}
      <p className="mb-4 text-sm text-stevens-gray">Processing time excludes time waiting for outline approval. Token totals include retries, exclude cached replays, and cover retained activity only. Missing provider usage is shown as not recorded. Output formats indicate supported exports.</p>
      {job&&!job.usage_complete&&job.requests>0&&<p className="mb-3 text-sm">Usage is incomplete: one or more requests did not report input/output tokens.</p>}
      <p className="mb-2 text-sm">Showing {events.length} of {job?.event_count??events.length} events</p>
      {cursor!=null&&<button className="btn-ghost mb-3" disabled={loading} onClick={older}>Load older events (pauses live updates)</button>}
      <div className="overflow-x-auto"><table className="w-full text-left text-sm"><thead><tr><th className="p-2">Time</th><th>Agent / tool</th><th>Action</th><th>Status</th><th>Duration</th><th>Input tokens</th><th>Output tokens</th><th>Details</th></tr></thead>
      <tbody>{events.map(e=><tr key={e.id} className="border-t"><td className="whitespace-nowrap p-2">{time(e.timestamp)}</td><td>{e.agent}</td><td>{e.action.replace(/_/g,' ')}</td><td>{e.status.replace(/_/g,' ')}</td><td>{duration(e.duration_ms)}</td><td>{e.action==='request_attempt'&&e.status!=='started'?number(e.input_tokens):'—'}</td><td>{e.action==='request_attempt'&&e.status!=='started'?number(e.output_tokens):'—'}</td><td>{[e.provider,e.model,e.template_id,e.error_type,e.attempt!=null?`Attempt ${e.attempt}`:null,e.http_status?`HTTP ${e.http_status}`:null].filter(Boolean).join(' · ')}</td></tr>)}</tbody></table></div></>}
  </section>;
}
