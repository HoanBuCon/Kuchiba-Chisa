# 🌸 Kuchiba Chisa - Emotional RAG Waifu Backend 🌸

<div align="center">
  <img src="assets/chisa_beauty.gif" alt="Chisa Beauty" width="400"/>
</div>

## ✨ Project Overview

**Chisa AI** is an advanced Backend System designed for a **Personalized Memory RAG (Retrieval-Augmented Generation) + Emotional AI system**. It acts as the "brain" and "heart" of your AI companion, persisting conversations, extracting long-term insights, and dynamically shifting her emotional state based on interactions over time.

Built for scale, stability, and speed using the bleeding edge Python ecosystem.

<div align="center">
  <img src="assets/dance_chisa.gif" alt="Chisa Dance" height="200"/>
  <img src="assets/chisa_eat.jpg" alt="Chisa Eat" height="200"/>
  <img src="assets/play_chisa.gif" alt="Play Chisa" height="200"/>
</div>

---

## 🏗️ Architecture & Tech Stack

![Chisa Drink](assets/chisa_drink.gif)

- **Language:** Python 3.11
- **API Framework:** FastAPI (Async)
- **Database (Relational):** PostgreSQL 16 (Short-term memory, User logic, Emotional State)
- **Vector Database:** Qdrant (Long-term semantic memory, RAG)
- **Caching & Message Broker:** Redis
- **Background Jobs:** Celery (Asynchronous embedding generation, pruning, emotional updates)
- **ORM:** SQLAlchemy 2.0 (Async) + Alembic for migrations
- **LLM Integration:** Groq (High-speed Llama-3 endpoints)
- **Infrastructure:** Docker & Docker Compose

---

## 🚀 Features

- **Long-Term Memory Indexing:** Asynchronously extracts and embeds relational and episodic memories.
- **Emotional State Tracking:** Stateful database-backed emotions (mood, affection, trust) instead of pure LLM-hallucinated emotions.
- **Affection System:** Tracks Chisa's affection deltas over time using `AffectionLog`, altering her behavior dynamically.
- **Conversation Lifecycle:** Complete Session Layer management indexing summaries.
- **Distributed Queuing:** Heavy NLP and vectoring tasks are deferred to Celery workers ensuring a zero-lag chat API.

---

## 🛠️ Quickstart (Docker Environment)

### 1. Prerequisites
- Docker Desktop
- Python 3.11 (for local virtualenv development)
- Git

### 2. Environment Variables
Copy `.env.example` to `.env` and fill in the secrets (Groq API keys, OpenAI API, JWT config, PostgreSQL credentials).

### 3. Spin up Infrastructure
Launch PostgreSQL, Redis, Qdrant, Celery Worker, and FastAPI:
```powershell
docker compose up -d --wait
```

### 4. Database Migrations
Initialize the database tables via Alembic from your local virtual environment:
```powershell
.\venv\Scripts\activate
.\venv\Scripts\alembic upgrade head
```

<div align="center">
  <img src="assets/chisa_cat_spin.gif" alt="Spin" width="200"/>
</div>

---

## 📜 Documentation

- **[Architecture & Data Flow](ARCHITECTURE.md)**: Detailed breakdown of the RAG system and database schema.
- **[Startup Guide](STARTUP_GUIDE.md)**: Advanced deployment instructions and Celery monitoring.

<br>

<div align="center">
  <img src="assets/chisa_kiss.gif" alt="Chisa Kiss" width="400"/>
  <p><i>Made with ❤️</i></p>
</div>
