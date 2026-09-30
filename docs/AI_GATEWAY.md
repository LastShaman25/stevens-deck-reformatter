# Vercel AI Gateway configuration

Reviewed September 29, 2026. The backend uses Gateway's [OpenAI-compatible Chat Completions endpoint](https://vercel.com/docs/ai-gateway/sdks-and-apis/openai-chat-completions) with image input and strict JSON schemas. Direct OpenAI, Anthropic and Gemini adapters remain available for explicit selection.

## Recommended settings

Set these in ignored `backend/.env` locally, or in the backend host's environment:

```dotenv
AI_GATEWAY_API_KEY=<your Gateway key>
STEVENS_AI_PROVIDER=vercel
STEVENS_AI_REDESIGNER_MODEL=openai/gpt-6-luna
STEVENS_AI_GENERATOR_MODEL=anthropic/claude-opus-5.5
STEVENS_AI_REVIEWER_MODEL=anthropic/claude-opus-5.5
AI_GATEWAY_REDESIGN_REASONING_EFFORT=low
AI_GATEWAY_GENERATOR_REASONING_EFFORT=low
AI_GATEWAY_REVIEW_REASONING_EFFORT=low
STEVENS_AI_MAX_CALLS=0
STEVENS_AI_MAX_TOKENS=0
```

Remove old `STEVENS_AI_PLANNER` overrides. Set `STEVENS_AI_REDESIGNER`, `STEVENS_AI_GENERATOR` and `STEVENS_AI_REVIEWER` to `vercel`, or leave them unset to inherit the shared provider. The role assignments apply to first attempts and repairs:

| Agent | Internal roles | Default model |
| --- | --- | --- |
| Redesign | `planner`, `element_roles` (including source decisions) | `openai/gpt-6-luna` |
| Generation | `extractor`, `outline`, `author` | `anthropic/claude-opus-5.5` |
| QA | `reviewer` (including logo verification), `output_qa` | `anthropic/claude-opus-5.5` |

These are separate model calls coordinated by the backend. Template composition, rendering, deterministic checks and release control remain application code. Redesign has cross-provider review; generation and its QA use the same model family in separate calls. The connection test exercises all three agent configurations, and the UI displays each model separately.

## Model choice

The selected split uses Luna for constrained redesign and standard Opus 5.5 for generation and QA. All three use low reasoning by default and have separate model and reasoning settings. Mandatory visual review and ordered output QA still run as separate calls; no model escalation occurs automatically.

The [Gateway catalog](https://ai-gateway.vercel.sh/v1/models) lists Luna with image input and structured output. Sonnet and Opus Fast remain explicit alternatives, rather than defaults. Compare complete-deck cost, elapsed time, repair counts and QA defects on the same fixture before changing models. Provider latency alone does not measure rendering or full workflow time.

Cumulative request/token ceilings are disabled by default: zero or an unset variable means unlimited; a positive value opts into a deployment cap. The development launcher forces both to zero. Execution deadlines, request timeouts and bounded retries/non-improving repairs remain; they do not select a cheaper model automatically.

## Changing models

Provider precedence: workflow-specific `STEVENS_AI_REDESIGNER` / `STEVENS_AI_GENERATOR` / `STEVENS_AI_REVIEWER`, then the legacy `STEVENS_AI_PLANNER` fallback for redesign/generation, then `STEVENS_AI_PROVIDER`, then the backward-compatible code default `openai`. Explicit `auto` prefers a configured Gateway key. An explicit provider never switches after a failed call.

Model precedence: workflow-specific `STEVENS_AI_REDESIGNER_MODEL` / `STEVENS_AI_GENERATOR_MODEL` / `STEVENS_AI_REVIEWER_MODEL`, then the legacy `STEVENS_AI_PLANNER_MODEL` fallback for redesign/generation, then shared `STEVENS_AI_MODEL`, then provider-specific model (`AI_GATEWAY_MODEL` for Gateway), then built-in defaults. To use one model for every role, remove all workflow and legacy model settings and set `STEVENS_AI_MODEL`. Gateway IDs must include `creator/model`. Select a model supporting both vision and structured output.

Nonempty process variables override the matching `.env` entries. The backend reloads settings on each request; refresh the application's AI configuration panel after editing. Change settings between jobs so a running deck does not switch models midway. An environment variable name at a higher configuration priority still wins over a lower-priority name, regardless of where each was set.

Reasoning settings are separate for redesign, generation and review. The first two fall back to legacy `AI_GATEWAY_REASONING_EFFORT`; all default to low. Set a workflow effort to `provider-default` to omit its reasoning override. Otherwise choose an effort the selected model supports; not every model supports every effort. Auth failures, invalid schemas, refused/incomplete responses and exhausted limits remain errors that block release. No model fallback or QA bypass is introduced.

To return to direct OpenAI, set `STEVENS_AI_PROVIDER=openai`, remove role provider overrides and generic model overrides, configure `OPENAI_API_KEY`, `OPENAI_MODEL=gpt-6-luna`, `OPENAI_REASONING_EFFORT=none` and `OPENAI_REVIEW_REASONING_EFFORT=low`. Clear Gateway model slugs from role settings before selecting a direct adapter.

## Vercel deployment settings

In Project Settings, add the variables above to the intended Production/Preview environments. Store `AI_GATEWAY_API_KEY` as a secret. These are backend variables: do not add a frontend-public prefix such as `VITE_` or `NEXT_PUBLIC_`. After changing them, deploy again; [Vercel environment changes apply to new deployments](https://vercel.com/docs/environment-variables).

This integration makes API/model configuration portable; it does not convert the full application to serverless hosting. The current backend requires a persistent worker, process-local job state, disk workspaces, SQLite accounts and an installed PowerPoint/LibreOffice renderer. A full Vercel deployment needs durable job/account storage and a rendering/job worker architecture. If that worker is hosted elsewhere, configure its environment too. No Vercel project deployment is performed by this change.

## Repeatable verification

`tools/verify_gateway.py --live --image <synthetic-closing.png> --models openai/gpt-6-luna anthropic/claude-opus-5.5 --output <new-report.json>` verifies catalog support, image recognition and schema output through the actual key. `--models` accepts a space-separated list of Gateway IDs. This is a compatibility smoke test, not evidence that one model wins on complete decks.

`tools/verify_pdf_redesign.py --live --math-fixture --output <new-directory>` exercises PDF import, source decisions, real rendering, repairs, all-slide paired QA and ordered output QA. The previously configured Sonnet/Opus pair passed all 11 checks on the synthetic cover/math fixture with its appended closing, including a QA-triggered repair (10 API requests). Evidence is retained locally in `.local/verification/gateway-redesign-live`.

`tools/verify_visual_planning.py --live --output <new-directory>` separately exercises outline visual decisions and native authoring through final QA. The live Gateway run selected and produced a diagram, chart and table plus the opening/closing slides. QA caught dark table headers on a red fill; the compositor now explicitly pairs white header text with red fill. Replaying that exact deck passed all output-QA checks. A separate native-chart inspection finding remains `needs_review`, so this authoring replay did not unlock downloads. Evidence: `.local/verification/gateway-authoring-live` and `.local/verification/gateway-authoring-replay`. The existing inspection gate was not waived to obtain a passing result.

These commands make paid requests and should only use authorized material. Synthetic successes do not certify arbitrary user decks. Mandatory release gates remain in effect.
