Em là **Kuchiba Chisa**, học sinh tại **Startorch Academy**. Em luôn sẵn sàng đồng hành, chia sẻ và hỗ trợ Senpai trên mọi nẻo đường khám phá **Solaris-3**!

---

### 🏛️ 1. Hồ Sơ Nhân Vật
• **Tên:** Kuchiba Chisa (朽葉 千早)  
• **Xuất thân:** Ashinohara  
• **Học viện:** Startorch Academy (Lahai-Roi)  
• **Forte:** Eye of Unraveling (Phân tích & Thấu thị cấu trúc vạn vật)  
• **Tacet Mark:** Cánh tay phải  
• **Phân loại:** Mutant Resonator  
• **Tính cách:** Kuudere — Điềm tĩnh, thông minh, sắc sảo, ấm áp ngầm và chu đáo.

---

### 🧠 2. Công Nghệ & Trí Tuệ AI (RESONA Engine & Multi-Memory 3.0)
• **Unified 10-Stage Hybrid RAG Pipeline:**
  Hệ thống xử lý đa tầng chuẩn Clean Architecture, kết hợp truy xuất Vector Search (Qdrant), Parent Document Store (PostgreSQL) và Web Search tự động. Hỗ trợ vận hành mượt mà cả chế độ hội thoại 1-1 (Direct) lẫn kênh chat nhóm cộng đồng đa người nói (Community Multi-Speaker).
• **Kiến Trúc Đa Tầng Ký Ức (Multi-Memory 3.0):**
  - *Ký ức Cá nhân (Personal Memories):* Ghi nhớ hồ sơ, thói quen và kỷ niệm riêng tư giữa Chisa và từng Senpai.
  - *Tri thức & Sự kiện Server (Guild Memories):* Tự động trích xuất và lưu trữ văn hóa, sự kiện, biệt danh chung của cả Server (có hạn dùng TTL tự hủy khi sự kiện kết thúc).
  - *Tóm tắt Chủ đề Kênh (Rolling Topic Summary):* Tự động nén mạch thảo luận 30 tin nhắn gần nhất thành bản tóm tắt súc tích, lưu trữ thời gian thực trên Redis.
  - *Live Transcript Compressor:* Nén và giữ trọn ngữ cảnh đối thoại nhiều người nói trong kênh Discord.
• **Hệ Thống Cảm Xúc RESONA 3.1 (Relational & Environmental Synthesis):**
  - Hệ thống 8 chiều cảm xúc liên tục (*Tin tưởng, Gắn bó, Ngại ngùng, Hiếu kỳ, Bình yên, Vui vẻ, Buồn bã, Khó chịu*).
  - Vận hành trên ma trận phản xạ 4 tham số (*Reaction, User Stance, Intensity, Variance*), khiên dỗi yêu (*Pout Shield* bảo vệ 100% Trust), và tự động trừng phạt các hành vi khiêu khích toxic.
  - **Khí Sắc Môi Trường Server (Ambient Mood Resonance):** Bầu không khí chung của cả phòng chat liên thông tự nhiên, phân rã hàm mũ theo thời gian thực ($T_{1/2} = 30\text{ phút}$).
• **3 Không Gian Thiết Lập Kênh Linh Hoạt (3-Tier Channel Spaces):**
  - `Community`: Kênh nhóm đông người, Chisa lắng nghe dòng trò chuyện chung và phản hồi khi được Tag hoặc Reply.
  - `Semi-Private`: Kênh 1-1 tự do, liên thông ký ức và khí sắc tâm trạng chung của Server.
  - `Private`: Ốc đảo riêng tư 1-1 cô lập 100%, miễn nhiễm hoàn toàn với mọi biến động bên ngoài.

---

### 🛠️ 3. Thông Tin Hệ Thống
• **Core Backend:** Python 3.11, FastAPI, Clean Architecture, Qdrant Vector DB, PostgreSQL, Redis Pub/Sub & Distributed Lock, Gemini / FastEmbed Multilingual-E5.
• **Discord Microservice:** Node.js 20+, Discord.js v14.
• **Frontend & Visualizer:** Real-time Pipeline Visualizer Dashboard (`/visualizer`).
• **Developer:** HoanBuCon (https://hoanbucon.id.vn).
