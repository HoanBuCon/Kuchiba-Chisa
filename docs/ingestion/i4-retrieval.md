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

## Golden batch 3: hard cases (2026-11-03)

Batch 3 adds 36 unverified cases that do not name their target, written before any retrieval run. Corpus `2026.11.03-1`, 108 cases:

| Set | Cases | `linked` Hit@5 / MRR@10 | + reranker Hit@5 / MRR@10 |
|---|---|---|---|
| First 32 | 32 | 0.938 / 0.729 | 0.938 / 0.810 |
| Batch 2 (easy) | 40 | 1.000 / 0.899 | 1.000 / 0.946 |
| Batch 3 (hard) | 36 | 0.611 / 0.326 | 0.694 / 0.649 |
| All | 108 | 0.852 / 0.658 | 0.880 / 0.807 |

QUAL-003 is not met: the retrieval gate fails on Hit@5 in both modes and on MRR@10 in `linked`. Of the 13 reranked misses, 7 rank below the reranker's top 15 candidates, 3 are inside it but not lifted to the top 5, and 3 are not in the top 50 at all. Batch 3 labels still await owner review.


## English query translation and reranker depth (2026-11-04)

ADV-010 allows LLM translation only when evaluation proves the need. It does: Vietnamese questions match an English wiki poorly. Questions were translated once through the LLM gateway (`deepseek-v4-flash`, median 0.86 s, 96 calls, about 37,700 tokens) and frozen in `query_translations.yaml`, so the gate calls no LLM. Corpus `2026.11.03-1`, 108 cases:

| Pipeline | Hit@5 | MRR@10 | Dev half Hit@5 / MRR@10 | Hard batch Hit@5 / MRR@10 |
|---|---|---|---|---|
| Vietnamese, no reranker | 0.852 | 0.658 | 0.816 / 0.609 | 0.611 / 0.326 |
| Vietnamese, Jina top 15 | 0.880 | 0.807 | | 0.694 / 0.649 |
| Translated, no reranker | 0.944 | 0.727 | 0.898 / 0.688 | 0.889 / 0.504 |
| Translated, local MiniLM-L-6 top 15 | 0.944 | 0.834 | 0.898 / 0.785 | 0.889 / 0.847 |
| Translated, Jina top 15 | 0.944 | 0.877 | 0.898 / 0.810 | 0.889 / 0.819 |
| Translated, Jina top 30 | 0.944 | 0.899 | 0.898 / 0.829 | 0.889 / 0.833 |
| Translated, Jina top 50 | 0.972 | 0.920 | 0.959 / 0.870 | 0.972 / 0.875 |

Local models were measured on 2 CPU threads: MiniLM-L-6 top 15 took a median of 687 ms. MiniLM-L-12 and Jina tiny and turbo scored no better. `bge-reranker-v2-m3-int8` failed to load its tokenizer in this fastembed version and was not measured.

Decisions and limits:
- The gate uses translated questions with local MiniLM-L-6 top 15, because it is free and needs no LLM. It understates the paid runtime reranker.
- The runtime uses Jina top 15. Top 50 scored best, but measured p95 was 9,295 ms against 761 ms for top 15, and PERF-009 asks for 750 ms. The numbers above for top 30 and 50 stay as evidence.
- At runtime each non-English question spends one of ADV-009's two LLM calls on translation. R2 must define the fallback when that call fails.
- The owner approved the golden set on 2026-11-04, so the gate counts every retrieval case. QUAL-003 is met on this set, with one limit: the agent wrote batch 3 from the wiki text, the pipeline was chosen on this same set, and the holdout half was seen during comparison. Real user questions may score lower, so R2 should add cases from real use.
