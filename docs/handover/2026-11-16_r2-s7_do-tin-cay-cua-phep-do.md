# Độ tin cậy của phép đo: reranker bị giới hạn tốc độ và ca out_of_scope

| | |
|---|---|
| Ngày | 16/11/2026 |
| Người thực hiện | Claude (QUAL-004, PERF-009, REL-005) |
| Nhánh | `fix/r2-eval-fidelity` (từ `HBC`), chưa có PR |

## Hiện tượng

- Log backend của một lượt golden cho thấy reranker Jina từ xa trả HTTP 429 và nhiều timeout; lượt đó rơi về thứ tự fusion (`rerank_jina_provider` bị degraded) nên Hit@5 tụt từ 0,93 xuống 0,82 dù số dư token còn đủ.
- 20 ca `oos-401..oos-420` được viết theo kiểu "bot lore phải từ chối", nhưng Chisa còn là bạn đồng hành: làn companion trả lời đúng kiến thức chung, chuyện trò, cảm xúc, nhờ vả đơn giản. QUAL-004 chỉ nói về câu hỏi không có đáp án trong phạm vi tri thức.

## Thay đổi

- **Reranker (`api_cross_encoder_reranker.py`):** gặp 429 thì đợi `Retry-After` rồi gọi lại đúng một lần, trong cùng hạn `timeout_seconds` (lần gọi lại chỉ được phần thời gian còn lại). Không có header thì đợi 0,5 giây. Không thử lại khi `Retry-After` quá 1 giây, không đọc được, hoặc phần còn lại không đủ. Lỗi vẫn thành `RerankerFailureKind.RATE_LIMIT`, cầu chì và fallback fusion giữ nguyên.
- **Timeout mặc định `RERANKER_TIMEOUT_SECONDS`: 1,5 giây thành 5,0 giây** (`settings.py`). Dịch vụ inference đã dùng 5,0 (`inference_settings.py`) và bộ đo retrieval dùng 30 giây; 1,5 giây chỉ vừa một vòng HTTPS tới Jina cho 15 tài liệu (`RERANKER_API_MAX_DOCUMENTS`), không chừa chỗ cho 429 hay hàng đợi. Trần cấu hình vẫn là 10.
- **Golden v2.6:** giữ 11 ca `out_of_scope` mới, xoá 9 ca (không chuyển sang persona). Các ca `oos-001..` cũ giữ nguyên.
  - Giữ (lore không có thật hoặc chưa phát hành): `oos-407`, `408` (Resonator hư cấu), `409`, `410` (chapter chưa có), `411` (vũ khí hư cấu), `412` (Echo hư cấu), `420` (phiên bản chưa phát hành).
  - Giữ (dữ liệu thời gian thực): `oos-415`, `416` (banner hiện tại), `417` (giá vàng), `419` (thời tiết).
  - Xoá: `oos-401`, `402`, `403` (game khác), `404`, `405`, `406` (kiến thức đời thực), `413`, `414` (lời khuyên, cảm xúc), `418` (viết code).
- **Chấm abstain:** thêm 3 cụm vào `abstain_markers`: "không có dữ liệu thời gian thực", "no real-time data", "không dám nói con số". Dòng chú thích v2.6 ở đầu file; `dataset_version: golden-v2.6`.
- Runner golden vốn tuần tự (`run_golden_set` `await` từng ca, không có `gather`), nên không cần giới hạn đồng thời.

## Quyết định

- Chỉ thử lại một lần và chỉ với 429: thử nhiều lần sẽ ăn hết hạn và che lỗi thật; các lỗi khác (timeout, 5xx) vẫn một lần gọi.
- Phạm vi out_of_scope v2.6 do Sếp duyệt. Ca đã xoá không chuyển sang persona; nếu cần đo companion thì tạo ca riêng sau.

## Kiểm tra

| Kiểm tra | Kết quả |
|---|---|
| Test mới cho reranker | 429 có `Retry-After: 0` thì gọi lại đúng 1 lần rồi thành công; 429 liên tục thì dừng sau 2 lần với `RATE_LIMIT`; `Retry-After` quá trần thì không gọi lại |
| Test cập nhật | `test_rag05_remote_provider_boundary` mong 2 lần gọi cho 429 (các lỗi khác vẫn 1 lần) |
| Test dataset | v2.6 có đúng 11 ca `oos-4xx`, đều `abstain`; câu từ chối thiếu dữ liệu thời gian thực được tính là abstain |
| `python -m evals validate` | Đạt: golden-v2.6, 165 ca, 0 chưa xác minh |

## Chưa kiểm tra

- Chưa chạy đo thật: chưa biết Hit@5 có về mức 0,93 và tỷ lệ 429 còn lại bao nhiêu.
- Chưa kiểm định dạng `Retry-After` trên Jina thật.

## Việc còn lại

- Chạy lại cổng đo R2 với v2.6, so với lượt trước và ghi số lần fallback reranker vào báo cáo.
