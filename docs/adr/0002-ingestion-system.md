# ADR-0002: Hệ thống ingestion tự động, chỉ dùng wiki

- Trạng thái: **Accepted**
- Ngày: 2026-10-31
- Người quyết định: chủ dự án (uỷ quyền chọn phương án đề xuất)
- Liên quan: [thiết kế ingestion](../ingestion/design.md), [rà soát SRS](../reviews/2026-10-31-srs-v2-audit.md), [SRS v2.1](../SRS_Chisa_v2_Advanced_Agentic_RAG.md) (ING-002/006/008, ING-013…018)

## Bối cảnh

- SRS v2.0 mô tả cách xử lý một trang (S0–S9) nhưng chưa có phần vận hành: phát hiện thay đổi, chống thoái lui, publish, lịch chạy, nâng cấp.
- Đo trên wiki: trong 7 ngày có 470/1.049 trang Tier A bị render lại do template, chỉ 93 trang có revision mới. Wiki có infobox JSON trong `pageprops`, không có Cargo/SMW. Không có trang "Honami City".
- Cổng release hiện tại đòi kiểm tra thủ công mỗi release, mâu thuẫn với mục tiêu tối thiểu Human In The Loop.
- Chủ dự án chỉ chấp nhận Fandom wiki làm nguồn.

## Quyết định

1. **D-ING-1** Tự publish khi cổng dữ liệu và cổng truy hồi đạt, và thay đổi nằm trong phong bì thường lệ; ngoài phong bì thì release ở `HELD`.
2. **D-ING-2** Tự rollback khi kiểm tra sau publish tụt.
3. **D-ING-3** Trễ ổn định 24 giờ (6 giờ ở chế độ ra bản).
4. **D-ING-4** Ingestion chạy bằng container one-shot do timer của host gọi, không nằm trong worker thường trực.
5. **D-ING-5** Không dùng orchestrator ngoài (Airflow, Dagster, Prefect).
6. **D-ING-6** Phạm vi văn bản R1 là Tier A; kho có cấu trúc phủ toàn wiki ngay từ R1.
7. **D-ING-7** Alias suy luận có bằng chứng, chỉ dùng cho entity linking sau khi eval chứng minh không tăng nhầm lẫn.
8. **D-ING-8** Chọn kênh lexical (sparse BM25 hay BM25 full-text index) bằng spike I0.

Kèm theo từ rà soát SRS: golden v2 tối thiểu 100 câu lore và 50 câu mỗi nhóm khác trước khi bật tự publish; truy hồi xuyên ngữ bằng entity linking song ngữ tất định (ADV-010); văn bản trí nhớ v2 lưu ở Postgres (MEM-011); RPO 24 giờ, RTO 4 giờ.

## Hệ quả

- Chu kỳ tuần bình thường không cần thao tác của người; dự kiến ≤ 1 lần can thiệp mỗi tháng.
- Trước khi golden v2 đủ cỡ mẫu, cổng truy hồi chỉ báo cáo, nên mọi release lúc đầu đều ở `HELD` và cần chủ dự án publish tay.
- Thêm cấu hình `config/ingestion/*.yaml` và 4 cảnh báo ingestion có runbook.
- `CorpusQualityReport` và luồng publish trong code phải sửa cho khớp ING-008.

## Phương án đã cân nhắc

| Phương án | Lý do không chọn |
|---|---|
| Đồng bộ chỉ theo `recentchanges` | Lỡ một cửa sổ là lệch vĩnh viễn; không bắt được thay đổi do template |
| Tải lại mọi trang `touched` | Vượt CAP-003 |
| Duyệt tay mỗi release | Trái mục tiêu tối thiểu HITL |
| Orchestrator ngoài | Thêm dịch vụ thường trực, tốn RAM, chỉ có một pipeline |
| Datamine, wiki Kuro | Chủ dự án không chấp nhận nguồn ngoài wiki |
