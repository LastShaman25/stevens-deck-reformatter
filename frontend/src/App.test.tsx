import { beforeEach, expect, test, vi } from 'vitest';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import App from './App';

const ai={configured:true,independent_providers:true,planner:{provider:'anthropic',model:'claude-test',configured:true},reviewer:{provider:'gemini',model:'gemini-test',configured:true}};

const session = {session_id:'test',name:'Fixture.pptx',slide_count:1,slides:[{index:0,title:'Opening',kind:'title',layout:'native',issues:[],rationale:'',n_body:3,n_images:0,needs_review:false}],capabilities:{gemini:false,libreoffice:false,ai},revisions:{'0':{tags:['dense'],instruction:'Saved note'}},ai_check:[0]};
const response = (data:unknown,ok=true) => Promise.resolve({ok,json:async()=>data} as Response);
beforeEach(() => {window.history.replaceState({},'', '/?session=test');vi.restoreAllMocks();});

test('completed QA with cosmetic suggestions enables download and labels them nonblocking',async()=>{
  const generation={generation_id:'g',candidate_sha256:'abc',mode:'ai',state:'ready',download_allowed:true,
    built_slides:1,checks:{ai_visual_review:{status:'passed'}},
    findings:[{id:'qa:0',check:'ai_visual_review',code:'AI_VISUAL_SPATIAL_LAYOUT',output_slide:0,
      severity:'warning',can_approve:false,message:'Optional extra caption spacing.'}],
    human_decisions:[],source_to_output_slides:{'0':[0]},corrections:[]};
  vi.stubGlobal('fetch',vi.fn(()=>response({...session,generation})));render(<App/>);
  expect(await screen.findByText('Ready with suggestions')).toBeVisible();
  expect(screen.getByText('Suggestion · does not block download')).toBeVisible();
  expect(screen.getByRole('button',{name:'Download verified PowerPoint and finish'})).toBeEnabled();
  expect(screen.queryByText(/Manual approval cannot clear this finding/)).not.toBeInTheDocument();
});

test('added closing has its own output preview without claiming it was a source page',async()=>{
  const generation={generation_id:'g',candidate_sha256:'abc',mode:'ai',state:'ready',download_allowed:true,
    built_slides:2,checks:{},findings:[],human_decisions:[],source_to_output_slides:{'0':[0]},corrections:[],
    added_slides:[{output_slide:1,kind:'closing',text:'Thank you!',authorization:'Required closing'}]};
  vi.stubGlobal('fetch',vi.fn(()=>response({...session,generation})));render(<App/>);
  expect(await screen.findByText('Added closing slide · Output slide 2')).toBeVisible();
  expect(screen.getByAltText('Thank you closing slide')).toHaveAttribute('src','/api/sessions/test/slides/1/preview?variant=after&generation_id=g');
  expect(screen.getByLabelText('Source slide').querySelectorAll('option')).toHaveLength(1);
});

test('resume restores revisions without optional mode or check controls',async()=>{
  vi.stubGlobal('fetch',vi.fn(()=>response(session)));
  render(<App/>);
  expect(await screen.findByLabelText('Reviewer note')).toHaveValue('Saved note');
  expect(screen.getByRole('button',{name:'Too dense'})).toHaveAttribute('aria-pressed','true');
  expect(screen.queryByRole('checkbox')).not.toBeInTheDocument();
  expect(screen.queryByRole('combobox',{name:'Generation mode'})).not.toBeInTheDocument();
  expect(screen.getByRole('button',{name:'Previous slide'})).toBeDisabled();
  expect(screen.getByRole('button',{name:'Next slide'})).toBeDisabled();
});

test('a failed revision save is visible and stops generation',async()=>{
  const fetcher=vi.fn((url:string)=>url.endsWith('/revise') ? response({detail:'Save failed'},false) : response(session));
  vi.stubGlobal('fetch',fetcher);render(<App/>);
  fireEvent.change(await screen.findByLabelText('Reviewer note'),{target:{value:'Changed'}});
  fireEvent.click(screen.getByRole('button',{name:'Redesign + QA'}));
  expect(await screen.findByRole('alert')).toHaveTextContent('Save failed');
  expect(fetcher.mock.calls.some(([url])=>url.endsWith('/generate'))).toBe(false);
});

test('failed verification disables final download and benchmark',async()=>{
  const generation={generation_id:'g',candidate_sha256:'abc',state:'failed',built_slides:1,checks:{artifact_coverage:{status:'failed'}},findings:[{id:'f',code:'MISSING',message:'Paragraph missing',severity:'blocking',source_slide:0}],human_decisions:[],source_to_output_slides:{'0':[0]},corrections:[]};
  vi.stubGlobal('fetch',vi.fn(()=>response({...session,generation})));render(<App/>);
  expect(await screen.findByRole('button',{name:'Download verified PowerPoint and finish'})).toBeDisabled();
  expect(screen.queryByRole('button',{name:'Save approved benchmark'})).not.toBeInTheDocument();
  expect(screen.queryByRole('button',{name:'Download unverified draft'})).not.toBeInTheDocument();
  expect(screen.queryByRole('button',{name:'Download unverified PDF draft'})).not.toBeInTheDocument();
  expect(screen.getByRole('button',{name:'Download verified PDF and finish'})).toBeDisabled();
  expect(screen.getByText('Paragraph missing')).toBeVisible();
});

test('start over clears old deck state and session URL',async()=>{
  vi.stubGlobal('fetch',vi.fn(()=>response(session)));render(<App/>);
  await screen.findByLabelText('Reviewer note');
  fireEvent.click(screen.getByRole('button',{name:'Start a new deck'}));
  expect(await screen.findByText('Build a better deck')).toBeVisible();
  expect(screen.queryByText('Saved note')).not.toBeInTheDocument();
  expect(window.location.search).toBe('');
});


test('editing and saving instructions retains the candidate image but removes approval access',async()=>{
  const generation={generation_id:'g',candidate_sha256:'abc',state:'ready',built_slides:1,checks:{},findings:[],human_decisions:[],source_to_output_slides:{'0':[0]},corrections:[]};
  vi.stubGlobal('fetch',vi.fn((url:string)=>response(url.endsWith('/revise')?{ok:true}:{...session,generation})));
  render(<App/>);
  const image=await screen.findByAltText('Generated candidate');
  const url=image.getAttribute('src');
  fireEvent.change(screen.getByLabelText('Reviewer note'),{target:{value:'Make this larger'}});
  expect(screen.getByAltText('Generated candidate')).toBe(image);
  expect(image).toHaveAttribute('src',url);
  expect(screen.getByText(/Showing the previous candidate/)).toBeVisible();
  expect(screen.queryByRole('button',{name:'Download verified PowerPoint and finish'})).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button',{name:'Save revision'}));
  await screen.findByText(/Revision saved/);
  expect(screen.getByAltText('Generated candidate')).toHaveAttribute('src',url);
});

test('configured AI mode sends explicit mode and requires full review',async()=>{
  const generation={generation_id:'g',candidate_sha256:'abc',mode:'ai',state:'error',built_slides:1,checks:{ai_visual_review:{status:'error'}},findings:[{id:'ai',severity:'blocking',message:'Provider timed out'}],human_decisions:[],source_to_output_slides:{'0':[0]},corrections:[]};
  const fetcher=vi.fn((url:string,_options?:RequestInit)=>response(url.endsWith('/generate') ? {generation} : {...session,capabilities:{...session.capabilities,ai}}));
  vi.stubGlobal('fetch',fetcher);render(<App/>);
  await screen.findByText(/claude-test/);
  expect(screen.queryByRole('combobox',{name:'Generation mode'})).not.toBeInTheDocument();
  expect(screen.queryByRole('checkbox')).not.toBeInTheDocument();
  expect(screen.getByText(/mandatory visual review/)).toBeVisible();
  fireEvent.click(screen.getByRole('button',{name:'Redesign + QA'}));
  await screen.findByText('Provider timed out');
  fireEvent.click(screen.getByText('Deck-wide findings (1)'));
  expect(screen.getByText('Provider timed out')).toBeVisible();
  const call=fetcher.mock.calls.find(([url])=>url.endsWith('/generate'));
  expect(JSON.parse(call?.[1]?.body as string)).toEqual({mode:'ai',repair_passes:1});
  expect(screen.getByRole('button',{name:'Download verified PowerPoint and finish'})).toBeDisabled();
});

test('missing keys block AI generation and connection testing',async()=>{
  vi.stubGlobal('fetch',vi.fn(()=>response({...session,capabilities:{}})));render(<App/>);
  await screen.findByLabelText('Reviewer note');
  expect(screen.getByRole('button',{name:'Redesign + QA'})).toBeDisabled();
  expect(screen.getByRole('button',{name:'Test AI connection'})).toBeDisabled();
});

test('connection failure is shown without enabling release',async()=>{
  vi.stubGlobal('fetch',vi.fn((url:string)=>response(url.endsWith('/ai/test') ? {configuration:ai,results:{planner:{status:'authentication_error',message:'Check configured key'},reviewer:{status:'completed'}}} : {...session,capabilities:{...session.capabilities,ai}})));
  render(<App/>);await screen.findByText(/claude-test/);
  fireEvent.click(screen.getByRole('button',{name:'Test AI connection'}));
  expect(await screen.findByText(/authentication_error/)).toBeVisible();
  expect(screen.queryByRole('button',{name:'Download verified PowerPoint and finish'})).not.toBeInTheDocument();
});

test('progress polling does not request a preview before rendering finishes',async()=>{
  const generation={generation_id:'g',candidate_sha256:'abc',mode:'preserve',state:'checking',built_slides:1,progress:{stage:'rendering'},checks:{},findings:[],human_decisions:[],source_to_output_slides:{'0':[0]},corrections:[]};
  let finish!: (value:Response)=>void;
  let started=false;
  vi.stubGlobal('fetch',vi.fn((url:string)=>{
    if(url.endsWith('/generate')) {started=true;return new Promise<Response>(resolve=>{finish=resolve;});}
    return response(started ? {...session,generation} : session);
  }));
  render(<App/>);await screen.findByLabelText('Reviewer note');
  fireEvent.click(screen.getByRole('button',{name:'Redesign + QA'}));
  await screen.findByText('rendering',{}, {timeout:3500});
  expect(screen.queryByAltText('Generated candidate')).not.toBeInTheDocument();
  finish(await response({generation:{...generation,state:'ready',progress:{stage:'finished'}}}));
  expect(await screen.findByAltText('Generated candidate')).toHaveAttribute('src',expect.stringContaining('generation_id=g'));
});

test('OpenAI-only configuration identifies the local key and selected model',async()=>{
  const selected={configured:false,independent_providers:false,planner:{provider:'openai',model:'gpt-6-luna',configured:false},reviewer:{provider:'openai',model:'gpt-6-luna',configured:false}};
  vi.stubGlobal('fetch',vi.fn(()=>response({...session,capabilities:{...session.capabilities,ai:selected}})));
  render(<App/>);
  expect(await screen.findByText(/Add OPENAI_API_KEY/)).toBeVisible();
  expect(screen.getByText('Planner: gpt-6-luna · Reviewer: gpt-6-luna')).toBeVisible();
  expect(screen.getByRole('button',{name:'Redesign + QA'})).toBeDisabled();
});

const reviewGeneration = {
  generation_id:'review-g',candidate_sha256:'checked-hash',state:'needs_review',built_slides:3,
  checks:{structural_formatting:{status:'needs_review'}},human_decisions:[],corrections:[],
  source_to_output_slides:{'0':[0,1],'1':[2]},
  findings:[
    {id:'a',code:'OVERFLOW',message:'Title fit on first page',severity:'review',output_slide:0},
    {id:'b',code:'FONT',message:'Caption size on first page',severity:'review',output_slide:0},
    {id:'blocked',code:'MISSING',message:'Missing content on first page',severity:'blocking',output_slide:0},
    {id:'part2',code:'OVERFLOW',message:'Second output part only',severity:'review',output_slide:1},
    {id:'source',code:'NOTES',message:'Second source slide only',severity:'review',source_slide:1},
    {id:'global',code:'RENDER_ERROR',message:'Deck-wide renderer problem',severity:'blocking'},
  ],
};
const reviewSession={...session,slide_count:2,slides:[session.slides[0],{...session.slides[0],index:1,title:'Next source'}],generation:reviewGeneration};

test('findings follow source and output page and discard selections when navigating',async()=>{
  vi.stubGlobal('fetch',vi.fn(()=>response(reviewSession)));render(<App/>);
  const list=await screen.findByRole('list',{name:'Findings for this page'});
  expect(within(list).getByText('Title fit on first page')).toBeVisible();
  expect(within(list).queryByText('Second output part only')).not.toBeInTheDocument();
  expect(within(list).queryByText('Deck-wide renderer problem')).not.toBeInTheDocument();
  fireEvent.click(screen.getByLabelText('Select all review findings on this page'));
  fireEvent.change(screen.getByLabelText('Review rationale'),{target:{value:'First page inspected'}});
  expect(screen.getByRole('button',{name:'Approve selected (2)'})).toBeEnabled();
  fireEvent.change(screen.getByLabelText('Output part'),{target:{value:'1'}});
  expect(screen.getByText('Second output part only')).toBeVisible();
  expect(screen.queryByText('Title fit on first page')).not.toBeInTheDocument();
  expect(screen.getByRole('button',{name:'Approve selected (0)'})).toBeDisabled();
  expect(screen.getByLabelText('Review rationale')).toHaveValue('');
  fireEvent.change(screen.getByLabelText('Source slide'),{target:{value:'1'}});
  expect(screen.getByText('Second source slide only')).toBeVisible();
  expect(screen.queryByText('Second output part only')).not.toBeInTheDocument();
});

test('bulk approval sends only selected reviewable findings for the current page',async()=>{
  const fetcher=vi.fn((url:string,_options?:RequestInit)=>response(url.endsWith('/decisions') ?
    {generation:{...reviewGeneration,human_decisions:[{finding_ids:['a','b'],rationale:'Inspected both'}]}} : reviewSession));
  vi.stubGlobal('fetch',fetcher);render(<App/>);
  fireEvent.click(await screen.findByLabelText('Select all review findings on this page'));
  expect(screen.getByLabelText('Select finding: Missing content on first page')).toBeDisabled();
  expect(screen.getByLabelText('Select finding: Missing content on first page')).not.toBeChecked();
  fireEvent.change(screen.getByLabelText('Review rationale'),{target:{value:'Inspected both'}});
  fireEvent.click(screen.getByRole('button',{name:'Approve selected (2)'}));
  await waitFor(()=>expect(screen.getAllByText('Approved')).toHaveLength(2));
  const call=fetcher.mock.calls.find(([url])=>url.endsWith('/decisions'));
  expect(JSON.parse(call?.[1]?.body as string)).toEqual({generation_id:'review-g',candidate_sha256:'checked-hash',finding_ids:['a','b'],rationale:'Inspected both'});
  expect(screen.getByLabelText('Approved finding: Title fit on first page')).toBeDisabled();
  expect(screen.getByRole('button',{name:'Download verified PowerPoint and finish'})).toBeDisabled();
});

test('failed bulk approval keeps the selection and rationale for retry',async()=>{
  vi.stubGlobal('fetch',vi.fn((url:string)=>url.endsWith('/decisions') ? response({detail:'Review could not be saved'},false) : response(reviewSession)));
  render(<App/>);
  fireEvent.click(await screen.findByLabelText('Select finding: Title fit on first page'));
  expect(screen.getByLabelText('Select all review findings on this page')).toBePartiallyChecked();
  fireEvent.change(screen.getByLabelText('Review rationale'),{target:{value:'Inspected the title'}});
  fireEvent.click(screen.getByRole('button',{name:'Approve selected (1)'}));
  expect(await screen.findByRole('alert')).toHaveTextContent('Review could not be saved');
  expect(screen.getByLabelText('Select finding: Title fit on first page')).toBeChecked();
  expect(screen.getByLabelText('Review rationale')).toHaveValue('Inspected the title');
});

test('new generation clears selections even when finding IDs are reused',async()=>{
  vi.stubGlobal('fetch',vi.fn((url:string)=>response(url.endsWith('/generate') ? {generation:{...reviewGeneration,generation_id:'new-g',candidate_sha256:'new-hash'}} : reviewSession)));
  render(<App/>);
  fireEvent.click(await screen.findByLabelText('Select all review findings on this page'));
  fireEvent.change(screen.getByLabelText('Review rationale'),{target:{value:'Old candidate inspected'}});
  fireEvent.click(screen.getByRole('button',{name:'Redesign + QA'}));
  await waitFor(()=>expect(screen.getByRole('button',{name:'Approve selected (0)'})).toBeDisabled());
  expect(screen.getByLabelText('Review rationale')).toHaveValue('');
});

test('a clean page shows an empty state while other slides still have findings',async()=>{
  const generation={...reviewGeneration,findings:reviewGeneration.findings.filter(f=>f.id==='source')};
  vi.stubGlobal('fetch',vi.fn(()=>response({...reviewSession,generation})));render(<App/>);
  expect(await screen.findByText('No findings for this page.')).toBeVisible();
  expect(screen.queryByText('Second source slide only')).not.toBeInTheDocument();
  expect(screen.queryByRole('button',{name:/Approve selected/})).not.toBeInTheDocument();
  expect(screen.getByRole('button',{name:'Download verified PowerPoint and finish'})).toBeDisabled();
});

test('previous and next navigate source slides, reset split parts, and keep saved notes',async()=>{
  vi.stubGlobal('fetch',vi.fn(()=>response(reviewSession)));render(<App/>);
  await screen.findByLabelText('Source slide');
  expect(screen.getByRole('button',{name:'Previous slide'})).toBeDisabled();
  expect(screen.getByText('Slide 1 of 2')).toBeVisible();
  fireEvent.change(screen.getByLabelText('Output part'),{target:{value:'1'}});
  fireEvent.click(screen.getByRole('button',{name:'Next slide'}));
  expect(screen.getByLabelText('Source slide')).toHaveValue('1');
  expect(screen.getByText('Slide 2 of 2')).toBeVisible();
  expect(screen.getByText('Second source slide only')).toBeVisible();
  expect(screen.getByAltText('Generated candidate')).toHaveAttribute('src',expect.stringContaining('/slides/2/preview'));
  expect(screen.getByRole('button',{name:'Next slide'})).toBeDisabled();
  fireEvent.click(screen.getByRole('button',{name:'Previous slide'}));
  expect(screen.getByLabelText('Source slide')).toHaveValue('0');
  expect(screen.getByLabelText('Output part')).toHaveValue('0');
  expect(screen.getByLabelText('Reviewer note')).toHaveValue('Saved note');
  expect(screen.getByText('Title fit on first page')).toBeVisible();
});

test('slide navigation is disabled during generation and preserves unsaved notes',async()=>{
  let finish!: (value:Response)=>void;
  vi.stubGlobal('fetch',vi.fn((url:string)=>url.endsWith('/generate') ? new Promise<Response>(resolve=>{finish=resolve;}) : response(reviewSession)));
  render(<App/>);await screen.findByLabelText('Reviewer note');
  fireEvent.change(screen.getByLabelText('Reviewer note'),{target:{value:'Keep this unsaved note'}});
  fireEvent.click(screen.getByRole('button',{name:'Next slide'}));
  fireEvent.click(screen.getByRole('button',{name:'Previous slide'}));
  expect(screen.getByLabelText('Reviewer note')).toHaveValue('Keep this unsaved note');
  fireEvent.click(screen.getByRole('button',{name:'Redesign + QA'}));
  await waitFor(()=>expect(finish).toBeDefined());
  expect(screen.getByRole('button',{name:'Next slide'})).toBeDisabled();
  expect(screen.getByRole('button',{name:'Previous slide'})).toBeDisabled();
  finish(await response({generation:reviewGeneration}));
  await waitFor(()=>expect(screen.getByRole('button',{name:'Next slide'})).toBeEnabled());
});


test('mandatory QA findings cannot be manually approved',async()=>{
  const generation={...reviewGeneration, findings:reviewGeneration.findings.map(f=>({...f,can_approve:false}))};
  vi.stubGlobal('fetch',vi.fn(()=>response({...reviewSession,generation})));render(<App/>);
  expect(await screen.findByLabelText('Select finding: Title fit on first page')).toBeDisabled();
  expect(screen.queryByRole('button',{name:/Approve selected/})).not.toBeInTheDocument();
  expect(screen.getAllByText('QA must pass after repair. Manual approval cannot clear this finding.').length).toBeGreaterThan(0);
});


test('preparation errors explain why QA has not started',async()=>{
  const generation={...reviewGeneration,findings:[],ai_pipeline:{status:'error',changed_objects:0,configuration:ai,
    calls:[{role:'source_decision',status:'completed'}],attempts:[],
    failure_message:'Source/template preparation failed: source canvas mismatch.'}};
  vi.stubGlobal('fetch',vi.fn(()=>response({...reviewSession,generation})));render(<App/>);
  expect(await screen.findByText('Source/template preparation failed: source canvas mismatch.')).toBeVisible();
});
