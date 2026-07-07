import { useState, useRef, useEffect } from 'react';
import axios from 'axios';
import { Send, MessageSquare, Trash2, Zap, Heart, Smile, Frown, Shield } from 'lucide-react';
import ReactMarkdown from 'react-markdown';

// ── Persistent User ID (UUIDv4) ──────────────────────────────────────────
const getDeviceId = () => {
  let id = localStorage.getItem('chisa_device_uuid_v4');
  if (!id) {
    id = 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, c => {
      const r = Math.random() * 16 | 0;
      return (c === 'x' ? r : (r & 0x3 | 0x8)).toString(16);
    });
    localStorage.setItem('chisa_device_uuid_v4', id);
  }
  return id;
};

const BASE = 'http://localhost:8000/api/v1';
const GREETING = { role: 'chisa', content: 'Chào Senpai~ Em là Chisa đây ♡  Hôm nay Senpai có gì muốn tâm sự với em không?' };

async function streamChatResponse(payload, { onLoopThinkingStart } = {}) {
  const response = await fetch(`${BASE}/chat/stream`, {
    method: 'POST',
    headers: {
      'content-type': 'application/json',
      accept: 'text/event-stream',
    },
    body: JSON.stringify(payload),
  });

  if (!response.ok || !response.body) {
    const errorText = await response.text().catch(() => '');
    throw new Error(errorText || `HTTP ${response.status}`);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let finalPayload = null;

  const parseChunk = (chunk) => {
    const lines = chunk.split(/\r?\n/);
    let eventName = 'message';
    const dataLines = [];

    for (const line of lines) {
      if (line.startsWith('event:')) {
        eventName = line.slice(6).trim();
      } else if (line.startsWith('data:')) {
        dataLines.push(line.slice(5).trimStart());
      }
    }

    const dataText = dataLines.join('\n');
    const data = dataText ? JSON.parse(dataText) : {};
    return { eventName, data };
  };

  while (true) {
    const { value, done } = await reader.read();
    if (done) {
      break;
    }

    buffer += decoder.decode(value, { stream: true });

    let boundaryIndex = buffer.indexOf('\n\n');
    while (boundaryIndex !== -1) {
      const rawChunk = buffer.slice(0, boundaryIndex).trim();
      buffer = buffer.slice(boundaryIndex + 2);
      boundaryIndex = buffer.indexOf('\n\n');

      if (!rawChunk) {
        continue;
      }

      const { eventName, data } = parseChunk(rawChunk);
      if (eventName === 'loop_thinking_started' && typeof onLoopThinkingStart === 'function') {
        onLoopThinkingStart(data);
      }
      if (eventName === 'complete') {
        finalPayload = data;
      }
      if (eventName === 'error') {
        throw new Error(data?.message || 'Không thể tạo phản hồi');
      }
    }
  }

  if (!finalPayload) {
    throw new Error('Stream kết thúc mà không có phản hồi cuối cùng');
  }

  return finalPayload;
}

// ── Message Renderer ─────────────────────────────────────────────────────
function Message({ msg }) {
  if (msg.role === 'user') {
    // Render /clear as a system badge, not a normal bubble
    if (msg.content === '/clear') {
      return (
        <div className="msg-row">
          <div className="msg-command">
            <span className="msg-command-badge">/clear</span>
          </div>
        </div>
      );
    }
    return (
      <div className="msg-row">
        <div className="msg-user">
          <div className="msg-user-bubble">{msg.content}</div>
        </div>
      </div>
    );
  }
  return (
    <div className="msg-row">
      <div className="msg-chisa">
        <img src="/dance_chisa.gif" className="chisa-avatar-img" alt="Chisa" />
        <div className="chisa-bubble">
          <div className="chisa-content">
            <ReactMarkdown>{msg.content}</ReactMarkdown>
          </div>
        </div>
      </div>
    </div>
  );
}

// ── Emotion Panel ──────────────────────────────────────────────────────────
function EmotionPanel({ emotions }) {
  const bars = [
    { label: 'Vui vẻ', key: 'joy', icon: <Smile size={12} />, color: '#4caf50' },
    { label: 'Buồn bã', key: 'sadness', icon: <Frown size={12} />, color: '#2196f3' },
    { label: 'Tin tưởng', key: 'trust', icon: <Shield size={12} />, color: '#ffeb3b' },
    { label: 'Khó chịu', key: 'irritation', icon: <Zap size={12} />, color: '#f44336' },
    { label: 'Gắn kết', key: 'attachment', icon: <Heart size={12} />, color: '#e91e63' },
  ];

  return (
    <div className="emotion-panel">
      <div className="sidebar-section-label" style={{ padding: 0 }}>Cảm xúc</div>
      <div className="emotion-list">
        {bars.map(b => {
          const val = emotions?.[b.key] || 0;
          return (
            <div className="emotion-item" key={b.key}>
              <div className="emotion-header">
                <span className="emotion-label" style={{ color: b.color }}>
                  {b.icon} {b.label}
                </span>
                <span className="emotion-value" style={{ color: b.color }}>
                  {Math.round(val * 100)}%
                </span>
              </div>
              <div className="emotion-bar-bg">
                <div 
                  className="emotion-bar-fg" 
                  style={{ 
                    width: `${val * 100}%`, 
                    background: b.color,
                    color: b.color 
                  }} 
                />
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ── Sidebar ──────────────────────────────────────────────────────────────
function Sidebar({ onClear, emotions }) {
  return (
    <aside className="sidebar">
      <div className="sidebar-logo">
        <div className="logo-icon">
          <img src="/dance_chisa.gif" alt="Chisa" style={{ width: '100%', height: '100%', objectFit: 'cover', borderRadius: '8px' }} />
        </div>
        <span className="logo-text">CHISA<span className="logo-dot">.</span>AI</span>
      </div>

      <div className="sidebar-chisa-art">
        <img src="/chisa_drink.gif" alt="Chisa" className="sidebar-chisa-img" />
      </div>

      <EmotionPanel emotions={emotions} />

      <span className="sidebar-section-label">Điều hướng</span>

      <button className="sidebar-item active">
        <MessageSquare size={15} />
        Cuộc trò chuyện
      </button>

      <div className="sidebar-spacer" />

      <div className="sidebar-footer">
        <button
          className="sidebar-item"
          onClick={onClear}
          title="Xóa toàn bộ ký ức"
          style={{ color: '#c62828' }}
        >
          <Trash2 size={14} />
          Xóa ký ức
        </button>
        <div className="status-badge">
          <div className="status-dot" />
          <span>Backend kết nối</span>
        </div>
      </div>
    </aside>
  );
}

// ── Main App ─────────────────────────────────────────────────────────────
export default function App() {
  const [messages, setMessages]             = useState([]);
  const [input, setInput]                   = useState('');
  const [isLoading, setIsLoading]           = useState(false);
  const [isThinkingMode, setIsThinkingMode] = useState(false);
  const [emotions, setEmotions]             = useState({ joy: 0.5, sadness: 0.0, trust: 0.5, irritation: 0.0, attachment: 0.0 });
  const [isHistoryLoading, setIsHistoryLoading] = useState(true);
  const messagesEndRef = useRef(null);
  const textareaRef    = useRef(null);

  const scrollToBottom = () =>
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });

  // Fetch history on mount
  useEffect(() => {
    axios.get(`${BASE}/chat/history/${getDeviceId()}?limit=50`)
      .then(res => {
        const hist = res.data?.history || [];
        setMessages(hist.length
          ? hist.map(m => ({ role: m.role === 'assistant' ? 'chisa' : m.role, content: m.content }))
          : [GREETING]
        );
      })
      .catch(() => setMessages([GREETING]))
      .finally(() => setIsHistoryLoading(false));

    axios.get(`${BASE}/chat/emotions/${getDeviceId()}`)
      .then(res => {
        if (res.data) setEmotions(res.data);
      })
      .catch(console.error);
  }, []);

  useEffect(() => { scrollToBottom(); }, [messages, isLoading]);

  // Auto-grow textarea
  const handleInput = e => {
    setInput(e.target.value);
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 180)}px`;
    }
  };

  // Clear memory
  const handleClear = async () => {
    if (!window.confirm("Senpai có chắc chắn muốn xóa đi mọi kỷ niệm với em không? (Hành động này không thể hoàn tác đâu nhé!)")) {
      return;
    }
    setMessages(prev => [...prev, { role: 'user', content: '/clear' }]);
    setIsLoading(true);
    try {
      const res = await axios.delete(`${BASE}/chat/clear/${getDeviceId()}`);
      setMessages([{ role: 'chisa', content: `🌸 ${res.data?.message || 'Ký ức đã được xóa!'}` }]);
      // Reset UI emotions to default baseline values
      setEmotions({ joy: 0.1, sadness: 0.0, trust: 0.5, irritation: 0.0, attachment: 0.0 });
    } catch {
      setMessages(prev => [...prev, { role: 'chisa', content: '*(Lỗi)* Em không thể xóa ký ức lúc này, hãy thử lại nhé!' }]);
    } finally {
      setIsLoading(false);
    }
  };

  // Send message
  const handleSend = async () => {
    if (!input.trim() || isLoading) return;
    const userText = input.trim();
    setInput('');
    if (textareaRef.current) textareaRef.current.style.height = 'auto';

    if (userText.toLowerCase() === '/clear') return handleClear();

    setMessages(prev => [...prev, { role: 'user', content: userText }]);
    setIsLoading(true);
    setIsThinkingMode(false);

    try {
      const res = await streamChatResponse(
        { user_id: getDeviceId(), message: userText, source: 'web' },
        {
          onLoopThinkingStart: () => {
            setIsThinkingMode(true);
          },
        },
      );

      if (res?.response) {
        setMessages(prev => [...prev, { role: 'chisa', content: res.response }]);
        if (res.emotions) {
          setEmotions(res.emotions);
        }
      } else {
        throw new Error('bad response');
      }
    } catch {
      setMessages(prev => [...prev, { role: 'chisa', content: '*(Lỗi kết nối)* Xin lỗi Senpai... Em đang gặp sự cố, hãy thử lại sau nhé!' }]);
    } finally {
      setIsThinkingMode(false);
      setIsLoading(false);
    }
  };

  const handleKeyDown = e => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend(); }
  };

  return (
    <div className="app-shell">
      <Sidebar onClear={handleClear} emotions={emotions} />

      <div className="chat-panel">
        {/* Header */}
        <header className="chat-header">
          <span className="chat-header-title">Cuộc trò chuyện</span>
          <div className="chat-header-badge">
            <Zap size={11} />
            Chisa AI
          </div>
        </header>

        {/* Messages */}
        <div className="messages-feed">
          {isHistoryLoading ? (
            <div className="history-loading">
              <div className="typing-dot" />
              <div className="typing-dot" />
              <div className="typing-dot" />
            </div>
          ) : (
            messages.map((msg, i) => <Message key={i} msg={msg} />)
          )}

          {isLoading && (
            <div className="msg-row">
              <div className="msg-chisa">
                <img src="/pet_chisa_gif.gif" className="chisa-avatar-img" alt="Chisa" />
                {isThinkingMode ? (
                  <div className="thinking-mode-bubble">
                    <div className="thinking-mode-label">
                      <span className="thinking-mode-icon">⚙️</span>
                      Chisa đang suy luận sâu...
                    </div>
                    <div className="thinking-mode-dots">
                      <div className="thinking-mode-dot" />
                      <div className="thinking-mode-dot" />
                      <div className="thinking-mode-dot" />
                    </div>
                  </div>
                ) : (
                  <div className="typing-indicator">
                    <div className="typing-dot" />
                    <div className="typing-dot" />
                    <div className="typing-dot" />
                  </div>
                )}
              </div>
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>

        {/* Input */}
        <div className="input-area">
          <div className="input-wrapper">
            <textarea
              ref={textareaRef}
              className="chat-input"
              placeholder="Nhắn gì đó với Chisa... (Shift+Enter để xuống dòng)"
              value={input}
              onChange={handleInput}
              onKeyDown={handleKeyDown}
              rows={1}
              disabled={isLoading}
            />
            <button
              className="send-btn"
              onClick={handleSend}
              disabled={!input.trim() || isLoading}
            >
              <Send size={16} />
            </button>
          </div>
          <div className="input-hint">Gõ <code>/clear</code> để xóa ký ức • Shift+Enter để xuống dòng</div>
        </div>
      </div>
    </div>
  );
}
