# Upload Interface Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a static, framework-free HTML/CSS/JS page where a user can select or drag-and-drop PDF/image files and see them listed locally (thumbnail/badge, name, size, remove) — no backend calls yet.

**Architecture:** Three plain static files in `web/` — `index.html` (structure, including a `<input type="file">` that fills the dropzone so click-to-open and native drag-and-drop both work without custom JS for file capture), `style.css` (layout/visuals), `app.js` (validation, in-memory file list state, rendering, remove/clear-all). No build tool, no framework, no test runner.

**Tech Stack:** Vanilla HTML5, CSS3, ES2017+ JavaScript (`const`/`let`, arrow functions, template literals, `Array.from`, `URL.createObjectURL`). No dependencies.

## Global Constraints

- Files live at repo root under `web/`: `web/index.html`, `web/style.css`, `web/app.js`. No build step, no package.json, no framework.
- Accepted file types: `.pdf`, `.png`, `.jpg`, `.jpeg` only (case-insensitive extension match). Anything else is rejected with an inline error and never added to the list.
- Multiple files may be selected or dropped in a single action.
- No network requests anywhere in this phase — local preview only.
- All UI copy is in Portuguese.
- No automated test framework (per spec) — verification is manual, in a browser, per the checklist in Task 2 Step 6.

---

### Task 1: Page skeleton — HTML structure and CSS

**Files:**
- Create: `web/index.html`
- Create: `web/style.css`

**Interfaces:**
- Produces DOM elements Task 2's `app.js` will query by id: `#dropzone`, `#file-input`, `#upload-errors`, `#upload-list`, `#upload-count`, `#upload-items`, `#clear-all`.
- Produces CSS classes Task 2's JS will toggle/set: `.is-dragging` (on `#dropzone`), `.upload-list-item`, `.upload-list-icon`, `.upload-list-thumb`, `.upload-list-info`, `.upload-list-name`, `.upload-list-size`.

- [ ] **Step 1: Create `web/index.html`**

```html
<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>TS Vision — Upload de Timesheets</title>
  <link rel="stylesheet" href="style.css" />
</head>
<body>
  <main class="app">
    <h1>TS Vision — Upload de Timesheets</h1>

    <section class="upload-zone">
      <div id="dropzone" class="upload-dropzone">
        <p>Arraste arquivos aqui ou clique para selecionar</p>
        <p class="upload-hint">Formatos aceitos: PDF, PNG, JPG</p>
        <input
          id="file-input"
          type="file"
          multiple
          accept=".pdf,.png,.jpg,.jpeg"
          class="upload-input"
        />
      </div>

      <ul id="upload-errors" class="upload-errors" hidden></ul>

      <div id="upload-list" class="upload-list" hidden>
        <div class="upload-list-header">
          <span id="upload-count"></span>
          <button type="button" id="clear-all">Limpar tudo</button>
        </div>
        <ul id="upload-items"></ul>
      </div>
    </section>
  </main>

  <script src="app.js"></script>
</body>
</html>
```

- [ ] **Step 2: Create `web/style.css`**

```css
* {
  box-sizing: border-box;
}

body {
  margin: 0;
  font-family: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
  color: #1a1a1a;
  background-color: #fff;
}

.app {
  min-height: 100vh;
  padding: 3rem 1.5rem;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2rem;
}

.app h1 {
  font-size: 1.5rem;
  font-weight: 600;
  text-align: center;
}

.upload-zone {
  max-width: 640px;
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.upload-dropzone {
  position: relative;
  border: 2px dashed #b3b3b3;
  border-radius: 8px;
  padding: 2.5rem 1.5rem;
  text-align: center;
  color: #444;
  transition: border-color 0.15s ease, background-color 0.15s ease;
}

.upload-dropzone.is-dragging {
  border-color: #2563eb;
  background-color: #eff6ff;
}

.upload-hint {
  font-size: 0.85rem;
  color: #888;
  margin-top: 0.25rem;
}

.upload-input {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  opacity: 0;
  cursor: pointer;
}

.upload-errors {
  margin: 0;
  padding: 0.75rem 1rem;
  background-color: #fef2f2;
  border: 1px solid #fecaca;
  border-radius: 6px;
  color: #b91c1c;
  font-size: 0.9rem;
  list-style: none;
}

.upload-list {
  border: 1px solid #e5e5e5;
  border-radius: 8px;
  overflow: hidden;
}

.upload-list-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0.75rem 1rem;
  background-color: #fafafa;
  border-bottom: 1px solid #e5e5e5;
  font-size: 0.9rem;
}

.upload-list-header button {
  background: none;
  border: none;
  color: #2563eb;
  cursor: pointer;
  font-size: 0.85rem;
}

.upload-list ul {
  list-style: none;
  margin: 0;
  padding: 0;
}

.upload-list-item {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.6rem 1rem;
  border-bottom: 1px solid #f0f0f0;
}

.upload-list-item:last-child {
  border-bottom: none;
}

.upload-list-icon {
  width: 36px;
  height: 36px;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background-color: #f3f4f6;
  border-radius: 4px;
  font-size: 0.65rem;
  font-weight: 700;
  color: #6b7280;
}

.upload-list-thumb {
  width: 36px;
  height: 36px;
  flex-shrink: 0;
  object-fit: cover;
  border-radius: 4px;
}

.upload-list-info {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
}

.upload-list-name {
  font-size: 0.9rem;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.upload-list-size {
  font-size: 0.75rem;
  color: #888;
}

.upload-list-item button {
  background: none;
  border: 1px solid #e5e5e5;
  border-radius: 4px;
  padding: 0.25rem 0.6rem;
  font-size: 0.8rem;
  cursor: pointer;
  color: #555;
}

.upload-list-item button:hover {
  border-color: #b91c1c;
  color: #b91c1c;
}
```

- [ ] **Step 3: Open `web/index.html` directly in a browser and verify manually**

Double-click the file (or `xdg-open web/index.html`). Expected: heading "TS Vision — Upload de Timesheets" is visible, the dashed dropzone box is visible with its two lines of text, and clicking anywhere inside the box opens the native file picker (this works already at this step because the real `<input type="file">` fills the box — no JS needed for that part).

- [ ] **Step 4: Commit**

```bash
git add web/index.html web/style.css
git commit -m "feat: add static upload page skeleton (HTML + CSS)"
```

---

### Task 2: File handling logic — validation, list rendering, remove/clear-all, drag feedback

**Files:**
- Create: `web/app.js`

**Interfaces:**
- Consumes: DOM ids/classes produced by Task 1 (`#dropzone`, `#file-input`, `#upload-errors`, `#upload-list`, `#upload-count`, `#upload-items`, `#clear-all`, `.is-dragging`, `.upload-list-item`, `.upload-list-icon`, `.upload-list-thumb`, `.upload-list-info`, `.upload-list-name`, `.upload-list-size`).
- Produces: nothing consumed by later tasks (this is the final task of this plan).

- [ ] **Step 1: Create `web/app.js`**

```javascript
const ACCEPTED_EXTENSIONS = ['.pdf', '.png', '.jpg', '.jpeg'];

const dropzone = document.getElementById('dropzone');
const fileInput = document.getElementById('file-input');
const errorsList = document.getElementById('upload-errors');
const uploadList = document.getElementById('upload-list');
const uploadCount = document.getElementById('upload-count');
const uploadItems = document.getElementById('upload-items');
const clearAllButton = document.getElementById('clear-all');

let files = [];
let nextId = 0;

function isAcceptedFileType(file) {
  const lowerName = file.name.toLowerCase();
  return ACCEPTED_EXTENSIONS.some((ext) => lowerName.endsWith(ext));
}

function formatFileSize(bytes) {
  if (bytes < 1024) {
    return `${bytes} B`;
  }
  if (bytes < 1024 * 1024) {
    return `${(bytes / 1024).toFixed(1)} KB`;
  }
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function addFiles(fileList) {
  const incoming = Array.from(fileList);
  const rejected = [];

  incoming.forEach((file) => {
    if (isAcceptedFileType(file)) {
      const isPdf = file.name.toLowerCase().endsWith('.pdf');
      nextId += 1;
      files.push({
        id: `file-${nextId}`,
        file,
        previewUrl: isPdf ? null : URL.createObjectURL(file),
        isPdf,
      });
    } else {
      rejected.push(`${file.name}: tipo de arquivo não suportado`);
    }
  });

  renderErrors(rejected);
  renderList();
}

function renderErrors(rejected) {
  errorsList.innerHTML = '';
  if (rejected.length === 0) {
    errorsList.hidden = true;
    return;
  }
  rejected.forEach((message) => {
    const li = document.createElement('li');
    li.textContent = message;
    errorsList.appendChild(li);
  });
  errorsList.hidden = false;
}

function renderList() {
  uploadItems.innerHTML = '';

  if (files.length === 0) {
    uploadList.hidden = true;
    return;
  }

  uploadList.hidden = false;
  uploadCount.textContent = `${files.length} arquivo(s) selecionado(s)`;

  files.forEach((entry) => {
    const li = document.createElement('li');
    li.className = 'upload-list-item';

    if (entry.isPdf) {
      const badge = document.createElement('div');
      badge.className = 'upload-list-icon';
      badge.setAttribute('aria-hidden', 'true');
      badge.textContent = 'PDF';
      li.appendChild(badge);
    } else {
      const img = document.createElement('img');
      img.className = 'upload-list-thumb';
      img.src = entry.previewUrl;
      img.alt = entry.file.name;
      li.appendChild(img);
    }

    const info = document.createElement('div');
    info.className = 'upload-list-info';

    const name = document.createElement('span');
    name.className = 'upload-list-name';
    name.textContent = entry.file.name;

    const size = document.createElement('span');
    size.className = 'upload-list-size';
    size.textContent = formatFileSize(entry.file.size);

    info.appendChild(name);
    info.appendChild(size);
    li.appendChild(info);

    const removeButton = document.createElement('button');
    removeButton.type = 'button';
    removeButton.textContent = 'Remover';
    removeButton.setAttribute('aria-label', `Remover ${entry.file.name}`);
    removeButton.addEventListener('click', () => removeFile(entry.id));
    li.appendChild(removeButton);

    uploadItems.appendChild(li);
  });
}

function removeFile(id) {
  const target = files.find((entry) => entry.id === id);
  if (target && target.previewUrl) {
    URL.revokeObjectURL(target.previewUrl);
  }
  files = files.filter((entry) => entry.id !== id);
  renderList();
}

function clearAll() {
  files.forEach((entry) => {
    if (entry.previewUrl) {
      URL.revokeObjectURL(entry.previewUrl);
    }
  });
  files = [];
  renderList();
}

fileInput.addEventListener('change', () => {
  if (fileInput.files && fileInput.files.length > 0) {
    addFiles(fileInput.files);
  }
  fileInput.value = '';
});

dropzone.addEventListener('dragenter', (event) => {
  event.preventDefault();
  dropzone.classList.add('is-dragging');
});

dropzone.addEventListener('dragover', (event) => {
  event.preventDefault();
});

dropzone.addEventListener('dragleave', () => {
  dropzone.classList.remove('is-dragging');
});

dropzone.addEventListener('drop', () => {
  dropzone.classList.remove('is-dragging');
});

clearAllButton.addEventListener('click', clearAll);
```

Note on drag-and-drop: `#file-input` is stretched to fill `#dropzone` (via the `.upload-input` CSS from Task 1) and sits on top of it, so dropping files anywhere in the box lands on the native `<input type="file">` itself. Modern browsers apply dropped files to the input and fire its `change` event automatically — the same `addFiles` path used for click-selection handles both. The `dragenter`/`dragover`/`dragleave`/`drop` listeners on `#dropzone` exist only to toggle the `.is-dragging` highlight class; they don't need to read `dataTransfer.files` themselves.

- [ ] **Step 2: Reload `web/index.html` in the browser**

The script tag already points to `app.js`; just refresh the page.

- [ ] **Step 3: Manually verify — select via click**

Click the dropzone, pick one `.pdf` and one `.png` from the native file dialog. Expected: both appear in the list below — the PDF with a "PDF" badge, the PNG with a thumbnail image — each showing filename and formatted size, and the header shows "2 arquivo(s) selecionado(s)".

- [ ] **Step 4: Manually verify — reject an unsupported type**

Click the dropzone and pick a `.txt` file. Expected: an inline red error box appears with text `"<nome>.txt: tipo de arquivo não suportado"`, and the file is not added to the list below.

- [ ] **Step 5: Manually verify — drag-and-drop**

Drag a `.jpg` file from your file manager onto the dropzone. Expected: while dragging over the box, the border turns blue and the background tints light blue (`.is-dragging`); on drop, the file appears in the list the same as a click-selected file.

- [ ] **Step 6: Manually verify — remove and clear all**

Click "Remover" on one file — expected: only that file disappears, the count updates, others remain. Click "Limpar tudo" — expected: the entire list and its header disappear (back to just the dropzone and no error box).

- [ ] **Step 7: Commit**

```bash
git add web/app.js
git commit -m "feat: add file validation, list rendering, and drag-and-drop handling"
```
