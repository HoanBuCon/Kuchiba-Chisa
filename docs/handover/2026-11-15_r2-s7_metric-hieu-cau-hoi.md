# Metric của bước hiểu câu hỏi (ADV-003)

| Mục | Nội dung |
|---|---|
| Ngày | 15/11/2026 |
| Người thực hiện | Claude (code do subagent viết, Claude review) |
| Nhánh | `feat/r2-understanding-metrics` |
| PR | chưa mở |

## Thay đổi

- **Một counter mới `chisa.chat.understanding`** với nhãn `outcome` giới hạn trong 5 giá trị:
  - `skipped_rules`: luật tất định đã chắc là trò chuyện, không gọi mô hình.
  - `cache_hit`: lấy kết quả từ cache Redis.
  - `llm`: đã gọi mô hình và nhận kết quả hợp lệ.
  - `failed`: lỗi nhà cung cấp hoặc kết quả sai định dạng (rơi về làn tất định).
  - `overridden`: mô hình trả companion nhưng có thực thể khác Chisa nên giữ làn Advanced.
- **Chỗ đếm:**
  - `LlmQuestionUnderstander` đếm `cache_hit`, `llm`, `failed`. Nhận telemetry qua tham số, mặc định là bản no-op.
  - `AdvancedTurnService._plan` đếm `skipped_rules` và `overridden`. Mỗi lượt đếm đúng một lần cho mỗi quyết định.
- **Nhãn mới `outcome`** trong `TelemetryDimensions` và danh sách cho phép của adapter OTel; giá trị lạ bị gộp thành `other` (MON-012, MON-013). Không có nội dung tin nhắn nào đi vào nhãn.
- **Tỉ lệ bỏ qua** = `skipped_rules` / tổng; **tỉ lệ cache** = `cache_hit` / (`cache_hit` + `llm`).
- Repo không có file catalog metric được CI kiểm tra, nên không sửa SRS.

## Kiểm tra

| Kiểm tra | Kết quả |
|---|---|
| Test mới | mỗi outcome tăng đúng một lần với đúng nhãn; nhãn không chứa nội dung; adapter OTel giữ 5 giá trị và gộp giá trị lạ |
| pytest unit, ruff, mypy, lint-imports, changed-lines, debt ratchet | Đạt |
