# Tối ưu hóa Hybrid Routing Architecture

## Tổng quan

Pipeline định tuyến hiện tại **đã có nền tảng Hybrid tốt** nhưng còn 3 điểm yếu kỹ thuật cụ thể cần giải quyết:

1. **Substring matching ở Lớp 2** gây false positive (vd: `"vũ khí"` khớp khi hỏi game khác)
2. **Không có Fast-Path cho `SYSTEM_ACTION`** — lệnh tường minh như `"tóm tắt"`, `"xem cảm xúc"` vẫn phải qua Embedding
3. **`SemanticToolRouter` thiếu Keyword Guard** — chỉ dùng cosine, dễ bị kéo sai tool khi intent mơ hồ

## Sơ đồ kiến trúc sau khi tối ưu

```
Tin nhắn đến
│
├─ [L1] Small Talk Fast-Path          ← Giữ nguyên, không đổi
│   └─ len < 8 hoặc phrase thuộc SMALL_TALK_PHRASES → OTHER
│
├─ [L2] High-Confidence Keyword Guard (NÂNG CẤP)
│   ├─ memory_patterns[]    → MEMORY
│   ├─ character_patterns[] → CHARACTER_LORE
│   ├─ world_patterns[]     → WORLD_LORE
│   ├─ story_patterns[]     → STORY_LORE
│   └─ system_patterns[]    → SYSTEM_ACTION  ← THÊM MỚI
│   └─ Dùng word-boundary regex thay substring match
│
├─ [L3] SemanticRouter + Keyword Boost (GIỮ + TINH CHỈNH)
│   ├─ Cosine Similarity với Anchor matrix
│   ├─ Explicit Anchor Bonus (+0.04)
│   ├─ Confidence Margin Guard (< 0.05)
│   └─ SYSTEM_ACTION Keyword Guard (đã có, giữ nguyên)
│
│   [L3b] SemanticToolRouter + Keyword Boost  ← THÊM MỚI
│   ├─ Cosine Similarity chọn Tool
│   └─ Keyword Guard trước khi execute (bypass embedding nếu match cứng)
│
└─ [L4] Basic Keyword Fallback         ← Merge và làm sạch
    └─ Merge logic vào L2, xóa duplicate
```

## Open Questions

> [!IMPORTANT]
> **Câu hỏi về ngưỡng `EXPLICIT_ANCHOR_BONUS`**
> Hiện tại bonus là `+0.04`. Có muốn tăng lên `+0.08` để tăng tính quyết đoán khi anchor tường minh khớp không? Hay giữ nguyên để an toàn?

> [!NOTE]
> **Câu hỏi về `SYSTEM_ACTION` Fast-Path**
> Nên thêm Fast-Path cho SYSTEM_ACTION ở Lớp 2 với danh sách từ khóa **tối thiểu và chặt chẽ** (chỉ bắt lệnh hoàn toàn tường minh), hay muốn nó **linh hoạt hơn** và phủ rộng phương ngữ/cách nói khác nhau?

---

## Proposed Changes

### Component 1: IntentClassifier

#### [MODIFY] [intent_classifier.py](file:///d:/Hoc_Tap/Code/Du_An_Ca_Nhan/Chisa_bot/kuchiba_chisa/app/domain/services/intent_classifier.py)

**Thay đổi 1 — Nâng cấp keyword matching lên word-boundary Regex**

Thay thế tất cả các đoạn `if any(keyword in msg_lower for keyword in ...)` ở Lớp 2 thành sử dụng hàm `_has_phrase(pattern, text)` dùng `re.search()`.

Lý do: `"vũ khí" in "game có vũ khí không"` trả về `True` dù ý định là hỏi game chung, không phải hỏi về Chisa.

```python
# TRƯỚC (dễ false positive)
if any(keyword in msg_lower for keyword in character_keywords):
    high_conf_intents.append(ChatIntent.CHARACTER_LORE)

# SAU (chặt hơn, dùng boundary)
if any(re.search(rf"(?<!\w){re.escape(kw)}(?!\w)", msg_lower) for kw in character_keywords):
    high_conf_intents.append(ChatIntent.CHARACTER_LORE)
```

> [!NOTE]
> Tiếng Việt không có `\b` chuẩn ASCII nên dùng `(?<!\w)..(?!\w)` thay cho `\b...\b` để tránh ký tự unicode không khớp.

**Thay đổi 2 — Thêm `SYSTEM_ACTION` Fast-Path vào Lớp 2**

Thêm block mới **sau** `story_keywords` và **trước** `if high_conf_intents:`. Chỉ bắt các lệnh tường minh với prefix rõ ràng, **không** bắt câu hỏi mơ hồ.

```python
# THÊM MỚI: High confidence SYSTEM_ACTION triggers
system_patterns = [
    r"tóm tắt.{0,10}(cuộc trò chuyện|hội thoại|nãy giờ|buổi chat)",
    r"(tổng hợp|tổng kết).{0,10}(cuộc trò chuyện|những gì|điểm chính)",
    r"(cho anh xem|xuất|hiển thị).{0,15}(cảm xúc|chỉ số|bảng đo|báo cáo cảm xúc)",
    r"(tra mạng|lên mạng|search google|tra cứu trên internet|lên web).{0,20}",
    r"(em tìm kiếm|em tra).{0,10}(trên internet|trên mạng|giúp anh)",
]
if any(re.search(p, msg_lower) for p in system_patterns):
    high_conf_intents.append(ChatIntent.SYSTEM_ACTION)
```

**Thay đổi 3 — Dọn dẹp Lớp 4 (Fallback)**

- Merge phần logic keyword hữu ích của Lớp 4 vào Lớp 2 (nơi nó thuộc về).
- Giữ Lớp 4 chỉ là lưới an toàn **không có intent cụ thể**, trả thẳng `OTHER`.

---

### Component 2: SemanticRouter

#### [MODIFY] [semantic_router.py](file:///d:/Hoc_Tap/Code/Du_An_Ca_Nhan/Chisa_bot/kuchiba_chisa/app/domain/services/semantic_router.py)

**Thay đổi 1 — Bổ sung thêm Anchor mẫu tiếng Việt phương ngữ Nam**

Hiện tại anchor chủ yếu dùng văn phong Bắc/trung. Thêm các anchor phong cách Nam để tăng độ phủ:

```python
# CHARACTER_LORE - phong cách Nam
("cây kéo của bồ đó\", False),
("em thích ăn gì nè\", False),
("em mấy tuổi vậy nè\", False),

# MEMORY - phong cách Nam  
("ông anh tên gì nè\", False),
("hồi trước anh nói gì đó\", False),
```

**Thay đổi 2 — Tăng `EXPLICIT_ANCHOR_BONUS` từ `0.04` → `0.06`**

Với `0.04` bonus quá nhỏ để tác động thực sự khi hai intent cạnh tranh có score chênh lệch `> 0.04`. Nâng lên `0.06` giúp anchor tường minh có sức ảnh hưởng rõ hơn trong quyết định routing mà vẫn đủ an toàn.

---

### Component 3: SemanticToolRouter

#### [MODIFY] [tool_router.py](file:///d:/Hoc_Tap/Code/Du_An_Ca_Nhan/Chisa_bot/kuchiba_chisa/app/domain/services/tool_router.py)

**Thêm `KeywordToolRouter` — Fast-Path bypass Embedding cho Tool routing**

Hiện tại `LLMToolRouter.execute()` luôn chạy `SemanticToolRouter.route()` kể cả khi Senpai gõ lệnh tường minh như `"tra mạng"`. Thêm một lớp keyword guard trước khi gọi semantic router:

```python
class KeywordToolRouter:
    """
    Fast-Path: khớp regex cứng trước semantic router.
    Nếu khớp → trả thẳng tool_name, bỏ qua embedding.
    Nếu không → để SemanticToolRouter xử lý.
    """
    PATTERNS: Dict[str, List[str]] = {
        "web_search": [
            r"(tra mạng|lên mạng|search google|tra cứu trên internet)",
            r"(em tìm kiếm|em tra).{0,10}(trên internet|trên mạng)",
            r"(lên web|kiểm tra xem|tìm hiểu xem).{0,20}",
        ],
        "conversation_summarizer": [
            r"tóm tắt.{0,10}(cuộc trò chuyện|hội thoại|nãy giờ)",
            r"(tổng hợp|tổng kết).{0,10}(cuộc trò chuyện|những gì)",
        ],
        "emotion_report": [
            r"(cho anh xem|xuất|hiển thị).{0,15}(cảm xúc|chỉ số|bảng đo)",
            r"(báo cáo cảm xúc|tâm trạng theo số liệu)",
        ],
    }

    @classmethod
    def match(cls, msg_lower: str) -> Optional[str]:
        for tool_name, patterns in cls.PATTERNS.items():
            if any(re.search(p, msg_lower) for p in patterns):
                return tool_name
        return None
```

Và trong `LLMToolRouter.execute()`:

```python
# ── Level 2a.0: Keyword Fast-Path (bypass embedding)
keyword_match = KeywordToolRouter.match(user_message.lower())
if keyword_match:
    log.info("Tool routing via keyword fast-path", tool=keyword_match)
    tool_name, score = keyword_match, 1.0
else:
    # ── Level 2a: Semantic routing như cũ
    tool_name, score = await self.semantic_tool_router.route(query_vector)
```

---

### Component 4: Tests

#### [MODIFY] [test_semantic_router.py](file:///d:/Hoc_Tap/Code/Du_An_Ca_Nhan/Chisa_bot/kuchiba_chisa/tests/unit/test_semantic_router.py)

Bổ sung thêm các test case mới:
- **False positive test**: `"game có vũ khí không"` → phải KHÔNG phải `CHARACTER_LORE`
- **SYSTEM_ACTION fast-path test**: `"tóm tắt cuộc trò chuyện"` → `SYSTEM_ACTION` (và kiểm tra không qua embedding)
- **Ambiguous message test**: `"em có biết gì về vũ khí"` → kiểm tra margin guard hoạt động

#### [NEW] [test_intent_classifier.py](file:///d:/Hoc_Tap/Code/Du_An_Ca_Nhan/Chisa_bot/kuchiba_chisa/tests/unit/test_intent_classifier.py)

Test riêng cho `IntentClassifier` bao gồm:
- L1 Small Talk bypass (không cần embedder)
- L2 Keyword Fast-Path (không cần embedder)
- L2 False positive prevention với word-boundary regex
- SYSTEM_ACTION Fast-Path qua L2

#### [NEW] [test_tool_router.py](file:///d:/Hoc_Tap/Code/Du_An_Ca_Nhan/Chisa_bot/kuchiba_chisa/tests/unit/test_tool_router.py)

Test cho `KeywordToolRouter`:
- `"tra mạng giúp anh"` → `web_search`
- `"tóm tắt nãy giờ"` → `conversation_summarizer`
- `"cho anh xem chỉ số cảm xúc"` → `emotion_report`
- `"rover là ai"` → `None` (không khớp keyword, đẩy qua semantic)

---

## Thứ tự triển khai

1. **`intent_classifier.py`** — Cải tiến L2 (regex) + Thêm SYSTEM_ACTION Fast-Path + Dọn L4
2. **`semantic_router.py`** — Thêm anchors + Tăng bonus
3. **`tool_router.py`** — Thêm `KeywordToolRouter`
4. **Tests** — Cập nhật + thêm mới
5. **Chạy `pytest tests/unit/`** để xác nhận

---

## Verification Plan

### Automated Tests

```bash
# Toàn bộ unit tests
.\venv\Scripts\pytest tests/unit/ -v

# Chỉ các test routing
.\venv\Scripts\pytest tests/unit/test_semantic_router.py tests/unit/test_intent_classifier.py tests/unit/test_tool_router.py -v
```

### Manual Verification (sau khi start server)

| Test case | Input | Expected | Mục tiêu kiểm tra |
|:----------|:------|:---------|:-----------------|
| Small talk bypass | `"hihi"` | `OTHER`, **0 embedding calls** | L1 hoạt động |
| Lệnh tường minh | `"tra mạng giúp anh"` | `SYSTEM_ACTION` + `web_search`, **0 embedding calls** | L2 Fast-Path + Tool Fast-Path |
| False positive | `"game có vũ khí không"` | `OTHER`, không phải `CHARACTER_LORE` | Word-boundary regex |
| Lore rõ ràng | `"vũ khí của em là gì"` | `CHARACTER_LORE` | L2 hoặc L3 đều ok |
| Câu mơ hồ | `"anh muốn biết thêm"` | `OTHER` | Confidence margin guard |
| Lore world tiếng Nam | `"sonoro sphere là gì vậy nè"` | `WORLD_LORE` | Anchor phủ phương ngữ |
