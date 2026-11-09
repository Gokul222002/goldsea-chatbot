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

  // Modals
  const shortcutsModal = document.getElementById('shortcuts-modal');
  const shortcutsModalBtn = document.getElementById('shortcuts-modal-btn');
  const closeShortcutsBtn = document.getElementById('close-shortcuts-btn');
  const exportModal = document.getElementById('export-modal');
  const exportChatBtn = document.getElementById('export-chat-btn');
  const closeExportBtn = document.getElementById('close-export-btn');
  const pwaInstallBtn = document.getElementById('pwa-install-btn');

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
    initLucide();
    initSpeechRecognition();
    initServiceWorker();
    setupEventListeners();
    setupDragAndDropAndPaste();
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
            const res = await fetch('/api/chat/transcribe', {
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
        const res = await fetch('/api/chat/upload', {
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
              <div class="inline-flex items-center gap-2 px-3 py-2 rounded-xl bg-dark-900/90 border border-spider-500/25 text-xs text-slate-200 shadow-sm">
                <i data-lucide="${icon}" class="w-4 h-4 text-spider-400 shrink-0"></i>
                <div class="flex flex-col text-left max-w-[180px] sm:max-w-[220px]">
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
        <div class="max-w-[85%] sm:max-w-xl rounded-2xl rounded-tr-sm bg-gradient-to-r from-emerald-600/20 to-spider-500/20 border border-spider-500/30 p-3.5 text-xs sm:text-sm text-slate-100 shadow-sm leading-relaxed">
          ${attachmentsHtml}
          ${msg.content ? `<div class="whitespace-pre-wrap">${escapeHtml(msg.content)}</div>` : ''}
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
          <button class="follow-up-chip px-3 py-1.5 rounded-full bg-dark-850 hover:bg-dark-800 border border-spider-500/30 hover:border-spider-400/60 text-spider-400 hover:text-spider-300 text-xs font-medium transition-all text-left shadow-sm active:scale-95 flex items-center gap-1.5">
            <i data-lucide="arrow-right" class="w-3 h-3 text-spider-400"></i>
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

      // Per-reply Action Buttons
      const actionsBarHtml = `
        <div class="mt-2.5 flex items-center gap-1 text-[11px] text-slate-400 border-t border-white/5 pt-2">
          <button class="per-reply-btn hover:text-spider-400 p-1.5 rounded-md hover:bg-white/5 flex items-center gap-1 transition-colors" data-action="regenerate" data-msg-id="${msg.id}" title="Regenerate this response">
            <i data-lucide="refresh-cw" class="w-3.5 h-3.5"></i>
            <span class="hidden sm:inline">Regenerate</span>
          </button>
          <button class="per-reply-btn hover:text-spider-400 p-1.5 rounded-md hover:bg-white/5 flex items-center gap-1 transition-colors" data-action="shorter" data-msg-id="${msg.id}" title="Make shorter">
            <i data-lucide="minimize-2" class="w-3.5 h-3.5"></i>
            <span class="hidden sm:inline">Make shorter</span>
          </button>
          <button class="per-reply-btn hover:text-spider-400 p-1.5 rounded-md hover:bg-white/5 flex items-center gap-1 transition-colors" data-action="detailed" data-msg-id="${msg.id}" title="Make more detailed">
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
        <div class="max-w-[95%] sm:max-w-2xl rounded-2xl rounded-tl-sm bg-dark-900 border border-spider-500/15 p-4 shadow-md w-full">
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
    assistantCard.className = 'flex flex-col items-start space-y-1.5 w-full';
    assistantCard.innerHTML = `
      <div class="max-w-[95%] sm:max-w-2xl rounded-2xl rounded-tl-sm bg-dark-900 border border-spider-500/15 p-4 shadow-md w-full">
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
      const response = await fetch('/api/chat/stream', {
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
        <button class="follow-up-chip px-3 py-1.5 rounded-full bg-dark-850 hover:bg-dark-800 border border-spider-500/30 hover:border-spider-400/60 text-spider-400 hover:text-spider-300 text-xs font-medium transition-all text-left shadow-sm active:scale-95 flex items-center gap-1.5">
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
        <button class="per-reply-btn hover:text-spider-400 p-1.5 rounded-md hover:bg-white/5 flex items-center gap-1 transition-colors" data-action="regenerate" data-msg-id="${msgId}">
          <i data-lucide="refresh-cw" class="w-3.5 h-3.5"></i>
          <span class="hidden sm:inline">Regenerate</span>
        </button>
        <button class="per-reply-btn hover:text-spider-400 p-1.5 rounded-md hover:bg-white/5 flex items-center gap-1 transition-colors" data-action="shorter" data-msg-id="${msgId}">
          <i data-lucide="minimize-2" class="w-3.5 h-3.5"></i>
          <span class="hidden sm:inline">Make shorter</span>
        </button>
        <button class="per-reply-btn hover:text-spider-400 p-1.5 rounded-md hover:bg-white/5 flex items-center gap-1 transition-colors" data-action="detailed" data-msg-id="${msgId}">
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

    const placeholderCard = document.createElement('div');
    placeholderCard.className = 'flex flex-col items-start space-y-1.5 w-full';
    placeholderCard.innerHTML = `
      <div class="max-w-[95%] sm:max-w-2xl rounded-2xl bg-dark-900 border border-white/5 p-4 text-xs text-slate-400 flex items-center gap-2">
        <span class="w-2 h-2 rounded-full bg-spider-400 animate-ping"></span>
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

  // --- Quick Actions Grid ---
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

    // Shortcuts Modal
    shortcutsModalBtn.addEventListener('click', () => shortcutsModal.classList.remove('hidden'));
    closeShortcutsBtn.addEventListener('click', () => shortcutsModal.classList.add('hidden'));

    // Export Modal
    exportChatBtn.addEventListener('click', () => {
      if (!currentConversationId) {
        showToast('Please select or start a conversation first.', 'info');
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
        exportModal.classList.add('hidden');
        if (imageModal) imageModal.classList.add('hidden');
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

  // Launch app
  document.addEventListener('DOMContentLoaded', init);

})();
