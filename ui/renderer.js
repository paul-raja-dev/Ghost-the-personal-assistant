const input = document.getElementById('command-input');
const badge = document.getElementById('action-badge');
const badgeText = document.getElementById('badge-text');
const barContainer = document.getElementById('bar-container');
const dynamicContent = document.getElementById('dynamic-content');
const chatStream = document.getElementById('chat-stream');
const historyDrawer = document.getElementById('history-drawer');
const historyList = document.getElementById('history-list');
const btnCloseDrawer = document.getElementById('btn-close-drawer');

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
  window.ghostAPI?.setWindowHeight?.(54, true);
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

function parseInlineCode(str) {
  const parts = str.split(/(`[^`]+`)/g);
  return parts.map((p) => {
    if (p.startsWith('`') && p.endsWith('`') && p.length > 2) {
      return `<span class="chat-inline-code">${escapeHtml(p.slice(1, -1))}</span>`;
    }
    return escapeHtml(p);
  }).join('');
}

function formatChatText(text) {
  if (!text) return '';

  // Handle multi-line code blocks ```...```
  const parts = text.split(/(```[\s\S]*?```)/g);
  return parts.map((part) => {
    if (part.startsWith('```') && part.endsWith('```')) {
      const firstLineEnd = part.indexOf('\n');
      let lang = '';
      let code = '';
      if (firstLineEnd !== -1) {
        lang = part.slice(3, firstLineEnd).trim();
        code = part.slice(firstLineEnd + 1, -3);
      } else {
        code = part.slice(3, -3);
      }
      return `<div class="chat-code-block"${lang ? ` data-lang="${escapeHtml(lang)}"` : ''}><pre><code>${escapeHtml(code)}</code></pre></div>`;
    }

    const lines = part.split('\n');
    return lines.map((line) => {
      const trimmed = line.trim();
      if (trimmed.endsWith(':') && !trimmed.startsWith('-') && !trimmed.startsWith('http')) {
        return `<div class="chat-section-title">${escapeHtml(trimmed)}</div>`;
      }
      if (trimmed.startsWith('- ')) {
        const bulletContent = parseInlineCode(trimmed.slice(2));
        return `<div class="chat-bullet"><span class="bullet-dash">-</span> ${bulletContent}</div>`;
      }
      if (trimmed === '') {
        return `<div class="chat-spacer"></div>`;
      }
      return `<div>${parseInlineCode(line)}</div>`;
    }).join('');
  }).join('');
}

function appendGhostMessage(data) {
  const row = document.createElement('div');
  row.className = 'chat-row ghost';

  const bubble = document.createElement('div');
  bubble.className = 'chat-bubble ghost';

  const mode = data.display || 'line';
  const bodyText = data.body || '';
  const titleText = data.title || '';

  // Main clean formatted text body
  if (bodyText) {
    const textEl = document.createElement('div');
    textEl.className = 'chat-text';
    textEl.innerHTML = formatChatText(bodyText);
    bubble.appendChild(textEl);
  } else if (titleText && mode === 'line') {
    const textEl = document.createElement('div');
    textEl.className = 'chat-text';
    textEl.innerHTML = formatChatText(titleText);
    bubble.appendChild(textEl);
  }

  // 1. Compose Widget (email draft, note draft)
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

// History Drawer (Ctrl + H)
async function toggleHistoryDrawer() {
  if (historyDrawer.classList.contains('hidden')) {
    expandWindow();
    historyDrawer.classList.remove('hidden');
    historyList.innerHTML = '<div style="color: #64748b; font-size: 12px; padding: 12px;">Loading chat history...</div>';

    try {
      const sessions = await window.ghostAPI.listSessions();
      historyList.innerHTML = '';

      if (!sessions || sessions.length === 0) {
        historyList.innerHTML = '<div style="color: #64748b; font-size: 12px; padding: 12px;">No past conversations found.</div>';
        return;
      }

      sessions.forEach((sess) => {
        const item = document.createElement('div');
        item.className = 'history-item';
        item.innerHTML = `
          <div class="history-item-left">
            <span class="history-item-title">${escapeHtml(sess.title)}</span>
            <span class="history-item-date">${escapeHtml(sess.date)}</span>
          </div>
          <button class="history-item-delete" title="Delete conversation" aria-label="Delete conversation">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M3 6h18m-2 0v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6m3 0V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2"></path>
              <line x1="10" y1="11" x2="10" y2="17"></line>
              <line x1="14" y1="11" x2="14" y2="17"></line>
            </svg>
          </button>
        `;
        item.addEventListener('click', () => {
          resumeSession(sess.id);
        });

        const btnDelete = item.querySelector('.history-item-delete');
        if (btnDelete) {
          btnDelete.addEventListener('click', async (e) => {
            e.stopPropagation();
            item.style.opacity = '0.3';
            item.style.pointerEvents = 'none';
            try {
              await window.ghostAPI.deleteSession(sess.id);
              item.remove();
              if (historyList.children.length === 0) {
                historyList.innerHTML = '<div style="color: #64748b; font-size: 12px; padding: 12px;">No past conversations found.</div>';
              }
            } catch (err) {
              console.error('Failed to delete session:', err);
              item.style.opacity = '1';
              item.style.pointerEvents = 'auto';
            }
          });
        }

        historyList.appendChild(item);
      });
    } catch (err) {
      historyList.innerHTML = `<div style="color: #f87171; font-size: 12px; padding: 12px;">Error loading history: ${escapeHtml(err.message)}</div>`;
    }
  } else {
    historyDrawer.classList.add('hidden');
    input.focus();
  }
}

if (btnCloseDrawer) {
  btnCloseDrawer.addEventListener('click', () => {
    historyDrawer.classList.add('hidden');
    input.focus();
  });
}

async function resumeSession(sessionId) {
  try {
    const sessionData = await window.ghostAPI.loadSession(sessionId);
    if (!sessionData || !Array.isArray(sessionData.turns)) return;

    chatStream.innerHTML = '';
    historyDrawer.classList.add('hidden');

    sessionData.turns.forEach((turn) => {
      if (turn.role === 'user') {
        appendUserMessage(turn.text);
      } else {
        let data;
        try {
          data = JSON.parse(turn.text);
        } catch {
          data = { display: 'line', body: turn.text };
        }
        appendGhostMessage(data);
      }
    });

    expandWindow();
    input.value = '';
    input.placeholder = `Continuing "${sessionData.title || 'chat'}"... (Esc to dismiss)`;
    setTimeout(() => input.focus(), 40);
  } catch (err) {
    console.error('Failed to resume session:', err);
  }
}

// Global Keyboard Navigation
window.addEventListener('keydown', (e) => {
  // Ctrl+H or Cmd+H to toggle chat history
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'h') {
    e.preventDefault();
    toggleHistoryDrawer();
    return;
  }

  if (e.key === 'Escape') {
    if (!historyDrawer.classList.contains('hidden')) {
      historyDrawer.classList.add('hidden');
      input.focus();
      return;
    }
    window.ghostAPI?.closeWindow?.();
    resetState();
    return;
  }

  // Ctrl+L or Cmd+L to clear chat and collapse back to single line
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'l') {
    e.preventDefault();
    historyDrawer.classList.add('hidden');
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
