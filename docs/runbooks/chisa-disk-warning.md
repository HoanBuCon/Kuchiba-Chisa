# chisa-disk-warning (P2)

**Ý nghĩa:** Ổ gốc dùng trên 80%.

**Tín hiệu:** system.filesystem.utilization. **Điều kiện:** root filesystem above 80%.

Mọi lệnh chạy trong thư mục deploy trên VPS (`cd /opt/chisa`).

## Chẩn đoán

1. Như runbook `chisa-disk-critical`, nhưng còn thời gian xử lý trong giờ làm việc.

## Xử lý

1. Dọn backup và log cũ; lên kế hoạch nâng đĩa nếu xu hướng tăng đều.

## Sau sự cố

P1: ghi chú hậu kiểm ngắn trong 7 ngày (STD-OPS-007).
