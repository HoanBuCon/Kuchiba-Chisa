# KNW-006: chọn model embedding

| Thuộc tính | Giá trị |
|---|---|
| Ngày đo | 2026-11-04 |
| Corpus | `2026.11.03-1`, 6.264 chunk `lore_canon` |
| Bộ câu hỏi | Golden v2, 108 câu truy hồi, chủ dự án đã duyệt |
| Quyết định | **Giữ `intfloat/multilingual-e5-small` fp32** |

## Cách đo

- Tìm dense chính xác bằng tích vô hướng, kết hợp kênh BM25 và hai kênh thực thể bằng RRF, giống bộ đo `evals/retrieval.py`.
- Mỗi model chạy trong một tiến trình riêng với 2 luồng, để số RSS không lẫn nhau.
- `Dịch` dùng câu hỏi tiếng Anh đã đóng băng (ADV-010). `Dịch + rerank` thêm MiniLM-L-6 top 15. `Tiếng Việt` dùng nguyên câu hỏi gốc, tức trường hợp bước dịch lỗi.
- Mỗi ô ghi Hit@5 / MRR@10. RSS đo lúc model vừa nạp, gồm cả các thư viện và dữ liệu của bộ đo.

## Kết quả

| Model | Chiều | Dịch | Dịch + rerank | Tiếng Việt | RSS sau nạp (MB) | Query (ms) | Embed corpus (phút) |
|---|---|---|---|---|---|---|---|
| **e5-small fp32** | 384 | **0,944** / 0,725 | **0,944** / 0,834 | **0,852** / 0,653 | 887 | 10 | 9,3 |
| e5-small int8 | 384 | 0,935 / 0,732 | 0,926 / 0,835 | 0,833 / 0,660 | 554 | 4 | 5,3 |
| bge-base-en-v1.5 (Q) | 768 | 0,898 / 0,695 | 0,917 / 0,829 | 0,759 / 0,584 | 609 | 25 | 25,6 |
| bge-small-en-v1.5 (Q) | 384 | 0,907 / 0,688 | 0,926 / 0,807 | 0,778 / 0,593 | 344 | 8 | 8,0 |
| nomic-embed-text-v1.5-Q | 768 | 0,917 / 0,729 | 0,935 / 0,828 | 0,704 / 0,575 | 375 | 12 | 13,5 |
| arctic-embed-s | 384 | 0,917 / 0,728 | 0,917 / 0,827 | 0,769 / 0,548 | 367 | 8 | 7,3 |
| paraphrase-multilingual-MiniLM-L12-v2 (Q) | 384 | 0,870 / 0,690 | 0,870 / 0,781 | 0,806 / 0,665 | 711 | 6 | 2,9 |

`(Q)` là bản lượng tử hoá do fastembed phân phối.

## Quyết định và lý do

1. **Giữ e5-small fp32.** Model này có Hit@5 cao nhất ở cả ba cấu hình và không có model nào vượt rõ về MRR@10. Đổi model còn đòi hỏi embed lại đồng thời lore và trí nhớ (MEM-011).
2. **Đa ngữ vẫn có giá trị.** Khi bước dịch lỗi, e5-small giữ Hit@5 0,852, trong khi các model tiếng Anh giảm còn 0,70–0,78. Đây là đường lui của R2.
3. **Chưa dùng int8.** Bản này tiết kiệm 333 MB và nhanh hơn, nhưng trượt thêm 2 câu khi có rerank. Chênh lệch nằm trong sai số của bộ 108 câu, nên int8 vẫn là phương án dự phòng khi inference service thiếu RAM, ví dụ khi bật reranker local ở R2.

## Giới hạn

- **`bge-m3` chưa được đo.** Model này không có sẵn trong danh mục fastembed đang dùng, và các model cỡ tương tự trong danh mục có file từ 2 GB, vượt giới hạn 1.400 MB của inference service (ADR-0004). Các model đa ngữ lớn (`multilingual-e5-large`, `jina-embeddings-v3`) không được đo vì lý do này.
- Bộ câu hỏi cũng là bộ đã dùng để chọn pipeline, nên số tuyệt đối có thể lạc quan. So sánh tương đối giữa các model ít bị ảnh hưởng hơn.
- RSS chưa phải số đo trong inference service thật. Cần đo lại khi bật reranker local cùng model embedding.
