# Repository layout

`backend/app` contains FastAPI routes, session handling, generation identity, AI providers and quality checks. `backend/slide_engine` contains inventory, native PowerPoint preservation, styling, repair and the analysis helpers. `backend/slide_fixer` contains the shared PowerPoint utility code. The approved template lives in `backend/assets`.

`frontend/src` contains the React workflow. `tests/backend` contains synthetic regression fixtures and backend tests; frontend component tests live beside the UI, and browser tests live in `frontend/e2e`. `tools` contains verification commands. `.github/workflows/verify.yml` runs offline checks with a renderer in CI.

The repository has one application root. No parent folder, legacy prototype checkout, private deck or archived report is required to run it. The Python import path is `backend`; use `--app-dir backend` with Uvicorn. The slide transformation package is named `slide_engine`.

Local-only files belong in `.local`: private source decks in `private`, verification evidence in `verification`, retained implementation history in `history`. Virtual environments and dependency directories are also excluded. Credentials belong in `backend/.env`; only `backend/.env.example` ships.
