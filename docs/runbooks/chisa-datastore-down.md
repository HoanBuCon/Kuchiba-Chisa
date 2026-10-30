# chisa-datastore-down (P1)

**Ý nghĩa:** Postgres, Redis hoặc Qdrant không chạy, hoặc `/ready` báo lỗi phụ thuộc.

**Tín hiệu:** container metrics and API readiness. **Điều kiện:** postgres, redis or qdrant not running or /ready failing for 2 minutes.

Mọi lệnh chạy trong thư mục deploy trên VPS (`cd /opt/chisa`).

## Chẩn đoán

1. `docker compose ps postgres redis qdrant` và `docker compose logs --tail=200 <service>`.
1. `df -h` kiểm tra đĩa đầy; `free -m` kiểm tra RAM/OOM.

## Xử lý

1. Khởi động lại service: `docker compose up -d <service>`.
1. Dữ liệu hỏng: khôi phục từ backup theo `scripts/ops/restore_drill.sh` và DEPLOYMENT_RUNBOOK.

## Sau sự cố

P1: ghi chú hậu kiểm ngắn trong 7 ngày (STD-OPS-007).
