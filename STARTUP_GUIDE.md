# 🚀 Chisa AI - Startup & Deployment Guide

Tài liệu này hướng dẫn chi tiết cách thiết lập, khởi chạy và giám sát toàn bộ hệ thống Backend của **Kuchiba Chisa AI**.

Nội dung dưới đây phản ánh hiện trạng code trong workspace: backend là FastAPI, dữ liệu chạy qua PostgreSQL/Redis/Qdrant, sử dụng FastAPI Background Tasks, và frontend trong thư mục `frontend/` là một app Vite + React riêng.

---

## 1. Yêu cầu hệ thống (Prerequisites)

Để chạy được toàn bộ hệ thống mượt mà, máy tính/server của bạn cần có:
- **Hệ điều hành:** Windows (khuyến nghị chạy trên WSL2) / Linux / macOS.
- **Môi trường:** Python `3.11`.
- **Nền tảng Ảo hóa:** Docker Desktop (để chạy DB, Cache, Vector Search).
- **Phần mềm quản lý source:** Git.

---

## 2. Thiết lập Lần đầu (First-time Setup)

### Bước 2.1: Clone dự án và tạo Môi trường ảo (Virtualenv)
```powershell
git clone <repository_url>
cd kuchiba_chisa
python -m venv venv

# Kích hoạt môi trường (Windows PowerShell):
.\venv\Scripts\activate
# (Nếu ở Linux/Mac): source venv/bin/activate
```

### Bước 2.2: Cài đặt thư viện (Dependencies)
```powershell
pip install -r requirements.txt
```

### Bước 2.3: Thiết lập Biến môi trường (.env)
Copy file mẫu cấu hình để sử dụng:
```powershell
cp .env.example .env
```
Mở file `.env` lên và điền các khóa (API Key) cần thiết:
- `GROQ_API_KEY`: Lấy từ trang quản trị developer của Groq.
- `LLM_PROVIDER`: Chọn `groq` hoặc `gemini`; mặc định trong code là `groq`.
- `GEMINI_API_KEY`: Chỉ cần khi chuyển provider sang Gemini.
- `JWT_SECRET`: Một chuỗi ngẫu nhiên bảo mật của bạn.

Các biến còn lại trong `.env.example` đã có default để hỗ trợ local dev, nhưng khi lên production bạn nên khai báo đầy đủ và thay toàn bộ secret mặc định.

---

## 3. Khởi chạy Hạ tầng (Infrastructure)

Dự án phụ thuộc vào 3 mảnh ghép Core Services nằm trong Docker:
1. **PostgreSQL** (Port 5432): Lưu trữ dữ liệu User, Tin nhắn (STM) và Trạng thái Cảm xúc tĩnh.
2. **Redis** (Port 6379): Phục vụ Rate Limiting, Cache.
3. **Qdrant** (Port 6333): Vector Database lưu trữ Ký ức (Memories) và Cốt truyện (Lore).

`docker-compose.yml` hiện cũng dựng thêm 1 service ứng dụng: `app` (FastAPI).

Để chạy tất cả dịch vụ này lên, hãy dùng lệnh:
```powershell
docker compose up -d --wait
```
*(Cờ `--wait` đảm bảo các hệ thống cơ sở dữ liệu đã Health-Check thành công trước khi bạn đi tiếp).*

---

## 4. Khởi tạo Database (Migrations)

Dự án dùng **Alembic** để quản lý cấu trúc bảng PostgreSQL. Lần đầu tiện chạy dự án, bạn **BẮT BUỘC** phải build các bảng schema vào DB.
Trong môi trường `venv`, chạy lệnh:
```powershell
alembic upgrade head
```
Nếu thành công, cơ sở dữ liệu của bạn đã có đủ bảng lõi để phục vụ chat, emotion state, memory metadata và thống kê người dùng.

---

## 5. Khởi chạy Ứng dụng & Dịch vụ Nền

### 5.1 Sử dụng Script tự động hóa (PowerShell)
Nếu bạn lười gõ lệnh, dự án đã có sẵn file `start.ps1` ở thư mục gốc. Script này sẽ tự động:
- Khởi động Docker Containers.
- Reset lại các Terminal con.
- Kích hoạt mội trường ảo và nổ máy Backend.
- Bật Frontend lên ở localhost.
```powershell
.\start.ps1
```

### 5.2 Khởi chạy thủ công (Để tiện gỡ lỗi/debug)

**Chạy Backend API (FastAPI):**
```powershell
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```
> [!NOTE]
> Khi ứng dụng FastAPI khởi động, hệ thống sẽ tự động thực hiện **Pre-warming** tải và nhúng (embed) toàn bộ anchors định tuyến ngữ nghĩa bằng **Batch Mode** trực tiếp lên RAM. Nhờ đó, tin nhắn đầu tiên của người dùng sẽ được phản hồi ngay lập tức (zero cold-start latency).

Sau đó truy cập Swagger UI để theo dõi tài liệu API tại: `http://localhost:8000/docs`

Các route chính hiện có là `/api/v1/chat`, `/api/v1/chat/history/{user_id}`, `/api/v1/chat/emotions/{user_id}` và `/api/v1/chat/clear/{user_id}`; health check nằm ở nhóm route hệ thống.

**Chạy Nạp Lore Vector (Chỉ cần chạy 1 lần nếu Cốt truyện thay đổi):**
```powershell
python scripts/ingest_production_lore.py
```

---

## 6. Giám sát Hệ thống (Monitoring Scripts)

Đây là những chức năng độc quyền của dự án giúp quan sát "não bộ" của Chisa chạy ngầm dưới dạng Real-Time (Theo thời gian thực). Bạn nên bật chúng ở các Tab Terminal riêng biệt song song với Backend.

Các script này đọc dữ liệu hiện có từ database/vector store, nên sẽ hữu ích nhất sau khi đã chạy migration, khởi động infra và có ít nhất một luồng chat thực tế.

### 6.1 Gương soi Cảm xúc (Emotion Watcher)
Hiển thị trực tiếp các xung động điểm cảm xúc (Joy, Sad, Irritation...) khi Chisa đang bị người dùng tác động, tích hợp bộ đếm DEHA Algorithm:
```powershell
python .\scripts\watch_emotions.py
```

### 6.2 Máy đo dòng Token (Token Consumption Watcher)
Theo dõi lượng Token bị đốt cháy trực tiếp của mô hình Llama-3 theo từng tin nhắn, hữu ích để tối ưu chi phí và tránh lỗi `429 Rate Limit` từ Groq:
```powershell
python .\scripts\watch_tokens.py
```

### 6.3 Bảng điều khiển trực quan Web (Chisa AI Visualizer Dashboard)
Giám sát toàn bộ luồng RAG, suy luận Loop Thinking, ngân sách token và cập nhật trạng thái cảm xúc theo thời gian thực dưới giao diện Web trực quan:
- **Địa chỉ:** `http://localhost:8000/visualizer`
- **Tính năng:** Theo dõi các vết thực thi (execution traces), chi tiết từng bước RAG (Lore, Memory), phân bổ ngân sách token (Prompt Budget), thời gian phản hồi/độ trễ và biến thiên trạng thái cảm xúc chi tiết.
- Giao diện có thiết kế responsive đầy đủ, hỗ trợ tốt cả trên PC, máy tính bảng và thiết bị di động.

---

## 7. Các lỗi thường gặp (Troubleshooting)

1. **Lỗi `429 Too Many Requests` từ Groq:** 
   - Lý do: Gói Miễn phí của Groq giới hạn Token Per Minute (~14,400 TPM).
   - Giải quyết: Nếu không nâng cấp lên Developer Plan ($5), hãy chờ khoảng 1 phút trước khi chat tiếp. Hệ thống đã được cấu hình Fail-fast (Vượt lỗi đi tiếp) mà không bị treo phần mềm.

2. **Lỗi backend không khởi động được ngay lúc startup:**
   - Lý do: `app/main.py` kiểm tra Postgres, Redis và Qdrant trong lifecycle startup. Nếu thiếu một trong ba dịch vụ này, backend có thể chỉ chạy ở chế độ cảnh báo trong dev hoặc dừng hẳn khi `APP_ENV=production`.
   - Giải quyết: Kiểm tra lại `docker compose up -d --wait`, giá trị `DATABASE_URL`, `REDIS_URL`, `QDRANT_URL`, và log của từng service.

3. **Lỗi `OperationalError (could not translate host name, Connection Refused)`:**
   - Lý do: Hạ tầng Docker chưa bật lên, hoặc Cổng 5432 (PostgreSQL)/6379 (Redis) đang bị ứng dụng khác chiếm dụng.
   - Giải quyết: Bật Docker Desktop lên, chạy lệnh `docker compose down` rồi lên lại `docker compose up -d`.

4. **Lỗi thiếu Thư viện (ModuleNotFoundError):**
   - Giải quyết: Đảm bảo bạn đang ở môi trường ảo `(venv)` trước khi chạy bất kỳ script hay lệnh uvicorn nào. Chạy lại `pip install -r requirements.txt`.
