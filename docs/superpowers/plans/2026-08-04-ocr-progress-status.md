# OCR Progress Status Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn `POST /api/ocr` into a streaming (newline-delimited JSON) response that emits one event per
pipeline stage, and have the frontend render those events into a live status timeline instead of a
static "Processando..." button label.

**Architecture:** `server/app.py`'s endpoint becomes a generator-backed Flask `Response` streaming NDJSON
lines; `web/app.js` reads the response body incrementally via `response.body.getReader()` and appends
each parsed event to a status timeline `<ul>`, then runs the existing table/notes rendering on the
terminal `concluido` event.

**Tech Stack:** No new dependencies — Flask's built-in streaming `Response` + generator on the backend,
the standard `ReadableStream`/`TextDecoder` browser APIs on the frontend.

## Global Constraints

- `POST /api/ocr` always returns HTTP 200 with `Content-Type: application/x-ndjson` now. Success/failure
  is signaled by the terminal event's `stage` (`concluido` vs `erro`), not by HTTP status code.
- Every event object has a `stage` key and a Portuguese `message` key. Stage names are the ones listed in
  the spec: `recebido`, `ocr_lendo`, `ocr_concluido`, `ocr_falhou`, `llm_processando`, `concluido`, `erro`.
- The `concluido` event's `csv`/`notes` fields keep the exact shape already consumed by
  `renderResultsTable`/`renderResultsNotes` in `web/app.js` — those two functions are not changed.
- Partial OCR failure must not abort the pipeline (matches current behavior) — only "zero files OCR'd" or
  an LLM call exception produce a terminal `erro` event.

---

### Task 1: Stream events from `server/app.py`

**Files:**
- Modify: `server/app.py`

**Interfaces:**
- Consumes: `ocr.extract_text` (unchanged signature), `llm.structure` (unchanged signature).
- Produces: `POST /api/ocr` now streams NDJSON lines per the event schema in the spec. Task 2's
  `web/app.js` consumes this.

- [ ] **Step 1: Replace the `ocr_endpoint` function body in `server/app.py`**

Replace the existing `@app.route("/api/ocr", ...)` function entirely with:

```python
import json


def _event(stage, message, **extra):
    payload = {"stage": stage, "message": message, **extra}
    return json.dumps(payload) + "\n"


@app.route("/api/ocr", methods=["POST"])
def ocr_endpoint():
    files = request.files.getlist("files")
    date_start = request.form.get("data_inicial", "").strip()
    date_end = request.form.get("data_final", "").strip()

    if not files:
        return Response(_event("erro", "Nenhum arquivo enviado."), mimetype="application/x-ndjson")
    if not date_start or not date_end:
        return Response(
            _event("erro", "Informe data inicial e data final."), mimetype="application/x-ndjson"
        )

    file_records = [(fs.filename, fs.read()) for fs in files]

    def generate():
        yield _event("recebido", "Arquivos recebidos, iniciando OCR...")

        ocr_texts = {}
        notes = []

        for filename, file_bytes in file_records:
            yield _event("ocr_lendo", f"Lendo {filename} com OCR...", arquivo=filename)
            try:
                ocr_texts[filename] = ocr.extract_text(file_bytes, filename)
                yield _event(
                    "ocr_concluido", f"OCR de {filename} concluído.", arquivo=filename
                )
            except Exception as exc:
                logger.exception("Falha no OCR de %s", filename)
                notes.append(f"{filename}: falha no OCR ({exc})")
                yield _event("ocr_falhou", f"Falha no OCR de {filename}.", arquivo=filename)

        if not ocr_texts:
            yield _event("erro", "Nenhum arquivo pôde ser processado pelo OCR.")
            return

        yield _event("llm_processando", "Ajustando texto extraído com IA...")

        try:
            csv_text, llm_notes = llm.structure(ocr_texts, date_start, date_end, PROMPT_TEMPLATE)
        except Exception as exc:
            logger.exception("Falha ao chamar o LLM")
            yield _event("erro", f"Falha ao processar com o LLM: {exc}")
            return

        yield _event(
            "concluido", "Concluído.", csv=csv_text, notes=notes + llm_notes
        )

    return Response(stream_with_context(generate()), mimetype="application/x-ndjson")
```

- [ ] **Step 2: Update the imports at the top of `server/app.py`**

Change:

```python
from flask import Flask, jsonify, request
```

to:

```python
from flask import Flask, Response, request, stream_with_context
```

(`jsonify` is no longer used anywhere in this file — the two early-return branches now build the NDJSON
event directly.)

- [ ] **Step 3: Verify validation paths still work, now as single-line NDJSON streams**

```bash
cd server
source venv/bin/activate
python app.py &
sleep 1.5

curl -s -N -X POST http://localhost:5000/api/ocr
echo
curl -s -N -X POST http://localhost:5000/api/ocr -F "files=@../prompt-to-OCR"
echo

kill %1
```

Expected: first call prints `{"stage": "erro", "message": "Nenhum arquivo enviado."}`; second prints
`{"stage": "erro", "message": "Informe data inicial e data final."}` (real credentials from your `.env`
are used here — this only exercises the pre-OCR validation branches, so no Vision/OpenRouter call
happens yet).

- [ ] **Step 4: Commit**

```bash
git add server/app.py
git commit -m "feat: stream OCR pipeline progress as NDJSON events"
```

---

### Task 2: Render the status timeline in `web/app.js`, `web/index.html`, `web/style.css`

**Files:**
- Modify: `web/index.html`
- Modify: `web/app.js`
- Modify: `web/style.css`

**Interfaces:**
- Consumes: the NDJSON stream from `POST /api/ocr` (Task 1) — one JSON object per line, each with
  `stage`/`message`, terminal `concluido` carrying `csv`/`notes`.
- Produces: nothing consumed by later tasks (final task of this plan).

- [ ] **Step 1: Add the status timeline container to `web/index.html`**

Insert right after the `<div id="submit-error" ...></div>` line and before `<div id="results" ...>`:

```html
      <ul id="status-timeline" class="status-timeline" hidden></ul>
```

- [ ] **Step 2: Add the element reference in `web/app.js`**

Add alongside the other `document.getElementById` constants near the top:

```javascript
const statusTimeline = document.getElementById('status-timeline');
```

- [ ] **Step 3: Add a function to append timeline entries**

Add this function near `renderResultsTable`/`renderResultsNotes`:

```javascript
function appendStatusEntry(stage, message) {
  statusTimeline.hidden = false;
  const li = document.createElement('li');
  li.className = `status-entry status-entry--${stage}`;
  li.textContent = message;
  statusTimeline.appendChild(li);
}
```

- [ ] **Step 4: Replace the submit handler's body in `web/app.js`**

Replace the entire existing `submitButton.addEventListener('click', async () => { ... });` block with:

```javascript
submitButton.addEventListener('click', async () => {
  submitError.hidden = true;
  statusTimeline.innerHTML = '';
  statusTimeline.hidden = true;

  if (files.length === 0) {
    return;
  }

  const dateInicio = dateInicioInput.value;
  const dateFim = dateFimInput.value;

  if (!dateInicio || !dateFim) {
    submitError.textContent = 'Informe data inicial e data final.';
    submitError.hidden = false;
    return;
  }

  const formData = new FormData();
  files.forEach((entry) => formData.append('files', entry.file));
  formData.append('data_inicial', dateInicio);
  formData.append('data_final', dateFim);

  submitButton.disabled = true;
  submitButton.textContent = 'Processando...';

  try {
    const response = await fetch(OCR_ENDPOINT, {
      method: 'POST',
      body: formData,
    });

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) {
        break;
      }

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop();

      for (const line of lines) {
        if (!line.trim()) {
          continue;
        }
        const event = JSON.parse(line);
        appendStatusEntry(event.stage, event.message);

        if (event.stage === 'concluido') {
          resultsSection.hidden = false;
          renderResultsTable(event.csv);
          renderResultsNotes(event.notes);
        } else if (event.stage === 'erro') {
          submitError.textContent = event.message;
          submitError.hidden = false;
        }
      }
    }
  } catch (error) {
    submitError.textContent = error.message;
    submitError.hidden = false;
  } finally {
    submitButton.disabled = files.length === 0;
    submitButton.textContent = 'Enviar para OCR';
  }
});
```

- [ ] **Step 5: Add styles for the timeline to `web/style.css`**

Append:

```css
.status-timeline {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
}

.status-entry {
  font-size: 0.85rem;
  color: #555;
  padding: 0.4rem 0.75rem;
  border-left: 3px solid #d1d5db;
  background-color: #fafafa;
}

.status-entry--concluido {
  border-left-color: #16a34a;
  color: #15803d;
  font-weight: 600;
}

.status-entry--erro,
.status-entry--ocr_falhou {
  border-left-color: #dc2626;
  color: #b91c1c;
}
```

- [ ] **Step 6: Manually verify with a stub streaming backend (no real credentials needed)**

Create a throwaway stub (not part of the repo — run directly, don't save it under `server/`) that mimics
the event sequence, to check the frontend renders incrementally without needing live Vision/OpenRouter
calls:

```bash
python3 -c "
from flask import Flask, Response, stream_with_context
from flask_cors import CORS
import json, time

app = Flask(__name__)
CORS(app)

@app.route('/api/ocr', methods=['POST'])
def ocr():
    def gen():
        events = [
            {'stage': 'recebido', 'message': 'Arquivos recebidos, iniciando OCR...'},
            {'stage': 'ocr_lendo', 'message': 'Lendo timesheet.pdf com OCR...', 'arquivo': 'timesheet.pdf'},
            {'stage': 'ocr_concluido', 'message': 'OCR de timesheet.pdf concluído.', 'arquivo': 'timesheet.pdf'},
            {'stage': 'llm_processando', 'message': 'Ajustando texto extraído com IA...'},
            {'stage': 'concluido', 'message': 'Concluído.', 'csv': 'Employee,Date\nJoao,2026-08-01', 'notes': []},
        ]
        for e in events:
            yield json.dumps(e) + '\n'
            time.sleep(0.3)
    return Response(stream_with_context(gen()), mimetype='application/x-ndjson')

app.run(port=5000)
"
```

With that running and `web/` served separately (`python3 -m http.server 8000` inside `web/`): select a
file, fill in the dates, click "Enviar para OCR." Expected: the timeline fills in one entry roughly every
0.3s (not all at once), ending with a green "Concluído." entry and the result table appearing.

- [ ] **Step 7: Commit**

```bash
git add web/index.html web/app.js web/style.css
git commit -m "feat: render live OCR pipeline status timeline"
```
