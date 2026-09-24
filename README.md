# Stevens Slide Studio

A local FastAPI + React application that uses AI to redesign supported PowerPoint objects on the shipped Stevens template, then verifies content and rendered output before offering a final download. A preservation-only mode is available without API keys.

Upload → review source → save corrections → generate and verify → inspect findings → download. An explicit **unverified draft** remains available when a candidate exists but has not passed the release gate.

## Project layout

```text
backend/       FastAPI app, slide engine, shared utilities, template
frontend/      React app and browser tests
tests/         Backend regression tests and synthetic fixtures
tools/         Verification commands
docs/          Architecture and verification checkpoints
.github/       Continuous integration
```

See [architecture](docs/ARCHITECTURE.md) and [verification checkpoints](docs/VERIFICATION.md). Private decks, past evidence and retained implementation history live in the ignored `.local/` folder. They are not required to run the app.

## Windows setup

Tested with Python 3.12 and Node 22. Vite 8 requires a supported recent Node version (22.12 or later on the Node 22 line). Install LibreOffice, or use an installed Windows Microsoft PowerPoint. Actual rendering is required for verified final downloads. Arial must be available; substitutions are reported.

Run from the repository root in PowerShell:

```powershell
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r backend/requirements-lock.txt
npm --prefix frontend ci
npm --prefix frontend run build
.venv/Scripts/python.exe -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
```

Open http://127.0.0.1:8000. Use one server worker: sessions are process-local. For frontend development, run `npm --prefix frontend run dev` and open port 5173 while the backend runs on port 8000. On other platforms use the equivalent virtual-environment executable and LibreOffice.

## What verification means

Each generation has a unique directory, source/candidate/template hashes, revision version, policy version, check results, and scoped review decisions. Four required checks cover the placement plan, reopened exported content, structural formatting, and fresh PDF/PNG rendering. AI mode additionally requires a valid AI redesign and a completed visual review of every output slide. Final download and benchmark capture recheck identity on the server and return the exact checked bytes.

Missing content, unsupported required objects, failed checks, or changed files block final release. Uncertain formatting, chart appearance, inherited table styles, and text visibly extending beyond its intended box require inspection. A reviewer can resolve specific review findings with a rationale; required failures cannot be waived. Optional AI failures are never a clean result.

## Supported behavior and limits

- Native text, images/crops, tables (including merges), groups, connectors, standard editable charts and workbook dependencies, speaker notes, and external/internal hyperlinks are preserved and independently checked. Column, line, and pie charts have regression fixtures.
- Source runs retain emphasis; supported inherited properties and source theme colors are materialized. Arial, title size, minimum body size, and approved red/neutral text rules are applied. The current builder favors native preservation over reconstructing arbitrary diagrams.
- A single text body can split at paragraph boundaries. A table with its title can split at row boundaries with a repeated header, provided no vertical merge crosses the split. Notes remain on the first output slide; internal links target the first mapped output slide.
- Preservation reflow is bounded to three measured attempts and rolls back regressions. AI mode adds model-proposed geometry, font sizing, and approved text colors, followed by one repair pass in the UI (API permits zero to two). Free-text notes guide AI layout/style decisions; the model cannot rewrite source wording, add/remove objects, alter chart data, or change links/notes. Arbitrary mixed-layout and single-paragraph overflow are not guaranteed to be solved.
- Source artwork and institutional logos are retained conservatively, which can duplicate template decoration. Complex layouts, chart typography, color semantics, gradients, table-style inheritance, and overlapping objects may require manual review. This is not full accessibility certification or a promise that arbitrary decks need no manual layout work.
- SmartArt, OLE/embedded objects, media, animations, unsupported graphic frames, and image slide backgrounds are explicitly blocked. Generated slide-number fields have a narrow, recorded template-policy exclusion; ordinary dates, citations, footnotes, and repeated text do not.

## AI setup and retention

Create `backend/.env` from `.env.example` if it does not exist. Enter `OPENAI_API_KEY` locally; never paste it into the application or commit the file. Both planning and visual review use **`gpt-6-luna`** through the OpenAI Responses API. Account/model access must be confirmed through **Test AI connection**. The local configuration is:

```dotenv
OPENAI_API_KEY=
OPENAI_MODEL=gpt-6-luna
OPENAI_REASONING_EFFORT=none
STEVENS_AI_PLANNER=openai
STEVENS_AI_REVIEWER=openai
```

`none` avoids a hidden reasoning budget for development checks; the model still receives the full object inventory and high-detail slide images. Responses use strict JSON schemas, bounded output tokens, standard service tier, and `store=false`. API failures and refusals block verification; no automatic provider or model fallback occurs.

One OpenAI key supplies both roles, in separate calls. The UI states that the same provider performs planning and review. The Anthropic and Gemini adapters remain available only when selected through `STEVENS_AI_PLANNER` / `STEVENS_AI_REVIEWER`. Supported choices are `openai`, `anthropic`, `gemini`, and `auto`; explicit `auto` prefers a configured OpenAI key, then legacy providers. Nonempty process environment settings override `.env`. Use **Refresh AI configuration** after editing the file; a server restart is unnecessary for key changes.

Select **AI redesign + full check**, then **Generate and verify**. This sends slide text, layout instructions, original previews when available, and generated slide images to the displayed providers. Invalid responses, quota/authentication failures, missing required checks, and content damage block AI verification. Repairs are accepted only when the combined checks improve without increasing deterministic blocking defects. Source words, emphasis, editable objects, charts, links, and notes are independently checked after edits. Visual AI judgment can still be wrong; unresolved review findings need inspection.

`STEVENS_AI_MAX_CALLS=160` bounds provider requests per generation; request timeouts also apply. There is no automatic model escalation or benchmark learning. `STEVENS_OFFLINE=1` disables providers. The preservation mode needs no keys; its optional per-slide check uses the configured reviewer, also GPT-6 Luna by default. The old atom-reconstruction Claude planner is not used by the new native-object AI pipeline.

Temporary sessions expire after one idle hour, with active jobs protected. Restarting the single-process server loses session lookup state; expired orphan directories are cleaned on subsequent startup. Start a new deck requests deletion of the old session. Explicitly saved approved benchmarks persist under `backend/learning`; saving does not train or automatically change the builder. There is no benchmark deletion toggle. Detailed verification artifacts contain deck text and should stay local.

## Verification commands

```powershell
New-Item -ItemType Directory .local/verification -Force | Out-Null
.venv/Scripts/python.exe -m pytest -q --basetemp=.local/verification/pytest-local
Push-Location frontend
npx vitest run
Pop-Location
npm --prefix frontend run build
.venv/Scripts/python.exe tools/create_test_fixture.py
npm --prefix frontend run test:e2e
```

Browser tests require the running application and locally installed Chrome. CI installs Chromium and LibreOffice. Use a fresh pytest temporary directory on subsequent runs in restricted environments. Private corpus inputs default to `.local/private`; use `--corpus-root PATH` for another location. The private corpus command is `python tools/run_acceptance.py --output .local/verification/new-run --render`; its output directory must be new. No private decks are uploaded by CI.

After configuring keys, run the live checkpoint with a **new** output directory:

```powershell
.venv/Scripts/python.exe tools/run_ai_smoke.py --live --output .local/verification/ai-live-01
```

This sends only a generated synthetic slide, keeps the source/candidate/renders/report locally, and does not approve findings automatically. Exit 0 means ready, 2 means missing keys, and 3 means review or repair is still required. Use `--mock-providers` instead of `--live` to exercise edits and real rendering without API calls; that mode does not validate model quality.

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
