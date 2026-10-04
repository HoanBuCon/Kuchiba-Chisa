import { useState } from 'react';
import { LogIn, LogOut, User, X, Link2 } from 'lucide-react';

// Minimal account UI: sidebar status + login/register modal. Reuses existing styles.
export function AccountStatus({ session, capabilities, onOpen, onLogout, onLinkGoogle }) {
  const account = session?.kind === 'account' ? session.account : null;
  if (!account) {
    return (
      <button className="sidebar-item" onClick={onOpen} title="Đăng nhập để giữ ký ức trên mọi thiết bị">
        <LogIn size={14} />
        Đăng nhập / Đăng ký
      </button>
    );
  }
  const hasGoogle = account.providers?.includes('google');
  return (
    <div className="account-status">
      <div className="account-identity" title={account.email || ''}>
        <User size={14} />
        <span className="account-email">{account.email || 'Tài khoản Google'}</span>
      </div>
      {capabilities?.google && !hasGoogle && (
        <button className="sidebar-item" onClick={onLinkGoogle} title="Liên kết tài khoản Google">
          <Link2 size={14} />
          Liên kết Google
        </button>
      )}
      <button className="sidebar-item" onClick={onLogout}>
        <LogOut size={14} />
        Đăng xuất
      </button>
    </div>
  );
}

export function AuthModal({ open, capabilities, onClose, onSubmit, onGoogle }) {
  const [mode, setMode] = useState('login');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  if (!open) return null;

  const submit = async (event) => {
    event.preventDefault();
    setError('');
    setBusy(true);
    try {
      await onSubmit(mode, email, password);
      setPassword('');
    } catch (err) {
      setError(err?.message || 'Không thể xử lý yêu cầu.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="auth-backdrop" role="dialog" aria-modal="true" aria-label="Tài khoản Chisa">
      <form className="auth-modal" onSubmit={submit}>
        <div className="auth-header">
          <span>{mode === 'login' ? 'Đăng nhập' : 'Tạo tài khoản'}</span>
          <button type="button" className="drawer-close-btn" onClick={onClose} aria-label="Đóng">
            <X size={16} />
          </button>
        </div>
        <label className="auth-label">
          Email
          <input
            className="auth-input"
            type="email"
            autoComplete="email"
            required
            maxLength={254}
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
        </label>
        <label className="auth-label">
          Mật khẩu
          <input
            className="auth-input"
            type="password"
            autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
            required
            minLength={mode === 'register' ? 10 : 1}
            maxLength={72}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </label>
        {mode === 'register' && <div className="auth-hint">Tối thiểu 10 ký tự.</div>}
        {error && <div className="auth-error">{error}</div>}
        <button className="new-chat-btn auth-submit" type="submit" disabled={busy}>
          {busy ? 'Đang xử lý…' : mode === 'login' ? 'Đăng nhập' : 'Đăng ký'}
        </button>
        {capabilities?.google && (
          <button type="button" className="sidebar-item auth-google" onClick={onGoogle} disabled={busy}>
            Tiếp tục với Google
          </button>
        )}
        <button
          type="button"
          className="auth-switch"
          onClick={() => {
            setMode(mode === 'login' ? 'register' : 'login');
            setError('');
          }}
        >
          {mode === 'login' ? 'Chưa có tài khoản? Đăng ký' : 'Đã có tài khoản? Đăng nhập'}
        </button>
        <div className="auth-hint">
          Khi đăng nhập, Chisa dùng ký ức của tài khoản. Ký ức của phiên ẩn danh hiện tại không được
          chuyển sang tài khoản.{' '}
          <a href="/privacy.html" target="_blank" rel="noopener noreferrer">
            Thông báo quyền riêng tư
          </a>
        </div>
      </form>
    </div>
  );
}
