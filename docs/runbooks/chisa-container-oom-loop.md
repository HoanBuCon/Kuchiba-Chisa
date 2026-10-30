# chisa-container-oom-loop (P1)

**Ý nghĩa:** Một container khởi động lại từ 3 lần trong 15 phút, thường do vượt giới hạn RAM.

**Tín hiệu:** container restarts and memory usage. **Điều kiện:** three or more restarts of one container within 15 minutes.

Mọi lệnh chạy trong thư mục deploy trên VPS (`cd /opt/chisa`).

## Chẩn đoán

1. `docker inspect <container> --format '{{.State.OOMKilled}}'`.
1. Dashboard Hạ tầng: RAM của container so với giới hạn trong compose.

## Xử lý

1. Tìm nguyên nhân tăng RAM (tải, rò rỉ, model) trước khi nâng giới hạn.
1. Chỉ nâng giới hạn khi tổng vẫn trong ngân sách SRS §3.4 (`scripts/ci/check_ram_budget.py`).

## Sau sự cố

P1: ghi chú hậu kiểm ngắn trong 7 ngày (STD-OPS-007).
