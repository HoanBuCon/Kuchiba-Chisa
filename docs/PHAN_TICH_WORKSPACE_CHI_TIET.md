# 🏛️ Phân Tích Cấu Trúc Mã Nguồn & Kiến Trúc Dự Án (Workspace Architecture)

> **Dự án**: Kuchiba Chisa — AI Companion & Game Knowledge Assistant  
> **Kiến trúc**: Clean Architecture (Layered) kết hợp Pipes & Filters Pipeline  
> **Thời gian cập nhật**: 31/08/2026

---

## 📑 Mục Lục
1. [Mô Hình Kiến Trúc Tổng Thể (Clean Architecture)](#1-mô-hình-kiến-trúc-tổng-thể-clean-architecture)
2. [Cây Thư Mục Dự Án (Directory Tree)](#2-cây-thư-mục-dự-án-directory-tree)
3. [Phân Tích Chi Tiết Từng Tầng Mã Nguồn](#3-phân-tích-chi-tiết-từng-tầng-mã-nguồn)
   - [Tầng 1: Domain Layer (`app/domain/`)](#tầng-1-domain-layer-appdomain)
   - [Tầng 2: Application Layer (`app/application/`)](#tầng-2-application-layer-appapplication)
   - [Tầng 3: Infrastructure Layer (`app/infrastructure/`)](#tầng-3-infrastructure-layer-appinfrastructure)
   - [Tầng 4: Interface Layer (`app/interface/`)](#tầng-4-interface-layer-appinterface)
4. [Mô Hình Dữ Liệu & Hệ Thống Lưu Trữ](#4-mô-hình-dữ-liệu--hệ-thống-lưu-trữ)
   - [PostgreSQL 16 (Relational Schema)](#postgresql-16-relational-schema)
   - [Qdrant Vector Collections (6 Collections)](#qdrant-vector-collections-6-collections)
   - [Redis 7 Key Namespace & TTL](#redis-7-key-namespace--ttl)
5. [Luồng Tương Tác & Dependency Injection](#5-luồng-tương-tác--dependency-injection)

---

## 1. Mô Hình Kiến Trúc Tổng Thể (Clean Architecture)

Hệ thống được tổ chức theo 4 vòng tròn đồng tâm của **Clean Architecture**, đảm bảo tính độc lập tối đa của logic nghiệp vụ lõi khỏi các framework hay cơ sở dữ liệu bên ngoài:

```
┌─────────────────────────────────────────────────────────────┐
│ 4. INTERFACE LAYER (FastAPI API Routes, WebSockets, Discord)│
│   ┌─────────────────────────────────────────────────────────┐
│   │ 3. INFRASTRUCTURE LAYER (PostgreSQL, Qdrant, Redis, LLM)│
│   │   ┌─────────────────────────────────────────────────────┐
│   │   │ 2. APPLICATION LAYER (Use Cases, DI Container)      │
│   │   │   ┌─────────────────────────────────────────────────┐
│   │   │   │ 1. DOMAIN LAYER (Entities, Pipeline Stages,     │
│   │   │   │    RESONA Emotion Engine, Context Builder)      │
│   │   │   └─────────────────────────────────────────────────┘
│   │   └─────────────────────────────────────────────────────┘
│   └─────────────────────────────────────────────────────────┘
└─────────────────────────────────────────────────────────────┘
```

---

## 2. Cây Thư Mục Dự Án (Directory Tree)

```
kuchiba_chisa/
├── app/
│   ├── application/                # Tầng Application: Use Cases & Dependency Injection
│   │   ├── dependencies.py         # DI Container (Khởi tạo toàn bộ Service & Stages)
│   │   └── usecases/               # Use cases nghiệp vụ (Clear memory, Ingestion...)
│   ├── config/                     # Cấu hình hệ thống, settings & tuning constants
│   ├── domain/                     # Tầng Domain Nghiệp Vụ Lõi
│   │   ├── entities/               # Data Classes (User, EmotionState, CommunityMessage...)
│   │   ├── interfaces/             # Abstract Repositories & LLM Provider Interfaces
│   │   └── services/               # Dịch vụ Domain cốt lõi
│   │       ├── chat_pipeline/      # 10 Sequential Pipeline Stages (Pipes & Filters)
│   │       │   ├── context.py      # ChatContext xuyên suốt vòng đời request
│   │       │   ├── stage.py        # PipelineStage ABC
│   │       │   └── stages/         # 11 implementation classes (Init, Intent, RAG...)
│   │       ├── community/          # TranscriptFormatter, AmbientManager, TopicSummarizer
│   │       ├── emotion_engine.py   # RESONA Emotion Engine 3.0
│   │       ├── context_builder.py  # StructuredPrompt Assembly & U-curve sort
│   │       ├── context_budget_manager.py # Flex Ceiling Token Budget Allocation
│   │       ├── memory_extractor.py # Batch Fact Extractor & Conflict Reconciliation
│   │       └── rag/                # RAG Pipeline, Retrievers, Assessor, ThinkingLoop
│   ├── infrastructure/             # Tầng Infrastructure (Drivers & Adapters)
│   │   ├── database/               # PostgreSQL Connection Pool & SQLAlchemy Models
│   │   ├── repositories/           # SQLAlchemy Repositories & Unit of Work
│   │   ├── vector/qdrant/          # Qdrant Vector Client & Multi-Collection Store
│   │   ├── cache/                  # Redis Client, UserStateCache & Locks
│   │   ├── llm/adapters/           # DeepSeek & Gemini LLM Adapters
│   │   └── logging/                # PipelineTracker & WebSocket Telemetry
│   └── interface/                  # Tầng Interface (Giao tiếp người dùng)
│       └── api/                    # FastAPI Routes, Schemas & Visualizer Static Files
├── discord/                        # Discord Gateway Client (Node.js 20 LTS)
├── docs/                           # Tài liệu kỹ thuật vận hành
├── reports/                        # Báo cáo kiểm toán & Đề xuất kỹ thuật
└── tests/                          # Automated Test Suite (Unit & Integration Tests)
```

---

## 3. Phân Tích Chi Tiết Từng Tầng Mã Nguồn

### Tầng 1: Domain Layer (`app/domain/`)
- **Entities (`app/domain/entities/`)**:
  - `User`, `UserStats`: Quản lý cấp độ tương tác, streak và thời gian tương tác.
  - `EmotionState`: Vector cảm xúc 8 chiều (*Joy, Sadness, Irritation, Trust, Attachment, Shyness, Curiosity, Comfort*).
  - `CommunityMessage`: Cấu trúc tin nhắn phòng chat đa người dùng kèm speaker metadata.
- **Chat Pipeline (`app/domain/services/chat_pipeline/`)**:
  - Xâu chuỗi 10 Canonical Stages tuần tự xử lý `ChatContext`.
- **RESONA Emotion Engine 3.0 (`app/domain/services/emotion_engine.py`)**:
  - Ma trận tương hỗ 2 cờ (`reaction` $\times$ `user_stance`), luật bão hòa Saturation Headroom và triệt tiêu đối kháng chéo Antagonistic Cross-Inhibition.

### Tầng 2: Application Layer (`app/application/`)
- **Container Khởi Tạo (`dependencies.py`)**:
  - Khởi tạo Singletons: `PostgreSqlPool`, `RedisClient`, `QdrantService`, `LLMClient`, `ContextBuilder`.
  - Lắp ráp mảng `stages` của `ChatPipeline` và bàn giao cho `ChatEngine`.

### Tầng 3: Infrastructure Layer (`app/infrastructure/`)
- **PostgreSQL Repositories**:
  - `SqlAlchemyUserRepository`, `SqlAlchemyEmotionRepository`, `SqlAlchemyConversationRepository`, `LoreParentRepository`.
- **Qdrant Vector Service (`qdrant_service.py`)**:
  - Quản lý 6 collections, Payload schema, HNSW RAM/On-disk indices và Vector search.
- **Redis Cache & Lock (`user_state_cache.py`, `redis_service.py`)**:
  - `chisa:user:{id}:state`: Write-through cache L1 (~0.2ms) giảm $95\%$ query SQL.
  - `chisa:chat_lock:{id}`: Distributed Lock chống race condition khi chat dồn dập.

### Tầng 4: Interface Layer (`app/interface/`)
- **REST Endpoints (`app/interface/api/routes/`)**:
  - `POST /api/v1/chat`: Direct 1-on-1 Chat endpoint.
  - `POST /api/v1/community/chat`: Group/Channel Community Chat endpoint.
  - `POST /api/v1/chat/stream`: Server-Sent Events (SSE) Streaming response.
  - `GET /api/v1/visualizer/ws`: WebSocket telemetry stream cho dashboard.

---

## 4. Mô Hình Dữ Liệu & Hệ Thống Lưu Trữ

### PostgreSQL 16 (Relational Schema)
- `users`: Thông tin định danh `user_uuid`, `platform_id`, `created_at`.
- `user_stats`: Chỉ số `interaction_count`, `trust_level`, `attachment_level`, `last_seen`.
- `user_emotions`: Bản ghi cảm xúc 8 chiều `joy`, `sadness`, `trust`, `attachment`...
- `conversations`: Quản lý phiên hội thoại và trường `summary` tích lũy.
- `messages`: Lưu trữ tin nhắn `role`, `content`, `rewritten_content`, `media_metadata`.
- `lore_parent_docs`: Lưu trữ tài liệu cha Markdown phục vụ Windowed Parent Resolution 1200 chars.

### Qdrant Vector Collections (6 Collections)
1. `memories`: Ký ức cá nhân (`user_id`, `fact`, `category`, `decay`).
2. `guild_memories`: Tri thức server (`guild_id`, `fact`, `category`, `expires_at`).
3. `image_memories`: Ký ức thị giác (`user_id`, `image_id`, `url`, `visual_caption`, `tags`).
4. `character_lore`: Tri thức nhân vật Wuthering Waves.
5. `world_lore`: Tri thức thế giới Solaris-3, địa danh, factions.
6. `story_lore`: Cốt truyện và hội thoại nhiệm vụ.

### Redis 7 Key Namespace & TTL
| Redis Key Pattern | Kiểu Dữ Liệu | TTL | Chức năng |
| :--- | :--- | :--- | :--- |
| `chisa:user:{uid}:state` | JSON Hash | 7 ngày | L1 Write-Through Cache (Stats + Emotion) |
| `chisa:user:{uid}:summary` | String | 7 ngày | Fast-Path Private Conversation Summary |
| `chisa:channel:{cid}:rolling_buffer` | JSON List | 7 ngày | Hàng đợi tin nhắn cộng đồng tích lũy (Max 60) |
| `chisa:channel:{cid}:topic_summary` | String | 7 ngày | Bản tóm tắt chủ đề kênh gần nhất |
| `chisa:guild:{gid}:ambient_mood` | JSON Hash | 7200s | Khí sắc cảm xúc chung của máy chủ |
| `chisa:chat_lock:{uid}` | String | 120s | Khóa phân tán chống race condition |
| `chisa:answer_cache:lore:{hash}` | JSON Hash | 24 giờ | Bộ nhớ đệm câu trả lời Lore thuần |
