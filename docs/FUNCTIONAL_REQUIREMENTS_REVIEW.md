# Functional requirements review

Reviewed September 24, 2026 against the supplied requirement for presentation generation, reformatting, alignment, user management, and files used only for processing without retention. Vercel deployment and Vercel AI Gateway are explicitly excluded from this review.

Source baseline: commit `82a22a5`, branch `reviewed`. Application code was not changed during this audit.

**Historical audit:** the findings below describe the pre-implementation baseline. The subsequent build adds invitation-code accounts, processing cleanup, authoring, and ordered output QA; see [implementation verification](IMPLEMENTATION_VERIFICATION.md) for the current result and limits. Google SSO and generated pictures are deferred by the user's later instructions.

## Conclusion

The uploaded-PowerPoint redesign and review workflow is implemented and tested. The application is **not yet functionally complete against the supplied requirements**: user management is absent, and the current retention behavior conflicts with the stated requirement. Creating new presentations from a topic, outline, or PDF is also absent and is now confirmed as required. The follow-up [implementation plan](IMPLEMENTATION_PLAN.md) covers these gaps with verification checkpoints; optional picture generation may be deferred.

## Requirement mapping

| Requirement | Current status | Evidence and limits |
|---|---|---|
| Presentation generation | Partial / new-deck authoring confirmed missing | `backend/app/api.py` accepts a PPTX upload, then generates a redesigned output through `generations.build`. There is no topic/outline/PDF authoring flow or new-deck generation route. The AI is deliberately prohibited from inventing or rewriting source content. Exporting a redesigned uploaded deck is supported. |
| Reformatting | Implemented for supported objects | `backend/slide_engine/preserve.py`, `text_style.py`, and `backend/app/ai/layout.py` apply the Stevens template, font/color/size policy, native object edits, and supported text/table splitting. SmartArt, embedded objects, media, animations and other documented unsupported content are blocked. |
| Alignment | Implemented as automatic/AI-assisted layout | The planner proposes object coordinates and sizes, checked against object coverage, bounds, aspect ratios and rendering. There is no direct on-canvas editor or dedicated left/center/right/distribute toolbar. Those controls are additional scope only if manual alignment is intended. |
| Review and verification | Implemented | Independent artifact checks, real rendering, visual AI review, bounded repairs, page-filtered findings, selected batch approvals, previous/next navigation and identity-checked download. Passing automated checks does not guarantee every real deck needs no human review. |
| User management | Missing | No login/logout, account provisioning, user records, account administration, or user ownership checks. Processing sessions are not authenticated user sessions. API access is based on possession of a session ID. |
| Files used only for processing; no retention | Not met | Source PPTX, rendered PDF/PNG, candidates, revisions and generation reports are written to disk. Sessions expire after one idle hour; a download does not delete them. Approved benchmarks are saved indefinitely under `backend/learning`. |

## Confirmed gaps and recommended implementation

### 1. User accounts and access control

The API's `session(sid)` helper checks that a processing session exists, without checking a signed-in user. Two separate anonymous test clients successfully read the same synthetic processing session when given its ID; both received HTTP 200. The API schema declares no authentication security scheme. This probe used only synthetic state and did not read another user's actual deck.

Recommended minimum: authenticated sign-in/out, account provisioning, member/admin roles, invite/deactivate controls, and server-enforced ownership on session metadata, previews, revision edits, generation, review decisions, downloads and deletion. A random session URL is not a substitute for ownership checks.

Checkpoint: anonymous protected requests return 401; user B cannot read, change, download or delete user A's presentation even with its exact IDs; a deactivated account cannot continue using an old login; admins can manage membership through a usable interface.

### 2. Processing-only file lifecycle

`backend/app/sessions.py` uses a 3,600-second idle expiry and best-effort deletion (`ignore_errors=True`). `backend/app/main.py` runs cleanup periodically while the process is alive. `backend/app/api.py` serves downloads without ending the session. `backend/app/benchmark.py` writes a permanent deck copy and benchmark log, with an active **Save approved benchmark** UI/API path. Git ignore rules protect commits; they do not delete retained files.

Recommended minimum: remove or disable permanent benchmark capture in the user-facing product; keep uploaded content only in an isolated temporary processing workspace; add a clear finish/cancel-and-delete lifecycle; enforce bounded expiry and cleanup on successful completion, failure, abandoned sessions, restart and shutdown; verify and retry failed deletion without logging slide content. Do not retain slide text, images, filenames or full generation reports in permanent application logs or backups. Existing development evidence/private files require a separate deliberate cleanup decision; this review does not delete them.

Temporary files required for rendering and interactive review need an explicit lifetime. If the requirement means absolutely no disk writes even during processing, the current PowerPoint/LibreOffice rendering design does not satisfy it and needs a different processing architecture. Recommended interpretation: temporary processing/review files are allowed, but no permanent retention after the workflow ends.

Checkpoint: enumerate all processing artifacts after success, explicit finish, cancellation, timeout, simulated errors, renderer failures and restart; verify the workspace is removed and cannot be read through the API. Confirm benchmark persistence is inaccessible in the product. Test deletion failures rather than merely checking that a delete method was called.

The OpenAI adapter sends `store=false`; provider-side retention was not verified by this audit. Gateway integration remains out of scope here.

### 3. Presentation generation scope

The user confirmed that generation means creating a new presentation: separate topic/outline input, audience and slide-count settings, editable outline approval, new slide content generation, native PPTX composition, and the same rendering/review/download gate. Planning and generating a deck from an uploaded PDF are also required. Generated pictures are optional and may be deferred. Keep new authoring separate from preservation mode, where source wording must remain immutable.

The user also confirmed required support for plots, charts, mathematical expressions, and function plots. Existing supported-chart preservation does not establish new chart/plot/math authoring. The implementation plan includes deterministic rendering, native editable charts where supported, source/formula checks, and a dedicated mathematics/plotting acceptance checkpoint; these are core scope independent of optional AI picture generation.

Subsequent scope refinements: after login, users choose **Use my PowerPoint** (the existing preservation workflow) or **Generate a new presentation** (a separate topic/outline/PDF authoring entry). New authoring uses an automatic length selection rather than a fixed slide-number input; the planner proposes a count for outline approval. A separate output-QA agent pipeline must inspect every output screenshot in actual presentation order, review narrative sequence and accuracy against source evidence, and gate the final download. This additional pipeline is planned, not established by the existing slide-level visual-review tests.

Checkpoint: start with no uploaded deck, provide a topic/outline, inspect/edit and approve the proposed slides, generate an editable PPTX, and complete verification and download. Repeat with a PDF, checking source grounding and page references. Follow the detailed acceptance gates in the [implementation plan](IMPLEMENTATION_PLAN.md).

## Verification performed

- Backend suite: **94 passed**, including two actual PowerPoint renderer tests.
- Frontend component suite: **16 passed**.
- Production frontend build: **passed**.
- Browser workflow checks: **3 passed** (upload/review/download, failed revision saves, split-slide mapping and stale-download rejection).
- Anonymous cross-client synthetic session probe: confirmed HTTP 200 from both clients, documenting the missing ownership boundary.
- Previous live GPT-6 Luna synthetic checkpoint is documented in `VERIFICATION.md`; no new provider calls were needed for this requirements audit.

Passing tests validate implemented behavior. They do not establish that missing account management, new-deck authoring or stricter retention requirements have been implemented.
