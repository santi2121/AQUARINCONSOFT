/* ============================================
   GOTICA — Asistente IA del Acueducto
   Agregar al final de script.js
   ============================================ */

// ── CHAT WIDGET ──────────────────────────────
(function initChat() {

  // ─ Inyectar HTML del widget ─────────────────
  const chatHTML = `
  <div id="chatWidget" class="chat-widget" aria-live="polite">

    <!-- Botón flotante -->
    <button id="chatToggle" class="chat-toggle" aria-label="Abrir asistente Gotica">
      <span class="chat-toggle-icon chat-toggle-open">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="24" height="24">
          <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
        </svg>
      </span>
      <span class="chat-toggle-icon chat-toggle-close" style="display:none">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="24" height="24">
          <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
        </svg>
      </span>
      <span class="chat-badge" id="chatBadge">1</span>
    </button>

    <!-- Ventana del chat -->
    <div class="chat-window" id="chatWindow" aria-hidden="true">
      <div class="chat-header">
        <div class="chat-avatar">
          <svg viewBox="0 0 40 40" fill="none" width="36" height="36">
            <path d="M20 3C20 3 9 13 9 21C9 27.075 13.925 32 20 32C26.075 32 31 27.075 31 21C31 13 20 3 20 3Z" fill="url(#cGrad)"/>
            <defs><linearGradient id="cGrad" x1="20" y1="3" x2="20" y2="32"><stop offset="0%" stop-color="#80DEEA"/><stop offset="100%" stop-color="#0288D1"/></linearGradient></defs>
          </svg>
        </div>
        <div class="chat-header-info">
          <strong>Gotica 💧</strong>
          <span class="chat-status"><span class="status-dot"></span>Asistente activo</span>
        </div>
        <button class="chat-minimize" id="chatMinimize" aria-label="Minimizar">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="16" height="16"><line x1="5" y1="12" x2="19" y2="12"/></svg>
        </button>
      </div>

      <div class="chat-messages" id="chatMessages">
        <!-- Mensaje de bienvenida -->
        <div class="chat-msg assistant">
          <div class="msg-bubble">
            👋 ¡Hola! Soy <strong>Gotica</strong>, tu asistente del Acueducto Rincón Santo.<br/><br/>
            Puedo ayudarte con consultas de factura, acuerdos de pago, PQRS y más. ¿En qué te ayudo hoy?
          </div>
          <div class="msg-time">${formatTime(new Date())}</div>
        </div>

        <!-- Sugerencias rápidas -->
        <div class="chat-suggestions" id="chatSuggestions">
          <button class="suggestion-chip" data-msg="¿Cómo consulto mi factura?">📄 Consultar factura</button>
          <button class="suggestion-chip" data-msg="Quiero hacer un acuerdo de pago">🤝 Acuerdo de pago</button>
          <button class="suggestion-chip" data-msg="¿Cuáles son los horarios de atención?">🕐 Horarios</button>
          <button class="suggestion-chip" data-msg="Quiero enviar un PQRS">📬 PQRS</button>
        </div>
      </div>

      <div class="chat-footer">
        <div class="chat-input-wrap">
          <textarea
            id="chatInput"
            class="chat-input"
            placeholder="Escribe tu consulta…"
            rows="1"
            maxlength="500"
            aria-label="Escribe tu mensaje"
          ></textarea>
          <button class="chat-send" id="chatSend" aria-label="Enviar">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="18" height="18">
              <line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/>
            </svg>
          </button>
        </div>
        <p class="chat-disclaimer">Asistente IA local · Acueducto Rincón Santo</p>
      </div>
    </div>

  </div>`;

  document.body.insertAdjacentHTML('beforeend', chatHTML);
  injectChatStyles();
  bindChatEvents();

})();

// ── Historial de conversación ────────────────
const chatHistory = [];

// ── Eventos ──────────────────────────────────
function bindChatEvents() {
  const toggle    = document.getElementById('chatToggle');
  const minimize  = document.getElementById('chatMinimize');
  const window_   = document.getElementById('chatWindow');
  const input     = document.getElementById('chatInput');
  const sendBtn   = document.getElementById('chatSend');
  const badge     = document.getElementById('chatBadge');

  // Abrir / cerrar
  toggle.addEventListener('click', () => {
    const isOpen = window_.classList.toggle('open');
    window_.setAttribute('aria-hidden', !isOpen);
    toggle.querySelector('.chat-toggle-open').style.display = isOpen ? 'none' : '';
    toggle.querySelector('.chat-toggle-close').style.display = isOpen ? '' : 'none';
    badge.style.display = 'none';
    if (isOpen) input.focus();
  });

  minimize.addEventListener('click', () => {
    window_.classList.remove('open');
    window_.setAttribute('aria-hidden', 'true');
    toggle.querySelector('.chat-toggle-open').style.display = '';
    toggle.querySelector('.chat-toggle-close').style.display = 'none';
  });

  // Enviar con Enter (Shift+Enter = salto de línea)
  input.addEventListener('keydown', e => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessageFast();
    }
  });

  // Auto-resize del textarea
  input.addEventListener('input', () => {
    input.style.height = 'auto';
    input.style.height = Math.min(input.scrollHeight, 100) + 'px';
  });

  sendBtn.addEventListener('click', sendMessageFast);

  // Chips de sugerencia
  document.querySelectorAll('.suggestion-chip').forEach(chip => {
    chip.addEventListener('click', () => {
      document.getElementById('chatInput').value = chip.dataset.msg;
      sendMessageFast();
      document.getElementById('chatSuggestions')?.remove();
    });
  });
}

// ── Enviar mensaje ───────────────────────────
async function sendMessage() {
  const input = document.getElementById('chatInput');
  const text  = input.value.trim();
  if (!text) return;

  // Ocultar sugerencias al primer mensaje real
  document.getElementById('chatSuggestions')?.remove();

  input.value = '';
  input.style.height = 'auto';

  appendMessage('user', text);
  chatHistory.push({ role: 'user', content: text });

  const typingId = showTyping();

  try {
    const res = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        message: text,
        history: chatHistory.slice(-10),
      }),
    });

    const data = await res.json();
    hideTyping(typingId);

    if (data.reply) {
      appendMessage('assistant', data.reply);
      chatHistory.push({ role: 'assistant', content: data.reply });
    } else {
      appendMessage('assistant', '⚠️ Ocurrió un error. Por favor intenta nuevamente.');
    }
  } catch (err) {
    hideTyping(typingId);
    appendMessage('assistant', '⚠️ No pude conectarme con el servidor. Verifica que el servidor Flask esté corriendo.');
    console.error('Chat error:', err);
  }
}

// ── Helpers ──────────────────────────────────
async function sendMessageFast() {
  const input = document.getElementById('chatInput');
  const sendBtn = document.getElementById('chatSend');
  const text = input.value.trim();
  if (!text) return;

  document.getElementById('chatSuggestions')?.remove();

  input.value = '';
  input.style.height = 'auto';

  appendMessage('user', text);
  chatHistory.push({ role: 'user', content: text });

  const typingId = showTyping();
  sendBtn.disabled = true;

  try {
    const res = await fetch('/api/chat/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        message: text,
        history: chatHistory.slice(-6),
      }),
    });

    if (!res.ok || !res.body) {
      throw new Error('Respuesta invalida del servidor');
    }

    hideTyping(typingId);
    const streamMsg = appendStreamingMessage('assistant');
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    let reply = '';

    while (true) {
      const { value, done } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const parts = buffer.split('\n\n');
      buffer = parts.pop() || '';

      for (const part of parts) {
        const line = part.split('\n').find(item => item.startsWith('data: '));
        if (!line) continue;

        const payload = line.slice(6);
        if (payload === '[DONE]') continue;

        const data = JSON.parse(payload);
        if (data.token) {
          reply += data.token;
          updateStreamingMessage(streamMsg, reply);
        }
      }
    }

    reply = reply.trim();
    if (reply) {
      updateStreamingMessage(streamMsg, reply);
      chatHistory.push({ role: 'assistant', content: reply });
    } else {
      streamMsg.wrapper.remove();
      appendMessage('assistant', 'No encontre una respuesta para esa consulta. Intenta escribirla con un poco mas de detalle.');
    }
  } catch (err) {
    hideTyping(typingId);
    appendMessage('assistant', 'No pude conectarme con el servidor. Verifica que Flask este corriendo e intenta de nuevo.');
    console.error('Chat error:', err);
  } finally {
    sendBtn.disabled = false;
  }
}

function appendMessage(role, text) {
  const msgs = document.getElementById('chatMessages');
  const div  = document.createElement('div');
  div.className = `chat-msg ${role}`;

  // Convertir saltos de línea y negritas básicas
  const safeText = text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
    .replace(/\n/g, '<br/>');

  div.innerHTML = `
    <div class="msg-bubble">${safeText}</div>
    <div class="msg-time">${formatTime(new Date())}</div>
  `;
  msgs.appendChild(div);
  msgs.scrollTop = msgs.scrollHeight;
}

function appendStreamingMessage(role) {
  const msgs = document.getElementById('chatMessages');
  const wrapper = document.createElement('div');
  wrapper.className = `chat-msg ${role}`;
  wrapper.innerHTML = `
    <div class="msg-bubble"></div>
    <div class="msg-time">${formatTime(new Date())}</div>
  `;
  msgs.appendChild(wrapper);
  msgs.scrollTop = msgs.scrollHeight;
  return { wrapper, bubble: wrapper.querySelector('.msg-bubble') };
}

function updateStreamingMessage(streamMsg, text) {
  streamMsg.bubble.innerHTML = formatMessageText(text);
  const msgs = document.getElementById('chatMessages');
  msgs.scrollTop = msgs.scrollHeight;
}

function formatMessageText(text) {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
    .replace(/\n/g, '<br/>');
}

function showTyping() {
  const msgs = document.getElementById('chatMessages');
  const id   = 'typing-' + Date.now();
  const div  = document.createElement('div');
  div.id = id;
  div.className = 'chat-msg assistant typing-indicator';
  div.innerHTML = `<div class="msg-bubble"><span></span><span></span><span></span></div>`;
  msgs.appendChild(div);
  msgs.scrollTop = msgs.scrollHeight;
  return id;
}

function hideTyping(id) {
  document.getElementById(id)?.remove();
}

function formatTime(date) {
  return date.toLocaleTimeString('es-CO', { hour: '2-digit', minute: '2-digit' });
}

// ── CSS del widget ────────────────────────────
function injectChatStyles() {
  const style = document.createElement('style');
  style.textContent = `
    /* ── Widget contenedor ── */
    .chat-widget {
      position: fixed;
      bottom: 28px;
      right: 28px;
      z-index: 9999;
      font-family: 'DM Sans', sans-serif;
    }

    /* ── Botón flotante ── */
    .chat-toggle {
      width: 60px; height: 60px;
      border-radius: 50%;
      background: linear-gradient(135deg, #0288D1, #4FC3F7);
      border: none; cursor: pointer;
      box-shadow: 0 4px 20px rgba(2,136,209,0.5);
      display: flex; align-items: center; justify-content: center;
      color: #fff;
      transition: transform 0.2s, box-shadow 0.2s;
      position: relative;
    }
    .chat-toggle:hover {
      transform: scale(1.08);
      box-shadow: 0 6px 28px rgba(2,136,209,0.65);
    }
    .chat-toggle-icon { display: flex; }
    .chat-badge {
      position: absolute; top: 2px; right: 2px;
      width: 18px; height: 18px; border-radius: 50%;
      background: #F44336; color: #fff;
      font-size: 10px; font-weight: 700;
      display: flex; align-items: center; justify-content: center;
      border: 2px solid #fff;
    }

    /* ── Ventana ── */
    .chat-window {
      position: absolute;
      bottom: 72px; right: 0;
      width: 360px; max-height: 520px;
      background: rgba(10, 20, 35, 0.97);
      border: 1px solid rgba(79,195,247,0.2);
      border-radius: 20px;
      display: flex; flex-direction: column;
      overflow: hidden;
      box-shadow: 0 20px 60px rgba(0,0,0,0.6);
      transform: scale(0.92) translateY(10px);
      opacity: 0; pointer-events: none;
      transform-origin: bottom right;
      transition: transform 0.25s cubic-bezier(.34,1.56,.64,1), opacity 0.2s;
    }
    .chat-window.open {
      opacity: 1; pointer-events: all;
      transform: scale(1) translateY(0);
    }

    /* ── Header ── */
    .chat-header {
      display: flex; align-items: center; gap: 10px;
      padding: 14px 16px;
      background: rgba(2,136,209,0.12);
      border-bottom: 1px solid rgba(79,195,247,0.12);
    }
    .chat-header-info { flex: 1; }
    .chat-header-info strong { display: block; color: #E0F7FA; font-size: 14px; }
    .chat-status { font-size: 11px; color: #80CBC4; display: flex; align-items: center; gap: 5px; }
    .status-dot {
      width: 7px; height: 7px; border-radius: 50%;
      background: #4CAF50;
      animation: pulse-dot 2s infinite;
    }
    @keyframes pulse-dot {
      0%,100% { opacity: 1; } 50% { opacity: 0.4; }
    }
    .chat-minimize {
      background: none; border: none; color: #80CBC4;
      cursor: pointer; padding: 4px; border-radius: 6px;
      display: flex; align-items: center;
      transition: color 0.2s;
    }
    .chat-minimize:hover { color: #4FC3F7; }

    /* ── Mensajes ── */
    .chat-messages {
      flex: 1; overflow-y: auto;
      padding: 16px 14px;
      display: flex; flex-direction: column; gap: 10px;
      scroll-behavior: smooth;
    }
    .chat-messages::-webkit-scrollbar { width: 4px; }
    .chat-messages::-webkit-scrollbar-thumb { background: rgba(79,195,247,0.2); border-radius: 4px; }

    .chat-msg { display: flex; flex-direction: column; max-width: 86%; }
    .chat-msg.user { align-self: flex-end; align-items: flex-end; }
    .chat-msg.assistant { align-self: flex-start; align-items: flex-start; }

    .msg-bubble {
      padding: 10px 14px;
      border-radius: 16px;
      font-size: 13.5px;
      line-height: 1.55;
    }
    .chat-msg.user .msg-bubble {
      background: linear-gradient(135deg, #0288D1, #0097A7);
      color: #fff;
      border-bottom-right-radius: 4px;
    }
    .chat-msg.assistant .msg-bubble {
      background: rgba(255,255,255,0.06);
      border: 1px solid rgba(79,195,247,0.15);
      color: #CFD8DC;
      border-bottom-left-radius: 4px;
    }
    .msg-time { font-size: 10px; color: rgba(176,190,197,0.5); margin-top: 3px; }

    /* ── Typing dots ── */
    .typing-indicator .msg-bubble {
      display: flex; gap: 5px; align-items: center;
      padding: 12px 16px;
    }
    .typing-indicator .msg-bubble span {
      width: 7px; height: 7px; border-radius: 50%;
      background: #4FC3F7;
      animation: typingDot 1.2s infinite;
    }
    .typing-indicator .msg-bubble span:nth-child(2) { animation-delay: 0.2s; }
    .typing-indicator .msg-bubble span:nth-child(3) { animation-delay: 0.4s; }
    @keyframes typingDot {
      0%,80%,100% { transform: scale(0.7); opacity: 0.4; }
      40% { transform: scale(1); opacity: 1; }
    }

    /* ── Sugerencias ── */
    .chat-suggestions {
      display: flex; flex-wrap: wrap; gap: 6px;
      padding: 0 0 4px;
    }
    .suggestion-chip {
      background: rgba(2,136,209,0.15);
      border: 1px solid rgba(79,195,247,0.25);
      color: #80DEEA;
      border-radius: 20px;
      padding: 5px 12px;
      font-size: 12px;
      cursor: pointer;
      font-family: 'DM Sans', sans-serif;
      transition: background 0.2s, transform 0.15s;
    }
    .suggestion-chip:hover {
      background: rgba(2,136,209,0.3);
      transform: translateY(-1px);
    }

    /* ── Footer / input ── */
    .chat-footer {
      padding: 10px 14px 12px;
      border-top: 1px solid rgba(79,195,247,0.1);
    }
    .chat-input-wrap {
      display: flex; align-items: flex-end; gap: 8px;
      background: rgba(255,255,255,0.05);
      border: 1px solid rgba(79,195,247,0.2);
      border-radius: 14px;
      padding: 8px 10px;
      transition: border-color 0.2s;
    }
    .chat-input-wrap:focus-within { border-color: rgba(79,195,247,0.5); }
    .chat-input {
      flex: 1; background: none; border: none; outline: none;
      color: #E0F7FA; font-size: 13.5px;
      font-family: 'DM Sans', sans-serif;
      resize: none; line-height: 1.5;
      max-height: 100px; overflow-y: auto;
    }
    .chat-input::placeholder { color: rgba(176,190,197,0.4); }
    .chat-send {
      background: linear-gradient(135deg, #0288D1, #4FC3F7);
      border: none; border-radius: 10px;
      width: 34px; height: 34px;
      color: #fff; cursor: pointer;
      display: flex; align-items: center; justify-content: center;
      flex-shrink: 0;
      transition: transform 0.15s, opacity 0.2s;
    }
    .chat-send:hover { transform: scale(1.1); }
    .chat-disclaimer {
      font-size: 10px; color: rgba(176,190,197,0.3);
      text-align: center; margin: 6px 0 0;
    }

    /* ── Responsive ── */
    @media (max-width: 420px) {
      .chat-window { width: calc(100vw - 32px); right: -4px; }
      .chat-widget { right: 16px; bottom: 16px; }
    }
  `;
  document.head.appendChild(style);
}
