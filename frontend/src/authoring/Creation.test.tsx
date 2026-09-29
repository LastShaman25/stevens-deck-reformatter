import {beforeEach,expect,test,vi} from 'vitest';
import {render,screen,fireEvent,waitFor} from '@testing-library/react';
import {Creation} from './Creation';

const response=(value:unknown)=>Promise.resolve({ok:true,json:async()=>value} as Response);
beforeEach(()=>{vi.restoreAllMocks();history.replaceState({},'','/?job=demo');});

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
