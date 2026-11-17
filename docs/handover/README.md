# Báo cáo bàn giao

Mỗi tính năng hoàn thành có một báo cáo ngắn, nằm trong cùng PR với tính năng đó. Viết cô đọng; mục nào không có nội dung thì bỏ.

## Đặt tên

```text
<YYYY-MM-DD>_<lát-cắt>_<ten-ngan-khong-dau>.md
```

Ví dụ: `2026-11-04_r2-s7_triage-lan-companion.md`.

## Nội dung

Bảng đầu file gồm ngày, người thực hiện, nhánh và PR, rồi đến các mục:

1. **Thay đổi:** phần vừa làm và cách dùng.
2. **Quyết định:** quy ước mới hoặc đánh đổi cần biết.
3. **Sự cố:** lỗi đã gặp và cách xử lý.
4. **Kiểm tra:** kết quả thực tế, tách test với lần chạy thật.
5. **Chưa kiểm tra.**
6. **Việc còn lại.**

Ghi đúng trạng thái PR, kể cả khi chưa merge. Không ghi secret hay dữ liệu người dùng thật.

## Danh sách

| Ngày | Lát cắt | Chủ đề |
|---|---|---|
| 2026-11-04 | R2 S7 | [Triage, làn companion và đánh giá qua API v2](2026-11-04_r2-s7_triage-lan-companion.md) |
| 2026-11-04 | R2 S7 | [Web chạy trên API v2 và hoàn thiện API v2](2026-11-04_r2-s7_web-chat-v2.md) |
| 2026-11-04 | R2 S7 | [Gộp khung trích dẫn và giám sát route v2](2026-11-04_r2-s7_khung-trich-dan-giam-sat-v2.md) |
| 2026-11-04 | R2 S7 | [Abstain khi hỏi chapter chưa có](2026-11-04_r2-s7_abstain-chapter-chua-co.md) |
| 2026-11-04 | R2 S7 | [Chấm độ có căn cứ, trích dẫn và ghi chú "anh"](2026-11-04_r2-s7_cham-can-cu-va-ghi-chu-anh.md) |
| 2026-11-04 | R2 S7 | [Khôi phục trường infobox bị mất do link interwiki](2026-11-04_r2-s7_sua-truong-interwiki-infobox.md) |
| 2026-11-04 | R2 S7 | [Báo riêng lỗi hết tiền của LLM](2026-11-04_r2-s7_bao-loi-het-tien-llm.md) |
| 2026-11-04 | R2 S7 | [Discord nhắn thường qua API v2](2026-11-04_r2-s7_discord-chat-v2.md) |
| 2026-11-04 | R2 S7 | [Persona v2 (bản nháp)](2026-11-04_r2-s7_persona-v2.md) |
| 2026-11-14 | R2 S7 | [Guard đầu ra cho ranh giới an toàn](2026-11-14_r2-s7_guard-ranh-gioi-an-toan.md) |
| 2026-11-14 | R2 S7 | [Đo persona v2 và golden trên corpus mới](2026-11-14_r2-s7_do-persona-v2-va-corpus-moi.md) |
| 2026-11-14 | R2 S7 | [Tập giữ lại cho bộ đánh giá](2026-11-14_r2-s7_tap-giu-lai-danh-gia.md) |
| 2026-11-15 | R2 S7 | [Đường lưu của lượt chat v2](2026-11-15_r2-s7_duong-luu-luot-chat.md) |
| 2026-11-15 | R2 S7 | [Hoàn quota khi client ngắt kết nối](2026-11-15_r2-s7_hoan-quota-khi-ngat-ket-noi.md) |
| 2026-11-15 | R2 S7 | [Job trích xuất trí nhớ cho v2](2026-11-15_r2-s7_job-tri-nho-v2.md) |
| 2026-11-15 | R2 S7 | [Sửa triage cho câu khen, câu chê và "tiếng Anh"](2026-11-15_r2-s7_sua-triage-cau-noi.md) |
| 2026-11-15 | R2 S7 | [Bước hiểu câu hỏi (ADV-003)](2026-11-15_r2-s7_buoc-hieu-cau-hoi.md) |
| 2026-11-15 | R2 S7 | [Báo lỗi hết tiền cho các adapter LLM còn lại](2026-11-15_r2-s7_bao-loi-het-tien-cac-adapter.md) |
| 2026-11-15 | Tổng hợp | [Handover tổng hợp: lỗi, đánh giá thất bại và trạng thái](2026-11-15_handover-tong-hop.md) |
| 2026-11-15 | R2 S7 | [Nhãn trường infobox trong trích dẫn](2026-11-15_r2-s7_nhan-truong-infobox-trong-trich-dan.md) |
| 2026-11-15 | R2 S7 | [Job hợp nhất core memory (MEM-005)](2026-11-15_r2-s7_hop-nhat-core-memory.md) |
| 2026-11-15 | R2 S7 | [Cửa sổ cắt theo token và summary cuộn](2026-11-15_r2-s7_cua-so-token-va-summary.md) |
| 2026-11-15 | R2 S7 | [Claim hai ngôn ngữ và lời dẫn theo giọng Chisa](2026-11-15_r2-s7_claim-song-ngu.md) |
| 2026-11-15 | R2 S7 | [Tải ngữ cảnh song song và chi phí từng lượt](2026-11-15_r2-s7_tien-to-prompt-va-chi-phi.md) |
| 2026-11-15 | R2 S7 | [Metric của bước hiểu câu hỏi (ADV-003)](2026-11-15_r2-s7_metric-hieu-cau-hoi.md) |
| 2026-11-15 | R2 S7 | [Đo gộp sau các PR ngày 15/11](2026-11-15_r2-s7_do-gop-sau-cac-pr.md) |
| 2026-11-15 | R2 S7 | [Phạm vi QUAL-004 và 20 ca out_of_scope mới](2026-11-15_r2-s7_pham-vi-qual004.md) |
| 2026-11-17 | R3 | [Mật khẩu Argon2id, rehash dần từ bcrypt (IAM-011)](2026-11-17_r3_argon2id.md) |
| 2026-11-17 | R3 | [Lõi RBAC phía máy chủ](2026-11-17_r3_rbac-core.md) |
| 2026-11-17 | R3 | [Cấp và thu hồi Chía-con](2026-11-17_r3_cap-thu-hoi-chia-con.md) |
| 2026-11-17 | R2 S7 | [Ảnh thực thể qua URL ký của server (KNW-010)](2026-11-17_r2-s7_anh-thuc-the.md) |
| 2026-11-16 | R2 S7 | [Độ tin cậy của phép đo: 429 reranker và ca out_of_scope](2026-11-16_r2-s7_do-tin-cay-cua-phep-do.md) |
