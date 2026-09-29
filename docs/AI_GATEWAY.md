# Vercel AI Gateway configuration

Reviewed September 29, 2026. The backend uses Gateway's [OpenAI-compatible Chat Completions endpoint](https://vercel.com/docs/ai-gateway/sdks-and-apis/openai-chat-completions) with image input and strict JSON schemas. Direct OpenAI, Anthropic and Gemini adapters remain available for explicit selection.

## Recommended settings

Set these in ignored `backend/.env` locally, or in the backend host's environment:

```dotenv
AI_GATEWAY_API_KEY=<your Gateway key>
STEVENS_AI_PROVIDER=vercel
STEVENS_AI_PLANNER_MODEL=anthropic/claude-sonnet-5.5
STEVENS_AI_REVIEWER_MODEL=anthropic/claude-opus-5.5-fast
AI_GATEWAY_REASONING_EFFORT=low
AI_GATEWAY_REVIEW_REASONING_EFFORT=medium
STEVENS_AI_MAX_CALLS=0
STEVENS_AI_MAX_TOKENS=0
```

Remove old `STEVENS_AI_PLANNER` and `STEVENS_AI_REVIEWER` overrides, or set both to `vercel`. The planner model handles source decisions, element recognition, redesign, outline planning, extraction and authoring. The reviewer model handles paired slide review and final ordered output QA. Both receive images where the workflow calls for them. Both recommended models are Anthropic models, so this is separate review, not cross-provider independence.

## Model choice

The public [Gateway model catalog](https://vercel.com/ai-gateway/models) and `/v1/models` metadata were checked for availability, image input and structured outputs. All five candidates below support the required capabilities. These are task-oriented recommendations, not a comprehensive quality ranking.

| Model ID | Role in this application |
| --- | --- |
| `anthropic/claude-sonnet-5.5` | Recommended planning/redesign/authoring model. Vercel specifically describes improved document, slide and spreadsheet work. |
| `anthropic/claude-opus-5.5-fast` | Recommended QA model for its vision and reasoning capabilities with high reported output throughput. Medium reasoning preserves deliberation for image comparisons. |
| `openai/gpt-6-sol-fast` | Strong alternative for structured agent workflows and a different model family for QA experiments. |
| `google/gemini-3.8-flash` | Alternative when response speed is the priority; configurable reasoning and multimodal input. |
| `spacexai/grok-4.7` | Supported alternative for document and presentation work; use the catalog's `spacexai` prefix. |

Sources: [Sonnet](https://vercel.com/ai-gateway/models/claude-sonnet-5.5), [Opus Fast](https://vercel.com/ai-gateway/models/claude-opus-5.5-fast), [Sol Fast](https://vercel.com/ai-gateway/models/gpt-6-sol-fast), [Gemini Flash](https://vercel.com/ai-gateway/models/gemini-3.8-flash), [Grok](https://vercel.com/ai-gateway/models/grok-4.7).

Vercel's latency figures are live provider metrics, including time to first token, not complete deck processing times. Images, prompt length, reasoning, generated output, rendering and repair rounds all affect end-to-end time. Budget was not the deciding factor in this recommendation. Cumulative request/token ceilings are disabled by default: zero or an unset variable means unlimited; a positive value opts into a cap. Execution deadlines, request timeouts and bounded retries/non-improving repairs remain; they do not select a cheaper model automatically.

## Changing models

Provider precedence: role-specific `STEVENS_AI_PLANNER` / `STEVENS_AI_REVIEWER`, then `STEVENS_AI_PROVIDER`, then the backward-compatible code default `openai`. Explicit `auto` prefers a configured Gateway key. An explicit provider never switches after a failed call.

Model precedence: role-specific `STEVENS_AI_PLANNER_MODEL` / `STEVENS_AI_REVIEWER_MODEL`, then shared `STEVENS_AI_MODEL`, then provider-specific model (`AI_GATEWAY_MODEL` for Gateway), then built-in defaults. To use one model for both roles, remove both role-specific model settings and set `STEVENS_AI_MODEL`. Gateway IDs must include `creator/model`. Select a model supporting both vision and structured output.

Nonempty process variables override the matching `.env` entries. The backend reloads settings on each request; refresh the application's AI configuration panel after editing. Change settings between jobs so a running deck does not switch models midway. An environment variable name at a higher configuration priority still wins over a lower-priority name, regardless of where each was set.

Reasoning settings are separate for planning and review. Set either to `provider-default` to omit the reasoning override. Otherwise choose an effort the selected model supports; not every model supports every effort. Auth failures, invalid schemas, refused/incomplete responses and exhausted limits remain errors that block release. No model fallback or QA bypass is introduced.

To return to direct OpenAI, set `STEVENS_AI_PROVIDER=openai`, remove role provider overrides and generic model overrides, configure `OPENAI_API_KEY`, `OPENAI_MODEL=gpt-6-luna`, `OPENAI_REASONING_EFFORT=none` and `OPENAI_REVIEW_REASONING_EFFORT=low`. Clear Gateway model slugs from role settings before selecting a direct adapter.

## Vercel deployment settings

In Project Settings, add the variables above to the intended Production/Preview environments. Store `AI_GATEWAY_API_KEY` as a secret. These are backend variables: do not add a frontend-public prefix such as `VITE_` or `NEXT_PUBLIC_`. After changing them, deploy again; [Vercel environment changes apply to new deployments](https://vercel.com/docs/environment-variables).

This integration makes API/model configuration portable; it does not convert the full application to serverless hosting. The current backend requires a persistent worker, process-local job state, disk workspaces, SQLite accounts and an installed PowerPoint/LibreOffice renderer. A full Vercel deployment needs durable job/account storage and a rendering/job worker architecture. If that worker is hosted elsewhere, configure its environment too. No Vercel project deployment is performed by this change.

## Repeatable verification

`tools/verify_gateway.py --live --image <synthetic-closing.png> --models anthropic/claude-sonnet-5.5 anthropic/claude-opus-5.5-fast --output <new-report.json>` verifies catalog support, image recognition and schema output through the actual key. `--models` accepts a space-separated list of Gateway IDs. The five-model smoke check passed with response times of 2.00–3.24 seconds, one small request per model at low effort. This is a compatibility smoke test, not evidence that one model wins on complete decks.

`tools/verify_pdf_redesign.py --live --math-fixture --output <new-directory>` exercises PDF import, source decisions, real rendering, repairs, all-slide paired QA and ordered output QA. The recommended pair passed all 11 checks on the synthetic cover/math fixture with its appended closing, including a QA-triggered repair (10 API requests). Evidence is retained locally in `.local/verification/gateway-redesign-live`.

`tools/verify_visual_planning.py --live --output <new-directory>` separately exercises outline visual decisions and native authoring through final QA. The live Gateway run selected and produced a diagram, chart and table plus the opening/closing slides. QA caught dark table headers on a red fill; the compositor now explicitly pairs white header text with red fill. Replaying that exact deck passed all output-QA checks. A separate native-chart inspection finding remains `needs_review`, so this authoring replay did not unlock downloads. Evidence: `.local/verification/gateway-authoring-live` and `.local/verification/gateway-authoring-replay`. The existing inspection gate was not waived to obtain a passing result.

These commands make paid requests and should only use authorized material. Synthetic successes do not certify arbitrary user decks. Mandatory release gates remain in effect.
