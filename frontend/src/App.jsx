import { useState, useRef, useEffect } from 'react';
import axios from 'axios';
import { Send, MessageSquare, Trash2, Zap, Heart, Smile, Frown, Shield, Plus, X } from 'lucide-react';
import ReactMarkdown from 'react-markdown';

// ── Persistent Device UUID ──────────────────────────────────────────
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

// ── Local Storage Conversation Threads Helper ────────────────────────────
const getStoredConversations = () => {
  try {
    const stored = localStorage.getItem('chisa_conversations');
    if (stored) {
      const parsed = JSON.parse(stored);
      if (Array.isArray(parsed) && parsed.length > 0) return parsed;
    }
  } catch (e) {
    console.error("Failed to read conversations from localStorage:", e);
  }
  const defaultId = getDeviceId();
  const initial = [{ id: defaultId, title: 'Cuộc trò chuyện 1', createdAt: Date.now() }];
  localStorage.setItem('chisa_conversations', JSON.stringify(initial));
  return initial;
};

const saveConversations = (convs) => {
  try {
    localStorage.setItem('chisa_conversations', JSON.stringify(convs));
  } catch (e) {
    console.error("Failed to save conversations to localStorage:", e);
  }
};

const BASE = 'http://localhost:8000/api/v1';
const GREETING = { role: 'chisa', content: 'Chào Senpai~ Em là Chisa đây ♡  Hôm nay Senpai có gì muốn tâm sự với em không?' };

// ── SSE Chat Streaming Handler ───────────────────────────────────────────
async function streamChatResponse(payload, { onLoopThinkingStart, onToken } = {}) {
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
    if (done) break;

    buffer += decoder.decode(value, { stream: true });

    let boundaryIndex = buffer.indexOf('\n\n');
    while (boundaryIndex !== -1) {
      const rawChunk = buffer.slice(0, boundaryIndex).trim();
      buffer = buffer.slice(boundaryIndex + 2);
      boundaryIndex = buffer.indexOf('\n\n');

      if (!rawChunk) continue;

      const { eventName, data } = parseChunk(rawChunk);
      if (eventName === 'loop_thinking_started' && typeof onLoopThinkingStart === 'function') {
        onLoopThinkingStart(data);
      }
      if (eventName === 'token' && typeof onToken === 'function') {
        onToken(data?.token || '');
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

// ── Message Component ───────────────────────────────────────────────────
function Message({ msg }) {
  if (msg.role === 'user') {
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

// ── Emotion Panel Component ──────────────────────────────────────────────
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
      <div className="sidebar-section-label" style={{ padding: 0 }}>Chỉ số cảm xúc</div>
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

// ── Sidebar Component (Conversation Management: Add & Delete Threads) ───
function Sidebar({ 
  conversations, 
  activeSessionId, 
  onSelectSession, 
  onCreateSession, 
  onDeleteSession, 
  onClearMemory 
}) {
  return (
    <aside className="sidebar">
      <div className="sidebar-logo">
        <div className="logo-icon">
          <img src="/dance_chisa.gif" alt="Chisa" style={{ width: '100%', height: '100%', objectFit: 'cover', borderRadius: '8px' }} />
        </div>
        <span className="logo-text">CHISA<span className="logo-dot">.</span>AI</span>
      </div>

      <button className="new-chat-btn" onClick={onCreateSession} title="Tạo cuộc trò chuyện mới">
        <Plus size={16} />
        <span>Cuộc trò chuyện mới</span>
      </button>

      <span className="sidebar-section-label">Đoạn hội thoại ({conversations.length})</span>

      <div className="conv-list">
        {conversations.map(conv => {
          const isActive = conv.id === activeSessionId;
          return (
            <div 
              key={conv.id} 
              className={`conv-item ${isActive ? 'active' : ''}`}
              onClick={() => onSelectSession(conv.id)}
            >
              <div className="conv-item-left">
                <MessageSquare size={14} className="conv-icon" />
                <span className="conv-title">{conv.title}</span>
              </div>
              <button 
                className="conv-delete-btn" 
                onClick={(e) => onDeleteSession(e, conv.id)}
                title="Xóa đoạn hội thoại"
              >
                <Trash2 size={13} />
              </button>
            </div>
          );
        })}
      </div>

      <div className="sidebar-spacer" />

      <div className="sidebar-footer">
        <button
          className="sidebar-item"
          onClick={onClearMemory}
          title="Xóa toàn bộ ký ức của hội thoại hiện tại"
          style={{ color: '#c62828' }}
        >
          <Trash2 size={14} />
          Xóa ký ức hội thoại
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
  const [conversations, setConversations]   = useState(getStoredConversations);
  const [activeSessionId, setActiveSessionId] = useState(() => conversations[0]?.id || getDeviceId());
  const [messages, setMessages]             = useState([]);
  const [input, setInput]                   = useState('');
  const [isLoading, setIsLoading]           = useState(false);
  const [isThinkingMode, setIsThinkingMode] = useState(false);
  const [streamedText, setStreamedText]     = useState('');
  const [emotions, setEmotions]             = useState({ joy: 0.5, sadness: 0.0, trust: 0.5, irritation: 0.0, attachment: 0.0 });
  const [isHistoryLoading, setIsHistoryLoading] = useState(true);
  const [isEmotionOpen, setIsEmotionOpen]   = useState(false);

  const messagesEndRef = useRef(null);
  const textareaRef    = useRef(null);

  const scrollToBottom = () =>
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });

  // Fetch history & emotions whenever activeSessionId changes
  useEffect(() => {
    setIsHistoryLoading(true);
    
    // Fetch History
    axios.get(`${BASE}/chat/history/${activeSessionId}?limit=50`)
      .then(res => {
        const hist = res.data?.history || [];
        setMessages(hist.length
          ? hist.map(m => ({ role: m.role === 'assistant' ? 'chisa' : m.role, content: m.content }))
          : [GREETING]
        );
      })
      .catch(() => setMessages([GREETING]))
      .finally(() => setIsHistoryLoading(false));

    // Fetch Emotions
    axios.get(`${BASE}/chat/emotions/${activeSessionId}`)
      .then(res => {
        if (res.data) setEmotions(res.data);
      })
      .catch(console.error);
  }, [activeSessionId]);

  useEffect(() => { scrollToBottom(); }, [messages, isLoading]);

  // Auto-grow textarea
  const handleInput = e => {
    setInput(e.target.value);
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 180)}px`;
    }
  };

  // Create a new conversation thread
  const handleCreateNewChat = () => {
    const newId = `chisa-conv-${Date.now()}-${Math.random().toString(36).substring(2, 7)}`;
    const newTitle = `Cuộc trò chuyện ${conversations.length + 1}`;
    const newConv = { id: newId, title: newTitle, createdAt: Date.now() };

    const updated = [newConv, ...conversations];
    setConversations(updated);
    saveConversations(updated);
    setActiveSessionId(newId);
    setEmotions({ joy: 0.5, sadness: 0.0, trust: 0.5, irritation: 0.0, attachment: 0.0 });
  };

  // Select a conversation thread
  const handleSelectSession = (id) => {
    if (id === activeSessionId) return;
    setActiveSessionId(id);
  };

  // Delete a conversation thread (Wipes backend memory + removes from local session list)
  const handleDeleteSession = async (e, id) => {
    e.stopPropagation();
    if (!window.confirm("Senpai có chắc chắn muốn xóa đoạn hội thoại này không?")) {
      return;
    }

    try {
      await axios.delete(`${BASE}/chat/clear/${id}`).catch(console.error);
    } catch {
      // Ignore backend delete errors if network issue
    }

    const filtered = conversations.filter(c => c.id !== id);
    if (filtered.length === 0) {
      // If deleted the last conversation, generate a fresh new one
      const freshId = `chisa-conv-${Date.now()}`;
      const freshConv = [{ id: freshId, title: 'Cuộc trò chuyện 1', createdAt: Date.now() }];
      setConversations(freshConv);
      saveConversations(freshConv);
      setActiveSessionId(freshId);
    } else {
      setConversations(filtered);
      saveConversations(filtered);
      if (id === activeSessionId) {
        setActiveSessionId(filtered[0].id);
      }
    }
  };

  // Clear memory for current session
  const handleClearMemory = async () => {
    if (!window.confirm("Senpai có chắc chắn muốn xóa đi mọi kỷ niệm của đoạn hội thoại này không?")) {
      return;
    }
    setMessages(prev => [...prev, { role: 'user', content: '/clear' }]);
    setIsLoading(true);
    try {
      const res = await axios.delete(`${BASE}/chat/clear/${activeSessionId}`);
      setMessages([{ role: 'chisa', content: `🌸 ${res.data?.message || 'Ký ức đã được xóa!'}` }]);
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

    if (userText.toLowerCase() === '/clear') return handleClearMemory();

    // Auto-update conversation title if it's generic ("Cuộc trò chuyện X")
    const currentConv = conversations.find(c => c.id === activeSessionId);
    if (currentConv && currentConv.title.startsWith('Cuộc trò chuyện')) {
      const truncatedTitle = userText.length > 22 ? `${userText.slice(0, 22)}...` : userText;
      const updatedConvs = conversations.map(c => 
        c.id === activeSessionId ? { ...c, title: truncatedTitle } : c
      );
      setConversations(updatedConvs);
      saveConversations(updatedConvs);
    }

    setMessages(prev => [...prev, { role: 'user', content: userText }]);
    setIsLoading(true);
    setIsThinkingMode(false);
    setStreamedText('');

    try {
      const res = await streamChatResponse(
        { user_id: activeSessionId, message: userText, source: 'web' },
        {
          onLoopThinkingStart: () => {
            setIsThinkingMode(true);
          },
          onToken: (token) => {
            setIsThinkingMode(false);
            setStreamedText(prev => prev + token);
          }
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
      setStreamedText('');
    }
  };

  const handleKeyDown = e => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend(); }
  };

  const currentConv = conversations.find(c => c.id === activeSessionId);

  return (
    <div className="app-shell">
      {/* ── Left Sidebar: Conversation Threads ── */}
      <Sidebar 
        conversations={conversations}
        activeSessionId={activeSessionId}
        onSelectSession={handleSelectSession}
        onCreateSession={handleCreateNewChat}
        onDeleteSession={handleDeleteSession}
        onClearMemory={handleClearMemory}
      />

      {/* ── Main Chat Panel ── */}
      <div className="chat-panel">
        {/* Header with Right Side Emotion Toggle */}
        <header className="chat-header">
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <span className="chat-header-title">{currentConv?.title || 'Cuộc trò chuyện'}</span>
            <div className="chat-header-badge">
              <Zap size={11} />
              Chisa AI
            </div>
          </div>

          <button 
            className={`emotion-toggle-btn ${isEmotionOpen ? 'active' : ''}`}
            onClick={() => setIsEmotionOpen(prev => !prev)}
            title="Trạng thái cảm xúc của Chisa"
          >
            <Heart size={14} />
            <span>Cảm xúc Chisa</span>
          </button>
        </header>

        {/* Messages Feed */}
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
                {streamedText ? (
                  <div className="chisa-bubble">
                    <div className="chisa-content">
                      <ReactMarkdown>{streamedText}</ReactMarkdown>
                    </div>
                  </div>
                ) : isThinkingMode ? (
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

        {/* Input Area */}
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

        {/* ── Right Side Emotion Drawer Panel ── */}
        <div 
          className={`emotion-drawer-backdrop ${isEmotionOpen ? 'open' : ''}`}
          onClick={() => setIsEmotionOpen(false)}
        />
        <div className={`emotion-drawer ${isEmotionOpen ? 'open' : ''}`}>
          <div className="drawer-header">
            <div className="drawer-title">
              <Heart size={16} className="drawer-title-icon" />
              <span>Trạng thái cảm xúc</span>
            </div>
            <button className="drawer-close-btn" onClick={() => setIsEmotionOpen(false)}>
              <X size={16} />
            </button>
          </div>
          <div className="drawer-body">
            <div className="sidebar-chisa-art">
              <img src="/chisa_drink.gif" alt="Chisa" className="sidebar-chisa-img" />
            </div>
            <EmotionPanel emotions={emotions} />
          </div>
        </div>
      </div>
    </div>
  );
}
