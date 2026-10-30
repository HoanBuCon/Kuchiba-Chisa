# chisa-job-lag (P2)

**Ý nghĩa:** Job nền tồn đọng quá 10 phút hoặc có job vào dead-letter.

**Tín hiệu:** chisa.jobs.lag and dead-letter count. **Điều kiện:** oldest ready job older than 10 minutes, or any dead-letter job.

Mọi lệnh chạy trong thư mục deploy trên VPS (`cd /opt/chisa`).

## Chẩn đoán

1. `python -m app.worker status`; log worker theo `job_type`.

## Xử lý

1. Tăng `WORKER_CONCURRENCY` nếu còn RAM.
1. Sửa nguyên nhân rồi replay: `python -m app.worker replay --job-id <id> --actor <tên>`.

## Sau sự cố

P1: ghi chú hậu kiểm ngắn trong 7 ngày (STD-OPS-007).
