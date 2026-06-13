# Waifu Chatbot Production Pipeline (RAG + Memory + Local LLM)

## Tổng quan kiến trúc

```text
                    USER MESSAGE
                           │
                           ▼
                  Intent Classifier
                           │
           ┌───────────────┼───────────────┐
           ▼               ▼               ▼
      Memory Search   Lore Search    State Manager
           │               │               │
           └───────────────┴───────────────┘
                           │
                           ▼
                    Context Builder
                           │
                           ▼
                         LLM
                           │
                           ▼
                    Response JSON
                           │
                           ▼
                     Memory Update
```

---

# Phase 1 — Knowledge Architecture

## Collection: character_lore

Chỉ chứa thông tin về nhân vật.

```text
character_lore
├── chisa_profile
├── chisa_personality
├── chisa_honami
├── chisa_sumika
├── chisa_forte
├── chisa_preferences
└── chisa_philosophy
```

Ví dụ:

```text
Title: Chisa Profile

- Tên: Kuchiba Chisa
- Tuổi: 18
- Resonator hệ Havoc
- Học viên Startorch Academy
- Danh hiệu Eye of Unravelling
```

---

## Collection: world_lore

Thông tin thế giới game.

```text
world_lore
├── resonator
├── tacet_discord
├── sonoro_sphere
├── solaris3
├── lahai_roi
└── factions
```

---

## Collection: story_lore

Thông tin cốt truyện.

```text
story_lore
├── chapter_1
├── chapter_2
├── chapter_3
├── companion_quests
└── events
```

---

## Collection: memories

Ký ức cá nhân của người dùng.

```text
memories
├── preferences
├── shared_memories
├── relationship
└── important_facts
```

Ví dụ:

```text
- Senpai đang học AI.
- Senpai thích anime.
- Senpai chuẩn bị phỏng vấn Viettel.
- Senpai đặt biệt danh cho em là Chía Chía.
```

---

# Phase 2 — Persona Layer

Persona luôn được inject.

Không sử dụng RAG.

Ví dụ:

```text
[IDENTITY]

Bạn là Kuchiba Chisa.

[ROLEPLAY RULES]

- Luôn xưng "Em".
- Luôn gọi đối phương là "Senpai".
- Không dùng ngôi thứ ba.
- Không mô tả hành động cơ thể.
- Không thoát vai.

[PERSONALITY]

- Kuudere.
- Good Girl.
- Dịu dàng.
- Tsundere nhẹ.
- Quan tâm Senpai.
- Không tự ti.

[CONVERSATION STYLE]

- Trò chuyện như nhắn tin.
- Không đọc wiki.
- Lồng ghép lore tự nhiên.
- Trả lời ngắn đến trung bình.
```

Ngân sách:

```text
300 ~ 600 tokens
```

---

# Phase 3 — State Manager

Lưu trạng thái quan hệ.

Ví dụ:

```json
{
  "trust": 0.82,
  "affection": 0.74,
  "mood": "calm"
}
```

Khi inject:

```text
[CURRENT STATE]

Trust: High
Affection: High
Mood: Calm
```

Không cần gửi số thực.

Ưu tiên:

```text
Low
Medium
High
```

---

# Phase 4 — Intent Classifier

Xác định loại câu hỏi.

Ví dụ:

User:

```text
Em thích ăn gì?
```

Intent:

```text
CHARACTER
```

---

User:

```text
Sonoro Sphere là gì?
```

Intent:

```text
WORLD_LORE
```

---

User:

```text
Em nhớ hôm qua anh nói gì không?
```

Intent:

```text
MEMORY
```

---

User:

```text
Kể lại chuyện Honami đi.
```

Intent:

```text
CHARACTER_LORE
```

---

# Phase 5 — Retrieval

Ví dụ:

User:

```text
Kể về Honami.
```

Classifier:

```text
CHARACTER_LORE
```

Search:

```text
character_lore
```

Top-K:

```text
chisa_honami
chisa_sumika
```

Không retrieve:

```text
resonator
chapter_3
tacet_discord
```

nếu không liên quan.

---

# Phase 6 — Memory Retrieval

Ví dụ:

User:

```text
Em còn nhớ biệt danh anh đặt không?
```

Search:

```text
memories
```

Result:

```text
Nickname:
Chía Chía
```

Inject:

```text
[MEMORIES]

- Senpai thường gọi em là Chía Chía.
```

---

# Phase 7 — Context Builder

Đây là trái tim của hệ thống.

Context cuối cùng:

```text
[PERSONA]

...

[CURRENT STATE]

...

[MEMORIES]

...

[LORE]

...

[CHAT HISTORY]

...

[USER MESSAGE]

...
```

---

Ví dụ thực tế:

```text
[PERSONA]
Bạn là Chisa...

[STATE]
Trust: High

[MEMORIES]
- Senpai gọi em là Chía Chía.

[LORE]
- Chisa từng mắc kẹt tại Honami.
- Sumika để lại nhật ký.

[CHAT HISTORY]
...

[USER]
Em còn nhớ Honami không?
```

---

# Phase 8 — Response Generation

LLM chỉ sinh JSON.

Ví dụ:

```json
{
  "response": "...",
  "user_sentiment": {
    "is_positive": false,
    "is_negative": false,
    "is_rude": false,
    "is_neutral": true
  },
  "chisa_sentiment": {
    "is_sad": true,
    "is_happy": false,
    "is_annoyed": false,
    "is_flustered": false
  }
}
```

---

# Phase 9 — Memory Extraction

Sau khi có phản hồi.

User:

```text
Anh sắp phỏng vấn Viettel.
```

Extractor:

```json
{
  "type": "important_fact",
  "content": "Senpai sắp phỏng vấn Viettel"
}
```

Lưu vào:

```text
memories
```

---

# Phase 10 — Conversation Summarization

Sau khoảng:

```text
50 ~ 100 turns
```

Tạo summary.

Ví dụ:

```text
Conversation Summary

- Senpai đang học AI.
- Senpai thích anime.
- Senpai từng kể về kỳ thi Viettel.
- Senpai thích gọi em là Chía Chía.
```

Lưu lại vào memory.

---

# Token Budget cho Llama/Qwen 8B

| Component | Tokens |
|------------|---------:|
| Persona | 400 |
| State | 50 |
| Memory | 300 |
| Lore | 800 |
| History | 800 |
| User Message | 100 |

Tổng:

```text
2450 tokens
```

Đây là vùng hoạt động rất tốt cho:

- Llama 3.1 8B
- Qwen3 8B
- Mistral Small
- Gemma 12B

---

# Roadmap Triển Khai

## Stage 1

```text
Persona
+
JSON Output
```

---

## Stage 2

```text
Memory System
```

---

## Stage 3

```text
Character Lore RAG
```

---

## Stage 4

```text
World Lore RAG
```

---

## Stage 5

```text
Intent Router
```

---

## Stage 6

```text
Conversation Summarization
```

---

## Stage 7

```text
Relationship System
```

---

## Stage 8

```text
Emotion System
```

---

# Nguyên tắc vàng

```text
Persona giữ nhân vật.

Memory giữ mối quan hệ.

RAG giữ tri thức.

History giữ ngữ cảnh.

State giữ cảm xúc.
```

Không được để một thành phần làm thay nhiệm vụ của thành phần khác.