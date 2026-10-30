# chisa-api-5xx-rate (P1)

**Ý nghĩa:** Hơn 5% request trả lỗi 5xx trong 5 phút.

**Tín hiệu:** http.server.request.duration (status_class). **Điều kiện:** 5xx share above 5% for 5 minutes.

Mọi lệnh chạy trong thư mục deploy trên VPS (`cd /opt/chisa`).

## Chẩn đoán

1. Dashboard Tổng quan: route nào lỗi nhiều nhất.
1. `docker compose logs --tail=300 app` lọc ERROR; mở trace lỗi trong backend theo `trace_id`.
1. Kiểm tra phụ thuộc: `/ready`, trạng thái LLM provider, Postgres/Redis/Qdrant.

## Xử lý

1. Lỗi do phụ thuộc: xử lý theo runbook của phụ thuộc đó.
1. Lỗi do bản deploy mới: rollback image.

## Sau sự cố

P1: ghi chú hậu kiểm ngắn trong 7 ngày (STD-OPS-007).
