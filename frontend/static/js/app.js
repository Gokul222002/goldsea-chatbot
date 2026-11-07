// GoldSea AI — Client Application Engine
(function() {
  'use strict';

  // State
  let currentConversationId = localStorage.getItem('goldsea_active_conv') || null;
  let conversations = [];
  let isStreaming = false;
  let currentAbortController = null;
  let attachedFile = null; // { name: string, content: string }
  let recognition = null;
  let isRecording = false;
  let deferredPrompt = null;

  // DOM Elements
  const messagesContainer = document.getElementById('messages-container');
  const messagesList = document.getElementById('messages-list');
  const welcomeView = document.getElementById('welcome-view');
  const chatInput = document.getElementById('chat-input');
  const sendBtn = document.getElementById('send-btn');
  const newChatBtn = document.getElementById('new-chat-btn');
  const headerNewChatBtn = document.getElementById('header-new-chat-btn');
  const conversationsList = document.getElementById('conversations-list');
  const activeChatTitle = document.getElementById('active-chat-title');
  const searchConvInput = document.getElementById('search-conv-input');

  // Mobile Drawer
  const sidebar = document.getElementById('sidebar');
  const sidebarBackdrop = document.getElementById('sidebar-backdrop');
  const openSidebarBtn = document.getElementById('open-sidebar-btn');
  const closeSidebarBtn = document.getElementById('close-sidebar-btn');

  // Attachment & Voice
  const fileInput = document.getElementById('file-input');
  const attachFileBtn = document.getElementById('attach-file-btn');
  const attachmentPreview = document.getElementById('attachment-preview');
  const attachmentName = document.getElementById('attachment-name');
  const removeAttachmentBtn = document.getElementById('remove-attachment-btn');
  const voiceInputBtn = document.getElementById('voice-input-btn');

  // Modals
  const shortcutsModal = document.getElementById('shortcuts-modal');
  const shortcutsModalBtn = document.getElementById('shortcuts-modal-btn');
  const closeShortcutsBtn = document.getElementById('close-shortcuts-btn');
  const exportModal = document.getElementById('export-modal');
  const exportChatBtn = document.getElementById('export-chat-btn');
  const closeExportBtn = document.getElementById('close-export-btn');
  const openQuickActionsBtn = document.getElementById('open-quick-actions-btn');
  const pwaInstallBtn = document.getElementById('pwa-install-btn');

  // Initialize
  async function init() {
    initLucide();
    initSpeechRecognition();
    initServiceWorker();
    setupEventListeners();
    await loadConversations();
    if (currentConversationId) {
      await loadConversationMessages(currentConversationId);
    } else {
      showWelcome();
    }
  }

  function initLucide() {
    if (window.lucide) {
      window.lucide.createIcons();
    }
  }

  // --- Speech Recognition ---
  function initSpeechRecognition() {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (SpeechRecognition) {
      recognition = new SpeechRecognition();
      recognition.continuous = false;
      recognition.interimResults = true;
      recognition.lang = 'en-US';

      recognition.onstart = () => {
        isRecording = true;
        voiceInputBtn.classList.add('recording-active');
      };

      recognition.onresult = (event) => {
        let transcript = '';
        for (let i = event.resultIndex; i < event.results.length; ++i) {
          transcript += event.results[i][0].transcript;
        }
        chatInput.value = transcript;
        updateSendButtonState();
        autoResizeInput();
      };

      recognition.onerror = () => {
        stopRecording();
      };

      recognition.onend = () => {
        stopRecording();
      };
    } else {
      voiceInputBtn.style.display = 'none';
    }
  }

  function toggleRecording() {
    if (!recognition) return;
    if (isRecording) {
      recognition.stop();
      stopRecording();
    } else {
      try {
        recognition.start();
      } catch (err) {
        stopRecording();
      }
    }
  }

  function stopRecording() {
    isRecording = false;
    voiceInputBtn.classList.remove('recording-active');
  }

  // --- PWA Service Worker ---
  function initServiceWorker() {
    if ('serviceWorker' in navigator) {
      window.addEventListener('load', () => {
        navigator.serviceWorker.register('/sw.js').catch(() => {});
      });
    }

    window.addEventListener('beforeinstallprompt', (e) => {
      e.preventDefault();
      deferredPrompt = e;
      if (pwaInstallBtn) {
        pwaInstallBtn.classList.remove('hidden');
      }
    });

    if (pwaInstallBtn) {
      pwaInstallBtn.addEventListener('click', async () => {
        if (deferredPrompt) {
          deferredPrompt.prompt();
          const { outcome } = await deferredPrompt.userChoice;
          if (outcome === 'accepted') {
            pwaInstallBtn.classList.add('hidden');
          }
          deferredPrompt = null;
        }
      });
    }
  }

  // --- Conversations Management ---
  async function loadConversations() {
    try {
      const res = await fetch('/api/conversations');
      if (res.ok) {
        conversations = await res.json();
        renderConversationsList();
      }
    } catch (err) {
      console.error('Failed to load conversations', err);
    }
  }

  function renderConversationsList() {
    conversationsList.innerHTML = '';
    const query = (searchConvInput.value || '').toLowerCase();
    const filtered = conversations.filter(c => c.title.toLowerCase().includes(query));

    if (filtered.length === 0) {
      conversationsList.innerHTML = `<div class="p-3 text-center text-xs text-slate-500">No conversations</div>`;
      return;
    }

    filtered.forEach(conv => {
      const isActive = conv.id === currentConversationId;
      const item = document.createElement('div');
      item.className = `group flex items-center justify-between px-3 py-2 rounded-xl text-xs cursor-pointer transition-colors ${
        isActive ? 'bg-gold-500/10 text-gold-400 font-medium border border-gold-500/20' : 'text-slate-300 hover:bg-white/5'
      }`;

      item.innerHTML = `
        <div class="flex items-center gap-2 truncate flex-1 mr-2" data-conv-id="${conv.id}">
          <i data-lucide="message-square" class="w-3.5 h-3.5 flex-shrink-0 ${isActive ? 'text-gold-400' : 'text-slate-400'}"></i>
          <span class="truncate">${escapeHtml(conv.title)}</span>
        </div>
        <div class="opacity-0 group-hover:opacity-100 flex items-center gap-1">
          <button class="delete-conv-btn p-1 text-slate-400 hover:text-rose-400" title="Delete" data-conv-id="${conv.id}">
            <i data-lucide="trash-2" class="w-3 h-3"></i>
          </button>
        </div>
      `;

      item.querySelector('[data-conv-id]').addEventListener('click', () => {
        switchConversation(conv.id);
        closeMobileSidebar();
      });

      const delBtn = item.querySelector('.delete-conv-btn');
      delBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        deleteConversation(conv.id);
      });

      conversationsList.appendChild(item);
    });

    initLucide();
  }

  async function switchConversation(convId) {
    if (convId === currentConversationId) return;
    currentConversationId = convId;
    localStorage.setItem('goldsea_active_conv', convId);
    renderConversationsList();
    await loadConversationMessages(convId);
  }

  async function loadConversationMessages(convId) {
    try {
      const res = await fetch(`/api/conversations/${convId}`);
      if (!res.ok) {
        startNewChat();
        return;
      }
      const data = await res.json();
      activeChatTitle.textContent = data.title || 'Conversation';
      renderMessages(data.messages || []);
    } catch (err) {
      startNewChat();
    }
  }

  async function deleteConversation(convId) {
    try {
      await fetch(`/api/conversations/${convId}`, { method: 'DELETE' });
      conversations = conversations.filter(c => c.id !== convId);
      if (currentConversationId === convId) {
        startNewChat();
      } else {
        renderConversationsList();
      }
    } catch (err) {
      console.error('Failed to delete conversation', err);
    }
  }

  function startNewChat() {
    currentConversationId = null;
    localStorage.removeItem('goldsea_active_conv');
    activeChatTitle.textContent = 'New Conversation';
    messagesList.innerHTML = '';
    renderConversationsList();
    showWelcome();
    chatInput.focus();
    closeMobileSidebar();
  }

  function showWelcome() {
    welcomeView.classList.remove('hidden');
    messagesList.classList.add('hidden');
  }

  function hideWelcome() {
    welcomeView.classList.add('hidden');
    messagesList.classList.remove('hidden');
  }

  // --- Rendering Messages ---
  function renderMessages(messages) {
    if (!messages || messages.length === 0) {
      showWelcome();
      return;
    }
    hideWelcome();
    messagesList.innerHTML = '';
    messages.forEach(msg => {
      appendMessageToUI(msg);
    });
    scrollToBottom();
  }

  function appendMessageToUI(msg) {
    hideWelcome();
    const isUser = msg.role === 'user';
    const card = document.createElement('div');
    card.id = `msg-${msg.id}`;
    card.className = `flex flex-col ${isUser ? 'items-end' : 'items-start'} space-y-1.5`;

    if (isUser) {
      card.innerHTML = `
        <div class="max-w-[85%] sm:max-w-xl rounded-2xl rounded-tr-sm bg-gradient-to-r from-amber-500/20 to-gold-500/20 border border-gold-500/30 p-3.5 text-xs sm:text-sm text-slate-100 shadow-sm leading-relaxed whitespace-pre-wrap">
          ${escapeHtml(msg.content)}
        </div>
      `;
    } else {
      const formattedHtml = renderMarkdown(msg.content);
      
      // Sources badges if any
      let sourcesHtml = '';
      if (msg.sources && msg.sources.length > 0) {
        const sourcePills = msg.sources.map(s => `
          <a href="${escapeHtml(s.url)}" target="_blank" rel="noopener noreferrer" class="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg bg-dark-800 hover:bg-dark-750 border border-cyan-500/20 text-cyan-400 text-[11px] hover:border-cyan-500/40 transition-colors">
            <i data-lucide="external-link" class="w-3 h-3"></i>
            <span class="max-w-[140px] truncate">${escapeHtml(s.title || 'Source')}</span>
          </a>
        `).join('');
        sourcesHtml = `
          <div class="mt-2.5 pt-2 border-t border-white/5">
            <div class="text-[10px] font-semibold text-slate-400 mb-1.5 flex items-center gap-1">
              <i data-lucide="check-check" class="w-3 h-3 text-emerald-400"></i>
              Grounded Sources Verified:
            </div>
            <div class="flex flex-wrap gap-1.5">${sourcePills}</div>
          </div>
        `;
      }

      // Follow-up chips if any
      let chipsHtml = '';
      if (msg.follow_up_chips && msg.follow_up_chips.length > 0) {
        const chipsList = msg.follow_up_chips.map(chip => `
          <button class="follow-up-chip px-3 py-1.5 rounded-full bg-dark-850 hover:bg-dark-800 border border-gold-500/30 hover:border-gold-500/60 text-gold-400 hover:text-gold-300 text-xs font-medium transition-all text-left shadow-sm active:scale-95 flex items-center gap-1.5">
            <i data-lucide="arrow-right" class="w-3 h-3"></i>
            <span>${escapeHtml(chip)}</span>
          </button>
        `).join('');
        chipsHtml = `
          <div class="mt-3 pt-2.5 border-t border-white/5 space-y-1.5">
            <div class="text-[11px] font-semibold text-slate-400">Suggested Follow-ups:</div>
            <div class="flex flex-wrap gap-2">${chipsList}</div>
          </div>
        `;
      }

      // Per-reply Action Buttons (Regenerate, Make shorter, Make more detailed, Copy)
      const actionsBarHtml = `
        <div class="mt-2.5 flex items-center gap-1 text-[11px] text-slate-400 border-t border-white/5 pt-2">
          <button class="per-reply-btn hover:text-gold-400 p-1.5 rounded-md hover:bg-white/5 flex items-center gap-1 transition-colors" data-action="regenerate" data-msg-id="${msg.id}" title="Regenerate this response">
            <i data-lucide="refresh-cw" class="w-3.5 h-3.5"></i>
            <span class="hidden sm:inline">Regenerate</span>
          </button>
          <button class="per-reply-btn hover:text-gold-400 p-1.5 rounded-md hover:bg-white/5 flex items-center gap-1 transition-colors" data-action="shorter" data-msg-id="${msg.id}" title="Make shorter">
            <i data-lucide="minimize-2" class="w-3.5 h-3.5"></i>
            <span class="hidden sm:inline">Make shorter</span>
          </button>
          <button class="per-reply-btn hover:text-gold-400 p-1.5 rounded-md hover:bg-white/5 flex items-center gap-1 transition-colors" data-action="detailed" data-msg-id="${msg.id}" title="Make more detailed">
            <i data-lucide="maximize-2" class="w-3.5 h-3.5"></i>
            <span class="hidden sm:inline">Make more detailed</span>
          </button>
          <button class="copy-reply-btn ml-auto hover:text-white p-1.5 rounded-md hover:bg-white/5 flex items-center gap-1 transition-colors" title="Copy response">
            <i data-lucide="copy" class="w-3.5 h-3.5"></i>
            <span class="copy-label hidden sm:inline">Copy</span>
          </button>
        </div>
      `;

      card.innerHTML = `
        <div class="max-w-[95%] sm:max-w-2xl rounded-2xl rounded-tl-sm bg-dark-900 border border-white/5 p-4 shadow-md w-full">
          <div class="prose max-w-none text-slate-200">
            ${formattedHtml}
          </div>
          ${sourcesHtml}
          ${chipsHtml}
          ${actionsBarHtml}
        </div>
      `;

      // Attach chip handlers
      card.querySelectorAll('.follow-up-chip').forEach(btn => {
        btn.addEventListener('click', () => {
          chatInput.value = btn.innerText.trim();
          sendMessage();
        });
      });

      // Attach per-reply action handlers
      card.querySelectorAll('.per-reply-btn').forEach(btn => {
        btn.addEventListener('click', () => {
          handlePerReplyAction(btn.dataset.action, btn.dataset.msgId);
        });
      });

      // Copy response handler
      const copyBtn = card.querySelector('.copy-reply-btn');
      if (copyBtn) {
        copyBtn.addEventListener('click', () => {
          navigator.clipboard.writeText(msg.content);
          const label = copyBtn.querySelector('.copy-label');
          if (label) label.textContent = 'Copied!';
          setTimeout(() => { if (label) label.textContent = 'Copy'; }, 2000);
        });
      }
    }

    messagesList.appendChild(card);
    initLucide();
    highlightCodeBlocks(card);
  }

  function renderMarkdown(raw) {
    if (!raw) return '';
    try {
      const parsed = marked.parse(raw, { gfm: true, breaks: true });
      return DOMPurify.sanitize(parsed);
    } catch (e) {
      return escapeHtml(raw);
    }
  }

  function highlightCodeBlocks(container) {
    if (window.hljs) {
      container.querySelectorAll('pre code').forEach((block) => {
        window.hljs.highlightElement(block);
      });
    }
  }

  function scrollToBottom() {
    messagesContainer.scrollTop = messagesContainer.scrollHeight;
  }

  // --- Send Message & Streaming Engine ---
  async function sendMessage(textOverride = null) {
    const rawText = textOverride !== null ? textOverride : chatInput.value.trim();
    if (!rawText && !attachedFile) return;
    if (isStreaming) return;

    let messageToSend = rawText;
    if (attachedFile) {
      messageToSend = `[Attached File: ${attachedFile.name}]\n\`\`\`\n${attachedFile.content}\n\`\`\`\n\n${rawText}`;
      clearAttachment();
    }

    // Reset input
    chatInput.value = '';
    updateSendButtonState();
    autoResizeInput();

    // Create temporary UI card for user
    const tempUserMsg = {
      id: 'tmp_' + Date.now(),
      role: 'user',
      content: messageToSend
    };
    appendMessageToUI(tempUserMsg);
    scrollToBottom();

    // Setup Assistant Streaming Card
    isStreaming = true;
    currentAbortController = new AbortController();

    const assistantMsgId = 'msg_' + Date.now();
    const assistantCard = document.createElement('div');
    assistantCard.id = `msg-${assistantMsgId}`;
    assistantCard.className = 'flex flex-col items-start space-y-1.5 w-full';
    assistantCard.innerHTML = `
      <div class="max-w-[95%] sm:max-w-2xl rounded-2xl rounded-tl-sm bg-dark-900 border border-white/5 p-4 shadow-md w-full">
        <div class="prose max-w-none text-slate-200" id="stream-content-${assistantMsgId}">
          <div class="flex items-center gap-2 text-slate-400 text-xs py-1">
            <span class="w-2 h-2 rounded-full bg-gold-400 animate-ping"></span>
            <span>Thinking and verifying...</span>
          </div>
        </div>
        <div id="stream-sources-${assistantMsgId}"></div>
        <div id="stream-chips-${assistantMsgId}"></div>
        <div id="stream-actions-${assistantMsgId}" class="hidden"></div>
      </div>
    `;
    messagesList.appendChild(assistantCard);
    scrollToBottom();

    let fullAccumulatedText = '';
    let accumulatedSources = [];
    let accumulatedChips = [];

    try {
      const response = await fetch('/api/chat/stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: messageToSend,
          conversation_id: currentConversationId,
          enable_search: true
        }),
        signal: currentAbortController.signal
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }

      // Read conversation ID from header if new
      const headerConvId = response.headers.get('X-Conversation-Id');
      if (headerConvId && headerConvId !== currentConversationId) {
        currentConversationId = headerConvId;
        localStorage.setItem('goldsea_active_conv', currentConversationId);
        loadConversations();
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      const contentEl = document.getElementById(`stream-content-${assistantMsgId}`);

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop(); // keep remainder

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            const jsonStr = line.slice(6).trim();
            if (!jsonStr) continue;

            try {
              const eventData = JSON.parse(jsonStr);

              if (eventData.type === 'sources') {
                accumulatedSources = eventData.sources || [];
                renderSourcesInStream(assistantMsgId, accumulatedSources);
              } else if (eventData.type === 'token') {
                fullAccumulatedText += eventData.token;
                contentEl.innerHTML = renderMarkdown(fullAccumulatedText);
                highlightCodeBlocks(contentEl);
                scrollToBottom();
              } else if (eventData.type === 'follow_up_chips') {
                accumulatedChips = eventData.chips || [];
              } else if (eventData.type === 'error') {
                renderErrorState(assistantCard, eventData.message, messageToSend);
                return;
              } else if (eventData.type === 'done') {
                finalizeStream(assistantCard, assistantMsgId, fullAccumulatedText, accumulatedSources, accumulatedChips);
              }
            } catch (err) {
              console.error('SSE parse error', err);
            }
          }
        }
      }

      finalizeStream(assistantCard, assistantMsgId, fullAccumulatedText, accumulatedSources, accumulatedChips);

    } catch (err) {
      if (err.name !== 'AbortError') {
        renderErrorState(assistantCard, 'Service connection failed or timed out.', messageToSend);
      }
    } finally {
      isStreaming = false;
      currentAbortController = null;
      initLucide();
    }
  }

  function renderSourcesInStream(msgId, sources) {
    const container = document.getElementById(`stream-sources-${msgId}`);
    if (!container || !sources.length) return;
    const pills = sources.map(s => `
      <a href="${escapeHtml(s.url)}" target="_blank" rel="noopener noreferrer" class="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg bg-dark-800 hover:bg-dark-750 border border-cyan-500/20 text-cyan-400 text-[11px] hover:border-cyan-500/40 transition-colors">
        <i data-lucide="external-link" class="w-3 h-3"></i>
        <span class="max-w-[140px] truncate">${escapeHtml(s.title || 'Source')}</span>
      </a>
    `).join('');
    container.innerHTML = `
      <div class="mt-2.5 pt-2 border-t border-white/5">
        <div class="text-[10px] font-semibold text-slate-400 mb-1.5 flex items-center gap-1">
          <i data-lucide="check-check" class="w-3 h-3 text-emerald-400"></i>
          Grounded Sources Verified:
        </div>
        <div class="flex flex-wrap gap-1.5">${pills}</div>
      </div>
    `;
    initLucide();
  }

  function finalizeStream(card, msgId, fullText, sources, chips) {
    const contentEl = document.getElementById(`stream-content-${msgId}`);
    if (contentEl) {
      contentEl.innerHTML = renderMarkdown(fullText);
      highlightCodeBlocks(contentEl);
    }

    // Render chips
    const chipsContainer = document.getElementById(`stream-chips-${msgId}`);
    if (chipsContainer && chips && chips.length > 0) {
      const chipsList = chips.map(chip => `
        <button class="follow-up-chip px-3 py-1.5 rounded-full bg-dark-850 hover:bg-dark-800 border border-gold-500/30 hover:border-gold-500/60 text-gold-400 hover:text-gold-300 text-xs font-medium transition-all text-left shadow-sm active:scale-95 flex items-center gap-1.5">
          <i data-lucide="arrow-right" class="w-3 h-3"></i>
          <span>${escapeHtml(chip)}</span>
        </button>
      `).join('');
      chipsContainer.innerHTML = `
        <div class="mt-3 pt-2.5 border-t border-white/5 space-y-1.5">
          <div class="text-[11px] font-semibold text-slate-400">Suggested Follow-ups:</div>
          <div class="flex flex-wrap gap-2">${chipsList}</div>
        </div>
      `;

      chipsContainer.querySelectorAll('.follow-up-chip').forEach(btn => {
        btn.addEventListener('click', () => {
          chatInput.value = btn.innerText.trim();
          sendMessage();
        });
      });
    }

    // Render actions bar
    const actionsContainer = document.getElementById(`stream-actions-${msgId}`);
    if (actionsContainer) {
      actionsContainer.className = "mt-2.5 flex items-center gap-1 text-[11px] text-slate-400 border-t border-white/5 pt-2";
      actionsContainer.innerHTML = `
        <button class="per-reply-btn hover:text-gold-400 p-1.5 rounded-md hover:bg-white/5 flex items-center gap-1 transition-colors" data-action="regenerate" data-msg-id="${msgId}">
          <i data-lucide="refresh-cw" class="w-3.5 h-3.5"></i>
          <span class="hidden sm:inline">Regenerate</span>
        </button>
        <button class="per-reply-btn hover:text-gold-400 p-1.5 rounded-md hover:bg-white/5 flex items-center gap-1 transition-colors" data-action="shorter" data-msg-id="${msgId}">
          <i data-lucide="minimize-2" class="w-3.5 h-3.5"></i>
          <span class="hidden sm:inline">Make shorter</span>
        </button>
        <button class="per-reply-btn hover:text-gold-400 p-1.5 rounded-md hover:bg-white/5 flex items-center gap-1 transition-colors" data-action="detailed" data-msg-id="${msgId}">
          <i data-lucide="maximize-2" class="w-3.5 h-3.5"></i>
          <span class="hidden sm:inline">Make more detailed</span>
        </button>
        <button class="copy-reply-btn ml-auto hover:text-white p-1.5 rounded-md hover:bg-white/5 flex items-center gap-1 transition-colors">
          <i data-lucide="copy" class="w-3.5 h-3.5"></i>
          <span class="copy-label hidden sm:inline">Copy</span>
        </button>
      `;

      actionsContainer.querySelectorAll('.per-reply-btn').forEach(btn => {
        btn.addEventListener('click', () => {
          handlePerReplyAction(btn.dataset.action, btn.dataset.msgId);
        });
      });

      const copyBtn = actionsContainer.querySelector('.copy-reply-btn');
      if (copyBtn) {
        copyBtn.addEventListener('click', () => {
          navigator.clipboard.writeText(fullText);
          const label = copyBtn.querySelector('.copy-label');
          if (label) label.textContent = 'Copied!';
          setTimeout(() => { if (label) label.textContent = 'Copy'; }, 2000);
        });
      }
    }

    initLucide();
    loadConversations();
  }

  function renderErrorState(card, errorMessage, queryToRetry) {
    card.innerHTML = `
      <div class="max-w-[95%] sm:max-w-xl rounded-2xl bg-rose-950/30 border border-rose-500/30 p-4 space-y-3">
        <div class="flex items-center gap-2 text-rose-400 font-semibold text-xs">
          <i data-lucide="alert-circle" class="w-4 h-4"></i>
          <span>${escapeHtml(errorMessage)}</span>
        </div>
        <p class="text-slate-300 text-xs">
          The AI provider hit a quota or temporary glitch. You can retry immediately.
        </p>
        <button class="retry-btn inline-flex items-center gap-2 bg-rose-600 hover:bg-rose-500 text-white font-semibold text-xs px-3.5 py-2 rounded-xl transition-all shadow-md active:scale-95">
          <i data-lucide="rotate-ccw" class="w-3.5 h-3.5"></i>
          <span>Retry Now</span>
        </button>
      </div>
    `;
    const retryBtn = card.querySelector('.retry-btn');
    if (retryBtn) {
      retryBtn.addEventListener('click', () => {
        card.remove();
        sendMessage(queryToRetry);
      });
    }
    initLucide();
  }

  // --- Per-Reply Action (Regenerate, Make shorter, Make more detailed) ---
  async function handlePerReplyAction(action, msgId) {
    if (isStreaming || !currentConversationId) return;

    const actionText = action === 'regenerate' ? 'Regenerating answer...' :
                       action === 'shorter' ? 'Condensing to punchy summary...' :
                       'Expanding with comprehensive detail...';

    // Temporary placeholder
    const placeholderCard = document.createElement('div');
    placeholderCard.className = 'flex flex-col items-start space-y-1.5 w-full';
    placeholderCard.innerHTML = `
      <div class="max-w-[95%] sm:max-w-2xl rounded-2xl bg-dark-900 border border-white/5 p-4 text-xs text-slate-400 flex items-center gap-2">
        <span class="w-2 h-2 rounded-full bg-gold-400 animate-ping"></span>
        <span>${actionText}</span>
      </div>
    `;
    messagesList.appendChild(placeholderCard);
    scrollToBottom();

    try {
      const res = await fetch('/api/chat/per-reply-action', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          action: action,
          message_id: msgId,
          conversation_id: currentConversationId
        })
      });

      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      placeholderCard.remove();
      appendMessageToUI({
        id: data.message_id,
        role: 'assistant',
        content: data.content,
        sources: data.sources,
        follow_up_chips: data.follow_up_chips
      });
      scrollToBottom();
    } catch (err) {
      placeholderCard.remove();
      renderErrorState(placeholderCard, 'Failed to process request.', 'Please retry.');
    }
  }

  // --- File Upload ---
  function setupFileHandling() {
    attachFileBtn.addEventListener('click', () => {
      fileInput.click();
    });

    fileInput.addEventListener('change', (e) => {
      const file = e.target.files[0];
      if (!file) return;

      const reader = new FileReader();
      reader.onload = (event) => {
        attachedFile = {
          name: file.name,
          content: event.target.result
        };
        attachmentName.textContent = file.name;
        attachmentPreview.classList.remove('hidden');
        updateSendButtonState();
        chatInput.focus();
      };
      reader.readAsText(file);
    });

    removeAttachmentBtn.addEventListener('click', () => {
      clearAttachment();
    });
  }

  function clearAttachment() {
    attachedFile = null;
    fileInput.value = '';
    attachmentPreview.classList.add('hidden');
    updateSendButtonState();
  }

  // --- Quick Actions Grid (Home Screen & Modal) ---
  function setupQuickActions() {
    document.querySelectorAll('[data-quick-action]').forEach(btn => {
      btn.addEventListener('click', () => {
        const action = btn.dataset.quickAction;
        const templates = {
          summarize: "Please summarize this text into key takeaways:\n\n",
          grammar: "Please fix my grammar, tone, and flow:\n\n",
          eli5: "Explain this concept like I'm new to it:\n\n",
          email: "Draft a polite, professional email about:\n\n",
          debug: "Debug this code and explain the fix:\n\n",
          plan: "Plan my day with a time-blocked schedule for:\n\n"
        };
        chatInput.value = templates[action] || '';
        hideWelcome();
        chatInput.focus();
        updateSendButtonState();
        autoResizeInput();
      });
    });
  }

  // --- Event Listeners & UI Controls ---
  function setupEventListeners() {
    // Send Click
    sendBtn.addEventListener('click', () => sendMessage());

    // Input Keydown
    chatInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
      }
    });

    chatInput.addEventListener('input', () => {
      updateSendButtonState();
      autoResizeInput();
    });

    // Voice
    voiceInputBtn.addEventListener('click', toggleRecording);

    // New Chat
    newChatBtn.addEventListener('click', startNewChat);
    headerNewChatBtn.addEventListener('click', startNewChat);

    // Mobile Sidebar Drawer
    openSidebarBtn.addEventListener('click', openMobileSidebar);
    closeSidebarBtn.addEventListener('click', closeMobileSidebar);
    sidebarBackdrop.addEventListener('click', closeMobileSidebar);

    // Search input for conversations
    searchConvInput.addEventListener('input', renderConversationsList);

    // Shortcuts Modal
    shortcutsModalBtn.addEventListener('click', () => shortcutsModal.classList.remove('hidden'));
    closeShortcutsBtn.addEventListener('click', () => shortcutsModal.classList.add('hidden'));

    // Export Modal
    exportChatBtn.addEventListener('click', () => {
      if (!currentConversationId) {
        alert('Please select or start a conversation first.');
        return;
      }
      exportModal.classList.remove('hidden');
    });
    closeExportBtn.addEventListener('click', () => exportModal.classList.add('hidden'));

    document.querySelectorAll('.export-format-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        const fmt = btn.dataset.format;
        if (currentConversationId) {
          window.open(`/api/conversations/${currentConversationId}/export?format=${fmt}`, '_blank');
          exportModal.classList.add('hidden');
        }
      });
    });

    // Global Desktop Keyboard Shortcuts
    document.addEventListener('keydown', (e) => {
      // Ctrl+N / Cmd+N -> New Chat
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'n') {
        e.preventDefault();
        startNewChat();
      }
      // Ctrl+K / Cmd+K -> Focus input or Quick Action
      else if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        chatInput.focus();
      }
      // Ctrl+/ -> Toggle Shortcuts Modal
      else if ((e.ctrlKey || e.metaKey) && e.key === '/') {
        e.preventDefault();
        shortcutsModal.classList.toggle('hidden');
      }
      // Escape -> Close any open modal or sidebar
      else if (e.key === 'Escape') {
        shortcutsModal.classList.add('hidden');
        exportModal.classList.add('hidden');
        closeMobileSidebar();
      }
    });

    setupFileHandling();
    setupQuickActions();
  }

  function openMobileSidebar() {
    sidebar.classList.remove('-translate-x-full');
    sidebarBackdrop.classList.remove('hidden');
  }

  function closeMobileSidebar() {
    sidebar.classList.add('-translate-x-full');
    sidebarBackdrop.classList.add('hidden');
  }

  function updateSendButtonState() {
    const hasText = chatInput.value.trim().length > 0;
    const hasFile = attachedFile !== null;
    sendBtn.disabled = !(hasText || hasFile) || isStreaming;
  }

  function autoResizeInput() {
    chatInput.style.height = 'auto';
    chatInput.style.height = Math.min(chatInput.scrollHeight, 140) + 'px';
  }

  function escapeHtml(str) {
    if (!str) return '';
    return str
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }

  // Launch app
  document.addEventListener('DOMContentLoaded', init);

})();
