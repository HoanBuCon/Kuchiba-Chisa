# chisa-llm-providers-down (P1)

**Ý nghĩa:** Mọi LLM provider đều mở circuit breaker; Chisa chỉ trả fallback.

**Tín hiệu:** chisa.llm.breaker.state. **Điều kiện:** every configured provider breaker open for 2 minutes.

Mọi lệnh chạy trong thư mục deploy trên VPS (`cd /opt/chisa`).

## Chẩn đoán

1. Dashboard LLM: `chisa.llm.breaker.state`, loại lỗi (timeout, 429, 5xx, auth).
1. Trang trạng thái của provider; kiểm tra số dư và hạn mức API key.

## Xử lý

1. 429/hết tiền: nạp tiền hoặc giảm tải (hạ quota CU tạm thời).
1. Auth: xoay lại API key trong secret của VPS rồi `docker compose up -d app worker`.
1. Sự cố phía provider: chờ breaker tự đóng; không tăng retry.

## Sau sự cố

P1: ghi chú hậu kiểm ngắn trong 7 ngày (STD-OPS-007).
