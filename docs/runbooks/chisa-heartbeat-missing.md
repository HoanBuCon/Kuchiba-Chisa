# chisa-heartbeat-missing (P1)

**Ý nghĩa:** Dịch vụ heartbeat không nhận ping đúng hạn: worker treo hoặc chết, hoặc backup không chạy.

**Tín hiệu:** external heartbeat service (worker every 5 minutes, backup daily). **Điều kiện:** an expected ping is missing past its grace period.

Mọi lệnh chạy trong thư mục deploy trên VPS (`cd /opt/chisa`).

## Chẩn đoán

1. Worker: `docker compose ps worker`, `docker compose logs --tail=200 worker`, `python -m app.worker status`.
1. Backup: `crontab -l`, log của lần chạy gần nhất, dung lượng đĩa.

## Xử lý

1. Worker: `docker compose up -d worker`; job kẹt thì xem dead-letter.
1. Backup: chạy tay `scripts/ops/backup.sh` và kiểm tra `SHA256SUMS`.

## Sau sự cố

P1: ghi chú hậu kiểm ngắn trong 7 ngày (STD-OPS-007).
