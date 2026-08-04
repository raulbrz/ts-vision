# OCR Progress Status — Design Spec

## Goal

Replace the current "black box" wait (frontend just disables the button and shows "Processando...") with
real, incremental status feedback as the backend actually works through the pipeline: per-file OCR
progress, then the LLM structuring step, then the final result or an error.

## Problem with faking it

A client-side simulated progress bar (fixed delays between canned messages) was considered and
rejected: the user's stated pain point is not knowing the *real* status, so a fake sequence would
misrepresent state whenever a step is slower/faster than expected or fails silently mid-way.

## Approach

Turn `POST /api/ocr` into a streaming response: the backend yields one newline-delimited JSON object per
pipeline stage as it happens, instead of building the whole JSON body before responding. The frontend
reads the response body incrementally (`response.body.getReader()`) and renders each event into a status
timeline as it arrives.

Alternative considered: a job-queue pattern (`POST` creates a job id, frontend polls
`GET /api/ocr/<id>` every N seconds). Rejected for now — it needs a server-side job store (even an
in-memory dict adds state/cleanup concerns) and polling latency, for no benefit over streaming in this
single-process, single-request-at-a-time tool. Streaming keeps the same one-request-one-response shape
the rest of the app already uses, with no new server-side state.

## Event schema

Each line of the streamed body is one JSON object, always with a `"stage"` key. Stages, in order:

1. `{"stage": "recebido", "message": "Arquivos recebidos, iniciando OCR..."}`
2. Per file, in order: `{"stage": "ocr_lendo", "message": "Lendo <arquivo> com OCR...", "arquivo": "<nome>"}`
   then either `{"stage": "ocr_concluido", "message": "OCR de <arquivo> concluído.", "arquivo": "<nome>"}`
   or `{"stage": "ocr_falhou", "message": "Falha no OCR de <arquivo>.", "arquivo": "<nome>"}`
3. `{"stage": "llm_processando", "message": "Ajustando texto extraído com IA..."}`
4. Terminal event, exactly one of:
   - `{"stage": "concluido", "message": "Concluído.", "csv": "<csv text>", "notes": ["...", ...]}`
   - `{"stage": "erro", "message": "<human-readable error>"}`

This replaces the current contract (`{"csv":.., "notes":..}` on 200, `{"error":..}` on 4xx/5xx). The
endpoint now always responds 200 with `Content-Type: application/x-ndjson`; success/failure is
communicated by which terminal stage arrives, not by HTTP status. Validation failures that previously
returned 400 (no files, no dates) become an immediate single-event stream: `{"stage": "recebido"}` is
skipped and the body is just one `{"stage": "erro", "message": "..."}` line.

Partial OCR failure keeps today's behavior: one file failing OCR doesn't stop the pipeline — it's
reported as `ocr_falhou`, execution continues to the remaining files and then the LLM step, and that
file's failure is folded into the final `concluido` event's `notes` array (same as today). Only "no file
could be OCR'd at all" or "the LLM call itself failed" produce a terminal `erro` event.

## Frontend rendering

A status timeline (`<ul>`, newest entry at the bottom) appended to on each event, replacing the current
plain button-text swap. Each entry shows the stage's `message`. The `concluido`/`erro` terminal entry is
styled distinctly (success vs error color) and, on `concluido`, the existing table/notes rendering runs
exactly as it does today — the `csv`/`notes` payload shape inside the terminal event is unchanged from
what `renderResultsTable`/`renderResultsNotes` already expect.

The timeline is cleared at the start of each submit and hidden until the first event arrives.

## Error handling

- Network-level failure (fetch rejects, e.g. backend not running): caught the same way as today —
  `submitError` inline message, timeline shows what was received so far (if anything) plus a final
  "Falha de conexão" entry.
- Malformed/partial JSON line (stream cut mid-object): buffered and only parsed once a full line
  (`\n`-terminated) is available — standard incremental NDJSON parsing, not a new failure mode.

## Testing / verification

Still no automated test framework (matches the rest of the project). Verification:
- Backend: `curl -N` (no buffering) against the endpoint with dummy credentials, confirm multiple lines
  arrive over time rather than one blob at the end (can be approximated with a `time.sleep` removed
  after verification, or observed via the real per-file loop timing once real credentials are used).
- Frontend: a stub Flask backend that streams canned events (same pattern used to verify the previous
  feature) drives a headless-browser check that the timeline fills in incrementally and the final table
  renders.
