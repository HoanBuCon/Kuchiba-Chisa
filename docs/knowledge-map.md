# Bản đồ tri thức hệ thống Kuchiba Chisa

Tài liệu này giúp người mới, hoặc một phiên AI khác, hiểu nhanh và đúng toàn bộ hệ thống trước khi sửa code. Mọi khẳng định ở đây đã được đối chiếu với code trên `HBC` ngày 14/11/2026; chỗ nào là mục tiêu của SRS mà code chưa làm thì ghi rõ. Khi tài liệu này mâu thuẫn với SRS, SRS thắng (STD-GOV-002); khi mâu thuẫn với code, hãy tin code rồi sửa tài liệu.

## 1. Đọc theo thứ tự này

| # | Tài liệu | Vì sao |
|---|---|---|
| 1 | `.claude/CLAUDE.md` → [`CONTRIBUTING.md`](CONTRIBUTING.md) | Quy tắc bắt buộc cho người và agent: lớp, nội dung bảo vệ, quy trình Git |
| 2 | Tài liệu này | Bức tranh toàn hệ thống và trạng thái thật |
| 3 | [SRS v2](SRS_Chisa_v2_Advanced_Agentic_RAG.md) | Nguồn sự thật. Đọc mục 2, 3, 10, 14 trước; mục 4 tra theo mã yêu cầu |
| 4 | [`r2-plan.md`](r2-plan.md) | Trạng thái R2, số đo, cổng thoát |
| 5 | [`handover/`](handover/README.md) | Báo cáo bàn giao từng tính năng: quyết định, kiểm tra, việc còn lại |
| 6 | [`adr/`](adr/) | 5 quyết định kiến trúc đã chấp nhận |
| 7 | [`design/target-architecture.md`](design/target-architecture.md) | Kiến trúc mục tiêu và lựa chọn công nghệ; thứ tự việc sẽ làm |

## 2. Hệ thống là gì

Chisa là bạn trò chuyện nhập vai nhân vật Kuchiba Chisa (game Wuthering Waves), có cảm xúc 8 chiều (RESONA) và trí nhớ, đồng thời trả lời lore có trích dẫn từ Fandom wiki. Kênh: web SPA và bot Discord. Một chủ dự án kiêm Admin duy nhất (CON-004). Mục tiêu triển khai là một VPS 4 vCPU / 8 GB; **hiện chưa có VPS**.

Quyết định gốc của chủ dự án (SRS, "Quyết định đã chốt"):

- **Hai chế độ:** Advanced RAG (mặc định, ai cũng dùng) và Agentic RAG (chỉ Chía-con và Admin). Mỗi lượt chạy đúng một chế độ.
- **Bốn lớp người dùng:** khách vãng lai, thành viên, Chía-con (vai trò do Admin cấp theo ID tài khoản), Admin (MFA).
- **Dữ liệu trước v2 đã xoá** ngày 31/10/2026; v2 khởi tạo sạch. Fandom wiki là nguồn tri thức duy nhất.

## 3. Trạng thái hiện tại

| Hạng mục | Trạng thái |
|---|---|
| Người dùng đang chạy trên | **v1**: `/api/v1/chat`, `/api/v1/chat/stream`, `/api/v1/community/chat` |
| v2 | Code xong phần lớn R2, **tắt sau cờ**: `CHAT_V2_ENABLED` (API), `VITE_CHAT_V2` (web), `CORE_RAG_CHAT_V2` (bot) |
| Lộ trình | R0, R1 xong; R2 chưa qua cổng thoát; R3–R6 chưa bắt đầu |
| Cổng thoát R2 | Xem [`r2-plan.md`](r2-plan.md): QUAL-001 và QUAL-004 chưa đạt; persona v2 đang được đo |
| Corpus | `2026.11.03-4` đã qua gate; `2026.11.04-1` (sửa trường lồng tiếng) mới ở staging |
| Nợ kỹ thuật đã ghi | PERF-003 (TTFT) chờ VPS; xem mục 17 |

## 4. Kiến trúc thực tế so với mục tiêu

```
              Web SPA (React/Vite)           Discord bot (Node, discord.js)
                    │  web JWT                       │  workload JWT (HS256, 120 s)
                    └───────────────┬────────────────┘
                                    ▼
   Caddy ──► FastAPI app  (middleware: RequestBodyLimit · RateLimit · Observability)
               │
               ├─ /api/v1  ── ChatPipeline 12 stage (v1, đang phục vụ người dùng)
               │                 + auth, community, admin ingestion
               └─ /api/v2  ── AdvancedTurnService (v2, sau cờ)
                                ├─ triage: lane_router (tất định)
                                ├─ làn companion ─► GroundedComposer.compose_companion
                                └─ làn advanced ─► AdvancedRetrieval ─► Composer + grounding
               │
   ┌───────────┼──────────────┬──────────────┬───────────────────┐
   ▼           ▼              ▼              ▼                   ▼
Postgres    Qdrant 1.20    Redis          Inference svc       LLM Gateway
(dữ liệu,   (lore, memory) (rate limit,   (embed e5-small,    (DeepSeek; Groq,
 job bền)                   cache, quota)  ADR-0004)           Gemini dự phòng)
   ▲
   └── worker (hàng đợi bền BE-01 trên bảng durable_background_jobs)
```

**Khác biệt quan trọng giữa SRS và code** (đừng giả định SRS đã được hiện thực):

| SRS mô tả | Code hiện tại |
|---|---|
| LangGraph cho làn Agentic (ADR-0005; bộ điều phối và Advanced là Python thuần) | Chưa có dependency LangGraph; làm ở R4 |
| Sự kiện qua **Redis Streams**, nối lại SSE được | SSE trả thẳng từ route; chưa nối lại được (CH-001 chưa đủ) |
| Outbox, job memory/summary/reflection cho v2 | Worker chỉ có job của v1; v2 chưa có job nào |
| Agentic subgraph, evidence ledger, interrupt | Chưa có (R4); mọi lượt bị ép về Advanced |
| RBAC 4 vai trò, Discord OAuth, Admin MFA | Chưa có (R3); hiện có tài khoản email/Google và phiên ẩn danh |
| Celery | Không dùng; hàng đợi bền tự viết |

## 5. Bố cục mã nguồn và quy tắc lớp

Quy tắc lớp (SRS 3.5.3, import-linter kiểm trong CI): `domain` không import lớp nào; `application` chỉ import `domain`; chỉ composition root (`app/application/dependencies.py`, `app/main.py`) import `infrastructure`.

| Thư mục | Trách nhiệm |
|---|---|
| `app/main.py` | Tạo FastAPI, gắn middleware và router |
| `app/application/dependencies.py` | Composition root: dựng mọi service, gồm runtime v1 (`ChatPipeline`) và v2 (`_build_chat_turn_runtime`) |
| `app/application/chat_turns.py` | Một lượt chat v2: chế độ, guard, triage, truy hồi, Composer, guard an toàn, lưu, sự kiện |
| `app/domain/services/knowledge/` | v2: `lore_search`, `advanced_retrieval`, `question_router`, `structured_tools`, `composer`, `cross_language_claims`, `lane_router` |
| `app/domain/services/chat_pipeline/` | v1: 12 stage (khởi tạo, intent, cache, tool routing, RAG, dựng context, che PII, gọi LLM, cảm xúc, lưu, cập nhật cache, job nền) |
| `app/domain/services/guardrails/` | Injection guard, che PII, claim/citation guard, lắp câu trả lời có căn cứ, guard ranh giới an toàn |
| `app/domain/services/` (gốc) | `context_builder.py`, `persona_loader.py` (**bảo vệ**), `persona_v2.py`, `chisa_voice.py`, `emotion_engine.py`, `state_manager.py`, `core_memory.py` |
| `app/domain/ingestion/` | Logic thuần của ingestion: chunk, khử trùng, entity linking, gate phát hành, báo cáo |
| `app/application/ingestion/` | Các stage ingestion và vòng đời phát hành corpus |
| `app/infrastructure/` | Postgres (models, repositories), Qdrant, Redis, LLM adapter, inference client, bảo mật, observability, ingestion I/O |
| `app/interface/` | Route API, middleware, CLI `wiki_sync`, service inference |
| `evals/` | Bộ đánh giá: golden, judge căn cứ, persona, retrieval gate |
| `frontend/`, `discord/` | Web React và bot Node |
| `deploy/` | Caddy, OTEL collector, alert, SLO, dashboard |

## 6. Một lượt chat v2 đi như thế nào

`POST /api/v2/chat/turns` (body: `message`, `turn_id`, `thread_id?`, `mode_override?`) → `app/interface/api/routes/chat_v2.py`:

1. **Ingress:** `require_scope("chat:write")`, `admit_chat` (quota theo người và theo IP cho khách), `RateLimitMiddleware` (phủ cả `/api/v2`). Bot không gửi thread id: route suy ra một thread cố định cho mỗi người mỗi kênh (`channel_thread_id`, uuid5).
2. **Idempotent:** cùng `turn_id` trong thread thì phát lại kết quả đã lưu, không gọi LLM lần nữa (CH-004). Bot suy `turn_id` từ id tin nhắn Discord.
3. **Chế độ:** `resolve_mode` luôn ra Advanced vì chưa có Agentic.
4. **Che PII** trên tin nhắn trước mọi provider; **injection guard**: nếu chặn thì trả `INPUT_BLOCKED`.
5. **Triage** (`lane_router.choose_lane`, tất định): trò chuyện rõ ràng → làn companion; còn lại → làn advanced. Sự kiện `turn.started` báo làn.
6. **Làn companion:** lịch sử thread + trí nhớ (nếu có consent) → `CompanionContextBuilder` (persona v2 + hồ sơ Chisa) → LLM.
7. **Làn advanced:** `AdvancedRetrieval.retrieve`:
   - dịch câu hỏi sang tiếng Anh (LLM, có cache Redis) → entity linking → truy hồi lai dense + BM25 + kênh thực thể, gộp bằng RRF có trọng số phía Qdrant → rerank Jina top 15, fallback MiniLM local → ngưỡng abstain;
   - `QuestionRouter` (tất định): liệt kê quest hay Resonator từ kho có cấu trúc; câu hỏi nêu chapter không có trong corpus thì abstain;
   - thiếu bằng chứng thì mở rộng một lần sang thoại (ADV-007).
8. **Composer:** danh sách do server trình bày (không gọi LLM); còn lại LLM trả `{decision, claims[], sentiment}` qua `GroundedContextBuilder`. Mỗi claim phải trích nguyên văn; `CrossLanguageClaimCheck` xét tên, số, phủ định rồi độ tương đồng ≥ 0,80; claim không qua được thì hiện trích dẫn tiếng Anh trong khung giọng Chisa.
9. **Guard ranh giới an toàn** (`safety_boundaries.py`): lời tình dục rõ ràng → câu từ chối; dấu hiệu tự hại mà câu trả lời chưa chỉ tới người giúp → nối lời nhắn hỗ trợ.
10. **Lưu** `thread_turns` (citation snapshot, số lời gọi LLM, làn) → **RESONA** cập nhật cảm xúc đúng một lần cho lượt đã lưu → stream `token` theo câu → `turn.completed` (`response`, `citations`, `emotions`, `emotion_caption`).

Ngân sách: tối đa **2 lời gọi LLM** mỗi lượt (dịch + Composer), hạn 30 giây.

## 7. Tri thức và ingestion

Nguồn duy nhất: Fandom wiki (ADR-0002). Lệnh: `python -m app.interface.cli.wiki_sync <plan|sync|clean|assemble|embed|load|structured|images|report|gate|status>`.

```
Fandom API ─► bronze (data/ingestion/bronze/<page_id>/, theo revid)
          ─► silver (cleaner silver-14, app/config/ingestion/cleaning.yaml)
          ─► gold (data/ingestion/gold/<version>/: chunks, knowledge, manifest)
          ─► vectors (cache theo nội dung; chỉ embed chunk mới)
          ─► Qdrant staging: lore_canon__<version>, lore_dialogue__<version>
          ─► gate (data gate + retrieval gate) ─► report (Corpus Explorer)
structured: infobox của toàn wiki ─► Postgres kb_entities, kb_aliases, kb_quests, kb_glossary, kb_location_edges
```

- Corpus có version kiểu `2026.11.04-1`. Runtime v2 đọc version từ `KNOWLEDGE_CORPUS_VERSION`.
- Tier A khoảng 1.054 trang, 9.872 chunk, 8.049 thực thể (phần lớn chỉ có dữ liệu cấu trúc).
- Gate cấu hình ở `app/config/ingestion/gates.yaml`; ngoại lệ an toàn cần chủ dự án duyệt.
- Embedding: `intfloat/multilingual-e5-small` fp32 qua inference service (`INFERENCE_URL`, cổng 8090).

## 8. LLM

- Mọi lời gọi qua `LLMGateway` (`app/application/llm_gateway.py`, STD-AI-001): retry, circuit breaker, bulkhead, fallback, ngân sách theo lượt, phân loại lỗi `LLMFailureClass` (gồm `billing` khi provider hết tiền).
- Adapter: `deepseek.py` (chính), `groq.py`, `gemini.py`. Chọn bằng `LLM_PROVIDER`, `LLM_FALLBACK_PROVIDERS`.
- Đầu ra luôn có schema; làn có căn cứ dùng tool-calling bắt buộc (`submit_grounded_answer`).
- Reranker chọn bằng `RERANKER_PROVIDER`; khi chạy dev dùng Jina (dịch vụ trả trước, theo ưu tiên của chủ dự án).

## 9. Persona, cảm xúc, trí nhớ

| Thành phần | Ghi chú |
|---|---|
| `context_builder.py`, `persona_loader.py` | **Nội dung bảo vệ** (CON-001): giữ nguyên văn, test hash file ở `tests/unit/security/test_persona_contract.py`. Đây là persona v1 |
| `persona_v2.py` | Persona v2 (chủ dự án duyệt 04/11): lõi nguyên văn từ v1 (test so từng dòng, hash nội dung) + quy tắc "anh" là Senpai, ngọt ngào theo độ thân thiết, ranh giới an toàn, quy tắc từng làn. Chỉ runtime v2 dùng |
| `chisa_voice.py` | Câu cố định do server viết theo giọng Chisa (PER-005): abstain, khung trích dẫn, lỗi, từ chối an toàn |
| RESONA | `emotion_engine.py`, `state_manager.py`: 8 chiều cảm xúc, mức Trust/Attachment, chỉ thị hành vi đưa vào prompt |
| Trí nhớ | Core memory (Postgres, sửa tay qua `/api/v2/me/memory/core`); recall từ Qdrant `memories`; cần consent. Khách không có trí nhớ dài hạn |

Xưng hô bất biến: Chisa xưng "Em", gọi người dùng "Senpai" (PER-003).

## 10. Dữ liệu

- **Postgres** (đầu migration `f2a9c4e7b105`, có test khẳng định): tài khoản và phiên (`accounts`, `account_identities`, `auth_sessions`, `account_tokens`, `users`); hội thoại v1 (`conversations`, `messages`); v2 (`threads`, `thread_turns`, `core_memory`); cảm xúc (`emotion_state`); quyền riêng tư (`user_privacy_preferences`, `erasure_jobs`); hàng đợi (`durable_background_jobs`); ingestion (`wiki_*`, `corpus_releases`, `ingestion_sources`…); tri thức có cấu trúc (`kb_*`); legacy (`pipeline_jobs`, `chunk_state`, `entities`…).
- **Qdrant:** `lore_canon__<version>`, `lore_dialogue__<version>`, `memories`, `guild_memories`, `image_memories`.
- **Redis:** rate limit, quota, cache bản dịch và trạng thái.
- **Đĩa:** `data/ingestion/` (bronze, silver, gold, vectors, images, reports); `.dev/` cho dữ liệu dev và kết quả đo.
- **Xoá dữ liệu:** xoá trí nhớ hoặc rút consent sẽ xoá cả thread và core memory v2 (`clear_user_memory.py`, `memory_policy.py`).

## 11. API và kênh

| Nhóm | Đường dẫn |
|---|---|
| Auth (v1, dùng chung) | `/api/v1/auth/*`: register, login, verify-email, password, Google OAuth, anonymous-session, refresh, logout, capabilities |
| Chat v1 | `/api/v1/chat`, `/chat/stream`, `/chat/history/{id}`, `/chat/emotions/{id}`, `/chat/clear/{id}`, memory-consent |
| Cộng đồng v1 | `/api/v1/community/chat`, `/community/clear/{guild}` |
| Ingestion admin | `sources`, `releases/{id}/publish`, `reconcile`, `rollback` (dưới `/api/v1`) |
| v2 | `POST /api/v2/chat/turns` (SSE), `/api/v2/threads[/{id}][/turns]`, `/api/v2/me/memory/core` |

Sự kiện SSE v2: `turn.started` → `evidence.added`… → `token`… → `turn.completed` hoặc `turn.failed`. Hợp đồng OpenAPI ở `docs/api/openapi.json` (CI kiểm drift; xuất lại bằng `PYTHONPATH=. python scripts/ci/export_openapi.py`).

**Discord:** bot ký workload JWT bằng `CORE_RAG_WORKLOAD_JWT_SECRET`; principal `kind=workload` không bị coi là khách. Kênh "community" dùng luồng cộng đồng v1 (transcript, topic summary, ambient mood). Không có allowlist guild trong beta; giới hạn nằm ở quota và ranh giới của Core.

## 12. Bảo mật và quyền riêng tư

- Principal có `source` (web/discord), `kind` (user/workload), `authentication` (anonymous/account/workload) và scope.
- Rate limit theo principal và route (gom path parameter để không tạo khoá mới); admission quota theo ngày; giới hạn kích thước body.
- Che PII trước mọi provider; injection guard trên tin nhắn và lịch sử; prompt-leakage guard trên đầu ra.
- Không có secret trong repo (gitleaks trong CI quét cả lịch sử commit của PR).
- Telemetry không chứa nội dung prompt hay câu trả lời (MON-013).

## 13. Vận hành và giám sát

- Compose production: `postgres`, `redis`, `qdrant`, `inference`, `model-warmup`, `app`, `worker`, `discord`, `web` (image Caddy: phục vụ SPA, TLS và reverse proxy `/api` tới `app`), `otel-collector`, `docker-socket-proxy`, `migrate`. Giới hạn RAM tổng khoảng 6,4 GB (CON-003, `scripts/ci/check_ram_budget.py`).
- Giám sát: OTEL → collector; alert và SLO ở `deploy/observability/`; mỗi alert phải có runbook ở `docs/runbooks/` (CI kiểm). Nhãn route bị giới hạn bởi danh sách `_ROUTES` trong `app/infrastructure/observability/otel.py`: route mới phải thêm vào đó, nếu không sẽ thành `other`.
- Dev: `./chisa dev start|status|stop` (Postgres, Redis, Qdrant, inference, backend, worker, frontend). **Backend dev không tự nạp lại code**: sửa code xong phải `stop` rồi `start`.

## 14. Đánh giá và cổng chất lượng

| Công cụ | Dùng để |
|---|---|
| `python -m evals run --base-url URL --api v2 --output DIR` | Chấm golden (`data/evaluations/golden_v2/golden_v2.yaml`, `golden-v2.2`, 120 case) qua HTTP |
| `python -m evals.judge REPORT.json` | QUAL-001/002 bằng LLM judge; claim nghiêm trọng phải đọc tay |
| `python -m evals.persona run/score/compare` | 33 kịch bản persona, rubric, bản so sánh trước/sau |
| `python -m evals.retrieval --version V --gate` | Retrieval gate không tốn LLM (Hit@5, MRR@10) |

Chạy eval cần stack dev với `CHAT_V2_ENABLED=true KNOWLEDGE_CORPUS_VERSION=<v>` và nới rate limit, quota **chỉ ở dev**. Golden chỉ được sửa nhãn khi chủ dự án duyệt, và phải nâng `dataset_version`. Kết quả mỗi lần chạy dao động; so theo từng case và giữ JSON ở `.dev/`. Chi phí đo thực tế rất thấp: pha persona 99 mẫu kèm chấm tốn khoảng 0,03 USD trên DeepSeek.

## 15. Quy trình phát triển

- Nhánh từ `HBC` (không có `develop`; `freeze/chisa-v1` đóng băng). Conventional Commits tiếng Anh, có `Refs: <mã yêu cầu>`.
- Mỗi tính năng: test + báo cáo bàn giao trong cùng PR (STD-DOC-007).
- CI: `changed-lines-lint`, `convention-gates`, `web-client-tests`, `discord-bot-tests`, `secret-scan`, `isolated-verification` (`make test-isolated`: unit, mypy, import-linter, OpenAPI, cùng Postgres/Redis/Qdrant tạm).
- Trước khi đẩy: `git add` file mới, rồi chạy `GITHUB_BASE_REF=HBC python scripts/ruff_changed_lines.py` và `scripts/ruff_debt_ratchet.py`; `make test-isolated` không chạy lint của CI.
- Không ghi đè lịch sử nhánh đã đẩy (amend, force-push) khi chưa được chủ dự án cho phép.

## 16. Bẫy đã gặp

| Bẫy | Cách tránh |
|---|---|
| So khớp tiếng Việt sau khi bỏ dấu làm "mẹ/tổ" khớp đại từ, "muộn" khớp "muốn" | Giữ dấu khi so khớp từ khoá |
| `pageprops` của Fandom chứa `<!--IWLINK n-->` thay cho link interwiki | Cleaner lấy giá trị từ DOM (`silver-14`) |
| Embedding một mình không phân biệt được claim bị đổi tên hay phủ định | Kiểm nguyên văn tên, số, phủ định trước |
| Backend dev không tự nạp lại code | Khởi động lại stack trước khi đo |
| File ghi bằng LF trên Windows làm Git báo sửa đổi | Giữ CRLF như bản gốc |
| Chuỗi giống khoá trong workflow hay test làm gitleaks đỏ cả PR | Sinh giá trị lúc chạy |
| Golden dao động giữa các lần chạy | Hỏi lại nhiều lần trước khi kết luận |

## 17. Việc mở chính

- **Cổng R2:** precision của abstain (0,6 so với ≥ 0,90), claim ghép sai quan hệ, kết quả đo persona v2, chuyển corpus `2026.11.04-1`.
- **v2 còn thiếu:** Discord kênh cộng đồng, ảnh, stream bằng sửa tin nhắn; summary cuộn (CONV-002/003); job core memory (MEM-005/010); EMO-003 cùng giao dịch.
- **Nợ:** PERF-003 chờ VPS; `rarity` trống vì giá trị là ảnh; trích dẫn lộ tên trường thô; báo `billing` cho adapter khác ngoài DeepSeek.
- **Sau R2:** R3 IAM, R4 Agentic, R5 Tier B và trí nhớ đầy đủ, R6 gỡ v1 (pipeline 12 stage, visualizer, ingestion legacy) và gộp `thread_turns` vào `messages`.

## 18. Thuật ngữ

| Từ | Nghĩa |
|---|---|
| Senpai | Cách Chisa gọi mọi người dùng |
| Chía-con | Vai trò được dùng Agentic RAG |
| Làn (lane) | Đường xử lý trong một lượt: companion hoặc advanced (sau này thêm agentic) |
| Abstain | Chisa từ chối trả lời vì thiếu bằng chứng; là câu trả lời đúng khi nguồn không có |
| Grounding | Mỗi dữ kiện trong câu trả lời phải bám một trích dẫn nguyên văn |
| RESONA | Hệ cảm xúc 8 chiều tất định của Chisa |
| Tier A / B | Phạm vi trang wiki: A là cốt lõi (khoảng 1.054 trang), B là mở rộng (R5) |
| Bronze / silver / gold | Ba tầng dữ liệu ingestion: thô, đã làm sạch, đã đóng gói thành corpus |
