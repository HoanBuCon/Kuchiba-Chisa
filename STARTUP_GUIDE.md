# ðŸš€ Chisa AI - Startup & Deployment Guide

TÃ i liá»‡u nÃ y hÆ°á»›ng dáº«n chi tiáº¿t cÃ¡ch thiáº¿t láº­p, khá»Ÿi cháº¡y vÃ  giÃ¡m sÃ¡t toÃ n bá»™ há»‡ thá»‘ng Backend cá»§a **Kuchiba Chisa AI**.

Ná»™i dung dÆ°á»›i Ä‘Ã¢y pháº£n Ã¡nh hiá»‡n tráº¡ng code trong workspace: backend lÃ  FastAPI, dá»¯ liá»‡u cháº¡y qua PostgreSQL/Redis/Qdrant, sá»­ dá»¥ng FastAPI Background Tasks, vÃ  frontend trong thÆ° má»¥c `frontend/` lÃ  má»™t app Vite + React riÃªng.

---

## 1. YÃªu cáº§u há»‡ thá»‘ng (Prerequisites)

Äá»ƒ cháº¡y Ä‘Æ°á»£c toÃ n bá»™ há»‡ thá»‘ng mÆ°á»£t mÃ , mÃ¡y tÃ­nh/server cá»§a báº¡n cáº§n cÃ³:
- **Há»‡ Ä‘iá»u hÃ nh:** Windows (khuyáº¿n nghá»‹ cháº¡y trÃªn WSL2) / Linux / macOS.
- **MÃ´i trÆ°á»ng:** Python `3.11`.
- **Ná»n táº£ng áº¢o hÃ³a:** Docker Desktop (Ä‘á»ƒ cháº¡y DB, Cache, Vector Search).
- **Pháº§n má»m quáº£n lÃ½ source:** Git.

---

## 2. Thiáº¿t láº­p Láº§n Ä‘áº§u (First-time Setup)

### BÆ°á»›c 2.1: Clone dá»± Ã¡n vÃ  táº¡o MÃ´i trÆ°á»ng áº£o (Virtualenv)
```powershell
git clone <repository_url>
cd kuchiba_chisa
python -m venv venv

# KÃ­ch hoáº¡t mÃ´i trÆ°á»ng (Windows PowerShell):
.\venv\Scripts\activate
# (Náº¿u á»Ÿ Linux/Mac): source venv/bin/activate
```

### BÆ°á»›c 2.2: CÃ i Ä‘áº·t thÆ° viá»‡n (Dependencies)
```powershell
pip install -r requirements.txt
```

### BÆ°á»›c 2.3: Thiáº¿t láº­p Biáº¿n mÃ´i trÆ°á»ng (.env)
Copy file máº«u cáº¥u hÃ¬nh Ä‘á»ƒ sá»­ dá»¥ng:
```powershell
cp .env.example .env
```
Má»Ÿ file `.env` lÃªn vÃ  Ä‘iá»n cÃ¡c khÃ³a (API Key) cáº§n thiáº¿t:
- `GROQ_API_KEY`: Láº¥y tá»« trang quáº£n trá»‹ developer cá»§a Groq.
- `LLM_PROVIDER`: Chá»n `groq` hoáº·c `gemini`; máº·c Ä‘á»‹nh trong code lÃ  `groq`.
- `GEMINI_API_KEY`: Chá»‰ cáº§n khi chuyá»ƒn provider sang Gemini.
- `JWT_SECRET`: Má»™t chuá»—i ngáº«u nhiÃªn báº£o máº­t cá»§a báº¡n.

CÃ¡c biáº¿n cÃ²n láº¡i trong `.env.example` Ä‘Ã£ cÃ³ default Ä‘á»ƒ há»— trá»£ local dev, nhÆ°ng khi lÃªn production báº¡n nÃªn khai bÃ¡o Ä‘áº§y Ä‘á»§ vÃ  thay toÃ n bá»™ secret máº·c Ä‘á»‹nh.

---

## 3. Khá»Ÿi cháº¡y Háº¡ táº§ng (Infrastructure)

Dá»± Ã¡n phá»¥ thuá»™c vÃ o 3 máº£nh ghÃ©p Core Services náº±m trong Docker:
1. **PostgreSQL** (Port 5432): LÆ°u trá»¯ dá»¯ liá»‡u User, Tin nháº¯n (STM) vÃ  Tráº¡ng thÃ¡i Cáº£m xÃºc tÄ©nh.
2. **Redis** (Port 6379): Phá»¥c vá»¥ Rate Limiting, Cache phá»¥c vá»¥ Rate Limiting.
3. **Qdrant** (Port 6333): Vector Database lÆ°u trá»¯ KÃ½ á»©c (Memories) vÃ  Cá»‘t truyá»‡n (Lore).

`docker-compose.yml` hiá»‡n cÅ©ng dá»±ng thÃªm 2 service á»©ng dá»¥ng: `app` (FastAPI) .

Äá»ƒ cháº¡y táº¥t cáº£ dá»‹ch vá»¥ nÃ y lÃªn, hÃ£y dÃ¹ng lá»‡nh:
```powershell
docker compose up -d --wait
```
*(Cá» `--wait` Ä‘áº£m báº£o cÃ¡c há»‡ thá»‘ng cÆ¡ sá»Ÿ dá»¯ liá»‡u Ä‘Ã£ Health-Check thÃ nh cÃ´ng trÆ°á»›c khi báº¡n Ä‘i tiáº¿p).*

---

## 4. Khá»Ÿi táº¡o Database (Migrations)

Dá»± Ã¡n dÃ¹ng **Alembic** Ä‘á»ƒ quáº£n lÃ½ cáº¥u trÃºc báº£ng PostgreSQL. Láº§n Ä‘áº§u tiá»‡n cháº¡y dá»± Ã¡n, báº¡n **Báº®T BUá»˜C** pháº£i build cÃ¡c báº£ng schema vÃ o DB.
Trong mÃ´i trÆ°á»ng `venv`, cháº¡y lá»‡nh:
```powershell
alembic upgrade head
```
Náº¿u thÃ nh cÃ´ng, cÆ¡ sá»Ÿ dá»¯ liá»‡u cá»§a báº¡n Ä‘Ã£ cÃ³ Ä‘á»§ báº£ng lÃµi Ä‘á»ƒ phá»¥c vá»¥ chat, emotion state, memory metadata vÃ  thá»‘ng kÃª ngÆ°á»i dÃ¹ng.

---

## 5. Khá»Ÿi cháº¡y á»¨ng dá»¥ng & Dá»‹ch vá»¥ Ná»n

### 5.1 Sá»­ dá»¥ng Script tá»± Ä‘á»™ng hÃ³a (PowerShell)
Náº¿u báº¡n lÆ°á»i gÃµ lá»‡nh, dá»± Ã¡n Ä‘Ã£ cÃ³ sáºµn file `start.ps1` á»Ÿ thÆ° má»¥c gá»‘c. Script nÃ y sáº½ tá»± Ä‘á»™ng:
- Khá»Ÿi Ä‘á»™ng Docker Containers.
- Reset láº¡i cÃ¡c Terminal con.
- KÃ­ch hoáº¡t má»™i trÆ°á»ng áº£o vÃ  ná»• mÃ¡y Backend.
- Báº­t Frontend lÃªn á»Ÿ localhost.
```powershell
.\start.ps1
```

### 5.2 Khá»Ÿi cháº¡y thá»§ cÃ´ng (Äá»ƒ tiá»‡n gá»¡ lá»—i/debug)

**Cháº¡y Backend API (FastAPI):**
```powershell
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```
> [!NOTE]
> Khi á»©ng dá»¥ng FastAPI khá»Ÿi Ä‘á»™ng, há»‡ thá»‘ng sáº½ tá»± Ä‘á»™ng thá»±c hiá»‡n **Pre-warming** táº£i vÃ  nhÃºng (embed) toÃ n bá»™ anchors Ä‘á»‹nh tuyáº¿n ngá»¯ nghÄ©a báº±ng **Batch Mode** trá»±c tiáº¿p lÃªn RAM. Nhá» Ä‘Ã³, tin nháº¯n Ä‘áº§u tiÃªn cá»§a ngÆ°á»i dÃ¹ng sáº½ Ä‘Æ°á»£c pháº£n há»“i ngay láº­p tá»©c (zero cold-start latency).

Sau Ä‘Ã³ truy cáº­p Swagger UI Ä‘á»ƒ theo dÃµi tÃ i liá»‡u API táº¡i: `http://localhost:8000/docs`

CÃ¡c route chÃ­nh hiá»‡n cÃ³ lÃ  `/api/v1/chat`, `/api/v1/chat/history/{user_id}`, `/api/v1/chat/emotions/{user_id}` vÃ  `/api/v1/chat/clear/{user_id}`; health check náº±m á»Ÿ nhÃ³m route há»‡ thá»‘ng.

**Cháº¡y Náº¡p Lore Vector (Chá»‰ cáº§n cháº¡y 1 láº§n náº¿u Cá»‘t truyá»‡n thay Ä‘á»•i):**
```powershell
python scripts/ingest_chisa_lore.py
```

---

## 6. GiÃ¡m sÃ¡t Há»‡ thá»‘ng (Monitoring Scripts)

ÄÃ¢y lÃ  nhá»¯ng chá»©c nÄƒng Ä‘á»™c quyá»n cá»§a dá»± Ã¡n giÃºp quan sÃ¡t "nÃ£o bá»™" cá»§a Chisa cháº¡y ngáº§m dÆ°á»›i dáº¡ng Real-Time (Theo thá»i gian thá»±c). Báº¡n nÃªn báº­t chÃºng á»Ÿ cÃ¡c Tab Terminal riÃªng biá»‡t song song vá»›i Backend.

CÃ¡c script nÃ y Ä‘á»c dá»¯ liá»‡u hiá»‡n cÃ³ tá»« database/vector store, nÃªn sáº½ há»¯u Ã­ch nháº¥t sau khi Ä‘Ã£ cháº¡y migration, khá»Ÿi Ä‘á»™ng infra vÃ  cÃ³ Ã­t nháº¥t má»™t luá»“ng chat thá»±c táº¿.

### 6.1 GÆ°Æ¡ng soi Cáº£m xÃºc (Emotion Watcher)
Hiá»ƒn thá»‹ trá»±c tiáº¿p cÃ¡c xung Ä‘á»™ng Ä‘iá»ƒm cáº£m xÃºc (Joy, Sad, Irritation...) khi Chisa Ä‘ang bá»‹ ngÆ°á»i dÃ¹ng tÃ¡c Ä‘á»™ng, tÃ­ch há»£p bá»™ Ä‘áº¿m DEHA Algorithm:
```powershell
python .\scripts\watch_emotions.py
```

### 6.2 MÃ¡y Ä‘o dÃ²ng Token (Token Consumption Watcher)
Theo dÃµi lÆ°á»£ng Token bá»‹ Ä‘á»‘t chÃ¡y trá»±c tiáº¿p cá»§a mÃ´ hÃ¬nh Llama-3 theo tá»«ng tin nháº¯n, há»¯u Ã­ch Ä‘á»ƒ tá»‘i Æ°u chi phÃ­ vÃ  trÃ¡nh lá»—i `429 Rate Limit` tá»« Groq:
```powershell
python .\scripts\watch_tokens.py
```

### 6.3 Báº£ng Ä‘iá»u khiá»ƒn trá»±c quan Web (Chisa AI Visualizer Dashboard)
GiÃ¡m sÃ¡t toÃ n bá»™ luá»“ng RAG, suy luáº­n Loop Thinking, ngÃ¢n sÃ¡ch token vÃ  cáº­p nháº­t tráº¡ng thÃ¡i cáº£m xÃºc theo thá»i gian thá»±c dÆ°á»›i giao diá»‡n Web trá»±c quan:
- **Äá»‹a chá»‰:** `http://localhost:8000/visualizer`
- **TÃ­nh nÄƒng:** Theo dÃµi cÃ¡c váº¿t thá»±c thi (execution traces), chi tiáº¿t tá»«ng bÆ°á»›c RAG (Lore, Memory), phÃ¢n bá»• ngÃ¢n sÃ¡ch token (Prompt Budget), thá»i gian pháº£n há»“i/Ä‘á»™ trá»… vÃ  biáº¿n thiÃªn tráº¡ng thÃ¡i cáº£m xÃºc chi tiáº¿t.
- Giao diá»‡n cÃ³ thiáº¿t káº¿ responsive Ä‘áº§y Ä‘á»§, há»— trá»£ tá»‘t cáº£ trÃªn PC, mÃ¡y tÃ­nh báº£ng vÃ  thiáº¿t bá»‹ di Ä‘á»™ng.

---

## 7. CÃ¡c lá»—i thÆ°á»ng gáº·p (Troubleshooting)

1. **Lá»—i `429 Too Many Requests` tá»« Groq:** 
   - LÃ½ do: GÃ³i Miá»…n phÃ­ cá»§a Groq giá»›i háº¡n Token Per Minute (~14,400 TPM).
   - Giáº£i quyáº¿t: Náº¿u khÃ´ng nÃ¢ng cáº¥p lÃªn Developer Plan ($5), hÃ£y chá» khoáº£ng 1 phÃºt trÆ°á»›c khi chat tiáº¿p. Há»‡ thá»‘ng Ä‘Ã£ Ä‘Æ°á»£c cáº¥u hÃ¬nh Fail-fast (VÆ°á»£t lá»—i Ä‘i tiáº¿p) mÃ  khÃ´ng bá»‹ treo pháº§n má»m.

2. **Lá»—i backend khÃ´ng khá»Ÿi Ä‘á»™ng Ä‘Æ°á»£c ngay lÃºc startup:**
   - LÃ½ do: `app/main.py` kiá»ƒm tra Postgres, Redis vÃ  Qdrant trong lifecycle startup. Náº¿u thiáº¿u má»™t trong ba dá»‹ch vá»¥ nÃ y, backend cÃ³ thá»ƒ chá»‰ cháº¡y á»Ÿ cháº¿ Ä‘á»™ cáº£nh bÃ¡o trong dev hoáº·c dá»«ng háº³n khi `APP_ENV=production`.
   - Giáº£i quyáº¿t: Kiá»ƒm tra láº¡i `docker compose up -d --wait`, giÃ¡ trá»‹ `DATABASE_URL`, `REDIS_URL`, `QDRANT_URL`, vÃ  log cá»§a tá»«ng service.

3. **Lá»—i `OperationalError (could not translate host name, Connection Refused)`:**
   - LÃ½ do: Háº¡ táº§ng Docker chÆ°a báº­t lÃªn, hoáº·c Cá»•ng 5432 (PostgreSQL)/6379 (Redis) Ä‘ang bá»‹ á»©ng dá»¥ng khÃ¡c chiáº¿m dá»¥ng.
   - Giáº£i quyáº¿t: Báº­t Docker Desktop lÃªn, cháº¡y lá»‡nh `docker compose down` rá»“i lÃªn láº¡i `docker compose up -d`.

4. **Lá»—i thiáº¿u ThÆ° viá»‡n (ModuleNotFoundError):**
   - Giáº£i quyáº¿t: Äáº£m báº£o báº¡n Ä‘ang á»Ÿ mÃ´i trÆ°á»ng áº£o `(venv)` trÆ°á»›c khi cháº¡y báº¥t ká»³ script hay lá»‡nh uvicorn nÃ o. Cháº¡y láº¡i `pip install -r requirements.txt`.
