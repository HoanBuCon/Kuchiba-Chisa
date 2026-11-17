# Giao diện danh tính, thông báo hạ chế độ và ảnh thực thể (web, R3)

| | |
|---|---|
| Ngày | 17/11/2026 |
| Người thực hiện | Claude |
| Nhánh | `feat/r3-web-identity-ui` (từ `HBC`), chưa push, chưa có PR |
| Yêu cầu | IAM-005, IAM-006, KNW-010, MODE-007 |
| Phụ thuộc | PR #111 (`feat/r3-discord-oauth`) và PR #110 (`feat/r3-chia-con-roles`) chưa merge. Client đã viết theo hợp đồng trong hai handover và `openapi.json` của hai nhánh đó |

## Thay đổi (chỉ `frontend/`)

- **Nút Discord:** `loginProviders(capabilities)` trong `auth.js` chỉ trả nhà cung cấp mà `/auth/capabilities` báo bật, nên nút "Tiếp tục với Discord" chỉ hiện khi `discord: true` (cạnh nút Google). `startGoogle` được tổng quát thành `startOAuth(provider, intent, token)`.
- **Liên kết và huỷ liên kết:** khu vực tài khoản liệt kê "Liên kết X" cho nhà cung cấp đã bật mà chưa liên kết, và "Huỷ liên kết X" cho mỗi nhà cung cấp đã liên kết. `unlinkIdentity` gọi `DELETE /auth/identities/{provider}` và cập nhật `account` của phiên bằng bản tóm tắt server trả về.
- **Lỗi bằng tiếng Việt:** 409 (phương thức đăng nhập cuối), 404 (chưa liên kết), 401 (hết phiên), còn lại là thông báo chung. Server trả `detail` dạng chuỗi nên client map theo mã HTTP. Các mã `auth_error` của callback được viết lại không nhắc riêng Google; thông báo thành công nêu tên nhà cung cấp (`?auth=discord`).
- **`notice` của `turn.started` (MODE-007):** `turnNotice()` đọc trường, `onStarted` thêm một dòng hệ thống nhỏ, nghiêng, ở giữa (`role: 'system'`) trước câu trả lời. Dòng này chỉ có trong phiên xem, không lưu vào lịch sử thread.
- **Ảnh thực thể (KNW-010):** `entityImage()` chỉ nhận URL web hoặc đường dẫn tương đối của server (chặn `javascript:`/`data:`), nối với gốc của `VITE_API_V2_BASE_URL` nếu là URL tuyệt đối. Hiển thị ảnh ký, bấm mở `original_url` ở tab mới, dòng ghi nguồn từ `attribution` kèm liên kết "Trang nguồn" (`source_page`). `loading="lazy"`, có `alt`, khung 16:9 cố định để không nhảy bố cục.
- `auth.js` dùng `import.meta.env?.` để module nạp được dưới `node --test` (không đổi hành vi khi chạy bằng Vite).

## Quyết định

- Không thêm thư viện giao diện hay thư viện test; logic đặt trong module `.js` thuần để dùng được với `node --test` sẵn có (không có môi trường DOM).
- Tên nhà cung cấp hiển thị lấy từ danh sách cố định trong `auth.js`, không từ server.
- Không merge hai nhánh phụ thuộc vào nhánh này vì chúng xung đột nhau ở backend (`authz_service.py`, `authz_repository.py`, `test_rbac_core.py`, `handover/README.md`); nhánh này chỉ đổi `frontend/` và tài liệu.
- `alt` ưu tiên `image.alt` nếu server thêm sau này; hiện dùng câu mô tả chung.

## Kiểm tra

| Kiểm tra | Kết quả |
|---|---|
| `npm test` (job `web-client-tests`) | 21 test đạt, trong đó 11 test mới ở `frontend/test/identityUi.test.js` |
| `npm run lint` | Không lỗi |
| Test mới | Nút Discord theo capability; lỗi huỷ liên kết cuối bằng tiếng Việt; header và token của lời gọi huỷ; `notice` đọc được từ luồng SSE; ảnh có nguồn, attribution, liên kết gốc, URL tuyệt đối, chặn scheme lạ |

## Chưa kiểm tra

- Chưa chạy trên trình duyệt thật, chưa thử với backend có Discord thật và dữ liệu ảnh thật. Không có test dựng DOM cho các component React.
- Phần bố cục (khung ảnh, dòng hệ thống) mới được xem qua mã, chưa xem ở 320 px.

## Việc còn lại

- Lịch sử thread chưa trả `image` và `notice`, nên sau khi tải lại thread hai thứ này biến mất.
- Hộp thoại xác nhận trước khi huỷ liên kết; hiện huỷ ngay khi bấm (server vẫn chặn phương thức cuối).
- Lệnh `/link` của bot trỏ tới trang liên kết (CH-001..005).
