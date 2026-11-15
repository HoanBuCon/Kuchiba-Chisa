# Nhãn trường infobox trong trích dẫn

| | |
|---|---|
| Ngày | 15/11/2026 |
| Người thực hiện | Claude (subagent) |
| Nhánh | `fix/r2-infobox-citation-labels` (từ `HBC`) |
| PR | chưa mở |

## Hiện tượng

Trích dẫn ở lane có căn cứ của v2 lộ tên trường thô, ví dụ `“voiceEN: Leader Looi”`.

## Nguyên nhân

`profile_unit` trong `app/domain/ingestion/units.py` ghép thẳng `key: value` vào văn bản thẻ hồ sơ. Văn bản này được đưa vào chunk, nên tên trường nằm sẵn trong corpus đã lập chỉ mục. Trích dẫn chỉ cắt đoạn nguyên văn từ chunk (giữ nguyên ngữ nghĩa kiểm chứng), nên lỗi không nằm ở `composer.py` hay các công cụ truy vấn lúc chạy.

## Thay đổi

- `app/domain/ingestion/field_labels.py` (mới): `field_label(key)` với bảng cố định cho `voiceEN/JP/KR/CN` và `id`; khoá khác tách theo camelCase, `_`, `-` thành nhãn tiếng Anh (`birthPlace` thành `Birth place`).
- `units.py`: thẻ hồ sơ dùng `field_label(key)`.
- Test: `tests/unit/ingestion/test_field_labels.py` (mới), cập nhật `test_gold_chunking.py`.

## Quyết định

- Sửa ở tầng ingestion, không sửa lúc hiển thị: nếu đổi nhãn sau khi truy xuất, trích dẫn sẽ không còn khớp nguyên văn với văn bản chunk và bước xác minh sẽ hỏng. Sửa tại nguồn thì chunk, bằng chứng và trích dẫn cùng một văn bản, logic xác minh không đổi.
- Không đụng vào bronze, silver hay dữ liệu Qdrant/Postgres.

## Kiểm tra

- Unit test ingestion và toàn bộ unit test (trừ integration), ruff, lint-imports, ratchet: xem kết quả trong commit/báo cáo.

## Chưa kiểm tra

- Chưa dựng corpus mới nên chưa đo tác động lên retrieval: nhãn dài hơn (`English voice actor` so với `voiceEN`) đổi văn bản embed của thẻ hồ sơ, cần chạy lại retrieval gate.
- Các khoá infobox thực tế ngoài `voice*` chưa được rà hết; khoá lạ rơi về bộ tách camelCase.

## Việc còn lại

- **Cần corpus release mới** (gold từ silver, embed lại các thẻ hồ sơ) thì bản sửa mới tới người dùng; corpus hiện tại vẫn hiển thị tên trường thô.
- Chạy retrieval gate và golden trên corpus mới.
