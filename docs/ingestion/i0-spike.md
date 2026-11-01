# Spike I0 — số đo và quyết định cho ingestion v2

| Thuộc tính | Giá trị |
|---|---|
| Ngày | 2026-11-01 → 2026-11-02 |
| Phạm vi | [Thiết kế ingestion](design.md) mục 10 (I0); [ADR-0002](../adr/0002-ingestion-system.md) D-ING-8; [ADR-0004](../adr/0004-inference-service.md); SRS ASM-002, KNW-006 |
| Môi trường | Windows 11, Python 3.11, Qdrant 1.20.0 dev (`127.0.0.1:6333`), nguồn: Fandom WuWa API ẩn danh |
| Mã thử nghiệm | Script dùng một lần, không đưa vào repo. Chỉ số liệu và quyết định được giữ lại ở đây |

## Tóm tắt quyết định

| # | Câu hỏi | Quyết định | Căn cứ |
|---|---|---|---|
| 1 | Parser HTML cho silver (I2) | **lxml** | Nhanh hơn BeautifulSoup 24–38 lần, đã có trong dependency |
| 2 | D-ING-8: kênh lexical | **Sparse BM25 do Qdrant sinh** (`Document(model="qdrant/bm25")`, modifier IDF) | Một mình: Hit@5 0,53 so với 0,34 của full-text; trong hybrid ngang nhau; latency thấp hơn; ổn định từ 1.15 |
| 3 | KNW-006: e5-small int8 thay fp32 | **Giữ fp32**, đánh giá lại khi golden v2 đạt ≥ 100 câu | int8 tiết kiệm ~330 MB và nhanh hơn 1,3 lần, nhưng dense-only mất 3/32 câu ở Hit@5 |
| 4 | Lớp có cấu trúc | `pageprops.infoboxes` đủ cho mọi họ trang Tier A có infobox | Phủ 100% (thuật ngữ 526/527); trang con kế thừa thực thể từ trang cha |
| 5 | Template chrome và content | Danh sách trong `app/config/ingestion/templates.yaml`; template chưa biết tính là content | Toàn bộ template sửa trong 7 ngày là navbox và một gallery |
| 6 | Vị trí cấu hình | `app/config/ingestion/*.yaml` thay vì `config/ingestion/` | Đóng gói cùng code trong image; cạnh `app/config/inference_settings.py` |

## 1. Nguồn wiki

### 1.1 Metadata Tier A

- `prop=info|pageprops|templates` cho toàn bộ Tier A: **44 request, 44 giây** ở nhịp 1 request/giây.
- 286 template khác nhau xuất hiện trên Tier A.
- Chi phí reconcile hằng ngày vì vậy chỉ ở mức vài chục request. Phần đắt là `action=parse` cho trang thực sự đổi.

### 1.2 `action=parse`

60 trang mẫu trải đều các họ trang:

| Chỉ số | Giá trị |
|---|---|
| Lỗi | 0 / 60 |
| Thời gian p50 / p95 | 0,75 s / 2,77 s |
| Kích thước gzip trung bình | khoảng 56 KB |

Với ngân sách 400 trang mỗi lần chạy (`max_pages_per_run`) và nhịp 1 giây, một lần chạy đầy ngân sách mất khoảng 7–15 phút. Bronze 400 trang chiếm khoảng 22 MB.

### 1.3 Độ phủ infobox (`pageprops.infoboxes`)

| Họ trang | Độ phủ |
|---|---|
| resonator, main_quest, lore, faction, region | 100% |
| terminology | 526 / 527 |
| Backstory, Voicelines, Forte, Archive (trang con) | 0%: kế thừa thực thể từ trang cha theo tiêu đề |

### 1.4 Template đổi gây chạm trang

- Template sửa trong 7 ngày: toàn bộ là navbox, cộng một template gallery.
- `Template:Resonator Navbox` nhúng vào 478 trang. Một lần sửa navbox làm `touched` của 478 trang thay đổi dù nội dung không đổi.
- Hệ quả cho change detection (ING-013):
  - `touched` đổi mà `revid` không đổi thì chỉ fetch lại khi một template **content** đổi;
  - template **chrome** được bỏ qua;
  - thiếu bước này, mỗi lần sửa navbox sẽ tiêu hết ngân sách fetch.

## 2. Parser HTML

Đo trên 300 trang HTML đã parse:

| Parser | ms / trang |
|---|---|
| BeautifulSoup + html.parser | 126 |
| BeautifulSoup + lxml | 80 |
| **lxml** | **3,3** |
| selectolax | 0,6 |

- selectolax nhanh nhất nhưng là dependency mới, API CSS hạn chế.
- lxml đã có sẵn, có XPath, đủ nhanh: 900 trang mất khoảng 3 giây.
- Chọn lxml.

## 3. Thử nghiệm retrieval

### 3.1 Thiết lập

| Thành phần | Chi tiết |
|---|---|
| Corpus | 851 trang Tier A, tách theo section, chunk ≤ 380 token (tokenizer e5): **12.492 chunk**, trung vị 947 ký tự |
| Truy vấn | 32 câu golden v2 có nhãn trang: 23 vi, 5 en, 2 teencode, 2 vi không dấu |
| Model dense | multilingual-e5-small, bản fp32 và bản int8 chính thức (`onnx/model_qint8_avx512_vnni.onnx`) |
| Chỉ số | Hit@5 và MRR@10 ở **mức trang** (chunk trùng trang được gộp) |
| Hybrid | RRF k = 60, trọng số bằng nhau, mỗi kênh lấy 50 |

### 3.2 Embedding fp32 và int8

| Bản | Nạp | RAM sau nạp | RAM đỉnh | Embed 12.492 chunk | Passage/s | Query |
|---|---|---|---|---|---|---|
| int8 | 16,1 s | 457 MB | 776 MB | 752 s | 16,6 | 3,9 ms |
| fp32 | 1,3 s | 794 MB | 1.107 MB | 992 s | 12,6 | 5,4 ms |

- Cosine giữa vector fp32 và int8 của cùng passage: trung bình 0,9942, thấp nhất 0,9846.
- RAM đo bằng peak working set trên Windows. Con số cgroup Linux của ADR-0004 vẫn là căn cứ cho ngân sách.

### 3.3 Chất lượng

| Biến thể | Hit@5 | MRR@10 | p50 (ms) | en | vi | teencode | vi không dấu |
|---|---|---|---|---|---|---|---|
| dense fp32 | **0,750** | 0,520 | 22,8 | 4/5 | **18/23** | 1/2 | 1/2 |
| dense int8 | 0,656 | 0,518 | 12,8 | 4/5 | 16/23 | 0/2 | 1/2 |
| sparse BM25 | 0,531 | 0,345 | 6,3 | 2/5 | 13/23 | 1/2 | 1/2 |
| full-text BM25 | 0,344 | 0,273 | 14,8 | 2/5 | 8/23 | 1/2 | 0/2 |
| hybrid fp32 + sparse | 0,719 | **0,531** | 34,9 | 4/5 | 17/23 | **2/2** | 0/2 |
| hybrid fp32 + full-text | 0,719 | 0,524 | 34,8 | 4/5 | 17/23 | 2/2 | 0/2 |
| hybrid int8 + sparse | **0,750** | 0,518 | 35,6 | 4/5 | 17/23 | 2/2 | 1/2 |

### 3.4 Diễn giải

- **Mẫu nhỏ.** 32 câu: mỗi câu là 3,1 điểm Hit@5. Chênh lệch dưới 2 câu không có ý nghĩa thống kê. Mọi kết luận dưới đây là tạm thời và chạy lại khi golden v2 đủ ≥ 100 câu lore.
- **D-ING-8.**
  - Sparse BM25 vượt full-text BM25 khi đứng một mình (+6 câu): full-text index tách từ theo khoảng trắng nên kém với tiếng Việt có dấu.
  - Trong hybrid, hai kênh cho kết quả gần như nhau.
  - Sparse nhanh hơn, ổn định lâu hơn và không cần payload index trên `text`.
  - Chọn sparse.
- **Hybrid chưa thắng dense.** Hit@5 hybrid fp32 thấp hơn dense 1 câu; MRR cao hơn một chút; teencode tốt hơn.
  - Chưa đủ để bỏ hybrid: ADV-004 và D11 yêu cầu kênh lexical cho tên riêng và truy vấn tiếng Anh, và bộ 32 câu chưa có nhiều câu loại đó.
  - Cần thử weighted RRF (Qdrant ≥ 1.17) và reranker khi golden đủ lớn.
- **int8.**
  - Mất 2 câu vi và 1 câu teencode ở dense-only.
  - Trong hybrid, khoảng cách biến mất (0,750).
  - Lợi ích là khoảng 330 MB RAM, cho phép hạ ngân sách inference từ 1.400 MB.
  - Vì chất lượng là ưu tiên và ngân sách hiện tại vẫn vừa (6.440 / 6.656 MB), giữ fp32.
  - Đánh giá lại cùng đợt chọn model KNW-006.

## 4. Việc cập nhật kèm theo

- [design.md](design.md) mục 6.6, mục 9 (bảng cấu hình) và bảng D-ING-8: ghi kết quả, đường dẫn cấu hình mới.
- [ADR-0002](../adr/0002-ingestion-system.md): D-ING-8 đã quyết.
- SRS 2.2.2: ASM-002 (kênh lexical đã chọn), ING-006 (đường dẫn cấu hình).
- Collection `i0_spike` trên Qdrant dev đã xoá sau thử nghiệm.
