# Unified Multimodal OCR — Design Spec

## Goal

Replace the two-step pipeline (Google Cloud Vision OCR → text handed to an LLM to structure) with a
single call to a multimodal LLM via OpenRouter that reads the timesheet images directly and returns
the structured CSV. This removes a network round-trip and, more importantly, fixes a structural bug in
the current pipeline: `ocr.py` only keeps `full_text_annotation.text` — Vision's own reading-order
flattening of the page — discarding all bounding-box/layout information. The LLM step then has to
reconstruct a row/column table from a linear string with no grid information, which is fragile for a
handwritten form that *is* a grid. A vision-capable model looking at the actual image can use the
visual table structure directly, which is what these models are trained for.

## Decision (validated by the user's own testing, not this session)

- Model: `google/gemma-4-26b-a4b-it:free` on OpenRouter, set as the new `OPENROUTER_MODEL` default.
- Cloud Vision is fully removed — no fallback, no dual-path.
- Input files stay PDF/PNG/JPG/JPEG (unchanged, matches `web/`'s `ACCEPTED_EXTENSIONS`). PDFs are
  common, so PDF pages must be converted to images before the call — most OpenRouter vision models
  accept `image_url` content parts (base64 data URIs), not raw PDF bytes.

## Scope

In scope:
- A new `server/attachments.py` module: turns uploaded file bytes into a list of OpenAI/OpenRouter-style
  `image_url` content parts — one per PDF page (rendered via PyMuPDF, no system Poppler dependency
  needed) or one for a plain image file (base64 of the original bytes, mime type from extension).
- Rewriting `server/llm.py`'s message-building to a multimodal `content` array: one text part with the
  `prompt-to-OCR` instructions (date range substituted, unchanged file otherwise — it already says "as
  imagens anexadas," which becomes literally true), then per file a text label (`--- Arquivo: X ---`)
  followed by that file's image parts. The retry/backoff wrapper (`_post_with_retry`) and
  `_split_csv_and_notes` parsing are unchanged — only what goes into `messages` changes.
- `server/app.py`'s streaming pipeline: the per-file OCR stages become per-file "prepare for the AI"
  stages (image conversion, not text extraction) — `ocr_lendo`/`ocr_concluido`/`ocr_falhou` become
  `preparando`/`preparado`/`preparo_falhou`. `llm_processando` and `llm_retentando` stay conceptually
  the same (single call, retried on transient failure) but now carry image attachments instead of OCR
  text. `concluido`/`erro` are unchanged.
- Deleting `server/ocr.py` and the `google-cloud-vision` dependency; adding `PyMuPDF` for PDF→image
  rendering; dropping `GOOGLE_APPLICATION_CREDENTIALS` from `config.py`/`.env.example`/`README.md`/
  `docker-compose.yml` (no more GCP service account needed anywhere).
- Frontend: `web/app.js`'s special-case reveal for `ocr_concluido`'s `texto` field is removed (there's
  no extracted text anymore, only prepared images — not useful to show inline); the `llm_processando`
  prompt reveal stays, now listing filenames + page counts instead of raw OCR text. `web/style.css`'s
  `.status-entry--ocr_falhou` rule is renamed to `.status-entry--preparo_falhou`.
- Docs: `CLAUDE.md`, `server/README.md`, `docker-compose.yml`/`deploy/` notes, `BACKLOG.md` updated to
  match — the 5-page-PDF-truncation backlog item is resolved by construction (PyMuPDF has no page cap).

Out of scope:
- Any change to the CSV schema or business rules in `prompt-to-OCR` — those are independent of how the
  document gets to the model.
- Capping pages per file. Cloud Vision's sync API forced a 5-page cap; PyMuPDF doesn't have that
  constraint, and timesheet scans are short, so no artificial cap is introduced. If real usage shows
  huge multi-page batches blowing up payload size/cost, that's a follow-up, not part of this change.
- Auth, rate limiting, and everything else outside the OCR/LLM pipeline — untouched.

## Architecture

```
server/app.py (unchanged shape: NDJSON streaming generator)
  for each uploaded file:
    yield preparando -> attachments.to_image_parts(bytes, filename) -> yield preparado/preparo_falhou
  yield llm_processando (prompt preview: instructions + filenames/page counts)
  llm.structure(attachments_dict, date_start, date_end, PROMPT_TEMPLATE)
    -> builds one multimodal `messages` payload (text + image_url parts)
    -> POST to OpenRouter via existing _post_with_retry (retry events unchanged)
    -> _split_csv_and_notes(content) (unchanged)
  yield concluido {csv, notes} | erro
```

`attachments.py` is the only new module:
- `to_image_parts(file_bytes: bytes, filename: str) -> list[dict]` — dispatches on `.pdf` suffix like
  `ocr.py` did; PDFs render each page via PyMuPDF (`page.get_pixmap(dpi=200).tobytes("png")`) — 200 DPI
  balances legibility of handwriting against base64 payload size; plain images pass through as-is with
  a mime type derived from the extension (`.png` → `image/png`, `.jpg`/`.jpeg` → `image/jpeg`).
- Each part is `{"type": "image_url", "image_url": {"url": f"data:{mime};base64,{...}"}}`, the standard
  OpenAI-compatible shape OpenRouter expects.

`llm.py` changes:
- `build_prompt` (used both for the real call and the `llm_processando` preview event) now takes
  `attachments: dict[str, list[dict]]` and returns the **text-only** instruction preview (filenames +
  page counts, not the image data — showing base64 blobs in the UI reveal panel is useless).
- A new `build_messages(attachments, date_start, date_end, prompt_template) -> list[dict]` builds the
  actual multimodal message sent to OpenRouter (text instructions + per-file label + image parts).
- `structure()` calls `build_messages` instead of building a plain string, otherwise unchanged
  (`_post_with_retry`, `_split_csv_and_notes` stay as-is).

## Data flow

1. User selects files + date range, clicks "Enviar para OCR" (unchanged UI).
2. `app.py` reads each file's bytes, calls `attachments.to_image_parts` per file inside the streaming
   generator — failures (corrupt PDF, unreadable image) are caught per file, recorded as a note, and
   that file is skipped, same partial-failure contract as today's OCR step.
3. Once all files are prepared (or skipped), one `llm.structure(...)` call is made with all remaining
   files' image parts in a single multimodal message.
4. Response is parsed into `(csv_text, notes)` exactly as today; `concluido`/`erro` events are
   unchanged in shape, so the frontend's success/error rendering needs no changes there.

## Error handling

- File can't be converted to image(s) (corrupt PDF, non-image bytes despite the extension): caught in
  `app.py`'s per-file loop, becomes a `preparo_falhou` event + a note, file excluded from the LLM call
  — mirrors today's `ocr_falhou` handling exactly, just renamed.
- All files fail to prepare: `erro` event, same as today's "no OCR text" case.
- OpenRouter call fails (network/429/5xx): unchanged — `_post_with_retry` handles transient failures,
  non-transient ones propagate as an `erro` event.
- Missing `OPENROUTER_API_KEY`: unchanged, `config.validate()` fails fast at startup.
- `GOOGLE_APPLICATION_CREDENTIALS` is no longer read or validated anywhere — removing it from `.env`
  has no effect after this change ships.

## Testing / verification

Same constraints as the original pipeline (no test framework, no free way to exercise a real
OpenRouter call):
- `attachments.to_image_parts` is a pure function (bytes in, list of dicts out) — verify PDF page
  count and image mime-type dispatch with a one-off `python3 -c` script against a real small PDF/image
  fixture (no network needed, PyMuPDF is local).
- `llm.build_prompt`/`build_messages` are pure — verify shape with a one-off script using fake
  attachment dicts.
- `app.py`'s validation paths (empty files, empty dates) are checked with `curl`, same as before.
- The actual OpenRouter multimodal call and real handwriting accuracy need a live `OPENROUTER_API_KEY`
  and a real timesheet scan — can't be exercised in this environment; the user already validated model
  choice/accuracy manually before this session.

## Configuration required from the user

- `OPENROUTER_API_KEY` (unchanged) — same OpenRouter account as before.
- `OPENROUTER_MODEL` — new default `google/gemma-4-26b-a4b-it:free`, overridable, as before.
- `GOOGLE_APPLICATION_CREDENTIALS` / the GCP service account JSON — no longer needed; user can remove
  it from `.env` and delete the credentials file once this ships (documented in the plan, not deleted
  automatically since it's the user's file outside version control).
