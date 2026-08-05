# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

ts-vision extracts data from handwritten "GOLD TIGERS SERVICES TIMESHEETS" (PDF/image scans) into a
CSV table. A static frontend uploads files; a Python backend runs them through a two-step OCR pipeline
and streams progress back as the pipeline runs. All UI copy and API error messages are in Portuguese.

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

- Backend request-validation and pure-function logic (e.g. `llm._split_csv_and_notes`) can be checked
  with one-off `python3 -c "..."` snippets — see the task steps in `docs/superpowers/plans/` for the
  pattern used so far.
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
`concluido` event additionally renders the results table/notes, and an `erro` event surfaces
`submitError`. `clearResults()` (bound to `#clear-results`) resets the table, notes, timeline, and
error banner back to their empty/hidden state without touching the selected-files list. Note:
`[hidden]` alone doesn't hide elements whose class also sets `display` (e.g. `.results { display:
flex }` beats the UA default `[hidden] { display: none }` at equal specificity) — `style.css` has a
global `[hidden] { display: none !important; }` rule to force it, so any new toggleable section should
rely on the `hidden` attribute rather than a bespoke `.is-visible`-style class.

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

`config.py` reads `GOOGLE_APPLICATION_CREDENTIALS` / `OPENROUTER_API_KEY` / `OPENROUTER_MODEL` from
`server/.env` (via `python-dotenv`) and `config.validate()` is called at import time in `app.py`, so a
missing credential fails the process at startup rather than on the first request.

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

`server/.env` (real credentials) and `server/*.json` (GCP service account keys) are gitignored.
`server/.env.example` must stay a placeholder template — never put real keys in it, since it isn't
gitignored.
