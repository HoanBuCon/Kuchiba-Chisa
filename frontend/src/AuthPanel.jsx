import { useState } from 'react';
import { KeyRound, LogIn, LogOut, User, X, Link2 } from 'lucide-react';

// Minimal account UI: sidebar status + one modal for every account flow.
export function AccountStatus({ session, capabilities, onOpen, onLogout, onLinkGoogle, onChangePassword }) {
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
      {account.has_password && (
        <button className="sidebar-item" onClick={onChangePassword}>
          <KeyRound size={14} />
          Đổi mật khẩu
        </button>
      )}
      <button className="sidebar-item" onClick={onLogout}>
        <LogOut size={14} />
        Đăng xuất
      </button>
    </div>
  );
}

const TITLES = {
  login: 'Đăng nhập',
  register: 'Tạo tài khoản',
  forgot: 'Quên mật khẩu',
  resend: 'Gửi lại email xác minh',
  reset: 'Đặt mật khẩu mới',
  change: 'Đổi mật khẩu',
};

const SUBMIT_LABELS = {
  login: 'Đăng nhập',
  register: 'Đăng ký',
  forgot: 'Gửi liên kết',
  resend: 'Gửi lại',
  reset: 'Lưu mật khẩu',
  change: 'Đổi mật khẩu',
};

export function AuthModal({ open, mode, onModeChange, capabilities, onClose, handlers, onGoogle }) {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [error, setError] = useState('');
  const [info, setInfo] = useState('');
  const [unverified, setUnverified] = useState(false);
  const [busy, setBusy] = useState(false);

  if (!open) return null;

  const canRegister = capabilities?.password_registration;
  const needsEmail = ['login', 'register', 'forgot', 'resend'].includes(mode);
  const needsPassword = ['login', 'register', 'change'].includes(mode);
  const needsNewPassword = ['reset', 'change'].includes(mode);

  const switchMode = (next) => {
    setError('');
    setInfo('');
    setUnverified(false);
    setPassword('');
    setNewPassword('');
    onModeChange(next);
  };

  const submit = async (event) => {
    event.preventDefault();
    setError('');
    setInfo('');
    setUnverified(false);
    setBusy(true);
    try {
      let message = null;
      if (mode === 'login') message = await handlers.login(email, password);
      else if (mode === 'register') message = await handlers.register(email, password);
      else if (mode === 'forgot') message = await handlers.forgot(email);
      else if (mode === 'resend') message = await handlers.resend(email);
      else if (mode === 'reset') message = await handlers.reset(newPassword);
      else if (mode === 'change') message = await handlers.change(password, newPassword);
      setPassword('');
      setNewPassword('');
      if (message) setInfo(message);
    } catch (err) {
      if (mode === 'login' && err?.status === 403) setUnverified(true);
      setError(err?.message || 'Không thể xử lý yêu cầu.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="auth-backdrop" role="dialog" aria-modal="true" aria-label="Tài khoản Chisa">
      <form className="auth-modal" onSubmit={submit}>
        <div className="auth-header">
          <span>{TITLES[mode]}</span>
          <button type="button" className="drawer-close-btn" onClick={onClose} aria-label="Đóng">
            <X size={16} />
          </button>
        </div>
        {needsEmail && (
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
        )}
        {needsPassword && (
          <label className="auth-label">
            {mode === 'change' ? 'Mật khẩu hiện tại' : 'Mật khẩu'}
            <input
              className="auth-input"
              type="password"
              autoComplete={mode === 'register' ? 'new-password' : 'current-password'}
              required
              minLength={mode === 'register' ? 10 : 1}
              maxLength={72}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </label>
        )}
        {needsNewPassword && (
          <label className="auth-label">
            Mật khẩu mới
            <input
              className="auth-input"
              type="password"
              autoComplete="new-password"
              required
              minLength={10}
              maxLength={72}
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
            />
          </label>
        )}
        {(mode === 'register' || needsNewPassword) && <div className="auth-hint">Tối thiểu 10 ký tự.</div>}
        {error && <div className="auth-error">{error}</div>}
        {info && <div className="auth-info">{info}</div>}
        {unverified && canRegister && (
          <button type="button" className="auth-switch" onClick={() => switchMode('resend')}>
            Gửi lại email xác minh
          </button>
        )}
        <button className="new-chat-btn auth-submit" type="submit" disabled={busy}>
          {busy ? 'Đang xử lý…' : SUBMIT_LABELS[mode]}
        </button>
        {mode === 'login' && capabilities?.google && (
          <button type="button" className="sidebar-item auth-google" onClick={onGoogle} disabled={busy}>
            Tiếp tục với Google
          </button>
        )}
        {mode === 'login' && canRegister && (
          <>
            <button type="button" className="auth-switch" onClick={() => switchMode('register')}>
              Chưa có tài khoản? Đăng ký
            </button>
            <button type="button" className="auth-switch" onClick={() => switchMode('forgot')}>
              Quên mật khẩu?
            </button>
          </>
        )}
        {['register', 'forgot', 'resend', 'reset'].includes(mode) && (
          <button type="button" className="auth-switch" onClick={() => switchMode('login')}>
            Quay lại đăng nhập
          </button>
        )}
        {mode === 'login' && (
          <div className="auth-hint">
            Khi đăng nhập, Chisa dùng ký ức của tài khoản. Ký ức của phiên ẩn danh hiện tại không được
            chuyển sang tài khoản.{' '}
            <a href="/privacy.html" target="_blank" rel="noopener noreferrer">
              Thông báo quyền riêng tư
            </a>
          </div>
        )}
      </form>
    </div>
  );
}
