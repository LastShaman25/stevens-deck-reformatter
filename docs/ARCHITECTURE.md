# Repository layout

`backend/app` contains FastAPI routes, session handling, generation identity, AI providers and quality checks. `backend/slide_engine` contains inventory, native PowerPoint preservation, styling, repair and the analysis helpers. `backend/slide_fixer` contains the shared PowerPoint utility code. The approved template lives in `backend/assets`.

`frontend/src` contains the React workflow. `tests/backend` contains synthetic regression fixtures and backend tests; frontend component tests live beside the UI, and browser tests live in `frontend/e2e`. `tools` contains verification commands. `.github/workflows/verify.yml` runs offline checks with a renderer in CI.

The repository has one application root. No parent folder, legacy prototype checkout, private deck or archived report is required to run it. The Python import path is `backend`; use `--app-dir backend` with Uvicorn. The slide transformation package is named `slide_engine`.

Local-only files belong in `.local`: private source decks in `private`, verification evidence in `verification`, retained implementation history in `history`. Virtual environments and dependency directories are also excluded. Credentials belong in `backend/.env`; only `backend/.env.example` ships.


## Slide additions and visual planning

Redesign preserves source content and mapping. It may split source material and appends the explicitly authorized Thank you closing through `slide_engine.bookends`; it cannot invent unrelated slides. Added closing provenance is separate from source mapping, is covered by QA, and has a direct preview link above the source-slide navigation.

New authoring outlines carry an explicit `visual` choice, description and rationale per slide. Supported choices are text only, editable process/comparison diagram, data chart, function/data plot, equation, table and a source PDF page. Native diagrams support two to six steps/alternatives; longer explanations should span slides. The author must implement the approved visual type, with a bounded correction request on mismatch. QA verifies the result and native artifact auditing checks diagram labels and relations after reopening the PPTX. Explicit user content edits can override a planned visual type, but never bypass factual or release checks.

Authoring repairs actionable visual, content and sequence findings once, then renders and reviews the repaired candidate again. Cosmetic warnings remain non-blocking. Missing QA or remaining material findings still prevent download.

Use `tools/verify_visual_planning.py --live --output <new-directory>` for a real provider/render/QA reproduction. It deliberately supplies a process and example data without requesting a visual type. Use `--replay <previous-output-directory>` to reproduce the exact earlier outline and authored content rather than obtaining an easier fresh plan. Reproduction succeeds only when the required closing is present and all release gates pass.
