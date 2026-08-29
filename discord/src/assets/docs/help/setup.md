**Chức năng:** Thiết lập hoặc hủy các cổng chat với 3 chế độ không gian chuyên biệt.
*(Yêu cầu quyền **Administrator** hoặc **Manage Channels**)*

---

### 🌐 3 CHẾ ĐỘ KHÔNG GIAN (CHANNEL MODES)
• **`community` (Kênh Cộng Đồng):** 
  - Thích hợp cho phòng chat đông người. 
  - Chisa chỉ trả lời khi được **Tag `@Chisa` hoặc Reply trực tiếp**. 
  - Chisa quan sát được 15 tin nhắn gần nhất của phòng để hiểu mạch trò chuyện.
• **`semi-private` (Kênh Bán Riêng Tư - Mặc định):** 
  - Trò chuyện 1-on-1 tự do trong server không cần gõ lệnh. 
  - Dùng chung bộ nhớ và hòa quyện khí sắc cảm xúc chung của Server.
• **`private` (Ốc Đảo Riêng Tư):** 
  - Trò chuyện 1-on-1 tự do trong phòng riêng. 
  - **Cô lập 100%** bộ nhớ và trạng thái cảm xúc, miễn nhiễm với mọi biến cố bên ngoài server.

---

### 📌 Cú pháp Slash Command
• `/setup action:enable [mode] [channel]` : Kích hoạt kênh theo chế độ (`community` / `semi-private` / `private`, mặc định là `semi-private` tại kênh hiện tại).
• `/setup action:disable [channel]` : Hủy kích hoạt cổng chat tại kênh chỉ định.
• `/setup action:disable all:True` : Hủy kích hoạt tất cả cổng chat trên toàn Server.
• `/setup action:list` : Xem danh sách các kênh đang được thiết lập.

---

### 📌 Cú pháp Prefix Command
• `c!setup [mode] [kênh1] [kênh2] ...` : Kích hoạt chế độ (ví dụ: `c!setup community #chung`, `c!setup private #vip`).
• `c!setup disable [kênh1] ...` : Tắt cổng chat tại một hoặc nhiều kênh.
• `c!setup disable all` : Tắt toàn bộ cổng chat trên Server.
• `c!setup list` : Xem danh sách các kênh đang kích hoạt.
