# OCR Pipeline — Design Spec

## Goal

Wire the existing static upload page (`web/`) to a real OCR pipeline: send the selected files to a Python backend, extract text with Google Cloud Vision, apply the `prompt-to-OCR` rules with a cheap LLM via OpenRouter, and render the resulting CSV as an HTML table in the browser.

## Scope

In scope:
- A Python backend (`server/`) with one endpoint that accepts multiple files (PDF/PNG/JPG) and a date range, runs the two-step pipeline below, and returns CSV text + attention notes as JSON.
- Step 1 — OCR: Google Cloud Vision `DOCUMENT_TEXT_DETECTION` extracts raw text per file/page.
- Step 2 — Structuring: the raw OCR text (labeled by source file) is sent, together with the full `prompt-to-OCR` prompt text, to an LLM via OpenRouter. The model applies the prompt's conversion/formatting/idem rules and returns the CSV plus a short list of "pontos de atenção."
- Frontend changes: an "Enviar" button (enabled once files are selected) plus two date inputs for `[DATA_INICIAL]`/`[DATA_FINAL]` (the prompt requires this range to filter rows). On success, render the CSV as an HTML `<table>` below the upload list, and show the attention notes as a bullet list. On failure, show an inline error.
- CORS enabled on the backend so the static frontend (served separately) can call it.

Out of scope (future phases):
- Authentication / multi-user isolation.
- Persisting uploads or results (everything is processed in-memory per request and discarded after the response).
- CSV export/download button (can be added trivially later — not requested yet).
- Retry/queue handling for large batches — single synchronous request/response.

## Architecture

```
web/ (static, unchanged tech)          server/ (new, Python)
┌─────────────────────────┐            ┌──────────────────────────────┐
│ index.html / style.css   │  multipart │ app.py (Flask + flask-cors)  │
│ app.js                   │──POST────► │  /api/ocr                   │
│  - existing upload UI    │  files +   │                              │
│  - + date range inputs   │  dates     │  ocr.py                     │
│  - + "Enviar" button     │            │   - Cloud Vision client      │
│  - + result table render │  ◄─JSON─── │   - extract_text(file)       │
└─────────────────────────┘   {csv,     │                              │
                               notes}   │  llm.py                     │
                                        │   - OpenRouter client (HTTP) │
                                        │   - structure(prompt, texts, │
                                        │       date_range) -> (csv,   │
                                        │       notes)                 │
                                        └──────────────────────────────┘
```

- `server/app.py` — Flask app, single route `POST /api/ocr`. Reads uploaded files, calls `ocr.extract_text` per file, calls `llm.structure` once with all extracted texts, returns `{ "csv": "...", "notes": ["...", ...] }` or `{ "error": "..." }` with an appropriate HTTP status.
- `server/ocr.py` — thin wrapper around `google-cloud-vision`. Function `extract_text(file_bytes: bytes, filename: str) -> str`. PDFs use Vision's file annotation (`batch_annotate_files`, `DOCUMENT_TEXT_DETECTION`, mime type `application/pdf`, first pages only — Vision's sync API caps at 5 pages per file, acceptable for a timesheet scan); images use `document_text_detection`.
- `server/llm.py` — thin wrapper around OpenRouter's OpenAI-compatible chat completions endpoint (plain `requests` call, no SDK needed). Function `structure(ocr_texts: dict[str, str], date_start: str, date_end: str) -> tuple[str, list[str]]`. Builds the user message from the `prompt-to-OCR` file content (with `[DATA_INICIAL]`/`[DATA_FINAL]` substituted) plus the labeled OCR text blocks, parses the model's response into the CSV block and the "pontos de atenção" list (split on the model's own section headers, as instructed by the prompt's own "SAÍDA" section).
- `server/config.py` — reads `GOOGLE_APPLICATION_CREDENTIALS` (standard Google SDK env var, unchanged), `OPENROUTER_API_KEY`, `OPENROUTER_MODEL` (default `openai/gpt-4o-mini`, overridable) from environment / `.env`.
- `web/app.js` — extended (not rewritten) with: state for the date range inputs, a submit handler that builds a `FormData` from the current file list plus dates, `fetch('http://localhost:5000/api/ocr', { method: 'POST', body: formData })`, and rendering of the returned CSV into a `<table>` (split CSV by lines/commas — simple parsing, no library, since the LLM output has no embedded commas per the prompt's field definitions) and the notes into a `<ul>`.

Rationale: keeping OCR (deterministic, cheap, good at raw text extraction) and structuring (rule application, needs reasoning) as two separate steps/functions makes each independently testable and swappable — e.g., the LLM step can be pointed at a different OpenRouter model via env var without touching the OCR code.

## Data flow

1. User selects files in the existing upload UI, fills in the two date fields, clicks "Enviar."
2. `app.js` POSTs a `multipart/form-data` request to `POST /api/ocr` with all files plus `data_inicial`/`data_final` fields.
3. `app.py` iterates files, calls `ocr.extract_text` for each, building `{ filename: raw_text }`.
4. `app.py` calls `llm.structure(ocr_texts, data_inicial, data_final)`.
5. `llm.structure` sends one chat completion request to OpenRouter with the assembled prompt; parses the response into `(csv_text, notes)`.
6. `app.py` returns `{ "csv": csv_text, "notes": notes }` as JSON (200) or `{ "error": message }` (4xx/5xx) on failure at any step.
7. `app.js` renders the table/notes, or the error message inline.

## Error handling

- No files selected when "Enviar" is clicked: button stays disabled (frontend-only guard, same pattern as existing validation).
- Date fields empty: inline validation message, request not sent.
- Cloud Vision call fails for a given file (bad credentials, API error, unsupported/corrupt file): that file's error is included in the response's `notes` list and the file is skipped in the OCR text sent to the LLM step (partial results still returned for the other files) — logged server-side with the filename.
- OpenRouter call fails (network, auth, rate limit): endpoint returns 502 with `{ "error": "Falha ao processar com o LLM: <detail>" }`; frontend shows this inline, nothing is rendered.
- Missing `OPENROUTER_API_KEY` or Google credentials at startup: `app.py` fails fast with a clear log message on boot rather than failing per-request.

## Testing / verification

No automated tests for the LLM step (non-deterministic, costs money per call) or Cloud Vision call (needs real credentials) in this phase. Verification is manual:
- `ocr.extract_text` and `llm.structure` are pure functions with mockable boundaries (bytes in, text out / dict in, tuple out) so they *could* be unit tested with mocked clients later — not required for this phase.
- Manual end-to-end check (documented in the plan): run the backend locally with real credentials, upload a sample timesheet image through the browser, confirm a table renders with plausible rows.

## Configuration required from the user (not automatable)

- A GCP project with the Vision API enabled and a service account key (JSON) downloaded, referenced via `GOOGLE_APPLICATION_CREDENTIALS`.
- An OpenRouter account and API key, set as `OPENROUTER_API_KEY`.
- Both documented in `server/.env.example` and `server/README.md` (created in the plan) with setup steps, since I cannot create these credentials on the user's behalf.
