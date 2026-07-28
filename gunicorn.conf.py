"""
Gunicorn configuration for multi-worker Uvicorn deployment.
Reads worker count from WEB_CONCURRENCY environment variable (default: 2 for 4GB VPS).
"""
import os

bind = f"{os.getenv('APP_HOST', '0.0.0.0')}:{os.getenv('APP_PORT', '8000')}"
workers = int(os.getenv("WEB_CONCURRENCY", "2"))
worker_class = "uvicorn.workers.UvicornWorker"
keepalive = 65
timeout = 120
graceful_timeout = 30
loglevel = "info"
accesslog = "-"
errorlog = "-"
