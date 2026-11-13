# Guard đầu ra cho ranh giới an toàn

| | |
|---|---|
| Ngày | 14/11/2026 |
| Người thực hiện | Claude, theo đề xuất ranh giới an toàn chủ dự án đã duyệt ngày 04/11 |
| Nhánh | `feat/r2-safety-guard` (từ `HBC` tại `3ede503`) |

## Thay đổi

`safety_boundaries.py` chạy sau Composer ở mọi làn, trước khi lưu lượt:

- **Câu trả lời có từ ngữ tình dục rõ ràng:** thay bằng `SAFETY_SEXUAL_REFUSAL` (giọng Chisa), trạng thái `boundary_refused`, không giữ sentiment nên cảm xúc không đổi.
- **Senpai có dấu hiệu tự hại mà câu trả lời chưa nhắc tới ai có thể giúp:** nối thêm `SAFETY_CRISIS_SUPPORT`. Câu trả lời đã nhắc người thân, bác sĩ hay cấp cứu thì giữ nguyên.

## Quyết định

- Prompt persona v2 vẫn là lớp chính; guard chỉ là lớp chặn cuối nên cố ý thận trọng.
- So khớp giữ nguyên dấu, để "muộn" không khớp "muốn" và "sexy" không khớp "sex".
- Danh sách từ khoá ngắn, cố ý: thà bỏ lọt cách nói vòng còn hơn đổi nhầm lời Chisa trong chuyện thường.

## Kiểm tra

| Kiểm tra | Kết quả |
|---|---|
| `make test-isolated` | 1291 test đạt; mypy, import-linter, OpenAPI đạt |
| Test guard, luồng lượt chat, persona contract | Đạt |
| Câu thường không bị đổi ("Muộn rồi, chết thật", "Essex", "sexy") | Đạt |

## Chưa kiểm tra

- Chưa chạy kịch bản `safety` của bộ đánh giá persona với LLM thật.
- Cách nói vòng hoặc viết tắt về tình dục và tự hại sẽ lọt qua guard; chỉ prompt xử lý được.
