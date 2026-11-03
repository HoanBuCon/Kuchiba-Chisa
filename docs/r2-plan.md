# Kế hoạch R2: Advanced RAG v2

Tài liệu này chia R2 thành các lát cắt giao được riêng. Yêu cầu vẫn lấy từ SRS mục 4 và 10.

## Điểm xuất phát

R1 đạt cổng thoát trên corpus `2026.11.03-4`: golden v2 đã duyệt đạt QUAL-003 ở mức truy hồi, 0 khối trùng khớp chính xác, 0 rác markup. Các số đo nằm ở [i4-retrieval.md](ingestion/i4-retrieval.md) và [knw-006-embedding.md](ingestion/knw-006-embedding.md).

## Lát cắt

| # | Nội dung | Yêu cầu chính | Trạng thái |
|---|---|---|---|
| S1 | `search_lore`: dịch câu hỏi, entity linking, truy hồi lai phía server, rerank có fallback, Evidence | ADV-002, ADV-004, ADV-006, ADV-010, KNW-001 | Xong phần lõi và index; adapter dịch làm ở S5 |
| S2 | `get_entity`, `find_entities`, `list_quests`, `get_quest` trên kho có cấu trúc | ADV-004, KNW-004 | Xong công cụ; định tuyến theo loại câu hỏi làm ở S3 |
| S3 | Định tuyến câu hỏi tất định, sửa sai tất định và abstain | ADV-001, ADV-002, ADV-007 | Xong |
| S4 | Composer gọi `ContextBuilder` tại chỗ, grounding, ảnh chụp trích dẫn | PER-001, PER-005, GRD-001..005 | Xong phần lõi |
| S5 | Thread, chế độ, `POST /api/v2/chat/turns` (SSE), ngân sách | CONV-001, MODE-001..007, ADV-001, ADV-009 | |
| S6 | Core memory, `recall_lite`, RESONA | MEM-001, MEM-002 | |
| S7 | Làn companion, triage; chạy song song hệ cũ, chuyển web rồi Discord | QUAL-001..004, QUAL-009 | |

Nội dung persona ở `context_builder.py` và `persona_loader.py` được giữ nguyên tại chỗ. Muốn chuyển sang tài sản có version thì phải có chủ dự án duyệt (PER-002).

## Quyết định từ số đo

| Quyết định | Căn cứ |
|---|---|
| Dịch mọi câu hỏi không phải tiếng Anh | Chỉ dịch khi không nhận diện được thực thể: 0,898 / 0,748; dịch mọi câu: 0,944 / 0,727 trước rerank |
| Runtime rerank top 15 | Jina p95: top 15 là 761 ms, top 30 là 2.452 ms, top 50 là 9.295 ms; PERF-009 yêu cầu 750 ms |
| Tra cứu có cấu trúc cho câu liệt kê | Đo trên golden: 24/24 dữ kiện của 6 câu liệt kê có trong bằng chứng |
| Reranker local làm fallback | MiniLM-L-6 top 15: 0,944 / 0,834, trung vị 687 ms |
| Ngưỡng abstain thận trọng: Jina 0,20, local -0,5 | Trên 108 câu trả lời được, không abstain nhầm câu nào. Với 6 câu ngoài phạm vi, Jina bắt được 2 câu theo điểm số, còn đường lui local không bắt được câu nào. Claim guard ở S4 vì vậy là bắt buộc |

## Xác minh claim xuyên ngữ

Guard cũ so khớp từ khoá nên không xác minh được claim tiếng Việt với bằng chứng tiếng Anh: chỉ giữ 13% claim đúng, phần còn lại rơi về trích dẫn tiếng Anh nguyên văn. Độ tương đồng embedding một mình không an toàn: claim đúng 0,884, đổi tên 0,867, phủ định 0,871.

Vì vậy `CrossLanguageClaimCheck` kiểm tra nguyên văn tên, số và phủ định so với bằng chứng, rồi mới yêu cầu similarity ≥ 0,80. Chỉ Composer mới dùng; hành vi của guard dùng chung và pipeline cũ không đổi. Hiệu chuẩn trên 224 claim thật:

| Loại | Tỷ lệ được chấp nhận |
|---|---|
| Claim đúng | 62% |
| Gắn sai trích dẫn | 0% |
| Đổi số | 0% |
| Phủ định | 1,4% |
| Đổi tên | 2,3% |

Chạy đầu cuối với LLM thật trên 24 câu trả lời được và 6 câu ngoài phạm vi: câu chỉ có trích dẫn tiếng Anh giảm từ 13 xuống 3, dữ kiện đúng từ 37/40 lên 39/40, và 6/6 câu ngoài phạm vi đều abstain.

**Giới hạn:** nhãn "claim đúng" là output của LLM, chưa được người kiểm từng câu; mẫu âm là biến đổi tự động; ngưỡng được đọc trên chính bộ này. Cần theo dõi trên câu hỏi thật. Nhóm câu chỉ khác nhau về nghĩa mà không đổi tên, số hay phủ định thì bộ kiểm tra này không phát hiện được.

## Rủi ro cần xác nhận

**PERF-003 (TTFT p50 ≤ 1,8 giây).** Dịch có trung vị 1,05 giây và rerank 0,4 giây, chưa tính thời gian đến token đầu của Composer. Vì vậy mục tiêu p50 có nguy cơ không đạt. Hướng giảm: cache bản dịch theo câu hỏi đã chuẩn hoá, thử model dịch nhanh hơn. Chỉ đề xuất đổi mục tiêu sau khi đo TTFT thật ở S5.

**PERF-007 (truy hồi p95 ≤ 150 ms).** Bộ đo cũ gọi Qdrant 4 lần tuần tự, hết trung vị 1.113 ms. S1 gộp thành một truy vấn với RRF phía server: p50 274 ms, p95 289 ms trên máy dev (Docker trên Windows, gồm cả sinh sparse BM25). Chất lượng giữ nguyên 0,944 / 0,834. Cần đo lại trên VPS.
