# chisa-rerank-fallback-high (P2)

**Ý nghĩa:** Hơn 20% lượt rerank rơi về fallback trong 15 phút.

**Tín hiệu:** chisa.rerank.fallbacks. **Điều kiện:** fallback share above 20% for 15 minutes.

Mọi lệnh chạy trong thư mục deploy trên VPS (`cd /opt/chisa`).

## Chẩn đoán

1. `chisa.rerank.fallbacks` theo `reason` (timeout, 429, lỗi provider).

## Xử lý

1. Hết hạn mức reranker API: nạp hoặc chuyển provider; fallback local vẫn giữ chất lượng tối thiểu.

## Sau sự cố

P1: ghi chú hậu kiểm ngắn trong 7 ngày (STD-OPS-007).
