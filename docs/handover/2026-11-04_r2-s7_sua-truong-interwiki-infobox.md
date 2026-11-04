# Khôi phục trường infobox bị mất do link interwiki

| | |
|---|---|
| Ngày | 04/11/2026 |
| Người thực hiện | Claude, theo kế hoạch R2 của HoanBuCon |
| Nhánh | `fix/r2-interwiki-infobox` (từ `HBC`) |

## Hiện tượng

"Who voices Chisa in English?" bị abstain. Corpus chỉ có `voiceEN` ở 2/58 Resonator, và cả 2 giá trị đều là mảnh như "(Female)".

## Nguyên nhân

`pageprops` của Fandom lưu link interwiki dưới dạng dấu giữ chỗ `<!--IWLINK 21-->`, nên giá trị đọc ra rỗng hoặc chỉ còn một mảnh. HTML của trang vẫn có tên đầy đủ. Trên 1.054 trang Tier A có 147 giá trị bị ảnh hưởng ở 70 trang, 137 giá trị mất hẳn.

## Thay đổi

- `html_cleaner.py`: `pageprops` vẫn được ưu tiên, nhưng trường có dấu giữ chỗ lấy giá trị từ HTML. Không có HTML thì bỏ trường, không lưu mảnh.
- `cleaning.yaml`: `silver-14`.
- Corpus `2026.11.04-1` ở staging, dựng từ bronze có sẵn, không tải lại Fandom.

## Kiểm tra

| Kiểm tra | Kết quả |
|---|---|
| `voiceEN`, `voiceJP`, `voiceKR` trên 58 Resonator | Đều 57/58 (trước đó `voiceEN` 2, `voiceJP` 1) |
| Data gate | Đạt; số chunk, entity, alias không đổi |
| Embed | 70 chunk mới, 9.802 chunk dùng lại cache |
| Retrieval gate (`runtime_local`) | Đạt: Hit@5 0,944, MRR@10 0,834 |
| `lore-012` với LLM thật | Trả lời đúng "Leader Looi" |

## Chưa kiểm tra

- **Golden trên corpus mới chưa xong:** DeepSeek trả 402 Payment Required giữa chừng, nên chỉ 46/118 câu được chấm: 43 đúng, bằng đúng số của các câu đó ở lần trước. Khác biệt: `lore-012` đúng ra, `lore-101` sai đi. Bộ chấm căn cứ chưa chạy được.
- 6.995 entity chỉ có dữ liệu cấu trúc không có HTML, nên trường có dấu giữ chỗ bị bỏ thay vì khôi phục.

## Việc còn lại

- Chạy lại golden và bộ chấm khi DeepSeek có số dư.
- Trích dẫn lộ tên trường thô: `“voiceEN: Leader Looi”`.
- `rarity` trống ở cả 58 Resonator vì giá trị là ảnh; chưa xử lý.
- Gateway xếp 402 vào lỗi `UNKNOWN`, nên hết tiền trông như lỗi không rõ nguyên nhân.
