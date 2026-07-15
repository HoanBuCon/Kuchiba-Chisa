from __future__ import annotations
from contextlib import asynccontextmanager
from typing import AsyncIterator
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from app.config.settings import settings
from app.infrastructure.logging.logger import configure_logging, get_logger
from app.infrastructure.database.engine import connect_database, disconnect_database
from app.infrastructure.cache.redis.redis_service import redis_service
from app.infrastructure.vector.qdrant.qdrant_service import qdrant_service
from app.interface.api.routes import health, chat, visualizer
from app.interface.middlewares.rate_limiter import RateLimitMiddleware
from app.shared.utils.background_tasks import BackgroundTaskManager

# Configure logging before anything else
configure_logging()
log = get_logger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ASSETS_DIR = PROJECT_ROOT / "assets"


# ─── Application Lifespan ────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """
    Manages the lifecycle of all infrastructure connections.
    Startup: connect and verify all services.
    Shutdown: gracefully close all connections.
    """
    log.info("[Chisa] Chisa API starting up...", env=settings.APP_ENV)

    # ── Startup ──────────────────────────────────────────────────
    startup_errors: list[str] = []

    # PostgreSQL
    try:
        await connect_database()
    except Exception as e:
        startup_errors.append(f"PostgreSQL: {e}")
        log.error("PostgreSQL startup failed", error=str(e))

    # Redis
    redis_ok = await redis_service.health_check()
    if redis_ok:
        log.info("Redis connection verified ✓")
    else:
        startup_errors.append("Redis: health check failed")
        log.error("Redis startup health check failed")

    # Qdrant
    qdrant_ok = await qdrant_service.health_check()
    if qdrant_ok:
        log.info("Qdrant connection verified ✓")
        # Initialize collections (idempotent)
        await qdrant_service.initialize_all_collections()
    else:
        startup_errors.append("Qdrant: health check failed")
        log.error("Qdrant startup health check failed")

    if startup_errors and settings.is_prod:
        raise RuntimeError(f"Critical startup failures: {startup_errors}")
    elif startup_errors:
        log.warning("Non-fatal startup warnings (dev mode)", issues=startup_errors)

    # ── Validate LLM API Key ──────────────────────────────────────
    try:
        provider = settings.LLM_PROVIDER
        if provider == "gemini":
            if not settings.GEMINI_API_KEY:
                startup_errors.append(f"LLM ({provider}): GEMINI_API_KEY is not set")
            else:
                log.info("LLM API key (Gemini) verified ✓")
        elif provider == "deepseek":
            if not settings.DEEPSEEK_API_KEY:
                startup_errors.append(f"LLM ({provider}): DEEPSEEK_API_KEY is not set")
            else:
                log.info("LLM API key (DeepSeek) verified ✓")
        elif provider == "groq":
            if not settings.GROQ_API_KEY:
                startup_errors.append(f"LLM ({provider}): GROQ_API_KEY is not set")
            else:
                log.info("LLM API key (Groq) verified ✓")
    except Exception as e:
        startup_errors.append(f"LLM API key validation failed: {e}")



    log.info("[Chisa] Chisa API ready", port=settings.APP_PORT)
    yield

    # ── Shutdown ─────────────────────────────────────────────────────────
    log.info("Shutting down Chisa API...")
    await BackgroundTaskManager.shutdown(timeout=10.0)
    await disconnect_database()
    await redis_service.disconnect()
    await qdrant_service.disconnect()
    
    from app.application.dependencies import container
    if "http_client" in container.__dict__:
        await container.http_client.aclose()
        
    log.info("Chisa API shutdown complete")


# ─── FastAPI Application ──────────────────────────────────────────────────────

def create_app() -> FastAPI:
    app = FastAPI(
        title="Chisa AI — Backend API",
        description="Production-grade AI Girlfriend backend with RAG, mood engine, and memory.",
        version="0.1.0",
        docs_url="/docs" if not settings.is_prod else None,
        redoc_url="/redoc" if not settings.is_prod else None,
        openapi_url="/openapi.json" if not settings.is_prod else None,
        lifespan=lifespan,
    )

    # ── CORS ─────────────────────────────────────────────────────────
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173",
                       "http://localhost:5174", "http://127.0.0.1:5174"] if settings.is_dev else [],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Rate Limiting ────────────────────────────────────────────────
    app.add_middleware(RateLimitMiddleware)

    # ── Routes ───────────────────────────────────────────────────
    app.include_router(health.router, tags=["System"])
    
    # Phase 3+ routes:
    app.include_router(chat.router, prefix="/api/v1", tags=["Chat"])
    app.include_router(visualizer.router, tags=["Visualizer"])
    # app.include_router(users.router, prefix="/api/v1", tags=["Users"])
    
    from app.api.routers import admin_ingestion
    app.include_router(admin_ingestion.router, prefix="/api/v1")

    if ASSETS_DIR.is_dir():
        app.mount("/assets", StaticFiles(directory=str(ASSETS_DIR)), name="assets")
    else:
        log.warning("Assets directory not found; /assets static route disabled", path=str(ASSETS_DIR))

    return app


app = create_app()


# ─── Entry Point ─────────────────────────────────────────────────────────────

def start() -> None:
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.APP_HOST,
        port=settings.APP_PORT,
        reload=settings.is_dev,
        log_level="debug" if settings.is_dev else "info",
        workers=1,
    )


if __name__ == "__main__":
    start()
