# Stevens Slide Studio

A local FastAPI + React application that applies the selected CPE or Stevens template locally, then runs structural, content and ordered AI output QA. New presentations can also be authored from a topic, outline, or PDF using AI. Completed artifacts are downloadable even when QA reports findings or failures; the original QA verdict remains visible.

Choose a format before uploading or planning a new deck. The bundled sources are `backend/assets/CPE_template.potx` and `backend/assets/stevens_template.pptx`. Each job keeps its own template selection, layout geometry, AI references and release fingerprint. The POTX is converted to a presentation package in a local cache without modifying its source artwork.

Sign in → choose Use my PowerPoint or Generate a new presentation → review/approve → generate and verify → inspect findings → download and finish. Downloads require completed processing and an unchanged artifact. Findings need review but do not block downloading. Authentication, ownership, freshness and identity checks apply to every download, including legacy draft requests.

## Project layout

```text
backend/       FastAPI app, slide engine, shared utilities, template
frontend/      React app and browser tests
tests/         Backend regression tests and synthetic fixtures
tools/         Verification commands
docs/          Architecture and verification checkpoints
.github/       Continuous integration
```

Current reconciled decisions and provenance: [handover](docs/HANDOVER.md). Developer permissions and activity: [developer activity](docs/DEVELOPER_ACTIVITY.md).

See [architecture](docs/ARCHITECTURE.md) and [verification checkpoints](docs/VERIFICATION.md). Private decks, past evidence and retained implementation history live in the ignored `.local/` folder. They are not required to run the app.

Current implementation results and limits: [implementation verification](docs/IMPLEMENTATION_VERIFICATION.md). Run the complete local verification with `powershell -NoProfile -File tools/verify.ps1`. After building, `powershell -NoProfile -File tools/start.ps1` starts the application in the background using the project's local API credential.

## Windows setup

Tested with Python 3.12 and Node 22. Vite 8 requires a supported recent Node version (22.12 or later on the Node 22 line). Install LibreOffice, or use an installed Windows Microsoft PowerPoint. Rendering is required for previews and PDF exports. The Windows launcher selects the portable LibreOffice installation under `.local/tools/libreoffice` when present. Arial must be available; substitutions are reported.

Run from the repository root in PowerShell:

```powershell
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r backend/requirements-lock.txt
npm --prefix frontend ci
npm --prefix frontend run build
.venv/Scripts/python.exe -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
```

Open http://127.0.0.1:8000. Use one server worker: sessions are process-local. For frontend development, run `npm --prefix frontend run dev` and open port 5173 while the backend runs on port 8000. On other platforms use the equivalent virtual-environment executable and LibreOffice.

Development policy: do not introduce spending, cumulative request, or cumulative token budget limits. `tools/start.ps1` explicitly forces `STEVENS_AI_MAX_CALLS=0` and `STEVENS_AI_MAX_TOKENS=0`, overriding inherited deployment settings. Keep those values at zero when launching the backend directly. Provider-side budgets are managed separately by the account owner; this launcher cannot change a Vercel API-key budget.

## What verification means

Each generation has a unique directory, source/candidate/template hashes, revision version, policy version, check results, and scoped review decisions. Four required checks cover the placement plan, reopened exported content, structural formatting, and fresh PDF/PNG rendering. AI mode additionally requires a valid AI redesign and a completed visual review of every output slide. A separate output-QA agent reviews every output screenshot in presentation order, followed by deck-wide sequence and source-based accuracy review. Final download rechecks identity and returns the exact checked bytes. Permanent benchmark capture is disabled.

QA failures, missing checks, content warnings and uncertain formatting remain visible for inspection. Completed artifacts can be downloaded without accepting those findings. Missing artifacts, unfinished processing, changed files and stale revisions still block downloads. Human decisions record acceptance without rewriting the QA verdict.

## Supported behavior and limits

- Native text, images/crops, tables (including merges), groups, connectors, standard editable charts and workbook dependencies, speaker notes, and external/internal hyperlinks are preserved and independently checked. Column, line, and pie charts have regression fixtures.
- Source runs retain emphasis; supported inherited properties and source theme colors are materialized. Arial, title size, minimum body size, and approved red/neutral text rules are applied. The current builder favors native preservation over reconstructing arbitrary diagrams.
- A single text body can split at paragraph boundaries. A table with its title can split at row boundaries with a repeated header, provided no vertical merge crosses the split. Notes remain on the first output slide; internal links target the first mapped output slide.
- Native charts retain their effective source theme, including default series colors; the content audit checks that theme as well as chart data. Table resizing updates row heights and column widths together with the frame. Generated opening/closing body text is measured to fit its template region at 16–20 pt; text that cannot fit readably is rejected rather than truncated.
- Preservation reflow is bounded to three measured attempts and rolls back regressions. AI mode adds model-proposed geometry, font sizing, and approved text colors, followed by mandatory final-QA repair cycles while the candidate improves and upload budget/time remain. The legacy zero-to-two initial repair setting cannot disable final QA. Free-text notes guide AI layout/style decisions; the model cannot rewrite source wording, add/remove objects, alter chart data, or change links/notes. Arbitrary mixed-layout and single-paragraph overflow are not guaranteed to be solved.
- Source artwork and institutional logos are retained conservatively, which can duplicate template decoration. Complex layouts, chart typography, color semantics, gradients, table-style inheritance, and overlapping objects may require manual review. This is not full accessibility certification or a promise that arbitrary decks need no manual layout work.
- SmartArt, OLE/embedded objects, media, animations, unsupported graphic frames, and image slide backgrounds are explicitly blocked. Generated slide-number fields have a narrow, recorded template-policy exclusion; ordinary dates, citations, footnotes, and repeated text do not.

## AI setup and retention

Create `backend/.env` from `.env.example` if it does not exist. Enter `OPENAI_API_KEY` locally; never paste credentials into the application or commit the file. The current configuration uses **GPT-6 Luna through the direct OpenAI API for redesign, generation, and QA**:

```dotenv
OPENAI_API_KEY=
STEVENS_AI_PROVIDER=openai
STEVENS_AI_REDESIGNER=openai
STEVENS_AI_GENERATOR=openai
STEVENS_AI_REVIEWER=openai
STEVENS_AI_REDESIGNER_MODEL=gpt-6-luna
STEVENS_AI_GENERATOR_MODEL=gpt-6-luna
STEVENS_AI_REVIEWER_MODEL=gpt-6-luna
OPENAI_REASONING_EFFORT=none
OPENAI_REVIEW_REASONING_EFFORT=low
```

Keep workflow provider overrides (`STEVENS_AI_REDESIGNER`, `STEVENS_AI_GENERATOR`, `STEVENS_AI_REVIEWER`) set to `openai`; these override the shared provider and legacy planner settings. Models can be changed without code; workflow model settings override legacy planner settings and the shared `STEVENS_AI_MODEL`. Generation covers extraction, outlines, visual planning, authoring and authoring repairs; redesign covers source decisions, layout and redesign repairs. Nonempty process environment settings override matching `.env` entries. **Refresh AI configuration** shows all three assignments; **Test AI connection** tests each role. Alternative deployment settings are documented in [Gateway configuration](docs/AI_GATEWAY.md).

All current workflows use the local OpenAI key, with separate calls for authoring and review; no Vercel Gateway is used. Other provider adapters remain available for a future explicit configuration change. Avoid `auto` for an OpenAI-only deployment because it can select another configured provider. Requests use strict JSON schemas, high-detail slide images and bounded timeouts/tokens. API failures, refusals and incomplete responses block verification; the app never silently switches models after an error.

Select **Generate and verify**. This sends slide text, layout instructions, original previews when available, and generated slide images to the displayed providers. Invalid responses, quota/authentication failures, missing required checks, and content damage block AI verification. Repairs are accepted only when the combined checks improve without increasing deterministic blocking defects. Source words, emphasis, editable objects, charts, links, and notes are independently checked after edits. Visual AI judgment can still be wrong; unresolved review findings need inspection.

Uploaded presentations default to **Format + QA**: native template composition followed by ordered AI output review. The public generation API defaults to `preserve`; explicit `ai` requests retain the redesign workflow. Idea/PDF authoring still uses AI. Cumulative request/token limits are zero/unlimited in the local launcher; per-request timeouts and bounded retries remain. Missing provider access produces visible QA errors, while completed local artifacts remain downloadable. No automatic provider switching occurs.

After generation, review navigation follows every output slide in order, including each split part and the added closing. Split parts share their source preview and revision instructions. Added slides show a no-original placeholder; findings follow the selected output. Before generation, navigation follows source slides.

Processing workspaces expire after one hour without meaningful user activity and at an absolute four-hour deadline. Polling does not keep files alive. Finish/cancel/logout and account deactivation revoke access and request deletion; active operations hold file leases until their bounded work returns. Failed filesystem deletions remain pending and are retried. Startup reconciles orphaned workspaces, respecting another live process's ownership. Account metadata stays outside the repository by default, separately from temporary presentation content. The renderer uses job-scoped temporary directories; operating-system/Office recovery caches are outside the application's deletion guarantee. No application timer can erase a powered-off machine's disk.

**Download and finish** retrieves the bytes before asking the server to delete the job. Interrupted downloads have a ten-minute retry window within the absolute deadline. Downloads retained on the user's device are not deleted. `store=false` does not establish zero provider-side retention; see OpenAI's data controls. Explicit verification-tool evidence is synthetic development material in ignored `.local/verification`, not product retention.

## Accounts and new-deck generation

Invitation-code sign-in is enabled by default. On first startup, the administrator code is **admin**, as requested. Open **Manage users** to create separate account-bound codes, change roles, deactivate accounts, replace codes, and remove inactive accounts. Codes are shown once when created; only hashes are stored. Replacing a code revokes that account's existing logins. The last active administrator cannot be removed. Each code should belong to one person; it signs back into that account until revoked. No email or Google credentials are needed for this mode.

`STEVENS_AUTH_DB` optionally sets the account SQLite path; the default is `%LOCALAPPDATA%/StevensSlideStudio/accounts.sqlite3`. This stores account metadata, hashed codes/sessions and schema version, never decks. `STEVENS_ADMIN_CODE` only controls first bootstrap, not an existing account's code. Google OIDC support is retained for later configuration in `.env.example`; it has not been verified with a real Google tenant and is not required for invitation sign-in.

After login:

- **Use my PowerPoint** opens the existing preservation/redesign workflow.
- **Generate a new presentation** accepts a topic/outline or PDF, audience, and **Auto / Brief / Standard / Detailed** length selection. The planner chooses the count, up to the current 30-slide resource ceiling. Users can edit/reorder/add/remove outline slides and must approve before generation.
- Creation composes native text, editable supported charts/tables, speaker notes, function/scientific plots, and rendered mathematical expressions. Plot expressions use an allowlisted mathematical parser; model-produced Python is never executed. Equations use Matplotlib mathtext, with unsupported syntax rejected. Plots/equations are high-resolution image objects with their source specifications preserved in notes, not native editable Office equations.
- PDF input supports text-layer and scanned documents using local extraction and bounded vision transcription. Original page references and exact source quotations are checked. PDF source figures currently use rendered source pages; specialized figure-only cropping remains a future improvement.
- Content/chart/formula edits create a new candidate and rerun all gates. A bounded visual repair pass can address QA findings; unresolved problems stay visible even when the completed artifact is downloadable. Changes to the outline require fresh approval.
- Generated pictures are disabled for this release. Charts, plots, equations, native tables and source-page illustrations do not need an image-generation model.

Limits: one PDF per job, 50 MB, 100 pages, 220,000 extracted characters, bounded per-page text and job budgets. New authoring is designed around one major visual per slide. Use one server worker; job state is process-local and not resumed after a restart. Structural checks and the QA agent are evidence, not guarantees of factual truth. Unsupported claims remain review findings; existing source content is not silently fact-corrected.


## Verification commands

```powershell
New-Item -ItemType Directory .local/verification -Force | Out-Null
Push-Location frontend
npx vitest run
Pop-Location
npm --prefix frontend run build
.venv/Scripts/python.exe -m pytest -q --basetemp=.local/verification/pytest-local
.venv/Scripts/python.exe tools/create_test_fixture.py
npm --prefix frontend run test:e2e
```

Browser tests require the running application with `STEVENS_OFFLINE=1`, invitation-code sign-in, and locally installed Chrome. Use `tools/start_verification_server.ps1` for an isolated synthetic server on port 8001 and set `STEVENS_TEST_URL=http://127.0.0.1:8001` when running Playwright. CI installs Chromium and LibreOffice. Use a fresh pytest temporary directory on subsequent runs in restricted environments. Private corpus inputs default to `.local/private`; use `--corpus-root PATH` for another location. The private corpus command is `python tools/run_acceptance.py --output .local/verification/new-run --render`; its output directory must be new. No private decks are uploaded by CI.

Build the frontend before backend HTTP tests: a clean checkout does not contain `frontend/dist`. Windows LibreOffice rendering uses its `soffice.com` console launcher when available, with an isolated headless profile in the short system temporary directory for conversion and version detection. Nesting the profile under long checkout/test paths can silently prevent Windows LibreOffice from producing a PDF. Set `STEVENS_SOFFICE` to an explicit console executable to reproduce CI locally; CI pins LibreOffice 26.2.6 and exercises real renders. The complete CI suite includes real render tests; a non-renderer-only local test pass is not equivalent to a passing CI run.

After configuring keys, run the live checkpoint with a **new** output directory:

```powershell
.venv/Scripts/python.exe tools/run_ai_smoke.py --live --output .local/verification/ai-live-01
```

This sends only a generated synthetic slide, keeps the source/candidate/renders/report locally, and does not approve findings automatically. Exit 0 means ready, 2 means missing keys, and 3 means review or repair is still required. Use `--mock-providers` instead of `--live` to exercise edits and real rendering without API calls; that mode does not validate model quality.

Additional explicit live checks (synthetic content only):

```powershell
.venv/Scripts/python.exe tools/verify_authoring.py --live --output .local/verification/authoring-live-new
.venv/Scripts/python.exe tools/verify_authoring.py --live --cases scanned --output .local/verification/scanned-live-new
.venv/Scripts/python.exe tools/verify_output_qa.py --live --output .local/verification/qa-challenge-new
```

Authoring exit 0 means all required checks completed without blocking defects; a `needs_review` result remains visible for inspection, while completed artifacts are downloadable. The QA challenge must detect an intentionally incorrect number and slide sequence. These commands never automatically approve human findings and verify removal of their application workspace. Their selected synthetic evidence remains in the requested development output folder.

## Code map

| Path | Responsibility |
|---|---|
| `backend/slide_engine/inventory.py`, `preserve.py`, `text_style.py`, `repair.py` | Source inventory, native emission, source styles, bounded repair |
| `backend/app/generations.py` | Generation identity and release decisions |
| `backend/app/qa/` | Artifact, formatting, render and optional AI checks |
| `backend/app/ai/` | Provider adapters, constrained native layout edits, visual review and bounded repair |
| `backend/app/api.py`, `sessions.py` | Workflow and session lifecycle |
| `frontend/src/App.tsx` | Active review workflow |
| `tests/backend`, frontend tests and `e2e` | Regression and browser verification |
| `.github/workflows/verify.yml` | Renderer-equipped CI workflow |

Brand constants are in `app/brand.py`: they follow the shipped template theme rather than older palette images. Analysis helpers retained by the active app do not authorize release through the API.

## Git and local credentials

The root `.gitignore` excludes `.env` files at every depth, local overrides, private decks, `.local`, dependencies, caches and build output. Only the empty `backend/.env.example` is intended for source control. Keep your API key in `backend/.env`; it is loaded by the backend and never bundled into the frontend.

The repository uses the `main` branch. Configure your own `origin` remote before pushing. `git check-ignore -v backend/.env` should report the ignore rule. Do not force-add ignored credentials. If importing existing history, check that it never tracked a key; ignore rules do not remove past commits.


### PDF redesign and export

Use **Use my PowerPoint or PDF** for content-preserving redesign. Text-based PDFs (up to 100 pages and 60 MB upload size) become editable text plus source graphic regions; plots and equations retain their visual content. Rasterized graphics are not editable chart data. Scanned pages require OCR first; interactive forms and annotations must be flattened. Original page screenshots are used for paired QA. PowerPoint and PDF downloads share completion, ownership and identity checks. Either download finishes the session. The UI has no draft bypass; legacy `draft=true` requests enforce the identical checks.

AI transport failures and malformed response JSON retry once, with a configurable `STEVENS_AI_REQUEST_TIMEOUT` (default 180 seconds, maximum 300). Existing call/token limits apply cumulatively to the upload, including retries and output QA. The UI reports these totals. Ordered output QA runs independently of earlier planner or visual-agent errors whenever its candidate/render validation succeeds. Rejected repairs retain the previous candidate and visible findings; completed artifacts remain downloadable. Request and token reserves protect ordered QA from earlier stages; admission estimates include input, images and output allowance without increasing an explicitly configured upload cap. Cumulative token and request limits default to unlimited for both redesign and generation; positive environment values opt into caps. Provider limits and incomplete rendering remain visible as QA failures; a PDF export requires an intact render. QA activity shows reviewed slides, request count and any incomplete-review reason. Validated source decisions are cached only in the temporary processing session and invalidated by source, instructions, model configuration, policy or repair feedback.

Run `python tools/verify_pdf_redesign.py --live --output .local/verification/pdf-live-new` for an opt-in synthetic PDF -> AI redesign -> PowerPoint render -> full QA check; it incurs configured API usage and never reads private course files.


Completed visual/output QA findings can be accepted after human review with a nonempty reason. Decisions are bound to the generation and candidate hash and do not rewrite the AI verdict. QA is advisory for downloading; completion, ownership and file identity remain enforced. Explicit AI redesign may attempt targeted repairs, while the default local workflow does not enter the per-slide redesign/repair pipeline. PDF composition preserves font proportions, native first-page layout and extracted title.


New-deck outlines include editable opening and closing slides within the adaptive slide count. Approve the outline in step 1 to enable generation in step 2; edits require approval again. Opening and closing positions are protected. Native composition uses mostly red `Title Slide` for opening and statue-photo `1_Title Slide` for closing, replaces closing sample text without changing its artwork, and audits the resulting layouts. Run `python tools/verify_bookends_qa.py --live --output .local/verification/bookends-new` for a synthetic native-render and live-QA acceptance check; success requires actual download eligibility.

Review controls: finding text and slide links navigate to every affected output (including split and added slides). Use **Show all slide findings** to review other pages. **Dismiss all findings for slide N** records an acceptance reason for every finding on that output slide, including hidden suggestions. Multi-slide findings remain open on other affected slides; **Show human-reviewed findings** restores its display. Corrections use one text prompt. **Download** opens a PowerPoint/PDF choice and closes the processing session after export.

Finding priorities are derived from QA materiality: blocking/review = high; cosmetic warning = low. Only high-priority findings appear initially. Low-priority suggestions can be shown and do not block a completed review. Slide acceptances are scoped to the generated artifact; API, rendering, and incomplete-QA errors cannot be waived. Vercel HTTP 402 is reported as a provider billing error, with a specific API-key budget message when available, and is not automatically retried. App request/token caps and Vercel team/key budgets are separate.
