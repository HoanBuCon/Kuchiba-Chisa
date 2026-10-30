# Controlled-Production Hardening — Verification Report

- Ngày: 2026-10-05
- Base: `HBC` @ `12b6073`. Nhánh: `hardening/controlled-production-accounts` (1 commit).
- Đầu vào: `reports/Production_Readiness_Assessment.md` (🟡 READY AFTER BLOCKER FIXES),
  `reports/SRS_Kuchiba_Chisa.md`.
- Không thay đổi: RAG retrieval, embedding, reranker, LLM gateway, personality, system
  prompt, relationship lore, protected prompts, golden set, SRS, acceptance criteria,
  benchmark artifacts.

## 1. Kết quả gate (trên cây mã cuối)

| Gate | Lệnh | Kết quả |
|---|---|---|
| Isolated CI (Postgres 16, Redis 7, Qdrant 1.12.4 thật) | `docker compose -f docker-compose.test.yml up --build --exit-code-from test` | **EXIT=0**: `alembic upgrade head` + `alembic check` OK, `mypy app` (312 file) không lỗi, **689 passed** (`tests/unit` + `tests/integration`, 0 skip) |
| Ruff changed-lines | `python scripts/ruff_changed_lines.py --base 12b6073` | PASS |
| Ruff debt ratchet | `python scripts/ruff_debt_ratchet.py` | PASS (2810 ≤ baseline 2914) |
| Discord | `cd discord && npm ci && npm test` | 14/14 PASS |
| Frontend | `cd frontend && npm ci && npm run lint && npm run build` | PASS |
| Compose | `docker compose --env-file .env.production.example config --quiet` | PASS |
| Caddy | `caddy validate` + `caddy adapt` (kiểm thứ tự route) | PASS |

Các test security mới trước đây chỉ chạy với stub (grpc/fastembed/qdrant_client/bcrypt).
Lần này chúng chạy với thư viện thật trong venv (`pip check` sạch) và trong image CI;
`tests/integration/test_account_repository.py` chạy trên Postgres thật.

## 2. Rehearsal compose + Caddy (stack sạch, `APP_ENV=production`)

Project compose riêng (`chisa-rehearsal`), secrets ngẫu nhiên, `CHISA_DOMAIN=localhost`
(Caddy dùng CA nội bộ), LLM key giả. Trình tự đúng như `docs/DEPLOYMENT_RUNBOOK.md`:
build → `migrate` (`1a7c3e5f9b20 (head)`) → `warm_embedding_cache` →
`app_python.sh -m app.ops.bootstrap_private_collections` (idempotent ở lần chạy 2) →
lore stub *chỉ dùng cho rehearsal* → `up` → `/ready` 200.

| Kiểm tra | Kết quả |
|---|---|
| Security headers trên `/` và `/api/*` | HSTS, CSP, `X-Frame-Options: DENY`, `nosniff`, Referrer-Policy, Permissions-Policy; không có header `Server` |
| `/docs`, `/docs/*`, `/redoc`, `/openapi.json`, `/static/uploads/*`, `/api/v1/visualizer`, `/api/v1/visualizer/traces` | 404 |
| `/health`, `/ready` qua Caddy | 200 JSON (`postgresql/redis/qdrant/llm_config: true`) |
| `http://` → `https://` | 308 |
| SPA deep link | 200 `text/html` (try_files) |
| SSE `/api/v1/chat/stream` qua Caddy | `text/event-stream`, chunked; event đầu tới sau 0.02–0.06 s, kể cả khi client gửi `Accept-Encoding: gzip, br, zstd` (Caddy không nén/buffer SSE) |
| Đăng ký không có `X-Chisa-Client` | 403 |
| Đăng ký | 201, `Set-Cookie: chisa_refresh=…; HttpOnly; Secure; SameSite=lax; Path=/api/v1/auth; Max-Age=604800`, `Cache-Control: no-store` |
| Đăng ký trùng email | 409 |
| `/auth/me` bằng access token tài khoản | `authentication: "account"`, subject = account UUID |
| Refresh → rotation | 200; dùng lại cookie cũ → 401; thiếu header CSRF → 403 |
| Logout → refresh bằng cookie đã thu hồi | 204 → 401 |
| Login sai mật khẩu / email không tồn tại | 401, cùng thông điệp |
| Anonymous-session bằng token tài khoản | 403 |
| Google start khi chưa cấu hình | 503; `capabilities.google=false` |
| Brute-force login (13 request/1 email) | 5 × 401 rồi 429 |
| Log app/Caddy sau toàn bộ luồng | 0 dòng chứa email, mật khẩu hay cookie |
| `backup.sh` | `postgres.dump`, `qdrant.snapshot` (991 KB), `uploads.tar.gz`, `SHA256SUMS` |
| `restore_drill.sh` | checksum OK; revision/users/accounts/messages khớp production; exit ≠ 0 khi archive hỏng |
| Restore Qdrant full snapshot (`--storage-snapshot`) | Đủ 6 alias `*__active` |
| RAM khi nghỉ | app 364 MiB, worker 154 MiB, Postgres 71 MiB, Qdrant 41 MiB, Caddy 12 MiB |

## 3. Lỗi phát hiện và sửa trong đợt verification này

| # | Mức | Lỗi | Sửa | Bằng chứng |
|---|---|---|---|---|
| V-1 | 🔴 | **Caddy bỏ qua chặn visualizer và proxy health.** `respond @blocked` và `reverse_proxy @health` ở cấp site được Caddy xếp **sau** nhóm `handle`; khối SPA catch-all luôn khớp nên chúng không bao giờ chạy: `/api/v1/visualizer*` được proxy tới app, còn `/health` trả index.html. | Chỉ dùng các khối `handle` loại trừ nhau (`handle @blocked`, `handle @health`, `handle /api/*`, `handle`). | `caddy adapt` trước/sau; rehearsal 404/200; test `test_caddyfile_routes_only_inside_handle_blocks` |
| V-2 | 🔴 | **Redis production không khởi động được** (lỗi có sẵn ở base): `printf '…\\n…'` sinh file ACL một dòng chứa `\n` dạng chữ → `Aborting Redis startup because of ACL errors`. | `\n` thật. | Rehearsal: Redis healthy, ACL 2 dòng; `test_redis_acl_file_is_written_with_real_newlines` |
| V-3 | 🔴 | **Ảnh người dùng ở máy dev bị đóng vào production image** (`COPY app/` chứa `app/static/uploads`), rồi được seed vào volume uploads. | `.dockerignore`: `app/static/uploads`, `.env`, `.env.*` (trừ template), `secrets`. | Image mới: 0 file upload, không có `.env`; `test_images_never_include_user_uploads_or_env_files` |
| V-4 | 🟠 | **Ops tool không chạy được ở production:** `docker compose exec/run app python -m …` không có `REDIS_PASSWORD`/`DATABASE_URL` (chỉ được export trong lệnh service) → Settings từ chối nạp; `backup.sh` ra `qdrant.snapshot` 0 byte. | `qdrant_snapshot` và `warm_embedding_cache` chỉ đọc đúng biến môi trường cần; thêm `scripts/ops/app_python.sh` cho tool cần Settings. | Backup/drill PASS; `test_ops_modules_do_not_load_full_application_settings` |
| V-5 | 🟠 | **Race khi tải model embedding lần đầu:** 2 uvicorn worker + worker cùng tải vào volume `model_cache` trống → snapshot thiếu `model.onnx` → `ONNXRuntimeError NO_SUCHFILE`. | Bước deploy `python -m app.ops.warm_embedding_cache` (một process) trước khi start. | Rehearsal: lỗi tái hiện được; sau warm-up 0 lỗi, model nạp thành công |
| V-6 | 🟠 | **Stack sạch không có đường bootstrap alias Qdrant được hỗ trợ** (R-12): production fail-closed khi thiếu alias. | `app.ops.bootstrap_private_collections` (chỉ 3 collection bộ nhớ riêng, idempotent). Lore phải đến từ corpus release đã duyệt (runbook). | Rehearsal stack sạch: `/ready` 200 |
| V-7 | 🟠 | **Refresh song song làm người dùng bị đăng xuất:** refresh token xoay vòng mỗi lần dùng; hai refresh đồng thời (React StrictMode, nhiều tab, token hết hạn đúng lúc gửi tin) → một request 401 và **xóa cookie**. | Frontend single-flight + `navigator.locks` giữa các tab. | Code review; lint/build PASS |
| V-8 | 🟡 | Guild erasure xóa **mọi** mapping của guild sau khi xong, kể cả member được map trong lúc chạy (mất retry handle). | `DELETE … AND core_user_id = ANY($2::uuid[])` chỉ với các user đã erase. | Test cập nhật, 14/14 PASS |
| V-9 | 🟡 | `restore_drill.sh` in "OK" dù kiểm archive thất bại (`cmd && echo` không kích hoạt `set -e`). | Lệnh đơn để `set -e` dừng drill. | exit 2 với archive hỏng, exit 0 khi hợp lệ |
| V-10 | 🟡 | Gate CI đỏ: test pin alembic head cũ (`9c0e1f2a3b4d`) và test đọc file không có trong test image; `npm test` lỗi trên Node 22 (`node --test test/`). | Pin `1a7c3e5f9b20` (hệ quả trực tiếp của migration accounts); bỏ qua file vắng mặt nhưng bắt buộc entrypoint Python; `node --test`. | CI EXIT=0; 14/14 |
| V-11 | 🟡 | 3 dòng vượt 100 ký tự trong các dòng log đã sửa (gate ruff changed-lines). | Xuống dòng. | Ruff PASS |

## 4. Đối chiếu blocker

| ID | Trạng thái | Ghi chú |
|---|---|---|
| B-1 SSRF | ✅ | `SafePageFetcher`: validate từng hop, pin IP + SNI, redirect thủ công ≤ 3, chỉ text, đọc stream ≤ 1 MB. 196 dòng test với lib thật. |
| B-2 Log | ✅ | Redaction processor luôn bật ngoài dev; traceback không có locals; không còn `backend.log` vô hạn; Docker rotation 10 MB × 5. Rehearsal: 0 dòng lộ dữ liệu. |
| B-3 Discord | ✅ | Quyền chỉ từ Administrator/ManageGuild hoặc allowlist role ID; mapping chỉ xóa khi mọi bước erasure hoàn tất (V-8 siết thêm). |
| B-4 HTTPS | ✅ (sau V-1) | Caddy TLS, headers, chặn bề mặt nội bộ, SSE flush, body 60 MB. |
| R-1/R-4/R-5/R-6/R-7/R-8 | ✅ cấu hình | `.env.production.example` + compose; validator production fail-closed với placeholder. |
| R-2 uploads volume | ✅ | + V-3. |
| R-10 Privacy notice | ✅ | `docs/PRIVACY_NOTICE_TESTERS.md`, `frontend/public/privacy.html`, link trong UI. |
| R-11 Backup/restore | ✅ rehearsal | Cần chạy lại trên VPS thật + offsite. |
| R-12 Rehearsal stack sạch | ✅ (trừ corpus) | Corpus lore thật chưa được publish trong rehearsal. |
| R-13 Đúng SHA | ⏳ | CI phải chạy lại trên commit/tag cuối trước khi deploy. |
| R-9 PII tới provider ở bước trung gian | ⚠️ công bố | Không đổi pipeline (ngoài phạm vi); privacy notice nêu rõ. |
| R-14 Ghi P0 vào SRS | ⏳ | Không sửa SRS trong đợt này (ràng buộc). |

## 5. Rủi ro còn lại

1. **Corpus lore chưa được rehearsal**: rehearsal dùng collection lore rỗng; chất lượng
   trả lời và `/ready` trên VPS phụ thuộc vào việc restore snapshot hoặc publish corpus đã
   duyệt. Phải làm và kiểm lại trước khi mời tester.
2. **Google OIDC chưa chạy với Google thật**: chỉ có unit test với JWKS/ID token giả. Phải
   thử login + link trên domain thật (consent screen ở chế độ Testing).
3. **Access token tài khoản sống tới 15 phút sau logout** (không kiểm `sid` mỗi request).
   Chấp nhận được cho beta; refresh bị thu hồi ngay.
4. **Không phát hiện reuse của refresh token** (không thu hồi cả "họ" phiên khi cookie cũ
   bị dùng lại); token cũ chỉ bị từ chối.
5. **Chưa có self-service xóa tài khoản**; quy trình thủ công trong runbook §9.
6. **RAM dưới tải thật chưa đo**: model embedding nạp theo từng process (2 API worker +
   worker). Theo dõi `docker stats` tuần đầu.
7. **Subnet cố định `172.28.0.0/24`** có thể trùng mạng Docker có sẵn trên VPS (đã gặp ở máy
   rehearsal); runbook nêu cách xử lý.
8. **UI chưa được duyệt bằng trình duyệt qua Caddy** (cert CA nội bộ); mới kiểm bằng
   build/lint và luồng API E2E. Smoke test trình duyệt trên domain thật là bắt buộc.
9. Thư mục `frontend/public/` có nhiều ảnh GIF/JPG được phục vụ công khai cho mọi tester;
   nên rà nội dung trước khi mời người ngoài.
10. Chưa có job purge tự động cho hội thoại (đã công bố: lưu trong thời gian beta, xóa thủ công).

## 6. Kết luận

**READY FOR DEPLOY REHEARSAL** trên VPS thật theo `docs/DEPLOYMENT_RUNBOOK.md`. Đây
**không** phải kết luận production-ready: còn phải restore/publish corpus, chạy Google
OIDC thật, chạy backup/restore drill trên VPS, chạy CI trên SHA release, và smoke test
trình duyệt trước khi mời tester.
