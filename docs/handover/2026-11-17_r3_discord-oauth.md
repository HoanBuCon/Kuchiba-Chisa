# Đăng nhập, liên kết Discord và giải danh tính bot (R3)

| | |
|---|---|
| Ngày | 17/11/2026 |
| Người thực hiện | Claude |
| Nhánh | `feat/r3-discord-oauth` (từ `feat/r3-rbac-core`, PR #108 chưa merge), chưa có PR |
| Yêu cầu | IAM-005, IAM-006, IAM-009 (SEC liên quan: chống chiếm tài khoản qua email chưa xác minh, CSRF/PKCE cho OAuth) |

## Thay đổi

- **Đăng nhập Discord (IAM-005):** `POST /api/v1/auth/discord/start` và `GET /api/v1/auth/discord/callback`, dựng theo luồng Google: giao dịch OAuth gắn với trình duyệt (cookie ký, `state` + PKCE S256), scope `identify email`, đổi mã ở phía máy chủ rồi đọc `/users/@me`. Discord là OAuth2 thuần nên không có ID token và không có nonce; `state` và PKCE gánh vai trò chống CSRF và chống chèn mã. Adapter ở `app/infrastructure/security/discord_oauth.py`.
- **Quy tắc email:** chỉ tin email khi Discord trả `verified` đúng bằng `true`. Nếu không, tài khoản `member` vẫn được tạo và đăng nhập, nhưng email **không được lưu** và tài khoản ở trạng thái chưa xác minh, nên không chiếm được địa chỉ của ai. Email Discord đã xác minh mà trùng tài khoản có sẵn thì không gộp: trả `link_required` (tài khoản giữ email đã xác minh) hoặc `claim_email` (tài khoản giữ email chưa xác minh), đúng như luồng Google.
- **Liên kết tường minh (IAM-006):** dùng lại luồng `intent: "link"` của Google cho Discord (phải có access token của tài khoản, cookie refresh phải cùng phiên). Một danh tính ngoài chỉ thuộc một tài khoản (ràng buộc duy nhất sẵn có của `account_identities`); liên kết danh tính đã thuộc tài khoản khác bị từ chối. Mới: `DELETE /api/v1/auth/identities/{google|discord}` huỷ liên kết; trả 409 nếu đó là phương thức đăng nhập cuối. Mật khẩu chỉ được tính là một phương thức khi email đã xác minh (không thì không đăng nhập được). Khoá hàng tài khoản (`SELECT ... FOR UPDATE`) để hai lần huỷ đồng thời không để lại 0 phương thức.
- **Bot (IAM-009):** workload credential vẫn chỉ mang `discord_user_id` (là `sub`). `get_effective_permissions` giờ gọi `AuthzService.permissions_for_discord_user`: tra `account_identities(provider='discord')`; chưa liên kết thì quyền `guest`; đã liên kết thì quyền do DB tính cho tài khoản đó (cùng cache và quy tắc khoá/thu hồi như IAM-002/010). Token của bot không có đường nào để khai vai trò.
- **Cấu hình:** `DISCORD_OAUTH_CLIENT_ID`, `DISCORD_OAUTH_CLIENT_SECRET`, `DISCORD_OAUTH_REDIRECT_URI`, `DISCORD_OAUTH_TIMEOUT_SECONDS`; mặc định rỗng, bật khi đủ ba giá trị đầu. Production bắt buộc redirect `https://` và cấm giá trị mẫu cho secret. `GET /auth/capabilities` có thêm `discord`. Đã ghi tên biến vào `.env.example`. Giới hạn tốc độ đã bao hai route mới. Hợp đồng `docs/api/openapi.json` đã xuất lại và `--check` đạt.

## Quyết định

- **Không thêm migration.** `account_identities` đã có `provider` kiểu chuỗi, hai ràng buộc duy nhất (provider+subject, account+provider) và `auth_method` đủ rộng; chỉ mở rộng kiểu `Literal` ở miền. Đầu migration vẫn là `c4d7a1e92b58`, test DB-01 không đổi.
- Cookie giao dịch OAuth tách theo đường dẫn (`/api/v1/auth/google`, `/api/v1/auth/discord`), nên giao dịch của nhà cung cấp này không tới được callback của nhà cung cấp kia (có test).
- Người dùng Discord đã liên kết nhận **quyền** của tài khoản (kể cả `chat:agentic` nếu có Chía-con) nhưng vẫn chat dưới chủ thể Discord; `ensure_workload_target_allowed` vẫn cấm bot nhắm vào chủ thể là tài khoản web. Tài khoản bị khoá thì người dùng Discord liên kết không có quyền nào (chặt hơn khách chưa liên kết).
- Chưa thu hồi access token Discord sau khi dùng (token chỉ sống trong một request, không lưu, không log); ghi nhận để cân nhắc gọi `/oauth2/token/revoke`.

## Kiểm tra

| Kiểm tra | Kết quả |
|---|---|
| `pytest tests/unit` | 1528 test đạt (37 test mới: adapter với HTTP giả, chính sách tài khoản, luồng HTTP, giải danh tính bot) |
| ruff trên file đã sửa | Không có lỗi mới (còn nợ cũ trong `settings.py`, `dependencies.py` nằm ngoài phạm vi) |
| mypy trên file app đã sửa | Đạt |
| `lint-imports` | 5 hợp đồng giữ nguyên |
| `export_openapi.py --check` | PASS |
| Test âm tính | Sai `state` bị từ chối; email Discord chưa xác minh không được tin hay lưu; email xác minh trùng không gộp; danh tính của tài khoản khác không liên kết được; không huỷ được phương thức cuối; cookie Google không dùng được ở callback Discord; bot với `discord_user_id` chưa liên kết chỉ có quyền khách; đã liên kết thì ra đúng quyền tài khoản |

Không gọi Discord thật trong test.

## Chưa kiểm tra

- Chưa chạy với ứng dụng Discord thật (cần Client ID/Secret và redirect hợp lệ); chưa test tích hợp Postgres cho `unlink_external_identity` và khoá hàng.
- Frontend chưa có nút "Đăng nhập/Liên kết Discord" và "Huỷ liên kết" (`frontend/src/auth.js` mới có Google); `auth_error` mới chỉ là các mã đã có.

## Việc còn lại

- **Chủ dự án cần cấu hình:** trong Discord Developer Portal, mục OAuth2, thêm Redirect `https://<miền công khai>/api/v1/auth/discord/callback` (khớp từng ký tự với `DISCORD_OAUTH_REDIRECT_URI`); đặt ba biến `DISCORD_OAUTH_CLIENT_ID`, `DISCORD_OAUTH_CLIENT_SECRET`, `DISCORD_OAUTH_REDIRECT_URI` trong cấu hình bí mật của môi trường triển khai.
- Giao diện web cho đăng nhập, liên kết, huỷ liên kết Discord; lệnh `/link` của bot trỏ người dùng tới trang liên kết (CH-001..005).
- IAM-008 (hỏi chuyển thread khi vãng lai đăng nhập) chưa nằm trong lát cắt này.
