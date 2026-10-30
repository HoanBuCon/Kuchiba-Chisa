# chisa-uptime-down (P1)

**Ý nghĩa:** Không truy cập được `/health` hoặc trang web từ bên ngoài.

**Tín hiệu:** external uptime check on /health and the web root. **Điều kiện:** two consecutive failed probes.

Mọi lệnh chạy trong thư mục deploy trên VPS (`cd /opt/chisa`).

## Chẩn đoán

1. `docker compose ps` xem container nào dừng hoặc unhealthy.
1. `docker compose logs --tail=200 web app` tìm lỗi khởi động hoặc TLS.
1. Kiểm tra DNS và chứng chỉ của domain; kiểm tra VPS còn chạy (console nhà cung cấp).

## Xử lý

1. Khởi động lại service lỗi: `docker compose up -d <service>`.
1. Nếu do bản deploy mới: rollback về image trước (DEPLOYMENT_RUNBOOK).

## Sau sự cố

P1: ghi chú hậu kiểm ngắn trong 7 ngày (STD-OPS-007).
