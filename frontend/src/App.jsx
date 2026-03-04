import { useState, useRef, useEffect } from 'react';
import axios from 'axios';
import { Send, MessageSquare, Trash2, Zap } from 'lucide-react';
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

// ── Sidebar ──────────────────────────────────────────────────────────────
function Sidebar({ onClear }) {
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
    setMessages(prev => [...prev, { role: 'user', content: '/clear' }]);
    setIsLoading(true);
    try {
      const res = await axios.delete(`${BASE}/chat/clear/${getDeviceId()}`);
      setMessages([{ role: 'chisa', content: `🌸 ${res.data?.message || 'Ký ức đã được xóa!'}` }]);
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
    try {
      const res = await axios.post(`${BASE}/chat`, { user_id: getDeviceId(), message: userText });
      if (res.data?.response) {
        setMessages(prev => [...prev, { role: 'chisa', content: res.data.response }]);
      } else throw new Error('bad response');
    } catch {
      setMessages(prev => [...prev, { role: 'chisa', content: '*(Lỗi kết nối)* Xin lỗi Senpai... Em đang gặp sự cố, hãy thử lại sau nhé!' }]);
    } finally {
      setIsLoading(false);
    }
  };

  const handleKeyDown = e => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend(); }
  };

  return (
    <div className="app-shell">
      <Sidebar onClear={handleClear} />

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
                <div className="typing-indicator">
                  <div className="typing-dot" />
                  <div className="typing-dot" />
                  <div className="typing-dot" />
                </div>
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
