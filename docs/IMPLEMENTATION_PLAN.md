# User management, processing-only cleanup, and presentation generation

Plan updated September 24, 2026. Status: **core workflows implemented; see [implementation verification](IMPLEMENTATION_VERIFICATION.md) for tested behavior and remaining limits**. The sections below preserve the design and acceptance targets; they are not a blanket statement that every future improvement is complete. Based on the [functional requirements review](FUNCTIONAL_REQUIREMENTS_REVIEW.md).

Implementation steering: the user subsequently selected **invitation-code sign-in now**, with `admin` as the initial administrator code and administrator-created member codes. Google SSO is deferred. Account storage uses a versioned SQLite schema for this local single-worker build. Source PDF figures currently use source-page images, and equations/plots use high-resolution raster rendering. Generated pictures remain disabled. These choices supersede the earlier proposed SSO-first/database/vector recommendations below.

## 1. Confirmed scope

After login, show two separate entry points: **Use my PowerPoint** and **Generate a new presentation**. The first routes directly to the existing PPTX upload/redesign workflow. The second opens a dedicated authoring screen with topic/outline or PDF as its source. These entries lead to three presentation workflows:

1. **Reformat a PowerPoint:** retain the existing content-preserving workflow, including alignment, rendering, review, and verified download.
2. **Create from a topic or outline:** accept a topic and/or starting outline, audience, and a presentation-length selection; automatically choose an appropriate slide count; propose an editable outline; require outline approval; generate new content; compose an editable native PPTX; render, review, repair, and gate download.
3. **Create from a PDF:** extract and understand the document, propose a source-grounded outline, and continue through the same approval, authoring, composition, and verification workflow.

All three require authenticated users, owner-only content access, and temporary processing workspaces with verified cleanup. Optional picture generation is a separate phase and must not block the core release. Existing PDF figures and native shapes/charts remain usable while generated pictures are disabled.

All three also require a separate output-QA agent pipeline that receives screenshots of every final output slide in presentation order and evaluates visual quality, narrative sequence, and content accuracy against available evidence. Existing slide-level checks alone do not satisfy this added requirement.

**Plots, charts, mathematical expressions, and function plots are required core capabilities**, not part of optional AI picture generation. They must work with the existing text/vision model and deterministic rendering libraries.

Vercel deployment and Vercel AI Gateway integration remain deferred. A permanent presentation library, collaboration/sharing, public signup, and a free-form slide canvas are outside this implementation.

## 2. Recommended defaults

These are implementation recommendations, not unresolved questions requiring the user's approval.

| Area | Initial choice |
|---|---|
| Identity | Provider-neutral OpenID Connect (OIDC), invite-only access, member and admin roles; use the organization's existing identity provider if available |
| Accounts | Retain only account, authentication, membership, and minimal operational metadata; never presentation content in the account database |
| Storage | SQLAlchemy and migrations; SQLite locally with a PostgreSQL-compatible schema; isolated temporary workspaces for presentation content |
| Main model | Keep `gpt-6-luna` for outline planning, content generation, PDF understanding, redesign, and review; no automatic upgrade to a costlier model |
| Slide settings | Selection: **Auto (recommended), Brief, Standard, Detailed**. The planner chooses the count from source coverage, audience, and readable density; no fixed-number input. Initial technical ceiling: 30 output slides, including title/closing/references; do not pad or truncate to meet a preset |
| Output QA | A separate reviewer role using the configured Luna model, with fresh review context, ordered screenshots of all slides, source evidence, and independent coverage/sequence/accuracy gates |
| PDF limits | Proposed application limits: 50 MB and 100 pages, with additional image-pixel, extracted-text, token, and runtime limits; reject excess explicitly instead of silently truncating |
| Lifetime | 60 minutes without meaningful user activity; four hours absolute job lifetime; a bounded generation execution window, initially 45 minutes; display expiry in the UI |
| Cleanup | Immediately revoke access on finish/cancel/expiry; stop workers, release file handles, delete artifacts, and verify deletion; sweep at least every minute |
| Download | Offer **Download and finish** to retrieve the verified file and end processing, plus **Finish and delete** and **Cancel and delete** |
| Images | Off by default; native diagrams and source figures first; optional image-model capability behind a feature flag and a separate budget |
| Plots and math | Native editable charts for supported data charts; deterministic scientific plots and equation graphics with their data/formulas preserved in the PPTX |
| Cost controls | Retain the configured call ceiling, add cumulative token and execution limits, limit concurrent jobs per account, and bound repair attempts |

“Processing-only” means temporary storage is permitted while extracting, generating, rendering, and reviewing, but content is removed when the workflow ends. It does not mean that PowerPoint/LibreOffice can operate without temporary disk files. User-downloaded files belong to the user and are outside application cleanup.

## 3. Phase 1 — Job ownership and user management

### Implementation

- Add an authentication module with OIDC authorization-code login, PKCE, state/nonce validation, issuer/audience validation, and logout. Use a maintained OIDC library instead of implementing token verification manually. OIDC provides the identity layer; application roles and permissions remain server-controlled. See the [OIDC specification](https://openid.net/specs/openid-connect-core-1_0.html).
- Use opaque, revocable server-side login sessions. Production cookies must be Secure, HttpOnly, and SameSite; protect state-changing requests against CSRF, restrict allowed origins, and rotate sessions on login. Follow the [OWASP session guidance](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html).
- Add migrations and records for users, identity bindings `(issuer, subject)`, role/status, invitations with hashed expiring tokens, and hashed login-session tokens. Provider credentials stay server-side in ignored environment files.
- Implement invite, list users, change role, deactivate/reactivate, and logout. Prevent removing or deactivating the last active admin. Bind invitation acceptance to a verified identity; do not trust client-supplied roles or unverified email addresses.
- Provide a repeatable initial-admin bootstrap command. Invitations can use a copyable invitation link initially; automated email delivery is not a prerequisite.
- Assign every processing job an immutable `owner_user_id`. Centralize authorization before every metadata, upload, outline, generation, preview, review, download, and deletion operation. Protect legacy session routes too.
- Members can access only their jobs. Admin privileges allow account administration, not automatic access to other users' presentations. Use consistent not-found responses for another user's object IDs.
- Deactivation revokes login sessions and cancels the user's active jobs. Logout ends that login and cancels its associated processing jobs. Account removal deletes identity metadata after associated jobs are purged; avoid retaining content in audit events.
- Add sign-in/out, an account menu, and an admin user-management screen. Preserve active work only within the stated processing lifetime; there is no saved-deck history.
- After login, show **Use my PowerPoint** and **Generate a new presentation** as separate primary actions. Route the former to existing upload/analysis/reformat/review screens and the latter to new authoring screens. An existing-PPTX job must not be sent through new-content generation automatically.

### Verification checkpoint A

- Anonymous requests to all protected routes return 401, including old session routes and static preview paths.
- Two real test identities exercise every route: user B cannot read, edit, approve, render, download, cancel, or delete user A's job even with exact IDs.
- Members cannot invoke admin endpoints. Admins cannot read other users' decks. Expired/replayed invitations, forged callbacks, invalid tokens, and CSRF attempts are rejected.
- Role changes, logout, and deactivation invalidate access immediately. Last-admin protection and migrations are tested.
- Run integration tests with a local test identity provider; perform a separate real-provider sign-in/admin acceptance check once configuration is supplied. A mocked login alone does not close this checkpoint.
- Browser tests cover both post-login entries, direct-link authentication, and correct routing. Existing PPTX uploads retain the preservation workflow; topic/outline/PDF creation uses the separate authoring entry.

## 4. Phase 2 — Processing-only file lifecycle

### Implementation

- Replace scattered temporary paths with one workspace manager. Every source, PDF extraction, prompt/content draft, image, preview, renderer output, PPTX candidate, revision, and report belongs to exactly one job directory.
- Put workspaces in a dedicated private temporary location outside the repository, OneDrive, and backups. Configure renderer temporary directories/profiles where supported and audit Office/LibreOffice recovery/cache locations for source-content copies.
- Keep only an opaque job ID, owner ID, lifecycle status, deadlines, worker lease, and deletion status in durable operational metadata. Do not put topic text, filenames, outlines, review rationale, thumbnails, or document hashes into permanent account/audit records. Artifact hashes and manifests live inside the temporary job workspace.
- Model lifecycle explicitly: `active -> closing -> purging -> purged`, with `purge_failed` visible to operational monitoring. Generation stages are separate from this lifecycle. Closing immediately denies further access and rejects late worker writes.
- Use worker leases and cancellation tokens. Wait for or terminate the bounded worker/renderer process before deleting its directory. Restrict termination to processes created for that job; never kill an unrelated user PowerPoint process.
- Make finish/cancel/delete idempotent. Verify that files and directories no longer exist; retain a content-free deletion task and retry if a Windows file lock prevents removal. Never report successful deletion merely because a delete method returned.
- Add a startup orphan scan and a periodic sweeper. Reconcile stale worker leases after crashes. Shutdown attempts cleanup; restart recovery remains required because graceful shutdown is not guaranteed.
- Apply both idle and absolute deadlines. Status polling and preview fetching must not extend idle lifetime indefinitely. A running model call cannot bypass the absolute deadline.
- Implement download completion safely: hold a read lease while streaming; the browser acknowledges a fully received blob, then closes the job. Failed/disconnected downloads get a bounded retry window, initially ten minutes, followed by cleanup. The UI states that automatic download-and-finish ends further editing; offer plain Finish and delete independently.
- Purge on explicit finish/cancel, expiry, deactivation, and terminal failure. Recoverable errors may retain files only inside the same bounded active job. Browser-close events are best-effort hints, never the cleanup mechanism.
- Remove **Save approved benchmark** and its product API. Disable content-bearing learning logs. Use synthetic fixtures for permanent automated tests; keep any deliberately retained development evidence outside the product lifecycle.
- Set no-store on content responses, avoid persistent browser storage for content, revoke object URLs, and clear client state on close/logout. Sanitize errors and logs so filenames, prompts, slide text, images, and provider request/response bodies are not retained.
- Inventory existing legacy workspaces and benchmark copies before migration. Automatically purge recognized expired application workspaces; report deliberately saved development files separately rather than deleting unrelated files.

### Verification checkpoint B

- Track unique synthetic content markers and enumerate application-managed files, logs, temporary renderer outputs, and database rows before/after each scenario: finish, download acknowledgment, interrupted download, cancel, idle expiry, absolute expiry, provider timeout, renderer crash, terminal error, account deactivation, shutdown, and restart.
- Confirm byte-bearing files disappear, stale URLs become inaccessible, late callbacks cannot recreate directories, and the database retains no presentation content.
- Simulate locked files and failed deletes; verify retry, operational visibility, and eventual removal after handles are released. Do not mark the checkpoint passed while a deletion failure is hidden.
- Kill the worker during rendering, restart the service, and verify orphan cleanup. Verify normal downloads are never truncated by cleanup and retries never extend the absolute deadline.
- Confirm benchmark APIs are unavailable and repeated polling cannot keep abandoned jobs alive.

**Guarantee boundary:** the cleanup timer requires a running supervisor or a disposable processing environment. If the entire machine is off, application code cannot erase its disk at the scheduled instant. The implementation must document startup recovery and avoid promising stronger guarantees than the tested runtime provides. This is a file-lifecycle constraint, not a request to deploy to Vercel now.

**Provider boundary:** keep `store=false` and avoid persistent Files/vector-store resources for this workflow. This does not establish zero provider retention; OpenAI documents separate application-state and abuse-monitoring rules. Verify the configured organization's data controls before claiming end-to-end zero retention. See [OpenAI data controls](https://developers.openai.com/api/docs/guides/your-data).

## 5. Phase 3 — New presentation from a topic or outline

### Product workflow

`Login -> Generate a new presentation -> topic/starting outline or PDF + audience + length selection -> automatically sized outline -> edit and approve -> generate content -> compose native PPTX -> render and verify -> independent ordered output QA -> user review -> download and finish`

- Give creation its own route and form, separate from Use my PowerPoint. Topic/outline input must not be overloaded into the existing redesign-instructions field. PDF upload belongs within new-presentation generation.
- Replace the fixed slide-number input with **Auto (recommended), Brief, Standard, Detailed**. Auto balances coverage and readable density; Brief emphasizes key takeaways; Standard adds supporting explanation; Detailed includes deeper evidence and examples. These are depth preferences, not hard-coded numeric quotas.
- Calculate the proposed count from the material, audience, selected depth, required sections, and space needed for readable plots/math. Display the resulting count and a short explanation alongside the outline. Short material must not be padded with repetitive slides; long material must not be silently truncated to a preset.
- Outline editor supports changing slide titles and key points, adding/removing/reordering slides, and marking required material. Recalculate the displayed count automatically. Approval binds to the actual proposed slide sequence, not a number the user must type.
- Allow adaptation during planning. If composition or QA later requires a split, merge, or reorder, propose an updated outline/count and return to outline approval before releasing that new sequence. Do not force overflowing content onto slides to preserve an obsolete count.
- Enforce a configurable resource ceiling (initially 30 slides), distinct from the length selection. If required coverage cannot fit, explain the limit and propose a narrower scope or multiple separate presentations; do not drop required material or silently exceed the budget.
- Store an outline revision and approval hash. Any later change to inputs or outline invalidates approval and all dependent candidates. Generation requires the approved revision, not whichever outline happens to be in the browser.
- Show progress and actionable errors for outline planning, authoring, composition, rendering, and review. Allow cancellation throughout.

### Backend and composition

- Define validated schemas for `CreationRequest`, `Outline`, `ApprovedOutline`, `DeckSpec`, `SlideSpec`, `SourceReference`, and `AssetSpec`. `CreationRequest` carries `length_preference: auto|brief|standard|detailed`; the planner supplies `proposed_slide_count` and its rationale. Approved slide IDs/order define the expected output count. Use stable slide IDs to preserve review mapping after reorder/split operations.
- Extend provider role configuration to outline/content/extraction roles while retaining `gpt-6-luna` defaults and existing planner/reviewer behavior. Validate structured responses, retry malformed output within budget, and provide explicit errors on exhaustion.
- Generate slide content and speaker notes from the approved outline. Record assumptions and unsupported factual claims as review findings. Do not manufacture citations, statistics, or quotes. Topic-only generation is not automatic factual verification or live web research.
- Build native PowerPoint objects using the existing template and `python-pptx`: titles, paragraphs, lists, shapes, connectors, pictures, editable tables, and supported native charts. Start with title, section, one/two-column, comparison, process, chart/table, and image-with-caption layouts.
- Use typed content plus deterministic layout functions. Never execute model-produced Python, macros, or arbitrary slide XML. Preserve editability for text, shapes, tables, and supported charts; source figures and pictures remain image objects.
- Create an immutable content manifest before composition. Version it whenever a repair changes content; invalidate affected checks and human approvals. Layout-only repairs keep authored wording intact.
- Keep existing uploaded-PPTX preservation rules unchanged. New authoring has permission to create wording; reformat mode does not acquire that permission.

### Required plots, charts, and mathematics

- Add typed `ChartSpec`, `PlotSpec`, and `MathSpec` elements to the authored content model. Accept formulas and data from topic/outline input, extracted PDF material, or slide-content corrections. Let reviewers inspect and edit the formula, domain, series data, labels, and units before regenerating the affected slide; changing them invalidates that candidate's checks.
- Support native editable PowerPoint column/bar, line, pie, area, and scatter charts initially. Preserve series names, categories, numeric values, axis labels, units, and legends in the chart's embedded workbook. Do not create factual datasets merely to fill a chart. Explicitly labeled illustrative data is acceptable for educational examples.
- Support deterministic 2D plots: function curves such as `y = sin(x)`, multiple functions/series, scatter plots, histograms, and heatmaps. Provide configurable x/y ranges, linear/log axes, labels, units, legends, and annotations. Distinguish a supplied data plot from a sampled mathematical function.
- Use trusted numerical/plotting libraries, such as NumPy and Matplotlib, to generate plots from validated specs. Parse functions with a restricted mathematical grammar and an allowlist of operators/constants/functions; never use unrestricted `eval`, run model-produced code, or pass untrusted expressions to an execution-capable parser. Bound sampling size, complexity, memory, and execution time.
- Treat undefined values and discontinuities explicitly: break lines across poles and invalid domains, check nonfinite results, reject invalid log-axis ranges, and avoid drawing misleading connections. Example fixtures include `1/x`, `sqrt(x)`, and `log(x)` as well as smooth functions.
- Render equations with a declared supported LaTeX-style math syntax, initially fractions, powers/subscripts, roots, Greek letters, sums, integrals, limits, and common functions. Use a maintained renderer with command/file/network execution disabled. Reject unsupported syntax with a precise finding instead of silently changing the formula. Formula display and numerical function plotting do not imply a general symbolic algebra solver.
- Package equations and plots as vector graphics when the chosen PowerPoint/rendering path supports them reliably, with a high-resolution raster fallback. Keep the original expression, plot settings, and data in slide notes or suitable PPTX metadata, plus readable alt text, so they can be reconstructed. Native chart editing is supported; embedded equation/plot graphics are not advertised as native editable Office equations or chart objects.
- When a PDF contains mathematics, preserve a source-page reference and flag uncertain symbols, signs, exponents, or values. Recreate a plot only when its function/data is recoverable and checked; otherwise retain the cited source figure. Never infer missing numeric data from appearance and label it exact.
- Apply brand styling and minimum readable sizes without clipping equation baselines, superscripts, axis labels, or legends. Place larger expressions on dedicated space rather than shrinking them below readable size.
- Send the completed slide render through the same visual review and download gate. Deterministic rendering needs no separate image-generation model or image-generation API budget.

### Mathematics and plotting verification checkpoint C-math

- Reopen native charts and compare embedded workbook values, series, and labels with their specs; detect mutated values, omitted series, and mislabeled units.
- Compare sampled function values against independently calculated reference points within explicit tolerances. Test smooth curves, discontinuities, restricted domains, log axes, multiple series, empty data, and nonfinite values.
- Render representative fractions, roots, Greek symbols, subscripts, superscripts, sums, integrals, and limits. Inspect the exported PPTX through the real renderer for missing glyphs, clipping, legend/axis overlap, and legibility; test vector and raster fallback paths.
- Reject malformed/unsupported equations and attempts to execute code through expression input. Confirm input/sample/runtime limits hold.
- Run an end-to-end topic deck and a PDF-derived deck containing a native chart, a function plot, and equations. Verify numeric/formula provenance, correction/regeneration, candidate invalidation, final download, and cleanup of plot/equation assets.

### Verification checkpoint C

- Start without an uploaded file, select a depth, create/edit/reorder an automatically sized outline, approve it, generate its approved sequence/count, inspect actual rendered slides, and download a native editable PPTX.
- Exercise all four length selections against short and dense inputs. Confirm that counts adapt to content, the UI has no required fixed-number input, required topics survive, and extra slides are not filler. Test updated outline approval after a required split and explicit handling of the technical ceiling.
- Reopen the exported PPTX independently and compare text, notes, object types, chart/table values, asset references, and slide sequence against the approved outline and authored content manifest.
- Exercise minimal/long content, a small automatically sized deck and the 30-slide ceiling, non-Latin text, long titles, charts, tables, and failed/malformed model responses. Verify overflows and unreadable text block readiness or require the appropriate review.
- Change an approved outline or content revision and confirm stale generation, review approvals, and downloads are rejected.
- Confirm the existing uploaded-PPTX regression fixtures still preserve original content and unsupported objects remain blocked.

## 6. Phase 4 — PDF-to-presentation authoring

### Implementation

- Add PDF as a source inside Generate a new presentation, with audience, automatic length selection, optional focus instructions, and optional page range. Initially support one PDF per job. Derive the outline/count from the selected document material using the same adaptive rules as topic authoring.
- Validate file signatures, page count, size, decompression/image limits, and password/encryption status. Return clear errors for corrupted or password-protected documents; process extraction in a bounded worker.
- Use the existing PyMuPDF dependency for text, page geometry, figures, and page previews. Preserve original one-based page numbers in every extracted block and figure.
- Prefer text-layer extraction. Use bounded vision-assisted extraction for scanned pages, charts, tables, or uncertain reading order. Flag illegible or ambiguous values instead of inventing them. Show extraction problems before outline approval so users can correct, exclude, or replace affected material.
- Build a temporary document map and section summaries across the selected page range, then generate the outline from that map. Chunking must retain page references and report uncovered sections; do not silently use only the first pages.
- Generate source references for factual statements, quotations, tables, and chart values. Include readable source page references in notes and appropriate on-slide captions/reference slides within the approved slide count.
- Prefer extracting/cropping existing figures when useful. Recreate tables/charts as native objects only when values can be recovered and checked; otherwise use the source figure with a caption.
- Pass necessary text and selected page images directly to model requests. Keep derived artifacts in the job workspace, without a permanent embedding database or uploaded provider file collection. PDF inputs involve both text and visual processing; see [OpenAI PDF guidance](https://developers.openai.com/api/docs/guides/file-inputs).
- Treat instructions embedded in PDFs as source data, never as permission to change system rules, access secrets, or invoke external tools. Apply the same rule to pasted outlines and uploaded PPTX content.
- Reuse the outline approval and generation flow from Phase 3. PDF mode is a grounded summary, not a requirement to reproduce every source paragraph. Required sections and omissions must be visible in the proposed outline.

### Verification checkpoint D

- Test digital-text, scanned, mixed text/image, multicolumn, bilingual, table/chart-heavy, malformed, encrypted, and limit-exceeding PDFs.
- Trace generated claims and figure/table data to genuine source pages. Mutation tests introduce invented citations, changed numbers, missing required sections, and substituted images; the appropriate checks must fail.
- Check long-document coverage, uncertain OCR handling, and source instructions attempting to override application rules.
- Complete a real PDF -> edited/approved outline -> editable PPTX -> rendered review -> verified download -> confirmed cleanup flow. Use a held-out PDF that was not used to tune prompts; document its provenance.

## 7. Shared verification and download policy

Extend the existing generation identity with workflow mode, source manifest, outline approval revision, content manifest, asset manifest, and ordered render manifest, in addition to candidate/template/policy hashes. Every finding, human approval, preview, and download must refer to that exact identity.

| Check | Reformat PPTX | New topic/outline deck | PDF-derived deck |
|---|---|---|---|
| Plan coverage | Original objects/required splits | Approved outline/order, audience, adaptive length preference and resulting count | Same plus required PDF sections |
| Artifact coverage | Original content preservation | Authored content manifest versus reopened PPTX | Same plus valid source/asset references |
| Content review | Detect unauthorized changes | Coherence, assumptions, unsupported claims | Grounding, citations, numbers, quotations, omissions |
| Structural formatting | Existing bounds/font/overlap rules | Same rules applied to native composition | Same |
| Render verification | Actual candidate render | Actual candidate render | Actual candidate render |
| AI visual review | Required in full AI workflow | Required for every output slide | Required for every output slide |
| Independent output QA | Every output screenshot in order; preservation, flow, and evidence checks | Every output screenshot in order; narrative and accuracy checks | Same plus PDF grounding |

- Reuse page-scoped findings, selected bulk approval, previous/next navigation, and generated-slide mapping. Newly created decks show outline/source evidence where the reformat view shows an original slide; PDF mode can show cited source pages.
- Repair layout within the existing bounded pass policy. Content repairs rerun content checks and invalidate dependent approval. Changing outline structure returns to outline approval.
- Missing mandatory checks, unresolved blocking findings, absent real renders, or stale candidate identity prevent verified download. Human approval cannot override an objective content mismatch or failed mandatory check.
- If an unverified draft remains available, label it clearly, apply identical authorization and cleanup, and never present it as a successful verified export.
- Automated semantic/visual review is evidence, not a guarantee of factual truth. Record the checks actually performed and route uncertainty to human review.

### Separate output-QA agent pipeline

Build a dedicated `output_qa` reviewer/orchestrator, separate from the authoring/redesign agent and existing repair logic. It may use the same configured model, but has its own system prompt, fresh context, structured result schema, and evidence inputs. It must not accept the generator's assertion that the deck is correct as proof or directly modify the candidate it is evaluating.

**Input and order contract**

1. Freeze the exact candidate PPTX and reopen its presentation slide list to obtain canonical output order. Do not derive order from filesystem enumeration, asynchronous completion order, or lexical filenames such as `slide-1`, `slide-10`, `slide-2`.
2. Render that exact candidate into one screenshot per output slide. Construct an ordered manifest containing candidate hash, render identity, output ordinal `1..N`, stable slide ID, screenshot hash, and source/outline mapping. Include title, closing, reference, and every split slide. Reject unhandled hidden slides explicitly; never silently omit them from coverage.
3. Validate screenshot count, uniqueness of ordinal/slide ID mapping, image decoding, and matching artifact identity before invoking the agent. Identical-looking slides may have identical image bytes; this is not itself evidence of a missing slide. Missing, duplicated mappings, stale, or swapped screenshots fail the preparation gate.
4. Send the actual ordered screenshots with explicit ordinal/ID labels, extracted output text/notes, approved outline, factual source excerpts/page references, and chart/math specs. A text summary or contact sheet alone is not a substitute for individual slide screenshots.
5. Review in contiguous ascending batches if the full deck exceeds request/image limits. Every screenshot must appear in a recorded review request, and each response must identify the reviewed slide IDs. Validate those IDs against the batch manifest; do not trust a generic statement such as “all slides checked.” Retry only missing/failed batches within budget. Include overlap at boundaries for transition checks without counting an overlap as additional coverage.
6. Maintain an ordered review ledger with evidence references and unresolved questions. Run a separate deck-wide synthesis over the complete ordered slide text/outline and ledger, with ordered screenshots where context permits and targeted screenshot reinspection for cross-slide findings. It must check all consecutive transitions and broader dependencies, not merely summarize per-slide cosmetic findings. No silent downsampling to a few slides or discarding late slides to fit context.

**Review responsibilities**

- Visual: clipping, overlap, small text, unreadable charts/formulas, missing graphics, inappropriate crops, inconsistent styling, and unexpected empty slides.
- Sequence: introduction before detail, definitions before use, logical grouping, prerequisite concepts, transitions, duplicate/missing sections, and conclusions supported by earlier evidence. Compare the final sequence with the approved outline, or original order/approved split mapping for existing PowerPoints.
- Accuracy: match rendered claims, numbers, labels, units, citations, equations, and plots against source evidence and independently checked data/specs. Check contradictions across distant slides as well as within a slide. Keep deterministic numerical/formula tests alongside the agent; screenshots alone cannot establish exact data fidelity.
- Treat authored text as a specification of intended output, not independent factual evidence. For PDF mode, use original source pages/excerpts. For existing PPTX mode, distinguish fidelity from factual truth and flag questionable source claims without rewriting them. For topic-only decks, flag claims that lack supporting material as **unverified**, rather than certifying them from model confidence; unsupported factual claims require correction, evidence, or explicit user review.
- Return structured findings with scope, affected slide IDs/ordinals, severity, category, observed issue, evidence, recommended correction, and status (`supported`, `contradicted`, `unverified`, or `not_applicable` for factual checks). Deck-wide findings list all affected slides; the UI retains page-filtered findings and a separate deck-wide list.

**Completion and repair gates**

- Required gates: `output_qa_coverage`, `output_qa_sequence`, and `output_qa_accuracy`, alongside existing render/visual/structural checks. Coverage means complete validated request/response bookkeeping for the final screenshot set; it is not a claim that the model is infallible.
- A missing/failed batch, timeout, invalid response, unavailable reviewer, or exhausted budget cannot yield a verified download. Show progress such as “Reviewed 8 of 12 slides” using unique valid output IDs. Reserve QA budget before generation; do not spend the entire allowance on authoring and then skip QA.
- Objective corruption, changed values, known contradictions, or an unapproved sequence are blocking and cannot be bulk-approved away. Uncertain judgment calls/unsupported claims remain visible and require the defined human review; disclose any user-accepted factual uncertainty rather than labeling it independently verified.
- The authoring/redesign pipeline consumes findings and performs bounded repairs. Preserve source wording/order in reformat mode unless the user explicitly approves a supported revision; do not automatically “correct” source facts. Outline/structure changes in authoring return to outline approval.
- Re-render a repaired candidate and rerun output QA against the entire final ordered screenshot set. Earlier partial results are diagnostic only and cannot authorize a different candidate. Bind QA and human decisions to the final candidate/manifest hash.
- Store screenshots, source evidence, request manifests, ledgers, and QA reports only in the temporary job workspace. Apply ownership checks, cancellation, expiry, and verified cleanup to this pipeline too.

### Output-QA verification checkpoint Q

- Use fixtures with at least 12 slides to catch lexical ordering errors; verify recorded image payloads and slide labels are in canonical presentation order, including split slides and reference slides.
- Inject missing images, repeated ID mappings, shuffled payloads, stale hashes, unreadable renders, hidden slides, failed middle/final batches, and partial reviewer responses. Every case must prevent a false complete/verified state.
- Inject a conclusion before its evidence, terminology before its definition, contradictory values on distant slides, missing required sections, incorrect units, a changed equation, and a chart with inaccurate data. Test finding-to-slide mapping and resulting download gates. Use authored expectations and human-reviewed live cases rather than assuming probabilistic detection is perfect.
- Test batch-boundary transitions and long-deck global synthesis, including evidence from the first and last slide. Confirm coverage is based on actual screenshot request manifests, not a model-generated summary count.
- Correct a candidate, rerender, and prove that old QA findings/approvals cannot release the new file. Verify both routes—existing PPTX and new topic/PDF generation—run output QA.
- Complete a small live ordered-screenshot QA run with known factual/sequence defects and a clean control deck, alongside deterministic coverage/failure tests. Document misses as unresolved quality issues rather than hiding them behind an aggregate pass rate.
- Confirm QA artifacts are removed in checkpoint B's lifecycle tests and a QA budget/timeout failure never bypasses the download gate.

## 8. Phase 5 — Optional generated pictures

GPT-6 Luna accepts images and can invoke an image-generation tool, but image output is produced by a separate image model. The current adapter does not implement that tool. Keep Luna as the main model and keep picture generation disabled until a dedicated backend and budget are configured. See the [Luna capabilities](https://developers.openai.com/api/docs/models/gpt-6-luna) and [image-generation API guide](https://developers.openai.com/api/docs/guides/image-generation).

- Add an `ImageGenerator` adapter and capability status, independent of text-model roles. Do not automatically switch the primary model or silently enable a paid image tool.
- During content planning, mark optional illustrative image requests. When enabled, generate a bounded number with explicit quality/size settings and cumulative budget controls; store prompts and output only in the temporary workspace.
- Insert returned image bytes with correct crop, aspect ratio, alt text, and provenance identifying them as generated illustrations. Review the actual rendered placement.
- Never use invented pictures as documentary evidence or substitute them for factual charts/source diagrams. Use native charts and source figures for those tasks.
- If disabled or unsuccessful, recompose using native shapes, source figures, or a text layout, then rerun verification. An unresolved required source figure remains a blocking problem; optional decoration does not.

**Checkpoint E:** disabled mode completes with zero image-generation calls; enabled mode respects budget, handles failures without broken placeholders, renders correctly, and deletes prompts/image bytes on completion. This phase may be deferred without blocking Phases 1–4 and 6.

## 9. Implementation map and API contracts

Exact module splits can change during implementation; responsibilities and boundaries should remain clear.

| Location | Planned work |
|---|---|
| `backend/app/auth/`, `users/`, `db/` (new) | Identity adapter, sessions, authorization, administration, migrations |
| `backend/app/jobs/` (new), `sessions.py`, `main.py` | Ownership, workspace lifecycle, leases, cancellation, cleanup retries/startup reconciliation |
| `backend/app/api.py` | Protect legacy routes; creation/outline/admin/lifecycle routes; secure preview and download |
| `backend/app/authoring/` (new) | Schemas, outline generation, content authoring, PDF extraction/provenance, native composition |
| `backend/app/authoring/graphics/` (new) | Native chart construction, restricted function parsing, numerical sampling, plot/equation rendering, source/data manifests |
| `backend/app/ai/providers.py`, `pipeline.py` | Additional text roles, usage limits, authoring orchestration, optional image adapter |
| `backend/app/ai/output_qa/` (new) | Separate reviewer prompt/schema, ordered screenshot batches, review ledger, deck-wide sequence/accuracy synthesis |
| `backend/app/generations.py`, `qa/` | Workflow-specific verification profiles and extended candidate identity |
| `backend/app/rendering.py` | Job-scoped renderer artifacts, timeouts, process cancellation and cleanup |
| `backend/app/benchmark.py`, content-learning hooks | Remove persistent capture from product routes and workflows |
| `frontend/src/` | Login/admin screens; two post-login entries; separate authoring route; adaptive length selector; outline editor; PDF evidence; ordered QA progress; finish/delete controls |
| `tests/backend/`, frontend tests, browser checks | Authorization, lifecycle, authoring, PDF, and release-gate regression coverage |
| `.env.example`, `.gitignore`, docs | Nonsecret settings, ignored account databases/workspaces, setup and lifecycle documentation |

Proposed API families:

- `/auth/login`, `/auth/callback`, `/auth/logout`, `/api/me`; `/api/admin/users` and invitations.
- `POST /api/jobs` with mode/settings and `length_preference` for new authoring; job-scoped input upload, extraction status, and creation status. The proposed count is planner output, not a required fixed-number request field.
- `GET/PUT /api/jobs/{id}/outline` with expected revision; `POST .../outline/approve` binds approval to that revision.
- `POST .../generate`, job-scoped previews/findings/review/download, and output-QA status/coverage; all bind to current candidate and ordered render identity.
- `POST .../cancel`, `POST .../finalize`, and idempotent delete; return lifecycle/deletion status without claiming completion before verification.

Retain existing reformat endpoints during migration, backed by the same ownership/lifecycle services. No legacy URL may bypass authorization or expiry. Make outline approval, generation initiation, finalization, and retries safe against duplicate requests and concurrent tabs.

## 10. Phase 6 — Integrated acceptance and release checkpoint

Implementation order: **Phase 1 -> Phase 2 -> Phase 3 -> Phase 4 -> shared output-QA pipeline/checkpoint Q -> Phase 6**. Define the output-QA contracts during Phase 3 so both existing and new workflows integrate with them. Phase 5 is optional. Define shared job/identity/manifest contracts first so new generation does not create a second storage or review system.

The last audited baseline was 94 passing backend tests, 16 frontend tests, 3 browser checks, and a successful production frontend build. These are historical baseline results, not tests of this proposed work. Re-run relevant suites after implementation and expand them with the checkpoints above.

The core release is complete only when:

- [ ] Real-provider login, account administration, and cross-user isolation pass checkpoint A.
- [ ] Every supported terminal path has verified cleanup, including file-lock/crash recovery, and passes checkpoint B.
- [ ] Topic/outline authoring produces an editable, reviewed PPTX and passes checkpoint C.
- [ ] Post-login routing offers Use my PowerPoint and Generate a new presentation; adaptive length selection chooses count automatically and never silently omits required material.
- [ ] Native charts, scientific plots, function plots, and mathematical expressions pass checkpoint C-math; they work with optional AI pictures disabled.
- [ ] PDF authoring passes checkpoint D with documented held-out evidence.
- [ ] The separate output-QA agent pipeline passes checkpoint Q with complete ordered screenshot coverage, deck-wide sequence review, and evidence-based accuracy findings on all three workflows.
- [ ] Existing reformatting, alignment, preservation, page findings, selected approvals, navigation, and verified-download checks still pass.
- [ ] A small live Luna acceptance run covers topic authoring, PDF authoring, and existing PPTX redesign with actual rendering and review. Mocked model responses and a successful connection test alone are insufficient.
- [ ] Test artifacts remain synthetic or explicitly managed development evidence; production jobs retain no deck content after closure.
- [ ] The UI accurately distinguishes verified, needs-review, failed, expired, and deletion-pending states; unavailable rendering/model services cannot produce a false verified result.
- [ ] Git checks confirm `backend/.env`, local identity databases, temporary documents, images, and generated artifacts are ignored and untracked; examples contain no secrets.
- [ ] Setup documentation explains identity configuration, initial admin provisioning, processing limits, renderer requirements, cleanup guarantees, and optional image status.

## 11. Input needed from the user

Resolved by the user: use invitation codes now, bootstrap the administrator with code `admin`, and allow administrators to create new member codes. Google SSO can be configured later. No identity-provider credentials are needed to use the current build. Future Google client secrets must be entered into ignored environment configuration, never pasted into the plan or committed.

No additional OpenAI key is needed for the planned Luna text/vision workflow if the existing key remains valid. Image generation stays deferred/off by default; enabling it later requires an image-model choice and spending limit. No Vercel configuration is needed for this implementation plan.
