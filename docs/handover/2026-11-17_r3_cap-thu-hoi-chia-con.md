# Cấp và thu hồi Chía-con (R3)

| | |
|---|---|
| Ngày | 17/11/2026 |
| Người thực hiện | Claude |
| Nhánh | `feat/r3-chia-con-roles` (từ `feat/r3-rbac-core`, PR #108 chưa merge), chưa có PR |
| Yêu cầu | ROLE-001, ROLE-002, ROLE-003, ROLE-006, ROLE-007, MODE-007 (ROLE-004 mới có điểm chặn, ROLE-005 chưa làm) |

## Thay đổi

- **API Admin** (`app/interface/api/routes/admin_roles.py`, gắn ở `/api/v2/admin/accounts`):
  - `GET /{account_id}/summary` đòi `account:read_metadata`; trả ID, email đã che (`s***@domain`), ngày tạo, trạng thái, đã xác minh email chưa, danh tính liên kết. Không có tra cứu theo email hay tên (ROLE-002); ID lạ trả 404 `account_not_found`.
  - `POST /{account_id}/roles/chia-con/grant` đòi `role:chia_con:grant`; body `reason` bắt buộc (1..1000 ký tự, chuỗi trắng bị từ chối 422), `expires_at` tuỳ chọn, phải có múi giờ và nằm ở tương lai.
  - `POST /{account_id}/roles/chia-con/revoke` đòi `role:chia_con:revoke`; body `reason` bắt buộc; thu hồi khi không có gì để thu hồi trả `revoked: false`.
  - Lỗi dùng một dạng `detail: {"code": ...}`. Member và Chía-con gọi grant/revoke nhận 403 (ROLE-001).
- **Điều kiện cấp (ROLE-003)** trong `AuthzService.grant_chia_con`: hàm thuần `grant_rejection` ở miền trả `account_not_active` hoặc `identity_not_verified` (HTTP 409). "Danh tính đã xác minh" là email đã xác minh hoặc có liên kết Google (liên kết chỉ tạo sau khi nhà cung cấp được xác thực). "Không phải vãng lai": khách không có hàng trong `accounts` nên cấp theo ID luôn ra 404, không cần mã riêng.
- **Hết hạn (ROLE-006):** `RoleExpirySweeper` (`app/application/security/role_expiry.py`) chạy mỗi 60 s trong tiến trình `app/worker.py`. Một câu `UPDATE ... RETURNING` thu hồi mọi phân công quá hạn với `revoked_by = system:expiry`, rồi mỗi tài khoản bị ảnh hưởng được tăng `authz_ver`, xoá cache và ghi audit. Nhiều worker chạy song song vẫn an toàn vì mỗi hàng chỉ bị thu hồi một lần.
- **Hạ chế độ (ROLE-007, MODE-007):** thêm `DowngradeReason.ROLE_REVOKED`. `resolve_mode` trả `role_revoked` khi thread đang ở `agentic` (không có override ở tin nhắn) mà người dùng mất `chat:agentic`; mọi trường hợp còn lại vẫn là `not_entitled`. Sự kiện `turn.started` có thêm trường `notice` là hằng số giọng Chisa (`AGENTIC_NOT_ENTITLED_NOTICE`, `AGENTIC_ROLE_REVOKED_NOTICE` trong `chisa_voice.py`), `null` khi không hạ. Lượt chạy `advanced` nên không tốn CU Agentic.
- **Audit:** chưa có kho `admin_audit_events` (SEC-ADM-007). Port `IRoleAuditSink` ở miền, cài đặt tạm `LoggingRoleAuditSink` ghi sự kiện có cấu trúc `role_audit` (hành động, actor, tài khoản, vai trò, lý do, thời điểm, `authz_ver` sau). Không ghi email. Khi kho audit có, chỉ cần thay cài đặt.
- **Điểm chặn ROLE-004:** `require_step_up_mfa` trong `security.py` được gắn vào cả grant và revoke, hiện không làm gì và có `TODO(ROLE-004)`; service cũng đánh dấu cùng TODO. Không tự dựng MFA.
- OpenAPI `docs/api/openapi.json` đã xuất lại (chỉ thêm 3 route và schema).
- Test: tách `tests/unit/security/authz_fakes.py` dùng chung cho `test_rbac_core.py` và `test_chia_con_admin.py`.

## Quyết định

- **Không dùng hàng đợi bền cho job hết hạn.** `durable_background_jobs.principal_id` có khoá ngoại tới `users` (job hệ thống không có người dùng), và hàng đợi không hỗ trợ hẹn giờ. Tránh thêm migration (việc của tác vụ khác), nên dùng vòng lặp định kỳ trong worker. Vẫn đúng khi mất tiến trình vì trạng thái nằm ở DB và truy vấn đã lọc `expires_at` (ROLE-006 phía đọc).
- Route Admin chưa tách phiên Admin (SEC-ADM-003/004): hiện dựa vào `require_permission` trên token chat có `authz_ver`.
- `role_revoked` chỉ suy ra từ thread đang `agentic`; nếu sau này lưu lịch sử quyền thì có thể chính xác hơn.

## Kiểm tra

| Kiểm tra | Kết quả |
|---|---|
| `pytest tests/unit` | 1520 test đạt |
| ruff trên file đã sửa, `ruff_changed_lines.py` | Đạt |
| mypy trên file app đã sửa | Đạt |
| `lint-imports` | 5 hợp đồng giữ nguyên |
| `export_openapi.py --check` | Đạt |
| Test âm tính | 403 cho member và Chía-con (grant, revoke, summary); thiếu hoặc trắng `reason` bị 422; email chưa xác minh và tài khoản bị khoá bị 409 kèm mã; hết hạn thu hồi đúng, tăng `authz_ver`, ghi audit, bỏ qua phân công còn hạn; lượt bị hạ mang `role_revoked` và `notice` |

## Chưa kiểm tra

- Chưa chạy repository SQL thật (`get_summary`, `revoke_expired`) trên Postgres; mới có fake trong unit test.
- Chưa có test tích hợp cho vòng lặp trong `app/worker.py`.

## Việc còn lại

- ROLE-004: step-up MFA thật (SEC-ADM-006, trả 401 `step_up_required`), phiên Admin tách biệt.
- ROLE-005: thông báo cho người được cấp/thu hồi (chỉ ghi "quản trị viên"). `AccountEmailDispatcher` hiện chỉ gửi email kèm liên kết token; chưa có thông báo trong ứng dụng, cần thêm loại thư và kênh thông báo.
- Kho audit append-only `admin_audit_events` có hash chain (SEC-ADM-007) để thay `LoggingRoleAuditSink`.
- Giao diện Admin Console gọi các route trên; trường `notice` của `turn.started` cần được frontend hiển thị.
