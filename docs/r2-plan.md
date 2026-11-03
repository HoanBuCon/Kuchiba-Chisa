# Kế hoạch R2: Advanced RAG v2

Tài liệu này chia R2 thành các lát cắt giao được riêng. Yêu cầu vẫn lấy từ SRS mục 4 và 10.

## Điểm xuất phát

R1 đạt cổng thoát trên corpus `2026.11.03-4`: golden v2 đã duyệt đạt QUAL-003 ở mức truy hồi, 0 khối trùng khớp chính xác, 0 rác markup. Các số đo nằm ở [i4-retrieval.md](ingestion/i4-retrieval.md) và [knw-006-embedding.md](ingestion/knw-006-embedding.md).

## Lát cắt

| # | Nội dung | Yêu cầu chính | Trạng thái |
|---|---|---|---|
| S1 | `search_lore`: dịch câu hỏi, entity linking, truy hồi lai phía server, rerank có fallback, Evidence | ADV-002, ADV-004, ADV-006, ADV-010, KNW-001 | Xong phần lõi và index; adapter dịch làm ở S5 |
| S2 | `get_entity`, `list_quests`, `get_quest` trên kho có cấu trúc | ADV-004, KNW-004 | |
| S3 | Sửa sai tất định và abstain | ADV-007 | |
| S4 | Composer gọi `ContextBuilder` tại chỗ, grounding, ảnh chụp trích dẫn | PER-001, GRD-001..005 | |
| S5 | Thread, chế độ, `POST /api/v2/chat/turns` (SSE), ngân sách | CONV-001, MODE-001..007, ADV-001, ADV-009 | |
| S6 | Core memory, `recall_lite`, RESONA | MEM-001, MEM-002 | |
| S7 | Làn companion, triage; chạy song song hệ cũ, chuyển web rồi Discord | QUAL-001..004, QUAL-009 | |

Nội dung persona ở `context_builder.py` và `persona_loader.py` được giữ nguyên tại chỗ. Muốn chuyển sang tài sản có version thì phải có chủ dự án duyệt (PER-002).

## Quyết định từ số đo

| Quyết định | Căn cứ |
|---|---|
| Dịch mọi câu hỏi không phải tiếng Anh | Chỉ dịch khi không nhận diện được thực thể: 0,898 / 0,748; dịch mọi câu: 0,944 / 0,727 trước rerank |
| Runtime rerank top 15 | Jina p95: top 15 là 761 ms, top 30 là 2.452 ms, top 50 là 9.295 ms; PERF-009 yêu cầu 750 ms |
| Reranker local làm fallback | MiniLM-L-6 top 15: 0,944 / 0,834, trung vị 687 ms |

## Rủi ro cần xác nhận

**PERF-003 (TTFT p50 ≤ 1,8 giây).** Dịch có trung vị 1,05 giây và rerank 0,4 giây, chưa tính thời gian đến token đầu của Composer. Vì vậy mục tiêu p50 có nguy cơ không đạt. Hướng giảm: cache bản dịch theo câu hỏi đã chuẩn hoá, thử model dịch nhanh hơn. Chỉ đề xuất đổi mục tiêu sau khi đo TTFT thật ở S5.

**PERF-007 (truy hồi p95 ≤ 150 ms).** Bộ đo cũ gọi Qdrant 4 lần tuần tự, hết trung vị 1.113 ms. S1 gộp thành một truy vấn với RRF phía server: p50 274 ms, p95 289 ms trên máy dev (Docker trên Windows, gồm cả sinh sparse BM25). Chất lượng giữ nguyên 0,944 / 0,834. Cần đo lại trên VPS.
