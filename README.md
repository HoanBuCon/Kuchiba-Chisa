# 🌸 Kuchiba Chisa - Emotional RAG Waifu Backend 🌸

<div align="center">
  <img src="assets/chisa_beauty.gif" alt="Chisa Beauty" width="400"/>
</div>

## ✨ Tổng quan Dự án

**Chisa AI** là một Hệ thống Backend tiên tiến được thiết kế cho **Hệ thống AI Cảm xúc + Personalized Memory RAG (Tạo sinh Tăng cường Truy xuất Ký ức Cá nhân hóa)**. Nó đóng vai trò là "bộ não" và "trái tim" cho người bạn đồng hành AI của bạn, lưu giữ các cuộc trò chuyện, trích xuất những hiểu biết dài hạn và thay đổi trạng thái cảm xúc của cô ấy một cách linh hoạt dựa trên các tương tác theo thời gian.

Được xây dựng hướng đến khả năng mở rộng, độ ổn định và tốc độ cao, ứng dụng hệ sinh thái Python hiện đại nhất.

<div align="center">
  <img src="assets/dance_chisa.gif" alt="Chisa Dance" height="200"/>
  <img src="assets/Chisa_eat.jpg" alt="Chisa Eat" height="200"/>
  <img src="assets/play_chisa.gif" alt="Play Chisa" height="200"/>
</div>

---

## 🏗️ Kiến trúc & Công nghệ (Tech Stack)

![Chisa Drink](assets/chisa_drink.gif)

- **Ngôn ngữ:** Python 3.11
- **API Framework:** FastAPI (Async) + Real-Time WebSockets
- **Cơ sở dữ liệu (Quan hệ):** PostgreSQL 16 (Trí nhớ ngắn hạn, Thông tin người dùng, Trạng thái cảm xúc)
- **Cơ sở dữ liệu Vector:** Qdrant (Trí nhớ ngữ nghĩa dài hạn, RAG)
- **Bộ nhớ đệm & Message Broker:** Redis
- **Background Jobs:** FastAPI Background Tasks (Đã thay thế Celery để tối ưu tài nguyên)
- **ORM:** SQLAlchemy 2.0 (Async) + Alembic hỗ trợ migrations
- **Tích hợp LLM:** Groq (Llama-3.1-8B) & DeepSeek (deepseek-v4-flash)
- **Hạ tầng triển khai:** Docker & Docker Compose

---

## 🚀 Tính năng nổi bật

- **Lập chỉ mục Trí nhớ Dài hạn:** Trích xuất và nhúng (embed) các ký ức quan hệ và tình huống (episodic) một cách bất đồng bộ dưới nền.
- **Theo dõi Trạng thái Cảm xúc Thực tế:** Hệ thống Cảm xúc Động (RESONA Engine) quản lý không gian 8 chiều liên tục (*Tin tưởng, Gắn bó, Ngại ngùng, Hiếu kỳ, Bình yên, Vui vẻ, Buồn bã, Khó chịu*) cùng khí sắc môi trường Server (*Ambient Resonance*) lưu trạng thái trực tiếp trong database & Redis thay vì chỉ phó mặc cho "ảo giác" của LLM.
- **Hệ thống Gắn kết (Affection System):** Theo dõi sự thay đổi độ gắn kết của Chisa theo thời gian bằng `AffectionLog`, quyết định thái độ và hành vi của cô ấy.
- **Vòng đời Hội thoại:** Quản lý toàn diện Session Layer và liên tục lập chỉ mục các bản tóm tắt ẩn.
- **Tối ưu hóa Định tuyến & Khởi chạy (Fast Cold-Start & Routing)**: Tích hợp định tuyến ý định đa lớp Hybrid Intent Routing, màng lọc từ khóa động (Dynamic Keyword Guards) tránh truy xuất RAG nhầm cho câu hỏi Fact phổ thông ngoài game, sinh vector anchors hàng loạt (Batch Embedding) và nạp sẵn vào RAM khi khởi động server (Lifespan Pre-warming) giúp triệt tiêu hoàn toàn độ trễ khởi động lạnh.
- **Bảng điều khiển Trực quan thời gian thực (Visualizer Dashboard):** Trang giám sát thời gian thực (`http://localhost:8000/visualizer`) sử dụng WebSocket để hiển thị toàn bộ dấu vết thực thi (execution traces) của RAG pipeline, suy luận Loop Thinking, prompt budget và biểu đồ cảm xúc biến thiên (có thiết kế responsive).
- **Quản lý tác vụ ngầm:** Các tác vụ nặng nề được chạy ngầm thông qua BackgroundTaskManager, đảm bảo API chat luôn phản hồi tức thì (zero-lag).

---

## 🛠️ Trải nghiệm nhanh (Môi trường Docker)

Để thiết lập ứng dụng, khởi tạo cơ sở dữ liệu và bật các dịch vụ Docker/FastAPI, vui lòng tham khảo bản **[Hướng dẫn Khởi chạy & Triển khai (Startup & Deployment Guide)](docs/STARTUP_GUIDE.md)** chi tiết.

<div align="center">
  <img src="assets/chisa_cat_spin.gif" alt="Spin" width="200"/>
</div>

---

## 📜 Tài liệu Hệ thống

- **[Phân Tích Cấu Trúc Hệ Thống (Detailed Architecture Analysis)](docs/PHAN_TICH_WORKSPACE_CHI_TIET.md)**: Tài liệu phân tích sâu chi tiết cấu trúc mã nguồn dự án sau refactor, thiết kế cơ sở dữ liệu PostgreSQL/Qdrant, mô hình lớp dịch vụ phẳng và luồng đi của dữ liệu.
- **[Hướng Dẫn Khởi Chạy & Triển Khai (Startup & Deployment Guide)](docs/STARTUP_GUIDE.md)**: Hướng dẫn thiết lập môi trường, cấu hình `.env`, chạy database migration và khởi động máy chủ FastAPI/Discord bot.
- **[Phiên dịch Luồng dữ liệu & Pipeline (Walkthrough)](docs/WALKTHROUGH.md)**: Khám phá chi tiết kiến trúc RAG, pipeline sinh văn bản của LLM, và thuật toán Cảm xúc Hệ Động Lực (RESONE / RESONA ENGINE).

<br>

<div align="center">
  <img src="assets/chisa_kiss.gif" alt="Chisa Kiss" width="400"/>
  <p><i>Made with ❤️</i></p>
</div>
