# chisa-container-memory-high (P2)

**Ý nghĩa:** Container dùng trên 85% giới hạn RAM trong 15 phút; có nguy cơ OOM.

**Tín hiệu:** container.memory.usage against the compose limit. **Điều kiện:** above 85% of the limit for 15 minutes.

Mọi lệnh chạy trong thư mục deploy trên VPS (`cd /opt/chisa`).

## Chẩn đoán

1. Dashboard Hạ tầng; xu hướng RAM theo thời gian (rò rỉ hay theo tải).

## Xử lý

1. Theo tải: giảm đồng thời hoặc quota. Rò rỉ: khởi động lại có kiểm soát rồi điều tra.

## Sau sự cố

P1: ghi chú hậu kiểm ngắn trong 7 ngày (STD-OPS-007).
