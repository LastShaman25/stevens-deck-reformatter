import { test, expect } from '@playwright/test';
import path from 'node:path';
const fixture=path.resolve('../.local/verification/browser/source.pptx');

test('upload, verify, download exact candidate, resume, and reset',async({page})=>{
  await page.goto('/');
  await page.locator('input[type=file]').setInputFiles(fixture);
  await expect(page.getByRole('button',{name:'Generate and verify'})).toBeVisible({timeout:90000});
  await page.getByLabel('Generation mode',{exact:true}).selectOption('preserve');
  await page.getByLabel('Reviewer note',{exact:true}).fill('Keep original speaker notes separate.');
  await page.getByRole('button',{name:'Save revision'}).click();
  await expect(page.getByRole('status').filter({hasText:'Revision saved'})).toBeVisible();
  const generated=page.waitForResponse(r=>r.url().endsWith('/generate') && r.request().method()==='POST');
  await page.getByRole('button',{name:'Generate and verify'}).click();
  const result=await (await generated).json();
  expect(['ready','needs_review']).toContain(result.generation.state);
  expect(result.generation.findings.every((f:any)=>f.severity==='review')).toBe(true);
  await expect(page.getByRole('button',{name:'Previous slide',exact:true})).toBeDisabled();
  await page.getByRole('button',{name:'Next slide',exact:true}).click();
  await expect(page.getByLabel('Source slide',{exact:true})).toHaveValue('1');
  await expect(page.getByAltText('Original source')).toHaveAttribute('src',/slides\/1\/preview/);
  await page.getByRole('button',{name:'Previous slide',exact:true}).click();
  await expect(page.getByLabel('Source slide',{exact:true})).toHaveValue('0');
  for (const [source,outputs] of Object.entries(result.generation.source_to_output_slides)) {
    await page.getByLabel('Source slide',{exact:true}).selectOption(source);
    for (const output of outputs as number[]) {
      if ((outputs as number[]).length>1) await page.getByLabel('Output part',{exact:true}).selectOption(String(output));
      const findings=result.generation.findings.filter((f:any)=>f.output_slide===output);
      if (!findings.length) continue;
      for (const finding of findings) expect(['OVERFLOW','UNRESOLVED_STYLE']).toContain(finding.code);
      await page.getByLabel('Select all review findings on this page',{exact:true}).check();
      await page.getByLabel('Review rationale',{exact:true}).fill('Inspected the synthetic render for this page: all source content is visible.');
      const decision=page.waitForResponse(r=>r.url().endsWith('/decisions'));
      await page.getByRole('button',{name:`Approve selected (${findings.length})`,exact:true}).click();
      expect((await decision).ok()).toBe(true);
      await expect(page.getByRole('list',{name:'Findings for this page'}).getByText('Approved',{exact:true})).toHaveCount(findings.length);
    }
  }
  await expect(page.getByRole('button',{name:'Download verified PowerPoint'})).toBeEnabled();
  const download=page.waitForEvent('download');
  await page.getByRole('button',{name:'Download verified PowerPoint'}).click();
  const file=await download;
  expect(file.suggestedFilename()).toBe('Stevens-verified.pptx');
  const fs=await import('node:fs');const crypto=await import('node:crypto');
  expect(crypto.createHash('sha256').update(fs.readFileSync((await file.path())!)).digest('hex')).toBe(result.generation.candidate_sha256);
  await page.reload();
  await expect(page.getByLabel('Reviewer note',{exact:true})).toHaveValue('Keep original speaker notes separate.');
  await expect(page.getByRole('button',{name:'Download verified PowerPoint'})).toBeEnabled();
  await expect.poll(()=>page.getByAltText('Generated candidate').evaluate((el:HTMLImageElement)=>el.complete && el.naturalWidth>0)).toBe(true);
  await page.screenshot({path:'test-results/verified-workflow.png',fullPage:true});
  await page.getByRole('button',{name:'Start a new deck'}).click();
  await expect(page.getByText('Build a better deck')).toBeVisible();
  expect(new URL(page.url()).search).toBe('');
});

test('revision save error stays visible and blocks generation',async({page})=>{
  await page.goto('/');await page.locator('input[type=file]').setInputFiles(fixture);
  await expect(page.getByRole('button',{name:'Generate and verify'})).toBeVisible({timeout:90000});
  await page.getByLabel('Generation mode',{exact:true}).selectOption('preserve');
  let generated=false;page.on('request',r=>{if(r.url().endsWith('/generate'))generated=true;});
  await page.route('**/slides/0/revise',route=>route.fulfill({status:500,contentType:'application/json',body:JSON.stringify({detail:'Injected save failure'})}));
  await page.getByLabel('Reviewer note',{exact:true}).fill('Cannot lose this revision');
  await page.getByRole('button',{name:'Generate and verify'}).click();
  await expect(page.getByRole('alert')).toContainText('Injected save failure');
  expect(generated).toBe(false);
});

test('split mapping survives resume and old previews cannot authorize a new revision',async({page})=>{
  await page.goto('/');await page.locator('input[type=file]').setInputFiles(fixture);
  await expect(page.getByRole('button',{name:'Generate and verify'})).toBeVisible({timeout:90000});
  await page.getByLabel('Generation mode',{exact:true}).selectOption('preserve');
  await page.getByRole('button',{name:'Split slide',exact:true}).click();
  const pending=page.waitForResponse(r=>r.url().endsWith('/generate'));
  await page.getByRole('button',{name:'Generate and verify'}).click();
  const generation=(await (await pending).json()).generation;
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
