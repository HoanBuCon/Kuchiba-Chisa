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
| S5 | Thread, chế độ, `POST /api/v2/chat/turns` (SSE), ngân sách | CONV-001, MODE-001..007, ADV-001, ADV-009 | Xong, sau cờ `CHAT_V2_ENABLED` (mặc định tắt); chưa đo TTFT trên endpoint |
| S6 | Core memory, `recall_lite`, RESONA | MEM-001, MEM-002, MEM-007, EMO-001..003 | Xong đọc, recall, cảm xúc và API sửa tay; job tự cập nhật core memory (MEM-005, MEM-010) còn thiếu |
| S7 | Làn companion, triage; chạy song song hệ cũ, chuyển web rồi Discord | MODE-008, QUAL-001..006, QUAL-009 | Xong triage, làn companion, target đánh giá `--api v2` và web v2 sau cờ `VITE_CHAT_V2` (mặc định tắt); còn Discord |

Lệch nhỏ so với mục 7.1 của SRS: lượt v2 lưu ở bảng `thread_turns` thay vì thêm cột vào `messages`, vì `messages` bắt buộc có `user_id` và `conversation_id` mà khách vãng lai không có, và hệ cũ phải tiếp tục chạy. Gộp lại khi gỡ hệ cũ ở R6.

Nội dung persona ở `context_builder.py` và `persona_loader.py` được giữ nguyên tại chỗ. Muốn chuyển sang tài sản có version thì phải có chủ dự án duyệt (PER-002).

## Quyết định từ số đo

| Quyết định | Căn cứ |
|---|---|
| Dịch mọi câu hỏi không phải tiếng Anh | Chỉ dịch khi không nhận diện được thực thể: 0,898 / 0,748; dịch mọi câu: 0,944 / 0,727 trước rerank |
| Runtime rerank top 15 | Jina p95: top 15 là 761 ms, top 30 là 2.452 ms, top 50 là 9.295 ms; PERF-009 yêu cầu 750 ms |
| Tra cứu có cấu trúc cho câu liệt kê | Đo trên golden: 24/24 dữ kiện của 6 câu liệt kê có trong bằng chứng |
| Câu liệt kê do server trình bày, không gọi LLM | Khi thấy cả danh sách và đoạn dài, LLM bỏ qua danh sách và viết từ đoạn nhiễu. Danh sách từ tra cứu tất định nên không có gì để bịa |
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

## Đánh giá toàn bộ golden qua `/api/v2`

Dùng `python -m evals run --api v2`, corpus `2026.11.03-4`, LLM thật, 118 câu chấm được (2 câu nhiều phiên bị bỏ qua vì khách vãng lai không có trí nhớ dài hạn):

| Chỉ số | Trước S7 | Sau S7 | Mục tiêu |
|---|---|---|---|
| Độ đúng | 0,881 | 0,924 (khoảng tin cậy 95%: 0,861–0,959) | |
| Lore một bước | 0,925 | 0,950 | |
| Liệt kê, chi tiết thoại | 1,0 | 1,0 | |
| Nhiều bước | 0,556 | 0,444 | Chờ Agentic |
| Ngoài phạm vi được abstain | 5/6 | 6/6 | |
| Abstain nhầm (QUAL-004) | 6,2% | 3,6% | ≤ 5% |
| Precision của abstain (QUAL-004) | 0,417 | 0,6 | ≥ 0,90: **chưa đạt** |
| Xưng hô (QUAL-005) | 100% | 100% | 100% |
| Triage sai (QUAL-006) | | 0/125 lượt | ≤ 10% |

**Giới hạn:** luật triage và router được chỉnh ngay trên bộ này, nên số còn lạc quan. Bộ chấm chỉ tìm từ khoá: ví dụ `memory-002` được tính đúng dù Chisa nói về đồ uống của mình thay vì của người dùng, nên chất lượng làn companion chưa được đo thật. QUAL-001 và QUAL-002 chưa có phép đo riêng, và 2 câu nhiều phiên của QUAL-008 chưa chạy được. Các số này chưa đủ để bật v2 cho người dùng.

## Rủi ro cần xác nhận

**PERF-003 (TTFT p50 ≤ 1,8 giây, p95 ≤ 3,5 giây). Nợ kỹ thuật:** chưa có VPS để đo; chủ dự án quyết mục tiêu sau khi đo (14/11/2026). Đo qua HTTP thật trên máy dev, 10 lượt:

| Lượt | TTFT p50 | Tối đa | Ghi chú |
|---|---|---|---|
| Có cache bản dịch một phần | 2,15 giây | 3,87 giây | Câu liệt kê 0,8 giây vì không gọi Composer |
| Chưa có cache | 3,55 giây | 5,45 giây | Trước khi tách câu liệt kê |

Tổng thời gian đạt PERF-004 (p95 ≤ 8 giây). Riêng TTFT vẫn trên mục tiêu, vì câu trả lời phải được kiểm chứng xong mới gửi (GRD-001..003), nên token đầu tiên gần như đến cùng lúc với cả câu. `turn.started` và `evidence.added` thì đến sớm. Mẫu nhỏ và là máy dev, cần đo lại trên VPS. Nếu vẫn không đạt thì phải chọn giữa đổi mục tiêu và đổi cách đo; đây là quyết định của chủ dự án.

**PERF-007 (truy hồi p95 ≤ 150 ms).** Bộ đo cũ gọi Qdrant 4 lần tuần tự, hết trung vị 1.113 ms. S1 gộp thành một truy vấn với RRF phía server: p50 274 ms, p95 289 ms trên máy dev (Docker trên Windows, gồm cả sinh sparse BM25). Chất lượng giữ nguyên 0,944 / 0,834. Cần đo lại trên VPS.
