**Chức năng:** Thiết lập hoặc hủy các kênh chat trực tiếp không cần gõ lệnh.
*(Yêu cầu quyền **Administrator** hoặc **Manage Channels**)*

### 📌 Cú pháp Slash Command
• `/setup action:enable [channel]` : Kích hoạt kênh làm cổng chat trực tiếp (mặc định kênh hiện tại).
• `/setup action:disable [channel]` : Hủy kích hoạt cổng chat tại kênh chỉ định.
• `/setup action:disable all:True` : Hủy kích hoạt tất cả cổng chat trên toàn Server.
• `/setup action:list` : Xem danh sách các kênh đang kích hoạt cổng chat trực tiếp.

### 📌 Cú pháp Prefix Command
• `c!setup [kênh1] [kênh2] ...` : Kích hoạt một hoặc nhiều kênh.
• `c!setup disable [kênh1] ...` : Tắt một hoặc nhiều kênh.
• `c!setup disable all` : Tắt toàn bộ cổng chat trên Server.
• `c!setup list` : Xem danh sách các kênh đang được kích hoạt.

### 💡 Mẹo sử dụng
Trong kênh đã kích hoạt, Senpai chỉ cần nhắn tin bình thường mà không cần gõ lệnh. Thêm dấu `!` ở đầu câu nếu muốn nhắn tin thường mà không gọi Chisa.
