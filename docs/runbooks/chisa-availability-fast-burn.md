# chisa-availability-fast-burn (P1)

**Ý nghĩa:** Error budget SLO-AVAIL (99,5%/30 ngày) đang cạn nhanh (burn rate > 14,4× trong 1 giờ).

**Tín hiệu:** SLO-AVAIL error budget. **Điều kiện:** burn rate above 14.4x over 1 hour.

Mọi lệnh chạy trong thư mục deploy trên VPS (`cd /opt/chisa`).

## Chẩn đoán

1. Xác định loại lỗi chiếm ưu thế (5xx, timeout) trên dashboard Tổng quan.
1. Đối chiếu thời điểm với lần deploy hoặc thay đổi cấu hình gần nhất.

## Xử lý

1. Giảm thiểu trước: rollback hoặc tắt tính năng mới qua feature flag.
1. Nếu đốt quá 50% budget trong 7 ngày: ưu tiên ổn định trước tính năng (SRS §13.6).

## Sau sự cố

P1: ghi chú hậu kiểm ngắn trong 7 ngày (STD-OPS-007).
