# chisa-disk-critical (P1)

**Ý nghĩa:** Ổ gốc của VPS dùng trên 90%; Postgres và Qdrant có thể dừng ghi.

**Tín hiệu:** system.filesystem.utilization. **Điều kiện:** root filesystem above 90%.

Mọi lệnh chạy trong thư mục deploy trên VPS (`cd /opt/chisa`).

## Chẩn đoán

1. `du -xh / --max-depth=2 | sort -h | tail`; kiểm tra `/opt/chisa/backups`, log Docker, volume.

## Xử lý

1. Xoá backup cũ vượt `KEEP_DAYS`, chạy `docker system prune` (không kèm `--volumes`).
1. Nếu vẫn thiếu: nâng dung lượng đĩa VPS.

## Sau sự cố

P1: ghi chú hậu kiểm ngắn trong 7 ngày (STD-OPS-007).
