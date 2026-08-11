# Unified Multimodal OCR Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the Cloud Vision OCR step + separate text-structuring LLM call with a single
multimodal OpenRouter call that reads timesheet images/PDF pages directly and returns the structured
CSV, per `docs/superpowers/specs/2026-08-11-multimodal-ocr-design.md`.

**Architecture:** New `server/attachments.py` (file bytes → OpenRouter `image_url` content parts, PDF
pages rendered via PyMuPDF). `server/llm.py` builds a multimodal `messages` payload instead of a plain
text prompt; retry/parsing logic unchanged. `server/app.py`'s streaming stages rename
`ocr_lendo`/`ocr_concluido`/`ocr_falhou` to `preparando`/`preparado`/`preparo_falhou`. `server/ocr.py`
and the `google-cloud-vision` dependency are deleted.

**Tech Stack:** Adds `PyMuPDF` (pure-wheel PDF rendering, no system Poppler needed); removes
`google-cloud-vision`. Everything else (Flask, requests, python-dotenv) unchanged.

## Global Constraints

- Model default becomes `OPENROUTER_MODEL=google/gemma-4-26b-a4b-it:free` (user-validated choice).
- No page cap per PDF (PyMuPDF has none) — resolves the existing 5-page-truncation backlog item by
  construction.
- `GOOGLE_APPLICATION_CREDENTIALS` is removed from `config.py`'s required vars and from all docs/deploy
  files — no code path reads it after this plan.
- Same verification constraints as the original pipeline: no test framework: pure functions get
  one-off `python3 -c` checks; `app.py` validation paths get `curl`; the real OpenRouter multimodal
  call needs live credentials the user already has and has already validated manually.
- All new/changed user-facing copy stays in Portuguese.

---

### Task 1: `server/attachments.py` — file bytes → image content parts

**Files:**
- Create: `server/attachments.py`
- Modify: `server/requirements.txt` (add `PyMuPDF`, remove `google-cloud-vision`)

**Interfaces:**
- Produces: `to_image_parts(file_bytes: bytes, filename: str) -> list[dict]`. Task 3's `llm.py` and
  Task 4's `app.py` consume this.

- [ ] **Step 1: Update `server/requirements.txt`**

```
Flask
flask-cors
PyMuPDF
python-dotenv
requests
```

- [ ] **Step 2: Create `server/attachments.py`**

```python
import base64

import fitz  # PyMuPDF

PDF_RENDER_DPI = 200


def to_image_parts(file_bytes: bytes, filename: str) -> list:
    """Turns one uploaded file into a list of OpenAI/OpenRouter-style image_url content
    parts — one per PDF page, or a single part for a plain image file."""
    if filename.lower().endswith(".pdf"):
        images = _pdf_to_png_pages(file_bytes)
    else:
        images = [(file_bytes, _mime_type(filename))]

    return [_image_part(data, mime) for data, mime in images]


def _pdf_to_png_pages(file_bytes: bytes) -> list:
    pages = []
    with fitz.open(stream=file_bytes, filetype="pdf") as doc:
        for page in doc:
            pixmap = page.get_pixmap(dpi=PDF_RENDER_DPI)
            pages.append((pixmap.tobytes("png"), "image/png"))
    return pages


def _mime_type(filename: str) -> str:
    ext = filename.lower().rsplit(".", 1)[-1]
    return "image/jpeg" if ext in ("jpg", "jpeg") else "image/png"


def _image_part(data: bytes, mime: str) -> dict:
    encoded = base64.b64encode(data).decode("ascii")
    return {
        "type": "image_url",
        "image_url": {"url": f"data:{mime};base64,{encoded}"},
    }
```

- [ ] **Step 3: Install the new dependency locally and verify against real fixtures**

```bash
cd server
source venv/bin/activate
pip install -r requirements.txt
python3 -c "
import attachments

# 1x1 PNG (smallest valid PNG, base64-decoded)
png_bytes = bytes.fromhex(
    '89504e470d0a1a0a0000000d49484452000000010000000108020000009077'
    '5310000000017352474200aece1ce90000000467414d410000b18f0bfc6105'
    '0000000774494d4507e6070a12232eb7b1b0b60000000c4944415408d76360'
    '60600000000300010db2c0f10000000049454e44ae426082'
)
parts = attachments.to_image_parts(png_bytes, 'foto.png')
assert len(parts) == 1
assert parts[0]['type'] == 'image_url'
assert parts[0]['image_url']['url'].startswith('data:image/png;base64,')
print('image dispatch OK')
"
```

Expected: prints `image dispatch OK`. (PDF branch needs a real multi-page PDF fixture; verify manually
with any sample PDF on hand: `python3 -c "import attachments; print(len(attachments.to_image_parts(open('sample.pdf','rb').read(), 'sample.pdf')))"` should print the page count.)

- [ ] **Step 4: Commit**

```bash
cd ..
git add server/attachments.py server/requirements.txt
git commit -m "feat: add PDF/image to multimodal attachment conversion"
```

---

### Task 2: `server/llm.py` — multimodal message building

**Files:**
- Modify: `server/llm.py`

**Interfaces:**
- Changes: `build_prompt(attachments, date_start, date_end, prompt_template) -> str` now takes an
  `attachments: dict[str, list[dict]]` (filename → image parts) instead of `ocr_texts: dict[str, str]`,
  and returns a **text-only preview** (instructions + filenames/page counts) for the `llm_processando`
  event — not the image data.
- Adds: `build_messages(attachments, date_start, date_end, prompt_template) -> list[dict]` — the real
  multimodal `messages` payload sent to OpenRouter.
- `structure(attachments, date_start, date_end, prompt_template)` — same generator contract as today
  (`{"type": "retry", ...}` then `{"type": "result", "result": (csv_text, notes)}`), now calls
  `build_messages` instead of building a plain string.
- `_post_with_retry`, `_retry_delay`, `_split_csv_and_notes` — unchanged.

- [ ] **Step 1: Replace `build_prompt` and add `build_messages` in `server/llm.py`**

```python
def build_prompt(
    attachments: dict, date_start: str, date_end: str, prompt_template: str
) -> str:
    """Text-only preview of what gets sent (instructions + attachment summary), so
    callers can display it (e.g. as a progress event) without embedding image data."""
    prompt = prompt_template.replace("[DATA_INICIAL]", date_start).replace(
        "[DATA_FINAL]", date_end
    )

    summary = "\n".join(
        f"- {filename} ({len(parts)} página(s))"
        for filename, parts in attachments.items()
    )

    return f"{prompt}\n\nARQUIVOS ANEXADOS:\n\n{summary}"


def build_messages(
    attachments: dict, date_start: str, date_end: str, prompt_template: str
) -> list:
    prompt = prompt_template.replace("[DATA_INICIAL]", date_start).replace(
        "[DATA_FINAL]", date_end
    )

    content = [{"type": "text", "text": prompt}]
    for filename, parts in attachments.items():
        content.append({"type": "text", "text": f"--- Arquivo: {filename} ---"})
        content.extend(parts)

    return [{"role": "user", "content": content}]
```

- [ ] **Step 2: Update `structure()` to use `build_messages`**

```python
def structure(
    attachments: dict, date_start: str, date_end: str, prompt_template: str
):
    """Generator: yields {"type": "retry", ...} progress events while a transient
    OpenRouter failure is being retried, then a final
    {"type": "result", "result": (csv_text, notes)} once the model responds."""
    messages = build_messages(attachments, date_start, date_end, prompt_template)

    response = None
    for progress in _post_with_retry(
        {
            "model": config.OPENROUTER_MODEL,
            "messages": messages,
        }
    ):
        if progress["type"] == "retry":
            yield progress
        else:
            response = progress["response"]

    content = response.json()["choices"][0]["message"]["content"]
    yield {"type": "result", "result": _split_csv_and_notes(content)}
```

- [ ] **Step 3: Verify pure-function shape with a one-off script**

```bash
cd server
python3 -c "
from llm import build_prompt, build_messages

attachments = {'folha1.pdf': [{'type': 'image_url', 'image_url': {'url': 'data:image/png;base64,AA=='}}]}

preview = build_prompt(attachments, '2026-08-01', '2026-08-15', 'Prompt [DATA_INICIAL] a [DATA_FINAL]')
assert '2026-08-01' in preview and '2026-08-15' in preview
assert 'folha1.pdf (1 página(s))' in preview
assert 'base64' not in preview
print('build_prompt OK')

messages = build_messages(attachments, '2026-08-01', '2026-08-15', 'Prompt [DATA_INICIAL] a [DATA_FINAL]')
assert messages[0]['role'] == 'user'
content = messages[0]['content']
assert content[0] == {'type': 'text', 'text': 'Prompt 2026-08-01 a 2026-08-15'}
assert content[1] == {'type': 'text', 'text': '--- Arquivo: folha1.pdf ---'}
assert content[2]['type'] == 'image_url'
print('build_messages OK')
"
```

Expected: prints both `OK` lines with no assertion errors.

- [ ] **Step 4: Commit**

```bash
cd ..
git add server/llm.py
git commit -m "feat: send images directly to the LLM instead of OCR text"
```

---

### Task 3: `server/app.py` + `server/config.py` — wire the new pipeline, drop Vision

**Files:**
- Modify: `server/app.py`
- Modify: `server/config.py`
- Delete: `server/ocr.py`

**Interfaces:**
- Consumes: `attachments.to_image_parts` (Task 1), `llm.build_prompt`/`llm.structure` (Task 2).
- Removes: `config.GOOGLE_APPLICATION_CREDENTIALS`, the `ocr` import in `app.py`.

- [ ] **Step 1: Update `server/config.py`**

Remove the `GOOGLE_APPLICATION_CREDENTIALS` line and its `validate()` check; change the
`OPENROUTER_MODEL` default:

```python
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")
OPENROUTER_MODEL = os.environ.get("OPENROUTER_MODEL", "google/gemma-4-26b-a4b-it:free")
```

```python
def validate() -> None:
    missing = []
    if not OPENROUTER_API_KEY:
        missing.append("OPENROUTER_API_KEY")
    if not APP_USERNAME:
        missing.append("APP_USERNAME")
    if not APP_PASSWORD:
        missing.append("APP_PASSWORD")
    if missing:
        raise RuntimeError(
            "Variáveis de ambiente obrigatórias ausentes: "
            + ", ".join(missing)
            + ". Veja server/.env.example."
        )
```

- [ ] **Step 2: Delete `server/ocr.py`**

```bash
git rm server/ocr.py
```

- [ ] **Step 3: Update `server/app.py`'s imports and `generate()`**

Replace `import ocr` with `import attachments`. Replace the per-file loop and the call site:

```python
    def generate():
        yield _event("recebido", "Arquivos recebidos, preparando envio à IA...")

        file_attachments = {}
        notes = []

        for filename, file_bytes in file_records:
            yield _event("preparando", f"Preparando {filename} para envio à IA...", arquivo=filename)
            try:
                parts = attachments.to_image_parts(file_bytes, filename)
                file_attachments[filename] = parts
                yield _event(
                    "preparado",
                    f"{filename} pronto ({len(parts)} página(s)).",
                    arquivo=filename,
                )
            except Exception as exc:
                logger.exception("Falha ao preparar %s", filename)
                notes.append(f"{filename}: falha ao preparar arquivo ({exc})")
                yield _event("preparo_falhou", f"Falha ao preparar {filename}.", arquivo=filename)

        if not file_attachments:
            yield _event("erro", "Nenhum arquivo pôde ser preparado para envio à IA.")
            return

        prompt_enviado = llm.build_prompt(
            file_attachments, date_start, date_end, PROMPT_TEMPLATE
        )
        yield _event(
            "llm_processando",
            "Analisando timesheets com IA...",
            prompt=prompt_enviado,
        )

        csv_text = None
        llm_notes = []
        try:
            for progress in llm.structure(file_attachments, date_start, date_end, PROMPT_TEMPLATE):
                if progress["type"] == "retry":
                    yield _event(
                        "llm_retentando",
                        f"Chamada à IA falhou ({progress['error']}). Tentativa "
                        f"{progress['attempt']}/{progress['max_attempts']}, nova tentativa em "
                        f"{progress['delay']:.1f}s...",
                        tentativa=progress["attempt"],
                        max_tentativas=progress["max_attempts"],
                    )
                else:
                    csv_text, llm_notes = progress["result"]
        except Exception as exc:
            logger.exception("Falha ao chamar o LLM")
            yield _event("erro", f"Falha ao processar com o LLM: {exc}")
            return

        yield _event(
            "concluido", "Concluído.", csv=csv_text, notes=notes + llm_notes
        )
```

- [ ] **Step 4: Verify startup and validation paths**

```bash
cd server
python3 -c "import config; config.validate()"
```

Expected: `RuntimeError` no longer mentions `GOOGLE_APPLICATION_CREDENTIALS` — only
`OPENROUTER_API_KEY`, `APP_USERNAME`, `APP_PASSWORD` (whichever are unset in this environment).

```bash
OPENROUTER_API_KEY=fake APP_USERNAME=admin APP_PASSWORD=secret1234 AUTH_SECRET=testsecret python3 app.py &
sleep 1
curl -s -X POST http://localhost:5000/api/ocr -H "Authorization: Bearer invalid"
echo
kill %1
```

Expected: 401 (invalid token) — confirms the app boots without `GOOGLE_APPLICATION_CREDENTIALS` set.

- [ ] **Step 5: Commit**

```bash
cd ..
git add server/app.py server/config.py
git commit -m "feat: replace Cloud Vision OCR step with direct image attachments"
```

---

### Task 4: Frontend — adjust status-entry handling for renamed stages

**Files:**
- Modify: `web/app.js`
- Modify: `web/style.css`

**Interfaces:** none (leaf task, no downstream consumers).

- [ ] **Step 1: Remove the `ocr_concluido`/`texto` special case in `web/app.js`**

The block around the stream-parsing loop currently reads:

```javascript
        if (event.stage === 'ocr_concluido' && event.texto) {
          appendStatusEntry(event.stage, event.message, 'Ver texto extraído pelo OCR', event.texto);
        } else if (event.stage === 'llm_processando' && event.prompt) {
          appendStatusEntry(event.stage, event.message, 'Ver conteúdo enviado à IA', event.prompt);
        } else {
          appendStatusEntry(event.stage, event.message);
        }
```

Change to:

```javascript
        if (event.stage === 'llm_processando' && event.prompt) {
          appendStatusEntry(event.stage, event.message, 'Ver conteúdo enviado à IA', event.prompt);
        } else {
          appendStatusEntry(event.stage, event.message);
        }
```

- [ ] **Step 2: Rename the CSS selector in `web/style.css`**

```css
.status-entry--erro,
.status-entry--preparo_falhou {
```

(was `.status-entry--ocr_falhou`.)

- [ ] **Step 3: Manual browser check**

Serve `web/` and `server/` locally (real credentials needed for the LLM call), submit a real timesheet
file, and confirm: the timeline shows "Preparando X..." → "X pronto (N página(s))." → "Analisando
timesheets com IA..." (with a working "Ver conteúdo enviado à IA" reveal showing the instructions +
attachment summary, no raw base64) → "Concluído." with the results table.

- [ ] **Step 4: Commit**

```bash
git add web/app.js web/style.css
git commit -m "feat: adjust status timeline for the multimodal pipeline stages"
```

---

### Task 5: Docs and deployment config

**Files:**
- Modify: `CLAUDE.md`
- Modify: `server/README.md`
- Modify: `server/.env.example`
- Modify: `docker-compose.yml`
- Modify: `BACKLOG.md`

**Interfaces:** none (documentation only).

- [ ] **Step 1: `server/.env.example`** — remove `GOOGLE_APPLICATION_CREDENTIALS`, update
  `OPENROUTER_MODEL` default to `google/gemma-4-26b-a4b-it:free`.

- [ ] **Step 2: `server/README.md`** — remove the GCP/Cloud Vision credential setup section entirely;
  keep only the OpenRouter setup step, noting the model must support vision/multimodal input.

- [ ] **Step 3: `docker-compose.yml`** — remove the `GOOGLE_APPLICATION_CREDENTIALS` environment
  override and the `server/gcp-service-account.json` bind mount from the `server` service.

- [ ] **Step 4: `CLAUDE.md`** — rewrite the `server/` architecture section (OCR/LLM paragraphs, the
  "two independent, swappable steps" description, `ocr.py`/`llm.py` module descriptions, `config.py`'s
  env var list) and the Deployment section's GCP JSON bind-mount paragraph to match the new
  single-call multimodal pipeline; update the event-stage list (`ocr_lendo`/`ocr_concluido`/
  `ocr_falhou` → `preparando`/`preparado`/`preparo_falhou`).

- [ ] **Step 5: `BACKLOG.md`** — check off the 5-page PDF truncation item as resolved by construction
  (PyMuPDF has no page cap); add a note under "Baixa prioridade" if PyMuPDF ever needs a page cap for
  cost/payload-size reasons in practice.

- [ ] **Step 6: Commit**

```bash
git add CLAUDE.md server/README.md server/.env.example docker-compose.yml BACKLOG.md
git commit -m "docs: document the unified multimodal OCR pipeline"
```
