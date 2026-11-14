# Đường lưu của lượt chat v2: một giao dịch, khoá thread, hoàn quota

| | |
|---|---|
| Ngày | 15/11/2026 |
| Người thực hiện | Claude, bước 4 của [thiết kế mục tiêu](../design/target-architecture.md) |
| Nhánh | `feat/r2-turn-commit-path` (từ `HBC` tại `107a586`) |

## Thay đổi

- **Một giao dịch (EMO-003, REL-007):** `PostgresTurnCommit` lưu lượt và cập nhật cảm xúc trong cùng một giao dịch. Lượt gửi lại thua cuộc đua thì không lưu và không đổi cảm xúc.
- **Khoá theo thread (MODE-005):** `RedisTurnLock` chỉ cho một lượt chạy trong mỗi thread. Lượt thứ hai nhận `turn.failed` với câu `TURN_BUSY` theo giọng Chisa. Khoá tự hết hạn sau 45 giây, phòng khi worker chết.
- **Hoàn quota (REL-007):** lượt lỗi, lượt bị từ chối vì thread bận và lượt phát lại kết quả cũ đều được hoàn quota. Lượt đã lưu thì giữ nguyên.

## Quyết định

- Port `ITurnCommit` và `ITurnLock` nằm ở tầng domain; hiện thực ở infrastructure, nối ở composition root.
- Không truyền `commit` thì dịch vụ dùng đường lưu cũ (hai bước), để test đơn vị không cần Postgres.
- Outbox cho job trí nhớ chưa nằm trong giao dịch này; sẽ thêm khi làm job cho v2.

## Kiểm tra

| Kiểm tra | Kết quả |
|---|---|
| `make test-isolated` | 1314 test đạt; mypy, import-linter, OpenAPI đạt |
| Test tích hợp trên Postgres | Lượt và cảm xúc lưu cùng nhau; gửi lại cùng lượt trả `False`, cảm xúc không đổi |
| Test đơn vị | Thread bận không tốn gì; khoá được nhả cả khi lượt lỗi; hoàn quota đúng 3 trường hợp |
| Lint như CI | Đạt |

## Chưa kiểm tra

- Khoá Redis đã thử trên Redis dev (5 lời gọi đua nhau, 1 cái giữ được; sai token không nhả được), nhưng chưa thử với hai worker API chạy thật.
- Chưa chạy đầu cuối với LLM thật sau thay đổi này.
- Lượt bị ngắt kết nối giữa chừng (client đóng SSE) không được hoàn quota.

## Việc còn lại

- Ghi outbox trong cùng giao dịch và job trí nhớ, summary cho v2 (MEM-005, CONV-003).
- `turn.completed` vẫn đọc cảm xúc bằng một phiên riêng sau khi lưu.
