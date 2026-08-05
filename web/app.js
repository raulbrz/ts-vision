const ACCEPTED_EXTENSIONS = ['.pdf', '.png', '.jpg', '.jpeg'];

const dropzone = document.getElementById('dropzone');
const fileInput = document.getElementById('file-input');
const errorsList = document.getElementById('upload-errors');
const uploadList = document.getElementById('upload-list');
const uploadCount = document.getElementById('upload-count');
const uploadItems = document.getElementById('upload-items');
const clearAllButton = document.getElementById('clear-all');
const submitButton = document.getElementById('submit-button');
const cancelButton = document.getElementById('cancel-button');
const dateInicioInput = document.getElementById('date-inicio');
const dateFimInput = document.getElementById('date-fim');
const submitError = document.getElementById('submit-error');
const resultsSection = document.getElementById('results');
const resultsNotesWrapper = document.getElementById('results-notes-wrapper');
const resultsNotesList = document.getElementById('results-notes');
const statusTimeline = document.getElementById('status-timeline');
const clearResultsButton = document.getElementById('clear-results');
const downloadCsvButton = document.getElementById('download-csv');

const OCR_ENDPOINT = 'http://localhost:5000/api/ocr';

let files = [];
let nextId = 0;
let lastCsvText = '';
let activeController = null;

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
  submitButton.disabled = files.length === 0;

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

function clearResults() {
  resultsSection.hidden = true;
  document.getElementById('results-table').innerHTML = '';
  resultsNotesList.innerHTML = '';
  resultsNotesWrapper.hidden = true;
  statusTimeline.innerHTML = '';
  statusTimeline.hidden = true;
  submitError.hidden = true;
  lastCsvText = '';
}

clearResultsButton.addEventListener('click', clearResults);

downloadCsvButton.addEventListener('click', () => {
  if (!lastCsvText) {
    return;
  }
  const blob = new Blob(['﻿' + lastCsvText], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = `timesheets_${dateInicioInput.value || 'inicio'}_${dateFimInput.value || 'fim'}.csv`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
});

function appendStatusEntry(stage, message) {
  statusTimeline.hidden = false;
  const li = document.createElement('li');
  li.className = `status-entry status-entry--${stage}`;
  li.textContent = message;
  statusTimeline.appendChild(li);
}

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
  cancelButton.hidden = false;

  const controller = new AbortController();
  activeController = controller;

  try {
    const response = await fetch(OCR_ENDPOINT, {
      method: 'POST',
      body: formData,
      signal: controller.signal,
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
          lastCsvText = event.csv;
          renderResultsTable(event.csv);
          renderResultsNotes(event.notes);
        } else if (event.stage === 'erro') {
          submitError.textContent = event.message;
          submitError.hidden = false;
        }
      }
    }
  } catch (error) {
    if (error.name === 'AbortError') {
      appendStatusEntry('cancelado', 'Processamento cancelado pelo usuário.');
    } else {
      submitError.textContent = error.message;
      submitError.hidden = false;
    }
  } finally {
    activeController = null;
    cancelButton.hidden = true;
    submitButton.disabled = files.length === 0;
    submitButton.textContent = 'Enviar para OCR';
  }
});

cancelButton.addEventListener('click', () => {
  if (activeController) {
    activeController.abort();
  }
});
