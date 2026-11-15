# Cửa sổ cắt theo token và summary cuộn cho thread v2

| | |
|---|---|
| Ngày | 15/11/2026 |
| Người thực hiện | Claude, bước 4 của [thiết kế mục tiêu](../design/target-architecture.md) |
| Nhánh | `feat/r2-thread-summary` (từ `HBC` tại `101c648`), chưa có PR |

## Hiện tượng

Lượt chat v2 luôn đưa 6 lượt gần nhất cho Composer và `summary=None`. Thread dài thì mất ngữ cảnh cũ, còn lượt dài thì tràn ngân sách prompt (CONV-002).

## Thay đổi

- **Cửa sổ theo token (CONV-002):** lịch sử đưa cho Composer là các lượt mới nhất vừa ngân sách `CHAT_HISTORY_TOKEN_BUDGET` (mặc định 1500). Luôn giữ ít nhất lượt cuối. Hàm thuần ở `app/domain/services/conversation_window.py`.
- **Summary có version (CONV-002):** bảng `thread_summaries` (migration `a7d3e9b2c418`), khoá chính là `thread_id`, khoá ngoại `ON DELETE CASCADE` nên xoá thread là xoá summary (CONV-004). Có cột `version` và `covered_turn_id` (lượt cuối đã được tóm).
- **Composer nhận summary ở cả hai làn** (companion và có căn cứ), cùng các lượt sau `covered_turn_id` đã cắt theo token.
- **Job nền `thread_summary.v1` (CONV-003):** `PostgresTurnCommit` ghi job vào outbox trong cùng giao dịch với lượt khi các lượt chưa được tóm, cộng lượt vừa xong, vượt `CHAT_SUMMARY_TRIGGER_TOKENS` (mặc định 1200, thấp hơn cửa sổ 1500). Khoá idempotency là `thread-summary:{thread}:{version summary hiện tại}` (0 nếu chưa có), nên dù backlog vượt ngưỡng qua nhiều lượt thì mỗi version chỉ có một job và một lời gọi LLM. Payload chỉ chứa id; worker tự đọc nội dung. Lượt chat không chờ job.
- **Worker:** `ThreadSummaryJobHandler` kiểm tra consent như job trí nhớ (`ensure_consent`; rút consent thì ném `DurableJobPayloadError`, không tóm), đọc summary hiện tại và các lượt chưa tóm của đúng chủ thread, gọi `LlmThreadSummarizer` (qua LLM gateway, `LLMPurpose.CONVERSATION_SUMMARY`) để gộp summary cũ với lượt mới thành đoạn tiếng Việt ngắn, rồi ghi bằng `UPDATE ... WHERE version = cũ` (chưa có thì `INSERT ... ON CONFLICT DO NOTHING`). Thua cuộc đua thì bỏ qua, không ghi đè. Nếu lượt đánh dấu `covered_turn_id` không còn, handler dựng lại từ đầu mà không dùng summary cũ (vẫn ghi có kiểm version), còn `recent_turns` quay về các lượt mới nhất thay vì trả rỗng. Đã đăng ký ở `app/worker.py` và thêm vào danh sách loại job của otel.

## Quyết định

- **Bộ đếm token:** dùng `TokenEstimator` có sẵn (`app/shared/utils/token_estimator.py`, tiktoken `cl100k_base`, rơi về 2 ký tự một token nếu thiếu thư viện), cùng bộ mà các adapter dùng để tính ngân sách prompt. Không thêm thư viện. Đây là ước lượng, không phải tokenizer riêng của từng provider; nếu CONV-002 cần đúng tokenizer provider thì phải đổi nguồn đếm (`count_tokens` của dịch vụ nhận bất kỳ hàm nào).
- **Đánh dấu lượt đã tóm bằng id lượt**, không bằng mốc thời gian: `TurnRecord` không có `created_at`, và id lượt không phụ thuộc đồng hồ.
- **Giữ 2 lượt mới nhất ngoài summary** (`SUMMARY_KEEP_RECENT_TURNS`): để câu hỏi tiếp nối vẫn đọc nguyên văn lượt vừa rồi. Job không làm gì nếu chỉ còn ≤ 2 lượt chưa tóm; mỗi lần tóm tối đa 30 lượt, phần còn lại do job sau.
- **Chặn trên khi lấy lượt chưa tóm:** tối đa 40 lượt mỗi lần đọc. Chạm 40 thì coi như đến hạn tóm, để backlog không bị ẩn.
- **Khách: không có summary.** `durable_background_jobs.principal_id` có khoá ngoại tới `users.id`, mà khách không chắc có hàng `users` (lượt trả lời dạng liệt kê và lượt bị chặn không gọi `personal.load` nên không tạo hàng). Nếu thiếu, `enqueue` gặp lỗi khoá ngoại, bị hiểu nhầm là trùng khoá idempotency rồi ném lỗi, làm mất cả lượt vừa lưu. Vì vậy khách chỉ có cửa sổ token. Thành viên cũng chỉ bị rủi ro này nếu mọi lượt trước đều là liệt kê hoặc bị chặn, mà khi đó chưa đến ngưỡng.
- **Summary gắn với consent trí nhớ:** vì handler dùng cùng `ensure_consent`, thành viên không bật trí nhớ dài hạn sẽ không có summary, và job của họ thất bại (mỗi version chỉ một job nhờ khoá idempotency). Cần Sếp quyết định có tách consent này không.
- Cả hai ngưỡng là biến cấu hình, kiểm tra miền giá trị trong `settings.py`. Ngưỡng tóm (1200) phải thấp hơn ngân sách cửa sổ (1500): `Settings` và `AdvancedTurnService` (khi có `summaries`) từ chối cấu hình ngược lại, để lượt được tóm trước khi rời cửa sổ. Test mô phỏng thread tăng dần xác nhận không lượt nào nằm ngoài cả cửa sổ lẫn summary khi job chạy kịp; job chậm hơn vài lượt vẫn có thể để hở tạm thời.
- Mỗi lượt chỉ đếm token một lần (`_conversation`), cửa sổ và ngưỡng dùng chung kết quả. Ngưỡng chỉ kích hoạt khi job có gì để tóm (ít nhất 3 lượt gồm lượt vừa xong), để version luôn tăng và khoá idempotency không kẹt.
- Nếu job của một version thất bại hẳn (dead letter), không job mới nào được xếp cho version đó cho đến khi vận hành phát lại job.
- Dịch vụ lượt không truyền `summaries` thì không đọc summary và không xin job, nên test cũ không cần Postgres.

## Kiểm tra

| Kiểm tra | Kết quả |
|---|---|
| Test đơn vị (`pytest --ignore=tests/integration`) | 1396 đạt; 28 test ở `tests/` gốc cần dịch vụ thật nên lỗi (gồm 2 test `test_health.py` phụ thuộc môi trường, không liên quan thay đổi này) |
| Test mới | Cửa sổ giữ lượt mới trong ngân sách và luôn giữ lượt cuối; Composer nhận summary cùng lượt chưa tóm ở cả hai làn; job chỉ được xin khi vượt ngưỡng, khách không bao giờ được xin; một job mỗi version dù nhiều lượt vượt ngưỡng; thread tăng dần không để lượt nào ngoài cả cửa sổ lẫn summary; mất lượt đánh dấu thì quay về các lượt mới nhất và dựng lại không dùng summary cũ; rút consent thì không tóm; ngưỡng không thấp hơn cửa sổ bị từ chối; commit chỉ ghi job khi lượt được lưu; handler ghi version + 1; thua cuộc đua và thread đã xoá không ghi đè; khoá ngoại có `CASCADE` |
| `ruff` (file đổi), changed-lines, debt ratchet | Đạt (2144 so với 2162) |
| `mypy` (file app đổi), `lint-imports` | Đạt, 5 hợp đồng giữ nguyên |
| RAM budget, runbooks | Đạt |
| Test chuỗi migration | Đầu migration duy nhất là `a7d3e9b2c418` (test DB-01 đã cập nhật) |

## Chưa kiểm tra

- **Worker và job chưa chạy với LLM thật:** prompt tóm tắt chưa được xem kết quả thực, chưa biết chất lượng summary tiếng Việt, độ dài và việc giữ đúng sự kiện.
- **Chưa chạy trên Postgres:** migration chưa được áp dụng và `tests/integration/test_conv03_thread_summary.py` (job vào outbox một lần mỗi version, version tăng, người ghi muộn bị từ chối, rút consent thì không tóm, xoá thread xoá summary) đã viết nhưng chưa chạy vì máy này không có dịch vụ. Cần `make test-isolated`.
- Chưa đo độ trễ lượt chat khi có summary, và chưa thử hai worker cùng tóm một thread.

## Việc còn lại

- Chạy `make test-isolated` rồi chạy thử một thread dài với LLM thật, đọc summary sinh ra.
- Cân nhắc đếm token theo tokenizer của provider đang dùng nếu độ lệch lớn.
- Summary dài hạn hơn vài lần cuộn có thể trôi nghĩa; chưa có cơ chế kiểm tra hay tóm lại từ đầu.
- Job core memory (MEM-005) và reflection (MEM-010) vẫn chưa làm.
