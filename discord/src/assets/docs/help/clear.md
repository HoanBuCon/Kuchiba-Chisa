**Chức năng:** Xóa bộ nhớ (Memory) và làm mới ngữ cảnh hội thoại của Chisa theo từng phân vùng (Cộng đồng hoặc Cá nhân).

---

### 📌 Cú pháp sử dụng
• **Slash Command:** `/clear mode:[community / private / nuke] scope:[self / all]`
• **Prefix Command:** `c!clear [community / private / nuke] [self / all]`

---

### 🎯 1. Phân loại Chế độ (Mode)

• **🌐 `community` (Ký ức Cộng đồng / Kênh chung & Semi-Private):**
  - **`scope: self`:** Xóa các tương tác và dữ kiện cộng đồng của riêng bạn. Chisa sẽ bắt nhịp lại như thành viên mới trong các kênh công cộng.
  - **`scope: all` (Yêu cầu quyền Admin/Mod):** Xóa sạch toàn bộ Ký ức Sự kiện Server (`guild_memories`), Mạch tóm tắt chủ đề các kênh (`topic_summary`), và Khí sắc chung (`ambient_mood`).

• **🔒 `private` (Ký ức Cá nhân / Lịch sử chat riêng & Cảm xúc - Mặc định):**
  - **`scope: self` (Mặc định):** Xóa sạch lịch sử chat riêng tư, kỷ niệm cá nhân và reset điểm tình cảm (Trust, Attachment) của riêng bạn.
  - **`scope: all` (Yêu cầu quyền Admin/Mod):** Xóa sạch toàn bộ Ký ức Cá nhân và điểm cảm xúc của TẤT CẢ thành viên trong Server.

• **☢️ `nuke` (Quick-clear Toàn diện - Yêu cầu quyền Admin/Mod):**
  - Xóa **TOÀN BỘ 100%** Ký ức Cộng đồng + Ký ức Cá nhân của TẤT CẢ thành viên trong Server!
  - Đưa toàn bộ Server về trạng thái như vừa mới cài đặt bot.

---

### 🛡️ 2. Phân quyền & Điều kiện thực thi
| Lệnh Thực Thi | Quyền Hạn Yêu Cầu | Phạm Vi Hoạt Động |
| :--- | :--- | :--- |
| `c!clear` *(hoặc `/clear mode:private scope:self`)* | Thành viên bất kỳ | Server & Tin nhắn riêng (DM) |
| `c!clear community self` | Thành viên bất kỳ | Server |
| `c!clear community all` | **Administrator / Moderator** | Server |
| `c!clear private all` | **Administrator / Moderator** | Server |
| `c!clear nuke` | **Administrator / Moderator** | Server |

---

### 📝 3. Ví dụ Minh Họa
> `c!clear` *(Xóa ký ức cá nhân của riêng bạn)*
> `c!clear community self` *(Xóa ký ức cộng đồng của riêng bạn)*
> `c!clear community all` *(Admin xóa toàn bộ sự kiện/văn hóa cộng đồng của Server)*
> `c!clear nuke` *(Admin quét sạch toàn bộ ký ức của cả Server)*
