# Stevens Slide Studio — reconciled handover

Updated October 6, 2026. Combines the user-supplied handover from the chat “work” with this chat's main-checkout changes. This document records decisions and status; it does not authorize deployments or publishing.

## Authoritative local version

Continue development in the main `stevens-slide-studio-main` checkout (branch `reviewed`). The separate `.local/deployment-checkout` (branch `codex/vercel-full-stack`) contains deployment work and substantial uncommitted changes. Preserve both; do not reset, clean or copy one wholesale over the other. The main checkout is the combined local app. Vercel/container/shared-storage changes remain in the separate checkout and are deferred.

## Reconciled decisions

- Windows FastAPI/Uvicorn plus React/Vite, using local LibreOffice rendering. `tools/start.ps1` prefers the existing portable renderer under `.local/tools/libreoffice/extracted/program/soffice.com`. Docker optimization is deferred.
- Default reformatting is local native template composition followed by QA (`preserve`). Explicit AI redesign remains an API option. Idea/PDF authoring still uses AI.
- Completed artifacts can be downloaded despite QA findings or failures. Preserve the QA verdict and review controls. Authentication, ownership, completion, revision, source, template and artifact identity protections remain.
- Use the existing personal OpenAI key with all active roles on GPT-6 Luna; no Vercel Gateway calls. Keep cumulative AI call/token caps zero/unlimited. Never record credentials in documents or test output.
- Users explicitly choose CPE or Stevens before uploading or planning. Retain the main registry `backend/slide_engine/templates.py` and the user's renamed `CPE_template.potx` and `stevens_template.pptx`. Do not import the deployment checkout's competing template registry/assets.
- Restore Developer account role and job-grouped operational logs. See DEVELOPER_ACTIVITY.md. No access to other users' decks or user management for Developers.

## Changes preserved from this chat

- Dismissal of a completed check's findings works despite unrelated API failures, with generation/slide-scoped decisions.
- PDF named/internal links and XML-invalid text handling, including Columbia_talk.pdf import coverage.
- Source chart theme preservation; synchronized table frame/row/column geometry; measured generated bookend text fitting.
- CPE layouts across all masters, template-scoped prompts/geometry/identity, removal of empty CPE Presenter sample label, source/template cache isolation.
- Cover-removal validation no longer conflicts with protected native content, links, groups and retained dependencies.
- QA batching plus final ordered synthesis.

## Deliberate integrations from “work”

Developer metadata service, activity UI and tests were integrated with targeted edits to authentication, import, providers, generation and authoring. Local formatting defaults and advisory downloads were reconciled without replacing the newer template, PDF, dismissal or timing fixes. The existing main account database is retained; the separate preview database is not copied or merged implicitly.

## Runtime and remaining deployment work

Start with `powershell -NoProfile -File tools/start.ps1`; open http://localhost:8000. Verify the actual listening process before restarting; launcher and Python PIDs can differ. Restarting clears in-memory jobs, so reupload afterward. Account metadata persists in the configured SQLite database.

No PR update, commit, push, paid-resource provisioning or Vercel deployment is part of this reconciliation. The other checkout's deployment PR and synthetic October 2 results are historical evidence only, not validation of the combined main app. A specific user's failing deck still requires a fresh run; synthetic checks do not prove it succeeds.

## Validation

Combined regression validation: 220 relevant backend tests passed (3 renderer tests deselected), covering Developer permissions/log accounting, local defaults, advisory QA downloads, authoring, dismissal, PDF identity and explicit AI repair behavior. The earlier broad run passed another 191 non-renderer tests outside this rerun's files; obsolete QA-gate assertions were updated, and its PowerPoint sandbox failure was rerun with LibreOffice.

Frontend: 35 tests passed; TypeScript and Vite production build passed. Actual LibreOffice render checks: CPE and Stevens three-slide samples rendered; the chart-color and fitted-closing regression passed. No new paid AI calls were required. These checks do not certify the user's specific deck.

Local server restarted successfully at http://localhost:8000. Health reports LibreOffice and direct OpenAI GPT-6 Luna for redesign, generation and review. The current production bundle is served; unauthenticated Developer access returns HTTP 401. Account data is retained; in-memory jobs reset.


## Follow-up: incomplete QA rubric response

Fixed the reported 25-of-32-slide stop caused by an adverse rubric status without a matching slide/criterion finding. Correction requests now include the rejected response and precise slide/criterion diagnostics. Repeated rubric inconsistencies trigger bounded subdivision of only that batch; coverage, object IDs and evidence validation remain enforced. Persistent single-slide failures remain explicitly incomplete. A synthetic 32-slide regression reaches final synthesis and preserves the reported defect. Validation: 101 targeted backend tests passed, 2 renderer tests deselected; no live model calls used for this regression.


## Reformatter validation with user test assets

The reported 32/32 review failure was a local request-size rejection before the API call. The saved job had 625,660 characters of slide manifest and 115,820 characters of prior reviews, exceeding the adapter's 300,000-character prompt bound. Deck synthesis now sends compact object identity/content rows and complete criterion-status maps instead of repeated layout metrics and passed-check prose. All original/final slide images, slide text/notes, source evidence and findings remain; the full manifest and audit ledger stay in local evidence. JSON is serialized compactly. Size failures now report a safe explicit error code/count rather than an opaque preparation error.

Real source testing also found a separate PDF link-decoration bug: vector underlines could cross native text after reformatting. Confidently matched, span-wide URL underlines now become native run underlines; partial/ambiguous/non-link artwork remains unchanged. MIT math glyphs were present visually but extracted out of order by LibreOffice. That narrow case is now a visual-review notice, not a missing-text failure; absent/changed symbols remain failures.

Actual live OpenAI tests (GPT-6 Luna, local LibreOffice):
- `test_asset/mit_ppt.pdf`, Stevens: 16 source pages, 17 output pages; all output QA checks passed; PPTX and PDF exports verified. 5 requests, 227,997 tokens, 117.5 seconds. Structural/render review notices remain. Evidence: `.local/verification/reformatter-real/mit-stevens-c/`.
- `test_asset/Columbia_talk.pdf`, CPE: 31 source pages, 32 output pages; all slides and global synthesis reviewed; PPTX/PDF exports verified. 11 requests, 865,846 tokens, 437.4 seconds. Final synthesis metadata was 227,049 characters (252,153 on correction). Coverage/sequence passed, but accuracy/visual checks report substantive layout and mathematical-notation findings, including legacy footer artwork, duplicated cover metadata and displaced/altered equation symbols. These quality findings are unresolved and were not waived. Evidence: `.local/verification/reformatter-real/columbia-cpe-b/`.

Do not describe Columbia as a clean fidelity pass. This work resolves the request-preparation failure and specific import/verifier defects; the local PDF reformatter still has limitations with this complex TeX-heavy source. No source test files were modified.

Validation after these changes: 430 backend tests passed, 8 renderer tests deselected. The shifted PDF-glyph renderer regression separately passed with LibreOffice. The corrected MIT link page and math output were visually inspected. Existing frontend assets are unchanged for these backend fixes.

## Follow-up: reformatter fidelity and QA references

The subsequent screenshots showed a completed review with genuine output defects, plus duplicated observations and a stale download-blocking label. The PDF importer now joins multiline cover headings, removes confirmed running-footer copy duplicated on the original cover, removes associated navigation controls and isolated title backdrops/shadows, and records those decisions. Unique citations, source logos and article artwork remain. Complex embedded fonts use source image regions with whole-object overlap closure; supported text and cover fields remain editable. The UI explicitly discloses image-region editability. Source previews remain the untouched original PDF.

Exact PDF path suppression replaces area deletion for navigation cleanup. It matches transformed root-page paths, leaves text/clip state and embedded article objects untouched, and preserves the original visible boundary above a full-width opaque footer. Region hashes/bounds and excluded navigation bounds are retained in the import receipt. Regression checks independently compare retained source pixels, text and non-navigation paths. Conservative unsupported stream constructs are left unchanged.

The native formatter fits surviving PDF content bounds instead of shrinking the old canvas and its margins into the template. Cover titles are measured to prevent overlap; standalone small lines on text-only pages receive bounded enlargement with following text moved only when it fits. Native object coverage remains independently checked. The formatting policy version is `local-advisory-qa-31`; existing imports must be uploaded again to use these changes.

QA synthesis reference corrections now include every invalid ID and the valid IDs for each affected slide, addressing the prior opaque retry that could fail twice. Paraphrased batch/synthesis observations with matching location and repair are consolidated, retaining both evidence records and the strongest verdict. The UI reports high-priority findings as needing correction instead of falsely claiming downloads are blocked.

Live intermediate validation: MIT/CPE final candidate (`.local/verification/reformatter-real/mit-cpe-fixed-b/`) passes all four AI QA checks with PPTX/PDF downloads verified: 17 output slides, 5 calls, 242,592 tokens, 107.2 seconds. Structural/render notices remain. Columbia's earlier intermediate candidates are diagnostic only; the final exact-path/boundary run is recorded separately below when complete. Frontend: 35 tests, TypeScript and production build passed. The backend suite passed 438 tests before the final path/boundary changes; final validation is recorded below.

The Columbia `fixed-d` run passed native structure, rendering, source coverage and AI coverage/sequence/accuracy, but the model falsely read `[left, top, width, height]` as corner coordinates. Its evidence claimed the content region ended at 6.05 inches; the true bottom is 0.4 + 6.05 = 6.45, and the cited objects were contained. QA now receives named rectangle edges for objects and template regions, explicit units/format and the arithmetic rule. The correction is covered by a regression asserting the exact 6.45-inch bottom in both batch and synthesis metadata. These false results were not converted to passes in saved historical records.

Final local regression suite: 439 backend tests passed, 8 renderer tests deselected; 16 targeted PDF/QA tests subsequently passed including the additional coordinate-format regression. A subsequent 11-test QA/deduplication subset also passed. Live tests exercise actual LibreOffice rendering and verified PPTX/PDF downloads. Frontend bundle `index-D-tHZ4z3.js` is served at localhost:8000 after restart; health reports LibreOffice and direct OpenAI GPT-6 Luna for all active AI roles. Launcher PID 31452, actual listening server PID 48976 at restart. Historical in-memory jobs reset; account data remains.

Final live Columbia result: `.local/verification/reformatter-real/columbia-stevens-fixed-e/`, Stevens, 31 source / 32 output slides, 212.4 seconds, 8 calls, 415,971 tokens. All nine checks passed, including native structure/rendering and all four AI QA checks; PPTX/PDF exports verified. Two raw cosmetic observations concern the same legible cover-title wrapping. The final consolidator was verified against these exact saved observations to produce one finding while retaining both evidence records; the saved historical test report is not rewritten. This supersedes the earlier unresolved Columbia status. The supplied source still contains cropped embedded webpage captures, so a passed fidelity review is not a claim that unseen source material was reconstructed.

Final deduplication regression: 11 tests passed after allowing matching descriptions as well as matching repair wording for the same criterion, slide and concrete object IDs. Distinct defects and different slide/object identities remain separate. The local server was restarted again to load this final reporting change; use the runtime log/current listener to resolve its latest PID.

## Follow-up: PDF pages with visible content but no text layer

The user clarified that the page-30 import error belongs to a different 97-page test deck, not Columbia. Their screenshot shows a diagram with equations. The exact PDF was not supplied, so its internal encoding has not been confirmed. The importer previously rejected any page with no extracted text before inspecting its graphics; that guard was the source of the error.

Such pages now retain their entire source composition as a bounded-resolution image, including blank pages, without OCR or invented labels. Internal/web links remain interactive. Receipts record the page-image bounds, pixel dimensions and hash, and explicitly disclose that text is not individually editable. Native-text pages keep their existing import path. QA receives this evidence and must check the paired images without treating an empty text inventory as missing content; visual/template/content checks remain required. Upload and QA UI copy describe the limitation. Policy is now `local-advisory-qa-32`.

Validation: 46 targeted backend tests passed, including a 30-page API-upload regression, raster/vector/blank page preservation, pixel equality, unchanged source bytes, internal/web links, both templates, existing PDF fidelity and QA recovery. One renderer test initially selected inaccessible PowerPoint COM; rerunning with the app's configured LibreOffice passed. Four actual raster/vector output decks rendered with all render checks passed (16 total output slides). The Stevens diagram output was visually inspected. All 35 frontend tests, TypeScript and production build passed. These tests do not constitute a paid AI QA run or verification of the user's unavailable PDF.

Local server restarted with launcher PID 38784 / server PID 38804; updated bundle `index-CJdSRM9p.js` is served at localhost:8000. Refresh and reupload the previously rejected deck.

## Follow-up: 98-slide final QA metadata limit

The next user screenshot showed all 98 output slides reviewed but synthesis rejected locally at 341,907 metadata characters (300,000 limit). Inspected the actual saved job before restart: repeated template contracts accounted for approximately 90,000 characters and template context for 47,000; there were only three distinct contracts and four context variants. This was a request preparation failure after completed batch reviews, not missing slide coverage.

New `app/ai/qa_payload.py` losslessly shares identical template contracts/context, note comparisons and PDF preservation explanations in large requests. Each `FIELD_ref` resolves through `shared_metadata`; QA receives explicit instructions. Full local manifests, ordered original/candidate images, findings, schema, object IDs, source evidence and response corrections are retained. Packing runs before every provider call, including validation retries. Call diagnostics record metadata size and sharing count. The provider limit is unchanged. Policy is `local-advisory-qa-33`; no frontend change was required.

Validation: 14 payload/recovery tests plus 97 provider/mandatory-QA/download tests passed. New regressions exercise 98 and 100 slides with all original/candidate images, preserved defects, lossless field reconstruction and object-reference corrections; all provider prompt formats preserve schema and caller input. The exact failed request was replayed using its previously validated batch results without paying to repeat those reviews. Live direct OpenAI synthesis used 208,159 characters and all 195 images (97 originals + 98 outputs), completed in 53.5 seconds, one API call, 375,255 tokens. Coverage, sequence and accuracy passed; visual QA remains failed with 63 consolidated findings (28 blocking, 6 review, 29 warning). These were not waived. This fixes the synthesis error, not the separate visual issues in this deck.

Diagnostic runner `.local/verification/recover_large_qa.py`; successful result `.local/verification/qa-98-recovery-live/qa-result.json`, with copies of the unchanged candidate `result.pptx` and `result.pdf` retained there for inspection. The first restricted-network diagnostic hit a provider connection error; the authorized network retry above completed. The app was restarted to load the code; old in-memory jobs are not restored. Use runtime logs/current listener to identify the latest server PID.
