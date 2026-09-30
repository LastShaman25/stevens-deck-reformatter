import { test, expect } from '@playwright/test';
import path from 'node:path';
const fixture=path.resolve('../.local/verification/browser/source.pptx');

test.beforeEach(async({page})=>{
  await page.goto('/');
  await page.getByLabel('Invitation code').fill('admin');
  await page.getByRole('button',{name:'Sign in',exact:true}).click();
  await page.getByRole('button',{name:/Use my PowerPoint/}).click();
});

test.afterEach(async({page})=>{
  const status=await page.request.get('/api/auth/status');
  const auth=await status.json();
  if(auth.user)await page.request.post('/api/auth/logout',{headers:{'X-CSRF-Token':auth.csrf},data:{}});
});

async function generateOffline(page: import('@playwright/test').Page) {
  const auth=await (await page.request.get('/api/auth/status')).json();
  const sid=new URL(page.url()).searchParams.get('session');
  const response=await page.request.post(`/api/sessions/${sid}/generate`,{
    headers:{'X-CSRF-Token':auth.csrf},data:{mode:'ai',repair_passes:0}});
  expect(response.ok()).toBeTruthy();
  const generation=(await response.json()).generation;
  await page.reload();
  return generation;
}

test('offline QA blocks all downloads and deletes on finish',async({page})=>{
  await page.locator('input[type=file]').setInputFiles(fixture);
  await expect(page.getByRole('button',{name:'Redesign + QA'})).toBeVisible({timeout:90000});
  const result=await generateOffline(page);
  expect(['not_run','error']).toContain(result.checks.output_qa_coverage.status);
  expect(result.qa_execution.complete).toBe(false);
  expect(result.download_allowed).toBe(false);
  await expect(page.getByRole('button',{name:'Download'})).toBeDisabled();
  const sid=new URL(page.url()).searchParams.get('session');
  expect((await page.request.get(`/api/sessions/${sid}/download?generation_id=${result.generation_id}`)).status()).toBe(409);
  await expect(page.getByRole('button',{name:'Download unverified draft'})).toHaveCount(0);
  for (const format of ['pptx','pdf']) {
    expect((await page.request.get(`/api/sessions/${sid}/download?generation_id=${result.generation_id}&draft=true&format=${format}`)).status()).toBe(409);
  }
  await page.getByRole('button',{name:'Next slide',exact:true}).click();
  await expect(page.getByLabel('Review slide',{exact:true})).toHaveValue('1');
  await page.getByRole('button',{name:'Finish and delete'}).click();
  await expect(page.getByRole('button',{name:/Generate a new presentation/})).toBeVisible();
  expect((await page.request.get(`/api/sessions/${sid}`)).status()).toBe(404);
});

test('revision save error stays visible and blocks generation',async({page})=>{
  await page.locator('input[type=file]').setInputFiles(fixture);
  await expect(page.getByRole('button',{name:'Redesign + QA'})).toBeVisible({timeout:90000});
  let generated=false;page.on('request',r=>{if(r.url().endsWith('/generate'))generated=true;});
  await page.route('**/slides/0/revise',route=>route.fulfill({status:500,contentType:'application/json',body:JSON.stringify({detail:'Injected save failure'})}));
  await page.getByLabel('Reviewer note',{exact:true}).fill('Cannot lose this revision');
  await page.getByRole('button',{name:'Save revision'}).click();
  await expect(page.getByRole('alert')).toContainText('Injected save failure');
  expect(generated).toBe(false);
});

test('split mapping survives resume and old previews cannot authorize a new revision',async({page})=>{
  await page.locator('input[type=file]').setInputFiles(fixture);
  await expect(page.getByRole('button',{name:'Redesign + QA'})).toBeVisible({timeout:90000});
  const auth=await (await page.request.get('/api/auth/status')).json();
  const sidBefore=new URL(page.url()).searchParams.get('session');
  // Seed a saved legacy split revision; the UI now uses one free-text prompt.
  await page.request.post(`/api/sessions/${sidBefore}/slides/0/revise`,{headers:{'X-CSRF-Token':auth.csrf},data:{tags:['split'],instruction:'Split this slide',reset_emphasis:false}});
  await page.reload();
  await page.getByRole('button',{name:'Save revision'}).click();
  await expect(page.getByRole('status').filter({hasText:'Revision saved'})).toBeVisible();
  const generation=await generateOffline(page);
  expect(generation.source_to_output_slides['0']).toHaveLength(2);
  await expect(page.getByLabel('Review slide',{exact:true})).toBeVisible();
  await page.getByLabel('Review slide',{exact:true}).selectOption(String(generation.source_to_output_slides['0'][1]));
  const image=page.getByAltText('Generated candidate');
  await expect(image).toHaveAttribute('src',new RegExp(`generation_id=${generation.generation_id}`));
  await expect.poll(()=>image.evaluate((el:HTMLImageElement)=>el.complete && el.naturalWidth>0)).toBe(true);
  await page.reload();
  await expect(page.getByLabel('Review slide',{exact:true})).toBeVisible();
  await page.getByLabel('Reviewer note',{exact:true}).fill('New version');
  await page.getByRole('button',{name:'Save revision'}).click();
  await expect(page.getByRole('status').filter({hasText:'Revision saved'})).toBeVisible();
  const sid=new URL(page.url()).searchParams.get('session');
  const stale=await page.request.get(`/api/sessions/${sid}/download?generation_id=${generation.generation_id}`);
  expect(stale.status()).toBe(409);
});


test('finding links, human dismissal and download format chooser',async({page})=>{
  let generation:any={generation_id:'ui-g',candidate_sha256:'ui-hash',mode:'ai',state:'needs_review',built_slides:2,
    download_allowed:false,pdf_available:true,checks:{output_qa_visual:{status:'needs_review'}},
    findings:[{id:'visual:0',code:'LAYOUT',check:'output_qa_visual',severity:'review',can_approve:true,output_slide:1,message:'Inspect the closing spacing'}, {id:'visual:1',code:'POLISH',check:'output_qa_visual',severity:'warning',priority:'low',can_approve:true,output_slide:1,message:'Optional fine spacing'}],
    human_decisions:[],corrections:[],source_to_output_slides:{'0':[0]},added_slides:[{output_slide:1,kind:'closing',text:'Thank you!'}]};
  await page.route('**/api/sessions/ui-review',route=>route.fulfill({json:{session_id:'ui-review',name:'Synthetic UI review',slide_count:1,
    slides:[{index:0,title:'Opening'}],revisions:{},capabilities:{},generation}}));
  await page.route('**/api/sessions/ui-review/decisions',async route=>{
    const decision=route.request().postDataJSON();
    expect(decision).toMatchObject({generation_id:'ui-g',candidate_sha256:'ui-hash',finding_ids:[],output_slide:1,rationale:'Inspected and accepted spacing'});
    generation={...generation,state:'ready',download_allowed:true,human_decisions:[{...decision,finding_ids:['visual:0','visual:1']}]};
    await route.fulfill({json:{generation}});
  });
  await page.goto('/?session=ui-review');
  await page.getByRole('button',{name:'Show all slide findings (2)'}).click();
  await page.getByRole('button',{name:'Inspect the closing spacing',exact:true}).click();
  await expect(page.getByLabel('Review slide')).toHaveValue('1');
  await expect(page.getByText('No original slide — this page was added during redesign.')).toBeVisible();
  await expect(page.getByText('Optional fine spacing',{exact:true})).toHaveCount(0);
  await page.getByRole('button',{name:'Dismiss all findings for slide 2'}).click();
  await expect(page.getByText(/Accept all 2 remaining findings/)).toBeVisible();
  await page.getByLabel('Reason for accepting this slide').fill('Inspected and accepted spacing');
  await page.getByRole('button',{name:'Accept and dismiss slide findings'}).click();
  await page.getByRole('button',{name:'Download',exact:true}).click();
  await expect(page.getByRole('dialog',{name:'Choose download format'})).toBeVisible();
  await page.getByLabel('PDF (.pdf)',{exact:true}).check();
  await expect(page.getByLabel('PDF (.pdf)',{exact:true})).toBeChecked();
  await page.screenshot({path:'test-results/review-download.png',fullPage:true});
  await page.getByRole('button',{name:'Cancel',exact:true}).click();
  await expect(page.getByRole('dialog')).not.toBeVisible();
  await page.route('**/api/sessions/ui-review/download?*',async route=>{
    expect(new URL(route.request().url()).searchParams.get('format')).toBe('pdf');
    await route.fulfill({contentType:'application/pdf',body:'%PDF-synthetic-test'});
  });
  await page.route('**/api/sessions/ui-review/finalize',route=>route.fulfill({json:{deleted:true}}));
  await page.getByRole('button',{name:'Download',exact:true}).click();
  const downloading=page.waitForEvent('download');
  await page.getByRole('button',{name:'Download and finish'}).click();
  expect((await downloading).suggestedFilename()).toBe('Stevens-verified.pdf');
});
