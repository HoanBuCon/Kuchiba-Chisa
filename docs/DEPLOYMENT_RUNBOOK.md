# Chisa — Deployment Runbook (controlled production, single VPS)

Phạm vi: một VPS Ubuntu 22.04/24.04, **4 vCPU / 8 GB RAM / 80 GB SSD**, chạy toàn bộ
stack bằng Docker Compose phía sau Caddy (HTTPS). Đối tượng: nhóm tester nhỏ có kiểm soát.

Mọi lệnh chạy từ thư mục repo trên VPS (ví dụ `/opt/chisa`) trừ khi ghi khác.
Các bước dưới đây đã được rehearsal trên stack sạch (xem
`reports/Controlled_Production_Hardening_Verification.md`).

---

## 0. Kiến trúc tóm tắt

| Service | Vai trò | Mạng | Port host |
|---|---|---|---|
| `web` (Caddy) | TLS, SPA, proxy `/api/*` → `app:8000`, security headers, chặn `/docs`, `/openapi.json`, `/static/*`, `/api/v1/visualizer*` | `chisa_edge` (IP cố định `172.28.0.10`) | 80, 443 |
| `app` | FastAPI (uvicorn, 2 worker) | `chisa_edge`, `chisa_data` | `127.0.0.1:8000` (chỉ loopback, cho monitor) |
| `worker` | Durable background worker | `chisa_edge`, `chisa_data` | — |
| `discord` | Discord bot | `chisa_edge`, `chisa_data` | — |
| `postgres`, `redis`, `qdrant` | Dữ liệu | `chisa_data` (internal) | — |
| `migrate` (profile `ops`) | `alembic upgrade head` một lần | `chisa_data` | — |

Volume bền vững: `postgres_data`, `qdrant_data`, `redis_data`, `uploads_data`
(ảnh memory), `model_cache` (FastEmbed), `caddy_data` (chứng chỉ TLS), `caddy_config`.

---

## 1. Chuẩn bị (một lần)

1. **DNS:** tạo bản ghi A (và AAAA nếu có IPv6) `chisa.<domain>` → IP VPS. Đợi DNS phân giải
   trước khi start Caddy (Let's Encrypt cần cổng 80/443 truy cập được từ Internet).
2. **SSH key:** đăng nhập bằng key cho user quản trị (`~/.ssh/authorized_keys` không rỗng).
3. **Hardening VPS** (UFW 22/80/443, SSH chỉ key, unattended-upgrades, swap 2 GB,
   log rotation Docker, thư mục backup/monitor):
   ```bash
   sudo ADMIN_USER=<user> bash scripts/ops/vps_bootstrap.sh
   ```
   Script từ chối tắt SSH password nếu chưa có authorized key.
4. **Docker Engine + Compose plugin** theo hướng dẫn chính thức của Docker
   (Compose ≥ 2.24).
5. **Clone repo** vào `/opt/chisa`, checkout **đúng tag/SHA release đã qua CI**.

> Lưu ý mạng: `chisa_edge` dùng subnet cố định `172.28.0.0/24` để API chỉ tin đúng
> địa chỉ của Caddy (`TRUSTED_PROXY_CIDRS=172.28.0.10/32`). Nếu VPS đã có mạng Docker
> khác chiếm `172.28.x`, `docker compose up` sẽ báo "Pool overlaps"; xóa mạng trùng
> hoặc đổi đồng thời subnet, `ipv4_address` của `web` và `TRUSTED_PROXY_CIDRS`.

---

## 2. Secrets và cấu hình

Không commit bất kỳ secret nào. Tất cả nằm trên VPS, quyền `600`, owner là user quản trị.

```bash
cd /opt/chisa
install -d -m 700 secrets
openssl rand -base64 32 | tr -d '\n' > secrets/postgres_password
openssl rand -base64 32 | tr -d '\n' > secrets/redis_password
chmod 600 secrets/*
cp .env.production.example .env
chmod 600 .env
```

Điền `.env` (mẫu và giải thích từng biến trong `.env.production.example`):

- `APP_ENV=production` (bắt buộc: production từ chối placeholder secret, ẩn `/docs`,
  fail-closed khi startup lỗi).
- `SECRET_KEY`, `JWT_SECRET`, `DISCORD_WORKLOAD_JWT_SECRET`: mỗi giá trị
  `openssl rand -base64 48`, **ba giá trị khác nhau**.
- `QDRANT_API_KEY`: `openssl rand -base64 32`.
- `POSTGRES_PASSWORD_FILE=./secrets/postgres_password`,
  `REDIS_PASSWORD_FILE=./secrets/redis_password`.
- `CORE_RAG_WORKLOAD_JWT_SECRET`: **bằng đúng** `DISCORD_WORKLOAD_JWT_SECRET` (bot ký
  workload token, Core xác minh). `DATABASE_URL` của bot và app được tính từ Docker
  secret trong lệnh khởi động service, không đặt trong `.env`.
- `CHISA_DOMAIN`, `CHISA_ACME_EMAIL`, `PUBLIC_APP_URL=https://<CHISA_DOMAIN>`.
- LLM key (`DEEPSEEK_API_KEY`…), reranker (`RERANKER_PROVIDER=jina`,
  `RERANKER_API_MODEL=jina-reranker-v3.5`, `JINA_API_KEY`).
- Discord: `DISCORD_TOKEN`, `DISCORD_CLIENT_ID`, `DISCORD_MODERATOR_ROLE_IDS`
  (danh sách **role ID**, không phải tên role; để trống = chỉ Administrator/ManageGuild).
  Bật *Message Content Intent* trong Discord Developer Portal.

### Google Sign-In (tùy chọn)

1. Google Cloud Console → *APIs & Services* → *Credentials* → *OAuth client ID*,
   loại **Web application**.
2. *Authorized redirect URI*: `https://<CHISA_DOMAIN>/api/v1/auth/google/callback`
   (phải khớp tuyệt đối với `GOOGLE_OAUTH_REDIRECT_URI`).
3. *OAuth consent screen*: scope `openid`, `email`, `profile`. Khi còn ở chế độ
   *Testing*, thêm email tester vào danh sách *Test users*.
4. Ghi `GOOGLE_OAUTH_CLIENT_ID`, `GOOGLE_OAUTH_CLIENT_SECRET`,
   `GOOGLE_OAUTH_REDIRECT_URI` **chỉ vào `.env` trên VPS**. Bỏ trống cả ba để tắt Google
   (UI tự ẩn nút).

App từ chối khởi động ở production nếu: secret là placeholder, `JWT_SECRET` trùng
`DISCORD_WORKLOAD_JWT_SECRET`, `AUTH_COOKIE_SECURE=false`, hoặc Google bật mà
`PUBLIC_APP_URL`/redirect URI không phải `https://`.

---

## 3. Lần deploy đầu tiên (stack sạch)

```bash
cd /opt/chisa
docker compose build
docker compose up -d postgres redis qdrant
docker compose --profile ops run --rm migrate          # in ra "<revision> (head)"
docker compose run --rm --no-deps app python -m app.ops.warm_embedding_cache
```

`warm_embedding_cache` tải model embedding **một lần** vào volume `model_cache`. Không bỏ
bước này: nếu `app` (2 worker) và `worker` cùng tải model trên cache trống, chúng ghi đè
lẫn nhau và để lại snapshot hỏng (lỗi `ONNXRuntimeError NO_SUCHFILE` khi embed; đã gặp
trong rehearsal). Nếu đã lỡ: dừng `app worker`, xóa volume `model_cache`, chạy lại bước này.

### Qdrant: alias runtime

Production chỉ khởi động khi đủ 6 alias `*__active`.

1. **Lore (`character_lore`, `world_lore`, `story_lore`)**: phải đến từ **corpus release
   đã được duyệt**. Chọn một trong hai:
   - *Khuyến nghị:* restore Qdrant snapshot lấy từ môi trường đang giữ corpus đã duyệt
     (mục 6.3). Snapshot chứa cả alias.
   - Hoặc chạy governed ingestion + publish theo `reports/ING02_*` và
     `reports/ING03_*`
     (`python chisa_cli.py ingest --source-id <uuid> --staging-collection <logical__version>`,
     sau đó promote alias). Không dùng `scripts/init_qdrant.py` (legacy, không tạo alias).
2. **Bộ nhớ riêng (`memories`, `guild_memories`, `image_memories`)**: trên VPS mới là
   collection rỗng:
   ```bash
   scripts/ops/app_python.sh -m app.ops.bootstrap_private_collections
   ```
   Idempotent: alias đã tồn tại thì bỏ qua. Script in trạng thái cả 6 alias; ba alias lore
   báo `NOT READY` cho tới khi bước 1 xong.

> `scripts/ops/app_python.sh` chạy lệnh Python một lần trong image `app` với cùng
> `DATABASE_URL`/`REDIS_PASSWORD` lấy từ Docker secrets như service `app`.
> `docker compose run app python ...` trần sẽ thiếu hai biến này và Settings production
> từ chối nạp.

### Khởi động

```bash
docker compose up -d app worker web discord
docker compose ps
curl -fsS https://<CHISA_DOMAIN>/ready     # {"status":"ready",...} 
```

---

## 4. Kiểm tra sau deploy (smoke test)

```bash
D=https://<CHISA_DOMAIN>
curl -sI $D/ | grep -iE 'strict-transport|content-security|x-frame|x-content-type'
for p in /docs /openapi.json /static/x /api/v1/visualizer; do curl -s -o /dev/null -w "$p %{http_code}\n" $D$p; done   # tất cả 404
curl -s -o /dev/null -w "%{http_code} %{redirect_url}\n" http://<CHISA_DOMAIN>/                                       # 308 → https
```

Trên trình duyệt: mở trang, gửi một tin nhắn (thấy chữ chạy dần, tức SSE không bị buffer),
tạo tài khoản, đăng xuất, đăng nhập lại, thử "Đăng nhập Google" nếu đã bật. Trên Discord:
mention bot trong kênh được cấu hình, thử `/clear` với một tài khoản không phải moderator
(phải bị từ chối).

---

## 5. Deploy bản mới (cập nhật)

```bash
cd /opt/chisa
scripts/ops/backup.sh                         # luôn backup trước
git fetch --tags && git checkout <tag-mới>    # chỉ tag đã qua CI
docker compose build
docker compose --profile ops run --rm migrate
docker compose up -d app worker web discord
curl -fsS https://<CHISA_DOMAIN>/ready
```

Migration chạy **trước** khi container mới nhận traffic. Nếu `/ready` không về 200 trong
vài phút, xem mục 8 (rollback).

---

## 6. Backup và restore

### 6.1 Backup hằng ngày

```bash
crontab -e
# 03:30 UTC mỗi ngày
30 3 * * * cd /opt/chisa && BACKUP_RCLONE_REMOTE=<crypt-remote>:chisa scripts/ops/backup.sh >> /var/log/chisa-backup.log 2>&1
```

Mỗi bản backup (`/var/backups/chisa/<STAMP>/`): `postgres.dump` (pg_dump `-Fc`),
`qdrant.snapshot` (full storage snapshot, gồm alias), `uploads.tar.gz`, `SHA256SUMS`.
Giữ 7 ngày local (`BACKUP_KEEP_DAYS`). Offsite: dùng remote rclone kiểu **crypt** để dữ
liệu được mã hóa khi rời VPS.

### 6.2 Restore drill (không phá dữ liệu, chạy ít nhất 1 lần trước khi mời tester, sau đó hằng tháng)

```bash
scripts/ops/restore_drill.sh /var/backups/chisa/<STAMP>
```

Drill kiểm checksum, restore Postgres vào DB tạm `chisa_restore_drill`, so sánh
revision/số user/account/message với production, kiểm archive uploads và snapshot,
rồi xóa DB tạm. Bất kỳ bước nào lỗi thì drill dừng với exit code ≠ 0.

### 6.3 Restore thật (sự cố mất dữ liệu)

```bash
docker compose stop app worker discord web
# PostgreSQL
docker compose exec -T postgres dropdb -U chisa chisa_db
docker compose exec -T postgres createdb -U chisa chisa_db
docker compose exec -T postgres pg_restore -U chisa -d chisa_db --no-owner --exit-on-error < /var/backups/chisa/<STAMP>/postgres.dump
# Qdrant (full snapshot, gồm alias)
docker compose stop qdrant
docker compose run --rm --no-deps -v /var/backups/chisa/<STAMP>/qdrant.snapshot:/restore/qdrant.snapshot:ro \
  qdrant ./qdrant --storage-snapshot /restore/qdrant.snapshot --force-snapshot   # Ctrl+C sau khi log báo đã sẵn sàng
docker compose up -d qdrant
# Uploads
docker compose run --rm --no-deps -v /var/backups/chisa/<STAMP>:/restore:ro app sh -c 'tar -C /app/app/static -xzf /restore/uploads.tar.gz'
docker compose --profile ops run --rm migrate
docker compose up -d app worker web discord
```

Restore snapshot Qdrant bằng `--storage-snapshot` đã được kiểm trong rehearsal: đủ 6 alias.

---

## 7. Monitoring

```bash
crontab -e
*/5 * * * * cd /opt/chisa && DISCORD_ALERT_WEBHOOK_URL=<webhook kênh alert riêng> scripts/ops/monitor.sh >> /var/log/chisa-monitor.log 2>&1
```

`monitor.sh` kiểm tra trạng thái/health/số lần restart của container, `/ready`, disk
(≥ 80%), RAM khả dụng (< 10%) và swap (> 1 GB). Script chỉ gửi webhook khi trạng thái
thay đổi (không spam). Thêm một uptime monitor bên ngoài (gói miễn phí) trỏ vào
`https://<CHISA_DOMAIN>/ready`.

Điều tra nhanh:

```bash
docker compose ps
docker compose logs --since 30m app | tail -200
docker stats --no-stream
```

Log đã được redaction (không có nội dung hội thoại, email, token). Docker xoay vòng log
ở 10 MB × 5 file mỗi container.

---

## 8. Rollback

1. **Chỉ code (migration không đổi):**
   ```bash
   git checkout <tag-trước>
   docker compose build && docker compose up -d app worker web discord
   ```
2. **Có migration mới:** ưu tiên *roll forward* (sửa lỗi, deploy tag mới). Nếu bắt buộc
   phải lùi schema: dừng `app worker discord`, chạy
   `scripts/ops/app_python.sh -m alembic downgrade <revision-trước>` (chỉ khi migration
   đó có downgrade đã được test), checkout tag trước, build, up. Migration tài khoản
   `1a7c3e5f9b20` có downgrade, nhưng downgrade **xóa toàn bộ tài khoản và session**.
3. **Dữ liệu hỏng:** restore theo mục 6.3 từ bản backup gần nhất trước sự cố.

Sau rollback luôn chạy smoke test mục 4.

---

## 9. Yêu cầu xóa tài khoản (tester)

Theo `docs/PRIVACY_NOTICE_TESTERS.md`: tester đăng nhập và gõ `/clear` (xóa hội thoại,
ký ức, ảnh, cache của subject = account ID), sau đó người vận hành xóa tài khoản. Xóa
`accounts` sẽ cascade sang `account_identities` (liên kết Google) và `auth_sessions`:

```bash
docker compose exec -T postgres psql -U chisa -d chisa_db -c \
  "DELETE FROM accounts WHERE email = lower('<email-tester>') RETURNING id;"
```

Nếu tester không thể tự `/clear`, dùng `id` trả về để chạy erasure cho subject đó trước khi
xóa (cùng đường xóa với endpoint `/api/v1/chat/clear/{id}`). Bản sao lưu cũ hết hạn sau 7 ngày.

---

## 10. Ngân sách tài nguyên (4 vCPU / 8 GB)

Giới hạn trong `docker-compose.yml` cộng lại ≤ 6.6 GB, để lại ≥ 1.4 GB cho OS/page cache,
cộng swap 2 GB làm đệm. Khi rehearsal ở trạng thái nghỉ (sau warm-up): app ≈ 365 MiB,
worker ≈ 155 MiB, Postgres ≈ 70 MiB, Qdrant ≈ 40 MiB (corpus rỗng), Caddy ≈ 12 MiB.
Model embedding nạp lười theo từng process (~0.5–0.7 GB mỗi process khi dùng), nên khi
có tải thật phải theo dõi `docker stats` trong tuần đầu.
