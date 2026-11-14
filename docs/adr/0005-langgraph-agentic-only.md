# ADR-0005: Bộ điều phối Python thuần, LangGraph chỉ cho làn Agentic

- Trạng thái: **Accepted**
- Ngày: 2026-11-14
- Người quyết định: chủ dự án (uỷ quyền chọn kiến trúc và công nghệ tối ưu hiệu năng trên chi phí, VPS 4 vCPU / 8–10 GB)
- Liên quan: SRS v2.3.0 (mục 3.1, 3.2, 3.5.4, 3.5.6, 10; ASM-001, ASM-004; AGT-001…012; STD-AI-001, STD-AI-006), [thiết kế kiến trúc mục tiêu](../design/target-architecture.md)

## Bối cảnh

- SRS mô tả toàn bộ Agent Runtime là một đồ thị LangGraph. R2 lại hiện thực runtime bằng Python thuần (`app/application/chat_turns.py`) mà không ghi ADR; ASM-004 (kiểm chứng LangGraph) cũng chưa ai làm. ADR này giải quyết chỗ lệch đó bằng số đo.
- Advanced và companion là chuỗi bước cố định, tối đa 2 lời gọi LLM, xong trong vài giây. Agentic (R4) là vòng gọi công cụ không cố định số bước, phải dừng để hỏi lại người dùng rồi chạy tiếp ở lượt sau (AGT-008) và phát sự kiện tiến trình (AGT-009).

Spike ngày 14/11/2026 trên máy dev (Windows, Python 3.11, LangGraph 1.2.22, Postgres 16 trong Docker):

| Phép đo | Kết quả |
|---|---|
| RAM thêm khi nạp LangGraph | +45 MB lúc import, +57 MB sau khi chạy, mỗi tiến trình |
| Chi phí điều phối một lượt 7 bước, không checkpoint | p50 3,7 ms, p95 5,1 ms |
| Như trên, checkpoint Postgres | p50 36 ms, p95 48 ms (khoảng 5 ms mỗi bước) |
| `interrupt`, lưu Postgres, chạy tiếp bằng một saver mới | Chạy đúng |
| Stream sự kiện tuỳ biến từ node | Chạy đúng |
| Xoá checkpoint theo thread | Chạy đúng |
| Dependency kéo theo | 42 gói, gồm `langchain-core`, `langsmith`, `psycopg` 3 và `psycopg-pool`; 80 MB trên đĩa |
| Bảng do checkpointer tạo | `checkpoints`, `checkpoint_blobs`, `checkpoint_writes`, `checkpoint_migrations` |

Kết luận từ số đo: chi phí lúc chạy của LangGraph không đáng kể so với vài giây gọi LLM. Cái giá thật nằm ở bề mặt dependency, driver Postgres thứ hai (dự án đang dùng `asyncpg`), và việc checkpoint giữ nội dung của người dùng trong các bảng do thư viện quản lý.

## Quyết định

1. **Bộ điều phối lượt chat là Python thuần.** Ingress, guard, hiểu câu hỏi, làn companion, làn Advanced, Composer, guard an toàn, lưu trữ và RESONA không phụ thuộc LangGraph.
2. **Advanced RAG là một hàm DAG Python.** Không có bước nào do LLM chọn (ADV-001).
3. **Chỉ làn Agentic là đồ thị LangGraph**, nằm sau một port của tầng domain và hiện thực ở `infrastructure`. Công cụ `advanced_rag` (AGT-007) gọi lại chính hàm DAG ở mục 2. Câu trả lời cuối vẫn do Composer chung viết (PER-001).
4. Ràng buộc khi dùng LangGraph:
   - node gọi LLM qua `LLMGateway`, không dùng chat model của LangChain (STD-AI-001); công cụ là công cụ có kiểu, chỉ đọc của dự án (STD-AI-006);
   - checkpointer chính thức `AsyncPostgresSaver` với `psycopg[binary]`, pool nhỏ, chỉ trong container `api`;
   - bốn bảng checkpoint tạo bằng migration Alembic, không gọi `setup()` lúc chạy, để giữ quy tắc schema do migration sở hữu;
   - checkpoint bị xoá khi lượt hoàn tất; chỉ lượt đang chờ người dùng mới giữ checkpoint, có hạn; xoá dữ liệu người dùng phải xoá cả checkpoint theo thread;
   - tắt tracing của LangSmith; quan sát qua OTEL của dự án;
   - ghim phiên bản `langgraph`, `langchain-core`, `langgraph-checkpoint-postgres`.
5. ASM-004 coi là **đã kiểm chứng trên máy dev**. Còn phải kiểm chứng ở đầu R4: ASM-001 (DeepSeek gọi công cụ ở chế độ thinking) và RAM thực tế của `api` trên Linux.

## Hệ quả

- Phần R2 đã có không phải viết lại; đường đi của mọi người dùng thường không phụ thuộc framework.
- Agentic có sẵn interrupt, checkpoint và streaming đã được kiểm chứng, thay vì tự viết.
- Thêm 42 gói và một driver Postgres thứ hai vào image `api`; phải theo dõi cập nhật.
- Có hai kiểu điều phối trong hệ thống. Ranh giới là một lời gọi qua port vào đồ thị Agentic.
- Các yêu cầu AGT-001…012 không đổi, vì chúng quy định hành vi chứ không quy định công nghệ.

## Phương án đã cân nhắc

| Phương án | Vì sao không chọn |
|---|---|
| A. Toàn bộ runtime là LangGraph (SRS cũ) | Companion và Advanced không cần interrupt hay checkpoint. Lợi ích chỉ là một kiểu điều phối duy nhất, đổi lại mọi lượt của mọi người dùng phụ thuộc 42 gói và phải viết lại phần đã chạy |
| **B. LangGraph chỉ cho Agentic** | **Chọn** |
| C. Tự viết vòng Agentic bằng Python | Không thêm dependency, nhưng phải tự viết và tự bảo trì interrupt, checkpoint và streaming. Agentic còn mở rộng theo backlog (BL-001, BL-002), nên phần tự viết sẽ lớn dần. Giữ làm phương án dự phòng sau cùng một port |
