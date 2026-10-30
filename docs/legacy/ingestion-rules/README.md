# Luật ingestion legacy (chỉ để tham khảo)

Các file cấu hình dưới đây được lấy lại từ pipeline ingestion legacy trước khi pipeline này bị xoá (SRS v2 `ING-010`, ngày 2026-10-31). Chúng **không được code nào đọc**. Mục đích là làm đầu vào khi viết luật cho data plane mới ở pha R1.

| File | Nội dung |
|---|---|
| `category_whitelist.json` | Danh sách category wiki được phép crawl |
| `pipeline_rules.yaml` | Luật lọc template, category rác, section boilerplate |
| `taxonomy.yaml` | Phân loại loại trang (character / world / story...) |

Toàn bộ code legacy (sanitizer, canonical builder, chunker, crawler có luật subpage, classifier, entity registry) vẫn còn nguyên trên nhánh `freeze/chisa-v1`, đường dẫn `app/infrastructure/ingestion/`. Xem một file bằng lệnh:

```bash
git show freeze/chisa-v1:app/infrastructure/ingestion/parsers/sanitizer.py
```
