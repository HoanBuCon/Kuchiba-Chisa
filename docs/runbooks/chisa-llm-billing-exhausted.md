# chisa-llm-billing-exhausted (P1)

**Ý nghĩa:** Provider LLM từ chối yêu cầu vì tài khoản hết tiền; Chisa không trả lời được cho đến khi nạp thêm.

**Tín hiệu:** chisa.llm.degraded với failure_class billing. **Điều kiện:** có provider trả về lỗi hết số dư (DeepSeek: HTTP 402).

Mọi lệnh chạy trong thư mục deploy trên VPS (`cd /opt/chisa`).

## Chẩn đoán

1. Dashboard LLM: xác nhận provider nào có `failure_class=billing`.
1. Xem số dư trên trang quản lý của provider đó.

## Xử lý

1. Chủ dự án nạp thêm tiền vào tài khoản provider. Chờ hay tăng retry đều không có tác dụng.
1. Gửi một tin nhắn thử để xác nhận Chisa trả lời lại.

## Sau sự cố

P1: ghi chú hậu kiểm ngắn trong 7 ngày (STD-OPS-007).
