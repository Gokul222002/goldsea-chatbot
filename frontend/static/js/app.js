// GoldSea AI — Client Application Engine
(function() {
  'use strict';

  // State
  let currentConversationId = localStorage.getItem('goldsea_active_conv') || null;
  let conversations = [];
  let isStreaming = false;
  let currentAbortController = null;
  
  // Attachments state (multiple files & images)
  let attachedFiles = []; // Array of { name, type, mime_type, size, data, preview, extracted_text, page_images, page_count }

  // Voice / Mic State
  let recognition = null;
  let mediaRecorder = null;
  let audioChunks = [];
  let isRecording = false;
  let micState = 'idle'; // 'idle' | 'requesting' | 'listening' | 'processing'
  let silenceTimer = null;
  let deferredPrompt = null;

  // --- Auth & Session State ---
  let currentUser = null;
  let csrfToken = null;
  let pendingEmail = '';
  let resendTimerInterval = null;

  async function fetchCsrfToken() {
    try {
      const res = await fetch('/api/auth/csrf', { credentials: 'include' });
      if (res.ok) {
        const data = await res.json();
        csrfToken = data.csrf_token;
      }
    } catch (e) {
      console.warn('Failed to fetch CSRF token', e);
    }
  }

  // Wrapper for all authenticated API requests
  async function authFetch(url, options = {}) {
    options.credentials = 'include';
    options.headers = options.headers || {};
    const method = (options.method || 'GET').toUpperCase();
    if (csrfToken && !['GET', 'HEAD'].includes(method)) {
      if (options.headers instanceof Headers) {
        options.headers.set('X-CSRF-Token', csrfToken);
      } else {
        options.headers['X-CSRF-Token'] = csrfToken;
      }
    }
    const res = await fetch(url, options);
    if (res.status === 401) {
      currentUser = null;
      showAuthScreen('login');
      return res;
    }
    if (res.status === 403) {
      const clone = res.clone();
      try {
        const err = await clone.json();
        if (err.detail && err.detail.toLowerCase().includes('verification required')) {
          showAuthScreen('verify');
        }
      } catch (_) {}
      return res;
    }
    return res;
  }

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

  // Attachment & Voice Elements
  const fileInput = document.getElementById('file-input');
  const attachFileBtn = document.getElementById('attach-file-btn');
  const attachmentsContainer = document.getElementById('attachments-container');
  const voiceInputBtn = document.getElementById('voice-input-btn');
  const micStatusDot = document.getElementById('mic-status-dot');
  const dropZoneOverlay = document.getElementById('drop-zone-overlay');
  const imageModal = document.getElementById('image-modal');
  const enlargedImage = document.getElementById('enlarged-image');
  const closeImageModalBtn = document.getElementById('close-image-modal-btn');
  const toastContainer = document.getElementById('toast-container');

  // Modals & PWA Banners
  const shortcutsModal = document.getElementById('shortcuts-modal');
  const shortcutsModalBtn = document.getElementById('shortcuts-modal-btn');
  const closeShortcutsBtn = document.getElementById('close-shortcuts-btn');
  const openQuickActionsBtn = document.getElementById('open-quick-actions-btn');
  const quickActionsModal = document.getElementById('quick-actions-modal');
  const closeQuickActionsBtn = document.getElementById('close-quick-actions-btn');
  const exportModal = document.getElementById('export-modal');
  const exportChatBtn = document.getElementById('export-chat-btn');
  const closeExportBtn = document.getElementById('close-export-btn');
  const pwaInstallBtn = document.getElementById('pwa-install-btn');
  const iosInstallBanner = document.getElementById('ios-install-banner');
  const dismissIosBannerBtn = document.getElementById('dismiss-ios-banner-btn');

  // Format bytes helper
  function formatBytes(bytes, decimals = 1) {
    if (!bytes || bytes === 0) return '0 B';
    const k = 1024;
    const dm = decimals < 0 ? 0 : decimals;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(dm)) + ' ' + sizes[i];
  }

  // Toast Notification helper
  function showToast(message, type = 'info') {
    if (!toastContainer) return;
    const toast = document.createElement('div');
    const isErr = type === 'error';
    toast.className = `toast-msg flex items-center gap-2.5 px-4 py-3 rounded-xl shadow-xl text-xs font-medium border ${
      isErr 
        ? 'bg-rose-950/90 text-rose-200 border-rose-500/40' 
        : 'bg-dark-900/90 text-slate-200 border-spider-500/40'
    }`;
    toast.innerHTML = `
      <i data-lucide="${isErr ? 'alert-triangle' : 'info'}" class="w-4 h-4 ${isErr ? 'text-rose-400' : 'text-spider-400'} shrink-0"></i>
      <span class="flex-1">${escapeHtml(message)}</span>
      <button class="text-slate-400 hover:text-white ml-1 text-sm leading-none">&times;</button>
    `;
    const closeBtn = toast.querySelector('button');
    closeBtn.addEventListener('click', () => toast.remove());
    toastContainer.appendChild(toast);
    initLucide();
    setTimeout(() => {
      if (toast.parentElement) toast.remove();
    }, 5000);
  }

  // Initialize Application
  async function init() {
    initVisualViewport();
    closeMobileSidebar();
    setupDrawerSwipe();
    initLucide();
    initSpeechRecognition();
    initServiceWorker();
    initIosInstallBanner();
    setupEventListeners();
    setupDragAndDropAndPaste();
    setupAuthHandlers();
    setupAccountSettingsHandlers();

    await fetchCsrfToken();
    const authenticated = await checkAuthState();
    if (authenticated) {
      await loadConversations();
      if (currentConversationId) {
        await loadConversationMessages(currentConversationId);
      } else {
        showWelcome();
      }
    }
  }

  function initLucide() {
    if (window.lucide) {
      window.lucide.createIcons();
    }
  }

  // --- Voice / Speech Recognition Engine ---
  function initSpeechRecognition() {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (SpeechRecognition) {
      try {
        recognition = new SpeechRecognition();
        recognition.continuous = true;
        recognition.interimResults = true;
        recognition.lang = 'en-US';

        let baseInputText = '';

        recognition.onstart = () => {
          setMicState('listening');
          baseInputText = chatInput.value ? (chatInput.value.trimEnd() + ' ') : '';
          resetSilenceTimer();
        };

        recognition.onresult = (event) => {
          resetSilenceTimer();
          let interimText = '';
          let finalText = '';

          for (let i = event.resultIndex; i < event.results.length; ++i) {
            const transcript = event.results[i][0].transcript;
            if (event.results[i].isFinal) {
              finalText += transcript;
            } else {
              interimText += transcript;
            }
          }

          if (finalText) {
            baseInputText += finalText + ' ';
          }
          chatInput.value = baseInputText + interimText;
          updateSendButtonState();
          autoResizeInput();
        };

        recognition.onerror = (event) => {
          clearTimeout(silenceTimer);
          setMicState('idle');
          if (event.error === 'not-allowed') {
            showToast('Microphone access denied. Please grant microphone permissions in browser settings.', 'error');
          } else if (event.error === 'no-speech') {
            // benign
          } else if (event.error === 'audio-capture') {
            showToast('No microphone found on your device.', 'error');
          } else if (event.error === 'network') {
            // Cloud speech recognition network error -> fall back to MediaRecorder
            startMediaRecorderFallback();
          }
        };

        recognition.onend = () => {
          clearTimeout(silenceTimer);
          setMicState('idle');
        };
      } catch (e) {
        recognition = null;
      }
    }
  }

  function resetSilenceTimer() {
    clearTimeout(silenceTimer);
    silenceTimer = setTimeout(() => {
      if (isRecording) {
        stopRecording();
      }
    }, 3500); // 3.5s auto-stop on silence
  }

  function setMicState(state) {
    micState = state;
    isRecording = (state === 'listening' || state === 'requesting');

    voiceInputBtn.classList.remove('recording-active', 'recording-requesting', 'recording-processing');
    if (micStatusDot) micStatusDot.classList.add('hidden');

    if (state === 'listening') {
      voiceInputBtn.classList.add('recording-active');
      if (micStatusDot) micStatusDot.classList.remove('hidden');
      voiceInputBtn.title = "Listening... Tap to stop";
    } else if (state === 'requesting') {
      voiceInputBtn.classList.add('recording-requesting');
      voiceInputBtn.title = "Requesting microphone permission...";
    } else if (state === 'processing') {
      voiceInputBtn.classList.add('recording-processing');
      voiceInputBtn.title = "Transcribing audio...";
    } else {
      voiceInputBtn.title = "Voice Input (Speech-to-Text)";
    }
  }

  function toggleRecording() {
    if (isRecording) {
      stopRecording();
    } else {
      startRecording();
    }
  }

  function startRecording() {
    if (recognition) {
      try {
        setMicState('requesting');
        recognition.start();
      } catch (err) {
        startMediaRecorderFallback();
      }
    } else {
      startMediaRecorderFallback();
    }
  }

  function stopRecording() {
    clearTimeout(silenceTimer);
    if (recognition) {
      try { recognition.stop(); } catch (e) {}
    }
    if (mediaRecorder && mediaRecorder.state !== 'inactive') {
      try { mediaRecorder.stop(); } catch (e) {}
    }
    setMicState('idle');
  }

  async function startMediaRecorderFallback() {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      showToast('Audio recording is not supported in this browser.', 'error');
      setMicState('idle');
      return;
    }

    try {
      setMicState('requesting');
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      audioChunks = [];
      const options = MediaRecorder.isTypeSupported('audio/webm') ? { mimeType: 'audio/webm' } : {};
      mediaRecorder = new MediaRecorder(stream, options);

      mediaRecorder.ondataavailable = (e) => {
        if (e.data && e.data.size > 0) audioChunks.push(e.data);
      };

      mediaRecorder.onstart = () => {
        setMicState('listening');
      };

      mediaRecorder.onstop = async () => {
        setMicState('processing');
        stream.getTracks().forEach(track => track.stop());

        const mimeType = mediaRecorder.mimeType || 'audio/webm';
        const audioBlob = new Blob(audioChunks, { type: mimeType });

        if (audioBlob.size > 1000) {
          try {
            const formData = new FormData();
            formData.append('file', audioBlob, 'recording.webm');
            const res = await authFetch('/api/chat/transcribe', {
              method: 'POST',
              body: formData
            });
            if (res.ok) {
              const data = await res.json();
              if (data.text) {
                const current = chatInput.value ? (chatInput.value.trimEnd() + ' ') : '';
                chatInput.value = current + data.text;
                updateSendButtonState();
                autoResizeInput();
                chatInput.focus();
              }
            } else {
              const err = await res.json().catch(() => ({}));
              showToast(err.detail || 'Voice transcription failed.', 'error');
            }
          } catch (e) {
            showToast('Transcription server connection failed.', 'error');
          }
        }
        setMicState('idle');
      };

      mediaRecorder.start();
    } catch (err) {
      setMicState('idle');
      if (err.name === 'NotAllowedError' || err.name === 'PermissionDeniedError') {
        showToast('Microphone permission denied. Please allow microphone access in site settings.', 'error');
      } else if (err.name === 'NotFoundError' || err.name === 'DevicesNotFoundError') {
        showToast('No microphone found on your system.', 'error');
      } else {
        showToast('Microphone error: ' + err.message, 'error');
      }
    }
  }

  // --- Attachments & Drag-and-Drop / Paste ---
  function setupDragAndDropAndPaste() {
    // Paste from clipboard (images, screenshots, files)
    window.addEventListener('paste', (e) => {
      const items = e.clipboardData && e.clipboardData.items;
      if (!items) return;

      const files = [];
      for (let i = 0; i < items.length; i++) {
        if (items[i].kind === 'file') {
          const file = items[i].getAsFile();
          if (file) files.push(file);
        }
      }
      if (files.length > 0) {
        handleFilesUpload(files);
      }
    });

    // Drag and drop overlay
    let dragCounter = 0;
    window.addEventListener('dragenter', (e) => {
      e.preventDefault();
      dragCounter++;
      if (dropZoneOverlay) dropZoneOverlay.classList.remove('hidden');
    });

    window.addEventListener('dragleave', (e) => {
      e.preventDefault();
      dragCounter--;
      if (dragCounter <= 0 && dropZoneOverlay) {
        dragCounter = 0;
        dropZoneOverlay.classList.add('hidden');
      }
    });

    window.addEventListener('dragover', (e) => {
      e.preventDefault();
    });

    window.addEventListener('drop', (e) => {
      e.preventDefault();
      dragCounter = 0;
      if (dropZoneOverlay) dropZoneOverlay.classList.add('hidden');
      if (e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files.length > 0) {
        handleFilesUpload(Array.from(e.dataTransfer.files));
      }
    });

    // Lightbox modal close
    if (closeImageModalBtn) {
      closeImageModalBtn.addEventListener('click', () => {
        if (imageModal) imageModal.classList.add('hidden');
      });
    }
    if (imageModal) {
      imageModal.addEventListener('click', (e) => {
        if (e.target === imageModal) imageModal.classList.add('hidden');
      });
    }
  }

  // Window global function for image modal zoom
  window.openImageModal = function(src) {
    if (enlargedImage && imageModal) {
      enlargedImage.src = src;
      imageModal.classList.remove('hidden');
    }
  };

  async function handleFilesUpload(fileList) {
    if (!fileList || fileList.length === 0) return;

    for (const file of fileList) {
      if (file.size > 25 * 1024 * 1024) {
        showToast(`File "${file.name}" exceeds the 25MB limit.`, 'error');
        continue;
      }

      const tempId = 'up_' + Date.now() + Math.random().toString(36).substring(2, 6);
      renderUploadProgressCard(tempId, file.name);

      try {
        const formData = new FormData();
        formData.append('file', file);
        const res = await authFetch('/api/chat/upload', {
          method: 'POST',
          body: formData
        });

        if (!res.ok) {
          const errData = await res.json().catch(() => ({ detail: 'Upload failed' }));
          throw new Error(errData.detail || `Upload failed with status ${res.status}`);
        }

        const data = await res.json();
        removeUploadProgressCard(tempId);
        attachedFiles.push(data);
        renderAttachmentsPreview();
        updateSendButtonState();
      } catch (err) {
        removeUploadProgressCard(tempId);
        showToast(`Error uploading "${file.name}": ${err.message}`, 'error');
      }
    }
  }

  function renderUploadProgressCard(tempId, filename) {
    if (!attachmentsContainer) return;
    attachmentsContainer.classList.remove('hidden');
    const card = document.createElement('div');
    card.id = `temp-upload-${tempId}`;
    card.className = "inline-flex items-center gap-2 bg-dark-800 border border-spider-500/20 px-3 py-1.5 rounded-xl text-xs text-slate-300 animate-pulse";
    card.innerHTML = `
      <span class="w-2.5 h-2.5 rounded-full bg-spider-400 animate-ping"></span>
      <span class="font-mono text-[11px] truncate max-w-[120px]">${escapeHtml(filename)}</span>
      <span class="text-[10px] text-slate-400">parsing...</span>
    `;
    attachmentsContainer.appendChild(card);
  }

  function removeUploadProgressCard(tempId) {
    const el = document.getElementById(`temp-upload-${tempId}`);
    if (el) el.remove();
  }

  function renderAttachmentsPreview() {
    if (!attachmentsContainer) return;

    if (attachedFiles.length === 0) {
      attachmentsContainer.innerHTML = '';
      attachmentsContainer.classList.add('hidden');
      return;
    }

    attachmentsContainer.classList.remove('hidden');
    attachmentsContainer.innerHTML = '';

    attachedFiles.forEach((file, index) => {
      const card = document.createElement('div');
      card.className = "relative group inline-flex items-center gap-2 bg-dark-800 border border-spider-500/30 rounded-xl p-1.5 pr-2.5 text-xs text-slate-200 shadow-sm transition-all";

      if (file.type === 'image' && (file.preview || file.data)) {
        const src = file.preview || `data:${file.mime_type};base64,${file.data}`;
        card.innerHTML = `
          <img src="${src}" alt="${escapeHtml(file.name)}" class="w-9 h-9 rounded-lg object-cover border border-spider-500/20 cursor-pointer" onclick="openImageModal('${src}')">
          <div class="flex flex-col text-left max-w-[120px]">
            <span class="font-medium text-[11px] text-white truncate">${escapeHtml(file.name)}</span>
            <span class="text-[10px] text-slate-400 font-mono">${formatBytes(file.size)}</span>
          </div>
          <button class="remove-att-btn text-slate-400 hover:text-rose-400 ml-1 p-0.5 rounded-md hover:bg-white/5" data-index="${index}" title="Remove image">
            <i data-lucide="x" class="w-3.5 h-3.5"></i>
          </button>
        `;
      } else {
        const icon = file.name.endsWith('.pdf') ? 'file-text' : (file.name.endsWith('.xlsx') || file.name.endsWith('.csv')) ? 'sheet' : 'file-code';
        const pageCountStr = file.page_count ? ` (${file.page_count}p)` : '';
        card.innerHTML = `
          <div class="p-1.5 rounded-lg bg-dark-850 border border-spider-500/20">
            <i data-lucide="${icon}" class="w-4 h-4 text-spider-400"></i>
          </div>
          <div class="flex flex-col text-left max-w-[140px]">
            <span class="font-medium text-[11px] text-white truncate">${escapeHtml(file.name)}</span>
            <span class="text-[10px] text-slate-400 font-mono">${formatBytes(file.size)}${pageCountStr}</span>
          </div>
          <button class="remove-att-btn text-slate-400 hover:text-rose-400 ml-1 p-0.5 rounded-md hover:bg-white/5" data-index="${index}" title="Remove document">
            <i data-lucide="x" class="w-3.5 h-3.5"></i>
          </button>
        `;
      }

      const removeBtn = card.querySelector('.remove-att-btn');
      removeBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        attachedFiles.splice(index, 1);
        renderAttachmentsPreview();
        updateSendButtonState();
      });

      attachmentsContainer.appendChild(card);
    });

    initLucide();
  }

  function clearAttachments() {
    attachedFiles = [];
    if (fileInput) fileInput.value = '';
    renderAttachmentsPreview();
    updateSendButtonState();
  }

  function setupFileHandling() {
    attachFileBtn.addEventListener('click', () => {
      fileInput.click();
    });

    fileInput.addEventListener('change', (e) => {
      if (e.target.files && e.target.files.length > 0) {
        handleFilesUpload(Array.from(e.target.files));
      }
    });
  }

  // --- Conversations Management ---
  async function loadConversations() {
    try {
      const res = await authFetch('/api/conversations');
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
    const query = (searchConvInput.value || '').trim().toLowerCase();
    const filtered = query 
      ? conversations.filter(c => (c.title || '').toLowerCase().includes(query))
      : conversations;

    if (filtered.length === 0) {
      conversationsList.innerHTML = `
        <div class="p-4 text-center text-xs text-slate-500">
          ${query ? 'No matching chats found.' : 'No conversations yet.'}
        </div>
      `;
      return;
    }

    filtered.forEach(conv => {
      const isActive = conv.id === currentConversationId;
      const item = document.createElement('div');
      item.className = `group flex items-center justify-between p-2.5 rounded-xl cursor-pointer text-xs transition-all ${
        isActive 
          ? 'bg-spider-500/15 text-spider-300 font-semibold border border-spider-500/25 shadow-sm' 
          : 'text-slate-300 hover:bg-dark-850 hover:text-white border border-transparent'
      }`;
      
      item.innerHTML = `
        <div class="flex items-center gap-2.5 truncate flex-1 mr-2">
          <i data-lucide="message-square" class="w-3.5 h-3.5 ${isActive ? 'text-spider-400' : 'text-slate-400'} shrink-0"></i>
          <span class="truncate">${escapeHtml(conv.title || 'Conversation')}</span>
        </div>
        <button class="delete-conv-btn opacity-0 group-hover:opacity-100 p-1 text-slate-400 hover:text-rose-400 rounded transition-opacity" title="Delete conversation">
          <i data-lucide="trash-2" class="w-3.5 h-3.5"></i>
        </button>
      `;

      item.addEventListener('click', () => {
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
      const res = await authFetch(`/api/conversations/${convId}`);
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
      await authFetch(`/api/conversations/${convId}`, { method: 'DELETE' });
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
    if (document.fonts && document.fonts.ready) {
      document.fonts.ready.then(() => scrollToBottom()).catch(() => {});
    }
  }

  function buildSourcesHtml(sources) {
    if (!sources || !sources.length) return '';
    const pills = sources.map(s => `
      <a href="${escapeHtml(s.url)}" target="_blank" rel="noopener noreferrer" class="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg bg-dark-800 hover:bg-dark-750 border border-cyan-500/20 text-cyan-400 text-[11px] hover:border-cyan-500/40 transition-colors">
        <i data-lucide="external-link" class="w-3 h-3"></i>
        <span class="max-w-[140px] truncate">${escapeHtml(s.title || 'Source')}</span>
      </a>
    `).join('');
    return `
      <div class="mt-2.5 pt-2 border-t border-white/5 min-w-0">
        <div class="text-[10px] font-semibold text-slate-400 mb-1.5 flex items-center gap-1">
          <i data-lucide="check-check" class="w-3 h-3 text-emerald-400"></i>
          Grounded Sources Verified:
        </div>
        <div class="chips-scroll-row flex flex-wrap gap-1.5">${pills}</div>
      </div>
    `;
  }

  function buildChipsHtml(chips) {
    if (!chips || !chips.length) return '';
    const chipsList = chips.map(chip => `
      <button class="follow-up-chip px-3 py-1.5 rounded-full bg-dark-850 hover:bg-dark-800 border border-spider-500/30 hover:border-spider-400/60 text-spider-400 hover:text-spider-300 text-xs font-medium transition-all text-left shadow-sm active:scale-95 flex items-center gap-1.5">
        <i data-lucide="arrow-right" class="w-3 h-3 text-spider-400"></i>
        <span>${escapeHtml(chip)}</span>
      </button>
    `).join('');
    return `
      <div class="mt-3 pt-2.5 border-t border-white/5 space-y-1.5 min-w-0">
        <div class="text-[11px] font-semibold text-slate-400">Suggested Follow-ups:</div>
        <div class="chips-scroll-row flex flex-wrap gap-2">${chipsList}</div>
      </div>
    `;
  }

  function buildActionsBarHtml(msgId) {
    return `
      <div class="chips-scroll-row mt-2.5 flex items-center gap-1 text-[11px] text-slate-400 border-t border-white/5 pt-2">
        <button class="per-reply-btn hover:text-spider-400 p-1.5 rounded-md hover:bg-white/5 flex items-center gap-1 transition-colors" data-action="regenerate" data-msg-id="${msgId}" title="Regenerate this response">
          <i data-lucide="refresh-cw" class="w-3.5 h-3.5"></i>
          <span class="hidden sm:inline">Regenerate</span>
        </button>
        <button class="per-reply-btn hover:text-spider-400 p-1.5 rounded-md hover:bg-white/5 flex items-center gap-1 transition-colors" data-action="shorter" data-msg-id="${msgId}" title="Make shorter">
          <i data-lucide="minimize-2" class="w-3.5 h-3.5"></i>
          <span class="hidden sm:inline">Make shorter</span>
        </button>
        <button class="per-reply-btn hover:text-spider-400 p-1.5 rounded-md hover:bg-white/5 flex items-center gap-1 transition-colors" data-action="detailed" data-msg-id="${msgId}" title="Make more detailed">
          <i data-lucide="maximize-2" class="w-3.5 h-3.5"></i>
          <span class="hidden sm:inline">Make more detailed</span>
        </button>
        <button class="copy-reply-btn ml-auto hover:text-white p-1.5 rounded-md hover:bg-white/5 flex items-center gap-1 transition-colors" title="Copy response">
          <i data-lucide="copy" class="w-3.5 h-3.5"></i>
          <span class="copy-label hidden sm:inline">Copy</span>
        </button>
      </div>
    `;
  }

  function appendMessageToUI(msg) {
    hideWelcome();
    const isUser = msg.role === 'user';
    const card = document.createElement('div');
    card.id = `msg-${msg.id}`;
    card.className = `flex flex-col ${isUser ? 'items-end' : 'items-start'} space-y-1.5 w-full min-w-0`;

    if (isUser) {
      // Clean attachment chips / cards inside user bubble (NEVER raw bytes!)
      let attachmentsHtml = '';
      if (msg.attachments && msg.attachments.length > 0) {
        const cards = msg.attachments.map(att => {
          if (att.type === 'image' && (att.preview || att.data)) {
            const src = att.preview || `data:${att.mime_type || 'image/png'};base64,${att.data}`;
            return `
              <div class="relative group cursor-pointer overflow-hidden rounded-xl border border-spider-500/25 bg-dark-900 shadow-sm" onclick="openImageModal('${src}')">
                <img src="${src}" alt="${escapeHtml(att.name)}" class="w-24 h-24 sm:w-28 sm:h-28 object-cover transition-transform group-hover:scale-105">
                <div class="absolute inset-0 bg-black/40 opacity-0 group-hover:opacity-100 flex items-center justify-center transition-opacity text-white text-[10px]">
                  <i data-lucide="zoom-in" class="w-4 h-4 mr-1"></i> View
                </div>
                <div class="absolute bottom-0 inset-x-0 bg-dark-950/80 px-1.5 py-0.5 text-[9px] text-slate-300 truncate">
                  ${escapeHtml(att.name)}
                </div>
              </div>
            `;
          } else {
            const icon = (att.name || '').endsWith('.pdf') ? 'file-text' : ((att.name || '').endsWith('.xlsx') || (att.name || '').endsWith('.csv')) ? 'sheet' : 'file-code';
            const sizeStr = formatBytes(att.size);
            return `
              <div class="inline-flex items-center gap-2 px-3 py-2 rounded-xl bg-dark-900/90 border border-spider-500/25 text-xs text-slate-200 shadow-sm max-w-full">
                <i data-lucide="${icon}" class="w-4 h-4 text-spider-400 shrink-0"></i>
                <div class="flex flex-col text-left max-w-[180px] sm:max-w-[220px] min-w-0">
                  <span class="font-medium truncate text-white text-xs">${escapeHtml(att.name || 'Document')}</span>
                  <span class="text-[10px] text-slate-400 font-mono">${sizeStr}</span>
                </div>
              </div>
            `;
          }
        }).join('');
        attachmentsHtml = `<div class="flex flex-wrap gap-2 mb-2">${cards}</div>`;
      }

      card.innerHTML = `
        <div class="max-w-[92%] md:max-w-xl min-w-0 rounded-2xl rounded-tr-sm bg-gradient-to-r from-emerald-600/20 to-spider-500/20 border border-spider-500/30 p-3.5 text-base md:text-sm text-slate-100 shadow-sm leading-relaxed">
          ${attachmentsHtml}
          ${msg.content ? `<div class="whitespace-pre-wrap msg-user-text">${escapeHtml(msg.content)}</div>` : ''}
        </div>
      `;
    } else {
      const formattedHtml = renderMarkdown(msg.content);
      const sourcesHtml = buildSourcesHtml(msg.sources);
      const chipsHtml = buildChipsHtml(msg.follow_up_chips);
      const actionsBarHtml = buildActionsBarHtml(msg.id);

      card.innerHTML = `
        <div class="max-w-[92%] md:max-w-2xl min-w-0 rounded-2xl rounded-tl-sm bg-dark-900 border border-spider-500/15 p-3.5 md:p-4 shadow-md w-full">
          <div class="flex items-center gap-2 mb-2.5 pb-2 border-b border-spider-500/10">
            <img src="/static/images/spider-avatar.png" alt="Spider Avatar" class="w-5 h-5 rounded-full spider-avatar object-cover">
            <span class="text-xs font-semibold text-spider-400">GoldSea AI</span>
          </div>
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
      const clean = DOMPurify.sanitize(parsed);
      const tmp = document.createElement('div');
      tmp.innerHTML = clean;
      tmp.querySelectorAll('table').forEach(tbl => {
        if (tbl.parentElement && tbl.parentElement.classList.contains('table-scroll-wrap')) return;
        const wrap = document.createElement('div');
        wrap.className = 'table-scroll-wrap';
        tbl.parentNode.insertBefore(wrap, tbl);
        wrap.appendChild(tbl);
      });
      return tmp.innerHTML;
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
    if (!rawText && attachedFiles.length === 0) return;
    if (isStreaming) return;

    // Snapshot current attachments
    const currentAttachments = [...attachedFiles];
    clearAttachments();

    // Reset input
    chatInput.value = '';
    updateSendButtonState();
    autoResizeInput();

    // Create temporary UI card for user
    const tempUserMsg = {
      id: 'tmp_' + Date.now(),
      role: 'user',
      content: rawText,
      attachments: currentAttachments
    };
    appendMessageToUI(tempUserMsg);
    scrollToBottom();

    // Setup Assistant Streaming Card
    isStreaming = true;
    currentAbortController = new AbortController();

    const assistantMsgId = 'msg_' + Date.now();
    const assistantCard = document.createElement('div');
    assistantCard.id = `msg-${assistantMsgId}`;
    assistantCard.className = 'flex flex-col items-start space-y-1.5 w-full min-w-0';
    assistantCard.innerHTML = `
      <div class="max-w-[92%] md:max-w-2xl min-w-0 rounded-2xl rounded-tl-sm bg-dark-900 border border-spider-500/15 p-3.5 md:p-4 shadow-md w-full">
        <div class="flex items-center gap-2 mb-2.5 pb-2 border-b border-spider-500/10">
          <img src="/static/images/spider-avatar.png" alt="Spider Avatar" class="w-5 h-5 rounded-full spider-avatar object-cover animate-pulse">
          <span class="text-xs font-semibold text-spider-400">GoldSea AI</span>
        </div>
        <div class="prose max-w-none text-slate-200" id="stream-content-${assistantMsgId}">
          <div class="flex items-center gap-2 text-slate-400 text-xs py-1">
            <span class="w-2 h-2 rounded-full bg-spider-400 animate-ping"></span>
            <span>Analyzing and verifying...</span>
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
      const response = await authFetch('/api/chat/stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: rawText,
          conversation_id: currentConversationId,
          enable_search: true,
          attachments: currentAttachments
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
        buffer = lines.pop(); // keep last uncompleted line

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            const rawData = line.replace('data: ', '').trim();
            if (!rawData) continue;

            try {
              const parsed = JSON.parse(rawData);

              if (parsed.type === 'sources') {
                accumulatedSources = parsed.sources || [];
                renderSourcesInStream(assistantMsgId, accumulatedSources);
              } else if (parsed.type === 'token') {
                fullAccumulatedText += parsed.token;
                if (contentEl) {
                  contentEl.innerHTML = renderMarkdown(fullAccumulatedText);
                  highlightCodeBlocks(contentEl);
                }
                scrollToBottom();
              } else if (parsed.type === 'follow_up_chips') {
                accumulatedChips = parsed.chips || [];
              } else if (parsed.type === 'error') {
                renderErrorState(assistantCard, parsed.message, rawText);
                return;
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
        renderErrorState(assistantCard, 'Service connection failed or timed out.', rawText);
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
    container.innerHTML = buildSourcesHtml(sources);
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
      chipsContainer.innerHTML = buildChipsHtml(chips);

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
      actionsContainer.className = '';
      actionsContainer.innerHTML = buildActionsBarHtml(msgId);

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
      <div class="max-w-[92%] md:max-w-xl min-w-0 rounded-2xl bg-rose-950/30 border border-rose-500/30 p-4 space-y-3">
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

    const placeholderCard = document.createElement('div');
    placeholderCard.className = 'flex flex-col items-start space-y-1.5 w-full min-w-0';
    placeholderCard.innerHTML = `
      <div class="max-w-[92%] md:max-w-2xl min-w-0 rounded-2xl bg-dark-900 border border-white/5 p-4 text-xs text-slate-400 flex items-center gap-2">
        <span class="w-2 h-2 rounded-full bg-spider-400 animate-ping"></span>
        <span>${actionText}</span>
      </div>
    `;
    messagesList.appendChild(placeholderCard);
    scrollToBottom();

    try {
      const res = await authFetch('/api/chat/per-reply-action', {
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

  // --- Quick Actions Grid & Modal ---
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
        if (quickActionsModal) quickActionsModal.classList.add('hidden');
        if (!currentConversationId && messagesList.children.length === 0) {
          hideWelcome();
        }
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

    // Voice Input Click
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

    // Quick Actions Modal
    if (openQuickActionsBtn && quickActionsModal) {
      openQuickActionsBtn.addEventListener('click', () => quickActionsModal.classList.remove('hidden'));
    }
    if (closeQuickActionsBtn && quickActionsModal) {
      closeQuickActionsBtn.addEventListener('click', () => quickActionsModal.classList.add('hidden'));
    }
    if (quickActionsModal) {
      quickActionsModal.addEventListener('click', (e) => {
        if (e.target === quickActionsModal) quickActionsModal.classList.add('hidden');
      });
    }

    // Shortcuts Modal
    shortcutsModalBtn.addEventListener('click', () => shortcutsModal.classList.remove('hidden'));
    closeShortcutsBtn.addEventListener('click', () => shortcutsModal.classList.add('hidden'));

    // Export Modal
    if (exportChatBtn) {
      exportChatBtn.addEventListener('click', () => {
        if (!currentConversationId) {
          showToast('Please select or start a conversation first.', 'info');
          return;
        }
        exportModal.classList.remove('hidden');
      });
    }
    if (closeExportBtn) {
      closeExportBtn.addEventListener('click', () => exportModal.classList.add('hidden'));
    }

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
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'n') {
        e.preventDefault();
        startNewChat();
      } else if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        chatInput.focus();
      } else if ((e.ctrlKey || e.metaKey) && e.key === '/') {
        e.preventDefault();
        shortcutsModal.classList.toggle('hidden');
      } else if (e.key === 'Escape') {
        shortcutsModal.classList.add('hidden');
        if (quickActionsModal) quickActionsModal.classList.add('hidden');
        exportModal.classList.add('hidden');
        if (imageModal) imageModal.classList.add('hidden');
        const accModal = document.getElementById('account-settings-modal');
        if (accModal) accModal.classList.add('hidden');
        closeMobileSidebar();
      }
    });

    setupFileHandling();
    setupQuickActions();
  }

  // --- Authentication & User Account Module ---
  async function checkAuthState() {
    try {
      const res = await fetch('/api/auth/me', { credentials: 'include' });
      if (res.ok) {
        const data = await res.json();
        currentUser = data.user;
        updateUserUI(currentUser);
        hideAuthScreen();
        return true;
      } else if (res.status === 403) {
        const data = await res.json().catch(() => ({}));
        if (data.user) {
          pendingEmail = data.user.email;
          const displayEl = document.getElementById('verify-email-display');
          if (displayEl) displayEl.textContent = pendingEmail;
        }
        showAuthScreen('verify');
        return false;
      } else {
        currentUser = null;
        showAuthScreen('login');
        return false;
      }
    } catch (e) {
      currentUser = null;
      showAuthScreen('login');
      return false;
    }
  }

  function updateUserUI(user) {
    if (!user) return;
    const isGuest = user.name === 'Guest' || (user.email && user.email.includes('@guest.goldsea.local'));
    const initial = isGuest ? 'G' : (user.name || 'U').trim().charAt(0).toUpperCase();
    const avatar = document.getElementById('user-avatar-initial');
    const nameEl = document.getElementById('user-display-name');
    const statusEl = document.getElementById('user-display-status');
    const welcomeName = document.getElementById('welcome-user-name');
    const settingsName = document.getElementById('settings-user-name');
    const settingsEmail = document.getElementById('settings-user-email');

    if (avatar) avatar.textContent = initial;
    if (nameEl) nameEl.textContent = isGuest ? 'Guest User' : user.name;
    if (statusEl) statusEl.textContent = isGuest ? 'Sign up to sync' : 'Memory Active';
    if (welcomeName) welcomeName.textContent = isGuest ? 'Guest' : user.name;
    if (settingsName) settingsName.textContent = user.name;
    if (settingsEmail) settingsEmail.textContent = isGuest ? 'Guest Session' : user.email;

    const guestSignInBtn = document.getElementById('guest-sign-in-btn');
    if (guestSignInBtn) {
      if (isGuest) {
        guestSignInBtn.classList.remove('hidden');
      } else {
        guestSignInBtn.classList.add('hidden');
      }
    }
  }

  function showAuthScreen(screen) {
    const authView = document.getElementById('auth-view');
    if (!authView) return;
    authView.classList.remove('hidden');

    const views = {
      login: document.getElementById('auth-login-view'),
      signup: document.getElementById('auth-signup-view'),
      verify: document.getElementById('auth-verify-view'),
      forgot: document.getElementById('auth-forgot-view'),
      reset: document.getElementById('auth-reset-view')
    };

    const subtitles = {
      login: 'Sign in to access your private conversations and cloud memory.',
      signup: 'Create your secure account with encrypted private cloud storage.',
      verify: 'Enter your 6-digit email verification code to proceed.',
      forgot: 'Enter your account email to receive a password reset code.',
      reset: 'Enter the 6-digit reset code and set your new password.'
    };

    Object.keys(views).forEach(k => {
      if (views[k]) views[k].classList.add('hidden');
    });

    if (views[screen]) {
      views[screen].classList.remove('hidden');
    }

    const subtitleEl = document.getElementById('auth-screen-subtitle');
    if (subtitleEl && subtitles[screen]) {
      subtitleEl.textContent = subtitles[screen];
    }

    // Reset error banners
    ['login-error', 'signup-error', 'verify-error', 'forgot-error', 'reset-error'].forEach(id => {
      const el = document.getElementById(id);
      if (el) {
        el.textContent = '';
        el.classList.add('hidden');
      }
    });

    if (screen === 'verify') {
      const d0 = document.getElementById('digit-0');
      if (d0) setTimeout(() => d0.focus(), 100);
      startResendCountdown(60);
    } else if (screen === 'reset') {
      const r0 = document.getElementById('reset-digit-0');
      if (r0) setTimeout(() => r0.focus(), 100);
    }

    initLucide();
  }

  function hideAuthScreen() {
    const authView = document.getElementById('auth-view');
    if (authView) authView.classList.add('hidden');
    if (resendTimerInterval) clearInterval(resendTimerInterval);
  }

  function setupDigitInputs(containerId, submitCallback) {
    const container = document.getElementById(containerId);
    if (!container) return;
    const inputs = Array.from(container.querySelectorAll('.digit-box'));

    inputs.forEach((input, idx) => {
      input.addEventListener('input', (e) => {
        const val = e.target.value.replace(/[^0-9]/g, '');
        e.target.value = val ? val[0] : '';
        if (val) {
          e.target.classList.add('filled');
          if (idx < inputs.length - 1) {
            inputs[idx + 1].focus();
          } else {
            const fullCode = inputs.map(i => i.value).join('');
            if (fullCode.length === 6 && submitCallback) {
              submitCallback(fullCode);
            }
          }
        } else {
          e.target.classList.remove('filled');
        }
      });

      input.addEventListener('keydown', (e) => {
        if (e.key === 'Backspace' && !e.target.value && idx > 0) {
          inputs[idx - 1].focus();
        }
      });

      input.addEventListener('paste', (e) => {
        e.preventDefault();
        const pasted = (e.clipboardData || window.clipboardData).getData('text') || '';
        const digits = pasted.replace(/[^0-9]/g, '').slice(0, 6);
        if (digits) {
          digits.split('').forEach((d, i) => {
            if (inputs[i]) {
              inputs[i].value = d;
              inputs[i].classList.add('filled');
            }
          });
          const nextIndex = Math.min(digits.length, inputs.length - 1);
          inputs[nextIndex].focus();
          if (digits.length === 6 && submitCallback) {
            submitCallback(digits);
          }
        }
      });
    });
  }

  function calculatePasswordStrength(pwd) {
    if (!pwd || pwd.length < 8) return 0;
    let score = 1;
    if (pwd.length >= 12) score++;
    if (/[A-Z]/.test(pwd) && /[a-z]/.test(pwd)) score++;
    if (/[0-9]/.test(pwd)) score++;
    if (/[^A-Za-z0-9]/.test(pwd)) score++;
    return Math.min(score, 4);
  }

  function updatePasswordStrengthMeter(pwd, barIds, labelId) {
    const score = calculatePasswordStrength(pwd);
    const bars = barIds.map(id => document.getElementById(id));
    const label = document.getElementById(labelId);
    
    const colors = ['bg-rose-500', 'bg-amber-500', 'bg-yellow-400', 'bg-spider-400'];
    const names = ['Too short (min 8 chars)', 'Weak', 'Fair', 'Strong', 'Very strong'];

    bars.forEach((b, i) => {
      if (!b) return;
      b.className = 'strength-bar flex-1';
      if (score > i) {
        b.classList.add(colors[score - 1]);
      } else {
        b.classList.add('bg-white/10');
      }
    });

    if (label) {
      label.textContent = pwd.length < 8 ? 'Password strength: min 8 characters required' : `Password strength: ${names[score]}`;
      label.className = `text-[10px] ${score >= 3 ? 'text-spider-400' : (score === 2 ? 'text-yellow-400' : 'text-slate-400')}`;
    }
  }

  function setupPasswordToggles() {
    document.querySelectorAll('.toggle-password-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        const targetId = btn.getAttribute('data-target');
        const input = document.getElementById(targetId);
        if (!input) return;
        const isPass = input.type === 'password';
        input.type = isPass ? 'text' : 'password';
        btn.innerHTML = `<i data-lucide="${isPass ? 'eye-off' : 'eye'}" class="w-4 h-4"></i>`;
        initLucide();
      });
    });
  }

  function startResendCountdown(seconds) {
    const resendBtn = document.getElementById('verify-resend-btn');
    const countdownEl = document.getElementById('resend-countdown');
    if (!resendBtn || !countdownEl) return;

    if (resendTimerInterval) clearInterval(resendTimerInterval);
    let remaining = seconds;
    resendBtn.disabled = true;
    countdownEl.textContent = remaining;

    resendTimerInterval = setInterval(() => {
      remaining--;
      if (remaining <= 0) {
        clearInterval(resendTimerInterval);
        resendBtn.disabled = false;
        resendBtn.innerHTML = 'Resend Code';
      } else {
        countdownEl.textContent = remaining;
      }
    }, 1000);
  }

  function setupAuthHandlers() {
    setupPasswordToggles();

    // Digits auto-advance & paste
    setupDigitInputs('verify-digits-container', (code) => {
      handleVerifySubmit(code);
    });
    setupDigitInputs('reset-digits-container', null);

    // Screen switches
    const switchToSignup = document.getElementById('switch-to-signup-btn');
    if (switchToSignup) switchToSignup.addEventListener('click', () => showAuthScreen('signup'));

    const switchToLogin = document.getElementById('switch-to-login-btn');
    if (switchToLogin) switchToLogin.addEventListener('click', () => showAuthScreen('login'));

    const forgotLink = document.getElementById('login-forgot-link');
    if (forgotLink) forgotLink.addEventListener('click', () => showAuthScreen('forgot'));

    const forgotBack = document.getElementById('forgot-back-to-login-btn');
    if (forgotBack) forgotBack.addEventListener('click', () => showAuthScreen('login'));

    const resetBack = document.getElementById('reset-back-to-login-btn');
    if (resetBack) resetBack.addEventListener('click', () => showAuthScreen('login'));

    const diffEmail = document.getElementById('verify-diff-email-btn');
    if (diffEmail) {
      diffEmail.addEventListener('click', async () => {
        await fetch('/api/auth/logout', { method: 'POST', credentials: 'include' });
        currentUser = null;
        showAuthScreen('login');
      });
    }

    // Guest Mode: Continue without login
    async function handleGuestLogin() {
      try {
        const guestBtn = document.getElementById('guest-continue-btn');
        if (guestBtn) {
          guestBtn.disabled = true;
          guestBtn.innerHTML = '<span class="text-xs">Entering as Guest...</span>';
        }
        const res = await fetch('/api/auth/guest-login', {
          method: 'POST',
          credentials: 'include'
        });
        if (res.ok) {
          const data = await res.json();
          currentUser = data.user;
          updateUserUI(currentUser);
          hideAuthScreen();
          await fetchConversations();
          if (window.lucide) lucide.createIcons();
        } else {
          alert('Could not start guest session. Please try again or create an account.');
          if (guestBtn) guestBtn.disabled = false;
        }
      } catch (err) {
        console.error('Guest login error:', err);
        hideAuthScreen();
      }
    }

    const guestBtn = document.getElementById('guest-continue-btn');
    if (guestBtn) guestBtn.addEventListener('click', handleGuestLogin);

    const guestBtnSignup = document.getElementById('guest-continue-btn-signup');
    if (guestBtnSignup) guestBtnSignup.addEventListener('click', handleGuestLogin);

    // Password strength listener on signup
    const signupPass = document.getElementById('signup-password');
    if (signupPass) {
      signupPass.addEventListener('input', (e) => {
        updatePasswordStrengthMeter(
          e.target.value,
          ['pw-bar-1', 'pw-bar-2', 'pw-bar-3', 'pw-bar-4'],
          'pw-strength-label'
        );
      });
    }

    // Login Form Submit
    const loginForm = document.getElementById('login-form');
    if (loginForm) {
      loginForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const email = document.getElementById('login-email').value.trim();
        const password = document.getElementById('login-password').value;
        const errEl = document.getElementById('login-error');
        const submitBtn = document.getElementById('login-submit-btn');
        errEl.classList.add('hidden');
        submitBtn.disabled = true;
        submitBtn.innerHTML = '<span>Signing In...</span>';

        try {
          const res = await fetch('/api/auth/login', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include',
            body: JSON.stringify({ email, password })
          });
          const data = await res.json();
          if (res.ok) {
            await fetchCsrfToken();
            currentUser = data.user;
            updateUserUI(currentUser);
            hideAuthScreen();
            await loadConversations();
            if (currentConversationId) {
              await loadConversationMessages(currentConversationId);
            } else {
              showWelcome();
            }
          } else if (res.status === 403) {
            pendingEmail = email;
            const disp = document.getElementById('verify-email-display');
            if (disp) disp.textContent = pendingEmail;
            showAuthScreen('verify');
          } else {
            errEl.textContent = data.detail || 'Invalid email or password.';
            errEl.classList.remove('hidden');
          }
        } catch (err) {
          errEl.textContent = 'Connection error. Please try again.';
          errEl.classList.remove('hidden');
        } finally {
          submitBtn.disabled = false;
          submitBtn.innerHTML = '<span>Sign In</span>';
        }
      });
    }

    // Signup Form Submit
    const signupForm = document.getElementById('signup-form');
    if (signupForm) {
      signupForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const name = document.getElementById('signup-name').value.trim();
        const email = document.getElementById('signup-email').value.trim();
        const password = document.getElementById('signup-password').value;
        const confirmPassword = document.getElementById('signup-confirm-password').value;
        const errEl = document.getElementById('signup-error');
        const submitBtn = document.getElementById('signup-submit-btn');

        errEl.classList.add('hidden');
        if (password !== confirmPassword) {
          errEl.textContent = 'Passwords do not match.';
          errEl.classList.remove('hidden');
          return;
        }

        submitBtn.disabled = true;
        submitBtn.innerHTML = '<span>Creating Account...</span>';

        try {
          const res = await fetch('/api/auth/signup', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include',
            body: JSON.stringify({ name, email, password, confirm_password: confirmPassword })
          });
          const data = await res.json();
          if (res.ok) {
            await fetchCsrfToken();
            pendingEmail = email;
            const disp = document.getElementById('verify-email-display');
            if (disp) disp.textContent = pendingEmail;
            showAuthScreen('verify');
            showToast('Account created! Please enter your 6-digit verification code.', 'info');
          } else {
            errEl.textContent = data.detail || 'Sign up failed.';
            errEl.classList.remove('hidden');
          }
        } catch (err) {
          errEl.textContent = 'Connection error. Please try again.';
          errEl.classList.remove('hidden');
        } finally {
          submitBtn.disabled = false;
          submitBtn.innerHTML = '<span>Create Account</span>';
        }
      });
    }

    // Verification Submit
    async function handleVerifySubmit(codeOverride) {
      let code = codeOverride;
      if (!code) {
        const inputs = Array.from(document.querySelectorAll('#verify-digits-container .digit-box'));
        code = inputs.map(i => i.value.trim()).join('');
      }

      const errEl = document.getElementById('verify-error');
      const submitBtn = document.getElementById('verify-submit-btn');
      errEl.classList.add('hidden');

      if (!code || code.length !== 6) {
        errEl.textContent = 'Please enter all 6 digits.';
        errEl.classList.remove('hidden');
        return;
      }

      submitBtn.disabled = true;
      submitBtn.innerHTML = '<span>Verifying...</span>';

      try {
        const res = await authFetch('/api/auth/verify-email', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ email: pendingEmail, code })
        });
        const data = await res.json();
        if (res.ok) {
          await fetchCsrfToken();
          currentUser = data.user;
          updateUserUI(currentUser);
          hideAuthScreen();
          showToast('Email verified successfully! Welcome to GoldSea AI.', 'info');
          await loadConversations();
          if (currentConversationId) {
            await loadConversationMessages(currentConversationId);
          } else {
            showWelcome();
          }
        } else {
          errEl.textContent = data.detail || 'Verification failed. Please check the code.';
          errEl.classList.remove('hidden');
        }
      } catch (err) {
        errEl.textContent = 'Connection error. Please try again.';
        errEl.classList.remove('hidden');
      } finally {
        submitBtn.disabled = false;
        submitBtn.innerHTML = '<span>Verify & Enter GoldSea AI</span>';
      }
    }

    const verifySubmitBtn = document.getElementById('verify-submit-btn');
    if (verifySubmitBtn) {
      verifySubmitBtn.addEventListener('click', () => handleVerifySubmit());
    }

    // Resend Code
    const resendBtn = document.getElementById('verify-resend-btn');
    if (resendBtn) {
      resendBtn.addEventListener('click', async () => {
        if (resendBtn.disabled) return;
        resendBtn.disabled = true;
        try {
          const res = await authFetch('/api/auth/resend-code', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email: pendingEmail, purpose: 'verification' })
          });
          const data = await res.json();
          if (res.ok) {
            showToast('New verification code sent! Check your email.', 'info');
            startResendCountdown(60);
          } else {
            showToast(data.detail || 'Could not resend code.', 'error');
            resendBtn.disabled = false;
          }
        } catch (e) {
          showToast('Network error while resending code.', 'error');
          resendBtn.disabled = false;
        }
      });
    }

    // Forgot Password Form Submit
    const forgotForm = document.getElementById('forgot-form');
    if (forgotForm) {
      forgotForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const email = document.getElementById('forgot-email').value.trim();
        const errEl = document.getElementById('forgot-error');
        const submitBtn = document.getElementById('forgot-submit-btn');

        errEl.classList.add('hidden');
        submitBtn.disabled = true;
        submitBtn.innerHTML = '<span>Sending Code...</span>';

        try {
          const res = await authFetch('/api/auth/forgot-password', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email })
          });
          const data = await res.json();
          if (res.ok) {
            pendingEmail = email;
            const disp = document.getElementById('reset-email-display');
            if (disp) disp.textContent = pendingEmail;
            showAuthScreen('reset');
            showToast('Reset code sent! Check your email.', 'info');
          } else {
            errEl.textContent = data.detail || 'Failed to send reset code.';
            errEl.classList.remove('hidden');
          }
        } catch (err) {
          errEl.textContent = 'Connection error. Please try again.';
          errEl.classList.remove('hidden');
        } finally {
          submitBtn.disabled = false;
          submitBtn.innerHTML = '<span>Send Reset Code</span>';
        }
      });
    }

    // Reset Password Form Submit
    const resetForm = document.getElementById('reset-form');
    if (resetForm) {
      resetForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const inputs = Array.from(document.querySelectorAll('#reset-digits-container .digit-box'));
        const code = inputs.map(i => i.value.trim()).join('');
        const newPassword = document.getElementById('reset-new-password').value;
        const confirmPassword = document.getElementById('reset-confirm-password').value;
        const errEl = document.getElementById('reset-error');
        const submitBtn = document.getElementById('reset-submit-btn');

        errEl.classList.add('hidden');
        if (code.length !== 6) {
          errEl.textContent = 'Please enter all 6 digits of your reset code.';
          errEl.classList.remove('hidden');
          return;
        }
        if (newPassword !== confirmPassword) {
          errEl.textContent = 'Passwords do not match.';
          errEl.classList.remove('hidden');
          return;
        }

        submitBtn.disabled = true;
        submitBtn.innerHTML = '<span>Resetting Password...</span>';

        try {
          const res = await authFetch('/api/auth/reset-password', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              email: pendingEmail,
              code,
              new_password: newPassword,
              confirm_password: confirmPassword
            })
          });
          const data = await res.json();
          if (res.ok) {
            await fetchCsrfToken();
            currentUser = data.user;
            updateUserUI(currentUser);
            hideAuthScreen();
            showToast('Password reset successfully! Logged in.', 'info');
            await loadConversations();
            if (currentConversationId) {
              await loadConversationMessages(currentConversationId);
            } else {
              showWelcome();
            }
          } else {
            errEl.textContent = data.detail || 'Password reset failed.';
            errEl.classList.remove('hidden');
          }
        } catch (err) {
          errEl.textContent = 'Connection error. Please try again.';
          errEl.classList.remove('hidden');
        } finally {
          submitBtn.disabled = false;
          submitBtn.innerHTML = '<span>Reset Password & Sign In</span>';
        }
      });
    }
  }

  // --- Account & Memories Settings Module ---
  function setupAccountSettingsHandlers() {
    const userProfileBtn = document.getElementById('user-profile-btn');
    const userMenuDropdown = document.getElementById('user-menu-dropdown');
    const openSettingsBtn = document.getElementById('open-account-settings-btn');
    const settingsModal = document.getElementById('account-settings-modal');
    const closeSettingsBtn = document.getElementById('close-account-settings-btn');
    const logoutBtn = document.getElementById('logout-btn');
    const exportMenuBtn = document.getElementById('export-chat-menu-btn');
    const guestSignInBtn = document.getElementById('guest-sign-in-btn');
    if (guestSignInBtn) {
      guestSignInBtn.addEventListener('click', () => {
        if (userMenuDropdown) userMenuDropdown.classList.add('hidden');
        showAuthScreen('signup');
      });
    }

    // Toggle dropdown menu
    if (userProfileBtn && userMenuDropdown) {
      userProfileBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        userMenuDropdown.classList.toggle('hidden');
      });
      document.addEventListener('click', (e) => {
        if (!userMenuDropdown.contains(e.target) && !userProfileBtn.contains(e.target)) {
          userMenuDropdown.classList.add('hidden');
        }
      });
    }

    // Export Chat from Menu
    if (exportMenuBtn) {
      exportMenuBtn.addEventListener('click', () => {
        if (userMenuDropdown) userMenuDropdown.classList.add('hidden');
        if (!currentConversationId) {
          showToast('Please select or start a conversation first.', 'info');
          return;
        }
        exportModal.classList.remove('hidden');
      });
    }

    // Open / Close Settings Modal
    if (openSettingsBtn && settingsModal) {
      openSettingsBtn.addEventListener('click', () => {
        if (userMenuDropdown) userMenuDropdown.classList.add('hidden');
        settingsModal.classList.remove('hidden');
        initLucide();
      });
    }
    if (closeSettingsBtn && settingsModal) {
      closeSettingsBtn.addEventListener('click', () => {
        settingsModal.classList.add('hidden');
      });
    }
    if (settingsModal) {
      settingsModal.addEventListener('click', (e) => {
        if (e.target === settingsModal) settingsModal.classList.add('hidden');
      });
    }

    // Settings Tabs
    const tabProfileBtn = document.getElementById('settings-tab-profile-btn');
    const tabMemoriesBtn = document.getElementById('settings-tab-memories-btn');
    const panelProfile = document.getElementById('settings-panel-profile');
    const panelMemories = document.getElementById('settings-panel-memories');

    if (tabProfileBtn && tabMemoriesBtn) {
      tabProfileBtn.addEventListener('click', () => {
        tabProfileBtn.className = 'flex-1 py-3 px-4 text-xs font-semibold text-spider-400 border-b-2 border-spider-400 flex items-center justify-center gap-2 transition-all';
        tabMemoriesBtn.className = 'flex-1 py-3 px-4 text-xs font-semibold text-slate-400 hover:text-slate-200 border-b-2 border-transparent flex items-center justify-center gap-2 transition-all';
        panelProfile.classList.remove('hidden');
        panelMemories.classList.add('hidden');
      });

      tabMemoriesBtn.addEventListener('click', () => {
        tabMemoriesBtn.className = 'flex-1 py-3 px-4 text-xs font-semibold text-spider-400 border-b-2 border-spider-400 flex items-center justify-center gap-2 transition-all';
        tabProfileBtn.className = 'flex-1 py-3 px-4 text-xs font-semibold text-slate-400 hover:text-slate-200 border-b-2 border-transparent flex items-center justify-center gap-2 transition-all';
        panelMemories.classList.remove('hidden');
        panelProfile.classList.add('hidden');
        loadMemories();
      });
    }

    // Change Password Form
    const changePassForm = document.getElementById('change-password-form');
    if (changePassForm) {
      changePassForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const currentPassword = document.getElementById('change-curr-pass').value;
        const newPassword = document.getElementById('change-new-pass').value;
        const confirmPassword = document.getElementById('change-confirm-pass').value;
        const msgEl = document.getElementById('change-password-msg');
        const submitBtn = document.getElementById('change-password-submit-btn');

        msgEl.className = 'hidden text-xs p-2.5 rounded-lg';
        if (newPassword !== confirmPassword) {
          msgEl.textContent = 'New passwords do not match.';
          msgEl.className = 'text-xs p-2.5 rounded-lg bg-red-950/40 border border-red-500/30 text-red-300';
          return;
        }

        submitBtn.disabled = true;
        submitBtn.textContent = 'Updating...';

        try {
          const res = await authFetch('/api/account/change-password', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              current_password: currentPassword,
              new_password: newPassword,
              confirm_password: confirmPassword
            })
          });
          const data = await res.json();
          if (res.ok) {
            msgEl.textContent = 'Password updated successfully!';
            msgEl.className = 'text-xs p-2.5 rounded-lg bg-spider-950/40 border border-spider-500/30 text-spider-300';
            changePassForm.reset();
          } else {
            msgEl.textContent = data.detail || 'Could not update password.';
            msgEl.className = 'text-xs p-2.5 rounded-lg bg-red-950/40 border border-red-500/30 text-red-300';
          }
        } catch (err) {
          msgEl.textContent = 'Connection error.';
          msgEl.className = 'text-xs p-2.5 rounded-lg bg-red-950/40 border border-red-500/30 text-red-300';
        } finally {
          submitBtn.disabled = false;
          submitBtn.textContent = 'Update Password';
        }
      });
    }

    // Log Out All Devices
    const logoutAllBtn = document.getElementById('logout-all-btn');
    if (logoutAllBtn) {
      logoutAllBtn.addEventListener('click', async () => {
        if (!confirm('Log out of all devices and active sessions?')) return;
        try {
          await authFetch('/api/auth/logout-all', { method: 'POST' });
          currentUser = null;
          if (settingsModal) settingsModal.classList.add('hidden');
          showAuthScreen('login');
          showToast('Logged out of all devices.', 'info');
        } catch (e) {
          showToast('Failed to log out of all devices.', 'error');
        }
      });
    }

    // Danger Zone Delete Account
    const showDeleteBtn = document.getElementById('show-delete-account-btn');
    const deleteToggleWrap = document.getElementById('delete-account-toggle-wrap');
    const deleteForm = document.getElementById('delete-account-form');
    const cancelDeleteBtn = document.getElementById('cancel-delete-account-btn');

    if (showDeleteBtn && deleteForm) {
      showDeleteBtn.addEventListener('click', () => {
        deleteToggleWrap.classList.add('hidden');
        deleteForm.classList.remove('hidden');
      });
      cancelDeleteBtn.addEventListener('click', () => {
        deleteForm.classList.add('hidden');
        deleteToggleWrap.classList.remove('hidden');
      });
      deleteForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const pwd = document.getElementById('delete-account-password').value;
        const errEl = document.getElementById('delete-account-error');
        errEl.classList.add('hidden');

        try {
          const res = await authFetch('/api/account/delete-account', {
            method: 'DELETE',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ password: pwd })
          });
          const data = await res.json();
          if (res.ok) {
            currentUser = null;
            conversations = [];
            currentConversationId = null;
            renderConversationsList();
            if (settingsModal) settingsModal.classList.add('hidden');
            showAuthScreen('signup');
            showToast('Account and all associated data permanently deleted.', 'info');
          } else {
            errEl.textContent = data.detail || 'Failed to delete account. Incorrect password.';
            errEl.classList.remove('hidden');
          }
        } catch (err) {
          errEl.textContent = 'Connection error. Please try again.';
          errEl.classList.remove('hidden');
        }
      });
    }

    // Memories CRUD
    const addMemoryForm = document.getElementById('add-memory-form');
    if (addMemoryForm) {
      addMemoryForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const key = document.getElementById('new-memory-key').value.trim();
        const value = document.getElementById('new-memory-val').value.trim();
        const errEl = document.getElementById('add-memory-error');
        errEl.classList.add('hidden');

        try {
          const res = await authFetch('/api/memories', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ key, value, category: 'preference' })
          });
          const data = await res.json();
          if (res.ok) {
            addMemoryForm.reset();
            showToast('Memory saved', 'info');
            loadMemories();
          } else {
            errEl.textContent = data.detail || 'Could not save memory.';
            errEl.classList.remove('hidden');
          }
        } catch (err) {
          errEl.textContent = 'Error saving memory.';
          errEl.classList.remove('hidden');
        }
      });
    }

    const clearAllMemoriesBtn = document.getElementById('clear-all-memories-btn');
    if (clearAllMemoriesBtn) {
      clearAllMemoriesBtn.addEventListener('click', async () => {
        if (!confirm('Clear all long-term memories? The assistant will forget these facts.')) return;
        try {
          const res = await authFetch('/api/memories', { method: 'DELETE' });
          if (res.ok) {
            showToast('All memories cleared', 'info');
            loadMemories();
          }
        } catch (e) {
          showToast('Failed to clear memories', 'error');
        }
      });
    }

    // Main Log Out
    if (logoutBtn) {
      logoutBtn.addEventListener('click', async () => {
        try {
          await authFetch('/api/auth/logout', { method: 'POST' });
        } catch (_) {}
        currentUser = null;
        conversations = [];
        currentConversationId = null;
        localStorage.removeItem('goldsea_active_conv');
        renderConversationsList();
        showAuthScreen('login');
        showToast('Signed out.', 'info');
      });
    }
  }

  async function loadMemories() {
    const listEl = document.getElementById('memories-list');
    const countEl = document.getElementById('memories-count');
    if (!listEl) return;
    try {
      const res = await authFetch('/api/memories');
      if (res.ok) {
        const memories = await res.json();
        if (countEl) countEl.textContent = memories.length;
        if (memories.length === 0) {
          listEl.innerHTML = '<div class="text-xs text-slate-500 p-3 text-center">No persistent memories saved yet. Talk with the assistant or add facts above.</div>';
          return;
        }
        listEl.innerHTML = '';
        memories.forEach(m => {
          const row = document.createElement('div');
          row.className = 'flex items-center justify-between p-2.5 rounded-lg bg-dark-900 border border-spider-500/10 text-xs';
          row.innerHTML = `
            <div class="min-w-0 flex-1 mr-2">
              <div class="font-mono text-[11px] text-spider-400">${escapeHtml(m.key)}</div>
              <div class="text-slate-200 truncate">${escapeHtml(m.value)}</div>
            </div>
            <button class="delete-memory-btn p-1 text-slate-400 hover:text-rose-400 rounded transition-colors" data-id="${m.id || m.key}" title="Delete memory">
              <i data-lucide="trash-2" class="w-3.5 h-3.5"></i>
            </button>
          `;
          row.querySelector('.delete-memory-btn').addEventListener('click', async (e) => {
            e.stopPropagation();
            await deleteMemory(m.id || m.key);
          });
          listEl.appendChild(row);
        });
        initLucide();
      }
    } catch (e) {
      console.error('Failed to load memories', e);
    }
  }

  async function deleteMemory(keyOrId) {
    try {
      const res = await authFetch(`/api/memories/${encodeURIComponent(keyOrId)}`, { method: 'DELETE' });
      if (res.ok) {
        showToast('Memory removed', 'info');
        loadMemories();
      }
    } catch (e) {
      showToast('Failed to delete memory', 'error');
    }
  }

  function initVisualViewport() {
    const updateAppHeight = () => {
      const h = (window.visualViewport && window.visualViewport.height) || window.innerHeight;
      document.documentElement.style.setProperty('--app-height', `${h}px`);
      if (window.scrollY !== 0) {
        window.scrollTo(0, 0);
      }
    };
    updateAppHeight();
    if (window.visualViewport) {
      window.visualViewport.addEventListener('resize', updateAppHeight);
      window.visualViewport.addEventListener('scroll', updateAppHeight);
    }
    window.addEventListener('resize', () => {
      updateAppHeight();
      if (window.innerWidth >= 768) {
        sidebarBackdrop.classList.add('hidden');
        sidebar.setAttribute('aria-hidden', 'false');
      }
    });
    chatInput.addEventListener('focus', () => {
      if (window.innerWidth < 768) {
        setTimeout(scrollToBottom, 150);
      }
    });
  }

  function setupDrawerSwipe() {
    if (!sidebar) return;
    let startX = null;
    let startY = null;
    sidebar.addEventListener('touchstart', (e) => {
      if (window.innerWidth >= 768) return;
      const t = (e.touches && e.touches[0]) || (e.changedTouches && e.changedTouches[0]);
      if (!t) return;
      startX = t.clientX;
      startY = t.clientY;
    }, { passive: true });
    sidebar.addEventListener('touchend', (e) => {
      if (startX === null || window.innerWidth >= 768) {
        startX = null;
        return;
      }
      const t = (e.changedTouches && e.changedTouches[0]) || (e.touches && e.touches[0]);
      if (!t) {
        startX = null;
        return;
      }
      const dx = t.clientX - startX;
      const dy = t.clientY - startY;
      if (dx < -45 && Math.abs(dx) > Math.abs(dy)) {
        closeMobileSidebar();
      }
      startX = null;
      startY = null;
    }, { passive: true });
  }

  function openMobileSidebar() {
    sidebar.classList.remove('-translate-x-full');
    sidebar.setAttribute('aria-hidden', 'false');
    sidebarBackdrop.classList.remove('hidden');
  }

  function closeMobileSidebar() {
    sidebar.classList.add('-translate-x-full');
    sidebar.setAttribute('aria-hidden', window.innerWidth < 768 ? 'true' : 'false');
    sidebarBackdrop.classList.add('hidden');
  }

  function updateSendButtonState() {
    const hasText = chatInput.value.trim().length > 0;
    const hasFiles = attachedFiles.length > 0;
    sendBtn.disabled = !(hasText || hasFiles) || isStreaming;
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

  // --- PWA Service Worker & Install Banners ---
  function initServiceWorker() {
    if ('serviceWorker' in navigator) {
      window.addEventListener('load', () => {
        navigator.serviceWorker.register('/sw.js')
          .then((reg) => reg.update().catch(() => {}))
          .catch(() => {});
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

  function initIosInstallBanner() {
    if (!iosInstallBanner) return;
    const isIos = /iphone|ipad|ipod/i.test(window.navigator.userAgent);
    const isStandalone = ('standalone' in window.navigator && window.navigator.standalone) ||
      window.matchMedia('(display-mode: standalone)').matches;
    const dismissed = localStorage.getItem('goldsea_ios_a2hs_dismissed') === '1';
    if (isIos && !isStandalone && !dismissed) {
      iosInstallBanner.classList.remove('hidden');
    }
    if (dismissIosBannerBtn) {
      dismissIosBannerBtn.addEventListener('click', () => {
        iosInstallBanner.classList.add('hidden');
        localStorage.setItem('goldsea_ios_a2hs_dismissed', '1');
      });
    }
  }

  // Launch app
  document.addEventListener('DOMContentLoaded', init);

})();
