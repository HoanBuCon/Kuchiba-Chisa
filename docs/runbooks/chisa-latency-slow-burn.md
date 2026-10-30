# chisa-latency-slow-burn (P2)

**Ý nghĩa:** Độ trễ vượt SLO (companion / Advanced / Agentic) kéo dài 6 giờ.

**Tín hiệu:** SLO-COMP / SLO-ADV / SLO-AGT error budgets. **Điều kiện:** burn rate above 6x over 6 hours.

Mọi lệnh chạy trong thư mục deploy trên VPS (`cd /opt/chisa`).

## Chẩn đoán

1. Dashboard Chat và LLM: làn nào chậm; latency provider; retrieval; rerank.

## Xử lý

1. Provider chậm: cân nhắc chuyển provider fallback.
1. Retrieval hoặc rerank chậm: xem runbook rerank, kiểm tra tài nguyên Qdrant và inference.

## Sau sự cố

P1: ghi chú hậu kiểm ngắn trong 7 ngày (STD-OPS-007).
