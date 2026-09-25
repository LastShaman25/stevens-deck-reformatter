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
  expect(result.checks.output_qa_coverage.status).toBe('not_run');
  await expect(page.getByRole('button',{name:'Download verified PowerPoint and finish'})).toBeDisabled();
  const sid=new URL(page.url()).searchParams.get('session');
  expect((await page.request.get(`/api/sessions/${sid}/download?generation_id=${result.generation_id}`)).status()).toBe(409);
  await expect(page.getByRole('button',{name:'Download verified PDF and finish'})).toBeDisabled();
  await expect(page.getByRole('button',{name:'Download unverified draft'})).toHaveCount(0);
  for (const format of ['pptx','pdf']) {
    expect((await page.request.get(`/api/sessions/${sid}/download?generation_id=${result.generation_id}&draft=true&format=${format}`)).status()).toBe(409);
  }
  await page.getByRole('button',{name:'Next slide',exact:true}).click();
  await expect(page.getByLabel('Source slide',{exact:true})).toHaveValue('1');
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
  await page.getByRole('button',{name:'Split slide',exact:true}).click();
  await page.getByRole('button',{name:'Save revision'}).click();
  await expect(page.getByRole('status').filter({hasText:'Revision saved'})).toBeVisible();
  const generation=await generateOffline(page);
  expect(generation.source_to_output_slides['0']).toHaveLength(2);
  await expect(page.getByLabel('Output part',{exact:true})).toBeVisible();
  await page.getByLabel('Output part',{exact:true}).selectOption(String(generation.source_to_output_slides['0'][1]));
  const image=page.getByAltText('Generated candidate');
  await expect(image).toHaveAttribute('src',new RegExp(`generation_id=${generation.generation_id}`));
  await expect.poll(()=>image.evaluate((el:HTMLImageElement)=>el.complete && el.naturalWidth>0)).toBe(true);
  await page.reload();
  await expect(page.getByLabel('Output part',{exact:true})).toBeVisible();
  await page.getByLabel('Reviewer note',{exact:true}).fill('New version');
  await page.getByRole('button',{name:'Save revision'}).click();
  await expect(page.getByRole('status').filter({hasText:'Revision saved'})).toBeVisible();
  const sid=new URL(page.url()).searchParams.get('session');
  const stale=await page.request.get(`/api/sessions/${sid}/download?generation_id=${generation.generation_id}`);
  expect(stale.status()).toBe(409);
});
