# Hoàn quota khi client ngắt kết nối giữa lượt chat v2

| | |
|---|---|
| Ngày | 15/11/2026 |
| Người thực hiện | Claude (subagent) |
| Nhánh | `fix/r2-refund-on-disconnect` (từ `HBC`) |
| PR | chưa mở |

## Thay đổi

- **Hoàn quota khi ngắt kết nối (REL-007):** route `POST /api/v2/chat/turns` hoàn quota đúng một lần nếu client đóng SSE (huỷ tác vụ hoặc đóng generator) trước khi lượt được lưu. Sau đó route ném lại tín hiệu huỷ, không nuốt.
- **Lượt đã lưu thì giữ phí:** `_deliver` lưu lượt trước khi phát token, nên token đầu tiên hoặc `turn.completed` chứng tỏ lượt đã lưu. Ngắt kết nối sau mốc đó không hoàn quota; người dùng đọc lại câu trả lời qua endpoint thread.
- **Không hoàn hai lần:** `_QuotaCharge` trong `chat_v2.py` gói lần đặt chỗ và chỉ hoàn một lần, dùng chung cho đường phát lại, lỗi LLM, thread bận và ngắt kết nối.

## Quyết định

- Lần hoàn trong lúc bị huỷ được bọc `asyncio.shield` để chính tín hiệu huỷ không làm đứt lần hoàn.
- Không đổi `chat_turns.py`; mốc "đã lưu" suy ra từ thứ tự sự kiện hiện có (lưu trước, phát token sau).
- Huỷ đúng lúc đang lưu (chưa nhận được sự kiện nào sau `evidence.added`) thì hoàn, vì giao dịch lưu chưa chắc đã commit.

## Kiểm tra

| Kiểm tra | Kết quả |
|---|---|
| Test đơn vị mới (6 ca) | Ngắt trước khi lưu hoàn một lần (huỷ và đóng generator); ngắt sau token hoặc sau `turn.completed` không hoàn; lỗi rồi ngắt hoàn một lần; phát lại rồi ngắt hoàn một lần |
| Toàn bộ test đơn vị, ruff, import-linter, lint changed-lines, ratchet | Đạt |

## Chưa kiểm tra

- Chưa thử với Starlette thật ngắt kết nối qua proxy hoặc trình duyệt; test điều khiển trực tiếp generator.
- Khi huỷ đúng giữa lúc giao dịch lưu đang chạy, lượt có thể đã commit nhưng vẫn được hoàn (sai lệch nhỏ, nghiêng về phía người dùng).

## Việc còn lại

- Cân nhắc cho `chat_turns.py` phát sự kiện "đã lưu" tường minh thay vì suy ra từ token đầu tiên.
