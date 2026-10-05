// Web identity client: registered accounts (email/password, Google) with an
// anonymous-session fallback. Identity is always issued by the server; the browser
// never chooses a user ID.
//
// - Access tokens live only in memory/sessionStorage and are short-lived.
// - The account refresh secret is an HttpOnly cookie the page cannot read.
// - Every cookie-bearing auth call sends X-Chisa-Client (CSRF guard enforced by the API).

const BASE = import.meta.env.VITE_API_BASE_URL ?? '/api/v1';
const ANON_STORAGE_KEY = 'chisa_web_session_v1';
const CLIENT_HEADERS = { 'X-Chisa-Client': 'web' };
const REFRESH_MARGIN_MS = 60_000;

const withExpiry = (data, extra = {}) => ({
  access_token: data.access_token,
  subject_id: data.subject_id,
  expires_at: Date.now() + Math.max(1, Number(data.expires_in || 60)) * 1000,
  account: null,
  ...extra,
});

async function readError(response) {
  try {
    const body = await response.json();
    if (typeof body?.detail === 'string') return body.detail;
  } catch {
    // ignore malformed error bodies
  }
  return `HTTP ${response.status}`;
}

async function anonymousSession() {
  const existing = sessionStorage.getItem(ANON_STORAGE_KEY);
  const request = (token) => fetch(`${BASE}/auth/anonymous-session`, {
    method: 'POST',
    headers: token ? { authorization: `Bearer ${token}` } : {},
  });

  let response = existing ? await request(existing) : null;
  if (!response || !response.ok) {
    sessionStorage.removeItem(ANON_STORAGE_KEY);
    response = await request(null);
  }
  if (!response.ok) throw new Error(`Unable to establish web session (${response.status})`);
  const data = await response.json();
  sessionStorage.setItem(ANON_STORAGE_KEY, data.access_token);
  return withExpiry(data, { kind: 'anonymous' });
}

async function postAuth(path, body, extraHeaders = {}) {
  const response = await fetch(`${BASE}/auth/${path}`, {
    method: 'POST',
    credentials: 'same-origin',
    headers: {
      ...CLIENT_HEADERS,
      ...extraHeaders,
      ...(body ? { 'content-type': 'application/json' } : {}),
    },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!response.ok) {
    const error = new Error(await readError(response));
    error.status = response.status;
    throw error;
  }
  return response.json();
}

async function accountRequest(path, body, extraHeaders = {}) {
  const data = await postAuth(path, body, extraHeaders);
  return withExpiry(data, { kind: 'account', account: data.account });
}

// Refresh tokens rotate on every use, so concurrent refreshes with the same cookie
// would make all but one fail (and the failing response clears the cookie). Calls
// are single-flighted within a tab and serialized across tabs via Web Locks.
let refreshInFlight = null;

export function refreshAccountSession() {
  if (!refreshInFlight) {
    const run = () => accountRequest('refresh').catch(() => null);
    const locked = navigator.locks?.request
      ? navigator.locks.request('chisa-account-refresh', run)
      : run();
    refreshInFlight = locked.finally(() => {
      refreshInFlight = null;
    });
  }
  return refreshInFlight;
}

// On page load: restore an account session from the refresh cookie if present,
// otherwise fall back to (or rotate) the anonymous browser session.
export async function bootstrapSession() {
  const account = await refreshAccountSession();
  return account ?? anonymousSession();
}

// Returns a session whose access token is valid for at least REFRESH_MARGIN_MS.
// An expired/revoked account session degrades to anonymous with `expired: true`.
export async function ensureFreshSession(session) {
  if (session && session.expires_at - Date.now() > REFRESH_MARGIN_MS) return session;
  if (session?.kind === 'account') {
    const refreshed = await refreshAccountSession();
    if (refreshed) return refreshed;
    const anonymous = await anonymousSession();
    return { ...anonymous, expired: true };
  }
  return anonymousSession();
}

// Login fails with status 403 while the e-mail is not verified yet.
export const login = (email, password) => accountRequest('login', { email, password });
// Registration never signs in: the server always answers 202 and e-mails the address.
export const register = (email, password) => postAuth('register', { email, password });
export const resendVerification = (email) => postAuth('verify-email/resend', { email });
export const forgotPassword = (email) => postAuth('password/forgot', { email });
export const verifyEmail = (token) => postAuth('verify-email', { token });
export const resetPassword = (token, newPassword) =>
  postAuth('password/reset', { token, new_password: newPassword });
export const changePassword = (accessToken, currentPassword, newPassword) =>
  accountRequest(
    'password/change',
    { current_password: currentPassword, new_password: newPassword },
    { authorization: `Bearer ${accessToken}` },
  );

// E-mailed links carry their secret in the URL fragment (#verify-email=… or
// #reset-password=…), which browsers never send to servers. Read it once and
// remove it from the address bar and history before doing anything else.
export function consumeAuthFragment() {
  const { hash } = window.location;
  if (!/^#(verify-email|reset-password)=/.test(hash)) return null;
  const match = /^#(verify-email|reset-password)=([A-Za-z0-9_-]{16,256})$/.exec(hash);
  const url = new URL(window.location.href);
  window.history.replaceState({}, '', `${url.pathname}${url.search}`);
  if (!match) return null;
  return { action: match[1], token: match[2] };
}

export async function logout() {
  await fetch(`${BASE}/auth/logout`, {
    method: 'POST',
    credentials: 'same-origin',
    headers: CLIENT_HEADERS,
  }).catch(() => {});
  return anonymousSession();
}

export async function fetchCapabilities() {
  try {
    const response = await fetch(`${BASE}/auth/capabilities`);
    if (response.ok) return await response.json();
  } catch {
    // capabilities are optional UI hints
  }
  return { password: true, password_registration: false, google: false };
}

// Starts Google sign-in (intent "login") or linking (intent "link", requires an
// account access token). The browser is then sent to Google's consent screen.
export async function startGoogle(intent = 'login', accessToken = null) {
  const headers = { ...CLIENT_HEADERS, 'content-type': 'application/json' };
  if (intent === 'link' && accessToken) headers.authorization = `Bearer ${accessToken}`;
  const response = await fetch(`${BASE}/auth/google/start`, {
    method: 'POST',
    credentials: 'same-origin',
    headers,
    body: JSON.stringify({ intent }),
  });
  if (!response.ok) throw new Error(await readError(response));
  const { authorization_url: url } = await response.json();
  window.location.assign(url);
}

const OAUTH_ERRORS = {
  link_required:
    'Email Google này đã thuộc một tài khoản có mật khẩu. Hãy đăng nhập bằng email/mật khẩu rồi chọn "Liên kết Google".',
  rejected: 'Không thể dùng tài khoản Google này (email chưa xác minh hoặc đã liên kết nơi khác).',
  session: 'Phiên liên kết không khớp. Hãy đăng nhập lại rồi thử liên kết Google.',
  cancelled: 'Đăng nhập Google đã bị hủy.',
  expired: 'Phiên đăng nhập Google đã hết hạn, hãy thử lại.',
  state: 'Yêu cầu đăng nhập Google không hợp lệ, hãy thử lại.',
  failed: 'Không xác minh được tài khoản Google, hãy thử lại.',
  unavailable: 'Đăng nhập Google chưa được bật trên máy chủ.',
  claim_email:
    'Email Google này đang bị giữ bởi một tài khoản chưa xác minh. Hãy dùng "Quên mật khẩu" với email này để chứng minh quyền sở hữu, rồi đăng nhập và liên kết Google.',
};

// Reads and removes ?auth= / ?auth_error= left by the Google callback redirect.
export function consumeOAuthRedirect() {
  const url = new URL(window.location.href);
  const success = url.searchParams.get('auth');
  const error = url.searchParams.get('auth_error');
  if (!success && !error) return null;
  url.searchParams.delete('auth');
  url.searchParams.delete('auth_error');
  window.history.replaceState({}, '', `${url.pathname}${url.search}${url.hash}`);
  if (error) return { type: 'error', text: OAUTH_ERRORS[error] || 'Đăng nhập Google thất bại.' };
  return { type: 'success', text: 'Đăng nhập Google thành công.' };
}
