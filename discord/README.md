# Discord Microservice — Kuchiba Chisa

Microservice Discord cho chatbot AI **Kuchiba Chisa**, hoạt động độc lập khỏi core backend và giao tiếp qua REST API.

## 🏗️ Kiến trúc & Công nghệ
- **Kết nối Core RAG Backend:** REST API (`POST /api/v1/chat`, `POST /community/chat`, `POST /api/v1/chat/clear/{user_id}`)
- **Thư viện Discord:** `discord.js` v14 (ES Modules)
- **Database:** PostgreSQL (Lưu trữ guild settings, direct channels, user mapping)
- **Hệ thống Cảm xúc:** RESONA Emotion Engine 8 chiều (*Tin tưởng, Gắn bó, Ngại ngùng, Hiếu kỳ, Bình yên, Vui vẻ, Buồn bã, Khó chịu*) cùng Khí sắc Server (Ambient Resonance)
- **Tương tác:** Hỗ trợ song song cả **Slash Commands (`/`)** và **Prefix Commands (`c!`)** với 3 chế độ không gian kênh (`community`, `semi-private`, `private`)

## 📂 Cấu trúc Thư mục
```text
discord/
  .dockerignore
  .env.example
  Dockerfile
  package.json
  README.md
  scripts/
    register-commands.js    # Script deploy slash commands lên Discord API
  src/
    index.js                # Entry point
    app.js                  # Khởi tạo Discord client & kết nối DB
    assets/
      docs/                 # Tài liệu Markdown nhúng trong bot (/docs, /about, /help)
      img/                  # Banner & hình ảnh giao diện
    bot/
      client.js
      loadCommands.js       # Dynamic command loader
      loadEvents.js         # Event listeners loader
    commands/               # /ask, /clear, /setup, /docs, /about, /help
    database/
      pool.js               # PostgreSQL connection pool
      schema.sql            # Migration schema
    events/
      ready.js
      interactionCreate.js  # Xử lý slash commands & interactive buttons
      messageCreate.js      # Xử lý prefix commands & auto-chat channel
    repositories/
      discordUserRepository.js
      guildSettingsRepository.js
      interactionRepository.js
    services/
      coreRagClient.js      # HTTP client kết nối FastAPI Core
      rateLimiter.js
    utils/
      reply.js
```

## 🛠️ Danh sách Lệnh Hỗ trợ
| Slash Command | Prefix Command | Mô tả |
|---|---|---|
| `/ask <nội dung>` | `c!ask <nội dung>` | Trò chuyện, hỏi đáp lore hoặc tâm sự cùng Chisa |
| `/clear [mode] [scope]` | `c!clear [mode] [scope]` | Xóa bộ nhớ & làm mới ngữ cảnh (`community / private / nuke`, `self / all`) |
| `/setup [action] [mode]` | `c!setup [mode] ...` | Thiết lập 3 chế độ không gian kênh: `community`, `semi-private`, `private` (Admin/Mod) |
| `/docs` | `c!docs` | Xem tài liệu chi tiết về hệ thống cảm xúc RESONA 3.1 & Khí sắc Server |
| `/about` | `c!about` | Xem hồ sơ nhân vật, Forte và công nghệ AI Multi-Memory 3.0 tích hợp |
| `/help` | `c!help` | Bảng điều khiển hướng dẫn tương tác & danh sách lệnh |

## 🚀 Cài đặt & Khởi chạy Local
1. Sao chép file môi trường:
   ```bash
   cp .env.example .env
   ```
2. Cài đặt dependencies:
   ```bash
   npm install
   ```
3. Đăng ký Slash Commands với Discord:
   ```bash
   npm run register:commands
   ```
4. Khởi chạy Bot:
   ```bash
   npm start
   ```

## 🔐 Quyền Hạn Tối Thiểu (Bot Permissions)
- View Channels
- Send Messages & Send Messages in Threads
- Read Message History
- Embed Links & Attach Files
- Use Application Commands
- *Lưu ý:* Cần bật **Message Content Intent** trong [Discord Developer Portal](https://discord.com/developers/applications) để sử dụng chế độ prefix command (`c!`) và kênh chat trực tiếp `/setup`.
