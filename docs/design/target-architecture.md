# Kiến trúc mục tiêu Chisa v2: Advanced RAG và Agentic RAG

| | |
|---|---|
| Ngày | 14/11/2026 |
| Phạm vi | Kiến trúc và công nghệ cho runtime v2, theo uỷ quyền của chủ dự án |
| Ràng buộc | VPS 4 vCPU, RAM tối thiểu 8 GB, tối đa 10 GB; một người phát triển; ưu tiên dịch vụ trả trước; Fandom wiki là nguồn duy nhất; persona v1 giữ nguyên văn |
| Tiêu chí | Hiệu năng trên chi phí: chất lượng câu trả lời và độ trễ đạt SRS với ít RAM, ít tiền LLM và ít thành phần nhất |

Tài liệu này chốt hướng thiết kế. Hiện trạng code xem [bản đồ tri thức](../knowledge-map.md); yêu cầu xem [SRS](../SRS_Chisa_v2_Advanced_Agentic_RAG.md). Số đo nào chưa có thì ghi là giả định ở mục 10.

## 1. Lựa chọn công nghệ

| Thành phần | Chọn | Căn cứ | Phương án loại |
|---|---|---|---|
| LLM | API DeepSeek (flash), qua `LLMGateway` | 4 vCPU không chạy nổi LLM local đủ chất lượng. Đo 14/11: khoảng 0,12 USD cho một đợt gồm golden 120 câu, 99 lượt persona và 99 lượt chấm, tức dưới 0,001 USD mỗi lượt (COST-002) | LLM tự host |
| LLM dự phòng | Một provider trả trước thứ hai có tool-calling, hỗ trợ đủ hợp đồng claim | Lần hết tiền 04/11 cho thấy một provider là điểm chết duy nhất (REL-001) | Chỉ một provider |
| Embedding | `multilingual-e5-small` fp32, ONNX, trong inference service | ADR-0004 và `knw-006-embedding.md`: nạp khoảng 0,82 GB, đạt cổng truy hồi | Model lớn hơn: không vừa RAM, chưa có bằng chứng tốt hơn |
| Reranker | Jina v3 qua API, top 15; MiniLM-L-6 local làm dự phòng | `i4-retrieval.md`: cùng Hit@5 0,944; MRR@10 0,877 so với 0,834. Rerank local tốn khoảng 0,7 giây trên 2 luồng CPU cho mỗi câu, nên dưới tải sẽ chiếm hết 4 vCPU | Local làm chính; Jina top 50 (p95 9,3 giây) |
| Kho vector | Qdrant 1.20: dense + BM25 phía server + RRF có trọng số | Đã dựng, đã qua gate, một truy vấn duy nhất | pgvector + FTS: bớt một container nhưng phải dựng và đo lại toàn bộ truy hồi. Xem lại nếu thiếu RAM |
| Điều phối lượt chat, Advanced | Python thuần | ADR-0005 | LangGraph toàn runtime |
| Điều phối Agentic | LangGraph 1.2, checkpoint Postgres | ADR-0005: thêm khoảng 57 MB mỗi tiến trình, 5 ms mỗi bước; interrupt và chạy tiếp đã kiểm chứng | Tự viết vòng lặp |
| Job nền | Hàng đợi bền trên Postgres (đã có) + transactional outbox | Không thêm broker; job được ghi cùng giao dịch với lượt chat | Celery, Kafka |
| Phát sự kiện | SSE trực tiếp cho companion và Advanced; Redis Streams cho Agentic | Lượt Advanced dài vài giây và gửi lại `turn_id` là nhận lại kết quả. Lượt Agentic dài tới 30 giây nên cần nối lại được (CH-001) | Redis Streams cho mọi làn ngay từ đầu |
| Dữ liệu | Postgres 16, Redis 7 | Đã có | |
| API, web, bot | FastAPI 2 worker, Caddy, React/Vite, discord.js | Đã có | |
| Giám sát | OTEL collector gửi ra dịch vụ hosted (hồ sơ M0) | Tự host tốn thêm khoảng 0,6 GB | Tự host Prometheus và Grafana |

## 2. Tổng thể

```
 Web SPA / Discord bot
        │
 Caddy ─► FastAPI ── middleware: body limit · rate limit · observability
            │
       Bộ điều phối lượt chat (Python)
        1 ingress: authn, quota, khoá thread, idempotent theo turn_id
        2 guard vào: che PII, chống injection
        3 hiểu câu hỏi: chọn làn + viết lại thành câu hỏi độc lập tiếng Anh
            ├─ companion ───────────────────────────────┐
            ├─ advanced: DAG Python ── bằng chứng ──────┤
            └─ agentic: đồ thị LangGraph ── sổ bằng chứng┤
        4 Composer chung (persona v2, cảm xúc, trí nhớ) ◄┘
        5 kiểm chứng claim · guard ranh giới an toàn
        6 commit một giao dịch: lượt + cảm xúc + outbox
        7 stream sự kiện
            │
  ┌─────────┼──────────┬───────────┬────────────┬──────────────┐
Postgres  Qdrant     Redis     Inference     LLM Gateway     Jina
                               (embed,       (DeepSeek,      (rerank)
                                rerank dự     dự phòng)
                                phòng)
  └── worker: trích xuất trí nhớ, summary, core memory, ingestion
```

Lớp tri thức (`search_lore`, `search_dialogue`, `get_entity`, `find_entities`, `list_quests`, `get_quest`) dùng chung cho Advanced và Agentic: Advanced gọi theo thứ tự cố định, Agentic gọi như công cụ.

## 3. Làn Advanced

```
tin nhắn + 1–2 lượt trước
   │
[U] Hiểu câu hỏi ── lời gọi LLM 1, nhỏ, có cache; bỏ qua khi luật tất định đã chắc
   │      trả {làn, câu hỏi độc lập tiếng Anh}
   ├──────────────► nạp cảm xúc và trí nhớ (chạy song song)
   ▼
[R] entity linking → Qdrant lai top 50 → rerank top 15 → top 8
    + tra cứu có cấu trúc (liệt kê quest, Resonator)
   ▼
[G] cổng đủ bằng chứng: ngưỡng rerank + luật tất định → không đủ thì abstain, không gọi LLM
   ▼
[C] Composer ── lời gọi LLM 2: {lời dẫn, claims[{nguồn, trích dẫn, claim_en, claim_vi}], lời kết, sentiment}
   ▼
[V] kiểm chứng: claim_en với trích dẫn (cùng ngôn ngữ) → claim_vi với claim_en (tên, số)
    lời dẫn và lời kết không được chứa tên riêng hay con số mới
   ▼
guard an toàn → commit → stream
```

Thay đổi so với code hiện tại, và lý do:

| # | Thay đổi | Lý do |
|---|---|---|
| 1 | Bước [U] thay cho bước dịch và regex triage: một lời gọi trả cả làn và câu hỏi độc lập | Truy hồi hiện bỏ qua lịch sử, nên câu hỏi nối tiếp mất chủ thể; triage regex được chỉnh trên chính bộ golden. Không tốn thêm lời gọi (ADV-009 giữ 2) |
| 2 | Claim có cả bản tiếng Anh và tiếng Việt | Kiểm chứng xuyên ngữ bằng embedding chỉ nhận 62% claim đúng; 45/118 câu trả lời golden phải hiện trích dẫn tiếng Anh. Kiểm cùng ngôn ngữ chặt hơn và ít loại nhầm hơn |
| 3 | Lời dẫn và lời kết do LLM viết theo giọng Chisa | Câu dẫn cố định làm câu trả lời lore mất chất nhân vật |
| 4 | Nạp trí nhớ song song với truy hồi | Chuỗi hiện tại tuần tự hoàn toàn |
| 5 | Lưu lượt, cập nhật cảm xúc và ghi outbox trong một giao dịch; khoá theo thread; hoàn quota khi lượt lỗi | EMO-003, MODE-005, REL-007 |
| 6 | Prompt xếp lại: persona → định dạng → core memory → phần biến động | PER-004: tăng phần đầu ổn định để trúng cache của provider. Làm trong builder của persona v2, không sửa file được bảo vệ |

Giữ nguyên: truy hồi lai và RRF, rerank top 15, luật liệt kê và luật chapter, danh sách do server trình bày, ngưỡng abstain, guard ranh giới an toàn, ngân sách 2 lời gọi LLM.

## 4. Làn Agentic (R4)

```
kế hoạch (LLM, prompt trung tính, tool-calling)
   │
kiểm tra lời gọi công cụ (allowlist, JSON Schema)
   │
chạy công cụ song song, chỉ đọc ─► sổ bằng chứng (id, nguồn, ACL, corpus_version, bước)
   │
đủ bằng chứng chưa? (tất định) ──► chưa, còn ngân sách ──► quay lại kế hoạch
   │                               └─ mơ hồ hoặc tốn kém ──► interrupt: hỏi lại, lưu checkpoint
   ▼
trả sổ bằng chứng cho Composer chung
```

- Ngân sách: tối đa 6 lời gọi LLM, 8 lời gọi công cụ, 30 giây (AGT-006). Hết ngân sách thì trả lời từ bằng chứng đã có hoặc abstain (REL-002).
- Planner không thấy persona và cảm xúc (AGT-001, EMO-004).
- Bulkhead riêng: giới hạn số lượt Agentic đồng thời theo tiến trình và toàn cục qua Redis (AGT-012).
- Sự kiện `agent.step` và `interrupt` đi qua Redis Streams; nội dung hiển thị là hằng số giọng Chisa (AGT-009).
- Checkpoint theo ADR-0005: xoá khi lượt xong, có hạn khi đang chờ.

## 5. Trí nhớ

| Lớp | Lưu ở | Ghi bởi | Giai đoạn |
|---|---|---|---|
| Cửa sổ ngắn hạn cắt theo token + summary cuộn | Postgres | Job nền theo ngưỡng token (CONV-002/003) | R2 |
| Core memory | Postgres | Người dùng sửa tay; job hợp nhất (MEM-005) | R2 |
| Trí nhớ tình tiết | Qdrant `memories` | Job trích xuất sau lượt, có lọc PII và consent | R2 |
| Dữ kiện có thời hạn hiệu lực | Postgres `facts` | Job hợp nhất (MEM-004) | R5 |

Mọi ghi nhớ đi qua outbox sau lượt. Hiện v2 chưa có job nào, nên đây là điều kiện bắt buộc trước khi bật v2.

## 6. Ngân sách tài nguyên

| Container | Giới hạn RAM | Ghi chú |
|---|---|---|
| postgres | 768 MB | Thêm bảng checkpoint, outbox |
| redis | 256 MB | Thêm khoá thread, Streams cho Agentic |
| qdrant | 1.200 MB | Khoảng 10 nghìn chunk; có thể hạ sau khi đo trên VPS |
| inference | 1.400 MB | e5-small và reranker dự phòng |
| api (2 worker) | 1.200 MB | LangGraph thêm khoảng 115 MB cho 2 tiến trình, vẫn trong giới hạn |
| worker | 700 MB | |
| discord | 300 MB | |
| web + caddy | 256 MB | |
| otel-collector | 200 MB | |
| **Tổng** | **khoảng 6,4 GB** | Compose đo 6.440 MB, gồm vài container phụ |

**Kết luận về cấu hình:** thiết kế này vừa gói **8 GB**, còn khoảng 1,6 GB cho hệ điều hành và page cache. Gói 10 GB không cần cho kiến trúc. Chỉ nên nâng khi số đo trên VPS cho thấy thiếu, hoặc khi muốn tự host giám sát (khoảng 0,6 GB).

CPU: tải nặng nhất tại chỗ là embedding và rerank dự phòng. Vì vậy rerank chính đi qua API, và rerank local có giới hạn số lượt đồng thời.

## 7. Kế thừa từ codebase cũ

| Giữ và dùng tiếp | Thay bằng thiết kế mới | Gỡ ở R6 |
|---|---|---|
| `LLMGateway`, các guard, che PII | Pipeline 12 stage → bộ điều phối lượt chat | `chat_pipeline/`, `rag/` cũ, `tools/` cũ |
| RESONA (`emotion_engine`, `state_manager`) | Intent và tool routing → bước hiểu câu hỏi | Visualizer, ingestion legacy |
| Persona v1 nguyên văn, persona v2 | RAG cũ → lớp tri thức v2 | Bảng legacy (`pipeline_jobs`, `chunk_state`…) |
| Hàng đợi bền và worker | Guard claim cũ → kiểm chứng hai ngôn ngữ | `/api/v1` sau khi mọi client đã chuyển |
| Auth, rate limit, quota, quyền riêng tư | | |
| Data plane ingestion v2, inference service, giám sát | | |
| Tính năng cộng đồng (transcript, topic summary, ambient mood): chuyển thành nguồn ngữ cảnh cho v2 | | |

## 8. Thứ tự thực hiện

1. **Đánh giá vững trước:** tách tập giữ lại, chạy lặp, thêm case lore nhiều lượt. Mọi bước sau đo trên tập chưa bị chỉnh.
2. **Bước hiểu câu hỏi** (mục 3, thay đổi 1).
3. **Đầu ra có căn cứ hai ngôn ngữ và lời dẫn theo giọng Chisa** (thay đổi 2, 3).
4. **Đường commit:** một giao dịch, outbox, khoá thread, hoàn quota; job trí nhớ và summary (thay đổi 5, mục 5).
5. **Thứ tự prompt và đo chi phí** (thay đổi 6, COST-001); nạp song song (thay đổi 4).
6. **Provider dự phòng; ảnh thực thể trong câu trả lời** (KNW-010).
7. Qua cổng R2 → R3 IAM → R4 Agentic trên LangGraph.

Mỗi bước là một PR có test, số đo trước và sau, và báo cáo bàn giao.

## 9. Đánh đổi đã chấp nhận

- Phụ thuộc API ngoài cho LLM và rerank: rẻ và nhẹ RAM, đổi lại cần provider dự phòng và alert hết tiền.
- Hai kiểu điều phối (Python và LangGraph): đổi lại đường đi thường ngày không phụ thuộc framework.
- Claim hai ngôn ngữ làm tăng token đầu ra của Composer; đổi lại kiểm chứng chặt hơn và bớt trích dẫn tiếng Anh.
- SSE của Advanced chưa nối lại được: chấp nhận vì lượt ngắn và có `turn_id`.

## 10. Giả định còn phải kiểm chứng

| Giả định | Kiểm chứng khi nào |
|---|---|
| Claim hai ngôn ngữ nâng tỷ lệ chấp nhận claim đúng mà không tăng claim sai | Bước 3, trên tập giữ lại |
| Bước hiểu câu hỏi không làm giảm độ đúng một lượt và sửa được câu nối tiếp | Bước 2 |
| Xếp lại prompt làm tăng cache-hit và giảm chi phí | Bước 5 |
| DeepSeek gọi công cụ được ở chế độ thinking (ASM-001) | Đầu R4 |
| RAM và độ trễ trên Linux khớp số đo trên máy dev; CAP-001 | Khi có VPS (PERF-003 đang là nợ) |
