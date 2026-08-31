# 📘 Hướng Dẫn Ingestion Dữ Liệu Lore RAG & Parent-Child Architecture

> **Dự án**: Kuchiba Chisa — AI Companion & Game Knowledge Assistant  
> **Kiến trúc**: Multi-Collection Structure-Aware Chunking & Windowed Parent Hydration  
> **Thời gian cập nhật**: 31/08/2026

---

## 📑 Mục Lục
1. [Tổng Quan Hệ Thống Ingestion](#1-tổng-quan-hệ-thống-ingestion)
2. [Cấu Trúc Đa Collection trong Qdrant & PostgreSQL](#2-cấu-trúc-đa-collection-trong-qdrant--postgresql)
3. [Luồng Xử Lý 5 Pha (5-Phase Ingestion Pipeline)](#3-luồng-xử-lý-5-pha-5-phase-ingestion-pipeline)
4. [Các Bộ Chunking Theo Cấu Trúc (Structure-Aware Chunkers)](#4-các-bộ-chunking-theo-cấu-trúc-structure-aware-chunkers)
5. [Cơ Chế Windowed Parent Resolution (1200 Ký Tự)](#5-cơ-chế-windowed-parent-resolution-1200-ký-tự)
6. [Hướng Dẫn Sử Dụng Ingestion CLI](#6-hướng-dẫn-sử-dụng-ingestion-cli)

---

## 1. Tổng Quan Hệ Thống Ingestion

Hệ thống Ingestion của Kuchiba Chisa được thiết kế để xử lý toàn bộ kho dữ liệu Wiki game Wuthering Waves, chuyển hóa văn bản thô thành các vector ngữ nghĩa chất lượng cao được lập chỉ mục trong **Qdrant Vector Database** kết hợp bảng tra cứu tài liệu cha trong **PostgreSQL**.

### 🌟 Đặc điểm Nổi bật:
1. **Lớp Trung gian Bất biến `canonical.jsonl`**: Tách biệt hoàn toàn khâu Parse/Clean khỏi khâu Chunking/Embedding. Cho phép thử nghiệm nhiều chiến lược chunking mà không cần re-crawl dữ liệu.
2. **UUIDv5 Deterministic ID**: Tạo `chunk_id` cố định dạng `uuid5(NAMESPACE_OID, "{page_id}::{heading_path}::{chunk_index}")`. Đảm bảo tính nhất quán (idempotency) khi ingest lại nhiều lần.
3. **Phân Luồng Đa Collection**: Tự động phân chia chunks vào 3 collection riêng biệt (`character_lore`, `world_lore`, `story_lore`).
4. **Windowed Parent Resolution**: Lưu trữ toàn văn Markdown cha trong PostgreSQL, chỉ cắt cửa sổ $1200\text{ ký tự}$ khi truy xuất để tránh tràn context window.

---

## 2. Cấu Trúc Đa Collection trong Qdrant & PostgreSQL

```
                                  [ RAW WIKI DATA ]
                                          │
                                          ▼
                            [ CANONICAL DATASET (JSONL) ]
                                          │
                                          ▼
                         [ STRUCTURE-AWARE CHUNKERS ]
                                          │
                  ┌───────────────────────┴───────────────────────┐
                  ▼                                               ▼
     ┌────────────────────────┐                     ┌────────────────────────┐
     │  QDRANT VECTOR DB      │                     │  POSTGRESQL DATABASE   │
     │  (Dense Semantic Index)│                     │  (Full Markdown Store) │
     ├────────────────────────┤                     ├────────────────────────┤
     │ • character_lore       │                     │ • lore_parent_docs     │
     │ • world_lore           │                     │   (Full Parent Doc,    │
     │ • story_lore           │                     │    Heading Hierarchy,  │
     │ • memories             │                     │    Provenance URL)     │
     │ • guild_memories       │                     │                        │
     │ • image_memories       │                     │                        │
     └────────────────────────┘                     └────────────────────────┘
```

---

## 3. Luồng Xử Lý 5 Pha (5-Phase Ingestion Pipeline)

1. **Pha 1: Data Schemas & Validation**: Khởi tạo cấu trúc Pydantic v2 chuẩn hóa cho `RawPage`, `CanonicalPage` và `ChunkModel`.
2. **Pha 2: Sanitizer & Parsers**: 9 bước làm sạch regex wikitext, bóc tách MediaWiki tables `{| ... |}`, infobox templates và phân loại page type.
3. **Pha 3: Canonical Layer Builder**: Trích xuất cây tiêu đề phân cấp (Heading Tree), metadata song ngữ Anh/Việt và ghi ra file `data/canonical/canonical.jsonl`.
4. **Pha 4: Structure-Aware Chunking**: Tự động định tuyến chunking phù hợp theo cấu trúc nội dung.
5. **Pha 5: Embedding & Dual Storage Sync**: Sinh vector embeddings qua FastEmbed / ONNX, lưu chunks vào Qdrant và lưu parent markdown vào PostgreSQL `lore_parent_docs`.

---

## 4. Các Bộ Chunking Theo Cấu Trúc (Structure-Aware Chunkers)

- **`DialogueChunker`**: Chuyên xử lý hội thoại cốt truyện. Giữ nguyên ngữ cảnh nhân vật nói (`<Speaker>: ...`), không cắt đứt phân đoạn kịch tính.
- **`TableInlinerChunker`**: Chuyển đổi bảng thuộc tính, chỉ số vũ khí/echo thành các câu văn tự nhiên mạch lạc (Prose).
- **`GenericChunker`**: Xử lý văn xuôi và danh sách với cửa sổ trượt (Sliding Window: 400 tokens chunk size, 50 tokens overlap).

---

## 5. Cơ Chế Windowed Parent Resolution (1200 Ký Tự)

Để giải quyết vấn đề **Lost-in-the-Middle** và **Parent Bloat** khi nạp tài liệu cha:

1. **Truy vấn Vector**: Qdrant trả về Child Chunk khớp nhất kèm điểm tương đồng.
2. **Truy vấn PostgreSQL**: `LoreRetriever` truy vấn PostgreSQL `lore_parent_docs` bằng `parent_id` để lấy toàn văn Section cha.
3. **Cắt Cửa Sổ Ngữ Cảnh Tối Ưu**:
   - Xác định vị trí của Child Chunk trong văn bản cha.
   - Mở rộng đều sang 2 phía trước và sau để đạt tổng độ dài $1200\text{ ký tự}$.
   - Luôn giữ nguyên Header `# Heading` ở đầu khối để LLM hiểu rõ vị trí trong cây tri thức.

---

## 6. Hướng Dẫn Sử Dụng Ingestion CLI

Mở terminal tại thư mục gốc và sử dụng bộ công cụ dòng lệnh `app.infrastructure.ingestion.cli`:

```powershell
# 1. Làm sạch và tạo Canonical Dataset từ dữ liệu thô
python -m app.infrastructure.ingestion.cli parse-canonical

# 2. Thực hiện Chunking và lưu vào SQLite State DB
python -m app.infrastructure.ingestion.cli chunk

# 3. Sinh Embedding và nạp toàn bộ vào Qdrant & PostgreSQL
python -m app.infrastructure.ingestion.cli embed-and-upsert

# 4. Kiểm tra sức khỏe dữ liệu và thống kê số lượng vector
python -m app.infrastructure.ingestion.cli status
```
