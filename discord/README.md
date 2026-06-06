# Discord microservice

Microservice Discord cho Chisa, tách độc lập khỏi core RAG và giao tiếp với backend qua HTTP API.

## Chọn kiến trúc
- Kết nối tới core RAG: `HTTP API`
- Thư viện Discord: `discord.js`
- Database: `PostgreSQL` với `pg`
- Cách tương tác: `slash command /ask`, `slash command /clear`, và prefix `c!ask`, `c!clear`

## Cây thư mục đề xuất
```text
discord/
  .dockerignore
  .env.example
  Dockerfile
  package.json
  README.md
  scripts/
    register-commands.js
  src/
    index.js
    app.js
    config/
      env.js
      logger.js
      constants.js
    bot/
      client.js
      loadCommands.js
      loadEvents.js
    commands/
      ask.js
      clear.js
    events/
      ready.js
      interactionCreate.js
    database/
      pool.js
      schema.sql
    repositories/
      discordUserRepository.js
      interactionRepository.js
    services/
      coreRagClient.js
      rateLimiter.js
    utils/
      reply.js
```

## Luồng chạy
1. User gõ `/ask <message>` trong Discord.
2. Bot lấy hoặc tạo `core_user_id` nội bộ cho user Discord.
3. Bot lưu metadata hội thoại vào PostgreSQL.
4. Bot gọi `POST /api/v1/chat` của core RAG.
5. Bot nhận response và trả lời lại trong Discord.
6. Khi user chạy `/clear`, bot gọi endpoint clear memory của core RAG và dọn log local.

## Chạy local
1. Copy `.env.example` thành `.env`.
2. Cài dependencies:
   ```bash
   npm install
   ```
3. Đăng ký slash commands:
   ```bash
   npm run register:commands
   ```
4. Chạy bot:
   ```bash
   npm start
   ```

## Quyền tối thiểu
Bot chỉ cần:
- View Channel
- Send Messages
- Read Message History
- Use Application Commands

## Ghi chú
- Bot không gọi thẳng vào database của core RAG.
- `user_id` gửi sang core RAG là UUID riêng được bot quản lý để tương thích với `/clear/{user_id}`.
- Prefix mode cần bật `Message Content Intent` trong Discord Developer Portal.
