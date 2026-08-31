# 🚀 Hướng Dẫn Cài Đặt, Cấu Hình & Khởi Chạy (Startup Guide)

> **Dự án**: Kuchiba Chisa — AI Companion & Game Knowledge Assistant (Wuthering Waves)  
> **Phiên bản**: Pipeline 3.0 (Hỗ trợ Multi-Memory, Multimodal Vision & REST/WebSocket)  
> **Môi trường**: Local Development (Windows/Linux/macOS) & Production Docker Container  
> **Thời gian cập nhật**: 31/08/2026

---

## 📑 Mục Lục
1. [Yêu Cầu Hệ Thống & Phần Cứng](#1-yêu-cầu-hệ-thống--phần-cứng)
2. [Cấu Hình Biến Môi Trường (.env)](#2-cấu-hình-biến-môi-trường-env)
3. [Khởi Chạy Cơ Sở Dữ Liệu & Hạ Tầng (Docker Compose)](#3-khởi-chạy-cơ-sở-dữ-liệu--hạ-tầng-docker-compose)
4. [Database Migrations (Alembic & PostgreSQL)](#4-database-migrations-alembic--postgresql)
5. [Khởi Động Backend FastAPI Server](#5-khởi-động-backend-fastapi-server)
6. [Khởi Động Discord Gateway Bot (Node.js)](#6-khởi-động-discord-gateway-bot-nodejs)
7. [Truy Cập Visualizer Dashboard & API Docs](#7-truy-cập-visualizer-dashboard--api-docs)
8. [Kiểm Thử & Chạy Test Suite](#8-kiểm-thử--chạy-test-suite)

---

## 1. Yêu Cầu Hệ Thống & Phần Cứng

- **Python**: Phiên bản `>= 3.11` (khuyến nghị Python 3.11.9)
- **Node.js**: Phiên bản `>= 18.0.0` (khuyến nghị Node 20 LTS cho Discord bot)
- **Docker & Docker Compose**: Để khởi chạy PostgreSQL 16, Redis 7 và Qdrant Vector DB
- **Cấu hình tối thiểu**:
  - **CPU**: 2 vCPU
  - **RAM**: 4GB - 6GB RAM (Tối ưu hóa chạy trên VPS 6GB)
  - **Ổ cứng**: Tối thiểu 10GB dung lượng trống

---

## 2. Cấu Hình Biến Môi Trường (.env)

Tạo file `.env` tại thư mục gốc của dự án (`kuchiba_chisa/.env`):

```bash
cp .env.example .env
```

### ⚙️ Nội dung file `.env` mẫu:

```ini
# ==============================================================================
# ENVIRONMENT & GENERAL CONFIG
# ==============================================================================
ENV=development
LOG_LEVEL=INFO
APP_HOST=0.0.0.0
APP_PORT=8000

# ==============================================================================
# DATABASE (POSTGRESQL 16)
# ==============================================================================
DATABASE_URL=postgresql+asyncpg://postgres:chisa_secret_pass@localhost:5432/chisa_db
POSTGRES_USER=postgres
POSTGRES_PASSWORD=chisa_secret_pass
POSTGRES_DB=chisa_db
POSTGRES_HOST=localhost
POSTGRES_PORT=5432

# ==============================================================================
# CACHE & DISTRIBUTED LOCK (REDIS 7)
# ==============================================================================
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_PASSWORD=
REDIS_DB=0

# ==============================================================================
# VECTOR DATABASE (QDRANT)
# ==============================================================================
QDRANT_HOST=localhost
QDRANT_PORT=6333
QDRANT_GRPC_PORT=6334
QDRANT_API_KEY=

# ==============================================================================
# LLM PROVIDERS & ADAPTERS
# ==============================================================================
# DeepSeek API (Primary Provider: DeepSeek Chat & Vision)
DEEPSEEK_API_KEY=sk-your-deepseek-api-key
DEEPSEEK_BASE_URL=https://api.deepseek.com/v1

# Google Gemini API (Fallback Vision & Multimodal Provider)
GEMINI_API_KEY=your-google-gemini-api-key

# Groq API (High-speed Fallback Provider)
GROQ_API_KEY=your-groq-api-key

# ==============================================================================
# DISCORD BOT CLIENT (NODE.JS)
# ==============================================================================
DISCORD_TOKEN=your_discord_bot_token_here
CLIENT_ID=your_discord_application_client_id
BACKEND_API_URL=http://localhost:8000
```

---

## 3. Khởi Chạy Cơ Sở Dữ Liệu & Hạ Tầng (Docker Compose)

Khởi động cụm dịch vụ phụ trợ gồm **PostgreSQL 16**, **Redis 7** và **Qdrant Vector DB**:

```powershell
# Chạy nền toàn bộ các container dịch vụ
docker compose up -d postgres redis qdrant

# Kiểm tra trạng thái hoạt động của các container
docker compose ps
```

| Dịch vụ | Cổng Host (Port) | Chức năng trong Hệ thống |
| :--- | :--- | :--- |
| **PostgreSQL 16** | `5432` | Lưu trữ User, Messages, EmotionState, Lore Parent Docs |
| **Redis 7** | `6379` | L1 Write-Through Cache, Distributed Lock, Answer Cache |
| **Qdrant Vector DB** | `6333` (HTTP) / `6334` (gRPC) | Lưu trữ Vector Embeddings 6 collections |

---

## 4. Database Migrations (Alembic & PostgreSQL)

Trước khi khởi chạy Backend, thực hiện khởi tạo schema và bảng biểu cơ sở dữ liệu:

```powershell
# Kích hoạt môi trường ảo Python
.\venv\Scripts\Activate.ps1    # Trên Windows PowerShell
# source venv/bin/activate     # Trên Linux / macOS

# Cài đặt thư viện dependencies
pip install -r requirements.txt

# Chạy migration nâng cấp database lên phiên bản mới nhất
alembic upgrade head
```

---

## 5. Khởi Động Backend FastAPI Server

Chạy máy chủ backend FastAPI với Hot Reload:

```powershell
# Khởi động máy chủ Uvicorn
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Khi khởi động thành công, hệ thống sẽ tự động thực hiện:
- **Lifespan Pre-warming**: Nạp trước tập vector anchors Small Talk và Persona vào RAM.
- **Qdrant Collection Verification**: Kiểm tra và tự động khởi tạo 6 collections (`memories`, `guild_memories`, `image_memories`, `character_lore`, `world_lore`, `story_lore`).
- **Redis State Cache Connection**: Kiểm tra kết nối Redis L1.

---

## 6. Khởi Động Discord Gateway Bot (Node.js)

Mở terminal thứ hai để khởi chạy Discord Bot Client:

```powershell
# Chuyển vào thư mục discord
cd discord

# Cài đặt Node modules
npm install

# Đăng ký Slash Commands với Discord API (/ask, /clear, /setup)
node deploy-commands.js

# Khởi động Discord Bot
node index.js
```

### 🎮 Các lệnh Discord có sẵn:
- `c!ask <câu hỏi>` hoặc `@Chisa <câu hỏi>` hoặc `/ask`: Trò chuyện cùng Chisa.
- `c!clear [self|all]`: Xóa lịch sử và ký ức cá nhân hoặc phòng chat.
- `c!setup [mode: private|community]`: Thiết lập chế độ trò chuyện của kênh.
- `c!docs`: Xem bảng hướng dẫn nhanh các tính năng.

---

## 7. Truy Cập Visualizer Dashboard & API Docs

- 📊 **Visualizer Dashboard (Thời gian thực)**: [http://localhost:8000/visualizer](http://localhost:8000/visualizer)
  - Giám sát luồng thực thi 10 Stages.
  - Phân tích chi tiết Token Budget Flex Ceiling.
  - Xem trực tiếp Live Channel Transcript, Server Ambient Mood và biểu đồ cảm xúc 8 chiều.
- 📖 **Swagger OpenAPI Documentation**: [http://localhost:8000/docs](http://localhost:8000/docs)
- 📑 **Redoc Interactive API Reference**: [http://localhost:8000/redoc](http://localhost:8000/redoc)

---

## 8. Kiểm Thử & Chạy Test Suite

Để đảm bảo toàn bộ hệ thống hoạt động ổn định và chính xác $100\%$:

```powershell
# Chạy toàn bộ Unit Test Suite
pytest tests/unit/ -v

# Chạy kiểm thử riêng các module cốt lõi
pytest tests/unit/test_context_budget_manager.py tests/unit/test_user_state_cache.py tests/unit/test_community_topic_summarizer.py tests/unit/test_unified_auto_summarize.py -v
```
