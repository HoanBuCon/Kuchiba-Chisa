# Job trích xuất trí nhớ cho v2

| | |
|---|---|
| Ngày | 15/11/2026 |
| Người thực hiện | Claude, bước 4 của [thiết kế mục tiêu](../design/target-architecture.md) |
| Nhánh | `feat/r2-v2-memory-jobs` (từ `HBC` tại `f328ad6`) |

## Hiện tượng

Lượt chat v2 không tạo job nền nào, nên trí nhớ dài hạn của người dùng trên v2 không bao giờ lớn lên: tụt so với v1.

## Thay đổi

- Loại job mới `thread_memory_extraction.v1`. Payload chỉ chứa id người dùng, thread và lượt; worker tự đọc nội dung từ `thread_turns`, nên hàng đợi không giữ nội dung chat.
- **Outbox (REL-004, REL-007):** job được ghi trong cùng giao dịch với lượt chat ở `PostgresTurnCommit`. Lượt gửi lại không tạo job thứ hai.
- Chỉ lượt ở làn companion của người dùng không phải khách mới tạo job.
- `ThreadMemoryExtractionJobHandler` ở worker: kiểm tra consent lúc chạy, chỉ đọc lượt thuộc đúng chủ, rồi gọi `MemoryExtractor` sẵn có kèm 5 lượt trước làm ngữ cảnh.

## Quyết định

- Trí nhớ lưu theo cùng id mà recall của v2 dùng để lọc (UUID chuẩn hoá của người dùng), để ghi vào là tìm lại được.
- Làn tra cứu không tạo job: câu hỏi lore hiếm khi chứa dữ kiện về người dùng, và mỗi job tốn một lời gọi LLM.
- Dùng lại `MemoryExtractor` của v1 (lọc PII, ngưỡng importance) thay vì viết mới.

## Kiểm tra

| Kiểm tra | Kết quả |
|---|---|
| `make test-isolated` | 1320 test đạt; mypy, import-linter, OpenAPI đạt |
| Test tích hợp trên Postgres | Job được ghi đúng một lần cùng lượt; worker đọc đúng lượt và lịch sử; không consent hoặc sai chủ thì không trích xuất |
| Lint như CI | Đạt |

## Chưa kiểm tra

- **Chưa chạy đầu cuối với LLM thật:** chưa xác nhận một dữ kiện nói ở v2 được trích xuất, lưu vào Qdrant rồi được recall ở lượt sau.
- Chưa chạy worker thật xử lý loại job này.

## Việc còn lại

- Summary cuộn và cửa sổ cắt theo token (CONV-002, CONV-003); job hợp nhất core memory (MEM-005); reflection (MEM-010).
- Người dùng Discord cũ có trí nhớ v1 lưu theo `discord_id`, khác id mà v2 dùng. Dữ liệu trước v2 đã xoá nên hiện không ảnh hưởng, nhưng phải thống nhất trước khi gỡ v1.
- Dữ kiện về người dùng nói trong làn tra cứu sẽ không được ghi nhớ.
