# Báo cáo kiểm tra kiến trúc Prompt & Budget

**Dự án:** kuchiba_chisa  
**Ngày quét:** 2026-07-07  
**Phạm vi:** Luồng lắp prompt production (`ChatEngine` → `ContextBuilder` → `ContextBudgetManager` → LLM adapter)  
**Mục tiêu:** Xác nhận các vấn đề kiến trúc prompt ảnh hưởng đến quản lý token budget

---

## 1. Tóm tắt điều hành

Hệ thống budget hiện tại **hoạt động được ở mức MVP** (cắt lore/memory/history, phân mode theo loại hội thoại), nhưng **không đảm bảo** tổng prompt input ≤ `total_budget` như tên gọi gợi ý.

Nguyên nhân cốt lõi: **thứ tự lắp prompt sai so với logic budget** — budget được áp dụng *trước* khi ghép system prompt đầy đủ, và nhiều thành phần system **không được tính vào ngân sách**.

| Mức độ | Vấn đề | Trạng thái |
|--------|--------|------------|
| 🔴 Cao | `system_reserve = 800` trong khi persona cố định ~1 815 token | **Đã xác nhận** |
| 🔴 Cao | Summary + Search inject vào system **sau** budget, không cap theo mode | **Đã xác nhận** |
| 🟠 Trung bình | Lore/memory nằm trong system prompt nhưng budget trừ riêng — cộng thêm persona vượt reserve | **Đã xác nhận** |
| 🟠 Trung bình | Hai hệ số ước lượng token (2 vs 4 ký tự/token) không thống nhất | **Đã xác nhận** |
| 🟠 Trung bình | Metric `token_budget_context` thiếu history | **Đã xác nhận** |
| 🟡 Thấp | `intent_name` truyền vào `ContextBuilder.build()` nhưng không dùng | **Đã xác nhận** |
| 🟡 Thấp | `estimate_tokens()` trên adapter không được budget manager gọi | **Đã xác nhận** |

**Kết luận:** Budget mode (5k / 8k / 12k) là **soft allocator** cho lore + memory + history, **không phải** hard cap toàn prompt. Prompt production thực tế thường **vượt 1 000–3 000+ token** so với ngân sách danh nghĩa.

---

## 2. Luồng kiến trúc hiện tại

```mermaid
flowchart TD
    CE[ChatEngine.chat] --> MODE{Chọn total_budget}
    MODE -->|small talk| B5[5000]
    MODE -->|RAG| B8[8000]
    MODE -->|loop thinking| B12[12000]

    CE --> RAG[RAGPipeline.retrieve_and_align]
    RAG --> CB[ContextBuilder.build]

    CB --> FMT[Format assistant history → JSON]
    FMT --> BM[ContextBudgetManager.enforce_budget]
    BM --> TRIM[trimmed_lore / memories / history]

    TRIM --> ASM[Ghép system prompt]
    ASM --> P[PERSONA ~1446 tok]
    ASM --> S[STATE ~29 tok]
    ASM --> O[OUTPUT FORMAT ~340 tok]
    ASM --> SUM[CONVERSATION SUMMARY — không cap]
    ASM --> MEM[[MEMORIES] từ trimmed]
    ASM --> LOR[[LORE] từ trimmed]
    ASM --> SEA[[SEARCH DATA] max 3000 chars]

    ASM --> OUT[StructuredPrompt → LLM adapter]
    OUT --> MSG["messages = system + history + user"]
```

### 2.1. Chọn budget (`chat_engine.py`)

```python
# app/domain/services/chat_engine.py (L223–229)
if is_st:
    total_budget = 5000
elif len(rag_context.thinking_steps) > 0:
    total_budget = 12000
else:
    total_budget = 8000
```

| Mode | Điều kiện | `total_budget` |
|------|-----------|----------------|
| Small talk | `IntentClassifier.is_small_talk()` | 5 000 |
| Loop Thinking | `len(rag_context.thinking_steps) > 0` | 12 000 |
| RAG thường | Còn lại | 8 000 |

### 2.2. Cắt budget (`context_budget_manager.py`)

```python
system_reserve = 800
remaining_budget = total_budget - system_reserve
# Lore cap: 0 / 1200 / 1500 token (theo mode)
# Memory cap: 0 / 800 / 1000 token
# History: phần còn lại, ưu tiên tin mới nhất
```

Hệ số ước lượng: **`1 token ≈ 2 ký tự`** (`CHARS_PER_TOKEN = 2`).

### 2.3. Lắp prompt (`context_builder.py`)

Thứ tự thực tế:

1. Format history (assistant → JSON schema)
2. **`enforce_budget()`** — cắt lore, memory, history
3. Ghép system: PERSONA + STATE + OUTPUT FORMAT
4. Thêm (nếu có): CONVERSATION SUMMARY, MEMORIES, LORE, SEARCH DATA
5. Trả `StructuredPrompt(system=..., history=trimmed_history, ...)`

### 2.4. Gửi LLM (`groq.py` / `gemini.py` / `deepseek.py`)

```python
messages = [
    {"role": "system", "content": prompt.system},
    *prompt.history,
    {"role": "user", "content": prompt.user_message},
]
```

**Input thực gửi API** = toàn bộ `system` + `history` + `user_message`.  
Các field `retrieved_memories`, `retrieved_lore`, `rag_decisions` trên `StructuredPrompt` **không được adapter inject thêm** — chỉ metadata nội bộ.

---

## 3. Số liệu đo thực tế (2026-07-07)

Đo bằng `venv\Scripts\python.exe` trên codebase hiện tại:

| Thành phần | Ký tự | Token (@ 2 ký tự/token) | Token (@ 4 ký tự/token) |
|------------|-------|-------------------------|-------------------------|
| `PERSONA_TEXT` | 2 893 | **~1 446** | ~723 |
| `[CURRENT STATE]` | 58 | ~29 | ~15 |
| `[OUTPUT FORMAT]` | ~680 | ~340 | ~170 |
| **System cố định (tối thiểu)** | ~3 631 | **~1 815** | ~908 |
| `system_reserve` cấu hình | — | **800** | — |
| **Chênh lệch (under-reserve)** | — | **~−1 015 token** | — |

### 3.1. Phân bổ danh nghĩa vs thực tế (khi cap lore/memory đầy)

Giả định không có summary/search:

| Mode | Budget danh nghĩa | History alloc | Tổng danh nghĩa (800+lore+mem+hist) | System min thực | Vượt so với budget |
|------|-------------------|---------------|--------------------------------------|-----------------|---------------------|
| Small talk | 5 000 | 4 200 | 5 000 | ~1 815 | +1 815 system chưa tính |
| RAG | 8 000 | 5 200 | 8 000 | ~1 815 + lore + mem trong system | +~1 815 phần persona/format/state |
| Loop | 12 000 | 8 700 | 12 000 | tương tự | +~1 815 |

Khi có **Loop Thinking + SEARCH DATA** (max 3 000 ký tự + ~600 ký tự hướng dẫn):

- Thêm ~**1 800 token** vào system (không qua `ContextBudgetManager`)
- Tổng input ước lượng mode RAG 8k: **~9 000–10 500 token** (chưa kể summary dài)

---

## 4. Vấn đề đã xác nhận (chi tiết)

### 4.1. 🔴 `system_reserve` không phản ánh system prompt thực

**File:** `app/domain/services/context_budget_manager.py` L33–34

```python
system_reserve = 800
remaining_budget = total_budget - system_reserve
```

**Thực tế:** Chỉ `PERSONA_TEXT` đã ~1 446 token (@2c/t). Cộng STATE + OUTPUT FORMAT → **~1 815 token** tối thiểu.

**Hệ quả:** History được phân bổ như thể system chỉ 800 token, trong khi system tối thiểu ~1 815 token → **tổng prompt vượt budget 1 000+ token** ngay cả khi lore/memory/history tuân cap.

**Mức tin cậy:** Cao — đo trực tiếp trên `ContextBuilder.PERSONA_TEXT`.

---

### 4.2. 🔴 Thứ tự build: budget trước, system sau

**File:** `app/domain/services/context_builder.py` L110–188

Budget manager chạy **trước** khi biết kích thước:

- `[CONVERSATION SUMMARY]` — không giới hạn
- `[SEARCH DATA]` — cap cứng 3 000 ký tự, không gắn `total_budget`
- `[MEMORIES]` / `[LORE]` — đã trim nhưng được **nhét vào system string** sau bước budget

**Hệ quả:**

1. Summary dài (auto-summarize sau 20+ tin) có thể chiếm hàng nghìn token **không bị cắt**
2. Search block ở mode Loop 12k vẫn cap 3 000 chars dù budget mode rộng hơn
3. Persona/format/state **không bao giờ** được trừ trực tiếp khỏi `remaining_budget`

**Mức tin cậy:** Cao — đọc trực tiếp source order.

---

### 4.3. 🔴 `[CONVERSATION SUMMARY]` không có budget cap

**File:** `app/domain/services/context_builder.py` L161–167  
**Nguồn dữ liệu:** `chat_engine.py` L81, L241 — `conv_obj.summary` từ Postgres, tạo bởi `_auto_summarize_conversation()` (không giới hạn độ dài output LLM).

**Hệ quả:** Cuộc hội thoại dài → summary phình → system prompt tăng không kiểm soát → history bị cắt mạnh hoặc tổng input tăng chi phí/latency.

**Mức tin cậy:** Cao.

---

### 4.4. 🟠 Lore/Memory: budget trừ riêng + nằm trong system

**Thiết kế hiện tại (có chủ ý nhưng accounting lệch):**

- `enforce_budget()` trừ lore/memory khỏi pool `total_budget - 800`
- Cùng nội dung được đưa vào `system` qua `[LORE]` / `[MEMORIES]`

Điều này **không phải duplicate gửi API** (chỉ 1 lần trong system), nhưng **`system_reserve = 800` giả định system = persona + format + state**, trong khi thực tế system **còn chứa lore + memory + summary + search** → reserve thiếu toàn bộ các phần động trong system.

**Mức tin cậy:** Cao.

---

### 4.5. 🟠 `[SEARCH DATA]` cap cứng, tách khỏi mode budget

**File:** `app/domain/services/context_builder.py` L172–176

```python
max_search_chars = 3000  # ~1500 token @2c/t, cố định mọi mode
```

**File:** `app/domain/services/rag/pipeline.py` L160–162 — search chỉ inject khi `did_search` hoặc context không rỗng.

**Hệ quả:** Mode Loop 12k tăng lore/memory/history nhưng **không tăng** quota search trong system prompt.

**Mức tin cậy:** Cao.

---

### 4.6. 🟠 Hai hệ số token không thống nhất

| Vị trí | Hệ số | Ghi chú |
|--------|-------|---------|
| `ContextBudgetManager` | 2 ký tự/token | Dùng thực tế khi cắt |
| `GroqAdapter.estimate_tokens()` | 4 ký tự/token | Docstring: "TODO tiktoken" |
| `GeminiAdapter.estimate_tokens()` | 4 ký tự/token | Tương tự |
| `DeepSeekAdapter.estimate_tokens()` | 4 ký tự/token | Tương tự |
| `chat_engine.py` pipeline log | `len // 2` | Chỉ system + user |

**Hệ quả:** Interface `BaseLLMAdapter.estimate_tokens()` được thiết kế cho budget enforcement nhưng **không được gọi** từ `ContextBudgetManager` hay `ContextBuilder`.

**Mức tin cậy:** Cao — grep toàn repo không có call site `enforce_budget` + `estimate_tokens`.

---

### 4.7. 🟠 Metric observability không đầy đủ

**File:** `app/domain/services/chat_engine.py` L245–248

```python
"token_budget_context": len(prompt.system) // 2 + len(prompt.user_message) // 2
```

**Thiếu:**

- `prompt.history` (có thể chiếm phần lớn input)
- Breakdown theo section (persona, lore, search, summary)
- So sánh với `total_budget` mode đã chọn
- Token thực từ API (`response.usage.prompt_tokens`) vs estimate

**Mức tin cậy:** Cao.

---

### 4.8. 🟡 Cắt lore/memory theo thứ tự, không theo relevance

**File:** `context_budget_manager.py` L51–73

Retriever (`rag/pipeline.py`) trả chunk đã rank theo score Qdrant, nhưng budget manager **first-fit theo thứ tự list** — chunk đầu dài có thể chặn chunk sau relevance cao hơn.

**Mức tin cậy:** Cao.

---

### 4.9. 🟡 History DB limit vs budget limit không đồng bộ

**File:** `conversation_repository.py` L62–63 — `get_recent_history(..., limit=15)`

Budget mode Loop có thể giữ **>15 message** nếu tin ngắn, nhưng DB **không bao giờ trả >15** → budget history rộng **không được tận dụng** ở tầng fetch.

**Mức tin cậy:** Cao.

---

### 4.10. 🟡 Assistant history inflate trước budget

**File:** `context_builder.py` L86–108

Plain-text assistant được bọc full JSON schema (~200+ ký tự overhead/tin) **trước** `enforce_budget()` → số turn history giữ được **ít hơn** mong đợi khi nhìn nội dung gốc.

**Mức tin cậy:** Cao — hành vi có chủ ý, cần document rõ.

---

### 4.11. 🟡 Tham số `intent_name` không sử dụng

**File:** `context_builder.py` L75, L239 (`chat_engine.py`)

`intent_name` được truyền vào `build()` nhưng **không ảnh hưởng** budget hay nội dung prompt → dead parameter, bỏ lỡ cơ hội điều chỉnh budget theo intent (ví dụ `OTHER` factual vs `CHARACTER_LORE`).

**Mức tin cậy:** Cao — grep chỉ thấy khai báo và call site.

---

## 5. Phạm vi ảnh hưởng

### 5.1. Không gây crash (hiện tại)

- Model mặc định (Groq `llama-3.1-8b-instant`, Gemini, DeepSeek) có context window lớn (8k–128k+)
- `LLMTokenOverflowError` chỉ bắt khi API trả lỗi context — prompt ~10k token vẫn thường chạy được

### 5.2. Ảnh hưởng thực tế

| Khía cạnh | Ảnh hưởng |
|-----------|-----------|
| **Chi phí API** | Input lớn hơn 20–40% so vì budget danh nghĩa |
| **Latency** | Prompt dài → TTFT chậm hơn |
| **Chất lượng** | History bị cắt sớm vì system chiếm chỗ; summary/search cạnh tranh token với lore |
| **Debug** | Metric pipeline gây hiểu nhầm (thiếu history) |
| **Loop Thinking** | Budget 12k không translate đầy đủ sang search context |

---

## 6. Test coverage hiện có

| Test | Phạm vi | Thiếu |
|------|---------|-------|
| `scratch/test_budget_enforcement.py` | Unit `ContextBudgetManager` 3 mode | Không qua `ContextBuilder`, không đo system thực |
| `WALKTHROUGH.md` § Dynamic Context Budgeting | Document design | Mô tả reserve 800, chưa nêu persona ~1446 tok |
| Unit tests pytest | Intent, tool router, RAG pipeline | **Không có** test budget end-to-end |

---

## 7. Đề xuất khắc phục (theo ưu tiên)

### P0 — Sửa accounting budget

1. **Đo system skeleton trước khi cắt:** persona + format + state (+ summary cap + search cap)
2. `remaining = total_budget - system_actual - user_message_reserve`
3. Phân bổ lore / memory / history từ `remaining`

### P1 — Cap các phần system động

| Thành phần | Đề xuất cap |
|------------|-------------|
| `[CONVERSATION SUMMARY]` | 600–800 token, cắt đuôi |
| `[SEARCH DATA]` | Scale theo mode: 1500 tok (8k) / 2500 tok (12k) |
| `PERSONA_TEXT` | Tách static/dynamic; cân nhắc rút gọn nếu >1200 tok |

### P2 — Thống nhất token estimation

- Một module `TokenEstimator` dùng chung (tiktoken hoặc `len//2` cho tiếng Việt)
- Gọi từ `ContextBuilder` trước khi trim
- Log breakdown trong `pipeline_tracker`

### P3 — Cải thiện chất lượng trim

- Lore/memory: knapsack theo score/relevance thay vì first-fit
- `get_recent_history(limit=...)` scale theo mode budget
- Dùng `intent_name` để tinh chỉnh cap (ví dụ factual `OTHER` ưu tiên search over lore)

---

## 8. File liên quan (reference)

| File | Vai trò |
|------|---------|
| `app/domain/services/chat_engine.py` | Chọn mode budget, gọi ContextBuilder, log metric |
| `app/domain/services/context_builder.py` | Lắp system prompt, cap search 3000 chars |
| `app/domain/services/context_budget_manager.py` | Cắt lore/memory/history, `system_reserve=800` |
| `app/domain/services/rag/pipeline.py` | Inject search vào `tool_output_msg` |
| `app/infrastructure/llm/adapters/base.py` | `StructuredPrompt`, `estimate_tokens()` abstract |
| `app/infrastructure/llm/adapters/groq.py` | Ghép messages gửi API |
| `app/infrastructure/database/repositories/conversation_repository.py` | History limit 15 |
| `scratch/test_budget_enforcement.py` | Test unit budget manager |

---

## 9. Kết luận

Quét lại mã nguồn **xác nhận** kiến trúc prompt hiện tại có **lỗ hổng accounting budget có hệ thống**:

1. **`total_budget` không bao phủ toàn bộ prompt gửi LLM**
2. **`system_reserve = 800` thiếu ~1 015 token** so với system cố định thực tế
3. **Summary và search nằm ngoài budget pipeline**
4. **Observability và token estimator không được tích hợp**

Hệ thống vẫn an toàn về context window model, nhưng **không đạt mục tiêu kiểm soát chi phí/chính xác budget** như mô tả trong `WALKTHROUGH.md`. Refactor theo mô hình **"measure full system first → trim the rest"** là hướng sửa impact cao nhất.

---

*Báo cáo được tạo tự động từ quét mã nguồn workspace `kuchiba_chisa`.*
