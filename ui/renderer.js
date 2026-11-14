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
    barContainer.classList.add('expanded');
    dynamicContent.classList.remove('hidden');
    window.ghostAPI?.setWindowHeight?.(480, true);
  }
}

function collapseWindow() {
  isExpanded = false;
  barContainer.classList.remove('expanded');
  dynamicContent.classList.add('hidden');
  historyDrawer.classList.add('hidden');
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

function safeParseEnvelope(input) {
  if (!input) return { display: 'line', body: '' };
  let candidate = input;

  // Unpack stringified JSON
  if (typeof candidate === 'string') {
    let clean = candidate.trim();
    if (clean.startsWith('```')) {
      clean = clean.replace(/^```(?:json)?\s*/i, '').replace(/\s*```$/i, '').trim();
    }
    try {
      candidate = JSON.parse(clean);
    } catch {
      if (clean.includes('\\"') || clean.includes('\\n')) {
        try {
          const unescaped = clean.replace(/\\"/g, '"').replace(/\\n/g, '\n');
          candidate = JSON.parse(unescaped);
        } catch {}
      }
    }
  }

  // If candidate is a dict and body itself contains an escaped JSON envelope
  if (candidate && typeof candidate === 'object') {
    if (typeof candidate.body === 'string') {
      const b = candidate.body.trim();
      if ((b.startsWith('{') && b.includes('display')) || (b.startsWith('{\\n') && b.includes('display'))) {
        try {
          const inner = safeParseEnvelope(b);
          if (inner && inner.body && inner.body !== b) {
            candidate = inner;
          }
        } catch {}
      }
    }
    return candidate;
  }

  return { display: 'line', body: String(input) };
}

function appendGhostMessage(data) {
  data = safeParseEnvelope(data);
  const row = document.createElement('div');
  row.className = 'chat-row ghost';

  const bubble = document.createElement('div');
  bubble.className = 'chat-bubble ghost';

  const mode = data.display || 'line';
  const bodyText = data.body || '';
  const titleText = data.title || '';

  // Main clean formatted text body
  if (bodyText && mode !== 'email_compose') {
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

  // 1. Generic Compose Widget (notes, general documents)
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

  // 2. Email List Card (Inbox Stream with Account Badges, Snippet Previews, Quick Reply)
  if (mode === 'email_list') {
    const emailListCard = document.createElement('div');
    emailListCard.className = 'email-list-card';

    const cardHeader = document.createElement('div');
    cardHeader.className = 'email-card-header';

    const headerTitle = document.createElement('div');
    headerTitle.className = 'email-card-title';
    headerTitle.innerHTML = `<span class="email-icon">@</span> <span>${escapeHtml(titleText || 'Inbox Stream')}</span>`;

    const emails = Array.isArray(data.emails) ? data.emails : [];
    const headerMeta = document.createElement('span');
    headerMeta.className = 'email-card-badge';
    headerMeta.textContent = `${emails.length} ${emails.length === 1 ? 'message' : 'messages'}`;

    cardHeader.appendChild(headerTitle);
    cardHeader.appendChild(headerMeta);
    emailListCard.appendChild(cardHeader);

    const emailListBody = document.createElement('div');
    emailListBody.className = 'email-items-container';

    if (emails.length === 0) {
      const emptyNotice = document.createElement('div');
      emptyNotice.className = 'email-empty-state';
      emptyNotice.textContent = 'No messages found in configured inboxes.';
      emailListBody.appendChild(emptyNotice);
    } else {
      emails.forEach((item) => {
        const itemEl = document.createElement('div');
        itemEl.className = 'email-item' + (item.unread ? ' unread' : '');

        // Account badge: personal vs work
        const isWork = (item.account || '').toLowerCase().includes('work') || (item.account_name || '').toLowerCase().includes('prof');
        const badgeClass = isWork ? 'email-badge-work' : 'email-badge-personal';
        const badgeLabel = escapeHtml(item.account_name || (isWork ? 'Work' : 'Personal'));

        itemEl.innerHTML = `
          <div class="email-item-header">
            <div class="email-item-sender-group">
              <span class="email-pill ${badgeClass}">${badgeLabel}</span>
              <span class="email-sender" title="${escapeHtml(item.from || '')}">${escapeHtml(item.from || 'Unknown')}</span>
            </div>
            <span class="email-date">${escapeHtml(item.date || '')}</span>
          </div>
          <div class="email-subject">${escapeHtml(item.subject || '(No Subject)')}</div>
          <div class="email-snippet">${escapeHtml(item.snippet || '')}</div>
          <div class="email-item-actions">
            <button class="email-action-btn email-btn-reply" title="Reply to this email">Reply</button>
            <button class="email-action-btn email-btn-read" title="Read full message">Read Full</button>
          </div>
        `;

        // Wire Reply button
        const btnReply = itemEl.querySelector('.email-btn-reply');
        if (btnReply) {
          btnReply.addEventListener('click', (e) => {
            e.stopPropagation();
            const replyTo = item.from || '';
            const replySub = item.subject?.startsWith('Re:') ? item.subject : `Re: ${item.subject || ''}`;
            input.value = `Draft an email reply to ${replyTo} regarding "${replySub}" from my ${item.account || 'personal'} account`;
            submitTask();
          });
        }

        // Wire Read Full button
        const btnRead = itemEl.querySelector('.email-btn-read');
        if (btnRead) {
          btnRead.addEventListener('click', (e) => {
            e.stopPropagation();
            input.value = `Read email ID ${item.id} from account ${item.account}`;
            submitTask();
          });
        }

        // Toggle snippet expansion on click
        itemEl.addEventListener('click', () => {
          itemEl.classList.toggle('expanded');
        });

        emailListBody.appendChild(itemEl);
      });
    }

    emailListCard.appendChild(emailListBody);
    bubble.appendChild(emailListCard);
  }

  // 3. Interactive Email Composer Card (Account switcher, editable To/Subject/Body, Send/Copy/Discard)
  if (mode === 'email_compose') {
    const composeCard = document.createElement('div');
    composeCard.className = 'email-compose-card';

    // Header with Title & Account Switcher
    const compHeader = document.createElement('div');
    compHeader.className = 'email-compose-header';

    const titleGroup = document.createElement('div');
    titleGroup.className = 'email-compose-title';
    titleGroup.innerHTML = `<span>${escapeHtml(titleText || 'Email Composer')}</span>`;

    // Account pill selector
    let currentAccount = (data.account || 'personal').toLowerCase();
    const accountSelector = document.createElement('div');
    accountSelector.className = 'email-account-toggle';

    const pillPersonal = document.createElement('button');
    pillPersonal.type = 'button';
    pillPersonal.className = 'account-toggle-btn' + (currentAccount === 'personal' ? ' active personal' : '');
    pillPersonal.textContent = 'Personal';

    const pillWork = document.createElement('button');
    pillWork.type = 'button';
    pillWork.className = 'account-toggle-btn' + (currentAccount === 'work' ? ' active work' : '');
    pillWork.textContent = 'Work';

    pillPersonal.addEventListener('click', () => {
      currentAccount = 'personal';
      pillPersonal.className = 'account-toggle-btn active personal';
      pillWork.className = 'account-toggle-btn';
    });

    pillWork.addEventListener('click', () => {
      currentAccount = 'work';
      pillWork.className = 'account-toggle-btn active work';
      pillPersonal.className = 'account-toggle-btn';
    });

    accountSelector.appendChild(pillPersonal);
    accountSelector.appendChild(pillWork);

    compHeader.appendChild(titleGroup);
    compHeader.appendChild(accountSelector);
    composeCard.appendChild(compHeader);

    // Form fields: To, Subject, Body
    const formContainer = document.createElement('div');
    formContainer.className = 'email-compose-fields';

    // Field: To
    const toRow = document.createElement('div');
    toRow.className = 'email-field-row';
    toRow.innerHTML = `<label class="email-field-label">To:</label>`;
    const toInput = document.createElement('input');
    toInput.type = 'text';
    toInput.className = 'email-field-input';
    toInput.value = data.to || '';
    toInput.placeholder = 'recipient@example.com';
    toRow.appendChild(toInput);
    formContainer.appendChild(toRow);

    // Field: Subject
    const subRow = document.createElement('div');
    subRow.className = 'email-field-row';
    subRow.innerHTML = `<label class="email-field-label">Subject:</label>`;
    const subInput = document.createElement('input');
    subInput.type = 'text';
    subInput.className = 'email-field-input';
    subInput.value = data.subject || '';
    subInput.placeholder = 'Subject line';
    subRow.appendChild(subInput);
    formContainer.appendChild(subRow);

    // Field: Body
    const bodyArea = document.createElement('textarea');
    bodyArea.className = 'email-compose-textarea';
    bodyArea.value = data.body || '';
    bodyArea.placeholder = 'Write your email here...';
    bodyArea.spellcheck = false;
    formContainer.appendChild(bodyArea);

    composeCard.appendChild(formContainer);

    // Action buttons: Send, Copy, Discard
    const actionRow = document.createElement('div');
    actionRow.className = 'email-compose-actions';

    // Extract ticket id if provided
    let ticketId = data.ticket_id || '';
    if (!ticketId && Array.isArray(data.actions)) {
      for (const act of data.actions) {
        if (act.payload && act.payload.includes('confirm: send_email ')) {
          ticketId = act.payload.split('confirm: send_email ')[1].trim();
          break;
        }
      }
    }

    const btnSend = document.createElement('button');
    btnSend.className = 'btn btn-primary email-btn-send';
    btnSend.innerHTML = `<span>Send Email</span>`;
    btnSend.addEventListener('click', () => {
      btnSend.disabled = true;
      btnSend.textContent = 'Sending...';

      const payloadObj = {
        ticket_id: ticketId,
        account: currentAccount,
        to: toInput.value.trim(),
        subject: subInput.value.trim(),
        body: bodyArea.value.trim(),
      };

      input.value = `confirm: send_email ${JSON.stringify(payloadObj)}`;
      submitTask();
    });

    const btnCopy = document.createElement('button');
    btnCopy.className = 'btn btn-secondary';
    btnCopy.textContent = 'Copy Draft';
    btnCopy.addEventListener('click', () => {
      const fullText = `To: ${toInput.value}\nSubject: ${subInput.value}\n\n${bodyArea.value}`;
      navigator.clipboard.writeText(fullText);
      btnCopy.textContent = 'Copied!';
      setTimeout(() => { btnCopy.textContent = 'Copy Draft'; }, 1500);
    });

    const btnDiscard = document.createElement('button');
    btnDiscard.className = 'btn btn-danger';
    btnDiscard.textContent = 'Discard';
    btnDiscard.addEventListener('click', () => {
      composeCard.remove();
    });

    actionRow.appendChild(btnSend);
    actionRow.appendChild(btnCopy);
    actionRow.appendChild(btnDiscard);
    composeCard.appendChild(actionRow);

    bubble.appendChild(composeCard);
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
    btnOk.textContent = (data.actions && data.actions[0] && data.actions[0].label) || 'Confirm Action';
    btnOk.addEventListener('click', () => {
      btnOk.disabled = true;
      btnOk.textContent = 'Executing...';
      let payload = '';
      if (data.actions && data.actions[0] && data.actions[0].payload) {
        payload = data.actions[0].payload;
      } else if (bodyText.includes('ticket:')) {
        const ticketMatch = bodyText.match(/ticket:\s*([a-zA-Z0-9_-]+)/);
        if (ticketMatch) {
          payload = `confirm: trash ${ticketMatch[1]}`;
        }
      }
      input.value = payload || `confirm: ${bodyText || titleText}`;
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

    const data = safeParseEnvelope(rawResult);
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
    barContainer.classList.add('expanded');
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
    if (dynamicContent.classList.contains('hidden') || !chatStream.children.length) {
      collapseWindow();
    }
    input.focus();
  }
}

if (btnCloseDrawer) {
  btnCloseDrawer.addEventListener('click', () => {
    historyDrawer.classList.add('hidden');
    if (dynamicContent.classList.contains('hidden') || !chatStream.children.length) {
      collapseWindow();
    }
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
        const data = safeParseEnvelope(turn.text);
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
