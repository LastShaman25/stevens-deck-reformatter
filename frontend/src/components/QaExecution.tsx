import type {Generation} from '../types';

export function QaExecution({generation}:{generation:Generation}) {
  const qa=generation.qa_execution;
  if(!qa)return null;
  return <div className="my-3 rounded border p-3 text-sm" aria-label="QA agent activity">
    {qa.redesign_review_status&&<p>Redesign visual QA: {qa.redesign_review_status.replace(/_/g,' ')} · {qa.redesign_reviewed_slides||0} of {qa.total_slides} slides reviewed against source/template</p>}
    <b>{qa.complete?'QA agent completed its review':qa.requests?'QA agent review incomplete':'QA agent has not completed a request'}</b>
    <p>{qa.reviewed_slides} of {qa.total_slides} slides reviewed · {qa.requests} requests</p>
    <p>{qa.complete?'See the check results below. Completion does not mean every check passed.':'Downloads remain blocked until all required checks pass.'}</p>
    {qa.error&&<p className="mt-2 text-stevens-red">{qa.error}</p>}
    {qa.error?.includes('402') && <p className="mt-2"><a className="text-stevens-blue underline" href="https://vercel.com/d?to=%2F%5Bteam%5D%2F%7E%2Fai-gateway%2Fbudgets%3Fdimension%3Dapi-key" target="_blank" rel="noreferrer">Open Vercel API-key budgets</a>. After the budget is updated, run redesign and QA again.</p>}
  </div>;
}
