import {beforeEach,expect,test,vi} from 'vitest';
import {apiFetch,jsonRequest,setSharedBackend} from './http';

beforeEach(()=>{vi.restoreAllMocks();setSharedBackend(false);});

test('plain-text Vercel 404 produces a routing message instead of a JSON parse error',async()=>{
  vi.stubGlobal('fetch',vi.fn(async()=>new Response('The page could not be found',{status:404,headers:{'Content-Type':'text/plain'}})));
  await expect(jsonRequest('/api/auth/status')).rejects.toThrow('route /api/* to FastAPI');
});

test('HTML fallback at a successful API URL is also rejected',async()=>{
  vi.stubGlobal('fetch',vi.fn(async()=>new Response('<html>frontend</html>',{headers:{'Content-Type':'text/html'}})));
  await expect(jsonRequest('/api/auth/status')).rejects.toThrow('backend is unavailable');
});

test('malformed JSON and network outages produce useful errors',async()=>{
  vi.stubGlobal('fetch',vi.fn(async()=>new Response('broken',{headers:{'Content-Type':'application/json'}})));
  await expect(jsonRequest('/api/auth/status')).rejects.toThrow('invalid response');
  vi.stubGlobal('fetch',vi.fn(async()=>{throw new Error('network');}));
  await expect(apiFetch('/api/auth/status')).rejects.toThrow('Cannot reach');
});

test('queued operations return their durable result',async()=>{
  const tid='a'.repeat(32);
  vi.stubGlobal('fetch',vi.fn(async(url:string)=>new Response(JSON.stringify(url==='/api/jobs/j/generate'
    ? {task_id:tid,status_url:`/api/cloud/tasks/${tid}`} : {state:'completed',result:{status:'verified'}}),
    {status:url==='/api/jobs/j/generate'?202:200,headers:{'Content-Type':'application/json'}})));
  expect(await jsonRequest('/api/jobs/j/generate',{})).toEqual({status:'verified'});
});
