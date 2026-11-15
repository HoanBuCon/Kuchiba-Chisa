# Ảnh thực thể qua URL ký của server (KNW-010)

| | |
|---|---|
| Ngày | 16/11/2026 |
| Người thực hiện | Claude |
| Nhánh | `feat/r2-entity-images` (từ `HBC`), chưa push, chưa có PR |

## Thay đổi

- Dữ liệu đã có sẵn từ ING-019: `images/index.json` trong `INGESTION_DATA_DIR` lưu mỗi ảnh với bản gốc, bản WebP hiển thị (cạnh dài ≤ 1.024 px, sinh lúc nạp), `file_page_url` và danh sách thực thể. Không đổi ingestion, không tải ảnh lúc phục vụ.
- `app/application/security/signed_image_url.py`: `ImageUrlSigner`, HMAC-SHA256 trên `sha256:biến thể:hết hạn`, khoá dẫn xuất từ `SECRET_KEY` với nhãn miền riêng. Không thêm secret mới.
- `app/application/entity_images.py`: `EntityImageService.for_entity(title)` trả `{url, original_url, source_page, attribution}`; `serve(...)` kiểm chữ ký rồi đọc file từ vault.
- `GET /api/v2/images/{sha256}?expires=&sig=[&original=1]` trong `chat_v2.py`, cùng cờ `CHAT_V2_ENABLED`. Quyền truy cập chỉ dựa vào chữ ký (thẻ `<img>` không gửi được bearer). Chữ ký phủ cả biến thể nên link hiển thị không mở được bản gốc.
- `turn.completed` có thêm khoá `image` (hoặc `null`). Chỉ có khi câu trả lời có căn cứ, không abstain, không phải danh sách, và bằng chứng `kb_entities` thuộc đúng một thực thể.
- `FileImageVault.read()` (chặn đường dẫn ra ngoài gốc) và cổng `IImageCatalog`; setting `IMAGE_URL_TTL_SECONDS` (mặc định 900 giây).

## Quyết định

- Chọn ảnh chính: ảnh có tên file chứa tên thực thể, nếu không thì theo tên file. Index chưa lưu thứ tự trong infobox nên đây là xấp xỉ.
- Index nạp một lần khi dùng lần đầu; chạy ingestion mới thì cần khởi động lại, giống kho kiến thức.
- Client chỉ nhận URL của server; host `static.wikia.nocookie.net` không bao giờ xuất hiện trong payload (có test).
- `source_page` là trang File trên wiki (liên kết để người dùng xem nguồn, không dùng để tải ảnh).

## Kiểm tra

- `tests/unit/test_entity_image_serving.py` (22 test): chữ ký hợp lệ/hết hạn/bị sửa (sha, biến thể, hạn, chữ ký, khoá khác), WebP ≤ 1.024 px từ ảnh PNG 3000x1500 trong bộ nhớ, vault không đọc ra ngoài gốc, route trả 200/403, không hotlink, điều kiện `image` trong lượt chat.

## Chưa kiểm tra

- Chưa chạy với dữ liệu ingestion thật hay trình duyệt thật.

## Việc còn lại

- Discord: client v2 chưa dùng embed ảnh, và URL hiện là đường dẫn tương đối; cần base URL công khai khi làm.
- Lượt phát lại (`replayed`) không kèm ảnh vì ảnh không nằm trong `TurnRecord`.
- Web: hiển thị ảnh và dòng nguồn/fair use từ `image` trong `turn.completed`.
- Lưu thứ tự ảnh infobox vào index để chọn đúng ảnh chính.
