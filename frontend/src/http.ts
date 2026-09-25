let csrf = '';
export function setCSRF(value: string) { csrf = value; }
export function apiFetch(input: string, init: RequestInit = {}) {
  const headers = new Headers(init.headers);
  if (!['GET','HEAD'].includes((init.method || 'GET').toUpperCase()) && csrf) headers.set('X-CSRF-Token', csrf);
  return fetch(input, {...init, headers, credentials:'same-origin', cache:'no-store'}).then(response=>{
    if(response.status===401&&!input.endsWith('/auth/code'))window.dispatchEvent(new Event('studio-signout'));
    return response;
  });
}
export async function jsonRequest<T>(path: string, body?: unknown, method='POST'): Promise<T> {
  const response = await apiFetch(path, body === undefined ? {} : {method, headers:{'Content-Type':'application/json'}, body:JSON.stringify(body)});
  const data = await response.json();
  if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail));
  return data;
}
