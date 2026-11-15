# Báo lỗi hết tiền cho các adapter LLM còn lại

| | |
|---|---|
| Ngày | 15/11/2026 |
| Người thực hiện | Claude (subagent) |
| Nhánh | `fix/r2-billing-other-adapters` |
| PR | chưa mở |

## Thay đổi

- Hàm dùng chung `billing_exhausted_error` và hằng `HTTP_PAYMENT_REQUIRED` trong `app/infrastructure/llm/adapters/billing.py`, trả đúng lỗi mã `BILLING` (không retry) mà gateway xếp vào `LLMFailureClass.BILLING`.
- Adapter Gemini và Groq đổi HTTP 402 thành lỗi `BILLING`, cả gọi thường lẫn stream (cùng đi qua hàm dịch lỗi).
- Adapter DeepSeek dùng lại hàm chung, hành vi không đổi.

## Quyết định

- Chỉ ánh xạ những gì SDK thật sự có. Groq (`groq.APIStatusError.status_code`) và Gemini (`google.genai.errors.APIError.code`) chỉ lộ mã HTTP; không SDK nào có lớp lỗi riêng cho hết tiền hay thanh toán.
- Gemini hết hạn mức trả 429 `RESOURCE_EXHAUSTED`, không phân biệt được với giới hạn tốc độ nên vẫn là `RATE_LIMIT`; không đoán theo chuỗi.
- Không thêm kiểm tra chuỗi nào mới.

## Kiểm tra

| Kiểm tra | Kết quả |
|---|---|
| `tests/unit/test_llm_adapter_billing.py`: 402 sang `BILLING` cho Gemini, Groq, DeepSeek; các lỗi khác giữ ánh xạ cũ | Đạt (8 test) |

## Chưa kiểm tra

- Chưa gọi API thật của Gemini và Groq; chưa biết thực tế hai bên có trả 402 khi hết tiền hay không.

## Việc còn lại

- Nếu một bên hết tiền bằng mã khác (Gemini có thể dùng 429), cần tài liệu hoặc ca thật từ nhà cung cấp rồi mới thêm ánh xạ.
