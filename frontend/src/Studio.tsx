import {useEffect, useState} from 'react';
import App from './App';
import {Creation} from './authoring/Creation';
import {jsonRequest, setCSRF} from './http';

type User = {id:string; email:string; role:'member'|'admin'; active:number};
type Auth = {user:User|null; csrf:string|null; mode:string; configured:boolean};

function Administration() {
  const [users,setUsers] = useState<User[]>([]), [name,setName] = useState(''), [role,setRole] = useState('member');
  const [code,setCode] = useState(''), [error,setError] = useState(''), [busy,setBusy] = useState(false);
  const refresh=()=>jsonRequest<{users:User[]}>('/api/admin/users').then(r=>setUsers(r.users));
  useEffect(()=>{refresh().catch(e=>setError(e.message));},[]);
  async function act(fn:()=>Promise<void>){setBusy(true);setError('');try{await fn();await refresh();}catch(e){setError((e as Error).message);}finally{setBusy(false);}}
  return <section className="card mx-auto mt-6 max-w-4xl p-6"><h2 className="text-xl font-bold">Manage users and invitation codes</h2>
    <p className="mt-2 text-sm">Each code belongs to one account. Deactivate an account to revoke access; replace its code if needed.</p>
    {error&&<p role="alert" className="mt-3 text-red-700">{error}</p>}
    <form className="my-5 flex flex-wrap gap-3" onSubmit={e=>{e.preventDefault();act(async()=>{const r=await jsonRequest<{code:string}>('/api/admin/codes',{name,role});setCode(r.code);setName('');});}}>
      <input aria-label="Account name" className="rounded border p-2" placeholder="Account name" value={name} onChange={e=>setName(e.target.value)} required/>
      <select aria-label="New account role" value={role} onChange={e=>setRole(e.target.value)} className="rounded border p-2"><option value="member">Member</option><option value="admin">Administrator</option></select>
      <button className="btn-red" disabled={busy}>Create invitation code</button></form>
    {code&&<div role="status" className="mb-5 rounded border bg-blue-50 p-3"><p>Copy this code now. It is shown only here.</p><code className="break-all select-all text-lg">{code}</code></div>}
    <ul className="divide-y">{users.map(u=><li key={u.id} className="flex flex-wrap items-center justify-between gap-3 py-3"><span>{u.email} · {u.active?'Active':'Inactive'}</span>
      <div className="flex gap-2"><select aria-label={`Role for ${u.email}`} disabled={busy} value={u.role} onChange={e=>act(async()=>{await jsonRequest(`/api/admin/users/${u.id}`,{role:e.target.value,active:!!u.active},'PATCH');})}><option value="member">Member</option><option value="admin">Administrator</option></select>
      <button className="btn-ghost" disabled={busy} onClick={()=>act(async()=>{await jsonRequest(`/api/admin/users/${u.id}`,{role:u.role,active:!u.active},'PATCH');})}>{u.active?'Deactivate':'Reactivate'}</button>
      <button className="btn-ghost" disabled={busy} onClick={()=>act(async()=>{const r=await jsonRequest<{code:string;csrf?:string}>(`/api/admin/users/${u.id}/rotate-code`,{});if(r.csrf)setCSRF(r.csrf);setCode(r.code);})}>Replace code</button><button className="btn-ghost" disabled={busy||!!u.active} onClick={()=>act(async()=>{await jsonRequest(`/api/admin/users/${u.id}`,{},'DELETE');})}>Remove inactive account</button></div></li>)}</ul>
  </section>;
}

export default function Studio(){
  const [auth,setAuth] = useState<Auth|null>(null), [code,setCode]=useState(''), [error,setError]=useState('');
  const [screen,setScreen]=useState<'home'|'ppt'|'create'|'admin'>(new URLSearchParams(location.search).has('session')?'ppt':new URLSearchParams(location.search).has('job')?'create':'home');
  const [busy,setBusy]=useState(false);
  function accept(value:Auth){setAuth(value);setCSRF(value.csrf||'');}
  useEffect(()=>{jsonRequest<Auth>('/api/auth/status').then(accept).catch(e=>setError(e.message));},[]);
  useEffect(()=>{const expired=()=>{setCSRF('');setAuth(previous=>previous?{...previous,user:null,csrf:null}:previous);setError('Your sign-in expired or was revoked. Sign in again.');};window.addEventListener('studio-signout',expired);return()=>window.removeEventListener('studio-signout',expired);},[]);
  async function login(e:React.FormEvent){e.preventDefault();setBusy(true);setError('');try{accept(await jsonRequest<Auth>('/api/auth/code',{code}));setCode('');}catch(e){setError((e as Error).message);}finally{setBusy(false);}}
  async function logout(){setBusy(true);try{await jsonRequest('/api/auth/logout',{});accept({...auth!,user:null,csrf:null});setScreen('home');history.replaceState({},'',location.pathname);}catch(e){setError((e as Error).message);}finally{setBusy(false);}}
  const home=()=>{setScreen('home');history.replaceState({},'',location.pathname);};
  if(!auth)return <main className="p-10" role="status">{error||'Loading sign-in…'}</main>;
  if(!auth.user)return <main className="mx-auto mt-20 max-w-md card p-8"><h1 className="text-2xl font-bold">Stevens Slide Studio</h1><p className="mt-2">Sign in to create or redesign a presentation.</p>
    {error&&<p role="alert" className="mt-4 text-red-700">{error}</p>}
    {auth.mode==='invitation'?<form className="mt-6 space-y-4" onSubmit={login}><label className="block">Invitation code<input type="password" autoComplete="off" className="mt-2 w-full rounded border p-3" value={code} onChange={e=>setCode(e.target.value)} required/></label><button className="btn-red w-full" disabled={busy}>Sign in</button></form>:<a className="btn-red mt-5 inline-block" href="/auth/login">Continue with Google</a>}
  </main>;
  return <div><header className="flex flex-wrap items-center justify-between gap-3 border-b bg-white px-5 py-3"><button className="font-bold" onClick={home}>Stevens Slide Studio</button><div className="flex items-center gap-3 text-sm"><span>{auth.user.email}</span>{auth.user.role==='admin'&&<button className="btn-ghost" onClick={()=>setScreen('admin')}>Manage users</button>}<button className="btn-ghost" disabled={busy} onClick={logout}>Sign out and delete active work</button></div></header>
    {error&&<p role="alert" className="p-3 text-red-700">{error}</p>}
    {screen==='home'&&<main className="mx-auto max-w-4xl p-8"><h1 className="text-3xl font-bold">What would you like to work on?</h1><p className="mt-3 text-stevens-gray">Files are temporary and deleted when you finish or cancel, or when the session expires.</p><div className="mt-8 grid gap-6 md:grid-cols-2">
      <button className="card p-8 text-left hover:border-stevens-red" onClick={()=>setScreen('ppt')}><h2 className="text-xl font-bold">Use my PowerPoint</h2><p className="mt-3">Upload your deck to improve layout and alignment while preserving its content.</p></button>
      <button className="card p-8 text-left hover:border-stevens-red" onClick={()=>setScreen('create')}><h2 className="text-xl font-bold">Generate a new presentation</h2><p className="mt-3">Start with a topic, outline, or PDF. Approve an outline, then create and verify your slides.</p></button>
    </div></main>}
    {screen==='ppt'&&<App onHome={home}/>}{screen==='create'&&<Creation onHome={home}/>}{screen==='admin'&&<Administration/>}
  </div>;
}
