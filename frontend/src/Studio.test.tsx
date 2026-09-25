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
  expect(await screen.findByRole('button',{name:'Generate and verify'})).toBeDisabled();
  fireEvent.click(screen.getByRole('button',{name:'Save and approve outline'}));
  await waitFor(()=>expect(screen.getByRole('button',{name:'Generate and verify'})).toBeEnabled());
  fireEvent.change(screen.getByLabelText('Slide 1 title'),{target:{value:'Updated opening'}});
  expect(screen.getByRole('button',{name:'Generate and verify'})).toBeDisabled();
});
