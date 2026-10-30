# chisa-llm-daily-cost-cap (P1)

**Ý nghĩa:** Chi phí LLM trong ngày đã chạm trần; Agentic bị tắt toàn cục (QUO-005).

**Tín hiệu:** chisa.llm.cost. **Điều kiện:** daily cost reaches the configured cap (QUO-005).

Mọi lệnh chạy trong thư mục deploy trên VPS (`cd /opt/chisa`).

## Chẩn đoán

1. Báo cáo chi phí theo chế độ và vai trò trên Admin Console.
1. Tìm tài khoản hoặc guild tiêu thụ bất thường (Postgres, cột usage của `messages`).

## Xử lý

1. Lạm dụng: khoá tài khoản hoặc hạ quota.
1. Tải hợp lệ: nâng trần có chủ đích và ghi lý do vào audit.

## Sau sự cố

P1: ghi chú hậu kiểm ngắn trong 7 ngày (STD-OPS-007).
