# Bài học từ pipeline dữ liệu IndexBeast cho ingestion của Chisa

| Thuộc tính | Giá trị |
|---|---|
| Ngày | 2026-10-31 |
| Đối tượng | Repo IndexBeast (`D:\Hoc_Tap\Code\Du_An_Ca_Nhan\Elden-Ring`, nhánh `docs/s2-tv1-khao-sat-du-lieu` dựa trên `develop` sau PR #51) |
| Phương pháp | Đọc toàn bộ code dữ liệu (`backend/ingest/**`, `backend/core/text/**`, `core/ids.py`, `core/corpus.py`, `core/vector/schema.py`); đo trực tiếp artifact thật trong `backend/data` (chỉ đọc); đối chiếu với API của Fandom wiki (nguồn của Chisa) |
| Áp dụng cho | [Thiết kế ingestion của Chisa](design.md), [ADR-0002](../adr/0002-ingestion-system.md) |

---

## 0. Tóm tắt

IndexBeast đã chạy thật một vòng **crawl → clean → chunk → load → index** trên 4.164 trang wiki.gg và 10.371 ảnh.

**Điểm mạnh** là kỷ luật về provenance và bất biến:
- mỗi node bị loại đều có vị trí DOM và lý do;
- chunk phủ kín nguồn, không đổi chữ;
- mọi artifact có checksum;
- index có preflight và "tem nhận" (admission stamp);
- ảnh lưu theo hash nội dung, kèm ngữ cảnh xuất hiện.

**Điểm yếu** nằm ở ba chỗ, đều có số đo:
- **hình dạng dữ liệu đầu ra**: 47% chunk EN dưới 50 token; 2.068 thân chunk trùng y hệt;
- **hiệu năng lưu trạng thái**: ghi lại toàn bộ file JSON 1–6 MB sau mỗi trang, mỗi ảnh;
- **tính tăng dần**: mỗi lần chạy làm lại toàn bộ clean/chunk/embedding; không có release/alias.

Kết luận cho Chisa:
1. **Giữ hướng của ADR-0002.** Thiết kế đã tránh được phần lớn lỗi của IndexBeast: ID theo nội dung, cache theo stage, release + alias, `touched`.
2. **Lấy thêm 12 kỹ thuật cụ thể** (mục 3).
3. **Thêm 6 quy tắc** để không lặp lỗi của IndexBeast (mục 4), đáng chú ý nhất:
   - chặn **chunk vụn** bằng ngưỡng token tối thiểu và "thẻ infobox";
   - lưu trạng thái bằng **SQLite/JSONL** thay vì ghi lại cả file JSON.
4. **Ảnh**: làm được với chi phí thấp nếu lấy **thumbnail do server Fandom resize** và gắn ảnh với thực thể **qua dữ liệu có cấu trúc** (infobox JSON, thẻ `characters=` trên trang file), thay vì tải ảnh gốc. Ảnh trên Fandom là **fair use**, không phải CC BY-SA. Đây là mở rộng phạm vi so với SRS, **cần chủ dự án quyết định** (mục 5).

---

## 1. Bản đồ pipeline IndexBeast

| Stage | Module | Artifact | Ghi chú |
|---|---|---|---|
| Discover + crawl | `ingest/crawl/full.py`, `sources/wikigg.py`, `crawl/http.py` | `crawl_runs/<run>/inventory.json`, `checkpoint.json`, `report.json`; `raw/wikigg/snapshots/<pageid>/<revid>-<sha256>.json` | Duyệt category theo BFS, `prop=info` lô 50, `action=parse` theo title |
| Ảnh | `crawl/media.py` | `media/blobs/<sha[:2]>/<sha256>.<ext>`, manifest occurrence theo trang, `media/url-index.json` | `imageinfo` + extmetadata; Pillow verify |
| Clean | `core/text/html_clean.py`, `core/text/lore_policy.py`, `transform/full.py` | `clean_runs/<run>/filtered/*.json`, `processed/*.json`, CSV, `report.json` | Section phẳng theo heading; block có kiểu; nhật ký loại bỏ |
| Chunk | `core/text/chunking.py`, `chunk/full.py` | `chunk_runs/<run>/chunks.jsonl` (+ per-doc JSONL, review, coverage) | Token thật của e5, ≤ 450, overlap 50 |
| Load / index | `chunk/load_full.py`, `ingest/indexing.py`, `core/corpus.py`, `core/vector/schema.py` | Postgres `documents/chunks`; Qdrant `lore_chunks` (dense 384 + sparse BM25 IDF) | Preflight dry-run; admission stamp |
| Audit | `debug/corpus_readiness.py`, `chunk_readiness.py`, `raw_scope_study.py` | `research_runs/…` | Audit chỉ đọc, ghi ra thư mục mới |

**Số đo artifact thật** (đọc ngày 2026-10-31):

| Chỉ số | Giá trị |
|---|---|
| Crawl đầy đủ | 4.157 trang thành công + 7 lỗi chỉ do ảnh; **1,6 giờ** (lượt cuối: 2.527 cache hit, 1.637 tải mới) |
| Ảnh: lần xuất hiện | 65.593, trong đó **42.000 (64%) là icon giao diện bị loại** |
| Ảnh: duy nhất | 10.371 blob, **7,96 GB**; median 188 KB, p95 3,4 MB, max 14,8 MB; chỉ 20% có cạnh dài > 1.024 px |
| Ảnh: khử trùng theo hash | 23.586 lần xuất hiện hợp lệ → 10.371 blob (giảm 56%) |
| Ảnh: giấy phép | **100% `unknown_review_required`** (wiki.gg không trả extmetadata giấy phép) |
| Ảnh: rendition | 13.871 bản gốc, **9.715 `display_fallback`** (dùng URL hiển thị khi không tra được trang file) |
| Chunk | 23.765; EN 18.368 có median **52 token**, **47% dưới 50 token**; infobox EN median 27 token |
| File trạng thái | `checkpoint.json` 1,19 MB, `report.json` 1,22 MB (ghi lại sau mỗi trang); `media/url-index.json` **6,4 MB** (ghi lại sau mỗi ảnh tải) |

---

## 2. Cách đọc báo cáo

- **Lấy**: kỹ thuật tốt, nên đưa vào Chisa.
- **Tránh**: lỗi có số đo, cần quy tắc để không lặp lại.

Mỗi mục có file nguồn để kiểm lại.

---

## 3. Lấy: 12 kỹ thuật nên đưa vào Chisa

| # | Kỹ thuật | Ở IndexBeast | Áp dụng cho Chisa |
|---|---|---|---|
| L1 | **HTTP client có kỷ luật**: một nhịp chung cho mọi request (cả robots, ảnh); `Retry-After` dạng số giây **và** HTTP-date; dừng nếu phải chờ > 60 giây; chặn redirect ra ngoài host allowlist; giới hạn byte khi stream; kiểm tra robots trả HTML (dấu hiệu bị challenge) | `crawl/http.py` | Dùng nguyên mẫu cho S1; thêm `touched`/breaker theo ADR-0002 |
| L2 | **Chống vòng lặp continuation** (lưu token `continue` đã thấy) và retry riêng cho lỗi `maxlag` | `sources/wikigg.py` | Áp cho `allpages`, `prop=info`, `recentchanges` ở S0 |
| L3 | **Khoá chạy cấp hệ điều hành** (`msvcrt`/`fcntl`): OS tự nhả khi tiến trình chết | `crawl/full.py::run_lock` | Bổ sung cho advisory lock Postgres khi chạy offline (máy dev, không có DB) |
| L4 | **Tên snapshot = `<revid>-<sha256 nội dung>`** và kiểm hash khi đọc lại cache | `crawl/full.py` | Khớp L1 bronze của Chisa (`revid-render_hash`) |
| L5 | **Nhật ký loại bỏ có vị trí DOM + lý do** cho mọi node bị bỏ (`dom:<n>:<tag>#id`) | `html_clean.py::audit` | Đã có trong ING-003; dùng đúng định dạng vị trí này cho Explorer |
| L6 | **Ngữ cảnh tab (tabber)**: nhãn, anchor của panel; dùng để gắn ngôn ngữ/biến thể | `html_clean.py::variant_context` | Áp cho tab giới tính Male/Female ở Voicelines (E5) |
| L7 | **Thoại thành lượt có kiểu + bất biến**: ghép lại các lượt phải ra đúng văn bản gốc, sai thì raise | `html_clean.py::table` | Áp cho `div.dialogue` của Fandom (E1): mỗi lượt có speaker/trigger, kiểm bất biến |
| L8 | **Chia theo token thật bằng tìm kiếm nhị phân**, ưu tiên ranh giới câu/đoạn ở nửa sau, overlap đo bằng token; `embedding_text` tách khỏi `text`; prefix có title, section, variant, ngôn ngữ, speaker, trigger, header bảng | `core/text/chunking.py` | Dùng thuật toán này cho S4 |
| L9 | **Bất biến phủ kín**: không hở, không đổi chữ; tính lại token cho mọi chuỗi cuối cùng | `chunking.py::chunk_section`, `chunk/full.py` | Đã có trong ING-004; lấy test này làm property test |
| L10 | **Fingerprint logic của corpus** (`logical_content_sha256` bỏ qua `updated_at`) + `tokenizer_sha256` + checksum từng artifact | `chunk/full.py` | Đưa vào manifest release để so hai lần dựng có giống nhau không |
| L11 | **Preflight chỉ đọc trước khi ghi**: parse JSON nghiêm ngặt (cấm key trùng, cấm NaN), validate hợp đồng bằng pydantic, đếm lý do loại; dry-run là mặc định | `ingest/indexing.py` | Chính là `chisa ingest plan` / cổng dữ liệu S8 |
| L12 | **Kiểm schema collection, sai thì fail** (dense 384/cosine, sparse BM25/IDF, payload index đúng kiểu) và **tem nhận** trong payload, truy vấn chỉ khớp điểm có tem | `core/vector/schema.py`, `core/corpus.py` | Khớp D11 và ING-008; tem tương đương `corpus_version` + alias |

**Kỹ thuật cho ảnh** (dùng nếu Chisa làm ảnh, xem mục 5):
- blob định địa chỉ theo SHA-256, chia thư mục theo 2 ký tự đầu;
- một blob có nhiều "lần xuất hiện" (trang, section, caption, alt);
- `verify_image` bằng Pillow: chặn decompression bomb, giới hạn pixel, so MIME khai báo với định dạng thật;
- loại icon nhỏ (≤ 40 px) và icon giao diện;
- mặc định `unknown_review_required` khi không có giấy phép, **không bao giờ tự gán giấy phép**;
- bỏ qua tải lại nhờ `sha1` của `imageinfo`.

---

## 4. Tránh: lỗi có số đo và quy tắc tương ứng cho Chisa

| # | Lỗi ở IndexBeast | Bằng chứng | Nguyên nhân gốc | Quy tắc cho Chisa |
|---|---|---|---|---|
| T1 | **Chunk vụn** | 47% chunk EN < 50 token; infobox median 27 token; 2.068 thân trùng y hệt (`Slots Used: 1` ×190) | `lore_policy.context_groups` cắt một section thành nhiều record mỗi khi quyết định, ngôn ngữ hay loại block đổi; mỗi trường infobox thành một block riêng; mỗi lượt thoại thành một unit; bước chunk không gộp xuyên record | **Ngưỡng tối thiểu** khoảng 120 token: gộp unit kề nhau trong cùng section path (cùng collection, cùng ngôn ngữ) tới mục tiêu khoảng 250–400 token; **một thẻ infobox mỗi trang** (hồ sơ thực thể, đã có ở S3); thoại gộp **cửa sổ nhiều lượt** (E1), không một lượt một chunk; cổng dữ liệu đo tỷ lệ chunk < 60 token và số thân trùng |
| T2 | **ID không ổn định** | `chunk_id = uuid5(doc_id, ordinal)`; `record_id` chứa `VERSION` của cleaner | Định danh theo vị trí và phiên bản code | Đã giải quyết bằng ING-015 (ID theo nội dung); **không đưa phiên bản code vào ID** |
| T3 | **Artifact không di chuyển được** | `source_snapshot`, `manifest.json`, `input-fingerprints.json` ghi `D:\Index-Beast\...` | Ghi đường dẫn tuyệt đối | Manifest và artifact **chỉ ghi đường dẫn tương đối** so với gốc `data/ingestion/`; test kiểm không có đường dẫn tuyệt đối |
| T4 | **Ghi trạng thái O(n²)** | `checkpoint.json` + `report.json` khoảng 1,2 MB, ghi lại 3 lần mỗi trang (trung bình khoảng 0,6 MB × 3 × 4.164 trang ≈ 7–8 GB ghi đĩa); `url-index.json` tới 6,4 MB ghi lại sau mỗi ảnh tải (9.114 lần ≈ khoảng 30 GB) | Lưu trạng thái bằng một file JSON lớn, ghi đè toàn bộ | Trạng thái chạy ở **Postgres** (inventory) hoặc **SQLite** khi chạy offline; log tiến độ dạng **JSONL append-only**; báo cáo tổng hợp chỉ ghi ở cuối stage |
| T5 | **Chạy tiếp phải băm lại toàn bộ ảnh** | `valid_media` đọc và băm SHA-256 mọi blob (8 GB) ở mỗi lần chạy lại | Xác minh bằng nội dung thay vì metadata | Tin `(size, mtime, sha256 đã lưu)`; chỉ băm lại khi size/mtime đổi; lệnh `verify` riêng để kiểm toàn bộ khi cần |
| T6 | **Text bị kéo theo lỗi ảnh** | 7 trang có text đầy đủ nhưng report ghi `failed`/`partial` | Crawl text và ảnh chung một giao dịch trang | **Tách hai luồng**: text không bao giờ chờ ảnh; ảnh có hàng đợi và trạng thái riêng |
| T7 | **Lãng phí băng thông** | `Accept-Encoding: identity` cho mọi request HTML/JSON | Đơn giản hoá giới hạn byte | Bật gzip cho API; áp giới hạn trên số byte đã giải nén |
| T8 | **Lưu ảnh gốc** | 7,96 GB; phân bố đuôi dài (p95 3,4 MB); chỉ 20% ảnh > 1.024 px | Tải `url` gốc từ `imageinfo` | Lấy **thumbnail do server resize** (`iiurlwidth`), cạnh dài ≤ 512 px. Ước tính giảm hơn 90% dung lượng |
| T9 | **Chỉ theo `lastrevid`, không xử lý xoá** | `crawl/full.py` so `lastrevid`; không có tombstone | — | Đã có trong ING-002 và ING-013 |
| T10 | **Mỗi lần chạy làm lại toàn bộ** | Clean full rồi chunk full, mọi row giữ trong RAM rồi ghi CSV cuối; index embed lại tất cả | Không có khoá cache theo trang | Đã có trong ING-007 (cache theo stage) + cache vector theo nội dung |
| T11 | **Không có release, một collection dùng chung** | Qdrant `lore_chunks` duy nhất; 30 lượt chạy lẫn với bản cuối; điểm cũ không bị xoá | Thiếu khái niệm release | Đã có release + alias (ING-008); thư mục `gold/<corpus_version>/` là nơi duy nhất cho bản cuối |
| T12 | **Phạm vi suy bằng regex văn bản** | 60% chunk `release_scope=unknown`; `spoiler_level` trống ở mọi chunk | Đoán từ chữ trong lead/infobox bằng danh sách từ khoá DLC | Suy thuộc tính từ **dữ liệu có cấu trúc** (`pageprops.infoboxes`, category) và ghi nguồn suy luận (E7, E8); không đoán từ văn xuôi |
| T13 | **Chính sách làm sạch lệch nhu cầu sản phẩm** | Bỏ Weight, FP, bảng chỉ số trong khi chatbot cần trả lời thông số | Quyết định phạm vi trước khi có bộ câu hỏi | Phạm vi theo **golden set** (câu hỏi thật); dữ liệu số giữ ở **kho có cấu trúc** dù không embed |
| T14 | **Parser chậm** | `BeautifulSoup(..., "html.parser")` | Chọn mặc định | Dùng `lxml` (đã có trong requirements của Chisa); có thể đo thêm `selectolax` ở I0 |

---

## 5. Ảnh: có nên làm cho Chisa không?

### 5.1 Bối cảnh

SRS v2 chưa có yêu cầu ingest ảnh từ wiki. Hiện chỉ có:
- ảnh người dùng (`image_memories`, `recall_image`);
- đính kèm ảnh do server ký (SEC-RAG-002).

### 5.2 Kiểm chứng trên Fandom (2026-10-31)

| Câu hỏi | Kết quả |
|---|---|
| `imageinfo` có giấy phép không? | **Không.** `extmetadata` chỉ có `DateTime`, `ObjectName` |
| Trang file ghi giấy phép gì? | `{{Fairuse}}`, category `Files with Fairuse Disclaimer`: ảnh là tài sản có bản quyền của game, wiki dùng theo fair use |
| Có gắn ảnh với thực thể được không? | **Có, tất định**: wikitext trang file có `{{File |categories=Character Cards |characters=Chisa}}`; category `Chisa Images`; infobox JSON trong `pageprops` có mục `image` với tên file, URL, caption |
| Có thumbnail không? | **Có.** `iiurlwidth=512` trả `thumburl` do server resize (ví dụ ảnh 1080×1920, 532 KB → bản 512 px) |
| Quy mô | Wiki có 63.211 file. Ảnh infobox của khoảng 1.050 trang Tier A ước khoảng 1–2 nghìn ảnh; thumbnail khoảng 30–80 KB, tổng cộng **khoảng 50–150 MB** |

### 5.3 Đề xuất (nếu chủ dự án đồng ý mở phạm vi)

1. **Chỉ ảnh định danh thực thể**: ảnh infobox (card, chân dung) của các thực thể trong kho có cấu trúc. Không lấy gallery, icon, ảnh trang trí.
2. **Nguồn liên kết có cấu trúc**: mục `image` trong `pageprops.infoboxes`, cộng với thẻ `characters=` và category `<Thực thể> Images`. Không gắn ảnh theo section như IndexBeast.
3. **Thumbnail ≤ 512 px**:
   - lưu theo SHA-256 (cách của IndexBeast), verify bằng Pillow;
   - lưu kèm `file_page_url`, `revid`, `license="fair_use"`, `attribution`.
4. **Phục vụ qua server của Chisa** bằng URL ký (SEC-RAG-002), có cache. **Không hotlink** `static.wikia.nocookie.net` từ trình duyệt người dùng, vì sẽ lộ IP người dùng cho bên thứ ba và phụ thuộc uptime của Fandom.
5. **Không** OCR, không caption bằng model, không embedding ảnh ở v2. Ảnh chỉ là thuộc tính của thực thể (`get_entity` trả kèm ảnh).
6. Luồng ảnh **tách khỏi luồng text** (T6), chạy sau S5, có cổng riêng (số ảnh lỗi, ảnh mồ côi).

**Rủi ro**: fair use phù hợp với dự án cá nhân phi thương mại, hiển thị thumbnail kèm nguồn. Không phù hợp nếu sau này thương mại hoá hoặc phân phối lại bộ ảnh. Ghi rõ trong privacy/terms.

---

## 6. Thay đổi đề xuất cho thiết kế Chisa

| # | Thay đổi | Vị trí | Loại |
|---|---|---|---|
| C1 | Ngưỡng chunk tối thiểu (khoảng 120 token) + gộp unit kề nhau cùng section path tới khoảng 250–400 token; cổng dữ liệu đo tỷ lệ chunk < 60 token và số thân trùng | design §6.5, ING-004, gates.yaml | Sửa nhỏ, trong phạm vi |
| C2 | Artifact và manifest chỉ dùng đường dẫn tương đối; test chặn đường dẫn tuyệt đối | design §5, ING-007 | Sửa nhỏ |
| C3 | Trạng thái chạy ở Postgres/SQLite; log tiến độ JSONL append-only; không ghi đè file JSON lớn theo từng item | design §5, §6.1 | Sửa nhỏ |
| C4 | Xác minh artifact theo `(size, mtime, sha256 đã lưu)`; `chisa ingest verify` mới băm toàn bộ | design §7 | Sửa nhỏ |
| C5 | Bật gzip cho API; giới hạn byte trên dữ liệu đã giải nén | design §6.2 | Sửa nhỏ |
| C6 | Parser `lxml`; đo `selectolax` ở I0 | design §14 (I0) | Sửa nhỏ |
| C7 | Lấy L1, L2, L5–L12 làm chuẩn hiện thực cho S0–S8 (trích dẫn module IndexBeast làm tham chiếu) | design §6 | Bổ sung |
| C8 | **Ảnh thực thể từ wiki** (mục 5.3) | SRS: yêu cầu mới (ví dụ KNW-010, ING-019), pha R5 | **Mở phạm vi, cần chủ dự án quyết định** |

**Đã áp dụng (2026-10-31):** C1–C7 vào thiết kế và SRS v2.2 (ING-002/004/007). C8 được chủ dự án duyệt với một thay đổi: **lấy ảnh kích thước gốc** thay vì thumbnail; bản hiển thị ≤ 1.024 px sinh tại chỗ ([ADR-0003](../adr/0003-wiki-entity-images.md), ING-019, KNW-010).

---

## Phụ lục: file đã đọc và số đo

- Code: `backend/ingest/crawl/{http,full,media,scope}.py`, `backend/ingest/sources/wikigg.py`, `backend/ingest/artifacts.py`, `backend/core/text/{html_clean,lore_policy,chunking,normalize}.py`, `backend/ingest/filter/rules.py`, `backend/ingest/transform/{document,full}.py`, `backend/ingest/chunk/{full,load_full}.py`, `backend/ingest/indexing.py`, `backend/core/{ids,corpus}.py`, `backend/core/vector/schema.py`.
- Tài liệu: `docs/data-sources.md`, `docs/adr/003-chunking.md`, handover khảo sát dữ liệu ngày 31/10.
- Số đo: script Python chỉ đọc trên `backend/data/crawl_runs/s2-full-20261028` (report, checkpoint, 4.164 manifest ảnh) và `media/url-index.json`.
- Fandom: `imageinfo` (`iiprop=url|size|mime|sha1|extmetadata`, `iiurlwidth=512`) và wikitext trang `File:Chisa_Card.jpg`.
