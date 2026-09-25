# Implementation and verification — September 24, 2026

## Implemented behavior

- Invitation-code sign-in, initial `admin` administrator, account-bound generated codes, role management, deactivation/reactivation, code rotation, inactive-account removal, last-admin protection, revocable cookie sessions, CSRF checks, and ownership enforcement on both old and new API routes. Google OIDC adapter remains available for later setup; the active mode needs no Google keys.
- Two separate post-login entries: **Use my PowerPoint** preserves the existing workflow; **Generate a new presentation** provides topic/outline/PDF authoring.
- Auto/Brief/Standard/Detailed length preferences, model-selected count, editable/reorderable outline, explicit revision-bound approval, native content generation, and independent artifact verification.
- Native editable text, charts, tables and notes; deterministic function/scientific plots and LaTeX-style equations; content/chart/formula editing with fresh candidates and checks. Plot input is parsed using a restricted grammar, not executed as model-written code.
- Text and scanned PDF processing, source-page previews, exact quotation/page validation, extraction-uncertainty acknowledgment, and source evidence supplied to QA.
- Independent output-QA role, ordered per-slide screenshots, contiguous overlapping batches, full-deck screenshot synthesis, coverage checks, sequence/accuracy findings, and candidate-bound release decisions. New authoring includes one bounded visual repair pass followed by a fresh full render/QA run.
- Owner-only temporary workspaces, immediate access revocation on closing, file leases, bounded expiry, download acknowledgment/finalization, retryable locked-file deletion, restart/orphan recovery, and no product benchmark capture. Renderer temporary paths are scoped beneath processing directories.

## Verification method

Run from the repository root:

```powershell
powershell -NoProfile -File tools/verify.ps1
```

This runs backend checks including actual PowerPoint/LibreOffice rendering, frontend tests, TypeScript/build, and Chrome browser workflows on an isolated offline server. Each run creates a fresh ignored `.local/verification/run-*` evidence folder. Renderer and browser installation are prerequisites. The script fails on a nonzero step; model quality is tested separately with the explicit live commands below.

```powershell
.venv/Scripts/python.exe tools/verify_authoring.py --live --output .local/verification/new-authoring-run
.venv/Scripts/python.exe tools/verify_authoring.py --live --cases scanned --output .local/verification/new-scanned-run
.venv/Scripts/python.exe tools/verify_output_qa.py --live --output .local/verification/new-qa-challenge
```

These submit only synthetic content, use the configured key/model, render real PPTX files, and verify deletion of the application workspace. Requested development evidence is retained separately. They do not auto-approve review findings. An authoring exit code of zero permits `needs_review`: it means mandatory checks completed without blocking defects, not that a verified download was released without review.

## Results recorded during implementation

| Checkpoint | Result / evidence |
|---|---|
| Backend contracts/regressions | **125 checks passed across the final runs**: the combined runner passed 122, followed by passing read-only-cleanup, administrator-self-rotation, and concurrent-lease regressions. The final implementation module passed 30 offline checks plus its real-renderer check. Evidence under `.local/verification/run-*/backend.xml` and `.local/verification/backend-implementation.xml` |
| Actual PowerPoint rendering | **3 passed**: existing preservation, existing AI native edits, and new chart/plot/equation composition; `.local/verification/renderer-implementation.xml` |
| Frontend components | **20 passed**: existing review plus sign-in, separate entries, code administration, CSRF header propagation and outline approval invalidation |
| TypeScript / production build | Passed |
| Chrome browser workflows | **3 passed**: authenticated upload, offline QA blocking verified release, exact draft bytes, deletion, revision error handling, split navigation and stale-download rejection |
| Live topic authoring | Four automatically planned slides; artifact/render/ordered QA passed; illustrative data and chart styling remained explicit review findings. `.local/verification/authoring-live-3/summary.json` |
| Live PDF authoring | Three slides; source grounding, artifact/render, ordered coverage, sequence, accuracy, and visual QA passed. Native chart-style inspection remained reviewable. `.local/verification/authoring-live-4/summary.json` |
| Live scanned-PDF authoring | Three slides after vision transcription; the same mandatory checks passed, with native chart-style inspection left for review. Same summary file |
| Live adversarial QA challenge | Detected a deliberately wrong result (`84` versus source `42`) and a conclusion preceding method/evidence; both became blocking findings. `.local/verification/qa-live-challenge-1/result.json` |
| Live existing-PPTX redesign | **Ready**: all ten mandatory checks passed, including the added ordered coverage, sequence, accuracy and visual QA. `.local/verification/redesign-ordered-live-2/result.json` |
| Credential hygiene | `backend/.env`, SQLite files and private evidence are ignored. Exact configured credential values were absent from publishable source files |

The live run initially caught a real chart legend/axis collision. The composer was corrected and the subsequent real render and QA run passed. A rejected multi-visual model response also led to schema-error feedback on retries. No mandatory checks were weakened to obtain a pass.

The original redesign live regression initially produced two reviewable false-positive omissions despite correct rendered/extracted title and notes. The prompt was clarified to distinguish speaker notes from slide content and to cross-check extracted text before asserting omissions. The subsequent live run passed all ten gates and reached `ready`. Model judgments still require review when uncertain; one agent result cannot establish perfect factual accuracy.

## What the automated contracts check

- Anonymous/member/admin boundaries, exact-ID cross-user access, forged CSRF/origin requests, session revocation, code rotation, last-admin protection, removal and cleanup.
- Explicit cancel, active read/write leases, failed deletion/retry, absolute expiry, polling not extending lifetime, restart orphans, and stale content becoming inaccessible.
- Read-only Windows/OneDrive artifacts are retried with path-contained permission changes; administrator self-rotation renews its own session so the new code remains visible while earlier sessions are revoked.
- Automatic outline counts and revision conflicts, approved outline identity, exact exported text/notes/chart/table/image content, source citation mismatch, and final screenshot identity.
- Unsafe function expressions, numerical reference values, invalid domains, deterministic graphics, and real rendered chart/plot/equation presence.
- Twelve-slide order including slide 10 versus slide 2, missing/swapped/stale screenshots, hidden slides, failed/partial QA responses and unknown slide IDs. Recorded image requests must cover all final slides in order.
- Bounded visual repair produces a new candidate, rerenders, and reviews the entire final slide set; earlier approvals cannot release a changed file.

Older preservation tests isolate their new authentication/QA boundary with explicit mocks so they continue testing the original engine. New implementation tests exercise real invitation authentication and the actual QA coverage orchestration; only model responses or rendering are mocked where noted. Separate real-renderer and live-model evidence closes those distinct checks.

## Limits and deferred work

- Google SSO credentials/tenant acceptance and generated-picture APIs are deferred. Invitation codes are reusable account credentials until rotated or revoked.
- This is a local single-worker application with SQLite account metadata and process-local job state. It is not a deployed multi-worker service. Vercel/Gateway work remains deferred.
- New decks have a 30-slide resource ceiling; source PPTX/output QA are bounded at 100 slides. PDFs are limited to 50 MB/100 pages and bounded extracted text. Excess material is rejected, never silently truncated.
- PDF figure placement currently uses source-page images. Specialized figure-only crops, native Office-equation editing, and additional layout families can be extended later. Plots/equations retain source specifications in notes but are raster graphics.
- The supported equation syntax is Matplotlib mathtext, not arbitrary TeX or a symbolic algebra system. Complex or unsupported expressions are rejected. Existing uploaded Office equation objects remain subject to preservation-mode unsupported-object checks.
- The app removes files it owns after work ends; locked files may stay pending until handles are released. OS/Office recovery caches and a powered-off machine are outside its erasure guarantee. `store=false` does not imply zero provider retention.
- Synthetic fixtures exercise functionality, not an independently proven real-world quality benchmark. The prior course-deck holdout's tuning history is unknown. A broader benchmark with known provenance remains future evaluation work.
