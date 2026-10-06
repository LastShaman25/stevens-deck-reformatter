# Developer activity

Admins can assign Developer in Manage users when creating or editing an account. Role changes invalidate that account's existing logins. Admins and Developers can open Developer activity; Members cannot. Developers cannot manage users or access another user's presentation or downloads.

The view lists jobs first. Select a job for timestamped events, live updates and paginated history. Summaries show workflow, template, input category, supported exports, processing time, input/output/total tokens and request counts. QA findings remain separate from processing completion.

Actual request attempts own token usage, including reported retry usage. Cached replays and model-step summaries do not double-count. Missing usage remains unknown/incomplete. Processing time merges overlapping operations and excludes outline approval idle time.

Only 24 hours of metadata are retained in the local account SQLite database. Timestamps are stored in UTC and displayed in browser-local time. Logs exclude prompts, document text, raw responses, model reasoning, file paths, keys and private exception messages. Totals cover retained events only; old jobs without instrumentation are not reconstructed.

Endpoints: `GET /api/developer/jobs` and `GET /api/developer/activity?job_id=...`. Access checks apply on both endpoints.
