# chisa-telemetry-quota (P2)

**Ý nghĩa:** Dùng trên 80% hạn mức free tier của backend monitoring (MON-061).

**Tín hiệu:** backend usage for series, logs and traces. **Điều kiện:** above 80% of the free-tier allowance (MON-061).

Mọi lệnh chạy trong thư mục deploy trên VPS (`cd /opt/chisa`).

## Chẩn đoán

1. Trang usage của backend: series, log hay trace đang tăng.

## Xử lý

1. Giảm tỷ lệ baseline trong `tail_sampling` của `deploy/otel/collector.yaml` trước, rồi giảm log INFO.
1. Series tăng: kiểm tra nhãn mới vi phạm allowlist (MON-012).

## Sau sự cố

P1: ghi chú hậu kiểm ngắn trong 7 ngày (STD-OPS-007).
