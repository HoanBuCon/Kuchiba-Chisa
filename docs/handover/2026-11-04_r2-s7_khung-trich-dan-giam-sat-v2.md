# Gộp khung trích dẫn và giám sát route v2

| | |
|---|---|
| Ngày | 04/11/2026 |
| Người thực hiện | Claude, theo kế hoạch R2 của HoanBuCon |
| Nhánh | `feat/r2-v2-readiness` (nối tiếp `feat/r2-web-v2`) |
| PR | [#67](https://github.com/HoanBuCon/Kuchiba-Chisa/pull/67) |

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
| `make test-isolated` | 1215 test đạt; mypy, import-linter, OpenAPI đạt |
| Golden v2 với LLM thật, 118 câu | Độ đúng 0,924 (CI 95%: 0,861–0,959); không có case lỗi |
| Khung trích dẫn trên golden | 45 câu có khung, không câu nào lặp |
| Lore một bước, nhiều bước | 0,97; 0,444 |
| Ngoài phạm vi được abstain | 5/6 (lần trước 6/6) |
| Abstain nhầm, precision của abstain | 3,6%; 0,556 (lần trước 0,6, mục tiêu ≥ 0,90) |
| Độ trễ p50, p95 | 2,9 giây; 5,3 giây |

Hỏi lại `oos-003` 5 lần: 3 lần trả lời, 2 lần abstain. Kết quả ngoài phạm vi vì thế dao động giữa các lần chạy, nên 6/6 lần trước chưa vững. `memory-002` lần này bị chấm sai đúng với thực tế: Chisa nói về đồ uống của mình. Hai thay đổi này chưa được so theo từng câu với lần trước, vì báo cáo cũ không còn trên máy.

## Chưa kiểm tra

- Chưa nạp alert và SLO vào Prometheus hay Grafana thật.

## Việc còn lại

- `oos-003`: "Chapter VII" chưa phát hành bị nhầm với "Chapter I: Act VII".
- `memory-002`: làn companion hiểu "anh" là Chisa dù có lịch sử. Persona là nội dung bảo vệ nên không tự sửa prompt.
- Câu trả lời vẫn có thể chứa trích dẫn tiếng Anh khi claim tiếng Việt không qua được bước kiểm chứng.
