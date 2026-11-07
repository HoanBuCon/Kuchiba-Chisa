# Discord nhắn thường qua API v2

| | |
|---|---|
| Ngày | 04/11/2026 |
| Người thực hiện | Claude, theo kế hoạch R2 của HoanBuCon |
| Nhánh | `feat/r2-discord-v2-chat` (từ `HBC` tại `014c731`) |

## Thay đổi

- Bot: `CORE_RAG_CHAT_V2=true` chuyển tin nhắn thường sang `/api/v2/chat/turns`. Mặc định tắt.
- `turn_id` suy ra từ id tin nhắn Discord, nên gửi lại không tạo câu trả lời thứ hai (CH-004).
- Server: mỗi người mỗi kênh có một thread cố định (`channel_thread_id`), vì bot không giữ thread id.
- Server: token bot không còn bị coi là khách vãng lai. Trước đó người dùng Discord trên v2 sẽ mất trí nhớ dài hạn; consent vẫn quyết định theo từng người.
- CI có thêm job `discord-bot-tests`. Trước đây CI không chạy test của bot.

## Quyết định

Vẫn đi qua v1 vì v2 chưa hỗ trợ:

| Loại tin | Thiếu gì ở v2 |
|---|---|
| Kênh chế độ cộng đồng | Transcript, topic summary, ambient mood (CONV-005) |
| Tin có ảnh | `images` trong turn |
| Tin trả lời kèm tham chiếu | `is_ephemeral_reference` |

## Kiểm tra

| Kiểm tra | Kết quả |
|---|---|
| `make test-isolated` | 1241 test đạt; mypy, import-linter, OpenAPI đạt |
| Test của bot | 27 test đạt |
| `get_or_create` trên Postgres dev | 5 lời gọi đua nhau ra một thread; chủ khác bị từ chối; dữ liệu thử đã xoá |

Chưa chạy bot với Discord thật hay với LLM thật, vì DeepSeek đang hết số dư.

## Việc còn lại

- Chạy thử đầu cuối trước khi bật cờ.
- Kênh cộng đồng, ảnh, stream bằng cách sửa tin nhắn (CH-002), lệnh `/mode` và `/link` (R3, R4).
- Thread cộng đồng dùng chung một kênh theo CONV-001 chưa làm: thread hiện là mỗi người mỗi kênh.
- `threads.channel` của thread bot là `discord`, chưa lưu guild hay kênh để hiển thị.
