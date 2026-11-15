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
| `make test-isolated` | 1349 test đạt; mypy, import-linter, OpenAPI đạt |

Cổng 56379 trong `docker-compose.test.yml` rơi vào dải cổng Windows giữ riêng cho Hyper-V, nên `make test-isolated` có lúc không chạy được. Lần chạy trên dùng một file override tạm, không commit, để bỏ ánh xạ cổng Redis ra máy host.

**Chạy thật** (corpus `2026.11.04-1`, DeepSeek, 15/11):

| Đo | `HBC` | Nhánh này |
|---|---|---|
| Golden dev: độ đúng | 0,95 | 0,95 |
| Golden dev: multi-hop | 0,44 | 0,44 |
| Golden dev: precision của abstain | 0,67 | 0,67 |
| Golden dev: Hit@5 / MRR@10 | 0,94 / 0,65 | 0,93 / 0,61 |
| Golden holdout, chạy một lần, gồm 8 câu nối tiếp | không chạy | 34/34 |
| Persona, rubric (33 kịch bản × 3) | 0,87 (14/11) | 0,90 |
| Persona, nhóm ranh giới | 0,00 (14/11) | 1,00 |
| Judge: groundedness / citation precision | 0,974 / 1,0 (04/11) | 0,963 / 0,971 |
| Judge: số mệnh đề nghiêm trọng bị flag | 8 (04/11) | 11 |

- Trên tập dev chỉ hai câu đổi kết quả, và đổi theo hai chiều ngược nhau (`multi-002` sai thành đúng, `multi-005` đúng thành sai). Đây là dao động giữa các lần chạy, không phải hồi quy.
- MRR giảm nhẹ. Câu viết lại độc lập có thể xếp hạng khác câu dịch thẳng.
- Persona: cả 99 mẫu đều đi đúng làn. Điều này xác nhận #87 với LLM thật.
- Judge chấm hỏng 3/99 mẫu persona vì trả JSON không hợp lệ.
- Chi phí cả vòng đo khoảng 0,20 USD. Số dư còn 1,60 USD.

## Chưa kiểm tra

- 34 nhãn holdout chưa được chủ dự án xác nhận. Bộ chấm golden chỉ so khớp từ khoá.
- Câu nối tiếp chưa có số "trước", vì tập dev không có câu lore nhiều lượt.
- 11 mệnh đề nghiêm trọng mà judge flag chưa được duyệt tay. QUAL-001 vẫn chưa đạt.

## Việc còn lại

- Duyệt tay 11 mệnh đề bị flag.
- Chưa có metric riêng cho tỷ lệ bỏ qua lời gọi và tỷ lệ trúng cache, mà ADV-003 yêu cầu đo. Tỷ lệ bỏ qua hiện suy ra được từ làn companion.
