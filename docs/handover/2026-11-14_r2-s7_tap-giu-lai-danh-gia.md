# Tập giữ lại cho bộ đánh giá

| | |
|---|---|
| Ngày | 14/11/2026 |
| Người thực hiện | Claude, bước 1 của [thiết kế mục tiêu](../design/target-architecture.md) |
| Nhánh | `feat/r2-eval-holdout` (từ `HBC` tại `a91c287`) |

## Thay đổi

- Mỗi case golden có trường `split`: `dev` (mặc định, 120 câu cũ) hoặc `holdout`.
- Báo cáo chấm riêng từng tập; `python -m evals run --split holdout` chạy một tập.
- Cổng truy hồi chỉ tính tập `dev`.
- Golden lên `golden-v2.3`, thêm 34 câu giữ lại:

| Nhóm | Số câu | Đo điều gì |
|---|---|---|
| Lore một bước | 16 | Resonator chưa từng xuất hiện trong golden; tiếng Việt, tiếng Anh, không dấu, teencode |
| Câu hỏi nối tiếp | 8 | Lượt cuối chỉ hiểu được nhờ lượt trước (ADV-003) |
| Không phải câu hỏi kiến thức | 6 | Khen, chê, tâm sự: abstain là lỗi triage (MODE-008) |
| Ngoài phạm vi | 4 | Phải abstain |

## Quy ước

- Chỉ chỉnh luật, ngưỡng và prompt trên tập `dev`. Không xem kết quả từng câu của tập giữ lại khi chỉnh.
- Đáp án lấy từ trường infobox của corpus `2026.11.04-1`, viết ra mà không chạy hệ thống trên các câu này.

## Kiểm tra

| Kiểm tra | Kết quả |
|---|---|
| `evals validate` | `golden-v2.3`: 154 câu, 34 câu chưa xác minh |
| `make test-isolated` | 1304 test đạt; mypy, import-linter, OpenAPI đạt |
| Lint như CI | Đạt |

## Chưa kiểm tra

- **Chưa chạy tập giữ lại với LLM thật**, vì phép đo trả phí đang tạm dừng. Chưa có số nào trên tập này.
- Cổng truy hồi chưa chạy lại sau thay đổi; số case đã xác minh không đổi vì câu mới chưa được xác minh.
- Bốn câu ngoài phạm vi dựa trên phán đoán rằng wiki không có thông tin đó.

## Việc còn lại

- Chủ dự án xác nhận 34 câu mới (`verified: false`).
- Câu tiếng Việt của tập giữ lại chưa có bản dịch đóng băng, nên chưa vào cổng truy hồi.
- Chạy lặp mỗi câu nhiều lần để giảm dao động: chưa làm.
