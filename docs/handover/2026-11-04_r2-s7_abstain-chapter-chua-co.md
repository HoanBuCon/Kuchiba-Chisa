# Abstain khi hỏi chapter chưa có

| | |
|---|---|
| Ngày | 04/11/2026 |
| Người thực hiện | Claude, theo kế hoạch R2 của HoanBuCon |
| Nhánh | `fix/r2-unknown-chapter` (từ `HBC` tại `ae28e23`) |

## Hiện tượng

Hỏi "Cốt truyện Chapter VII kết thúc như thế nào?" thì 3/5 lần Chisa trả lời bằng nội dung "Chapter I: Act VII", dù Chapter VII chưa phát hành.

## Thay đổi

- `QuestionRouter`: lấy danh sách chapter từ quest trong corpus và đặt `unknown_chapter` khi câu hỏi nêu chapter ngoài danh sách. Nhận cả số La Mã và số thường.
- `AdvancedRetrieval`: gặp `unknown_chapter` thì abstain, không gọi Composer.

## Quyết định

- Luật tất định, không dựa vào điểm rerank hay LLM, vì kết quả cũ dao động giữa các lần hỏi.
- Corpus không có dữ liệu chapter thì không kết luận gì, để tránh abstain nhầm mọi câu.

## Sự cố

Backend trên stack dev không tự nạp lại code khi sửa file. Lần thử đầu vẫn chạy code cũ nên `Chapter VII` còn được trả lời; khởi động lại stack mới có kết quả đúng. Sau khi sửa code phải khởi động lại trước khi đo.

## Kiểm tra

| Kiểm tra | Kết quả |
|---|---|
| Corpus `2026.11.03-4` | Có Chapter I–IV, từ 75 quest |
| Router trên toàn bộ golden, không gọi LLM | 2 câu nêu chapter; chỉ `oos-003` bị đánh dấu, `enum-006` không bị |
| `Chapter VII` tiếng Việt và tiếng Anh, sau khi khởi động lại | 15/15 lần abstain |
| `Chapter 9` | 3/3 lần abstain |
| `Chapter III: Prologue`, `Chapter I: Act VII` | 6/6 lần trả lời |

## Chưa kiểm tra

- Chưa chạy lại toàn bộ golden: luật chỉ tác động câu nêu tên chapter. Lần kiểm tra router chỉ dùng câu gốc, chưa dùng bản dịch.
- Luật được viết sau khi xem `oos-003`, nên cải thiện trên case này chưa phải bằng chứng độc lập.

## Việc còn lại

- "Chapter II kết thúc như thế nào?" abstain 5/6 lần và 1 lần `invalid_output`, dù chapter có trong corpus. Câu tóm tắt cả chapter là phần việc của Agentic hoặc cần tra cứu riêng.
- Câu nêu số Act chưa có vẫn có thể bị trả lời nhầm, vì luật chỉ xét chapter.
