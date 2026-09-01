# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

ts-vision extracts data from handwritten "GOLD TIGERS SERVICES TIMESHEETS" (PDF/image scans) into a
CSV table. A static frontend uploads files; a Python backend sends them, as images, to a multimodal LLM
in a single call and streams progress back as the pipeline runs. The whole site sits behind a
username/password login:
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

`server/README.md` has the steps for obtaining the one required credential (an OpenRouter API key —
`OPENROUTER_MODEL` must point at a model with multimodal/image input support).

There is no build tool, package manager lockfile, linter, or test suite in this repository — neither
`web/` nor `server/` has one configured. Don't assume `npm test`, `pytest`, or similar will do anything.
Verification is manual/ad hoc:

- Backend request-validation and pure-function logic (e.g. `llm._split_csv_and_notes`,
  `users.verify_password`, `auth.verify_token`) can be checked with one-off `python3 -c "..."` snippets
  — see the task steps in `docs/superpowers/plans/` for the pattern used so far.
- The auth endpoints (`/api/login`, `/api/register`, `/api/session`, and the 401 on `/api/ocr`) are the
  one part exercisable end to end for free: `curl` against a running `python app.py` covers every path,
  since none of them reach OpenRouter. Registering test users writes to `server/users.db` — delete them
  afterwards so the real database stays clean. The `/api/ocr` streaming stages up through
  `preparando`/`preparado`/`preparo_falhou` are also exercisable with a fake `OPENROUTER_API_KEY` and a
  real image/PDF fixture — only the final OpenRouter call itself needs a live key.
- Frontend behavior needs a real browser; the plans directory shows how this was checked with
  `playwright-core` driving a local browser against a `python3 -m http.server` instance, since no test
  runner is wired into `web/`.
- The OpenRouter multimodal call needs a live credential and costs money per call (and has to be a
  vision-capable model) — it isn't exercised by any automated check, only by manually running both
  servers and using the UI.

## Architecture

Two independently-deployable halves that only communicate over HTTP — nothing shared, no monorepo
tooling:

**`web/`** — vanilla HTML/CSS/JS, no framework, no build step, no npm dependency at all. `index.html`
holds the DOM structure; `style.css` the styling; `app.js` holds all logic as plain top-level functions
(no modules) operating on an in-memory `files` array. Clicking or dropping onto the dropzone works
natively because the real `<input type="file">` is stretched transparently over the whole dropzone box
(`.upload-input` in `style.css`) — the JS only adds a cosmetic `.is-dragging` class and reacts to the
input's `change` event, it doesn't implement drag-and-drop file capture itself. A third way to add files
is pasting (Ctrl+V) — a `document`-level `paste` listener reads `event.clipboardData.items`, filters for
`kind === 'file'` (e.g. a screenshot copied to the clipboard), and feeds the resulting `File` objects
into the same `addFiles()` used by the input and drop paths; it's a no-op (and doesn't call
`preventDefault`) when the clipboard payload has no files, so pasting text into the date fields or
login form is unaffected, and it's gated on `appScreen` being visible so paste doesn't fire from the
login screen. The "Enviar para OCR"
button POSTs a `multipart/form-data` request (files + `data_inicial`/`data_final`) to `OCR_ENDPOINT`
in `app.js`. `API_BASE` (and `register.js`'s `REGISTER_ENDPOINT`) resolve to the absolute
`http://localhost:5000/api` only when `location.hostname` is `localhost`/`127.0.0.1` — that's the
non-Docker local dev layout, frontend and backend on different ports. Anywhere else they resolve to
a relative `/api`, which is what the docker-compose deployment (see below) relies on: the `web` nginx
container proxies `/api/` to the `server` container over the compose network, so frontend and backend
share an origin and no hostname needs to be baked in. `app.js` then reads the OCR response body as a
stream (`response.body.getReader()` + `TextDecoder`, buffering and splitting on `\n`) to parse
newline-delimited JSON events as they arrive rather than waiting for one final response.
Each parsed event is appended to `#status-timeline` via `appendStatusEntry(stage, message)`; a
`concluido` event additionally renders the results table/notes and caches the raw CSV string in
`lastCsvText`, and an `erro` event surfaces `submitError`. The in-flight request is cancellable: the
submit handler stores its `AbortController` in `activeController` and passes `controller.signal` to
`fetch`; `#cancel-button` (shown only while a request is running) calls `.abort()`, and the resulting
`AbortError` is caught and rendered as a `cancelado` status-timeline entry — a client-only stage the
server never emits, so don't look for it in `app.py`. `#download-csv` builds a `Blob` from
`lastCsvText` (with a UTF-8 BOM so accented characters survive when opened in Excel) and triggers the
download via a synthetic `<a download>` click, naming the file from the selected `data_inicial`/
`data_final`. `#copy-csv` copies `lastCsvText` straight to the clipboard via
`navigator.clipboard.writeText`, showing "Copiado!"/"Erro ao copiar" on the button label for 2s as
feedback instead of a separate status element. `clearResults()` (bound to `#clear-results`) resets the
table, notes, timeline, `lastCsvText`, and error banner back to their empty/hidden state without
touching the selected-files list. Note: `[hidden]` alone doesn't hide elements whose class also sets
`display` (e.g. `.results {
display: flex }` beats the UA default `[hidden] { display: none }` at equal specificity) —
`style.css` has a global `[hidden] { display: none !important; }` rule to force it, so any new
toggleable section should rely on the `hidden` attribute rather than a bespoke `.is-visible`-style
class.

The app screen also has a "Modelo de IA" `<select>` (`#model-select-input`, above the upload zone)
that lets a logged-in user switch which OpenRouter model handles OCR without editing `server/.env` —
the original way, which required a redeploy. `showApp()` calls `loadModelSetting()` on login/bootstrap,
which does a `GET` to `MODEL_SETTINGS_ENDPOINT` (`/api/settings/model`) and hands the response
(`{model, options}`) to `populateModelSelect()`, which fills the `<select>` from `options` and selects
`model` — adding it as an extra option first if it isn't already in `options` (e.g. it came from
`.env` or was set previously via the API), so the dropdown never ends up unable to represent the
server's actual state. There's no "outro/custom" free-text entry in the UI by design — only the
curated list from `config.OPENROUTER_MODEL_OPTIONS` is selectable. Picking an option fires the
`select`'s `change` listener straight into `applyModel()`, which `POST`s `{model}` to the same
endpoint and shows a 2.5s inline confirmation/error via `showModelStatus()` (`#model-select-status`),
following the same transient-feedback pattern as `#copy-csv`. A 401 from either call routes through
`handleUnauthorized()` like every other authenticated fetch in this file.

**`server/`** — Flask app run as a flat script (`python app.py`), not an installed package — modules
import each other directly (`import config`, `import attachments`, `import llm`), not via relative
imports. `app.py` is the only HTTP surface (`POST /api/ocr`). Instead of returning one JSON response,
it streams newline-delimited JSON (`application/x-ndjson`, via
`Response(stream_with_context(generate()), ...)`): each `_event(stage, message, **extra)` call yields
one line as the pipeline progresses through `recebido` → per-file `preparando`/`preparado`/
`preparo_falhou` → `llm_processando` → a terminal `concluido` (carrying `csv` and `notes`) or `erro`
event. This lets the frontend show live per-file status instead of a single opaque spinner. The
OpenRouter call itself emits no events while it blocks (can be minutes on a big timesheet), so the
`llm_processando` loop iterates `llm.structure_with_heartbeat` — which runs the real call on a daemon
thread and surfaces a `heartbeat` progress item every `llm.HEARTBEAT_INTERVAL_SECONDS` (15s) it's
still waiting — and `app.py` turns each `heartbeat` into a bare `"\n"` on the wire. That keeps bytes
flowing so idle-timeout proxies in front of the app (Cloudflare's non-configurable ~100s 524, an
NPM/nginx `proxy_read_timeout`) don't sever the response mid-stream; the frontend already skips blank
lines when splitting the NDJSON, so the `"\n"` is invisible to it. Symptom this fixed: a prod-only
`TypeError: network error` in `app.js`'s OCR fetch (a cut *response* stream, not a failed connect),
seen ~60–100s into a large-timesheet run. There used
to be a separate Google Cloud Vision OCR step before the LLM call; it was removed because Vision's
`full_text_annotation.text` flattens the page into reading-order text and throws away the row/column
layout, which then had to be blindly reconstructed by the LLM from a linear string — a bad fit for a
handwritten grid. A vision-capable LLM reading the actual image handles that layout natively, so OCR
and structuring collapsed into one step:

1. `attachments.py` — turns each uploaded file into a list of OpenAI/OpenRouter-style `image_url`
   content parts: PDFs are rendered page-by-page to PNG via PyMuPDF (`to_image_parts`, no page cap,
   no system Poppler dependency needed), plain image files pass through as base64 of the original
   bytes with a mime type derived from the extension. One file's conversion failure (corrupt PDF,
   unreadable bytes) doesn't fail the request — it's recorded as a `preparo_falhou` event and a
   `notes` entry, and that file is skipped from the LLM call. No cap on page count or PNG size also
   means no cap on how big the eventual OpenRouter request gets — `llm.py` still sends every page of
   every file as one multimodal request (see below). A ~18-page/10MB scanned PDF hit this in
   production against the free `google/gemma-4-26b-a4b-it:free` (the `config.py` default): the
   model's backend rejected the request with an opaque, non-retryable error (`"Error in input
   stream"`, not generated anywhere in this codebase). Switching `OPENROUTER_MODEL` to a paid,
   larger-context model (`google/gemini-2.5-flash-lite` in production) resolved it with no code
   change; see `BACKLOG.md` for the page-batching mitigation designed for if a free/small model needs
   to be used again.
2. `llm.py` — sends one multimodal chat message to OpenRouter: `build_messages` assembles a `content`
   array with the full `prompt-to-OCR` prompt text (with `[DATA_INICIAL]`/`[DATA_FINAL]` substituted)
   followed by, per file, one `--- Arquivo: <name> | Página <n> ---` text label per image part from
   `attachments.py` (`<n>` starts at 1 within that file — a plain image file has exactly one part, so
   it's always labeled Página 1) immediately followed by that image part. `prompt-to-OCR` instructs the
   model to echo this exact page number into the `Page` column of the CSV it returns, which is how a
   multi-page PDF upload ends up with a page number the frontend can display per row rather than the
   model having to infer one on its own. `build_prompt` builds a text-only preview of the same instructions (filenames +
   page counts, no image data) used for the `llm_processando` progress event, since embedding base64
   blobs in a UI reveal panel isn't useful. The actual POST goes through `_post_with_retry` rather than
   a direct `requests.post` call, which retries transient failures (HTTP 429, any 5xx, or a
   network-level `requests.exceptions.RequestException`) up to `MAX_RETRIES` (3) times with exponential
   backoff plus jitter, honoring a `Retry-After` response header when present; non-transient errors
   (400/401/etc.) propagate immediately without retrying. `structure`/`_post_with_retry` log (at
   `INFO`) the page count and payload size sent, each attempt's HTTP status and wall-clock time, and
   the total call duration — `docker compose logs server` is how you tell whether a slow OCR run is
   the OpenRouter call itself vs. retries vs. upload/render. `_split_csv_and_notes` then splits the
   model's free-text reply into the CSV block and the "pontos de atenção" list by looking for the
   model's own "Pontos de atenção" section header — this parsing is coupled to the output format
   `prompt-to-OCR` asks the model to produce, so if that prompt's `SAÍDA` section changes, this parser
   likely needs to change too. The final `notes` sent to the frontend is `notes + llm_notes` —
   file-preparation failure messages (Python-generated) followed by the LLM's own content-quality
   observations.

`config.py` reads `OPENROUTER_API_KEY` / `OPENROUTER_MODEL` (default `google/gemma-4-26b-a4b-it:free`
— must be a vision-capable model) plus the auth settings (`APP_USERNAME`, `APP_PASSWORD`,
`AUTH_SECRET`, `AUTH_TOKEN_TTL_HOURS`, `REGISTRATION_SECRET`, `USERS_DB_PATH`) from `server/.env` (via
`python-dotenv`) and `config.validate()` is called at import time in `app.py`, so a missing credential
— including the login pair — fails the process at startup rather than on the first request.
`AUTH_SECRET` is the one optional field: when absent, `config` generates a per-process random secret
(`AUTH_SECRET_IS_EPHEMERAL` is set and `app.py` logs a warning), which means every restart, including
`debug=True` reloads, invalidates all issued tokens. `config.OPENROUTER_MODEL_OPTIONS` is a curated,
deduplicated list (current `OPENROUTER_MODEL` first, then a handful of known vision-capable slugs)
that only feeds the model `<select>` on the frontend — it is not an allowlist enforced anywhere.

**`server/runtime_settings.py`** holds the one setting that's meant to change without an `.env` edit
and a redeploy: which OpenRouter model actually handles OCR. `get_active_model()`/`set_active_model()`
read/write a `key`/`value` row (`app_settings` table, key `"openrouter_model"`) in the same SQLite file
as `users.db` (`config.USERS_DB_PATH`) — reusing that file, rather than a new one, means the setting
rides along on the same Docker named volume (`users_db`) that already persists `users.db` across
container restarts/redeploys, with no compose changes needed. `get_active_model()` falls back to
`config.OPENROUTER_MODEL` (the `.env` value) when no row exists yet. `set_active_model()` validates
against `MODEL_PATTERN` — a permissive `provedor/modelo` shape (letters/digits/`.`/`_`/`:`/`-` either
side of one slash, ≤200 chars) — and raises `SettingsError` (→ 400) on a bad value; unlike the
frontend's curated `<select>`, this validation is intentionally not restricted to
`config.OPENROUTER_MODEL_OPTIONS`, so the API stays usable for a model not yet added to that list
(e.g. via `curl`) without a code change. `app.py` calls `runtime_settings.init_db()` at import time,
same pattern as `users.init_db()`. `llm.structure()` reads `runtime_settings.get_active_model()` per
request (not `config.OPENROUTER_MODEL` directly) when building the OpenRouter payload, so a change
takes effect on the very next OCR call with no restart; the `llm_processando` progress event's message
in `app.py` reads the same live value so what the UI displays matches what was actually sent.
`GET /api/settings/model` (→ `{model, options}`) and `POST /api/settings/model` (body `{model}` →
`{model}` or 400) in `app.py` are both behind `@auth.login_required` like every other authenticated
route — there's no extra role check, so any logged-in user (root or registered) can change the model
for everyone, consistent with this app having no per-user permission tiers anywhere else.

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
`llm.py` on every request. It defines the exact CSV schema (`Page,Employee,Date,entrada1,saida1,
entrada2,saida2`), the AM/PM inference rule for timesheet punches, and the idem/illegible-field
conventions.
Changing the CSV columns or business rules means editing this file, not the Python code.

**`docs/superpowers/`** holds the spec → plan documents this project's features were built from
(brainstorming skill → design spec in `specs/`, then implementation plan in `plans/`). They're a useful
record of *why* a given architecture was chosen — e.g. `2026-08-03-ocr-pipeline-design.md` records the
original Cloud Vision + separate LLM call design, and `2026-08-11-multimodal-ocr-design.md` records why
it was later replaced with a single multimodal call — when extending the pipeline.

**`BACKLOG.md`** (repo root) tracks known improvement items across `web/` and `server/`, ranked by
priority (result correctness first, then usability, then code quality/perf, with production/security
hardening deliberately deferred to last since it isn't the current focus). Check an item off (`- [ ]` →
`- [x]`, with a short note on how it was resolved) when you fix it, and add new items there when you
spot a real gap while working — keep it in sync with actual repo state rather than letting it drift.

## Deployment

`docker-compose.yml` (repo root) is the VPS deployment path: `git clone` the repo, fill in
`server/.env` (same credential the non-Docker setup needs — see `server/README.md`), then
`docker compose up -d --build`. It builds two images:

- `server/Dockerfile` — `python:3.11-slim` running the Flask app under `gunicorn` (not the
  `debug=True` dev server `python app.py` uses locally) on `--worker-class gthread --workers 1
  --threads 8`. Workers are pinned at 1 deliberately: `config.AUTH_SECRET` falls back to a random
  per-process value when unset in `.env`, and separate worker *processes* (unlike threads) don't
  share that value — with `workers > 1` and no fixed `AUTH_SECRET`, a token signed by one worker
  would fail verification on requests routed to another. Setting `AUTH_SECRET` in `server/.env` is
  recommended for this deployment anyway, since it's also what keeps sessions alive across container
  restarts/redeploys. The build context is the repo root (not `server/`) because the image also needs
  the sibling `prompt-to-OCR` file at the same relative path (`../prompt-to-OCR` from `app.py`) that
  the non-Docker layout uses.
- `web/Dockerfile` — `nginx:alpine` serving `web/` as static files, configured by
  `deploy/nginx.conf` to reverse-proxy `/api/` to the `server` container over the compose network
  (`proxy_buffering off` so the NDJSON `/api/ocr` stream still arrives incrementally, long
  `proxy_read_timeout`/`proxy_send_timeout` to cover a slow LLM call with retries). This is why
  `web/app.js`'s `API_BASE` and `web/register/register.js`'s `REGISTER_ENDPOINT` resolve to a
  relative `/api` outside of `localhost`/`127.0.0.1` — see the `web/` section above.

Neither container publishes a port to the host. The VPS this was built for already runs an external
Nginx Proxy Manager (NPM) container as the internet-facing edge, so `docker-compose.yml` declares
`nginx_proxy-network` as an `external: true` network (the one NPM itself is attached to — it isn't
created by this compose file) and only the `web` service joins it, with a pinned `container_name:
ts-vision-web` so NPM's proxy host config has a stable name to target (Forward Hostname/IP
`ts-vision-web`, port `80`). `server` stays off that network entirely — it's reachable only from
`web`, over the default compose network, exactly as `deploy/nginx.conf` expects. NPM needs only one
proxy host, no custom location for `/api`: the split between static files and the API is handled
inside the `web` container by `deploy/nginx.conf`, not by NPM. If the VPS's NPM network has a
different name, update the `networks:` block in `docker-compose.yml` to match — `docker network ls`
on the VPS shows it (look for whatever network the `nginx-proxy-manager` container is attached to).

`docker-compose.yml` overrides `USERS_DB_PATH` via its `environment:` block (to a container-internal
path) even though `server/.env` also sets/omits it — compose `environment:` wins over `env_file:`, so
the same `.env` works locally and in Docker without edits. `users.db` lives in a named volume
(`users_db`, mounted at `/data`) rather than a bind mount, since bind-mounting a not-yet-existing file
path is what SQLite/Docker gets wrong (Docker creates a directory instead). There's no credential file
to bind-mount anymore — `OPENROUTER_API_KEY` is the only secret, and it travels via `env_file:` like
everything else in `server/.env`.

The public domain for this deployment (`ts.rbservice.online`) is proxied through Cloudflare in front
of NPM, and Cloudflare caches static file extensions (`.js`, `.css`, …) at the edge by default —
observed as `cache-control: max-age=14400` (4h) on `app.js`, independent of whatever the `web`
container's nginx serves. This means redeploying `web` (even with `--no-cache`) does **not** make
browsers pick up the new `app.js`/`style.css`/`index.html` immediately: Cloudflare keeps serving the
pre-deploy edge copy (`cf-cache-status: HIT`) until that 4h TTL lapses, and neither a browser hard
refresh nor a fresh container fixes it, since the request never reaches the origin. `curl -sI
https://ts.rbservice.online/app.js` showing `cf-cache-status: HIT` plus a `last-modified` older than
the deploy confirms this rather than a bad build (check `docker compose exec web wc -c
/usr/share/nginx/html/app.js` against the repo's actual byte count to rule that out first). Fastest
fix after any `web`-affecting deploy: Cloudflare dashboard → Caching → Configuration → **Purge
Cache** (Purge Everything, or a custom purge of the specific static files) — or just wait out the
remaining TTL (`max-age` minus the `age` header value from that same `curl`), since it self-resolves
with no action once the edge entry expires.

## Secrets

`server/.env` (real credentials) and `server/users.db` (hashed passwords of registered users) are
gitignored. `server/.env.example` must stay a placeholder template — never put real keys in it, since
it isn't gitignored.
