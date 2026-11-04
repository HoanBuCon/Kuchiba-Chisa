# Gộp khung trích dẫn và giám sát route v2

| | |
|---|---|
| Ngày | 04/11/2026 |
| Người thực hiện | Claude, theo kế hoạch R2 của HoanBuCon |
| Nhánh | `feat/r2-v2-readiness` (nối tiếp `feat/r2-web-v2`) |

## Thay đổi

- `GroundedOutputAssembler`: thêm `gather_quotes`, mặc định tắt nên luồng v1 giữ nguyên. Composer bật cờ này, nên mỗi câu trả lời chỉ có một khung trích dẫn, đặt sau các claim đã kiểm chứng.
- `otel.py`: thêm `/api/v2/chat/turns` và `/api/v2/other` vào danh sách route. Thiếu chúng thì exporter đổi nhãn thành `other`, nên nhóm metric thêm ở PR #66 chỉ có tác dụng sau thay đổi này.
- `alerts.yaml`, `slo.yaml` và dashboard tính thêm `/api/v2/chat/turns`.

## Quyết định

- Thứ tự trình bày không còn theo thứ tự claim của LLM khi câu trả lời có cả claim đã kiểm chứng và trích dẫn. Đổi lại Chisa không lặp câu dẫn. Nội dung trích dẫn không bị sửa, và `answer` dùng để kiểm chứng không đổi.
- SLO của v2 dùng chung ngưỡng TTFT với v1. Mục tiêu PERF-003 vẫn chờ chủ dự án quyết sau khi đo trên VPS.

## Kiểm tra

| Kiểm tra | Kết quả |
|---|---|
| Test mới cho khung trích dẫn và danh sách route | Đạt |
| Alert, SLO, dashboard | Parse được; test taxonomy nhãn đạt |

## Chưa kiểm tra

- Chưa nạp alert và SLO vào Prometheus hay Grafana thật.
- Chưa đo lại độ đúng trên golden với thay đổi này.

## Việc còn lại

- Câu trả lời vẫn có thể chứa trích dẫn tiếng Anh khi claim tiếng Việt không qua được bước kiểm chứng.
