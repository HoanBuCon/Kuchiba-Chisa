# I4: đo truy hồi trên corpus thật

| Thuộc tính | Giá trị |
|---|---|
| Corpus | `2026.11.02-7`, 1.054 trang Tier A, 9.872 chunk |
| Công cụ | `python -m evals.retrieval` (không gọi LLM; `--mode reranked` tốn token Jina) |
| Mục tiêu | QUAL-003: Hit@5 ≥ 0,90, MRR@10 ≥ 0,80 trên ≥ 100 câu lore |

**Kết luận: chưa đủ căn cứ để nói đạt QUAL-003.** Các số dưới đây tốt, nhưng mẫu còn nhỏ và đợt 2 quá dễ.

## Ablation trên đợt 1 (32 câu, nhiều câu về Chisa)

| Chiến lược (chỉ canon, ADV-005) | Hit@5 | MRR@10 |
|---|---|---|
| Dense | 0,688 | 0,588 |
| Dense + BM25 | 0,844 | 0,625 |
| Dense + BM25 + gắn thực thể | 0,906 | 0,719 |
| Như trên, sau khi sửa nhãn `enum-002` | 0,938 | 0,729 |
| + `jina-reranker-v2-base-multilingual`, 15 ứng viên | 0,938 | 0,760 |
| + `jina-reranker-v2-base-multilingual`, 30 ứng viên | 0,938 | 0,698 |
| **+ `jina-reranker-v3`, 15 ứng viên** | **0,938** | **0,810** |
| + `jina-reranker-v3`, 30 ứng viên | 0,906 | 0,807 |

Model được chọn trên chính 32 câu này, nên số 0,810 dễ lạc quan. Nhóm câu liệt kê đạt 4/6: hai câu còn lại cần tra kho có cấu trúc (ADV-004), và phần đó chưa làm.

## Đợt 2 (40 câu, chưa dùng để tinh chỉnh, chưa được duyệt)

| Chiến lược | Hit@5 | MRR@10 | MRR@10 nhóm thoại |
|---|---|---|---|
| Dense + BM25 + gắn thực thể | 1,000 | 0,899 | 0,45 |
| + `jina-reranker-v3`, 15 ứng viên | 1,000 | 0,946 | 0,767 |

Đợt 2 **dễ hơn thực tế**: câu hỏi được soạn sau khi đọc đúng trang đích, và hầu hết nêu thẳng tên trang, nên bước gắn thực thể gần như chắc chắn trúng. Đợt này cho biết cách làm không chỉ đúng với Chisa, chứ chưa cho biết hệ thống xử lý câu hỏi diễn đạt tự nhiên ra sao.

## Reranker

- Chọn Jina vì trả trước: mua gói token theo khoá, hết thì dừng. Phải tắt auto top-up.
- Mỗi câu gửi khoảng 3.100 token với 15 ứng viên; độ trễ p50 khoảng 400–450 ms.
- Giới hạn tốc độ của khoá thấp: lần đo không giãn cách có 12–26/32 câu bị từ chối và rơi về thứ tự chưa rerank, nên kết quả đó đã bị loại. Runtime phải xử lý trường hợp này bằng fallback (ADV-006) và phải đo lại với lưu lượng thật.
- Chỉ wiki công khai và câu hỏi đã qua lọc PII được gửi ra ngoài.

## Việc còn thiếu

- Đợt golden khó hơn: không nêu tên trực tiếp, nhiều bước suy luận, nhân vật ngoài Chisa.
- Tra kho có cấu trúc cho câu liệt kê.
- Fusion hiện chạy phía client trong bộ đo; ADV-004 yêu cầu RRF có trọng số phía server ở runtime.


## Release `2026.11.03-1`: gates (2026-11-03)

Data gate passed: 9,872 chunks, 0 over limit, 0 duplicates, 0 uncovered, 0 quarantined, with 8 owner-approved safety exceptions.

| Mode | Cases | Hit@5 (95% CI) | MRR@10 |
|---|---|---|---|
| `linked` (free, used by the gate) | 72 | 0.972 (0.904-0.992) | 0.823 |
| `linked` + `jina-reranker-v3` top 15 | 72 | 0.972 (0.904-0.992) | 0.885 |

The retrieval gate fails on `golden_cases` (72 of 100), so QUAL-003 is still not proven. These numbers include batch 2, which is easy and not owner-verified, and the reranker was chosen on the first 32 cases. Both misses are enumeration questions, which belong to typed lookups.
