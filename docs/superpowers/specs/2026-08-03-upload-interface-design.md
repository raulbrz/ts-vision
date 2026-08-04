# Upload Interface — Design Spec

## Goal

Build a minimal, static web interface for uploading timesheet documents (PDF or image) as the first step of the ts-vision app. This phase covers **only** local file selection/preview — no network calls, no OCR integration yet. Google Vision OCR (driven by the `prompt-to-OCR` prompt) and the resulting table view are future phases, built on top of this foundation.

## Scope

In scope:
- A single HTML page with a drag-and-drop zone and a "select file" button.
- Client-side validation restricted to `.pdf`, `.png`, `.jpg`, `.jpeg` — the formats the `prompt-to-OCR` prompt is written against (scanned/photographed timesheet sheets).
- Multiple files can be added in one action (a timesheet may span several pages/photos).
- A list of selected files: thumbnail (images) or a "PDF" badge, filename, formatted file size, per-file remove button, and a "Limpar tudo" (clear all) action.
- All UI copy in Portuguese.

Out of scope (future phases):
- Any network request (uploading to a backend, calling Google Vision).
- OCR processing or table rendering/output.
- Authentication, persistence, multi-user concerns.

## Architecture

Plain static files, no build tooling, no framework:

- `web/index.html` — page structure and the file `<input>`.
- `web/style.css` — minimal, neutral styling for the dropzone and file list.
- `web/app.js` — vanilla JS: handles file selection (input change + drag/drop events), validation, in-memory list of selected files, rendering the list, remove/clear actions, and revoking object URLs for thumbnails on removal.

Rationale: the request is explicitly for a basic HTML/CSS/JS interface. A build step (Vite/React, as considered in an earlier discarded plan) adds setup and tooling overhead this phase doesn't need. The page can be opened directly in a browser or served by any static file server. When a backend is introduced later (to call Google Vision), it can live alongside this folder without forcing a rewrite of the upload UI.

## Data flow

1. User selects files via the input or drag-and-drop.
2. `app.js` validates each file's extension against the accepted list (case-insensitive).
   - Accepted files are added to an in-memory array (`{ id, file, previewUrl, isPdf }`) and rendered in the list.
   - Rejected files produce an inline error message (`"<nome>: tipo de arquivo não suportado"`) and are not added.
3. Removing a file (individually or via "Limpar tudo") drops it from the array, re-renders the list, and revokes its `URL.createObjectURL` preview if one exists.
4. No data leaves the browser in this phase.

## Error handling

- Unsupported file type: inline error text near the dropzone, file not added, existing selections untouched.
- No other failure modes exist yet (no network, no parsing) — this is deliberately minimal.

## Testing / verification

No automated test framework is introduced for this phase (no build tooling to host one). Verification is manual, in a browser:
- Dragging a PDF and a PNG onto the dropzone lists both, with a thumbnail for the PNG and a "PDF" badge for the PDF.
- Selecting a `.txt` file shows the inline error and is not added to the list.
- Remove button removes only that file; "Limpar tudo" clears the whole list.
- Selecting the same accepted file twice adds two independent entries (no dedup logic).

## Open questions / future phases (not building now)

- Backend endpoint and storage for uploaded files before sending to Google Vision.
- How `prompt-to-OCR`'s `[DATA_INICIAL]`/`[DATA_FINAL]` placeholders get filled by the user (likely a date range input added in a later phase).
- Table rendering/export of the OCR CSV result.
