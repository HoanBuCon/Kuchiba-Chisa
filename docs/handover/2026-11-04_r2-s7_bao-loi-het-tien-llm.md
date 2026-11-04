# Báo riêng lỗi hết tiền của LLM

| | |
|---|---|
| Ngày | 04/11/2026 |
| Người thực hiện | Claude, theo kế hoạch R2 của HoanBuCon |
| Nhánh | `feat/r2-llm-billing` |

## Hiện tượng

DeepSeek trả 402 khi hết số dư, nhưng gateway xếp vào `UNKNOWN`, nên lỗi chỉ hiện là "LLM request unavailable" và phải đọc log mới biết nguyên nhân.

## Thay đổi

- `LLMFailureClass.BILLING`: lỗi kết thúc, không retry và không tính vào circuit breaker.
- Adapter DeepSeek đổi 402 thành mã `BILLING`, cả khi gọi thường lẫn stream.
- Alert P1 `chisa-llm-billing-exhausted` kèm runbook.

## Kiểm tra

| Kiểm tra | Kết quả |
|---|---|
| Test gateway và adapter (gọi thường) | Đạt |
| Test tài sản giám sát, `check_runbooks.py` | Đạt; 17 alert đều có runbook |

## Chưa kiểm tra

- Nhánh stream của adapter chưa có test riêng cho 402.
- Alert chưa được nạp vào Prometheus thật.
- Các adapter khác chưa được đổi; hết tiền ở các bên đó vẫn là lỗi cũ.
