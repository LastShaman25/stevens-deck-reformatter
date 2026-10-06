import {beforeEach,expect,test,vi} from 'vitest';
import {render,screen,fireEvent,waitFor} from '@testing-library/react';
import Studio from './Studio';
import {setCSRF} from './http';

const response=(data:unknown,status=200)=>Promise.resolve({ok:status<400,status,json:async()=>data} as Response);
const user={id:'u1',email:'Administrator',role:'admin',active:1};
const auth={user,csrf:'csrf-test',mode:'invitation',configured:true};
beforeEach(()=>{vi.restoreAllMocks();history.replaceState({},'','/');setCSRF('');});

test('invitation sign-in opens two distinct workflow entries',async()=>{
  const fetcher=vi.fn((url:string)=>response(url==='/api/auth/code'?auth:{...auth,user:null,csrf:null}));
  vi.stubGlobal('fetch',fetcher);render(<Studio/>);
  fireEvent.change(await screen.findByLabelText('Invitation code'),{target:{value:'admin'}});
  fireEvent.click(screen.getByRole('button',{name:'Sign in'}));
  expect(await screen.findByRole('button',{name:/Use my PowerPoint/})).toBeVisible();
  expect(screen.getByRole('button',{name:/Generate a new presentation/})).toBeVisible();
  expect(fetcher.mock.calls.some(([url])=>url==='/api/auth/code')).toBe(true);
});

test('existing deck selection routes to upload while generation has adaptive length',async()=>{
  vi.stubGlobal('fetch',vi.fn((url:string)=>response(url==='/api/auth/status'?auth:{capabilities:{}})));
  render(<Studio/>);fireEvent.click(await screen.findByRole('button',{name:/Use my PowerPoint/}));
  expect(await screen.findByText('Build a better deck')).toBeVisible();
  fireEvent.click(screen.getByRole('button',{name:'Stevens Slide Studio'}));
  fireEvent.click(screen.getByRole('button',{name:/Generate a new presentation/}));
  expect(screen.getByLabelText('Presentation length')).toHaveValue('auto');
  expect(screen.getAllByRole('option').map(x=>x.textContent)).toContain('Detailed — evidence and examples');
  expect(screen.queryByRole('spinbutton')).not.toBeInTheDocument();
  expect(screen.getByLabelText('Start from')).toHaveValue('topic');
  fireEvent.change(screen.getByLabelText('Start from'),{target:{value:'pdf'}});
  expect(screen.getByLabelText('Source PDF')).toBeVisible();
});

test('administrator creates member code with CSRF and can revoke membership',async()=>{
  const fetcher=vi.fn((url:string,options?:RequestInit)=>response(url==='/api/auth/status'?auth:
    url==='/api/admin/users'?{users:[user,{id:'member',email:'Learner',role:'member',active:1}]}:
    url==='/api/admin/codes'?{code:'synthetic-invite'}:{ok:true}));
  vi.stubGlobal('fetch',fetcher);render(<Studio/>);
  fireEvent.click(await screen.findByRole('button',{name:'Manage users'}));
  fireEvent.change(await screen.findByLabelText('Account name'),{target:{value:'Learner'}});
  fireEvent.click(screen.getByRole('button',{name:'Create invitation code'}));
  expect(await screen.findByText('synthetic-invite')).toBeVisible();
  const call=fetcher.mock.calls.find(([url])=>url==='/api/admin/codes')!;
  expect(new Headers(call[1]?.headers).get('X-CSRF-Token')).toBe('csrf-test');
  const member=screen.getByText('Learner · Active').closest('li')!;
  fireEvent.click(Array.from(member.querySelectorAll('button')).find(b=>b.textContent==='Deactivate')!);
  await waitFor(()=>expect(fetcher.mock.calls.some(([url,opts])=>url==='/api/admin/users/member'&&JSON.parse(opts?.body as string).active===false)).toBe(true));
});

test('outline approval is required and edits invalidate generation',async()=>{
  const outline={title:'Topic',rationale:'Three concepts need three slides.',slides:[{id:'s1',title:'Opening',points:['Context'],source_pages:[]}]};
  const job={id:'j1',request:{},outline,revision:1,content_revision:1,approved_hash:null,deck:null,status:'outline',error:null,pages:[],generation:null,progress:{stage:'outline'},expires_at:9999999999};
  vi.stubGlobal('fetch',vi.fn((url:string)=>response(url==='/api/auth/status'?auth:url.endsWith('/outline/approve')?{...job,approved_hash:'hash'}:job)));
  history.replaceState({},'','/?job=j1');render(<Studio/>);
  expect(await screen.findByRole('button',{name:'2. Generate and verify'})).toBeDisabled();
  fireEvent.click(screen.getByRole('button',{name:'1. Save and approve outline'}));
  await waitFor(()=>expect(screen.getByRole('button',{name:'2. Generate and verify'})).toBeEnabled());
  fireEvent.change(screen.getByLabelText('Slide 1 title'),{target:{value:'Updated opening'}});
  expect(screen.getByRole('button',{name:'2. Generate and verify'})).toBeDisabled();
});

test('developer opens a job before inspecting activity and token breakdown',async()=>{
  const job={job_id:'job123',started_at:'2026-10-01T16:00:00+00:00',updated_at:'2026-10-01T16:00:02+00:00',status:'completed',workflow:'reformat',input_category:'pdf',output_category:'pptx / pdf',duration_ms:1234,input_tokens:100,output_tokens:20,tokens:120,requests:1,event_count:1,usage_complete:true};
  const fetcher=vi.fn((url:string)=>response(url==='/api/auth/status'?{...auth,user:{...user,role:'developer'}}:url==='/api/developer/jobs'?{jobs:[job]}:{events:[{id:'e',timestamp:job.started_at,job_id:'job123',agent:'reviewer',action:'request_attempt',status:'completed',model:'test-model',duration_ms:1234,input_tokens:100,output_tokens:20}],next_before:null}));
  vi.stubGlobal('fetch',fetcher);
  render(<Studio/>);fireEvent.click(await screen.findByRole('button',{name:'Developer activity'}));
  expect(await screen.findByRole('button',{name:'Open job job123'})).toBeVisible();
  expect(screen.queryByText('reviewer')).not.toBeInTheDocument();
  expect(fetcher.mock.calls.some(([url])=>url.startsWith('/api/developer/activity'))).toBe(false);
  expect(screen.getByText('120')).toBeVisible();
  fireEvent.click(screen.getByRole('button',{name:'Open job job123'}));
  expect(await screen.findByText('reviewer')).toBeVisible();
  expect(screen.getByText('test-model')).toBeVisible();
  expect(screen.getByText('Input tokens: 100')).toBeVisible();
  expect(screen.getByText('Output tokens: 20')).toBeVisible();
  expect(document.querySelector('time')).toHaveAttribute('datetime',job.started_at);
  expect(screen.queryByRole('button',{name:'Manage users'})).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button',{name:'Back to jobs'}));
  expect(await screen.findByRole('button',{name:'Open job job123'})).toBeVisible();
});

test('member does not see developer controls',async()=>{
  vi.stubGlobal('fetch',vi.fn(()=>response({...auth,user:{...user,role:'member'}})));
  render(<Studio/>);await screen.findByRole('button',{name:/Use my PowerPoint/});
  expect(screen.queryByRole('button',{name:'Developer activity'})).not.toBeInTheDocument();
});
