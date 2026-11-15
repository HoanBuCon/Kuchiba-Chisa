# Job hợp nhất core memory

| | |
|---|---|
| Ngày | 15/11/2026 |
| Người thực hiện | Claude, nửa sau của MEM-005 |
| Nhánh | `feat/r2-core-memory-consolidation` (từ `HBC`) |

## Hiện tượng

Job trích xuất trí nhớ v2 chỉ ghi trí nhớ từng sự kiện vào Qdrant. Không có gì đưa những dữ kiện bền vững (sở thích, mốc quan hệ, lời hứa) vào core memory, nên core memory chỉ đổi khi người dùng tự sửa.

## Thay đổi

- Loại job mới `core_memory_consolidation.v1`, payload chỉ chứa id người dùng. Đã thêm vào `_JOB_TYPES` của telemetry và đăng ký ở `app/worker.py`.
- **Hàng đợi:** `ThreadMemoryExtractionJobHandler` xếp job này khi `MemoryExtractor.extract_and_store_batch` lưu ít nhất một trí nhớ mới (hàm giờ trả về số trí nhớ đã lưu). Khoá idempotency là `core-memory-consolidation:<user>:<mốc>:<version core memory>:<giờ>`: các lượt trước khi job chạy dùng chung một khoá; job chạy xong và đẩy mốc lên thì trí nhớ mới có khoá mới (không phải chờ lượt chat sau); thua race với người dùng đổi version nên cũng được xếp lại. Thành phần giờ chỉ để trí nhớ rơi đúng giây của mốc không bị kẹt quá một giờ. Xếp job lỗi chỉ ghi cảnh báo, không làm hỏng job trích xuất.
- **Handler:** kiểm tra consent lúc chạy như job trí nhớ, rồi gọi `CoreMemoryConsolidator` (`app/domain/services/core_memory_consolidator.py`). Khách không có job này: job trích xuất chỉ có cho thành viên, và `ensure_consent` từ chối người không có hàng `users`.
- **Mốc đã hợp nhất (watermark):** bảng mới `core_memory_consolidation` (migration `a7d3e9b21c64`, nối sau `a7d3e9b2c418` của thread_summaries) giữ `consolidated_through` (epoch giây của trí nhớ mới nhất đã xử lý) và `job_owned`. Trí nhớ được đọc từ Qdrant bằng `QdrantService.list_user_memories_since` (`created_at >= mốc`, bỏ mục hết hạn): đọc hết các trang rồi sắp tăng dần theo `(created_at, id)` và mới cắt 40 mục cũ nhất, vì thứ tự scroll của Qdrant không xác định; nhờ vậy mốc không bao giờ vượt qua mục chưa đọc. Cột `boundary_ids` giữ id các mục đã xử lý nằm đúng giây của mốc, nên mục biên không bị đọc lại và lần chạy không có gì mới thì không gọi LLM.
- **LLM:** qua gateway hiện có, `LLMPurpose.MEMORY_RECONCILIATION`, đầu ra JSON theo schema `{nickname, add, retire}`. Toàn bộ prompt đi qua `PiiRedactor`; mục do model sinh ra bị bỏ nếu còn dấu hiệu PII hoặc chứa `[REDACTED_`.
- **Ghi có kiểm soát phiên bản:** `PostgresCoreMemoryConsolidationStore.commit` khoá hàng core memory (`FOR UPDATE`), so `version` với phiên bản đã đọc, rồi mới ghi nội dung và mốc trong một giao dịch. Lệch phiên bản thì không ghi gì, mốc đứng yên, job kết thúc êm (job sau thử lại trên phiên bản mới). Khi chưa có hàng thì `INSERT ... ON CONFLICT DO NOTHING`.
- Xoá dữ liệu cá nhân (`SqlAlchemyPersonalDataPurge.delete_core_memory`) xoá luôn hàng trạng thái hợp nhất.

## Quyết định

- **Bảo vệ mục do người dùng viết.** Core memory không có thông tin nguồn gốc, và schema `CoreMemory` (cũng là hợp đồng API) không đổi. Job nên ghi riêng danh sách `job_owned` các chuỗi nó đã thêm. Job chỉ được thêm mục mới hoặc gỡ mục nằm trong `job_owned` (khớp chính xác); mọi mục khác là của người dùng và không bao giờ bị sửa hay xoá. Mục job đã thêm mà người dùng sửa lại thì không còn khớp, tự thành của người dùng. Biệt danh chỉ được đặt khi trống, hoặc thay khi chính job đã đặt.
- **Giới hạn kích thước:** mục dài hơn `MAX_ITEM_CHARS` bị bỏ (không cắt giữa chừng, tránh câu cụt làm sai dữ kiện), danh sách đầy `MAX_ITEMS` thì không thêm nữa (job không bao giờ đẩy mục của người dùng ra), kết quả luôn qua `CoreMemory.model_validate`.
- **Khoá gom theo mốc và version** thay vì theo giờ: job xong thì lượt có trí nhớ mới xếp được job mới ngay. Đổi lại, một người nói nhiều có thể tốn một lời gọi LLM mỗi lượt có trí nhớ mới khi worker kịp xử lý giữa các lượt; muốn gom mạnh hơn cần job có `available_at` trễ, hiện hàng đợi chưa hỗ trợ.
- Chỉ trí nhớ cá nhân (collection `memories`); trí nhớ guild không vào core memory.
- Nếu người dùng gõ tay một mục trùng chữ với mục job đã thêm, job coi đó là của nó và có thể gỡ khi bị model yêu cầu.

## Kiểm tra

| Kiểm tra | Kết quả |
|---|---|
| Test đơn vị mới (`tests/unit/test_core_memory_consolidation.py`, 23 test) | Đạt: một job mỗi đợt, rút consent thì không ghi, thua race với người sửa tay thì không ghi đè và mốc đứng yên, mục người dùng được giữ, giới hạn kích thước, khử trùng và PII, mốc chỉ tiến khi thành công |
| `pytest` (không gồm tích hợp) | 1368 đạt; 27 test ở thư mục gốc cần dịch vụ thật nên lỗi như trên `HBC` |
| `ruff`, `mypy`, `lint-imports`, ratchet lint (2144 / nền 2162), changed-lines, RAM budget, runbooks | Đạt |

## Chưa kiểm tra

- **Chưa chạy với LLM thật:** chưa biết model có trả JSON đúng schema và có chọn dữ kiện hợp lý không; chất lượng prompt chưa được đo.
- Chưa chạy `PostgresCoreMemoryConsolidationStore` và migration trên Postgres thật (cần Docker); test đơn vị dùng bản giả lập cùng quy tắc phiên bản.
- Chưa chạy `QdrantService.list_user_memories_since` trên Qdrant thật; `created_at` chưa có chỉ mục payload nên lọc theo khoảng chạy trên tập đã lọc theo `user_id`.
- Chưa chạy worker thật xử lý loại job này.

## Việc còn lại

- Test tích hợp Postgres cho store (đua giữa job và `PUT /me/memory/core`).
- Reflection (MEM-010), summary cuộn (CONV-002).
- Cân nhắc trễ có chủ đích cho job hợp nhất để gom thêm lượt.
