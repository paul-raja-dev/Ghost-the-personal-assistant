const input = document.getElementById('command-input');
const badge = document.getElementById('action-badge');
const badgeText = document.getElementById('badge-text');
const barContainer = document.getElementById('bar-container');
const dynamicContent = document.getElementById('dynamic-content');
const chatStream = document.getElementById('chat-stream');

let isBusy = false;
let isExpanded = false;

function escapeHtml(text) {
  const div = document.createElement('div');
  div.textContent = text || '';
  return div.innerHTML;
}

function scrollToBottom() {
  requestAnimationFrame(() => {
    chatStream.scrollTop = chatStream.scrollHeight;
  });
}

function expandWindow() {
  if (!isExpanded) {
    isExpanded = true;
    dynamicContent.classList.remove('hidden');
    window.ghostAPI?.setWindowHeight?.(420, true);
  }
}

function collapseWindow() {
  isExpanded = false;
  dynamicContent.classList.add('hidden');
  chatStream.innerHTML = '';
  window.ghostAPI?.setWindowHeight?.(64, true);
}

function resetState() {
  collapseWindow();
  input.value = '';
  input.disabled = false;
  input.placeholder = 'Tell me what to do...';
  barContainer.classList.remove('working');
  badge.classList.remove('active');
  badgeText.textContent = '>';
  isBusy = false;
  setTimeout(() => input.focus(), 40);
}

// Keep focus when hotkey summons Ghost
if (window.ghostAPI?.onResetFocus) {
  window.ghostAPI.onResetFocus(() => {
    input.focus();
  });
}

// Save position on drag release
window.addEventListener('mouseup', () => {
  window.ghostAPI?.savePosition?.();
});

input.addEventListener('input', () => {
  const query = input.value.trim();
  if (query.length > 0) {
    badge.classList.add('active');
  } else {
    badge.classList.remove('active');
  }
});

badge.addEventListener('click', () => {
  if (!isBusy && input.value.trim()) {
    submitTask();
  }
});

function appendUserMessage(text) {
  const row = document.createElement('div');
  row.className = 'chat-row user';
  row.innerHTML = `<div class="chat-bubble user">${escapeHtml(text)}</div>`;
  chatStream.appendChild(row);
  scrollToBottom();
}

function showTypingIndicator() {
  const row = document.createElement('div');
  row.className = 'chat-row ghost';
  row.id = 'typing-row';
  row.innerHTML = `
    <span class="chat-avatar">&gt;</span>
    <div class="chat-bubble ghost typing">
      <div class="typing-dot"></div>
      <div class="typing-dot"></div>
      <div class="typing-dot"></div>
    </div>
  `;
  chatStream.appendChild(row);
  scrollToBottom();
}

function removeTypingIndicator() {
  const typing = document.getElementById('typing-row');
  if (typing) {
    typing.remove();
  }
}

function appendGhostMessage(data) {
  const row = document.createElement('div');
  row.className = 'chat-row ghost';

  const avatar = document.createElement('span');
  avatar.className = 'chat-avatar';
  avatar.textContent = '>';

  const bubble = document.createElement('div');
  bubble.className = 'chat-bubble ghost';

  const mode = data.display || 'line';
  const bodyText = data.body || '';
  const titleText = data.title || '';

  // Main text line/body
  if (bodyText) {
    const textEl = document.createElement('div');
    textEl.className = 'chat-text';
    textEl.innerHTML = escapeHtml(bodyText).replace(/\n/g, '<br>');
    bubble.appendChild(textEl);
  } else if (titleText && mode === 'line') {
    const textEl = document.createElement('div');
    textEl.className = 'chat-text';
    textEl.innerHTML = escapeHtml(titleText);
    bubble.appendChild(textEl);
  }

  // 1. List Widget (for memories, search results, tasks)
  if (mode === 'list' && Array.isArray(data.items) && data.items.length > 0) {
    const listWidget = document.createElement('div');
    listWidget.className = 'widget-list';

    if (titleText) {
      const header = document.createElement('div');
      header.className = 'widget-title';
      header.innerHTML = `<span>${escapeHtml(titleText)}</span><span class="widget-meta">${data.items.length} items</span>`;
      listWidget.appendChild(header);
    }

    const itemsContainer = document.createElement('div');
    itemsContainer.className = 'widget-list-items';

    data.items.forEach((item) => {
      const itemEl = document.createElement('div');
      itemEl.className = 'widget-item';
      itemEl.innerHTML = `
        <div class="widget-item-left">
          <span class="widget-item-label">${escapeHtml(item.label || item.title || '')}</span>
          ${item.detail ? `<span class="widget-item-detail">${escapeHtml(item.detail)}</span>` : ''}
        </div>
        ${item.badge ? `<span class="widget-item-badge">${escapeHtml(item.badge)}</span>` : ''}
      `;
      itemsContainer.appendChild(itemEl);
    });

    listWidget.appendChild(itemsContainer);
    bubble.appendChild(listWidget);
  }

  // 2. Compose Widget (email draft, note draft)
  if (mode === 'compose') {
    const composeWidget = document.createElement('div');
    composeWidget.className = 'widget-compose';

    if (titleText) {
      const header = document.createElement('div');
      header.className = 'widget-title';
      header.innerHTML = `<span>${escapeHtml(titleText)}</span>`;
      composeWidget.appendChild(header);
    }

    const textarea = document.createElement('textarea');
    textarea.className = 'widget-compose-body';
    textarea.value = bodyText;
    textarea.spellcheck = false;

    const actions = document.createElement('div');
    actions.className = 'widget-actions';

    const btnCopy = document.createElement('button');
    btnCopy.className = 'btn btn-primary';
    btnCopy.textContent = 'Copy to clipboard';
    btnCopy.addEventListener('click', () => {
      navigator.clipboard.writeText(textarea.value);
      btnCopy.textContent = 'Copied!';
      setTimeout(() => { btnCopy.textContent = 'Copy to clipboard'; }, 1500);
    });

    actions.appendChild(btnCopy);
    composeWidget.appendChild(textarea);
    composeWidget.appendChild(actions);
    bubble.appendChild(composeWidget);
  }

  // 3. Confirm Widget (file deletions, system actions)
  if (mode === 'confirm') {
    const confirmWidget = document.createElement('div');
    confirmWidget.className = 'widget-confirm';

    if (titleText) {
      const header = document.createElement('div');
      header.className = 'widget-title';
      header.innerHTML = `<span>${escapeHtml(titleText)}</span>`;
      confirmWidget.appendChild(header);
    }

    const actions = document.createElement('div');
    actions.className = 'widget-actions';

    const btnOk = document.createElement('button');
    btnOk.className = 'btn btn-danger';
    btnOk.textContent = 'Confirm Action';
    btnOk.addEventListener('click', () => {
      btnOk.disabled = true;
      btnOk.textContent = 'Executing...';
      input.value = `confirm: ${bodyText || titleText}`;
      submitTask();
    });

    const btnCancel = document.createElement('button');
    btnCancel.className = 'btn btn-secondary';
    btnCancel.textContent = 'Cancel';
    btnCancel.addEventListener('click', () => {
      confirmWidget.remove();
    });

    actions.appendChild(btnOk);
    actions.appendChild(btnCancel);
    confirmWidget.appendChild(actions);
    bubble.appendChild(confirmWidget);
  }

  row.appendChild(avatar);
  row.appendChild(bubble);
  chatStream.appendChild(row);
  scrollToBottom();
}

async function submitTask() {
  const prompt = input.value.trim();
  if (!prompt || isBusy) return;

  // Intercept clear command directly
  if (prompt.toLowerCase() === '/clear' || prompt.toLowerCase() === 'clear') {
    window.ghostAPI?.runPrompt?.('/clear');
    resetState();
    return;
  }

  isBusy = true;
  barContainer.classList.add('working');
  badgeText.textContent = '...';

  // Smoothly expand window on first message
  expandWindow();

  // Show user message & typing indicator
  appendUserMessage(prompt);
  showTypingIndicator();

  // Reset input immediately for next follow-up
  input.value = '';
  badge.classList.remove('active');
  input.placeholder = 'Thinking...';

  try {
    const rawResult = await window.ghostAPI.runPrompt(prompt);
    removeTypingIndicator();

    let data;
    try {
      data = JSON.parse(rawResult);
    } catch {
      data = { display: 'line', body: rawResult };
    }

    appendGhostMessage(data);
  } catch (err) {
    removeTypingIndicator();
    appendGhostMessage({
      display: 'line',
      title: 'Error',
      body: `[error] ${err.message}`,
    });
  } finally {
    barContainer.classList.remove('working');
    badgeText.textContent = '>';
    isBusy = false;
    input.placeholder = 'Type a message or follow-up... (Esc to dismiss)';
    setTimeout(() => input.focus(), 40);
  }
}

// Global Keyboard Navigation
window.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') {
    window.ghostAPI?.closeWindow?.();
    resetState();
    return;
  }

  // Ctrl+L or Cmd+L to clear chat and collapse back to single line
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'l') {
    e.preventDefault();
    window.ghostAPI?.runPrompt?.('/clear');
    resetState();
    return;
  }

  if (e.key === 'Enter' && !isBusy && document.activeElement === input) {
    e.preventDefault();
    submitTask();
  }
});

input.focus();
