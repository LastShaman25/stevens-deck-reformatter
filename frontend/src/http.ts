let csrf = '';
let shared = false;
export function setSharedBackend(value: boolean) { shared = value; }
export function setCSRF(value: string) { csrf = value; }
async function rawFetch(input: string, init: RequestInit = {}): Promise<Response> {
  const headers = new Headers(init.headers);
  if (!['GET','HEAD'].includes((init.method || 'GET').toUpperCase()) && csrf) headers.set('X-CSRF-Token', csrf);
  let response: Response;
  try { response = await fetch(input, {...init, headers, credentials:'same-origin', cache:'no-store'}); }
  catch { throw new Error('Cannot reach the Slide Studio backend. Check your connection and try again.'); }
    if(response.status===401&&!input.endsWith('/auth/code'))window.dispatchEvent(new Event('studio-signout'));
    const type=response.headers?.get('content-type') || '';
    if(input.startsWith('/api/') && (type.includes('text/html') || type.includes('text/plain'))) {
      throw new Error(`The Slide Studio backend is unavailable (HTTP ${response.status}). The deployment must route /api/* to FastAPI. Please contact the administrator or try again later.`);
    }
    return response;
}

export async function readJSON(response: Response) {
  try { return await response.json(); }
  catch { throw new Error(`The Slide Studio backend returned an invalid response (HTTP ${response.status}). Please try again or contact the administrator.`); }
}

async function waitForTask(response:Response):Promise<Response> {
  const queued=await readJSON(response);
  if(!/^\/api\/cloud\/tasks\/[0-9a-f]{32}$/.test(queued.status_url))throw new Error('Invalid processing task response.');
  while(true) {
    const statusResponse=await rawFetch(queued.status_url);
    const status=await readJSON(statusResponse);
    if(!statusResponse.ok)throw new Error(status.detail || 'Cannot read processing status. Sign in again or retry.');
    if(status.state==='completed')return new Response(JSON.stringify(status.result),{headers:{'Content-Type':'application/json'}});
    if(['failed','cancelled'].includes(status.state))throw new Error(status.error || 'Processing stopped. Your output has not been released.');
    // Server-side leases make concurrent tabs and scheduler delivery safe.
    const advance=await rawFetch(`${queued.status_url}/advance`,{method:'POST'});
    if(!advance.ok)throw new Error('Processing could not advance. Your saved job remains on the server; reload to retry.');
    await new Promise(resolve=>setTimeout(resolve,1500));
  }
}

export async function apiFetch(input: string, init: RequestInit = {}):Promise<Response> {
  if(shared && init.body instanceof FormData && init.body.get('file') instanceof File) {
    const file=init.body.get('file') as File;
    const ticketResponse=await rawFetch('/api/cloud/uploads',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({target:input,filename:file.name,size:file.size})});
    const ticket=await readJSON(ticketResponse);
    if(!ticketResponse.ok)throw new Error(ticket.detail || 'Cannot prepare upload.');
    const form=new FormData();Object.entries(ticket.fields).forEach(([k,v])=>form.append(k,String(v)));form.append('file',file);
    const uploaded=await fetch(ticket.url,{method:'POST',body:form,credentials:'omit'});
    if(!uploaded.ok)throw new Error('The private file upload failed. Try uploading again.');
    const submitted=await rawFetch('/api/cloud/uploads/complete',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({upload_id:ticket.upload_id})});
    return submitted.status===202 ? waitForTask(submitted) : submitted;
  }
  const response=await rawFetch(input,init);
  if(response.status===202)return waitForTask(response);
  if(shared && response.ok && input.includes('/download')) {
    const data=await readJSON(response);
    if(!data.download_url)throw new Error('No verified download is available.');
    const file=await fetch(data.download_url,{credentials:'omit',cache:'no-store'});
    if(!file.ok)throw new Error('The verified download expired or failed. Try again.');
    return file;
  }
  return response;
}
export async function jsonRequest<T>(path: string, body?: unknown, method='POST'): Promise<T> {
  const response = await apiFetch(path, body === undefined ? {} : {method, headers:{'Content-Type':'application/json'}, body:JSON.stringify(body)});
  const data = await readJSON(response);
  if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail));
  return data;
}
