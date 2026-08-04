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
