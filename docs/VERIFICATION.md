# Verification checkpoints

For the current invitation accounts, authoring, cleanup, math/plots and ordered screenshot QA build, see [implementation verification](IMPLEMENTATION_VERIFICATION.md). The live results below are historical preservation-pipeline evidence. Use `powershell -NoProfile -File tools/verify.ps1` for the current automated suite.

1. Run backend regression tests, including the two actual-renderer checks. These cover preservation, exported content, release gating, AI request/response handling and failure paths. Provider calls are mocked; passing does not establish live model quality.
2. Run frontend component tests and production build. Generate the synthetic browser fixture and run all browser workflows against the local server.
3. Check Git's handling of nested `.env` files and local artifacts, then scan files eligible for source control for configured credential values. Only the empty environment example should be publishable.
4. After configuring `backend/.env`, use **Test AI connection**, then run the synthetic live smoke command in the README. Inspect the resulting slides and review findings. Offline tests cannot substitute for this live checkpoint.

## Live checkpoint completed September 24, 2026

GPT-6 Luna performed real planning and visual review calls using the configured OpenAI key. The synthetic slide exercised one repair pass, native geometry edits, source text and speaker-note preservation, actual PowerPoint rendering, and the final release gate. All six required checks passed with no unresolved findings; the resulting generation was `ready`. The rendered slide was also visually inspected. Evidence remains local at `.local/verification/openai-live-02/result.json` and its sibling `generation` directory.

The initial live run identified a template-context error in visual review and insufficient text-box height. The prompts now identify approved master artwork explicitly, while still checking for real collisions. The planner receives text margins and fit estimates; overflow feedback identifies the affected object so repair can enlarge its box. No verifier thresholds or release requirements were relaxed.

This establishes a working live development pipeline, not universal slide quality. Complex user decks can still require review. Both AI roles use the same model in separate calls; deterministic preservation and rendering checks remain separate from model judgment.

All private-course acceptance runs and render evidence stay local. The previous candidate holdout's training/tuning history is unknown, so it must not be described as a proven independent holdout. A future independent quality benchmark needs newly supplied decks with known provenance.

Final download is permitted only for the exact checked candidate. Required failures cannot be waived; specific review findings require a recorded decision. AI judgments can be wrong, even when the automated checks complete.

## Geometry namespace regression

A 12-slide deck from another authoring tool exposed a false preservation failure: all 308 objects were reported as altered because inclusive XML canonicalization included unused namespace declarations inherited from the destination slide. Geometry comparison now uses exclusive canonicalization, which ignores those unrelated declarations while retaining geometry elements, attributes, adjustment formulas and path coordinates. The original candidate passes the corrected artifact check without changing its bytes. Regression fixtures cover harmless namespace differences and real changes to preset shapes, adjustment values and custom paths. Verification policy is now `preservation-ai-3`; old generations must be regenerated. Other layout/render findings still require their normal checks.
