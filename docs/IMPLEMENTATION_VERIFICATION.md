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
