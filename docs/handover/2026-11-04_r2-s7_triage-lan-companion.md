# Triage, làn companion và đánh giá qua API v2

| | |
|---|---|
| Ngày | 04/11/2026 |
| Người thực hiện | Claude, theo kế hoạch R2 của HoanBuCon |
| Nhánh | `feat/r2-companion-lane` (từ `HBC` tại `8994845`) |
| PR | [#65](https://github.com/HoanBuCon/Kuchiba-Chisa/pull/65) |

## Thay đổi

- `lane_router.py`: triage tất định. Câu trò chuyện rõ ràng vào làn companion, có lịch sử và trí nhớ; câu còn lại ở làn có bằng chứng.
- `composer.py`: thêm `compose_companion`; câu trả lời chỉ gồm trích dẫn nay ghi trang nguồn.
- `question_router.py`: chỉ liệt kê quest hoặc Resonator khi câu hỏi thật sự hỏi về chúng, sửa lỗi liệt kê nhầm.
- `python -m evals run --api v2`: chấm trực tiếp trên `/api/v2`, cần `CHAT_V2_ENABLED=true` trên stack dev.

## Quyết định

- Làn companion không có grounding, nên triage chỉ chọn làn này khi dấu hiệu rõ.
- `CHAT_V2_ENABLED` vẫn tắt: các số đo dưới đây chưa đủ để bật cho người dùng.

## Kiểm tra

| Kiểm tra | Kết quả |
|---|---|
| `make test-isolated` và CI của PR | 1199 test đạt; mypy, import-linter, OpenAPI đạt |
| Golden v2 với LLM thật, 118 câu | Độ đúng 0,924 (CI 95%: 0,861–0,959) |
| Ngoài phạm vi được abstain | 6/6 |
| Abstain nhầm | 3,6% (mục tiêu ≤ 5%) |
| Precision của abstain | 0,6, **chưa đạt** mục tiêu ≥ 0,90 |
| Câu nhiều bước | 0,444, chờ Agentic |
| Triage sai | 0/125 lượt |

Luật triage và router được chỉnh ngay trên bộ này, nên số còn lạc quan. Bộ chấm chỉ tìm từ khoá: `memory-002` được tính đúng dù Chisa nói về đồ uống của mình.

## Chưa kiểm tra

- QUAL-001 và QUAL-002 chưa có phép đo riêng; chất lượng làn companion chưa được đo thật.
- 2 câu nhiều phiên của QUAL-008 chưa chạy.
- PERF-003 và PERF-007 chưa đo trên VPS.

## Việc còn lại

Phát hiện khi rà API v2 để chuyển web, đều phải xử lý trước khi bật v2:

- `RateLimitMiddleware` chỉ phủ `/api/v1`; `/api/v2` mới có `admit_chat` ở route gửi lượt.
- Metric gộp `/api/v2` vào nhóm `other` và chưa ghi TTFT cho stream v2.
- `turn.started` luôn báo `lane=advanced`, kể cả lượt companion.
- `turn.completed` thiếu `emotions` và `emotion_caption` theo SRS 8.2; `usage` chờ R3.
- Thiếu API đọc lại lượt của thread và `POST /threads`.
- Chuyển web, rồi Discord. Discord còn thiếu ảnh và ngữ cảnh kênh (CONV-005) trên v2.
