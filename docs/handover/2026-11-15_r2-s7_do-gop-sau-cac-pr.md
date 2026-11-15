# Đo gộp sau các PR ngày 15/11

| Mục | Nội dung |
|---|---|
| Ngày | 15/11/2026 |
| Người thực hiện | Claude |
| Nhánh | `docs/r2-batch-measurement` |
| PR | chưa mở |

## Thay đổi được đo

`HBC` tại `a66969e`, gồm #92 (hiểu câu hỏi), #94 (claim song ngữ), #95 (cửa sổ token, summary), #96 (metric), #97 (hợp nhất core memory), #98 (nạp song song, chi phí từng lượt). Corpus `2026.11.04-1`, golden `golden-v2.4`, tập dev. Holdout không chạy lại.

## Kiểm tra

| Đo | Trước (#92, sáng 15/11) | Sau |
|---|---|---|
| Độ đúng golden dev | 0,95 | 0,92 (CI 0,86–0,96) |
| Single-hop | 0,99 | 0,97 |
| Multi-hop | 0,44 | 0,44 |
| Persona (4 câu) / xưng hô | 1,00 / 1,00 | 0,75 / 0,99 |
| Groundedness / citation precision | 0,963 / 0,971 | 0,963 / 0,971 |
| Mệnh đề nghiêm trọng bị flag | 11 | 10 |

Chi phí thật từng lượt (cột mới của #98, 121 lượt):

| Làn | Token vào | Trúng cache | Token ra | Chi phí trung bình |
|---|---|---|---|---|
| Advanced | 5.322 | 2.187 (41%) | 440 | 0,00148 USD |
| Companion | 4.017 | 3.273 (81%) | 125 | 0,00039 USD |

- Các câu sai mới chủ yếu dao động giữa các lần chạy, cùng kiểu với `multi-002`/`multi-005` trước đây.
- `lore-104` sai thật: `claim_vi` dịch "Sword" thành "kiếm", trái quy tắc giữ nguyên tên riêng.
- `persona-002` đi làn companion, không đổi gì trong PR nào, nhưng lần này gọi người dùng là "bạn".
- Cả vòng đo tốn khoảng 0,08 USD. Số dư còn 1,40 USD.

## Chưa kiểm tra

- 10 mệnh đề nghiêm trọng chưa duyệt tay. QUAL-001 vẫn chưa đạt.
- Job summary và job hợp nhất core memory chưa chạy với worker thật (lần đo này tắt worker).

## Việc còn lại

- **COST-002 chưa đạt ở làn Advanced:** 0,00148 USD/lượt, mục tiêu ≤ 0,001 USD. Hướng rẻ nhất là giảm số bằng chứng đưa vào Composer (top 8) và giữ phần đầu prompt ổn định để tăng cache.
- Prompt: nhắc rõ không dịch tên loại vũ khí và thuộc tính.

## Giảm chi phí (cùng ngày, nhánh `perf/r2-advanced-cost`)

- Đưa 6 đoạn bằng chứng vào Composer thay vì 8. Thêm quy tắc không dịch tên hệ và loại vũ khí.
- Golden dev: độ đúng 0,93 (trước 0,92). Chi phí làn Advanced 0,00140 USD/lượt (trước 0,00148). Token vào 4.999, trúng cache 2.113, token ra 437.
- Vẫn chưa đạt COST-002 theo giá giờ cao điểm. Phần lớn chi phí đến từ khoảng 2.900 token vào không trúng cache và 437 token ra (claim song ngữ). Theo giá ngoài giờ cao điểm, chi phí là 0,0007 USD, đạt mục tiêu.
