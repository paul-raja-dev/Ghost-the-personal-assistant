const input = document.getElementById('command-input');
const badge = document.getElementById('action-badge');
const badgeText = document.getElementById('badge-text');
const barContainer = document.getElementById('bar-container');

// Dynamic containers
const dynamicContent = document.getElementById('dynamic-content');
const viewLine = document.getElementById('view-line');
const lineMarker = document.getElementById('line-marker');
const lineText = document.getElementById('line-text');

const viewList = document.getElementById('view-list');
const listTitle = document.getElementById('list-title');
const listMeta = document.getElementById('list-meta');
const listItems = document.getElementById('list-items');

const viewCompose = document.getElementById('view-compose');
const composeTitle = document.getElementById('compose-title');
const composeBody = document.getElementById('compose-body');
const btnComposeSend = document.getElementById('btn-compose-send');
const btnComposeCancel = document.getElementById('btn-compose-cancel');

const viewConfirm = document.getElementById('view-confirm');
const confirmTitle = document.getElementById('confirm-title');
const confirmBody = document.getElementById('confirm-body');
const btnConfirmOk = document.getElementById('btn-confirm-ok');
const btnConfirmCancel = document.getElementById('btn-confirm-cancel');

let isBusy = false;
let autoCloseTimer = null;
let currentItems = [];
let selectedIndex = 0;

function hideAllViews() {
  viewLine.classList.add('hidden');
  viewList.classList.add('hidden');
  viewCompose.classList.add('hidden');
  viewConfirm.classList.add('hidden');
  dynamicContent.classList.add('hidden');
  if (autoCloseTimer) {
    clearTimeout(autoCloseTimer);
    autoCloseTimer = null;
  }
}

function resetState() {
  hideAllViews();
  window.ghostAPI?.setWindowHeight?.(64);
  input.value = '';
  input.disabled = false;
  input.placeholder = 'Tell me what to do...';
  barContainer.classList.remove('working');
  badge.classList.remove('active');
  badgeText.textContent = '>';
  isBusy = false;
  currentItems = [];
  selectedIndex = 0;
  setTimeout(() => input.focus(), 40);
}

// Reset when hotkey summons Ghost
if (window.ghostAPI?.onResetFocus) {
  window.ghostAPI.onResetFocus(() => {
    resetState();
  });
}

// Save position on drag release
window.addEventListener('mouseup', () => {
  window.ghostAPI?.savePosition?.();
});

input.addEventListener('input', () => {
  if (autoCloseTimer) {
    clearTimeout(autoCloseTimer);
    autoCloseTimer = null;
  }
  const query = input.value.trim();
  if (query.length > 0) {
    badge.classList.add('active');
  } else {
    badge.classList.remove('active');
  }
});

// Click action badge to submit
badge.addEventListener('click', () => {
  if (!isBusy && input.value.trim()) {
    submitTask();
  }
});

function renderLine(data) {
  hideAllViews();
  const isErr = (data.title || '').toLowerCase().includes('error') || (data.body || '').toLowerCase().includes('error');
  viewLine.className = isErr ? 'view-line error' : 'view-line';
  lineMarker.textContent = isErr ? '[error]' : '>';
  lineText.textContent = data.body || data.title || 'Done.';

  viewLine.classList.remove('hidden');
  dynamicContent.classList.remove('hidden');
  window.ghostAPI?.setWindowHeight?.(108);

  if (data.auto_close !== false) {
    autoCloseTimer = setTimeout(() => {
      window.ghostAPI?.closeWindow?.();
      resetState();
    }, 2400);
  }
}

function renderList(data) {
  hideAllViews();
  listTitle.textContent = data.title || 'Results';
  listMeta.textContent = `${(data.items || []).length} items`;
  listItems.innerHTML = '';

  currentItems = data.items || [];
  selectedIndex = 0;

  if (currentItems.length === 0) {
    const empty = document.createElement('div');
    empty.className = 'list-item';
    empty.innerHTML = `<span class="item-label">${data.body || 'No items found.'}</span>`;
    listItems.appendChild(empty);
  } else {
    currentItems.forEach((item, idx) => {
      const el = document.createElement('div');
      el.className = idx === 0 ? 'list-item selected' : 'list-item';
      el.innerHTML = `
        <div class="item-left">
          <span class="item-label">${escapeHtml(item.label || item.title || '')}</span>
          ${item.detail ? `<span class="item-detail">${escapeHtml(item.detail)}</span>` : ''}
        </div>
        ${item.badge ? `<span class="item-badge">${escapeHtml(item.badge)}</span>` : ''}
      `;
      listItems.appendChild(el);
    });
  }

  viewList.classList.remove('hidden');
  dynamicContent.classList.remove('hidden');
  window.ghostAPI?.setWindowHeight?.(340);
}

function renderCompose(data) {
  hideAllViews();
  composeTitle.textContent = data.title || 'Draft Content';
  composeBody.value = data.body || '';

  viewCompose.classList.remove('hidden');
  dynamicContent.classList.remove('hidden');
  window.ghostAPI?.setWindowHeight?.(390);
  setTimeout(() => composeBody.focus(), 50);
}

function renderConfirm(data) {
  hideAllViews();
  confirmTitle.textContent = data.title || 'Confirmation Required';
  confirmBody.textContent = data.body || 'Do you want to proceed with this action?';

  viewConfirm.classList.remove('hidden');
  dynamicContent.classList.remove('hidden');
  window.ghostAPI?.setWindowHeight?.(240);
}

function escapeHtml(text) {
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}

async function submitTask() {
  const prompt = input.value.trim();
  if (!prompt || isBusy) return;

  isBusy = true;
  input.disabled = true;
  barContainer.classList.add('working');
  badgeText.textContent = '...';

  try {
    const rawResult = await window.ghostAPI.runPrompt(prompt);
    let data;
    try {
      data = JSON.parse(rawResult);
    } catch {
      data = { display: 'line', body: rawResult, auto_close: true };
    }

    badgeText.textContent = '>';
    barContainer.classList.remove('working');
    isBusy = false;
    input.disabled = false;

    const mode = data.display || 'line';

    if (mode === 'list') {
      renderList(data);
    } else if (mode === 'compose') {
      renderCompose(data);
    } else if (mode === 'confirm') {
      renderConfirm(data);
    } else {
      renderLine(data);
    }

    // Interactive continuation: re-enable input for immediate follow-up
    if (mode === 'confirm') {
      // Retain prompt context in confirm view
      setTimeout(() => input.focus(), 40);
    } else {
      input.value = '';
      badge.classList.remove('active');
      input.placeholder = 'Follow-up or new command... (Esc to dismiss)';
      setTimeout(() => input.focus(), 40);
    }
  } catch (err) {
    barContainer.classList.remove('working');
    badgeText.textContent = '>';
    isBusy = false;
    input.disabled = false;
    renderLine({ display: 'line', title: 'Error', body: err.message, auto_close: false });
    input.placeholder = 'Type a command... (Esc to dismiss)';
    setTimeout(() => input.focus(), 40);
  }
}

// Button actions
btnComposeSend.addEventListener('click', () => {
  navigator.clipboard.writeText(composeBody.value);
  btnComposeSend.textContent = 'Copied!';
  setTimeout(() => {
    window.ghostAPI?.closeWindow?.();
    resetState();
  }, 800);
});

btnComposeCancel.addEventListener('click', () => {
  window.ghostAPI?.closeWindow?.();
  resetState();
});

btnConfirmCancel.addEventListener('click', () => {
  window.ghostAPI?.closeWindow?.();
  resetState();
});

btnConfirmOk.addEventListener('click', () => {
  input.disabled = false;
  input.value = `confirmed: ${input.value}`;
  submitTask();
});

// Keyboard navigation
window.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') {
    window.ghostAPI?.closeWindow?.();
    resetState();
    return;
  }

  // Ctrl+L or Cmd+L to clear session and reset view
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'l') {
    e.preventDefault();
    window.ghostAPI?.runPrompt?.('/clear');
    resetState();
    return;
  }

  // List view arrow navigation
  if (!viewList.classList.contains('hidden') && currentItems.length > 0) {
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      selectedIndex = (selectedIndex + 1) % currentItems.length;
      updateListSelection();
      return;
    }
    if (e.key === 'ArrowUp') {
      e.preventDefault();
      selectedIndex = (selectedIndex - 1 + currentItems.length) % currentItems.length;
      updateListSelection();
      return;
    }
  }

  if (e.key === 'Enter' && !isBusy && document.activeElement === input) {
    e.preventDefault();
    submitTask();
  }
});

function updateListSelection() {
  const items = listItems.querySelectorAll('.list-item');
  items.forEach((item, idx) => {
    if (idx === selectedIndex) {
      item.classList.add('selected');
      item.scrollIntoView({ block: 'nearest' });
    } else {
      item.classList.remove('selected');
    }
  });
}

input.focus();
