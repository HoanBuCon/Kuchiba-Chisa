# chisa-tls-expiry (P2)

**Ý nghĩa:** Chứng chỉ TLS sẽ hết hạn trong dưới 14 ngày; Caddy lẽ ra đã tự gia hạn.

**Tín hiệu:** external uptime check certificate data. **Điều kiện:** certificate expires in less than 14 days.

Mọi lệnh chạy trong thư mục deploy trên VPS (`cd /opt/chisa`).

## Chẩn đoán

1. `docker compose logs web | grep -i acme`; kiểm tra DNS trỏ đúng VPS và cổng 80/443 mở.

## Xử lý

1. Sửa nguyên nhân ACME rồi `docker compose restart web`.

## Sau sự cố

P1: ghi chú hậu kiểm ngắn trong 7 ngày (STD-OPS-007).
