# Tiền tố prompt ổn định, tải ngữ cảnh song song và chi phí từng lượt

| | |
|---|---|
| Ngày | 15/11/2026 |
| Người thực hiện | Claude, thay đổi 4 và 6 của [thiết kế mục tiêu](../design/target-architecture.md) cùng COST-001 |
| Nhánh | `feat/r2-prompt-cost` (từ `HBC`), chưa có PR |

## Hiện tượng

- Ngữ cảnh cá nhân (cảm xúc, trí nhớ) chỉ được tải sau khi bước hiểu câu hỏi và truy hồi xong, nên lượt chờ nối tiếp ba bước.
- Trong prompt, khối trạng thái cảm xúc (đổi từng lượt) nằm giữa persona và phần còn lại, còn `[OUTPUT FORMAT]` nằm cuối. Tiền tố giống nhau giữa các lượt chỉ kéo dài đến hết persona nên cache tiền tố của provider ít trúng (PER-004).
- Lượt không lưu token và chi phí (COST-001, MODE-006).

## Thay đổi

- **Tải song song:** sau khi lấy lịch sử, `AdvancedTurnService` tạo một task tải ngữ cảnh cá nhân chạy cùng bước hiểu và truy hồi; chỗ cần mới `await`. Lượt bị chặn không tạo task. Thoát bất kỳ đường nào (lỗi, client ngắt) task đều bị huỷ rồi được chờ, nên không để sót task hay cảnh báo "exception never retrieved". Lỗi tải chỉ nổ ra ở chỗ cần ngữ cảnh, như trước.
- **Thứ tự prompt (PER-004):** `_StablePrefixBuilder` trong `persona_v2.py`, là lớp cha của cả hai builder v2, ghi đè `build()` và sắp lại `system` thành persona, rồi `[OUTPUT FORMAT]`, rồi khối trạng thái cảm xúc, rồi summary, trí nhớ, lore. Không sửa `context_builder.py` (được bảo vệ): chỉ cắt lại chuỗi mà nó trả về theo `components`. Tiền tố đến hết `[OUTPUT FORMAT]` giống nhau giữa các lượt cùng làn.
- **Chi phí từng lượt (COST-001, MODE-006):**
  - `LLMResponse.cached_input_tokens`; adapter DeepSeek đọc `usage.prompt_cache_hit_tokens`. Adapter Gemini và Groq không báo nên là 0.
  - `LLMCallBudget` cộng dồn token vào, token cache, token ra (`record_usage`); gateway gọi sau mỗi lời gọi thành công, nên cộng cả lượt hiểu lẫn Composer.
  - Hàm thuần `estimate_cost_usd` và `TokenPrices` ở `app/domain/services/token_cost.py`: token cache tính giá cache, phần còn lại của token vào tính giá thường.
  - Bảng giá trong `settings.py`: `LLM_PRICE_INPUT_PER_MTOK` (0.28), `LLM_PRICE_CACHED_INPUT_PER_MTOK` (0.028), `LLM_PRICE_OUTPUT_PER_MTOK` (0.42), đơn vị USD mỗi triệu token.
  - Migration `b3e8c1f5a926` thêm 4 cột nullable vào `thread_turns` (`input_tokens`, `cached_input_tokens`, `output_tokens`, `cost_usd`), nối sau `a7d3e9b2c418`. Lượt cũ đọc ra là 0.
  - Các số này chỉ được lưu, không có trong payload SSE (`turn.completed`).

## Quyết định

- **Giá mặc định là giá niêm yết của DeepSeek tôi nhớ, chưa đối chiếu với trang giá hiện hành.** Có ghi chú trong `settings.py`; cần Sếp kiểm tra trước khi tin con số chi phí.
- **Trí nhớ cốt lõi chưa đứng riêng trước phần biến động.** SRS yêu cầu persona, định dạng, core memory, rồi phần biến động. Hiện `PostgresPersonalContext` trộn core memory vào danh sách `memories` (dòng đầu), `ContextBuilder.build()` sắp xếp lại danh sách đó theo đường cong chữ U, nên core memory nằm trong khối `[MEMORIES]` sau khối trạng thái. Tách riêng cần đổi `PersonalContext` và giao diện Composer, không thuộc phạm vi "chỉ ghi đè builder v2", nên chưa làm. Phần tiền tố ổn định thật sự hiện dừng ở hết `[OUTPUT FORMAT]`.
- **`[OUTPUT FORMAT]` không còn ở cuối prompt.** Bản gốc đặt nó cuối để tận dụng độ chú ý gần nhất; đổi chỗ có thể ảnh hưởng độ tuân thủ JSON. Chưa đo.
- **Lượt trả lời dạng liệt kê** không dùng ngữ cảnh cá nhân nhưng task vẫn được tạo; kết quả bị huỷ khi lượt kết thúc. Đổi lại lượt đó có thể tốn một lần tải DB và embed vô ích. Chấp nhận để giữ logic đơn giản.
- Chi phí lượt bị chặn là 0 vì chưa có lời gọi nào.

## Kiểm tra

| Kiểm tra | Kết quả |
|---|---|
| Test đơn vị mới | Tải ngữ cảnh bắt đầu khi truy hồi đang chạy (fake ghi lại chồng lấn); lỗi truy hồi huỷ task đang chờ; lỗi tải nổ ra ở Composer; lượt lưu token và chi phí đúng công thức và không có trong SSE; lượt bị chặn tốn 0; gateway cộng usage vào budget qua nhiều lời gọi; DeepSeek đọc token cache; `estimate_cost_usd`; thứ tự persona, định dạng, trạng thái, summary, trí nhớ ở cả hai builder; tiền tố không đổi khi trạng thái cảm xúc đổi |
| Test hash persona (STD-AI-003) | Đạt, không đụng `_IDENTITY`, `_VOICE_RULES`, `_SECURITY` |
| Test DB-01 | Cập nhật đầu migration thành `b3e8c1f5a926` |
| `ruff` changed-lines, debt ratchet, `mypy`, `lint-imports`, RAM budget | Đạt |

## Chưa kiểm tra

- **Không chạy đo thật nào:** chưa gọi DeepSeek, nên chưa biết tỷ lệ cache-hit sau khi đổi thứ tự, chưa kiểm `prompt_cache_hit_tokens` trả về đúng như tài liệu, và chưa so chất lượng trả lời trước/sau khi `[OUTPUT FORMAT]` đổi chỗ.
- **Migration chưa áp dụng trên Postgres** và cột mới chưa được kiểm bằng test tích hợp (cần `make test-isolated`).
- Chưa đo độ trễ tiết kiệm được nhờ tải song song.
- Nếu một nhánh khác cũng thêm migration, đầu chuỗi sẽ có hai đầu; cần xếp lại `down_revision` và test DB-01 khi gộp.

## Việc còn lại

- Đối chiếu bảng giá với trang của provider; cân nhắc giá theo từng model.
- Tách core memory thành khối riêng đặt trước phần biến động (PER-004 đầy đủ).
- Đo tỷ lệ cache-hit và chất lượng JSON bằng lời gọi thật; đưa `chisa.llm.cached_tokens` và `chisa.llm.cost` vào telemetry (không chứa nội dung, MON-013).
- Kiểm COST-002 (≤ 0,001 USD mỗi lượt) trên dữ liệu thật.
