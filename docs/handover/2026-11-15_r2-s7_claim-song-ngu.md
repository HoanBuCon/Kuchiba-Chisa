# Claim hai ngôn ngữ và lời dẫn theo giọng Chisa

| | |
|---|---|
| Ngày | 15/11/2026 |
| Người thực hiện | Claude (subagent) |
| Nhánh | `feat/r2-bilingual-claims` (từ `HBC`) |
| PR | chưa mở |

## Thay đổi

Output của Composer làn có bằng chứng đổi thành `{decision, lead, claims[{evidence_id, quote, claim_en, claim_vi}], closing, sentiment}` (GRD-001, thay đổi 2 và 3 của `target-architecture.md`):

- `claim_en` kiểm với `quote` cùng ngôn ngữ bằng `ClaimEvidenceGuard` có sẵn, thêm kiểm phủ định hai chiều.
- `claim_vi` kiểm với `claim_en` bằng so khớp chữ: mọi con số và tên riêng phải có trong `claim_en` hoặc nguồn, phủ định phải khớp. Không còn gọi embedding.
- Claim trượt một trong hai bước bị loại (GRD-003). Hết claim thì giữ khung trích dẫn nguyên văn; không đủ bằng chứng thì abstain như cũ.
- `lead` và `closing` do LLM viết; chứa tên riêng hoặc con số không có trong câu hỏi và các claim giữ lại thì bỏ. `lead` thay bằng `GROUNDED_ANSWER_LEAD`, `closing` bỏ hẳn.
- Văn bản hiện cho Senpai = lead + các `claim_vi` giữ lại + closing. Trích dẫn là mã nguồn của các claim giữ lại.

Mã mới: `guardrails/bilingual_output.py` (schema chặt, `BilingualOutputAssembler`), `guardrails/literal_facts.py` (chuyển `facts_match` và các regex từ `knowledge/cross_language_claims.py`, thêm `introduces_new_facts`, `negation_agrees`), model `BilingualModelPayload` trong `grounded_generation.py`. `_GROUNDED_RULES` và mẫu JSON trong `persona_v2.py` mô tả các trường mới; lõi persona không đổi.

## Quyết định

- `GroundedOutputAssembler` của làn v1 vẫn dùng ở `llm_generation_stage`, nên không sửa hành vi; chỉ thêm `resolve_quote` công khai để lớp mới dùng lại cách khớp trích dẫn.
- Xoá `CrossLanguageClaimCheck`, tham số `embedder` của `GroundedComposer`, và test của chúng vì không còn nơi gọi (STD-PY-011).
- Khung trích dẫn chỉ dùng khi không còn claim nào; trước đây claim hỏng được trộn cạnh claim đạt.
- `lead` hợp lệ không cần nhắc Senpai; trước đây server tự chèn câu dẫn cố định nếu thiếu "Senpai".

## Kiểm tra

| Kiểm tra | Kết quả |
|---|---|
| `pytest -q --ignore=tests/integration` | 1368 đạt; 27 lỗi cũ cần dịch vụ thật (cũng lỗi trên `HBC`) |
| `ruff`, `mypy`, `lint-imports`, `ruff_debt_ratchet.py` | đạt |
| Test mới | schema, claim đúng, `claim_en` không được quote đỡ, `claim_vi` đổi tên hoặc thêm số hoặc lật phủ định, lead và closing có tên hoặc số mới, hết claim thì khung trích dẫn, abstain |

## Chưa kiểm tra

Chưa chạy đo trực tiếp với LLM thật: tỷ lệ claim đúng được giữ, tỷ lệ phải dùng khung trích dẫn, và việc model có viết `lead` đúng giọng mà không thêm tên hay số hay không.

## Việc còn lại

- Đo trên bộ golden và bộ hiệu chuẩn claim, so với mốc 62% của kiểm embedding.
- `chat_turns.py` và các route v2 chưa đổi; chỉ cần kiểm lại nếu có nơi đọc trường `claims` cũ.
