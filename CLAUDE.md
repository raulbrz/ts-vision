# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

ts-vision extracts data from handwritten "GOLD TIGERS SERVICES TIMESHEETS" (PDF/image scans) into a
CSV table. A static frontend uploads files; a Python backend runs them through a two-step OCR pipeline
and streams progress back as the pipeline runs. The whole site sits behind a username/password login:
a root account from `server/.env` plus any accounts created on `/register`, which is gated by a shared
registration secret rather than being open to the public. All UI copy and API error messages are in
Portuguese.

## Running it locally

Two independent processes, no shared build step:

```bash
# Terminal 1 — backend (http://localhost:5000)
cd server
python3 -m venv venv && source venv/bin/activate   # first time only
pip install -r requirements.txt                     # first time only
cp .env.example .env                                 # first time only, then fill in real values
python app.py

# Terminal 2 — frontend (http://localhost:8000)
cd web
python3 -m http.server 8000
```

`server/README.md` has the steps for obtaining the two required credentials (a GCP service account
JSON with the Cloud Vision API enabled, and an OpenRouter API key).

There is no build tool, package manager lockfile, linter, or test suite in this repository — neither
`web/` nor `server/` has one configured. Don't assume `npm test`, `pytest`, or similar will do anything.
Verification is manual/ad hoc:

- Backend request-validation and pure-function logic (e.g. `llm._split_csv_and_notes`,
  `users.verify_password`, `auth.verify_token`) can be checked with one-off `python3 -c "..."` snippets
  — see the task steps in `docs/superpowers/plans/` for the pattern used so far.
- The auth endpoints (`/api/login`, `/api/register`, `/api/session`, and the 401 on `/api/ocr`) are the
  one part exercisable end to end for free: `curl` against a running `python app.py` covers every path,
  since none of them reach Vision or OpenRouter. Registering test users writes to `server/users.db` —
  delete them afterwards so the real database stays clean.
- Frontend behavior needs a real browser; the plans directory shows how this was checked with
  `playwright-core` driving a local browser against a `python3 -m http.server` instance, since no test
  runner is wired into `web/`.
- The Cloud Vision and OpenRouter calls need live credentials and cost money per call — they aren't
  exercised by any automated check, only by manually running both servers and using the UI.

## Architecture

Two independently-deployable halves that only communicate over HTTP — nothing shared, no monorepo
tooling:

**`web/`** — vanilla HTML/CSS/JS, no framework, no build step, no npm dependency at all. `index.html`
holds the DOM structure; `style.css` the styling; `app.js` holds all logic as plain top-level functions
(no modules) operating on an in-memory `files` array. Clicking or dropping onto the dropzone works
natively because the real `<input type="file">` is stretched transparently over the whole dropzone box
(`.upload-input` in `style.css`) — the JS only adds a cosmetic `.is-dragging` class and reacts to the
input's `change` event, it doesn't implement drag-and-drop file capture itself. The "Enviar para OCR"
button POSTs a `multipart/form-data` request (files + `data_inicial`/`data_final`) to
`http://localhost:5000/api/ocr`, which is hardcoded as `OCR_ENDPOINT` in `app.js`, then reads the
response body as a stream (`response.body.getReader()` + `TextDecoder`, buffering and splitting on
`\n`) to parse newline-delimited JSON events as they arrive rather than waiting for one final response.
Each parsed event is appended to `#status-timeline` via `appendStatusEntry(stage, message)`; a
`concluido` event additionally renders the results table/notes and caches the raw CSV string in
`lastCsvText`, and an `erro` event surfaces `submitError`. The in-flight request is cancellable: the
submit handler stores its `AbortController` in `activeController` and passes `controller.signal` to
`fetch`; `#cancel-button` (shown only while a request is running) calls `.abort()`, and the resulting
`AbortError` is caught and rendered as a `cancelado` status-timeline entry — a client-only stage the
server never emits, so don't look for it in `app.py`. `#download-csv` builds a `Blob` from
`lastCsvText` (with a UTF-8 BOM so accented characters survive when opened in Excel) and triggers the
download via a synthetic `<a download>` click, naming the file from the selected `data_inicial`/
`data_final`. `clearResults()` (bound to `#clear-results`) resets the table, notes, timeline,
`lastCsvText`, and error banner back to their empty/hidden state without touching the selected-files
list. Note: `[hidden]` alone doesn't hide elements whose class also sets `display` (e.g. `.results {
display: flex }` beats the UA default `[hidden] { display: none }` at equal specificity) —
`style.css` has a global `[hidden] { display: none !important; }` rule to force it, so any new
toggleable section should rely on the `hidden` attribute rather than a bespoke `.is-visible`-style
class.

**`server/`** — Flask app run as a flat script (`python app.py`), not an installed package — modules
import each other directly (`import config`, `import ocr`, `import llm`), not via relative imports.
`app.py` is the only HTTP surface (`POST /api/ocr`). Instead of returning one JSON response, it streams
newline-delimited JSON (`application/x-ndjson`, via `Response(stream_with_context(generate()), ...)`):
each `_event(stage, message, **extra)` call yields one line as the pipeline progresses through
`recebido` → per-file `ocr_lendo`/`ocr_concluido`/`ocr_falhou` → `llm_processando` → a terminal
`concluido` (carrying `csv` and `notes`) or `erro` event. This lets the frontend show live per-file
status instead of a single opaque spinner. The generator orchestrates two independent, swappable steps:

1. `ocr.py` — Google Cloud Vision `document_text_detection` (images) / `batch_annotate_files` (PDF,
   capped at 5 pages by Vision's sync API) turns each uploaded file into raw text. One file's OCR
   failure doesn't fail the request — it's recorded as an `ocr_falhou` event and a `notes` entry, and
   that file is skipped from the LLM step.
2. `llm.py` — sends the raw OCR text (labeled per source filename) plus the full contents of the
   repo-root `prompt-to-OCR` prompt (with `[DATA_INICIAL]`/`[DATA_FINAL]` substituted) to an LLM via
   OpenRouter's OpenAI-compatible chat completions endpoint, through `_post_with_retry` rather than a
   direct `requests.post` call. `_post_with_retry` retries transient failures (HTTP 429, any 5xx, or a
   network-level `requests.exceptions.RequestException`) up to `MAX_RETRIES` (3) times with exponential
   backoff plus jitter, honoring a `Retry-After` response header when present; non-transient errors
   (400/401/etc.) propagate immediately without retrying. `_split_csv_and_notes` then splits the
   model's free-text reply into the CSV block and the "pontos de atenção" list by looking for the
   model's own "Pontos de atenção" section header — this parsing is coupled to the output format
   `prompt-to-OCR` asks the model to produce, so if that prompt's `SAÍDA` section changes, this parser
   likely needs to change too. The final `notes` sent to the frontend is `notes + llm_notes` — OCR
   failure messages (Python-generated) followed by the LLM's own content-quality observations.

`config.py` reads `GOOGLE_APPLICATION_CREDENTIALS` / `OPENROUTER_API_KEY` / `OPENROUTER_MODEL` plus the
auth settings (`APP_USERNAME`, `APP_PASSWORD`, `AUTH_SECRET`, `AUTH_TOKEN_TTL_HOURS`,
`REGISTRATION_SECRET`, `USERS_DB_PATH`) from `server/.env`
(via `python-dotenv`) and `config.validate()` is called at import time in `app.py`, so a missing
credential — including the login pair — fails the process at startup rather than on the first request.
`AUTH_SECRET` is the one optional field: when absent, `config` generates a per-process random secret
(`AUTH_SECRET_IS_EPHEMERAL` is set and `app.py` logs a warning), which means every restart, including
`debug=True` reloads, invalidates all issued tokens.

**Auth** — `server/auth.py` + `server/users.py`, no new dependency: a token is
`base64url(payload).base64url(hmac_sha256)`, where the payload is `{"sub", "exp"}`, signed with
`config.AUTH_SECRET` (stdlib `hmac`/`hashlib`) — not
a JWT library, so don't reach for `pyjwt` when touching it. `verify_token` rejects bad signatures and
expired `exp`; the `@auth.login_required` decorator reads `Authorization: Bearer <token>` and returns
401 with a body shaped like a pipeline event (`{"stage": "erro", "message": ...}`) so the frontend
renders something sensible even if it reads the response as an NDJSON stream. `app.py` exposes
`POST /api/login` (JSON `{usuario, senha}` → `{token, usuario, expira_em}`), `POST /api/register`, and
`GET /api/session` (revalidates a stored token), and decorates `POST /api/ocr` with `login_required`.

There are **two credential sources**, and `auth.check_credentials` tries them in this order: the root
pair `APP_USERNAME`/`APP_PASSWORD` from `.env` (plain text, compared with `hmac.compare_digest`), then
`users.authenticate` against the SQLite database. The root account is deliberately *not* seeded into
the database — it stays env-only, so changing it in `.env` takes effect on restart with no migration.

`users.py` owns `server/users.db` (SQLite via stdlib `sqlite3`, gitignored, created by `users.init_db()`
at `app.py` import time): one `users` table with `username TEXT UNIQUE COLLATE NOCASE` — hence
duplicate checks are case-insensitive — and a `password_hash` in the format
`scrypt$n$r$p$salt_b64$hash_b64` produced by `hashlib.scrypt` (no bcrypt/argon2 dependency).
`users.authenticate` hashes a throwaway password when the user doesn't exist, so a missing user and a
wrong password take the same time. `validate_new_user` enforces the username pattern (3–32 chars of
`[A-Za-z0-9._-]`), the 8-char minimum password, and rejects the root username as taken; it raises
`UserError` carrying the Portuguese message that `app.py` maps to 409 (name in use) or 400 (everything
else).

Both credential-guessing routes are throttled by `server/ratelimit.py` — an in-memory
`AttemptLimiter` (dict + `threading.Lock`, so it resets on restart and counts per process, not across
workers). `app.py` holds one instance and keys it `"login:<ip>"` / `"register:<ip>"` via `_rate_key`,
so the two counters are independent. Only credential failures count (wrong password, wrong
registration secret) — 400/409 validation errors don't. Each failure goes through `_penalize`, which
sleeps `AUTH_FAILURE_DELAY_SECONDS` and, from the `AUTH_MAX_ATTEMPTS`-th failure on, blocks the IP for
`AUTH_BLOCK_SECONDS` doubling per extra failure up to `AUTH_MAX_BLOCK_SECONDS`; a blocked request gets
429 + `Retry-After` instead of 401/403, and any success calls `limiter.reset`. The sleep is a
deliberate second-order defense — it ties up a worker thread, so keep it short and rely on the block
for the real protection.

Registration is gated by `config.REGISTRATION_SECRET`, which defaults to `AUTH_SECRET` when unset —
the `/register` screen tells the user to type the `AUTH_SECRET` from `.env`. Set `REGISTRATION_SECRET`
separately to stop the token-signing key from being typed into a form. `config.REGISTRATION_ENABLED`
is false when there is no explicit registration secret *and* `AUTH_SECRET` is ephemeral (nobody could
know the random value), in which case `/api/register` answers 503 instead of being unguessable-but-open.

On the frontend, `index.html` has two top-level screens — `#login-screen` and `#app-screen`, both
starting `hidden` — and `app.js` toggles them: `bootstrapSession()` runs at the bottom of the file on
load, shows the login screen when no token is stored, otherwise shows the app optimistically while
revalidating the token against `/api/session`. The token and username live in `localStorage`
(`tsvision_token` / `tsvision_user`); `authHeaders()` adds the `Authorization` header to the OCR fetch,
and any 401 (on `/api/session` or `/api/ocr`) routes through `handleUnauthorized()`, which drops the
stored token, clears files and results, and returns to the login screen. Since the frontend is served
as static files by `python3 -m http.server`, this gate is cosmetic on its own — the real enforcement is
the `login_required` decorator on the API.

Registration is a **separate static page**, not a third screen inside `index.html`:
`web/register/index.html` + `web/register/register.js`, reusing `../style.css`. The directory name is
what makes the URL `/register` work under plain `python3 -m http.server` (it 301s `/register` →
`/register/` and serves the `index.html` inside) — no router, no rewrite rules. On success the backend
already returns a token, so `register.js` writes the same `localStorage` keys and redirects to `../`,
landing the new user logged in. `register.js` duplicates the endpoint constant and the token key names
rather than importing them — `web/` has no module system, so keep the two files in sync by hand.

**`prompt-to-OCR`** (repo root, no file extension) is not documentation — it's live input read by
`llm.py` on every request. It defines the exact CSV schema (`Employee,Date,entrada1,saida1,entrada2,
saida2`), the AM/PM inference rule for timesheet punches, and the idem/illegible-field conventions.
Changing the CSV columns or business rules means editing this file, not the Python code.

**`docs/superpowers/`** holds the spec → plan documents this project's features were built from
(brainstorming skill → design spec in `specs/`, then implementation plan in `plans/`). They're a useful
record of *why* a given architecture was chosen (e.g. why Cloud Vision + a separate LLM call was picked
over a single multimodal call) when extending the pipeline.

**`BACKLOG.md`** (repo root) tracks known improvement items across `web/` and `server/`, ranked by
priority (result correctness first, then usability, then code quality/perf, with production/security
hardening deliberately deferred to last since it isn't the current focus). Check an item off (`- [ ]` →
`- [x]`, with a short note on how it was resolved) when you fix it, and add new items there when you
spot a real gap while working — keep it in sync with actual repo state rather than letting it drift.

## Secrets

`server/.env` (real credentials), `server/*.json` (GCP service account keys) and `server/users.db`
(hashed passwords of registered users) are gitignored.
`server/.env.example` must stay a placeholder template — never put real keys in it, since it isn't
gitignored.
