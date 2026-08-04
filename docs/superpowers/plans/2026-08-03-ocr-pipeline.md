# OCR Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire the existing static upload page to a real OCR pipeline: a Python backend that extracts text with Google Cloud Vision, structures it into CSV via an OpenRouter LLM call following the `prompt-to-OCR` rules, and a frontend that submits files + a date range and renders the returned CSV as a table.

**Architecture:** Flask backend in `server/` with one endpoint (`POST /api/ocr`) that orchestrates two pure-function modules — `ocr.py` (Cloud Vision) and `llm.py` (OpenRouter) — and the existing `web/app.js` extended with a submit button, date inputs, and table rendering.

**Tech Stack:** Python 3, Flask, flask-cors, google-cloud-vision, requests, python-dotenv. Frontend stays vanilla JS (no new dependencies).

## Global Constraints

- Backend lives in `server/` at repo root, run as a standalone script (`python app.py`), not packaged — flat imports (`import config`, not relative imports).
- Config comes from environment variables: `GOOGLE_APPLICATION_CREDENTIALS`, `OPENROUTER_API_KEY`, `OPENROUTER_MODEL` (default `openai/gpt-4o-mini`). Loaded via `python-dotenv` from a `.env` file in `server/`, which is gitignored.
- No automated test framework introduced (matches the spec) — verification is manual: imports, `curl`, and browser checks. Where a function is pure and cheap to call (e.g. CSV/notes splitting), verify it with a one-off `python3 -c` invocation rather than a persisted test file.
- All new user-facing copy (frontend and API error messages) is in Portuguese.
- The backend must fail fast and loudly at startup if required env vars are missing, not fail per-request.

---

### Task 1: Backend scaffolding — config, dependencies, env template, setup docs

**Files:**
- Create: `server/config.py`
- Create: `server/requirements.txt`
- Create: `server/.env.example`
- Create: `server/README.md`
- Modify: `.gitignore` (create if still absent — it was deleted earlier in this project's history)

**Interfaces:**
- Produces: `config.GOOGLE_APPLICATION_CREDENTIALS: str | None`, `config.OPENROUTER_API_KEY: str | None`, `config.OPENROUTER_MODEL: str`, `config.validate() -> None` (raises `RuntimeError` listing missing required vars). Tasks 3 and 4 import these.

- [ ] **Step 1: Create `server/requirements.txt`**

```
Flask
flask-cors
google-cloud-vision
python-dotenv
requests
```

- [ ] **Step 2: Create `server/.env.example`**

```
GOOGLE_APPLICATION_CREDENTIALS=/caminho/absoluto/para/service-account.json
OPENROUTER_API_KEY=sk-or-v1-xxxxxxxx
OPENROUTER_MODEL=openai/gpt-4o-mini
```

- [ ] **Step 3: Create `server/config.py`**

```python
import os

from dotenv import load_dotenv

load_dotenv()

GOOGLE_APPLICATION_CREDENTIALS = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")
OPENROUTER_MODEL = os.environ.get("OPENROUTER_MODEL", "openai/gpt-4o-mini")


def validate() -> None:
    missing = []
    if not GOOGLE_APPLICATION_CREDENTIALS:
        missing.append("GOOGLE_APPLICATION_CREDENTIALS")
    if not OPENROUTER_API_KEY:
        missing.append("OPENROUTER_API_KEY")
    if missing:
        raise RuntimeError(
            "Variáveis de ambiente obrigatórias ausentes: "
            + ", ".join(missing)
            + ". Veja server/.env.example."
        )
```

- [ ] **Step 4: Ensure `.gitignore` exists at repo root and ignores `server/.env` and the Python venv**

Check current content first:

```bash
cat .gitignore 2>/dev/null || echo "(missing)"
```

Write/append so it contains at least:

```
.worktrees/
server/.env
server/venv/
server/__pycache__/
```

- [ ] **Step 5: Create `server/README.md`**

```markdown
# ts-vision backend

Backend Python que recebe os arquivos enviados pela interface em `web/`, extrai texto
com o Google Cloud Vision e estrutura o resultado em CSV usando um LLM via OpenRouter.

## Setup

1. Crie um ambiente virtual e instale as dependências:

   ```bash
   cd server
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

2. Copie `.env.example` para `.env` e preencha:

   ```bash
   cp .env.example .env
   ```

   - `GOOGLE_APPLICATION_CREDENTIALS`: caminho para o JSON de uma service account do
     Google Cloud com a API **Cloud Vision** habilitada no projeto
     (console.cloud.google.com → APIs & Services → Library → Cloud Vision API → Enable;
     depois IAM & Admin → Service Accounts → Create → Keys → Create key → JSON).
   - `OPENROUTER_API_KEY`: chave gerada em openrouter.ai/keys.
   - `OPENROUTER_MODEL`: modelo a usar (padrão `openai/gpt-4o-mini`; qualquer modelo
     listado em openrouter.ai/models funciona, desde que suporte instruções longas).

3. Rode o servidor:

   ```bash
   python app.py
   ```

   O servidor sobe em `http://localhost:5000`.
```

- [ ] **Step 6: Verify `config.py` fails fast without env vars, and passes with dummy ones**

```bash
cd server
python3 -c "import config; config.validate()"
```

Expected: raises `RuntimeError: Variáveis de ambiente obrigatórias ausentes: GOOGLE_APPLICATION_CREDENTIALS, OPENROUTER_API_KEY. Veja server/.env.example.`

```bash
GOOGLE_APPLICATION_CREDENTIALS=/tmp/fake.json OPENROUTER_API_KEY=fake python3 -c "import config; config.validate(); print('ok')"
```

Expected: prints `ok`.

- [ ] **Step 7: Commit**

```bash
cd ..
git add server/config.py server/requirements.txt server/.env.example server/README.md .gitignore
git commit -m "chore: scaffold Python backend (config, deps, setup docs)"
```

---

### Task 2: `ocr.py` — Google Cloud Vision text extraction

**Files:**
- Create: `server/ocr.py`

**Interfaces:**
- Consumes: nothing beyond the `google-cloud-vision` package (Task 1 dependency).
- Produces: `extract_text(file_bytes: bytes, filename: str) -> str`. Task 4's `app.py` calls this per uploaded file.

- [ ] **Step 1: Create `server/ocr.py`**

```python
from google.cloud import vision


def extract_text(file_bytes: bytes, filename: str) -> str:
    client = vision.ImageAnnotatorClient()

    if filename.lower().endswith(".pdf"):
        return _extract_text_from_pdf(client, file_bytes)
    return _extract_text_from_image(client, file_bytes)


def _extract_text_from_image(client: "vision.ImageAnnotatorClient", file_bytes: bytes) -> str:
    image = vision.Image(content=file_bytes)
    response = client.document_text_detection(image=image)
    if response.error.message:
        raise RuntimeError(response.error.message)
    return response.full_text_annotation.text


def _extract_text_from_pdf(client: "vision.ImageAnnotatorClient", file_bytes: bytes) -> str:
    input_config = vision.InputConfig(content=file_bytes, mime_type="application/pdf")
    feature = vision.Feature(type_=vision.Feature.Type.DOCUMENT_TEXT_DETECTION)
    request = vision.AnnotateFileRequest(input_config=input_config, features=[feature])

    response = client.batch_annotate_files(requests=[request])
    file_response = response.responses[0]

    pages_text = []
    for page_response in file_response.responses:
        if page_response.error.message:
            raise RuntimeError(page_response.error.message)
        pages_text.append(page_response.full_text_annotation.text)
    return "\n".join(pages_text)
```

Note: Cloud Vision's synchronous `batch_annotate_files` caps PDF processing at 5 pages — acceptable for a single timesheet scan; multi-page batches beyond that are out of scope for this phase.

- [ ] **Step 2: Verify the module imports cleanly and the dispatch logic is correct**

```bash
cd server
python3 -c "
import ocr
assert ocr.extract_text.__module__ == 'ocr'
print('ocr.py imports OK, extract_text is defined')
"
```

Expected: prints the confirmation line with no import errors. (A real Vision API call requires live credentials, which aren't available in this environment — that end-to-end check happens later, once the user has configured `GOOGLE_APPLICATION_CREDENTIALS` for real, per `server/README.md`.)

- [ ] **Step 3: Commit**

```bash
cd ..
git add server/ocr.py
git commit -m "feat: add Cloud Vision OCR text extraction module"
```

---

### Task 3: `llm.py` — OpenRouter structuring call

**Files:**
- Create: `server/llm.py`

**Interfaces:**
- Consumes: `config.OPENROUTER_API_KEY`, `config.OPENROUTER_MODEL` (Task 1).
- Produces: `structure(ocr_texts: dict[str, str], date_start: str, date_end: str, prompt_template: str) -> tuple[str, list[str]]`. Task 4's `app.py` calls this once per request with the dict of `{filename: extracted_text}` from Task 2.

- [ ] **Step 1: Create `server/llm.py`**

```python
import re

import requests

import config

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


def structure(
    ocr_texts: dict, date_start: str, date_end: str, prompt_template: str
) -> tuple:
    prompt = prompt_template.replace("[DATA_INICIAL]", date_start).replace(
        "[DATA_FINAL]", date_end
    )

    sources = "\n\n".join(
        f"--- Texto extraído de {filename} ---\n{text}"
        for filename, text in ocr_texts.items()
    )

    user_message = f"{prompt}\n\nTEXTOS EXTRAÍDOS POR OCR:\n\n{sources}"

    response = requests.post(
        OPENROUTER_URL,
        headers={
            "Authorization": f"Bearer {config.OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": config.OPENROUTER_MODEL,
            "messages": [{"role": "user", "content": user_message}],
        },
        timeout=120,
    )
    response.raise_for_status()
    content = response.json()["choices"][0]["message"]["content"]

    return _split_csv_and_notes(content)


def _split_csv_and_notes(content: str) -> tuple:
    lines = content.strip().splitlines()
    csv_lines = []
    notes = []
    in_notes = False

    for line in lines:
        if re.search(r"pontos? de atenç[aã]o", line, re.IGNORECASE):
            in_notes = True
            continue
        if in_notes:
            stripped = line.strip(" -*\t")
            if stripped:
                notes.append(stripped)
        elif line.strip():
            csv_lines.append(line)

    return "\n".join(csv_lines), notes
```

- [ ] **Step 2: Verify `_split_csv_and_notes` with a one-off call (pure function, no network needed)**

```bash
cd server
python3 -c "
from llm import _split_csv_and_notes

sample = '''Employee,Date,entrada1,saida1,entrada2,saida2
Joao,2026-08-01,08:00,12:00,13:00,17:00

Pontos de atenção:
- Data da linha 2 estava rasurada
- Campo de almoco ilegivel na segunda folha'''

csv_text, notes = _split_csv_and_notes(sample)
assert csv_text.startswith('Employee,Date')
assert len(notes) == 2
assert notes[0] == 'Data da linha 2 estava rasurada'
print('csv:', repr(csv_text))
print('notes:', notes)
print('OK')
"
```

Expected: prints the parsed CSV block, the two notes, and `OK`.

- [ ] **Step 3: Commit**

```bash
cd ..
git add server/llm.py
git commit -m "feat: add OpenRouter structuring call and CSV/notes parsing"
```

---

### Task 4: `app.py` — Flask endpoint wiring OCR + LLM together

**Files:**
- Create: `server/app.py`

**Interfaces:**
- Consumes: `config.validate` (Task 1), `ocr.extract_text` (Task 2), `llm.structure` (Task 3).
- Produces: `POST /api/ocr` HTTP endpoint. Task 5's `web/app.js` calls this.

- [ ] **Step 1: Create `server/app.py`**

```python
import logging
import os

from flask import Flask, jsonify, request
from flask_cors import CORS

import config
import llm
import ocr

config.validate()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROMPT_PATH = os.path.join(BASE_DIR, "..", "prompt-to-OCR")

with open(PROMPT_PATH, "r", encoding="utf-8") as f:
    PROMPT_TEMPLATE = f.read()

app = Flask(__name__)
CORS(app)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@app.route("/api/ocr", methods=["POST"])
def ocr_endpoint():
    files = request.files.getlist("files")
    date_start = request.form.get("data_inicial", "").strip()
    date_end = request.form.get("data_final", "").strip()

    if not files:
        return jsonify({"error": "Nenhum arquivo enviado."}), 400
    if not date_start or not date_end:
        return jsonify({"error": "Informe data inicial e data final."}), 400

    ocr_texts = {}
    notes = []

    for file_storage in files:
        filename = file_storage.filename
        file_bytes = file_storage.read()
        try:
            ocr_texts[filename] = ocr.extract_text(file_bytes, filename)
        except Exception as exc:
            logger.exception("Falha no OCR de %s", filename)
            notes.append(f"{filename}: falha no OCR ({exc})")

    if not ocr_texts:
        return jsonify({"error": "Nenhum arquivo pôde ser processado pelo OCR."}), 502

    try:
        csv_text, llm_notes = llm.structure(ocr_texts, date_start, date_end, PROMPT_TEMPLATE)
    except Exception as exc:
        logger.exception("Falha ao chamar o LLM")
        return jsonify({"error": f"Falha ao processar com o LLM: {exc}"}), 502

    return jsonify({"csv": csv_text, "notes": notes + llm_notes})


if __name__ == "__main__":
    app.run(port=5000, debug=True)
```

- [ ] **Step 2: Verify startup fails fast without credentials**

```bash
cd server
python3 app.py
```

Expected: exits immediately with the `RuntimeError` from `config.validate()` (no env vars set in this environment) — confirms the fail-fast behavior from Task 1.

- [ ] **Step 3: Verify the endpoint's request-validation paths with dummy credentials**

Dummy values are enough here because these two checks (`files` empty, dates empty) return before any Cloud Vision or OpenRouter call is made.

```bash
GOOGLE_APPLICATION_CREDENTIALS=/tmp/fake.json OPENROUTER_API_KEY=fake python3 app.py &
sleep 1

curl -s -X POST http://localhost:5000/api/ocr
echo
curl -s -X POST http://localhost:5000/api/ocr -F "files=@../prompt-to-OCR"
echo

kill %1
```

Expected: first `curl` returns `{"error":"Nenhum arquivo enviado."}`; second returns `{"error":"Informe data inicial e data final."}`.

- [ ] **Step 4: Commit**

```bash
cd ..
git add server/app.py
git commit -m "feat: add /api/ocr endpoint wiring OCR and LLM steps together"
```

---

### Task 5: Frontend integration — date range, submit button, table rendering

**Files:**
- Modify: `web/index.html`
- Modify: `web/app.js`
- Modify: `web/style.css`

**Interfaces:**
- Consumes: `POST http://localhost:5000/api/ocr` (Task 4), returning `{ "csv": string, "notes": string[] }` on success (200) or `{ "error": string }` on failure.
- Produces: nothing consumed by later tasks (final task of this plan).

- [ ] **Step 1: Add date inputs, submit button, and results containers to `web/index.html`**

Insert this block right after the closing `</div>` of `#upload-list` (still inside `<section class="upload-zone">`, before that section's closing `</section>`):

```html
      <div class="upload-actions">
        <div class="date-range">
          <label>
            Data inicial
            <input type="date" id="date-inicio" />
          </label>
          <label>
            Data final
            <input type="date" id="date-fim" />
          </label>
        </div>
        <button type="button" id="submit-button" disabled>Enviar para OCR</button>
      </div>

      <div id="submit-error" class="upload-errors" hidden></div>

      <div id="results" class="results" hidden>
        <h2>Resultado</h2>
        <div class="results-table-wrapper">
          <table id="results-table"></table>
        </div>
        <div id="results-notes-wrapper" hidden>
          <h3>Pontos de atenção</h3>
          <ul id="results-notes"></ul>
        </div>
      </div>
```

- [ ] **Step 2: Add new element references and the OCR endpoint constant to the top of `web/app.js`**

Add right after the existing `const clearAllButton = ...` line:

```javascript
const submitButton = document.getElementById('submit-button');
const dateInicioInput = document.getElementById('date-inicio');
const dateFimInput = document.getElementById('date-fim');
const submitError = document.getElementById('submit-error');
const resultsSection = document.getElementById('results');
const resultsNotesWrapper = document.getElementById('results-notes-wrapper');
const resultsNotesList = document.getElementById('results-notes');

const OCR_ENDPOINT = 'http://localhost:5000/api/ocr';
```

- [ ] **Step 3: Enable/disable the submit button whenever the file list changes**

In `renderList()`, right after the existing `uploadList.hidden = false;` / `uploadList.hidden = true;` branching (i.e. at the very top of the function, before the `if (files.length === 0)` check), add:

```javascript
  submitButton.disabled = files.length === 0;
```

So the top of `renderList()` reads:

```javascript
function renderList() {
  uploadItems.innerHTML = '';
  submitButton.disabled = files.length === 0;

  if (files.length === 0) {
    uploadList.hidden = true;
    return;
  }
  // ...unchanged...
```

- [ ] **Step 4: Add table/notes rendering functions and the submit handler to the end of `web/app.js`**

```javascript
function renderResultsTable(csvText) {
  const table = document.getElementById('results-table');
  table.innerHTML = '';

  const rows = csvText
    .trim()
    .split('\n')
    .map((line) => line.split(','));

  if (rows.length === 0) {
    return;
  }

  const thead = document.createElement('thead');
  const headerRow = document.createElement('tr');
  rows[0].forEach((cell) => {
    const th = document.createElement('th');
    th.textContent = cell;
    headerRow.appendChild(th);
  });
  thead.appendChild(headerRow);
  table.appendChild(thead);

  const tbody = document.createElement('tbody');
  rows.slice(1).forEach((row) => {
    const tr = document.createElement('tr');
    row.forEach((cell) => {
      const td = document.createElement('td');
      td.textContent = cell;
      tr.appendChild(td);
    });
    tbody.appendChild(tr);
  });
  table.appendChild(tbody);
}

function renderResultsNotes(notes) {
  resultsNotesList.innerHTML = '';
  if (!notes || notes.length === 0) {
    resultsNotesWrapper.hidden = true;
    return;
  }
  notes.forEach((note) => {
    const li = document.createElement('li');
    li.textContent = note;
    resultsNotesList.appendChild(li);
  });
  resultsNotesWrapper.hidden = false;
}

submitButton.addEventListener('click', async () => {
  submitError.hidden = true;

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
    const data = await response.json();

    if (!response.ok) {
      throw new Error(data.error || 'Erro desconhecido');
    }

    resultsSection.hidden = false;
    renderResultsTable(data.csv);
    renderResultsNotes(data.notes);
  } catch (error) {
    submitError.textContent = error.message;
    submitError.hidden = false;
  } finally {
    submitButton.disabled = files.length === 0;
    submitButton.textContent = 'Enviar para OCR';
  }
});
```

- [ ] **Step 5: Add styles for the new elements to `web/style.css`**

Append:

```css
.upload-actions {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-end;
  justify-content: space-between;
  gap: 1rem;
}

.date-range {
  display: flex;
  gap: 1rem;
}

.date-range label {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  font-size: 0.85rem;
  color: #444;
}

.date-range input[type="date"] {
  padding: 0.4rem 0.5rem;
  border: 1px solid #d1d5db;
  border-radius: 6px;
  font-size: 0.9rem;
}

#submit-button {
  padding: 0.6rem 1.2rem;
  background-color: #2563eb;
  color: #fff;
  border: none;
  border-radius: 6px;
  font-size: 0.9rem;
  cursor: pointer;
}

#submit-button:disabled {
  background-color: #93c5fd;
  cursor: not-allowed;
}

.results {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.results h2 {
  font-size: 1.1rem;
  margin: 0;
}

.results-table-wrapper {
  overflow-x: auto;
  border: 1px solid #e5e5e5;
  border-radius: 8px;
}

#results-table {
  border-collapse: collapse;
  width: 100%;
  font-size: 0.85rem;
}

#results-table th,
#results-table td {
  padding: 0.5rem 0.75rem;
  border-bottom: 1px solid #f0f0f0;
  text-align: left;
  white-space: nowrap;
}

#results-table thead th {
  background-color: #fafafa;
  font-weight: 600;
}

#results-notes-wrapper h3 {
  font-size: 0.95rem;
  margin: 0 0 0.5rem;
}

#results-notes {
  margin: 0;
  padding-left: 1.25rem;
  font-size: 0.85rem;
  color: #555;
}
```

- [ ] **Step 6: Manually verify the button-enable and validation paths in a browser (no backend needed yet)**

Serve `web/` (`python3 -m http.server 8000` from inside `web/`) and open it.

- Confirm the "Enviar para OCR" button is disabled with no files selected.
- Select a valid file — confirm the button becomes enabled.
- Click it without filling the dates — confirm the inline error "Informe data inicial e data final." appears and no request is attempted (check the browser's network tab: no request fires).
- Remove the file (or "Limpar tudo") — confirm the button disables again.

- [ ] **Step 7: Manually verify the full pipeline once real credentials are available**

This step needs the user's own `GOOGLE_APPLICATION_CREDENTIALS` and `OPENROUTER_API_KEY` (`server/README.md` has setup steps) — it can't be completed inside this environment.

With `server/app.py` running (`python app.py` inside `server/`, real `.env` filled in) and `web/` served separately: select a real timesheet image, fill in a date range covering its dates, click "Enviar para OCR." Expected: after a short wait, a table appears with the extracted rows; if the model flagged anything, a "Pontos de atenção" list appears below it.

- [ ] **Step 8: Commit**

```bash
git add web/index.html web/app.js web/style.css
git commit -m "feat: submit files to OCR pipeline and render result table"
```
