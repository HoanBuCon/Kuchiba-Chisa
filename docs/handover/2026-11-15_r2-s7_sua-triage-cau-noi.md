# Sửa triage cho câu khen, câu chê và "tiếng Anh"

| | |
|---|---|
| Ngày | 15/11/2026 |
| Người thực hiện | Claude |
| Nhánh | `fix/r2-triage-chat-turns` (từ `HBC` tại `8a57b17`) |

## Hiện tượng

Lần đo persona ngày 14/11: nhóm ranh giới bằng 0 ở cả hai bản persona. Câu khen "Chía tròn ơi, hôm nay đáng yêu thế." và câu chê "Mày ngu quá…" vào làn tra cứu, nên Chisa trả câu "chưa đủ bằng chứng". Ngược lại, "Ai lồng tiếng tiếng Anh cho Chisa?" vào làn trò chuyện.

## Nguyên nhân

- Triage mặc định đưa mọi câu không có dấu hiệu trò chuyện vào làn tra cứu, kể cả câu không hỏi gì.
- Chữ "Anh" trong "tiếng Anh" bị nhận là đại từ xưng hô.

## Thay đổi (`lane_router.py`)

- Câu không có dấu hỏi, không có từ hỏi và không yêu cầu kể hay liệt kê thì vào làn trò chuyện.
- Thêm đại từ "mày", "tao", "cậu" và biệt danh "Chía" vào dấu hiệu trò chuyện.
- "tiếng Anh" không còn bị coi là xưng hô; thêm "lồng tiếng", "voice", "diễn viên" vào dấu hiệu hỏi dữ kiện.
- Thêm từ hỏi teencode "j", "ji".

## Kiểm tra

Triage là hàm tất định, nên đo offline, không gọi LLM, trên corpus `2026.11.04-1`:

| Tập | Trước | Sau |
|---|---|---|
| 33 kịch bản persona | 3 câu sai làn | 0 |
| Golden tập dev, 125 lượt | 0 câu lore sai làn | 0 |

`make test-isolated`: 1330 test đạt; mypy, import-linter, OpenAPI và lint như CI đều đạt.

## Chưa kiểm tra

- Chưa chạy lại với LLM thật, nên chưa có điểm rubric mới cho nhóm ranh giới.
- Tập giữ lại không được dùng khi chỉnh, đúng quy ước; kết quả trên tập đó chưa biết.
- Luật vẫn là regex chỉnh trên các câu đã thấy. Bước "hiểu câu hỏi" trong thiết kế mục tiêu mới là giải pháp lâu dài.
