# 🚀 Hướng Dẫn Cài Đặt, Cấu Hình & Khởi Chạy (Startup Guide)

> **Dự án**: Kuchiba Chisa — AI Companion & Game Knowledge Assistant (Wuthering Waves)  
> **Phiên bản**: Pipeline 3.0 (Hỗ trợ Multi-Memory, Multimodal Vision & REST/WebSocket)  
> **Môi trường**: Local Development (Windows/Linux/macOS) & Production Docker Container  
> **Thời gian cập nhật**: 31/08/2026

---

## ⚡ Quick start (môi trường DEV, một lệnh)

> Chỉ dành cho **development** trên máy local. CLI từ chối chạy nếu `APP_ENV` khác `development`
> hoặc nếu DB/Redis/Qdrant/API không phải `localhost`. Hướng dẫn production: `docs/DEPLOYMENT_RUNBOOK.md`.

**Chuẩn bị (một lần)**

1. Python 3.11 + venv: `python -m venv venv`, kích hoạt, `pip install -r requirements-dev.txt`.
2. Node.js >= 20: `cd frontend && npm ci` và (nếu dùng bot) `cd discord && npm ci`.
3. Docker Desktop đang chạy.
4. Lần chạy đầu cần mạng: tải model embedding ~470 MB vào `.dev/models` (chỉ một lần).
5. `cp .env.example .env`, rồi điền các biến **bắt buộc** (tên biến, không đặt giá trị mẫu):

| Nhóm | Biến |
| :--- | :--- |
| Môi trường | `APP_ENV=development` |
| Kết nối (đều là `localhost`) | `DATABASE_URL` (có mật khẩu dev), `REDIS_URL`, `QDRANT_URL` |
| Bí mật (>= 32 ký tự, không để giá trị mẫu) | `JWT_SECRET`, `SECRET_KEY`, `DISCORD_WORKLOAD_JWT_SECRET` |
| LLM (theo `LLM_PROVIDER`) | `DEEPSEEK_API_KEY` (hoặc `GROQ_API_KEY` / `GEMINI_API_KEY`) |
| Reranker (theo `RERANKER_PROVIDER`) | `VOYAGE_API_KEY` / `JINA_API_KEY` / `COHERE_API_KEY` |
| Tùy chọn cho dev | `PUBLIC_APP_URL=http://localhost:5173`, các `QUOTA_*` (dev đặt cao), `SMTP_*` |

Bot Discord (tùy chọn): trong `discord/.env` cần `DISCORD_TOKEN`, `DISCORD_CLIENT_ID` và
`CORE_RAG_WORKLOAD_JWT_SECRET` (**bằng đúng** `DISCORD_WORKLOAD_JWT_SECRET` trong `.env` gốc).
Kiểm tra cấu hình bất cứ lúc nào: `chisa dev check [--discord]` (chỉ in tên biến thiếu, không in giá trị).

**Chạy**

```bash
./chisa dev start              # Git Bash / Linux / macOS      (Windows cmd/PowerShell: chisa.bat dev start)
./chisa dev start --discord    # kèm bot Discord
```

Lệnh này lần lượt: kiểm tra env -> bật Postgres/Redis/Qdrant (Docker, chỉ bind `127.0.0.1`, **dùng lại volume dev
có sẵn**) -> Alembic (tự `pg_dump` vào `.dev/backups` trước khi nâng cấp DB cũ) -> tạo alias Qdrant `*__active`
-> tải model embedding (lần đầu) -> backend (`http://127.0.0.1:8000`) -> worker -> frontend
(`http://127.0.0.1:5173`, proxy `/api`) -> bot (nếu có). Mỗi bước **chờ sẵn sàng thật** rồi mới đi tiếp; lỗi thì dừng
và in đuôi log (đã che bí mật).

| Lệnh | Tác dụng |
| :--- | :--- |
| `./chisa dev status` | Trạng thái hạ tầng, migration, backend `/ready`, worker, frontend, bot |
| `./chisa dev logs [backend\|worker\|frontend\|discord] [-n 50] [-f]` | Log (`.dev/logs/*.log`, đã che bí mật) |
| `./chisa dev test` | Smoke test hệ thống (xem dưới) |
| `./chisa dev restart [--discord]` | Dừng app rồi chạy lại |
| `./chisa dev stop [--infra]` | Dừng app; `--infra` dừng cả Postgres/Redis/Qdrant (**không bao giờ xóa dữ liệu**) |
| `./chisa dev migrate` / `bootstrap` | Chỉ chạy Alembic / chỉ tạo alias Qdrant |
| `./chisa dev backfill-lore-acl` | Một lần: đánh dấu lore dev cũ là `public` (xem Troubleshooting) |

**Health / readiness**: `GET http://127.0.0.1:8000/health` (process sống), `GET /ready` (Postgres, Redis, Qdrant alias, cấu hình LLM).

**Smoke test** (`./chisa dev test`, cần stack đang chạy): hạ tầng, migration ở head, lore nhìn thấy được, `/health`, `/ready`,
worker, frontend + proxy, một lượt chat thật qua frontend -> backend -> LLM (phải là câu trả lời thật, **không phải
fallback**), dọn hội thoại thử, và (nếu bot đang chạy) token workload -> Core -> chat; cuối cùng quét log tìm bí mật bị lộ.
Trả mã thoát khác 0 nếu có bước FAIL.

**Troubleshooting**

| Triệu chứng | Nguyên nhân / cách xử lý |
| :--- | :--- |
| `shell environment overrides .env for: …` | Shell đang export biến cùng tên (vd `APP_ENV=production`). `unset` rồi chạy lại. |
| `docker compose failed` / cổng 5432, 6379, 6333 bận | Docker Desktop chưa chạy, hoặc dịch vụ khác giữ cổng. Dừng nó hoặc `./chisa dev stop --infra`. |
| `alembic upgrade failed: … already exists` | Schema DB dev từng bị sửa ngoài Alembic. DB vẫn nguyên (đã có bản `pg_dump` trong `.dev/backups`). So schema với một DB Alembic mới, rồi `alembic stamp <revision đã thật sự áp dụng>` và chạy lại. |
| `backend /ready: not ready after 150s` | Xem `chisa dev logs backend`. Thường là Qdrant thiếu alias (`chisa dev bootstrap`) hoặc thiếu key LLM. |
| Lần đầu chạy rất lâu ở `[embeddings]` | Đang tải model ~470 MB; để yên. Hỏng giữa chừng thì xóa `.dev/models` và chạy lại. |
| Chat trả "Mình chưa có đủ bằng chứng…" cho câu hỏi lore, `citations: []` | Lore dev cũ thiếu `access_scope` nên retrieval không thấy: `./chisa dev backfill-lore-acl` (idempotent, chỉ thêm một khóa payload). |
| Chat trả "Chisa hơi mệt…" hoặc có `emotions: null` | Fallback do LLM lỗi/timeout hoặc bị guard an toàn đầu ra từ chối; xem `chisa dev logs backend` và thử lại (LLM không tất định). |
| HTTP 429 khi chat | Hết quota/giới hạn phút. Dev đặt `QUOTA_*` cao trong `.env`; mặc định production thấp hơn nhiều. |
| Đăng ký / quên mật khẩu trả 503 | Chưa cấu hình `SMTP_HOST`/`SMTP_FROM`: đúng thiết kế. Dev dùng chat ẩn danh hoặc Google; muốn thử luồng email thì điền `SMTP_*` thật. |
| `[discord] … not ready` | Token sai/hết hạn, hoặc `CORE_RAG_WORKLOAD_JWT_SECRET` khác `DISCORD_WORKLOAD_JWT_SECRET`. Xem `chisa dev logs discord`. |

Trạng thái cục bộ (PID, log, bản sao lưu, cache model) nằm trong `.dev/` (đã gitignore).

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

> ⚠️ Nội dung mẫu bên dưới là bản cũ; tên biến chính xác và cách chạy một lệnh nằm ở mục **Quick start (DEV)** phía trên
> và trong `.env.example`.

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

Khởi động cụm dịch vụ phụ trợ gồm **PostgreSQL 16**, **Redis 7** và **Qdrant Vector DB**.
Cho DEV, dùng `./chisa dev start` (hoặc `docker compose -f docker-compose.dev.yml up -d`); `docker-compose.yml` là cấu hình
production (Docker secrets, Redis ACL) và không dùng cho máy dev:

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
