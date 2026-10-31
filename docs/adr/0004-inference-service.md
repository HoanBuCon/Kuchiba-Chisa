# ADR-0004: Inference service tự xây trên fastembed/ONNX

- Trạng thái: **Accepted**
- Ngày: 2026-10-31
- Người quyết định: chủ dự án (uỷ quyền chọn phương án tối ưu)
- Liên quan: SRS v2.2.1 (KNW-005, KNW-007, mục 3.4), [thiết kế ingestion](../ingestion/design.md) (S6)

## Bối cảnh

- API (2 worker uvicorn) và worker mỗi tiến trình tự nạp `multilingual-e5-small`, tổng 3 bản model, nên compose phải cấp app 2.048 MB và worker 1.200 MB.
- SRS dự kiến dùng TEI 1.000 MB. Tuy nhiên TEI mỗi container chỉ phục vụ một model, nên embedding cộng rerank local cần 2 container, vượt ngân sách.
- Đo ngày 2026-10-31 (e5-small fp32, đoạn ~512 token):

  | Phép đo | Kết quả |
  |---|---|
  | Nạp model trong một tiến trình | +694 MB |
  | Lô 64, bộ nhớ đệm ONNX mặc định | ~3 GB |
  | Tắt bộ nhớ đệm, độ trễ | gần như không đổi (query 6,2 → 6,4 ms) |
  | cgroup Linux theo lô 1 / 4 / 8 / 16 / 32 | đỉnh 928 / 970 / 1.069 / 1.332 / 1.858 MB; riêng nạp model ~820 MB |

Đo tải (Docker Desktop trên máy dev, có nhiễu; 150 query trong lúc lô 8 passage chạy liên tục):

| Cấu hình | Query khi có tải: p50 / p95 / p99 | Thông lượng passage | RAM đỉnh cgroup |
|---|---|---|---|
| 1 làn, 1 CPU | 3.137 / 7.912 / 12.731 ms | 1,9 /s | — |
| 2 làn, 1 CPU | 50 / 152 / 414 ms | 0,8 /s | 1.117 MB |
| **2 làn, 2 CPU** | **41 / 78 / 129 ms** | 2,1 /s | 1.127 MB |

## Quyết định

1. Một service nội bộ `inference` (FastAPI, `app/interface/inference/main.py`), chạy bằng chính image của app, là **tiến trình duy nhất nạp model**. Endpoint:
   - `/v1/embed` (kind `query`/`passage`, áp prefix e5);
   - `/v1/rerank` (chỉ khi có model local);
   - `/v1/info` (model, revision, dimension);
   - `/health`, `/ready`.
2. Engine fastembed tắt bộ nhớ đệm ONNX (`enable_cpu_mem_arena=False`), lô tối đa 8.
   **Hai làn** dùng chung một model: làn `query` (gồm cả rerank, vì nằm trên đường chat) và làn `passage`. Query không bao giờ xếp hàng sau lô passage.
   Giới hạn CPU 2.0 cho khớp `INFERENCE_THREADS=2`.
3. Giới hạn RAM 1.400 MB. API giảm còn 1.200 MB, worker 700 MB; tổng compose 6.440 / 6.656 MB.
4. Service không có egress (mạng `chisa_data`) và không cần secret của app (cấu hình riêng `InferenceSettings`). Model được tải một lần bằng `model-warmup` (profile `ops`).
5. API và worker gọi qua `InferenceEmbeddingClient` (cache query trên Redis) và `InferenceCrossEncoderReranker`. Lúc khởi động, cả hai kiểm model và dimension (KNW-005); readiness có thêm `inference`.

## Hệ quả

- Tiết kiệm khoảng 350 MB so với 3 bản model, đồng thời bỏ rủi ro ba tiến trình cùng tải model vào một cache.
- Embedding thành một lời gọi HTTP nội bộ (query đo được 7,8 ms so với 6,2 ms khi chạy trong tiến trình).
- Inference là phụ thuộc mới: inference lỗi thì API báo `degraded` ở `/ready`. Chế độ dự phòng của REL-005 (truy hồi chỉ BM25, bỏ phần trí nhớ, gắn cờ degraded) làm ở runtime R2.
- Khi ingestion chạy, query p95 khoảng 78 ms, hơi vượt PERF-008 (60 ms). Vì vậy ingestion chạy giờ thấp tải và tự giới hạn (lô 4, nghỉ giữa các lô khi có người dùng hoạt động), theo thiết kế S6.
- Bản int8 chính thức (`onnx/model_qint8_avx512_vnni.onnx`, 118 MB) có thể hạ ngân sách nhiều. Việc này thuộc đánh giá chọn model ở I0 (KNW-006), không đổi trong ADR này.

## Phương án đã cân nhắc

| Phương án | Lý do không chọn |
|---|---|
| HF TEI | Một model mỗi container; thêm image lớn; vector khác fastembed nên phải so lại |
| Giữ model trong từng tiến trình | 3 bản model; vi phạm KNW-007; khó vừa ngân sách khi thêm reranker local |
| Giới hạn 1.000 MB như SRS cũ | Đo thực tế ~930 MB ngay ở lô 1, không còn dư địa |
