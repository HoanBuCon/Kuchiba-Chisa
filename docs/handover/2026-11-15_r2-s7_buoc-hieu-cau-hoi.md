# Bước hiểu câu hỏi (ADV-003)

| Mục | Nội dung |
|---|---|
| Ngày | 15/11/2026 |
| Người thực hiện | Claude (code do subagent Sonnet viết, Claude review) |
| Nhánh | `feat/r2-question-understanding` |
| PR | chưa mở |

## Thay đổi

- **Một lời gọi LLM thay cho bước dịch** trong lượt chat v2.
  - Đầu vào: tin nhắn và 2 lượt trước. Mỗi câu trả lời trước được cắt còn 400 ký tự.
  - Đầu ra: làn (`advanced` hoặc `companion`) và một câu hỏi tiếng Anh độc lập.
  - Câu nối tiếp như "Còn cô ấy học ở đâu?" giữ được chủ thể khi truy xuất.
- **Mã nguồn:**
  - Cổng `IQuestionUnderstander` nằm ở `app/domain/services/knowledge/understanding.py`.
  - Bản LLM là `app/infrastructure/knowledge/llm_question_understander.py`.
  - Cache Redis 7 ngày, khoá gồm cả các lượt trước.
- **Truy xuất nhận câu tiếng Anh có sẵn.** `LoreSearchService.search` và `AdvancedRetrieval.retrieve` có thêm tham số `english=`; khi có tham số này thì không gọi bộ dịch nữa. Bộ dịch cũ vẫn dùng khi không có `english=`, ví dụ trong eval truy xuất.
- **`turn.started` mang làn cuối cùng.** Event này giờ phát sau bước hiểu câu hỏi.
- **Lịch sử chỉ đọc một lần mỗi lượt.**

## Quyết định

- **Luật tất định đã chắc là trò chuyện thì không gọi LLM.**
- **LLM chỉ được chuyển câu sang companion khi không có thực thể nào khác Chisa.** Câu hỏi lore mà vào companion thì sẽ được trả lời không có căn cứ.
- **Bước hiểu câu hỏi lỗi:**
  - Giữ làn tất định.
  - Truy xuất bằng chính tin nhắn, không gọi thêm LLM.
  - Ghi `understanding_failed` vào `degraded`.
- **Ngân sách vẫn tối đa 2 lời gọi** (ADV-009): bước hiểu câu hỏi và Composer.

## Kiểm tra

| Kiểm tra | Kết quả |
|---|---|
| Test mới | 13 test cho bộ hiểu câu hỏi, 7 test cho lượt chat, 1 test cho `english=` |
| pytest unit (không có service) | 1328 đạt. 27 test lỗi sẵn có trên `HBC` (cần service ngoài), không do thay đổi này |
| ruff, lint-imports, changed-lines, debt ratchet | Đạt |

## Chưa kiểm tra

- Chưa đo với LLM thật.

## Việc còn lại

- Đo golden dev trước và sau, rồi chạy holdout một lần.
- Chưa có metric riêng cho tỷ lệ bỏ qua lời gọi và tỷ lệ trúng cache, mà ADV-003 yêu cầu đo. Tỷ lệ bỏ qua hiện suy ra được từ làn companion.
