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


## Template regions and final-QA feedback — September 25, 2026

Policy `template-regions-qa-feedback-7`; rubric `template-regions-feedback-3`.

Implemented native first-page extraction into `1_Title Slide`, preserving all source objects and content; ordinary text boxes are eligible titles. New-deck composition also uses this cover. Interior source objects stay inside the content box above the inherited bottom-left Stevens mark. Explicit RGB source backgrounds are retained in independently audited panels, fixing white-on-white output. The model receives the cover/interior distinction, approved template artwork and exact region coordinates.

Final ordered QA now sends rubric findings and affected output indices back to the redesigner. Only affected slides are replanned; every slide is rerendered and reviewed afterward. A default one-cycle budget (maximum two) plus the shared redesign-call limit prevents indefinite loops. A repair must improve final QA without new blocking scopes or technical regression; otherwise the previous candidate remains, with its unresolved findings. Repair attempts and outcomes are shown in the UI.

Verification performed:

- Full offline backend suite: **155 passed**, before one additional final-repair budget regression was added. Final affected-suite rerun: **41 passed**, including that budget test, ordinary-text cover extraction, independent source-background tampering detection, protected-logo intrusion rejection, targeted final-QA repair, unchanged clean slides, and rollback on unchanged/incomplete review. These totals overlap; they are not additive.
- All **3 real PowerPoint renderer tests passed** across the final runs: native preservation, native AI edits, and chart/plot/math composition. The old mock's arbitrary cover shift was updated to obey the explicit cover bounds.
- Frontend: **21 tests passed**; TypeScript and production build passed.
- The first three slides of the user's existing source were rebuilt and rendered **locally only**. Native content coverage and content-region checks passed; the formerly invisible introduction text became visible, and the original footer is separated from the template wordmark. This was a local diagnostic, not approval of the complete course deck.
- Live GPT-6 Luna synthetic acceptance: **ready**, all ten release checks passed, no human override. Evidence: `.local/verification/template-feedback-live-2/result.json`.
- The preceding live run exposed false positives applying interior logo rules to the cover and treating its approved campus photo as invented content. The shared rubric and contract were clarified, then the subsequent live run passed. No verifier was disabled. Targeted feedback/rollback behavior is tested with controlled faults; the successful live deck did not require final-QA repair.
- `.env` and local evidence remain ignored. The server was restarted with the user's explicit approval; the previous in-memory job must be uploaded again.

Limits: native cover extraction starts with a conservative font/reading-order hypothesis, which the required AI role pass rechecks. Ambiguous source graphics are preserved, not silently removed as decoration. This is not a claim that every source deck or every semantic role is automatically correct; unresolved QA findings still prevent verified release.


## Source decisions and paired QA — September 25, 2026

Policy `source-decisions-paired-qa-8`; rubric `source-decisions-paired-4`.

The agent now classifies original elements before native composition, using original screenshots and rendered template references. It can keep a matching slide unchanged or redesign it with individually recorded non-content-artwork removals. Logos and meaningful/uncertain images remain protected. The final ordered reviewer receives explicitly labeled original/candidate image pairs for every output, including repeated source images for split pages, plus the source decisions to challenge. Missing originals block review.

QA can cause source decisions to be reconsidered. Native recomposition can restore a wrongly removed picture or change an artwork decision; only affected slides are replaced. Complete artifact/render/visual/ordered checks still run, and regressions roll back. Source-decision summaries are shown for the current slide.

Evidence and verification:

- Source-decision contracts cover protected logo/content/linked-dependent removal rejection, actual removal, retained rejected artwork, original logo image bytes, complete native preservation, and tamper detection. A controlled end-to-end defect test proved final QA can restore an incorrectly removed picture.
- Paired-QA tests verify source/output order and repeated originals for split slides; missing originals fail closed.
- Real PowerPoint testing found and fixed a native import problem: imported masters and layout identifiers must be registered with globally unique IDs. The final unchanged-slide test passed with **pixel-identical source and output PNGs**. Three existing real-render tests also passed (native preservation, AI edits, chart/plot/math composition). Evidence: `.local/verification/source-decisions-renderer-1/` and the corrected unchanged-slide test under `source-decisions-renderer-3/`.
- Full offline backend suite and final targeted tests passed; frontend **21 tests**, TypeScript and production build passed. Detailed run directories: `.local/verification/source-decisions-final/` and `.local/verification/source-decisions-feedback-3/`.
- Live synthetic GPT-6 Luna pipeline reached **ready with all ten checks passed**, without human override: `.local/verification/source-decisions-live-1/result.json`. This confirms the live source-decision/schema/pairing path, not perfect judgment on every private source deck. The newly supplied six screenshots were not sent externally during this verification.
- `.env` and private evidence remain ignored. The local server was restarted to activate the update; re-upload and regenerate for new decisions.

Unchanged import compares the complete source dependency graph, normalizing only the nonvisual source-preservation slide-name marker and globally remapped numeric layout IDs. It does not exempt altered text, images, themes, positions or relationships. Unchanged preservation currently requires equal source/template canvas sizes. Decision repairs that would change the source-to-output mapping require a fresh generation rather than silently invalidating slide identity.


## Actionable redesign rubric checkpoint (September 25, 2026)

Active rubric: `actionable-slide-decisions-5`; release policy: `actionable-slide-decisions-qa-9`.

Implemented mandatory slide-type decisions, explicit retain/remove agreement, semantic cover extraction, source font resolution, protected code/logo text, exact whitespace/typeface audits, structured correction/acceptance evidence, targeted repair handoff, and original/template/candidate review context. Native checks still protect content regions and template-logo space. Bounded schema/relationship correction never bypasses release validation.

Verification evidence:

- Full offline suite: **180 passed**, four renderer tests deselected (`.local/verification/actionable-release-final/backend.xml`).
- Final review-contract regression suite: **85 passed**, including the additional test that a contract correction retains its reported defect (`.local/verification/actionable-review-contract/backend.xml`).
- Final image-order/rubric suite: **33 passed** (`.local/verification/actionable-image-order/`).
- Real PowerPoint rendering checkpoint: **4 passed**, including pixel-identical unchanged cover, native preservation, AI geometry and charts/plots/math (`.local/verification/actionable-renderer/backend.xml`).
- Live synthetic runs used only synthetic content and the bundled template; no uploaded screenshots/course deck were sent. Runs 1-4 exposed invalid role/QA contracts, notes-evidence confusion and a reference/candidate image-order defect. The latter is corrected: the audited candidate is last in per-slide review, explicitly labeled; template example words are reference only.
- Final live run (`.local/verification/actionable-live-5/result.json`) **did not pass release**. Native content, structure, rendering, redesign and ordered coverage/sequence/accuracy checks passed. Visual QA still made incorrect positional/wrapping judgments about text within its prescribed cover boxes. The bounded repair was not promoted and the candidate remained blocked. This verifies failure handling and the handoff, not reliable live visual acceptance. No review overrides were applied and the selected model was not changed.
- The local server was restarted to activate the implementation. Credentials and verification artifacts remain ignored by Git.

Remaining limitation: raster artwork that combines an obsolete background with a required embedded logo cannot yet be safely separated by the native editor. It must remain protected and flagged, not silently discarded. Live visual model judgments also remain fallible; neither unit tests nor a schema-valid response proves that every real slide is visually correct.

## Verified embedded-logo extraction checkpoint (September 25, 2026)

Current rubric: `verified-logo-extraction-6`; release policy: `verified-logo-extraction-qa-10`. This supersedes the embedded-logo limitation above for bounded, supported raster regions.

The source stage now retains native logos first, identifies known bundled artwork to suggest logo regions, and supports an explicit `extract_logo` decision. Clean crops retain original pixels and padding. Exact approved template variants can be reused without adding a second logo, only after asset comparison and separate visual identity review. Raster boundary, resolution, proportions, meaningful-content and dependency checks run before composition. The artifact gate independently reconstructs the extraction from the reopened source and verifies the exported crop or inherited template mark. Missing, altered, hidden, cropped, distorted, duplicated or replaced logos fail. Extraction failures return specific criteria and reasons to the source agent; plain removal cannot evade a rejected extraction.

Verification:

- Full offline backend suite: **210 passed**, six renderer cases deselected (`.local/verification/logo-extraction/release-tests/backend.xml`). Final extraction/provider configuration changes: **50 passed**, two renderer cases deselected (`config-tests/backend.xml` under the same evidence root).
- Real PowerPoint: source-crop and template-reuse export paths each passed rendering and artifact checks (`renderer-tests/backend.xml`, `reuse-render/backend.xml`). The reuse render has one template mark and no old background inset; the crop fixture exercises preservation separately, not whole-slide visual approval.
- TypeScript and production frontend build passed. The slide summary includes the number of embedded logos preserved. Git continues to ignore `backend/.env` and `.local/verification/`.
- Live runs used only synthetic text and bundled template artwork, with explicit user approval for that payload. Early `none`-reasoning runs correctly remained blocked when visual review disputed the mark; they exposed insufficient crop padding, a replaceable cover-text contrast dependency and false logo-variant judgments. No review result was overridden.
- The final live check **passed** with the production split: GPT-6 Luna, planning effort `none`, reviewer effort `low`. Evidence: `.local/verification/logo-extraction/live-release/result.json` and `calls.json`. Source identification selected verified template reuse; independent extraction/identity review, native artifact audit, real PowerPoint rendering and the final paired review all passed. This is a one-slide capability checkpoint, not a new full-deck ordered-QA benchmark or a guarantee for every private deck.
- `OPENAI_REVIEW_REASONING_EFFORT` configures reviewers separately. It defaults to `low` when general effort is `none`, preserving higher global settings otherwise; the selected model does not change. Low reasoning consumes additional output tokens. [Official GPT-6 Luna settings](https://developers.openai.com/api/docs/models/gpt-6-luna).
- Repeat the opt-in live checkpoint with `python tools/verify_logo_extraction.py --live --output <new-local-evidence-directory>` after configuring the key locally. It uses synthetic content and template artwork and incurs API charges.

The local server was restarted to activate this update. Existing uploads must be uploaded again. Arbitrary photographic-background segmentation, low-resolution logo reconstruction and generative logo redrawing remain unsupported; uncertain cases retain the source image or stay blocked. App-generated inspection images live within the processing session and follow its normal cleanup lifecycle.


## Section-header branding exception (September 25, 2026)

The approved private Module 8 reference uses section dividers at slides 5, 10, 14 and 19. Generator and QA now distinguish these from regular content pages: section dividers omit the bottom-left wordmark and retain the top-right mark unchanged. Native redesign selects Section Header, hides only the content master's furniture for that layout, and extracts title/supporting text into section regions. Matching section slides can still remain unchanged.

A narrowly validated exception allows removing a standalone bottom-left Stevens source footer logo. Top-right logos, full backgrounds, linked artwork, dependencies and regular content-slide logos remain protected. Artifact coverage independently revalidates removals. Section-logo template reuse cannot fall back to the regular content footer.

Verification: regression coverage in `tests/backend/test_section_headers.py` tests native composition and reopened artifact coverage plus forbidden removal cases. Local PowerPoint renders in `.local/verification/section-render` confirm no section footer wordmark while the following regular content slide retains it. The private reference and generated evidence stay ignored; no reference content was sent to an external model. These checks verify composition/policy behavior, not a live full-deck AI quality benchmark.


## PDF redesign, timeout recovery and first-page enforcement (September 25, 2026)

- Text-based PDF import preserves native text, raster graphic regions, supported hyperlinks and original page previews. Page/text inventory is checked on reopened PPTX; imported PDF and PPTX hashes are pinned. Scans, unflattened annotations/forms and unsupported links fail explicitly.
- PDF downloads use the exact hash-bound PDF rendered for the current candidate and the same verified release gate. Tampered or stale PDF output is rejected. The later mandatory QA change below removes draft downloads.
- Source-decision inputs omit irrelevant template examples and ordinary raw photos already visible in the source screenshot. OpenAI schema is sent once through structured output. Transport failures retry once within the cumulative upload budget; completed decisions are cached in the processing workspace. Error states stop downstream output QA.
- A native photo cover test confirms the meaningful source image fills the support area without a source background panel, keeps its source bytes/aspect ratio and replaces the inherited campus photo. Top-right branding remains intact.
- Offline regression suite: 222 backend tests passed (six renderer tests excluded), followed by the photo-cover regression. Frontend: 21 tests, TypeScript and production build passed.
- Live one-page synthetic PDF checkpoint: `.local/verification/pdf-live-1/result.json`, all 11 checks passed, state `ready`, PDF available, six requests and 54,006 recorded tokens. This is a bounded live checkpoint, not a claim that a complete private course deck has passed.


## Mandatory QA download gate (September 25, 2026)

All downloadable output now requires a ready generation with every required gate complete: native checks, render checks, AI redesign and visual review (redesign workflow), ordered output coverage/sequence/accuracy/visual QA, and grounding for authored decks. The server recomputes release state before returning bytes; a stale ready flag cannot bypass failed or missing checks. PDF and PPTX, redesign and authoring, and legacy draft=true requests share this gate. Previews remain available for inspection; there are no draft-download buttons.

The reported 16-page PDF stopped at source slide 7 after a provider response could not be decoded/validated, before QA began. Stored metadata contains usage but no raw response, so the exact malformed content cannot be reconstructed. Response diagnostics now distinguish local request preparation, response JSON, response content and structured-output decoding. Malformed response JSON/content receives one bounded retry; invalid local inputs and incomplete verification remain blocked. Diagnostics do not expose provider bodies or private source text.

Regression tests exercise every required AI/QA status (not_run, checking, error, failed), both file formats and both draft flags, plus malformed-response recovery and retry exhaustion. The frontend removes bypass controls and relies on the server's explicit download_allowed flag.


Validation for the mandatory gate: full non-renderer regression run had 247 passing tests and six obsolete draft-access assertions; after updating those assertions, the complete AI pipeline test module passed (30 tests). Frontend unit tests: 21 passed, TypeScript and build passed. Chrome offline end-to-end regression passed: no draft controls, both download formats blocked through direct requests, and cleanup on finish. The live synthetic PDF checkpoint `.local/verification/mandatory-qa-live-1/result.json` completed all 11 gates and reached ready (six requests, 54,089 recorded tokens). PowerPoint rendering ran during that live checkpoint; separate renderer-marked tests require desktop permissions and are not included in the non-renderer count.


## Mandatory QA pass and repeated repair — September 25, 2026

- Policy `mandatory-qa-pass-14`, rubric `mandatory-pass-spacing-9`: per-slide visual and all ordered-deck QA checks require explicit passed status. Human decisions cannot waive them; UI marks unapproved previews and disables QA approval. The backend rejects draft and ordinary exports on an incomplete/failed/review QA result.
- Final QA repair continues while findings improve, preserving request/token/time limits. Each candidate is rendered and rechecked against originals, across all output slides. Failed, regressive, unchanged or stalled proposals retain the blocked prior candidate. A legacy zero repair setting cannot disable mandatory final repair.
- First-page layout and native title are independently checked. Composition no longer forces the body-font minimum into small source line boxes. The planner validates new text collisions and projected text fit; styled text must fit its proposed box. Math/spacing acceptance criteria are shared by generator and both QA stages.
- Full non-renderer backend run: 269 passed, 6 renderer tests deselected. Final fit-validator follow-up: 41 passed. Fingerprint/no-op follow-up: 12 passed. Frontend: 22 passed; TypeScript and production build succeeded.
- Live synthetic one-page PDF: all 11 checks passed; 6 API requests, 54,886 recorded tokens. Actual PowerPoint cover render inspected. Evidence: `.local/verification/qa-loop-live-1/` (ignored).
- First live two-page math check: all AI QA passed, but one deterministic title-box overflow warning correctly kept the output in needs_review. Its attempt to repair without improving findings was rejected. This prompted stricter validation when changing font/title role. Evidence: `.local/verification/qa-loop-math-live-1/` (ignored).
- Tests use synthetic inputs. The user's specific math deck has not been reproduced in this checkpoint; rerun it after refreshing and re-uploading.

- Final live two-page math check after the validator fix: all 11 checks passed, including structural formatting; state ready. One repair followed by a fresh render and both QA stages. 14 API requests, 150,171 recorded tokens. Evidence: `.local/verification/qa-loop-math-live-2/` (ignored). Local server restarted with user approval; health check passed.


## Cover background and QA-startup correction — September 25, 2026

The reported 16-page PDF imported to width 12,191,999 EMU; the native template is 12,192,000 EMU. A later keep_original source decision aborted composition on this one-EMU difference, leaving a preliminary preview and QA not_run. Imports now use exact native canvas dimensions, negligible two-EMU differences are accepted without shape rescaling, and actual mismatches are rejected during source-decision validation so the agent can correct them before composition.

The cover also contained an imported all-white graphic and a generated contrast panel triggered by bottom notes excluded from cover extraction. Invisible graphics matching the page background are no longer imported. Cover notes and metadata flow into the right-hand text region; source background panels over the cover photo are blocked. Details start at x=7.75 to clear the sloping photo edge. All 16 pages passed local artifact coverage on reimport; the actual first-page PowerPoint render was inspected locally. Private diagnostic files remain inside the original processing session and expire/delete with it.

Backend regression run: 272 passed, 6 renderer cases deselected. After metadata-flow changes: 40 targeted tests passed; final cover-region follow-up: 18 passed. Frontend tests and production build passed. Live submission of the private PDF was initially blocked by automatic approval review, then explicitly approved. That run reached visual review, but the original processing session was cleaned up before its final result could be saved; it is not counted as a confirmed live QA pass. Local rendering and original content-preservation checks completed earlier. The old UI in the screenshot was a previously loaded bundle: the running server serves the current bundle without draft buttons. HTML now uses no-store, and preparation failures are surfaced directly in the AI status panel.


Follow-up: the independent artifact gate now shares the same two-EMU tolerance; all slide objects and relationships remain compared exactly. A new regression covers both composition and artifact audit for this rounding case. Layout validation supplies the offending object/box and prior proposal on correction. If proposals still fail after source composition succeeds, per-slide and ordered diagnostic QA now run on the rendered candidate; ai_redesign remains error and no output is released. The corresponding regression verifies both reviews run and download remains denied. Tests use an isolated processing root to avoid interacting with live application jobs. Full backend run: 273 passed (six renderer cases excluded); follow-up QA tests: 84 passed. Real PowerPoint unchanged-slide regression: passed with desktop COM access. Frontend: 23 passed; production build successful.

Final live synthetic cover verification: `.local/verification/cover-footer-live-final-2/` passed all 11 checks, state ready, seven API requests and 72,200 recorded tokens. It includes a blank white source drawing, multiple metadata rows, a low footnote and a page number. Actual rendered cover inspected. Server restarted with explicit user approval; health and HTML no-store headers confirmed. This verifies the pipeline with synthetic content, not the cleaned-up private PDF run.


### 2026-09-25 — Independent QA execution, approval clarity, authored bookends

- Ordered QA now runs independently of preceding planner/per-slide-review errors. Candidate hashes and ordered screenshot coverage remain mandatory; any missing/failed required check still blocks review approval and all exports. Upload request/token reserves protect final QA without increasing configured caps. Admission estimates include structured input, image allowance and maximum response size; actual usage is still charged to the same upload. The estimates cannot guarantee completion under arbitrary provider limits or unusually large decks.
- QA response validation gets one correction attempt. Partial validated batches and request metadata are retained; the UI distinguishes completed review, incomplete execution and actual pass/fail results, with reviewed-slide counts and errors.
- Authoring shows numbered approval/generation steps and an explicit explanation of the disabled button. Edits invalidate approval. Dedicated opening/closing slides appear before approval, count toward adaptive length, and cannot be removed or reordered past the content. Native composition uses the opening and Thank You layouts and removes inherited closing sample text from the output package while preserving artwork. Reopened-artifact checks verify the chosen layout.
- Verification: 278 backend tests passed (six renderer-marked tests excluded); 24 frontend tests passed; TypeScript and production build passed. New tests cover reserved budgets, QA after an upstream error, invalid coverage correction/partial audit retention, protected bookends, native layout audit and edit/reapproval UI behavior.
- Live six-slide synthetic PDF authoring ran QA and correctly blocked its candidate for inherited closing text collision and an interval/title inconsistency. The closing collision was fixed in the composer. That six-slide candidate was not certified.
- Corrected three-slide synthetic acceptance: all nine checks passed, ready, downloads allowed; two live QA requests, 26,489 recorded tokens, all three screenshots reviewed followed by full-deck synthesis. Opening/closing renders visually inspected. Evidence: `.local/verification/qa-bookends-corrected-live/`. Synthetic processing workspace deletion confirmed. No private user document was sent in these checks. `tools/verify_bookends_qa.py` reproduces this bounded check, and both live authoring scripts now require true download eligibility for a successful exit.


### 2026-09-25 — Correct visual template roles and redesign-specific QA

The earlier opening/closing mapping was wrong: the mostly red opening artwork is `Title Slide`; the statue-photo closing artwork is `1_Title Slide`. `Thank You Slide` uses a different balloon image. User screenshots establish the visual mapping. Native builders, source decisions, layout contracts, logo reuse, generator instructions and QA rubric now enforce the corrected roles, and rubric/policy versions invalidate previous decisions. Source closing slides classified for redesign use the statue layout and native extracted text. The generated-deck composer uses the same mapping. Rendered red opening and statue-photo closing were inspected against the references.

Redesign paired visual review now continues to subsequent slides after an invalid/unavailable review response; the failed slide remains a blocking error. Both paired and ordered QA are independently visible in the UI. Planning reserves per-slide review allowance in addition to final ordered QA. Unlike the earlier fixed default, the redesign token budget scales with slide count, bounded at 500,000–2,000,000 tokens; explicit STEVENS_AI_MAX_TOKENS always wins. The cap is shown with upload usage. New-deck generation retains its existing default.

Live evidence uses the actual PDF-import/redesign path, NOT authoring:
- Two-page synthetic math PDF: all 11 checks passed, state ready; paired original/output visual QA and final ordered review completed; ten requests, 111,233 recorded tokens. Evidence `.local/verification/red-opening-redesign-live/`.
- Twelve-page synthetic PDF: all 12 paired reviews passed; three overlapping final-review batches and full-deck synthesis passed coverage, sequence, accuracy and visual checks. 33 requests, 416,675 tokens; default cap 960,000. The deck correctly remained blocked because a layout proposal was rejected twice (collision, then text-fit regression); its native baseline also retained structural review warnings. This is confirmed QA execution/pass, NOT successful release of that candidate. No QA result or planner error was waived. Evidence `.local/verification/redesign-12-slide-qa-live/`.
- Both synthetic processing workspaces were deleted after evidence export. No private user document was sent.

Final checks: 280 backend tests passed (six renderer-marked tests deselected), 24 frontend tests passed, TypeScript and production build passed. Server restarted after confirming no active uploaded jobs; health and current frontend bundle verified.


## Real-file redesign acceptance

Synthetic fixture results and mocked QA tests are not sufficient to certify a user deck.
Use `tools/reproduce_redesign.py --live --source <read-only-pdf> --report <new-report.json>`
against the running local server. This logs in, uploads the exact file, calls the same
redesign endpoint as the browser, observes progress, and requests both PPTX and PDF
through their real download gates. No provider or QA response is mocked. It exits
nonzero unless all mandatory QA checks pass, both paired and ordered reviews cover
every output slide, both downloads succeed with the right slide counts, the PPTX
hash matches the reviewed artifact, and the original file hash is unchanged.
Only sanitized status/hash/timing evidence is saved by this harness; source and
candidate content remain in the application's expiring processing session.

The redesigned pipeline first reviews the native composition, then sends only
observed failing slides for edits. An invalid per-slide proposal cannot discard valid
proposals for other slides. Every edited candidate is rendered and reviewed again;
failed, incomplete, or unchanged repairs cannot unlock exports. PDF import preserves
run baseline offsets and crops only uniform outside padding from graphics. Equation
run size ratios survive subsequent resizing. Heuristic visual advisories may be
closed only by complete passing paired and final QA bound to the exact candidate;
blocking checks and QA findings cannot be waived this way.

The real MIT PDF reproduction additionally found PowerPoint applying a second 2/3 size reduction to shifted PDF glyphs, a scope filter freezing a paired bullet and adjacent paragraph during repairs, and stale advisory findings re-targeting already-passing slides. Import now compensates for the renderer sizing; repairs include related styles and displaced geometry; only live QA defects or technical blockers select subsequent repair targets. Actual rejected model proposals were replayed, validated, and rendered to verify these fixes.

The real cover comparison also exposed the bundled opening date placeholder's solid fill masking the bottom rule. Replacing sample text had removed that artwork. Both native composers now retain the fill/geometry as fixed layout artwork, without its sample text. The corrected cover was rendered and visually compared with the approved template. The latest non-renderer regression run passed 290 tests; the shifted-glyph PowerPoint render regression passed separately. These checks do not substitute for the live HTTP acceptance report.

A subsequent full 16-page run completed both QA stages but correctly returned HTTP 409 for both exports: final QA found attribution crowding, and repair admission exhausted the remaining reserved budget. Evidence is `.local/verification/mit-redesign-verified.json` (passed=false), not a successful release. This led to reuse of passing paired reviews only when every image/native/template/rubric evidence hash is identical, with new findings invalidating reuse. Full ordered output QA still runs after edits. The source-fidelity rubric also no longer demands unsolicited external research for unchanged source claims; introduced claims and evidenced contradictions remain checked. Regression coverage now includes changed-image invalidation and re-review of repaired native objects.

Further real-file runs reproduced (a) invisible PDF paths joining screenshots/underlines into a single bitmap, (b) rejected rendered repairs being mistaken for an unchanged proposal, and (c) a missing slide-index component in a model relationship ID suppressing all paired QA. Import now excludes fully transparent paths as region seeds; final repair retries carry rejected-render findings with a two-retry bound; unique omitted-index references normalize only to existing supplied IDs. Ambiguous/unknown references still fail. A source-preparation failure now runs diagnostic paired QA on the preserved baseline but retains the preparation error and export block. The exact rejected relationship response validated after the normalization fix. Default redesign allowance is now 120,000 tokens per source slide, capped at 2,000,000; explicit configured caps remain authoritative. Paired-review reserves account for targeted/unresolved slides after an initial full review.

The final 16-page MIT run used Luna for both agents and completed paired review of all 16 originals/candidates, targeted repairs, and all 16 ordered output reviews. Coverage, sequence, accuracy, and final visual QA passed. The paired review still flagged embedded screenshot text on page 4; therefore the deck is NOT certified. Both actual PPTX and PDF download requests returned 409. The original PDF hash is unchanged. Evidence: `.local/verification/mit-redesign-release-check.json`, `passed=false`, 55 requests and 1,118,886 recorded tokens. The live job continued despite a progress-connection interruption; the harness now retries bounded read-only requests and supports `--resume-session <id>` to collect that same job without uploading or generating again. Resume collection time is recorded separately from generation duration. Backend regression verification: 297 passed, 7 renderer-marked tests deselected; the native shifted-glyph render test passed separately. These are implementation checks, not a claim that this real deck passed QA.

### Accepted cosmetic-warning policy — September 28

Rubric `severity-aware-qa-14` and release policy `severity-aware-qa-23` add a non-blocking warning severity for cosmetic spacing/alignment without impaired readability or meaning. Warnings remain visible and do not trigger automatic repairs. Uncertainty about material harm, confirmed defects, missing reviews and provider errors still block. A passed check label cannot hide review/blocking findings. Code text boxes retain a requested shared left edge; their protected text and typography are no longer incorrectly treated as a centered image.

Live evidence re-reviewed the user's existing 16-slide candidate (SHA-256 `9bc2ad4a3be8779b0411d779bfc0a9313c58b376a683261b75de3bf12b922a0b`) without changing its bytes or the source. All 16 paired reviews and all 16 ordered reviews passed through 21 fresh Luna calls. The release functions settled the record to ready and accepted the download gate, retaining cosmetic warnings. This was a real-artifact re-review and gate check, not a new HTTP upload/download cycle or an alteration of the active browser session. Sanitized evidence: `.local/verification/severity-real-deck.json`. Old QA receipts are not silently downgraded; a fresh upload/generation after restart uses the new rubric.

Verification: 305 backend tests passed (7 renderer tests deselected), plus the subsequently added ordered-warning test passed; 25 frontend tests, TypeScript compilation and production build passed. Tests cover warning-only release without cosmetic replanning, material/missing-review blocks, retained warning evidence, code geometry protection, and enabled download UI with suggestions. Server restarted after live verification.

### Mandatory closing — September 28

Rubric `required-closing-15` and policy `required-closing-24` require a final Thank you page on `1_Title Slide` (statue photograph). Redesign preserves all source pages, reuses a suitable existing final closing, or appends an explicitly authorized native closing. Source mapping remains source-only; added-page provenance is separately validated. Missing, moved, changed or unexplained added closing content fails artifact coverage. Source-derived pages retain original comparisons; the added closing is reviewed against its authorization and approved template. It is included in all ordered QA and appears in its own output preview. Authoring outlines require the Thank you title before approval.

Tests: 314 backend passed, 7 renderer-marked deselected; 26 frontend tests, TypeScript compilation and production build passed. Coverage includes no duplicate closing, preservation of the prior final source page, tampering/missing-closing rejection, added-page visual review, ordered QA without a fabricated source original, and output preview addressing.

Live test: copied the user's previously approved 16-slide candidate, appended the closing, rendered 17 pages through PowerPoint, and made 22 fresh Luna review calls. Native artifact coverage passed and all 17 individual visual reviews passed; the closing had only a cosmetic placement warning. Final ordered QA completed all 17 but reported separate missing-text/attribution findings on existing page 5, so the complete test deck stayed blocked. This is NOT a claim of full-deck release success. Original PDF unchanged. Evidence: `.local/verification/required-closing-real-deck.json`; template-only preview: `.local/verification/required-closing-preview.png`. Server restarted to activate the feature.


### Explicit visual planning and repeatable authoring repair — September 29

Rubric `visual-planning-16`, policy `visual-planning-25`. Live Luna planning chose a diagram and table for a synthetic process/numerical-comparison topic without being asked for visuals. The first real render exposed a four-step diagram limit and a mistaken assumption flag on user-supplied illustrative data. The diagram now allows up to six bounded steps; author instructions distinguish supplied examples from new assumptions.

The second live case generated the correct statue-photo closing but failed QA for an omitted first-review total. This exposed an authoring repair filter that only forwarded visual findings. It now forwards actionable content and sequence findings too. An exact replay of that failed outline/content triggered one repair, preserved the diagram, rendered again, and passed all nine checks with no remaining findings (`state=ready`, downloads enabled; five Luna calls). Evidence: `.local/verification/visual-planning-live-v3/generation/generation.json` and `summary.json`. This was a synthetic authoring run, not a new full Matrix Calculus redesign; the earlier PDF is no longer present in this workspace.

### Vercel AI Gateway — September 29

Added the Gateway Chat Completions adapter with image input, strict structured outputs, role-specific model selection and separate reasoning settings. The recommended configuration is Sonnet 5.5 (low effort) for planning/authoring/redesign and Opus 5.5 Fast (medium effort) for QA. Credential values remain in the ignored local environment or deployment secrets; returned configuration and errors expose no keys. Explicit provider selection never falls back after a failure. See `AI_GATEWAY.md` for model evidence, configuration precedence and deployment limitations.

All five shortlisted models passed the live synthetic vision/schema smoke test. The full synthetic PDF redesign used the recommended pair for source decisions, paired QA, a QA-triggered repair, rerendering and final ordered QA. All 11 checks passed, with PPTX/PDF release allowed and the appended closing present (10 calls, 190,501 recorded tokens). Evidence: `.local/verification/gateway-redesign-live`.

The separate authoring run chose a diagram, chart and table. QA correctly blocked dark header text on the inherited red table fill. The compositor now sets explicit contrasting header/body colors, verified in the saved PPTX and a real PowerPoint render. Replaying the exact generated deck passed all four output-QA checks with two fresh calls. Its native `CHART_STYLE` inspection finding remains `needs_review`; therefore the authoring replay is not a fully released deck. Cosmetic QA suggestions remain visible. Evidence: `.local/verification/gateway-authoring-live` and `.local/verification/gateway-authoring-replay`.

Verification: 335 backend regression tests passed (seven renderer-marked tests deselected), followed by 41 focused Gateway/OpenAI/visual-planning tests after the table-contrast fix. Live tests used the actual Gateway key and real PowerPoint rendering, without mocking model responses. No new full private MIT-deck reproduction was performed.
