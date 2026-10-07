import {beforeEach,expect,test,vi} from 'vitest';
import {render,screen,fireEvent,waitFor} from '@testing-library/react';
import {Creation} from './Creation';

const response=(value:unknown)=>Promise.resolve({ok:true,json:async()=>value} as Response);
beforeEach(()=>{vi.restoreAllMocks();history.replaceState({},'','/?job=demo');});

test('new presentations require and submit a template choice',async()=>{
  history.replaceState({},'','/');
  const job={id:'demo',request:{source:'topic',template_id:'cpe'},outline:null,revision:0,approved_hash:null,pages:[],progress:{},expires_at:1,generation:null};
  const fetcher=vi.fn(()=>response(job));vi.stubGlobal('fetch',fetcher);
  const {container}=render(<Creation onHome={()=>{}}/>);
  expect(screen.getByLabelText('Presentation format')).toBeRequired();
  fireEvent.submit(container.querySelector('form')!);
  expect(fetcher).not.toHaveBeenCalled();
  fireEvent.change(screen.getByLabelText('Presentation format'),{target:{value:'cpe'}});
  fireEvent.change(screen.getByLabelText('Topic or starting outline'),{target:{value:'Example'}});
  fireEvent.change(screen.getByLabelText('Audience'),{target:{value:'Students'}});
  fireEvent.submit(container.querySelector('form')!);
  await waitFor(()=>expect(fetcher).toHaveBeenCalled());
  const call=(fetcher.mock.calls as unknown as [string,RequestInit][])[0];
  expect(JSON.parse(String(call[1].body)).template_id).toBe('cpe');
});

test('approval clearly unlocks generation and edits require approval again',async()=>{
  let job={id:'demo',request:{source:'topic'},revision:1,approved_hash:null as string|null,
    outline:{title:'Test',rationale:'Three slides including opening and closing.',slides:[
      {id:'opening',kind:'opening',title:'Introduction',points:['Purpose'],source_pages:[]},
      {id:'body',kind:'content',title:'Explanation',points:['Evidence'],source_pages:[],visual:{kind:'diagram',description:'Draft then review.',reason:'Show the process order.'}},
      {id:'closing',kind:'closing',title:'Thank you',points:['Questions'],source_pages:[]}]},
    generation:null,pages:[],progress:{},expires_at:1};
  const requests:string[]=[];
  vi.stubGlobal('fetch',vi.fn((url:string,options?:RequestInit)=>{
    requests.push(url);
    if(url.endsWith('/outline')&&options?.method==='PUT')job={...job,outline:JSON.parse(String(options.body)).outline,revision:2,approved_hash:null};
    if(url.endsWith('/approve'))job={...job,approved_hash:'approved'};
    return response(job);
  }));
  render(<Creation onHome={()=>{}}/>);
  const generate=await screen.findByRole('button',{name:'2. Generate and verify'});
  expect(generate).toBeDisabled();
  expect(screen.getByLabelText('Slide 2 visual plan')).toHaveValue('diagram');
  expect(screen.getByLabelText('Slide 2 visual description')).toHaveValue('Draft then review.');
  expect(screen.getByLabelText('Slide 1 visual plan')).toBeDisabled();
  expect(screen.getByText(/Approve the outline to enable step 2/)).toBeVisible();
  const removes=screen.getAllByRole('button',{name:'Remove'});
  expect(removes[0]).toBeDisabled();expect(removes[2]).toBeDisabled();
  fireEvent.click(screen.getByRole('button',{name:'1. Save and approve outline'}));
  await waitFor(()=>expect(generate).toBeEnabled());
  expect(screen.getByText(/Step 2 is ready/)).toBeVisible();
  fireEvent.change(screen.getByLabelText('Slide 2 visual plan'),{target:{value:'table'}});
  expect(generate).toBeDisabled();
  expect(screen.getByText(/Your outline has changes/)).toBeVisible();
  fireEvent.click(screen.getByRole('button',{name:'1. Save and approve outline'}));
  await waitFor(()=>expect(generate).toBeEnabled());
  expect(requests).toContain('/api/jobs/demo/outline');
  expect(job.outline.slides[1].visual?.kind).toBe('table');
  fireEvent.click(generate);
  await waitFor(()=>expect(requests).toContain('/api/jobs/demo/generate'));
});

test('failed composition shows its error without requesting a broken preview',async()=>{
  const generation={generation_id:'failed',candidate_sha256:null,state:'error',download_allowed:false,
    checks:{build:{status:'error'}},human_decisions:[],corrections:[],findings:[
      {id:'build:0',code:'AUTHORING_FAILED',check:'build',severity:'blocking',can_approve:false,
       message:'Generation stopped during composing (ValueError).'}]};
  const job={id:'demo',request:{source:'topic'},outline:{title:'Example',rationale:'One slide',slides:[
      {id:'s1',title:'Example',points:['Purpose'],source_pages:[]}]},
    deck:{slides:[{id:'s1',title:'Example',bullets:[],notes:'',citations:[]}]},
    revision:1,approved_hash:'approved',pages:[],progress:{},expires_at:1,generation};
  vi.stubGlobal('fetch',vi.fn(()=>response(job)));
  render(<Creation onHome={()=>{}}/>);
  expect(await screen.findByText(/No rendered preview is available/)).toBeVisible();
  expect(screen.getByText('Generation stopped during composing (ValueError).')).toBeVisible();
  expect(screen.queryByAltText('Output slide 1')).not.toBeInTheDocument();
  expect(screen.getByRole('button',{name:'Download'})).toBeDisabled();
});
