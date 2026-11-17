# Audit chỉ ghi thêm cho thay đổi vai trò (R3)

| | |
|---|---|
| Ngày | 17/11/2026 |
| Người thực hiện | Claude |
| Nhánh | `feat/r3-admin-audit` (từ `feat/r3-chia-con-roles`, PR #110 chưa merge), chưa có PR |
| Yêu cầu | SEC-ADM-007, SEC-ADM-008 (một phần) |

## Thay đổi

- **Bảng `admin_audit_events`** (migration `d5e2b8f4a173`, nối sau `c4d7a1e92b58`): `seq` (identity), `actor` (ID tài khoản hoặc `system:expiry`), `action`, `target` (`account:<uuid>`), `reason`, `request_id`, `created_at`, `detail` (JSONB: `role`, `expires_at`, `authz_ver_after`), `prev_hash`, `hash` (duy nhất).
- **Hash chain** (`app/domain/services/audit_chain.py`, thuần miền): `hash = SHA-256(prev_hash | JSON chuẩn hoá các trường)`, dòng đầu nối với `GENESIS_HASH` (64 số 0). JSON chuẩn hoá sắp khoá, bỏ khoảng trắng, thời gian quy về UTC.
- **Chặn sửa ở tầng DB:** hàm `admin_audit_events_reject_change()` cùng trigger `BEFORE UPDATE OR DELETE` (theo dòng) và `BEFORE TRUNCATE` (theo câu lệnh), đều `RAISE EXCEPTION`. Dùng trigger vì role ứng dụng sở hữu bảng nên `REVOKE` không ràng buộc được nó.
- **`PostgresRoleAuditSink`** (`app/infrastructure/security/postgres_role_audit.py`) thay `LoggingRoleAuditSink` ở `AppContainer.authz_service`. Cổng `IRoleAuditSink.record` nay nhận thêm `session`, và `AuthzService` truyền chính phiên đang dùng, nên dòng audit commit hoặc rollback cùng thay đổi vai trò (cả grant, revoke, và vòng hết hạn của worker). Khoá `pg_advisory_xact_lock` tuần tự hoá người ghi để không hai dòng cùng nối vào một `prev_hash`; khoá nhả khi commit.
- **Kiểm chuỗi:** `verify_admin_audit_chain(session)` duyệt theo `seq` và trả `ChainVerification(checked, first_broken_seq)`; hàm thuần `verify_chain` làm phần so khớp. Phát hiện được sửa nội dung, xoá dòng giữa chuỗi, và sửa kèm tính lại hash (vì dòng sau lệch liên kết).
- **Không PII (MON-013, SEC-ADM-008):** dòng chỉ có ID, hằng số vai trò, lý do do Admin nhập, thời điểm. Không email, không nội dung chat hay bộ nhớ. `RoleAuditEvent` có thêm `request_id` tuỳ chọn.
- `LoggingRoleAuditSink` giữ lại (chữ ký đã đổi) nhưng không còn được nối.

## Quyết định

- **Khoá ghi nối tiếp:** chấp nhận nghẽn nhẹ vì tần suất đổi vai trò rất thấp.
- **Không dùng `REVOKE`:** xem trên. Hạn chế còn lại: chủ bảng vẫn có thể `DROP TRIGGER`; hash chain là lớp phát hiện cho trường hợp đó, và bản sao hằng ngày (bên dưới) là lớp phục hồi.
- `seq` dùng `GENERATED ALWAYS AS IDENTITY`; rollback có thể để lại khoảng trống `seq`, không ảnh hưởng chuỗi vì liên kết dựa vào `hash`, không dựa vào `seq` liền nhau.

## Kiểm tra

| Kiểm tra | Kết quả |
|---|---|
| `pytest tests/unit` | 1552 test đạt |
| ruff trên file đã sửa | Đạt (lỗi E501/F401 cũ ở `dependencies.py` không do thay đổi này) |
| mypy trên file app đã sửa | Đạt |
| `lint-imports` | 5 hợp đồng giữ nguyên |
| Test mới | hash tính đúng và nối dây; sửa dòng, xoá dòng, sửa kèm tính lại hash đều bị verifier báo đúng `seq`; sink ghi đúng trường, không có `@`; migration chứa trigger UPDATE/DELETE/TRUNCATE; head DB-01 pin sang `d5e2b8f4a173` |

## Chưa kiểm tra

- Chưa chạy migration và trigger trên Postgres thật; test hiện ở mức đơn vị (sink dùng phiên giả, trigger kiểm bằng nội dung SQL). Cần test tích hợp: `UPDATE`/`DELETE`/`TRUNCATE` bị từ chối, hai ghi đồng thời không rẽ nhánh chuỗi.

## Việc còn lại

- Endpoint `audit:read` / `audit:export` (export cần step-up MFA) và gọi `verify_admin_audit_chain` từ đó hoặc từ tác vụ định kỳ.
- Xuất bản sao audit hằng ngày vào backup (SEC-ADM-007), chính sách lưu giữ.
- Nạp `request_id` thật từ middleware vào `RoleAuditEvent` (hiện route chưa truyền, cột để trống).
- Các trường còn thiếu của SEC-ADM-008: session, trạng thái trước/sau, hash IP và user-agent.
- Khi merge: tech lead nối lại `down_revision` nếu tác vụ khác cũng nối sau `c4d7a1e92b58`, và cập nhật lại test head DB-01.
