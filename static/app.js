"use strict";

// ── WebSocket ──────────────────────────────────────────────────────────────

let ws = null;
let wsReconnectDelay = 1000;
const WS_MAX_DELAY = 30000;

function connectWS() {
  const protocol = location.protocol === "https:" ? "wss:" : "ws:";
  const url = `${protocol}//${location.host}/ws`;
  ws = new WebSocket(url);
  ws.binaryType = "arraybuffer";

  ws.onopen = () => {
    wsReconnectDelay = 1000;
    setStatus("待機", "idle");
  };

  ws.onmessage = (e) => {
    if (typeof e.data === "string") {
      handleServerMsg(JSON.parse(e.data));
    }
  };

  ws.onclose = () => {
    setStatus("連線中斷，重新連線中...", "processing");
    setTimeout(() => {
      wsReconnectDelay = Math.min(wsReconnectDelay * 2, WS_MAX_DELAY);
      connectWS();
    }, wsReconnectDelay);
  };

  ws.onerror = () => ws.close();
}

function wsSend(obj) {
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify(obj));
  }
}

// ── Server message handler ─────────────────────────────────────────────────

function handleServerMsg(msg) {
  switch (msg.type) {
    case "message":
      appendMessage(msg.role, msg.text);
      if (msg.role === "assistant") lastAssistantResponse = msg.text;
      break;
    case "status":
      handleStatus(msg.text);
      break;
    case "tts":
      enqueueTTS(msg.text, msg.priority || "medium");
      break;
    case "tts_control":
      if (msg.action === "stop") cancelTTS();
      break;
    case "sessions":
      updateSessionSelect(msg.list, msg.current);
      break;
    case "clear":
      document.getElementById("messages").innerHTML = "";
      break;
  }
}

function handleStatus(text) {
  const dotClass = {
    "待機":   "idle",
    "錄音中": "recording",
    "處理中": "processing",
    "傳送中": "sending",
  }[text] || "idle";
  setStatus(text, dotClass);
}

// ── Status bar ─────────────────────────────────────────────────────────────

function setStatus(text, dotClass) {
  document.getElementById("status-text").textContent = text;
  const dot = document.getElementById("status-dot");
  dot.className = "status-dot " + (dotClass || "idle");
}

// ── Messages ───────────────────────────────────────────────────────────────

const ROLE_LABELS = {
  user:      "你",
  voice:     "🎙 語音",
  assistant: "🤖 AI",
  system:    "⌘ 系統",
  summary:   "💡 摘要",
  error:     "⚠ 錯誤",
  sending:   "📤",
};

function appendMessage(role, text) {
  const msgs = document.getElementById("messages");
  const div = document.createElement("div");
  div.className = `message msg-${role}`;

  const header = document.createElement("div");
  header.className = "message-header";
  header.textContent = ROLE_LABELS[role] || role;

  const body = document.createElement("div");
  body.className = "message-body";
  body.textContent = text;

  div.appendChild(header);
  div.appendChild(body);
  msgs.appendChild(div);

  // Auto-scroll to bottom
  msgs.scrollTop = msgs.scrollHeight;
}

// ── Text input ─────────────────────────────────────────────────────────────

function sendText() {
  const input = document.getElementById("text-input");
  const content = input.value.trim();
  if (!content) return;
  input.value = "";

  if (content.startsWith("/")) {
    const parts = content.split(/\s+/);
    const cmd = parts[0].toLowerCase();
    const args = parts.slice(1);
    wsSend({ type: "cmd", cmd, args });
  } else {
    wsSend({ type: "text", content });
  }
  input.focus();
}

function onInputKeydown(e) {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    sendText();
  }
}

// ── Command helpers ────────────────────────────────────────────────────────

function sendCmd(cmd, args) {
  wsSend({ type: "cmd", cmd, args: args || [] });
  closePanel();
}

function promptCmd(cmd, label) {
  const val = prompt(label);
  if (val === null) return;
  const args = val.trim() ? [val.trim()] : [];
  wsSend({ type: "cmd", cmd, args });
  closePanel();
}

function promptRename() {
  const oldName = prompt("舊名稱:");
  if (!oldName) return;
  const newName = prompt("新名稱:");
  if (!newName) return;
  wsSend({ type: "cmd", cmd: "/rename", args: [oldName.trim(), newName.trim()] });
  closePanel();
}

// ── Session select ─────────────────────────────────────────────────────────

function updateSessionSelect(list, current) {
  const sel = document.getElementById("session-select");
  sel.innerHTML = "";
  list.forEach(title => {
    const opt = document.createElement("option");
    // title may have " (當前)" suffix from list_sessions()
    const cleanTitle = title.replace(" (當前)", "");
    opt.value = cleanTitle;
    opt.textContent = cleanTitle;
    if (title.includes("(當前)") || cleanTitle === current) {
      opt.selected = true;
    }
    sel.appendChild(opt);
  });
}

function onSessionChange(sel) {
  const title = sel.value;
  if (title) {
    wsSend({ type: "cmd", cmd: "/switch", args: [title] });
  }
}

// ── Command panel ──────────────────────────────────────────────────────────

function togglePanel() {
  const panel = document.getElementById("cmd-panel");
  if (panel.classList.contains("visible")) {
    closePanel();
  } else {
    panel.classList.add("visible");
    document.getElementById("panel-overlay").classList.add("visible");
  }
}

function closePanel() {
  document.getElementById("cmd-panel").classList.remove("visible");
  document.getElementById("panel-overlay").classList.remove("visible");
}

// ── Recording ──────────────────────────────────────────────────────────────

let mediaRecorder = null;
let audioChunks = [];
let isRecording = false;
let mediaStream = null;

async function toggleRecord() {
  if (isRecording) {
    stopRecord();
  } else {
    await startRecord();
  }
}

async function startRecord() {
  // Unlock SpeechSynthesis on first user gesture (iOS requirement)
  unlockSpeechSynthesis();

  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    alert("此瀏覽器不支援麥克風存取。\niOS 需使用 Safari，且可能需要 HTTPS。");
    return;
  }

  try {
    mediaStream = await navigator.mediaDevices.getUserMedia({ audio: true });
  } catch (err) {
    alert("無法存取麥克風：" + err.message);
    return;
  }

  // Pick a supported MIME type (WebM → Chrome/Android, mp4 → Safari/iOS)
  const mimeType = pickAudioMime();
  const options = mimeType ? { mimeType } : {};

  try {
    mediaRecorder = new MediaRecorder(mediaStream, options);
  } catch (err) {
    mediaRecorder = new MediaRecorder(mediaStream);
  }

  audioChunks = [];
  mediaRecorder.ondataavailable = (e) => {
    if (e.data.size > 0) audioChunks.push(e.data);
  };
  mediaRecorder.onstop = sendAudio;
  mediaRecorder.start();

  isRecording = true;
  setRecordUI(true);
}

function stopRecord() {
  if (mediaRecorder && mediaRecorder.state !== "inactive") {
    mediaRecorder.stop();
  }
  if (mediaStream) {
    mediaStream.getTracks().forEach(t => t.stop());
    mediaStream = null;
  }
  isRecording = false;
  setRecordUI(false);
}

function sendAudio() {
  if (audioChunks.length === 0) return;
  const blob = new Blob(audioChunks, { type: mediaRecorder.mimeType });
  audioChunks = [];
  if (ws && ws.readyState === WebSocket.OPEN) {
    // Send as binary frame
    blob.arrayBuffer().then(buf => ws.send(buf));
  }
}

function setRecordUI(recording) {
  const btn = document.getElementById("record-btn");
  const icon = document.getElementById("record-icon");
  const label = document.getElementById("record-label");

  if (recording) {
    btn.classList.add("recording");
    icon.textContent = "⏺";
    label.textContent = "停止錄音";
  } else {
    btn.classList.remove("recording");
    icon.textContent = "🎙";
    label.textContent = "錄音";
  }
}

function pickAudioMime() {
  const candidates = [
    "audio/webm;codecs=opus",
    "audio/webm",
    "audio/ogg;codecs=opus",
    "audio/mp4",
  ];
  for (const m of candidates) {
    if (MediaRecorder.isTypeSupported && MediaRecorder.isTypeSupported(m)) {
      return m;
    }
  }
  return "";
}

// ── TTS (Web Speech API) ───────────────────────────────────────────────────

// Priority: high=0, medium=1, low=2
const TTS_PRIORITY = { high: 0, medium: 1, low: 2 };
let ttsQueue = [];  // [{ text, priority }]
let ttsSpeaking = false;
let ttsUnlocked = false;
let lastAssistantResponse = "";

function unlockSpeechSynthesis() {
  if (ttsUnlocked || !window.speechSynthesis) return;
  const u = new SpeechSynthesisUtterance("");
  u.volume = 0;
  window.speechSynthesis.speak(u);
  ttsUnlocked = true;
}

function getChineseVoice() {
  const voices = window.speechSynthesis.getVoices();
  return (
    voices.find(v => v.lang === "zh-TW") ||
    voices.find(v => v.lang === "zh-CN") ||
    voices.find(v => v.lang.startsWith("zh")) ||
    null
  );
}

function enqueueTTS(text, priority) {
  if (!window.speechSynthesis || !text.trim()) return;
  const pval = TTS_PRIORITY[priority] ?? 1;

  if (pval === 0) {
    // HIGH: 打斷當前，清空佇列
    cancelTTS();
    ttsQueue = [{ text, pval }];
  } else {
    ttsQueue.push({ text, pval });
    ttsQueue.sort((a, b) => a.pval - b.pval);
  }
  playNextTTS();
}

function playNextTTS() {
  if (ttsSpeaking || ttsQueue.length === 0) return;
  if (!window.speechSynthesis) return;

  const { text } = ttsQueue.shift();
  const utt = new SpeechSynthesisUtterance(text);
  const voice = getChineseVoice();
  if (voice) utt.voice = voice;
  utt.lang = "zh-TW";
  utt.rate = 1.0;

  ttsSpeaking = true;
  utt.onend = utt.onerror = () => {
    ttsSpeaking = false;
    playNextTTS();
  };

  window.speechSynthesis.speak(utt);
}

function cancelTTS() {
  ttsQueue = [];
  ttsSpeaking = false;
  if (window.speechSynthesis) {
    window.speechSynthesis.cancel();
  }
}

function stopTTS() {
  cancelTTS();
  wsSend({ type: "signal", signal: "FORCE_STOP_TTS" });
}

function playLastResponse() {
  if (!lastAssistantResponse) return;
  cancelTTS();
  enqueueTTS(lastAssistantResponse, "medium");
}

// iOS Safari: SpeechSynthesis voices load asynchronously
if (window.speechSynthesis) {
  window.speechSynthesis.onvoiceschanged = () => {};
}

// ── Init ───────────────────────────────────────────────────────────────────

connectWS();
