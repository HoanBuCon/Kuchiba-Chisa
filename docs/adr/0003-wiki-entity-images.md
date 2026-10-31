# ADR-0003: Ảnh thực thể từ wiki, lưu kích thước gốc

- Trạng thái: **Accepted**
- Ngày: 2026-10-31
- Người quyết định: chủ dự án
- Liên quan: [bài học IndexBeast](../ingestion/indexbeast-lessons.md) (mục 5), [thiết kế ingestion](../ingestion/design.md) (mục 6.10), SRS v2.2 (ING-019, KNW-010, CAP-004)

## Bối cảnh

- SRS v2.1 chỉ có ảnh của người dùng; chưa ingest ảnh từ wiki.
- IndexBeast tải 10.371 ảnh gốc (7,96 GB). Ảnh được gắn theo section, 100% chưa rõ giấy phép, và lỗi ảnh làm hỏng trạng thái trang text.
- Trên Fandom (đo 2026-10-31):
  - liên kết ảnh–thực thể có sẵn ở dạng có cấu trúc (mục `image` của `pageprops.infoboxes`, thẻ `characters=`, category `<Thực thể> Images`);
  - ảnh mang `{{Fairuse}}`; API không trả giấy phép;
  - ảnh infobox của Tier A gồm 646 file, 0,94 GB bản gốc.

## Quyết định

1. Ingest **ảnh infobox của thực thể** trong kho có cấu trúc, liên kết bằng dữ liệu có cấu trúc, không gắn theo section.
2. Lưu **bản gốc** (theo yêu cầu của chủ dự án), định địa chỉ theo SHA-256, kiểm an toàn bằng Pillow.
3. Sinh **bản hiển thị** WebP ≤ 1.024 px tại chỗ để dùng trong câu trả lời; bản gốc chỉ phục vụ khi người dùng mở xem, qua URL ký của server.
4. Ghi `license=fair_use` và nguồn trang file; không hotlink từ trình duyệt người dùng.
5. Luồng ảnh tách khỏi luồng text; Tier A ở R1, hiển thị ở R2, Tier B ở R5.
6. Không OCR, không caption bằng model, không embedding ảnh ở v2.

## Hệ quả

- Thêm khoảng 1 GB đĩa cho Tier A (cộng khoảng 10% cho bản hiển thị). Ảnh không cần backup vì tải lại được từ wiki.
- Tải lần đầu thêm khoảng 15–20 phút ở 1 req/s, chạy sau text với ngân sách riêng.
- Fair use phù hợp với dự án cá nhân phi thương mại có ghi nguồn. Nếu thương mại hoá hoặc phân phối lại bộ ảnh thì phải xem lại quyết định này.

## Phương án đã cân nhắc

| Phương án | Lý do không chọn |
|---|---|
| Chỉ lấy thumbnail 512 px do server Fandom resize | Chủ dự án muốn giữ chất lượng gốc |
| Hotlink ảnh từ Fandom | Lộ IP người dùng cho bên thứ ba; phụ thuộc uptime của Fandom |
| Lấy mọi ảnh của trang như IndexBeast | 64% là icon giao diện; tốn dung lượng; liên kết theo section kém tin cậy |
