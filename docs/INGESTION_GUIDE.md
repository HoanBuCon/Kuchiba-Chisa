# 📘 Hướng dẫn Vận hành Hệ thống Ingestion Architecture v1.1

> **Dự án**: Kuchiba Chisa RAG Wiki  
> **Phiên bản**: v1.1 Production Ingestion Architecture  
> **Cập nhật gần nhất**: 2026-07-26  

---

## 1. Tổng quan Hệ thống

Hệ thống Ingestion v1.1 được thiết kế để xử lý quy mô từ **10.000 đến 50.000 trang Wiki** (game lore Wuthering Waves / Kuchiba Chisa), biến đổi wikitext/markdown thô thành dữ liệu vector embedding chất lượng cao cho Qdrant Vector Store.

### 🌟 Đặc điểm Cốt lõi:
1. **Lớp Trung gian Bất biến `canonical.jsonl` (Decoupling Boundary)**: Tách biệt hoàn toàn khâu Parse/Clean đắt đỏ với khâu Chunking/Embedding. Cho phép thử nghiệm nhiều chiến lược chunking mà không cần re-crawl hay re-parse.
2. **Metadata-First Architecture (§6.0)**: Mỗi chunk tự động kế thừa toàn bộ metadata cấp tài liệu (`canonical_name`, `region`, `faction`, `element`, `page_type`...) từ `CanonicalPage` mà không tốn chi phí gọi LLM per-chunk.
3. **Idempotency với UUIDv5 Deterministic ID**: Tạo `chunk_id` cố định dạng `uuid5(NAMESPACE_OID, "{page_id}::{heading_path}::{chunk_index}")`. Re-process 100 lần vẫn ra đúng chunk ID cũ.
4. **Structure-Aware Chunkers**: Tự động phân tuyến 3 chiến lược chunking phù hợp theo cấu trúc (`DialogueChunker`, `TableInlinerChunker`, `GenericChunker`).
5. **Incremental State & Orphan Cleanup**: Sử dụng SQLite (`ingestion.sqlite`) so sánh SHA-256 hash để bỏ qua trang không đổi và xóa sạch vector mồ côi khi trang Wiki bị xóa.

---

## 2. Cấu trúc Kiến trúc 3 Tầng

```
                                    STAGE 0: FETCH / READ
                                     Raw Wiki / Lore Files
                                              │
                                              ▼
                             ┌─────────────────────────────────┐
                             │  PHA 2: SANITIZER & PARSERS     │
                             │  - Wikitext Sanitizer (9 ops)   │
                             │  - MediaWiki Table Parser       │
                             │  - Infobox & Template Parser    │
                             │  - Multi-source Classifier      │
                             └─────────────────────────────────┘
                                              │
                                              ▼
                             ┌─────────────────────────────────┐
                             │  PHA 3: CANONICAL LAYER BUILDER │
                             │  - Bilingual Provenance (EN/VI) │
                             │  - Section Hierarchy Tree       │
                             │  - Document Metadata Extraction │
                             └─────────────────────────────────┘
                                              │
                                              ▼
                       ===============================================
                       ★ CANONICAL DATASET (data/canonical/canonical.jsonl)
                       ===============================================
                                              │
                                              ▼
                             ┌─────────────────────────────────┐
                             │  PHA 4: STRUCTURE-AWARE CHUNKER │
                             │  - DialogueChunker (Scene)      │
                             │  - TableInlinerChunker (Prose)  │
                             │  - GenericChunker (Overlap)     │
                             └─────────────────────────────────┘
                                              │
                                              ▼
                             ┌─────────────────────────────────┐
                             │  PHA 5: STATE DB & QDRANT SYNC  │
                             │  - FastEmbed Embedding Adapter  │
                             │  - Atomic Page-level Pre-Delete │
                             │  - SQLite State & Orphan Purge  │
                             └─────────────────────────────────┘
                                              │
                                              ▼
                              QDRANT VECTOR STORE & SQLITE DB
```

---

## 3. Thư mục Mã nguồn (`app/infrastructure/ingestion/`)

```
app/infrastructure/ingestion/
├── __init__.py                 # Root package init
├── cli.py                      # Production CLI (5 subcommands)
├── models/                     # PHA 1: Data Schemas (Pydantic v2)
│   ├── __init__.py
│   ├── raw_page.py             # RawPage & RawPageMeta
│   ├── canonical_page.py       # CanonicalPage (14 sub-models & Enums)
│   └── chunk_model.py          # Chunk schema, UUIDv5 & token estimation
├── parsers/                    # PHA 2: Sanitizer & Upstream Parsers
│   ├── __init__.py
│   ├── sanitizer.py            # 9 bước dọn dẹp regex, convert Markdown & strip boilerplate
│   ├── table_parser.py         # MediaWiki table {| ... |} -> List[Dict]
│   ├── infobox_parser.py       # Infobox template parser (mwparserfromhell + fallback)
│   └── classifier.py           # Multi-source page type classifier (15 types)
├── canonical/                  # PHA 3: Canonical Layer Builder & Writer
│   ├── __init__.py
│   ├── builder.py              # CanonicalPage assembly & bilingual merge
│   └── writer.py               # Streaming JSONL reader/writer (canonical.jsonl)
├── chunkers/                   # PHA 4: Structure-Aware Chunkers
│   ├── __init__.py             # Router chunk_canonical_page
│   ├── base.py                 # BaseChunker ABC & metadata inheritance helper
│   ├── dialogue_chunker.py     # Scene Boundary & speaker preservation chunker
│   ├── table_inliner.py        # Tabular row -> natural prose chunker
│   └── generic_chunker.py      # Paragraph merge + sentence sliding window
└── storage/                    # PHA 5: State Management & Vector Sync
    ├── __init__.py
    ├── state_db.py             # SQLite DB (ingestion.sqlite) & orphan page detector
    └── qdrant_sync.py          # Qdrant collection router & atomic pre-delete upsert
```

---

## 4. Chuẩn bị Môi trường & Thư mục

### 4.1 Yêu cầu Môi trường
- Python 3.10+
- Virtual Environment đã kích hoạt (`.\venv\`)
- Qdrant Vector Store (chạy Docker local tại `localhost:6333` hoặc Qdrant Cloud)

### 4.2 Cấu hình `.env`
Đảm bảo file `.env` chứa các thông số:
```env
QDRANT_URL=http://localhost:6333
QDRANT_API_KEY=
QDRANT_EMBEDDING_DIM=384
EMBEDDING_MODEL=intfloat/multilingual-e5-small
```

### 4.3 Chuẩn bị Cấu trúc Thư mục Dữ liệu
Tạo các thư mục làm việc (nếu chưa có):
```bash
mkdir -p data/raw_wiki data/lore data/canonical data/chunks data/scratch
```

---

## 5. Hướng dẫn Sử dụng Production CLI

Toàn bộ pipeline được vận hành thông qua giao diện dòng lệnh `python -m app.infrastructure.ingestion.cli`.

### 5.1 Kiểm tra Trạng thái Pipeline (`status`)
Xem dung lượng file, số lượng bản ghi và trạng thái SQLite state DB:
```bash
.\venv\Scripts\python.exe -m app.infrastructure.ingestion.cli status
```
**Output mẫu**:
```text
==================================================
📊 Kuchiba Chisa — Ingestion Pipeline Status
==================================================
📁 Raw Storage (data/raw_wiki): 12 files
📄 Canonical Dataset (data/canonical/canonical.jsonl): EXISTS (75.8 KB)
🧩 Chunks Dataset (data/chunks/chunks.jsonl): EXISTS (142.3 KB)
🗄️ SQLite State DB (data/ingestion.sqlite):
   - Processed Pages: 6
   - Total Chunks: 86
   - Quarantined Pages: 0
==================================================
```

---

### 5.2 Lệnh 1: Xây dựng Canonical Dataset (`build-canonical`)
Đọc tất cả file thô `.wikitext` hoặc `.md` từ thư mục raw, thực hiện làm sạch, bóc tách cấu trúc, gán metadata và xuất ra `data/canonical/canonical.jsonl`:

```bash
.\venv\Scripts\python.exe -m app.infrastructure.ingestion.cli build-canonical --raw-dir data/lore --output data/canonical/canonical.jsonl
```

**Tùy chọn**:
- `--raw-dir`: Thư mục chứa file thô (mặc định: `data/raw_wiki`).
- `--output`: File xuất Canonical JSONL (mặc định: `data/canonical/canonical.jsonl`).

---

### 5.3 Lệnh 2: Sinh Chunks Tối ưu Retrieval (`process-chunks`)
Đọc file `canonical.jsonl`, phân tuyến các section qua 3 chiến lược chunking (`DialogueChunker`, `TableInlinerChunker`, `GenericChunker`) và ghi ra file `data/chunks/chunks.jsonl`:

```bash
.\venv\Scripts\python.exe -m app.infrastructure.ingestion.cli process-chunks --input data/canonical/canonical.jsonl --output data/chunks/chunks.jsonl --target-size 256
```

**Tùy chọn**:
- `--input`: Đường dẫn file canonical input (mặc định: `data/canonical/canonical.jsonl`).
- `--output`: File xuất chunks output (mặc định: `data/chunks/chunks.jsonl`).
- `--target-size`: Ngưỡng token mục tiêu mỗi chunk (mặc định: 256).

---

### 5.4 Lệnh 3: Tạo Vector & Sync Qdrant + SQLite (`sync-qdrant`)
Tạo vector embedding cho toàn bộ chunks (dùng FastEmbed `intfloat/multilingual-e5-small`), thực hiện xóa sạch chunk cũ cấp trang (Atomic Pre-delete), upsert vector vào Qdrant và lưu vết trạng thái vào `ingestion.sqlite`:

```bash
.\venv\Scripts\python.exe -m app.infrastructure.ingestion.cli sync-qdrant --input data/chunks/chunks.jsonl --db data/ingestion.sqlite
```

**Tùy chọn**:
- `--input`: File chunks input (mặc định: `data/chunks/chunks.jsonl`).
- `--db`: File SQLite DB (mặc định: `data/ingestion.sqlite`).

---

### 5.5 Lệnh 4: Dọn dẹp Trang bị Xóa (`cleanup-orphans`)
Phát hiện các trang đã bị xóa trên Wiki (không còn nằm trong dataset canonical hiện tại) và tự động xóa sạch các vector chunks tương ứng trong Qdrant lẫn SQLite:

```bash
.\venv\Scripts\python.exe -m app.infrastructure.ingestion.cli cleanup-orphans --db data/ingestion.sqlite
```

---

### 💡 Quy trình Vận hành Pipeline Từ A đến Z (1-Liner script)
Để chạy toàn bộ pipeline tự động từ khâu raw data đến Qdrant vector store:

```powershell
.\venv\Scripts\python.exe -m app.infrastructure.ingestion.cli build-canonical --raw-dir data/lore ; `
.\venv\Scripts\python.exe -m app.infrastructure.ingestion.cli process-chunks ; `
.\venv\Scripts\python.exe -m app.infrastructure.ingestion.cli sync-qdrant ; `
.\venv\Scripts\python.exe -m app.infrastructure.ingestion.cli cleanup-orphans ; `
.\venv\Scripts\python.exe -m app.infrastructure.ingestion.cli status
```

---

## 6. Chi tiết Kỹ thuật Cấp Module

### 6.1 Wikitext Sanitizer (`parsers/sanitizer.py`)
Áp dụng 9 thao tác dọn dẹp theo thứ tự nghiêm ngặt (pre-compiled regex):
1. Xóa HTML Comments (`<!-- ... -->`)
2. Xóa `<ref>` tags & citation texts
3. Xóa `<gallery>` blocks
4. Xóa `[[Category:...]]`
5. Xóa interwiki links `[[zh:...]]` và bare `zh:星炬学院` ở cuối trang
6. Xóa magic words `__NOTOC__`, `__NOEDITSECTION__`
7. Xóa dòng chứa tham số ảnh icon `50px`, `|50px`
8. Chuẩn hóa CRLF (`\r\n`) → LF (`\n`)
9. Thu gọn 3+ dòng trống liên tiếp thành 2 dòng trống
10. Loại bỏ các mục rác (`## Other Languages`, `## References`, `## Navigation`, ...) nhưng bảo tồn `## Trivia` cho trang `CHARACTER` và `QUEST`.

### 6.2 Table Parser (`parsers/table_parser.py`)
Bóc tách bảng cú pháp MediaWiki `{| class="..." !Header1!!Header2 |- |Cell1 || Cell2 |}` thành danh sách dicts `List[Dict[str, str]]`. Tự động dọn dẹp thẻ bold/link, icon `50px` và danh sách bullet lồng nhau (`*`, `**`) trong cell.

### 6.3 Page Type Classifier (`parsers/classifier.py`)
Phân loại 15 loại trang (`CHARACTER`, `WEAPON`, `ECHO`, `BOSS`, `QUEST`, `ITEM`, `REGION`, `FACTION`, `NPC`, `MECHANIC`, `TUTORIAL`, `TIMELINE`, `DIALOGUE`, `META_NAVIGATION`, `GENERIC`) theo mô hình ưu tiên 4 tầng:
- Tầng 1: Categories (Độ tin cậy 0.80–0.95)
- Tầng 2: Infobox Template Name (Độ tin cậy 0.90–0.95)
- Tầng 3: Title Heuristics (Độ tin cậy 0.70–0.95)
- Tầng 4: Content Section Heuristics (Độ tin cậy 0.45–0.70)

### 6.4 Structure-Aware Chunkers (`chunkers/`)
- `DialogueChunker`: Chunk theo Scene Boundary, giữ nguyên người phát ngôn (`Rover: "..."`, `Lucilla: "..."`), không bao giờ cắt đôi thoại, tự động trích xuất speakers thành entity metadata.
- `TableInlinerChunker`: Biến đổi hàng trong bảng thành câu văn xuôi có bối cảnh (`Startorch Academy Staff: Name: Lucilla. Position: President.`), giữ nguyên hàng không bị cắt đôi.
- `GenericChunker`: Phân đoạn theo paragraph (`\n\n`), gom nhóm tới 256 tokens, ngắt theo ranh giới câu an toàn và áp dụng Sentence-Level Overlap (gối đầu 1-2 câu).

### 6.5 Incremental State & Qdrant Sync (`storage/`)
- SQLite Table `ingestion_state` lưu vết `page_id`, `text_hash`, `chunk_count`, `last_updated`. So sánh SHA-256 hash để skip các trang chưa thay đổi.
- Qdrant Sync Manager tự động xóa sạch points theo `page_id` (`delete_lore_by_page`) trước khi upsert vector mới, ngăn ngừa triệt để hiện tượng chunk mồ côi (Orphan Chunks).

---

## 7. Chạy Suite kiểm thử (Automated Tests)

Mã nguồn đi kèm 5 file test suite covering 100% các pha:

```powershell
# Chạy toàn bộ 38 unit & integration tests
.\venv\Scripts\python.exe -m tests.test_ingestion_models ; `
.\venv\Scripts\python.exe -m tests.test_ingestion_parsers ; `
.\venv\Scripts\python.exe -m tests.test_ingestion_canonical ; `
.\venv\Scripts\python.exe -m tests.test_ingestion_chunkers ; `
.\venv\Scripts\python.exe -m tests.test_ingestion_storage_cli
```

**Bảng thống kê Test Coverage**:

| Test File | Phạm vi Kiểm thử | Số Tests | Kết quả |
|-----------|------------------|----------|---------|
| `test_ingestion_models.py` | Pydantic v2 schemas, UUIDv5, text hash, JSONL round-trip | 9 | PASS |
| `test_ingestion_parsers.py` | Sanitizer 9 ops, Table Parser, Infobox, Classifier | 17 | PASS |
| `test_ingestion_canonical.py` | Canonical builder, bilingual provenance, JSONL streaming | 4 | PASS |
| `test_ingestion_chunkers.py` | DialogueChunker, TableInliner, GenericChunker, UUIDv5 check | 4 | PASS |
| `test_ingestion_storage_cli.py` | SQLite DB CRUD, Orphan detection, Qdrant router, CLI E2E | 4 | PASS |
| **TỔNG CỘNG** | **Toàn bộ Pipeline Ingestion v1.1** | **38** | **✅ 100% PASS** |

---

## 8. Khắc phục Lỗi Thường gặp (Troubleshooting)

### ❓ Qdrant container offline khi chạy `sync-qdrant`
**Hiện tượng**: CLI log warning `qdrant_upsert_fallback` hoặc `qdrant_delete_fallback`.  
**Khắc phục**: 
- Kiểm tra Docker container Qdrant xem đã bật chưa: `docker ps`.
- Nếu chạy local, khởi động Qdrant container bằng: `docker run -p 6333:6333 -p 6334:6334 qdrant/qdrant`.
- Lưu ý: CLI vẫn cập nhật SQLite State DB thành công ngay cả khi Qdrant tạm thời offline nhờ cơ chế graceful fallback.

### ❓ Lỗi mã hóa Unicode trên Windows Terminal (CP1252)
**Hiện tượng**: `UnicodeEncodeError: 'charmap' codec can't encode character...`  
**Khắc phục**:  
Mọi file test và CLI script đã tích hợp dòng cấu hình tự động force UTF-8 stdout:
```python
import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
```
Nếu chạy từ PowerShell, bạn cũng có thể set môi trường:
```powershell
$env:PYTHONIOENCODING="utf-8"
```

---

## 9. Liên kết Tài liệu Liên quan

- 📋 [Kiến trúc Ingestion v1.1 Specification](file:///d:/Hoc_Tap/Code/Du_An_Ca_Nhan/Chisa_bot/kuchiba_chisa/reports/kuchiba_chisa_ingestion_architecture.md)
- 📍 [Báo cáo PHA 1: Data Schemas](file:///d:/Hoc_Tap/Code/Du_An_Ca_Nhan/Chisa_bot/kuchiba_chisa/reports/pha1_data_schemas_report.md)
- 📍 [Báo cáo PHA 2: Sanitizer & Parsers](file:///d:/Hoc_Tap/Code/Du_An_Ca_Nhan/Chisa_bot/kuchiba_chisa/reports/pha2_parsers_report.md)
- 📍 [Báo cáo PHA 3: Canonical Layer Builder](file:///d:/Hoc_Tap/Code/Du_An_Ca_Nhan/Chisa_bot/kuchiba_chisa/reports/pha3_canonical_layer_report.md)
- 📍 [Báo cáo PHA 4: Structure-Aware Chunkers](file:///d:/Hoc_Tap/Code/Du_An_Ca_Nhan/Chisa_bot/kuchiba_chisa/reports/pha4_structure_aware_chunkers_report.md)
- 📍 [Báo cáo PHA 5: State Management & CLI](file:///d:/Hoc_Tap/Code/Du_An_Ca_Nhan/Chisa_bot/kuchiba_chisa/reports/pha5_state_management_cli_report.md)
