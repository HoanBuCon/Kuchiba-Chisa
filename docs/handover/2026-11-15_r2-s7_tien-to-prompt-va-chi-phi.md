# Tải ngữ cảnh song song và chi phí từng lượt

| | |
|---|---|
| Ngày | 15/11/2026 |
| Người thực hiện | Claude, thay đổi 4 và 6 của [thiết kế mục tiêu](../design/target-architecture.md) cùng COST-001 |
| Nhánh | `feat/r2-prompt-cost` (từ `HBC`), chưa có PR |

## Hiện tượng

- Ngữ cảnh cá nhân (cảm xúc, trí nhớ) chỉ được tải sau khi bước hiểu câu hỏi và truy hồi xong, nên lượt chờ nối tiếp ba bước.
- Lượt không lưu token và chi phí (COST-001, MODE-006).

## Thay đổi

- **Tải song song:** sau khi lấy lịch sử, `AdvancedTurnService` tạo một task tải ngữ cảnh cá nhân chạy cùng bước hiểu và truy hồi; chỗ cần mới `await`. Lượt bị chặn không tạo task. Thoát bất kỳ đường nào (lỗi, client ngắt) task đều bị huỷ rồi được chờ, nên không để sót task hay cảnh báo "exception never retrieved". Lỗi tải chỉ nổ ra ở chỗ cần ngữ cảnh, như trước.
- **Chi phí từng lượt (COST-001, MODE-006):**
  - `LLMResponse.cached_input_tokens`; adapter DeepSeek đọc `usage.prompt_cache_hit_tokens`. Adapter Gemini và Groq không báo nên là 0.
  - `LLMCallBudget` cộng dồn token vào, token cache, token ra (`record_usage`); gateway gọi sau mỗi lời gọi thành công, nên cộng cả lượt hiểu lẫn Composer.
  - Hàm thuần `estimate_cost_usd` và `TokenPrices` ở `app/domain/services/token_cost.py`: token cache tính giá cache, phần còn lại của token vào tính giá thường.
  - Bảng giá trong `settings.py`: `LLM_PRICE_INPUT_PER_MTOK` (0.3), `LLM_PRICE_CACHED_INPUT_PER_MTOK` (0.006), `LLM_PRICE_OUTPUT_PER_MTOK` (1.2), đơn vị USD mỗi triệu token.
  - Migration `b3e8c1f5a926` thêm 4 cột nullable vào `thread_turns` (`input_tokens`, `cached_input_tokens`, `output_tokens`, `cost_usd`), nối sau `a7d3e9b21c64`. Lượt cũ đọc ra là 0.
  - Các số này chỉ được lưu, không có trong payload SSE (`turn.completed`).

## Quyết định

- **Giá mặc định là giá giờ cao điểm của deepseek-flash** (cache hit 0,006, cache miss 0,3, output 1,2 USD mỗi triệu token), đọc ở trang giá của DeepSeek ngày 15/11/2026; giờ thấp điểm bằng một nửa nên chi phí ghi nhận là cận trên.
- **PER-004 chỉ đạt ở tiền tố persona.** `ContextBuilder.build()` (được bảo vệ) đặt khối trạng thái cảm xúc ngay sau persona và `[OUTPUT FORMAT]` ở cuối, còn core memory bị trộn vào danh sách trí nhớ rồi sắp lại; sắp lại chuỗi `system` sau khi build thì mong manh và đẩy định dạng JSON khỏi cuối prompt. Nên chỉ persona dẫn đầu prompt là phần tiền tố ổn định. Muốn đủ PER-004 phải sửa builder được bảo vệ khi Sếp duyệt.
- **Lượt trả lời dạng liệt kê** không dùng ngữ cảnh cá nhân nhưng task vẫn được tạo; kết quả bị huỷ khi lượt kết thúc. Đổi lại lượt đó có thể tốn một lần tải DB và embed vô ích. Chấp nhận để giữ logic đơn giản.
- Chi phí lượt bị chặn là 0 vì chưa có lời gọi nào.

## Kiểm tra

| Kiểm tra | Kết quả |
|---|---|
| Test đơn vị mới | Tải ngữ cảnh bắt đầu khi truy hồi đang chạy (fake ghi lại chồng lấn); lỗi truy hồi huỷ task đang chờ; lỗi tải nổ ra ở Composer; lượt lưu token và chi phí đúng công thức và không có trong SSE; lượt bị chặn tốn 0; gateway cộng usage vào budget qua nhiều lời gọi; DeepSeek đọc token cache; `estimate_cost_usd` |
| Test DB-01 | Cập nhật đầu migration thành `b3e8c1f5a926` |
| `ruff` changed-lines, debt ratchet, `mypy`, `lint-imports`, RAM budget | Đạt |

## Chưa kiểm tra

- **Không chạy đo thật nào:** chưa gọi DeepSeek, nên chưa kiểm `prompt_cache_hit_tokens` trả về đúng như tài liệu.
- **Migration chưa áp dụng trên Postgres** và cột mới chưa được kiểm bằng test tích hợp (cần `make test-isolated`).
- Chưa đo độ trễ tiết kiệm được nhờ tải song song.

## Việc còn lại

- Cân nhắc giá theo từng model và theo giờ cao/thấp điểm.
- Đo tỷ lệ cache-hit bằng lời gọi thật; đưa `chisa.llm.cached_tokens` và `chisa.llm.cost` vào telemetry (không chứa nội dung, MON-013).
- Kiểm COST-002 (≤ 0,001 USD mỗi lượt) trên dữ liệu thật.
