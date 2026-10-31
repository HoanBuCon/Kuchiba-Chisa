"""Chisa DEVELOPMENT stack orchestrator (``chisa dev <command>``).

Starts infrastructure (Docker: Postgres, Redis, Qdrant), applies migrations,
bootstraps the Qdrant alias contract, then runs the backend, worker, frontend and
(optionally) the Discord bot on the host, waiting for real readiness at each step.

Development only, by construction:

* ``.env`` must say ``APP_ENV=development``; every datastore/API URL must be local;
* a conflicting process environment (e.g. a leftover ``APP_ENV=production``) aborts;
* only ``.env`` / ``discord/.env`` are read, never ``.env.production*``;
* nothing is ever deleted: ``stop`` stops containers, it never removes volumes.

Secrets are never printed: output and log tails are scrubbed of known secret values.
"""

from __future__ import annotations

import argparse
import base64
import contextlib
import hashlib
import hmac
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import unquote, urlparse

ROOT = Path(__file__).resolve().parents[1]
STATE_DIR = ROOT / ".dev"
LOG_DIR = STATE_DIR / "logs"
BACKUP_DIR = STATE_DIR / "backups"
MODEL_CACHE = STATE_DIR / "models"
PID_FILE = STATE_DIR / "pids.json"
COMPOSE_FILE = ROOT / "docker-compose.dev.yml"

LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})
BACKEND_PORT = 8000
INFERENCE_PORT = 8090
FRONTEND_PORT = 5173
BACKEND_URL = f"http://127.0.0.1:{BACKEND_PORT}"
FRONTEND_URL = f"http://127.0.0.1:{FRONTEND_PORT}"
INFERENCE_URL = f"http://127.0.0.1:{INFERENCE_PORT}"
INFRA_SERVICES = ("postgres", "redis", "qdrant")
APP_SERVICES = ("inference", "backend", "worker", "frontend", "discord")

LLM_KEYS = {"deepseek": "DEEPSEEK_API_KEY", "groq": "GROQ_API_KEY", "gemini": "GEMINI_API_KEY"}
RERANKER_KEYS = {"voyage": "VOYAGE_API_KEY", "jina": "JINA_API_KEY", "cohere": "COHERE_API_KEY"}
PLACEHOLDER = re.compile(r"replace_|change_this|your_|placeholder", re.IGNORECASE)
SECRET_NAME = re.compile(r"KEY|SECRET|PASSWORD|TOKEN", re.IGNORECASE)
# Keys whose process-environment value would silently override .env (pydantic reads both).
SAFETY_KEYS = (
    "APP_ENV",
    "DATABASE_URL",
    "REDIS_URL",
    "QDRANT_URL",
    "PUBLIC_APP_URL",
    "CORE_RAG_BASE_URL",
)

Env = dict[str, str]


class DevError(Exception):
    """A precondition failed; the message is safe to print."""


# ── Output ───────────────────────────────────────────────────────────────


def say(message: str = "") -> None:
    print(message, flush=True)


def step(tag: str, message: str) -> None:
    say(f"[{tag}] {message}")


# ── Environment loading, validation and safety ───────────────────────────


def load_env(path: Path) -> Env:
    from dotenv import dotenv_values

    if not path.is_file():
        raise DevError(f"{path.relative_to(ROOT)} not found (copy .env.example and fill it in)")
    return {k: (v or "") for k, v in dotenv_values(path).items()}


def secret_values(*envs: Env) -> list[str]:
    """Every secret-looking value (plus passwords inside URLs), for output scrubbing."""
    found: set[str] = set()
    for env in envs:
        for key, value in env.items():
            if (
                value
                and SECRET_NAME.search(key)
                and len(value) >= 8
                and not PLACEHOLDER.search(value)
            ):
                found.add(value)
            parsed = urlparse(value) if "://" in value else None
            if parsed and parsed.password:
                found.add(unquote(parsed.password))
    return sorted(found, key=len, reverse=True)


def scrub(text: str, secrets: list[str]) -> str:
    for secret in secrets:
        text = text.replace(secret, "***")
    return text


def host_of(url: str) -> str:
    return (urlparse(url).hostname or "").lower()


def validate_environment(env: Env, *, with_discord: bool = False) -> list[str]:
    """Return a list of problems (empty when the dev environment is startable)."""
    problems: list[str] = []
    if env.get("APP_ENV", "") != "development":
        problems.append("APP_ENV must be 'development' (this tool refuses anything else)")

    for key in ("DATABASE_URL", "REDIS_URL", "QDRANT_URL"):
        if not env.get(key):
            problems.append(f"{key} is missing")
        elif host_of(env[key]) not in LOCAL_HOSTS:
            problems.append(f"{key} must point to localhost (found a non-local host)")
    for key in (
        "CELERY_BROKER_URL",
        "CELERY_RESULT_BACKEND",
        "PUBLIC_APP_URL",
        "CORE_RAG_BASE_URL",
    ):
        if env.get(key) and host_of(env[key]) not in LOCAL_HOSTS:
            problems.append(f"{key} must point to localhost (found a non-local host)")
    if env.get("DATABASE_URL") and not urlparse(env["DATABASE_URL"]).password:
        problems.append("DATABASE_URL must include the development database password")

    for key in ("JWT_SECRET", "SECRET_KEY", "DISCORD_WORKLOAD_JWT_SECRET"):
        value = env.get(key, "")
        if not value:
            problems.append(f"{key} is missing")
        elif PLACEHOLDER.search(value):
            problems.append(f"{key} still has a template value")
        elif len(value) < 32:
            problems.append(f"{key} must be at least 32 characters")

    providers = {env.get("LLM_PROVIDER", "deepseek")}
    providers |= {p.strip() for p in env.get("LLM_ENABLED_PROVIDERS", "").split(",") if p.strip()}
    for provider in sorted(providers):
        key_name = LLM_KEYS.get(provider)
        if key_name is None:
            problems.append(f"unknown LLM provider '{provider}'")
        elif not env.get(key_name) or PLACEHOLDER.search(env[key_name]):
            problems.append(f"{key_name} is missing (LLM provider '{provider}' is enabled)")
    reranker = env.get("RERANKER_PROVIDER", "disabled")
    reranker_key = RERANKER_KEYS.get(reranker)
    if reranker_key and (not env.get(reranker_key) or PLACEHOLDER.search(env[reranker_key])):
        problems.append(f"{reranker_key} is missing (RERANKER_PROVIDER='{reranker}')")

    if with_discord:
        problems += validate_discord(env)
    return problems


def validate_discord(env: Env) -> list[str]:
    try:
        discord = load_env(ROOT / "discord" / ".env")
    except DevError as error:
        return [str(error)]
    problems: list[str] = []
    token = discord.get("DISCORD_TOKEN", "")
    if not token or PLACEHOLDER.search(token):
        problems.append("discord/.env: DISCORD_TOKEN is missing")
    if not discord.get("DISCORD_CLIENT_ID"):
        problems.append("discord/.env: DISCORD_CLIENT_ID is missing")
    bot_secret = discord.get("CORE_RAG_WORKLOAD_JWT_SECRET", "")
    if not bot_secret:
        problems.append("discord/.env: CORE_RAG_WORKLOAD_JWT_SECRET is missing")
    elif not hmac.compare_digest(bot_secret, env.get("DISCORD_WORKLOAD_JWT_SECRET", "")):
        problems.append(
            "discord/.env CORE_RAG_WORKLOAD_JWT_SECRET must equal DISCORD_WORKLOAD_JWT_SECRET"
        )
    for key in ("DATABASE_URL", "CORE_RAG_BASE_URL"):
        if discord.get(key) and host_of(discord[key]) not in LOCAL_HOSTS:
            problems.append(f"discord/.env: {key} must point to localhost")
    return problems


def conflicting_process_env(env: Env) -> list[str]:
    """Names of variables exported in the shell that disagree with .env."""
    return [key for key in SAFETY_KEYS if key in os.environ and os.environ[key] != env.get(key, "")]


def check_settings_load(python: str) -> None:
    """Let the real Settings class have the final word (prints field names only)."""
    probe = (
        "import sys\n"
        "try:\n"
        "    from app.config.settings import Settings\n"
        "    Settings()\n"
        "except Exception as e:\n"
        "    errs = e.errors() if hasattr(e, 'errors') else []\n"
        "    names = [('.'.join(map(str, x['loc'])) or x['msg']) for x in errs]\n"
        "    print('INVALID ' + (', '.join(names) or type(e).__name__))\n"
        "    sys.exit(1)\n"
        "print('OK')\n"
    )
    result = subprocess.run(
        [python, "-c", probe],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
    )
    if result.returncode != 0:
        raise DevError(f"backend Settings rejected the environment: {result.stdout.strip()}")


def preflight(env: Env, python: str, *, with_discord: bool) -> list[str]:
    """Validate and print the environment banner. Returns secrets to scrub."""
    conflicts = conflicting_process_env(env)
    if conflicts:
        raise DevError(
            "shell environment overrides .env for: "
            + ", ".join(conflicts)
            + " (unset them; this tool never mixes environments)"
        )
    problems = validate_environment(env, with_discord=with_discord)
    if problems:
        raise DevError("environment is not startable:\n  - " + "\n  - ".join(problems))
    check_settings_load(python)
    db, redis, qdrant = (urlparse(env[k]) for k in ("DATABASE_URL", "REDIS_URL", "QDRANT_URL"))
    say("=" * 64)
    say(" CHISA DEV   environment=development   (local only)")
    say(
        f" postgres={db.hostname}:{db.port or 5432}  redis={redis.hostname}:{redis.port or 6379}"
        f"  qdrant={qdrant.hostname}:{qdrant.port or 6333}"
    )
    provider = env.get("LLM_PROVIDER", "deepseek")
    reranker = env.get("RERANKER_PROVIDER", "disabled")
    say(f" provider={provider}  reranker={reranker}")
    say("=" * 64)
    return secret_values(env, load_env(ROOT / "discord" / ".env") if with_discord else {})


# ── Probes ───────────────────────────────────────────────────────────────


def _tcp(host: str, port: int, payload: bytes, timeout: float = 2.0) -> bytes | None:
    try:
        with socket.create_connection((host, port), timeout=timeout) as sock:
            sock.settimeout(timeout)
            sock.sendall(payload)
            return sock.recv(64)
    except OSError:
        return None


def probe_postgres(env: Env) -> bool:
    url = urlparse(env["DATABASE_URL"])
    reply = _tcp(url.hostname or "127.0.0.1", url.port or 5432, b"\x00\x00\x00\x08\x04\xd2\x16\x2f")
    return reply in (b"S", b"N")  # a Postgres server answers the SSLRequest handshake


def probe_redis(env: Env) -> bool:
    url = urlparse(env["REDIS_URL"])
    reply = _tcp(url.hostname or "127.0.0.1", url.port or 6379, b"PING\r\n")
    return bool(reply and reply.startswith(b"+PONG"))


def probe_qdrant(env: Env) -> bool:
    return http_status(env["QDRANT_URL"].rstrip("/") + "/readyz") == 200


def http_status(url: str, timeout: float = 3.0) -> int | None:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return int(response.status)
    except urllib.error.HTTPError as error:
        return int(error.code)
    except (urllib.error.URLError, OSError, ValueError):
        return None


def http_json(
    method: str,
    url: str,
    body: Mapping | None = None,
    headers: Mapping[str, str] | None = None,
    timeout: float = 30.0,
) -> tuple[int, object]:
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(url, data=data, method=method)
    request.add_header("Accept", "application/json")
    if data is not None:
        request.add_header("Content-Type", "application/json")
    for key, value in (headers or {}).items():
        request.add_header(key, value)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
            status = int(response.status)
    except urllib.error.HTTPError as error:
        raw, status = error.read(), int(error.code)
    except (urllib.error.URLError, OSError):
        return 0, None  # not reachable (yet): callers treat status 0 as "not ready"
    try:
        return status, json.loads(raw) if raw else None
    except ValueError:
        return status, None


def wait_for(
    description: str,
    check: Callable[[], bool],
    timeout: float,
    *,
    alive: Callable[[], bool] | None = None,
    interval: float = 1.0,
) -> None:
    """Block until ``check`` passes; fail fast if the owning process died."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if check():
            return
        if alive is not None and not alive():
            raise DevError(f"{description}: process exited during startup")
        time.sleep(interval)
    raise DevError(f"{description}: not ready after {int(timeout)}s")


# ── Infrastructure, migrations, Qdrant bootstrap ─────────────────────────


def postgres_password(env: Env) -> str:
    return unquote(urlparse(env["DATABASE_URL"]).password or "")


def compose_env(env: Env) -> dict[str, str]:
    merged = dict(os.environ)
    merged["CHISA_DEV_POSTGRES_PASSWORD"] = postgres_password(env)
    return merged


def infra_status(env: Env) -> dict[str, bool]:
    return {
        "postgres": probe_postgres(env),
        "redis": probe_redis(env),
        "qdrant": probe_qdrant(env),
    }


def ensure_infra(env: Env, secrets: list[str]) -> None:
    status = infra_status(env)
    missing = [name for name, ok in status.items() if not ok]
    if not missing:
        step("infra", "postgres, redis and qdrant already running (left untouched)")
        return
    if shutil.which("docker") is None:
        raise DevError(
            "docker is not installed or not on PATH (needed to start " + ", ".join(missing) + ")"
        )
    step("infra", "starting " + ", ".join(missing) + " (docker-compose.dev.yml)")
    result = subprocess.run(
        ["docker", "compose", "-f", str(COMPOSE_FILE), "up", "-d", "--no-deps", "--wait", *missing],
        cwd=ROOT,
        env=compose_env(env),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=600,
    )
    if result.returncode != 0:
        detail = scrub((result.stdout + result.stderr).strip()[-1200:], secrets)
        raise DevError(
            f"docker compose failed (is Docker Desktop running? port already used?):\n{detail}"
        )
    probes = {"postgres": probe_postgres, "redis": probe_redis, "qdrant": probe_qdrant}
    for name in missing:
        wait_for(name, lambda probe=probes[name]: probe(env), 90)
    step("infra", "postgres, redis and qdrant are ready")


def child_env() -> dict[str, str]:
    """Environment for every spawned Python/Node process."""
    return dict(
        os.environ,
        PYTHONUTF8="1",
        PYTHONUNBUFFERED="1",
        # FastEmbed's default cache is the OS temp dir, which gets cleaned and forces a
        # 470 MB re-download; keep it with the other (git-ignored) development state.
        FASTEMBED_CACHE_PATH=str(MODEL_CACHE),
    )


def run_python(python: str, *args: str, timeout: float = 600) -> subprocess.CompletedProcess[str]:
    env = child_env()
    return subprocess.run(
        [python, *args],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )


def alembic_revisions(python: str, secrets: list[str]) -> tuple[str, str]:
    """(current revision or '', head revision)."""
    current = run_python(python, "-m", "alembic", "current")
    heads = run_python(python, "-m", "alembic", "heads")
    if current.returncode != 0 or heads.returncode != 0:
        detail = scrub((current.stderr + heads.stderr).strip()[-800:], secrets)
        raise DevError(f"alembic could not reach the database:\n{detail}")
    rev = re.compile(r"^([0-9a-f]{12})\b", re.MULTILINE)
    now = rev.search(current.stdout)
    head = rev.search(heads.stdout)
    if head is None:
        raise DevError("alembic reported no head revision")
    return (now.group(1) if now else ""), head.group(1)


def backup_database(current: str, secrets: list[str]) -> Path:
    if shutil.which("docker") is None:
        raise DevError(
            "cannot back up before migrating: docker not found (use --no-backup to skip)"
        )
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    target = BACKUP_DIR / f"chisa_db-{stamp}-from-{current}.dump"
    with target.open("wb") as out:
        result = subprocess.run(
            ["docker", "exec", "chisa_postgres", "pg_dump", "-U", "chisa", "-Fc", "chisa_db"],
            stdout=out,
            stderr=subprocess.PIPE,
            timeout=600,
        )
    if result.returncode != 0 or target.stat().st_size == 0:
        target.unlink(missing_ok=True)
        detail = scrub(result.stderr.decode(errors="replace")[-500:], secrets)
        raise DevError(f"database backup failed; migration not attempted:\n{detail}")
    for old in sorted(BACKUP_DIR.glob("chisa_db-*.dump"))[:-5]:
        old.unlink(missing_ok=True)
    return target


def ensure_migrations(python: str, secrets: list[str], *, backup: bool) -> None:
    current, head = alembic_revisions(python, secrets)
    if current == head:
        step("migrate", f"database already at head ({head})")
        return
    if current and backup:
        dump = backup_database(current, secrets)
        step("migrate", f"backup written: {dump.relative_to(ROOT)}")
    step("migrate", f"upgrading {current or '<empty>'} -> {head}")
    result = run_python(python, "-m", "alembic", "upgrade", "head")
    if result.returncode != 0:
        detail = scrub((result.stdout + result.stderr).strip()[-1500:], secrets)
        raise DevError(f"alembic upgrade failed:\n{detail}")
    current, head = alembic_revisions(python, secrets)
    if current != head:
        raise DevError(f"database is at {current}, expected {head} after upgrade")
    step("migrate", f"database at head ({head})")


def ensure_qdrant_state(python: str, secrets: list[str]) -> None:
    result = run_python(python, str(ROOT / "scripts" / "dev_bootstrap_qdrant.py"), timeout=120)
    output = scrub((result.stdout + result.stderr).strip(), secrets)
    if result.returncode != 0:
        raise DevError(f"qdrant bootstrap failed:\n{output[-1200:]}")
    created = [ln for ln in result.stdout.splitlines() if "->" in ln]
    step("qdrant", f"aliases ready ({len(created)} created, rest already present)")
    for line in created:
        say(f"         {line}")


LORE_COLLECTIONS = ("character_lore", "world_lore", "story_lore")
_NO_ACL = {"must": [{"is_empty": {"key": "access_scope"}}]}


def lore_acl_gap(env: Env) -> dict[str, int]:
    """Lore points that retrieval cannot see because they have no ``access_scope``.

    Retrieval only returns points whose payload says public/user/tenant. Corpora
    ingested before that contract (older local dev data) have none and are invisible.
    """
    base = env["QDRANT_URL"].rstrip("/")
    gap: dict[str, int] = {}
    for name in LORE_COLLECTIONS:
        status, body = http_json(
            "POST",
            f"{base}/collections/{name}__active/points/count",
            {"filter": _NO_ACL, "exact": True},
            timeout=15,
        )
        if status != 200 or not isinstance(body, dict):
            raise DevError(f"qdrant count failed for {name}__active (HTTP {status})")
        gap[name] = int(body["result"]["count"])
    return gap


def warn_if_lore_invisible(env: Env) -> None:
    gap = lore_acl_gap(env)
    if any(gap.values()):
        total = sum(gap.values())
        step(
            "qdrant",
            f"WARNING {total} lore points have no access_scope and are invisible to retrieval; "
            "run `chisa dev backfill-lore-acl` (dev corpus predates the ACL payload contract)",
        )


def cmd_backfill_lore_acl(args: argparse.Namespace, python: str) -> int:
    """Mark legacy dev lore points public (adds one payload key; nothing is deleted)."""
    env = load_env(ROOT / ".env")
    preflight(env, python, with_discord=False)
    gap = lore_acl_gap(env)
    say(f"points without access_scope: {gap}")
    if not any(gap.values()):
        say("nothing to do")
        return 0
    base = env["QDRANT_URL"].rstrip("/")
    for name, missing in gap.items():
        if not missing:
            continue
        status, _ = http_json(
            "POST",
            f"{base}/collections/{name}__active/points/payload?wait=true",
            {"payload": {"access_scope": "public"}, "filter": _NO_ACL},
            timeout=120,
        )
        if status != 200:
            raise DevError(f"backfill failed for {name} (HTTP {status})")
        step("qdrant", f"{name}: {missing} points marked access_scope=public")
    after = lore_acl_gap(env)
    if any(after.values()):
        raise DevError(f"points still missing access_scope: {after}")
    say("lore corpus is now visible to retrieval")
    return 0


def embedding_model_cached() -> bool:
    pattern = "models--*multilingual-e5-small/snapshots/*/onnx/model.onnx"
    return any(MODEL_CACHE.glob(pattern))


def ensure_embedding_cache(python: str, secrets: list[str]) -> None:
    """Download the embedding model once, in a single process, before any service starts.

    Concurrent first-time downloads (API workers + worker) corrupt the cache, so this
    must finish before the backend and worker are launched.
    """
    if embedding_model_cached():
        step("embeddings", "model cache present")
        return
    step("embeddings", "first run: downloading the embedding model (~470 MB), please wait")
    result = run_python(python, "-m", "app.ops.warm_embedding_cache", timeout=1800)
    if result.returncode != 0 or not embedding_model_cached():
        detail = scrub((result.stdout + result.stderr).strip()[-800:], secrets)
        raise DevError(f"embedding model download failed (network?):\n{detail}")
    step("embeddings", "model cached in .dev/models")


# ── Process management ───────────────────────────────────────────────────


def _load_pids() -> dict[str, dict]:
    try:
        return json.loads(PID_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _save_pids(pids: dict[str, dict]) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    PID_FILE.write_text(json.dumps(pids, indent=2), encoding="utf-8")


def is_running(name: str) -> bool:
    import psutil

    entry = _load_pids().get(name)
    if not entry:
        return False
    try:
        process = psutil.Process(entry["pid"])
        # create_time guards against a recycled PID belonging to another program
        return abs(process.create_time() - entry["created"]) < 2 and process.is_running()
    except psutil.Error:
        return False


def port_in_use(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.5):
            return True
    except OSError:
        return False


def spawn(name: str, argv: list[str], cwd: Path) -> None:
    import psutil

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log = (LOG_DIR / f"{name}.log").open("ab")
    log.write(f"\n--- {datetime.now(UTC).isoformat()} start {name} ---\n".encode())
    flags: dict = {}
    if os.name == "nt":
        flags["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
    else:
        flags["start_new_session"] = True
    process = subprocess.Popen(
        argv,
        cwd=cwd,
        stdin=subprocess.DEVNULL,
        stdout=log,
        stderr=subprocess.STDOUT,
        env=child_env(),
        **flags,
    )
    pids = _load_pids()
    pids[name] = {"pid": process.pid, "created": psutil.Process(process.pid).create_time()}
    _save_pids(pids)


def stop_process(name: str) -> bool:
    import psutil

    entry = _load_pids().get(name)
    stopped = False
    if entry and is_running(name):
        try:
            parent = psutil.Process(entry["pid"])
            family = parent.children(recursive=True) + [parent]
            for proc in family:
                with contextlib.suppress(psutil.Error):
                    proc.terminate()
            _, alive = psutil.wait_procs(family, timeout=8)
            for proc in alive:
                with contextlib.suppress(psutil.Error):
                    proc.kill()
            stopped = True
        except psutil.Error:
            pass
    pids = _load_pids()
    pids.pop(name, None)
    _save_pids(pids)
    return stopped


def log_tail(name: str, lines: int, secrets: list[str]) -> str:
    path = LOG_DIR / f"{name}.log"
    if not path.is_file():
        return ""
    text = path.read_text(encoding="utf-8", errors="replace").splitlines()[-lines:]
    return scrub("\n".join(text), secrets)


def fail_with_log(name: str, secrets: list[str], error: DevError) -> DevError:
    tail = log_tail(name, 25, secrets)
    return DevError(f"{error}\n--- last lines of .dev/logs/{name}.log ---\n{tail}")


def require_node_deps(directory: str) -> None:
    if not (ROOT / directory / "node_modules").is_dir():
        raise DevError(f"{directory}/node_modules missing: run `cd {directory} && npm ci`")


def start_inference(python: str, secrets: list[str]) -> None:
    """The backend and worker refuse to start until the shared model service is ready (KNW-007)."""
    if is_running("inference"):
        step("inference", "already running")
    else:
        if port_in_use(INFERENCE_PORT):
            raise DevError(f"port {INFERENCE_PORT} is already in use by another program")
        step("inference", "starting (embedding model service)")
        spawn(
            "inference",
            [
                python,
                "-m",
                "uvicorn",
                "app.interface.inference.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(INFERENCE_PORT),
            ],
            ROOT,
        )
    try:
        wait_for(
            "inference /ready",
            lambda: http_status(f"{INFERENCE_URL}/ready", timeout=5) == 200,
            120,
            alive=lambda: is_running("inference"),
        )
    except DevError as error:
        raise fail_with_log("inference", secrets, error) from None
    step("inference", f"ready at {INFERENCE_URL}")


def start_backend(python: str, secrets: list[str]) -> None:
    if is_running("backend"):
        step("backend", "already running")
    else:
        if port_in_use(BACKEND_PORT):
            raise DevError(f"port {BACKEND_PORT} is already in use by another program")
        step("backend", "starting (uvicorn --reload)")
        spawn(
            "backend",
            [
                python,
                "-m",
                "uvicorn",
                "app.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(BACKEND_PORT),
                "--reload",
                "--reload-dir",
                "app",
            ],
            ROOT,
        )
    try:
        wait_for(
            "backend /ready", lambda: _backend_ready(), 150, alive=lambda: is_running("backend")
        )
    except DevError as error:
        raise fail_with_log("backend", secrets, error) from None
    step("backend", f"ready at {BACKEND_URL}")


def _backend_ready() -> bool:
    status, body = http_json("GET", f"{BACKEND_URL}/ready", timeout=5)
    return status == 200 and isinstance(body, dict) and body.get("status") == "ready"


def start_worker(python: str, secrets: list[str]) -> None:
    if is_running("worker"):
        step("worker", "already running")
        return
    step("worker", "starting (python -m app.worker)")
    spawn("worker", [python, "-m", "app.worker"], ROOT)
    # The worker validates Postgres/Redis/Qdrant itself and exits on failure.
    time.sleep(8)
    if not is_running("worker"):
        raise fail_with_log("worker", secrets, DevError("worker exited during startup"))
    step("worker", "running")


def start_frontend(secrets: list[str]) -> None:
    if is_running("frontend"):
        step("frontend", "already running")
    else:
        require_node_deps("frontend")
        npm = shutil.which("npm")
        if npm is None:
            raise DevError("npm not found on PATH")
        if port_in_use(FRONTEND_PORT):
            raise DevError(f"port {FRONTEND_PORT} is already in use by another program")
        step("frontend", "starting (vite)")
        spawn(
            "frontend",
            [
                npm,
                "run",
                "dev",
                "--",
                "--host",
                "127.0.0.1",
                "--port",
                str(FRONTEND_PORT),
                "--strictPort",
            ],
            ROOT / "frontend",
        )
    try:
        wait_for(
            "frontend",
            lambda: http_status(FRONTEND_URL + "/") == 200,
            60,
            alive=lambda: is_running("frontend"),
        )
        wait_for(
            "frontend /api proxy",
            lambda: http_status(FRONTEND_URL + "/api/v1/auth/capabilities") == 200,
            20,
        )
    except DevError as error:
        raise fail_with_log("frontend", secrets, error) from None
    step("frontend", f"ready at {FRONTEND_URL} (api proxied to backend)")


def start_discord(secrets: list[str]) -> None:
    if is_running("discord"):
        step("discord", "already running")
        return
    require_node_deps("discord")
    node = shutil.which("node")
    if node is None:
        raise DevError("node not found on PATH")
    step("discord", "starting bot")
    spawn("discord", [node, "src/index.js"], ROOT / "discord")
    marker = "Discord bot login completed"
    try:
        wait_for(
            "discord login",
            lambda: marker
            in (LOG_DIR / "discord.log").read_text(encoding="utf-8", errors="replace"),
            60,
            alive=lambda: is_running("discord"),
        )
    except DevError as error:
        raise fail_with_log("discord", secrets, error) from None
    step("discord", "logged in to Discord")


# ── Commands ─────────────────────────────────────────────────────────────


def cmd_start(args: argparse.Namespace, python: str) -> int:
    env = load_env(ROOT / ".env")
    secrets = preflight(env, python, with_discord=args.discord)
    ensure_infra(env, secrets)
    ensure_migrations(python, secrets, backup=not args.no_backup)
    ensure_qdrant_state(python, secrets)
    warn_if_lore_invisible(env)
    ensure_embedding_cache(python, secrets)
    start_inference(python, secrets)
    start_backend(python, secrets)
    if not args.no_worker:
        start_worker(python, secrets)
    if not args.no_frontend:
        start_frontend(secrets)
    if args.discord:
        start_discord(secrets)
    say()
    say("Chisa dev stack is READY")
    if not args.no_frontend:
        say(f"  web       {FRONTEND_URL}")
    say(f"  api       {BACKEND_URL}   (health: /health, readiness: /ready)")
    say("  logs      chisa dev logs [inference|backend|worker|frontend|discord] [-f]")
    say("  smoke     chisa dev test")
    say("  stop      chisa dev stop")
    return 0


def cmd_stop(args: argparse.Namespace, python: str) -> int:
    if args.infra:  # decide before stopping anything
        env = load_env(ROOT / ".env")
        if env.get("APP_ENV") != "development":
            raise DevError("refusing to touch infrastructure: APP_ENV is not 'development'")
    for name in reversed(APP_SERVICES):
        step("stop", f"{name}: {'stopped' if stop_process(name) else 'not running'}")
    if args.infra:
        result = subprocess.run(
            ["docker", "compose", "-f", str(COMPOSE_FILE), "stop", *INFRA_SERVICES],
            cwd=ROOT,
            env=compose_env(env),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
        )
        step(
            "stop",
            "infrastructure stopped (volumes kept)"
            if result.returncode == 0
            else "docker compose stop failed: " + result.stderr.strip()[-300:],
        )
    else:
        step("stop", "infrastructure left running (use --infra to stop it; data is never deleted)")
    return 0


def cmd_restart(args: argparse.Namespace, python: str) -> int:
    cmd_stop(argparse.Namespace(infra=False), python)
    return cmd_start(args, python)


def cmd_status(args: argparse.Namespace, python: str) -> int:
    env = load_env(ROOT / ".env")
    secrets = secret_values(env)
    say(f"environment: {env.get('APP_ENV', '?')}")
    healthy = True
    for name, ok in infra_status(env).items():
        say(f"  {name:<9} {'up' if ok else 'DOWN'}")
        healthy &= ok
    if healthy:
        try:
            current, head = alembic_revisions(python, secrets)
            if current == head:
                say("  migrations at head")
            else:
                say(f"  migrations BEHIND ({current or '<empty>'} -> {head})")
            healthy &= current == head
        except DevError as error:
            say(f"  migrations unknown: {str(error).splitlines()[0]}")
            healthy = False
    ready = _backend_ready() if is_running("backend") else False
    for name in APP_SERVICES:
        state = "running" if is_running(name) else "stopped"
        extra = ""
        if name == "backend" and state == "running":
            extra = "  /ready ok" if ready else "  /ready NOT READY"
        say(f"  {name:<9} {state}{extra}")
    return 0 if healthy and ready else 1


def cmd_logs(args: argparse.Namespace, python: str) -> int:
    env = load_env(ROOT / ".env")
    secrets = secret_values(
        env, load_env(ROOT / "discord" / ".env") if (ROOT / "discord" / ".env").is_file() else {}
    )
    names = [args.service] if args.service else list(APP_SERVICES)
    for name in names:
        say(f"--- {name} ---")
        say(log_tail(name, args.lines, secrets) or "(no log yet)")
    if args.follow and args.service:
        path = LOG_DIR / f"{args.service}.log"
        position = path.stat().st_size if path.is_file() else 0
        try:
            while True:
                if path.is_file() and path.stat().st_size > position:
                    with path.open("rb") as handle:
                        handle.seek(position)
                        chunk = handle.read().decode(errors="replace")
                        position = handle.tell()
                    print(scrub(chunk, secrets), end="", flush=True)
                time.sleep(0.5)
        except KeyboardInterrupt:
            pass
    return 0


def cmd_migrate(args: argparse.Namespace, python: str) -> int:
    env = load_env(ROOT / ".env")
    secrets = preflight(env, python, with_discord=False)
    ensure_infra(env, secrets)
    ensure_migrations(python, secrets, backup=not args.no_backup)
    return 0


def cmd_bootstrap(args: argparse.Namespace, python: str) -> int:
    env = load_env(ROOT / ".env")
    secrets = preflight(env, python, with_discord=False)
    ensure_infra(env, secrets)
    ensure_qdrant_state(python, secrets)
    return 0


def cmd_check(args: argparse.Namespace, python: str) -> int:
    env = load_env(ROOT / ".env")
    preflight(env, python, with_discord=args.discord)
    say("environment OK")
    return 0


# ── Smoke test ───────────────────────────────────────────────────────────


class Smoke:
    def __init__(self) -> None:
        self.failures: list[str] = []

    def check(self, name: str, ok: bool, detail: str = "") -> bool:
        say(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" - {detail}" if detail else ""))
        if not ok:
            self.failures.append(name)
        return ok


def mint_workload_token(env: Env, subject: str, scopes: list[str]) -> str:
    def part(value: object) -> str:
        return (
            base64.urlsafe_b64encode(json.dumps(value, separators=(",", ":")).encode())
            .rstrip(b"=")
            .decode()
        )

    now = int(time.time())
    header = part({"alg": "HS256", "typ": "JWT"})
    payload = part(
        {
            "sub": subject,
            "scopes": scopes,
            "source": "discord",
            "token_use": "workload",
            "tenant_id": "dev-smoke-guild",
            "channel_id": "dev-smoke-channel",
            "iss": env.get("DISCORD_WORKLOAD_JWT_ISSUER", "kuchiba-chisa-discord"),
            "aud": env.get("JWT_AUDIENCE", "kuchiba-chisa-api"),
            "iat": now,
            "exp": now + 120,
        }
    )
    signature = hmac.new(
        env["DISCORD_WORKLOAD_JWT_SECRET"].encode(), f"{header}.{payload}".encode(), hashlib.sha256
    ).digest()
    return f"{header}.{payload}.{base64.urlsafe_b64encode(signature).rstrip(b'=').decode()}"


def cmd_test(args: argparse.Namespace, python: str) -> int:
    env = load_env(ROOT / ".env")
    secrets = preflight(env, python, with_discord=False)
    smoke = Smoke()
    say("Smoke test")

    infra = infra_status(env)
    for name, ok in infra.items():
        smoke.check(f"{name} reachable", ok)
    if all(infra.values()):
        try:
            current, head = alembic_revisions(python, secrets)
            smoke.check("migrations at head", current == head, head)
        except DevError as error:
            smoke.check("migrations at head", False, str(error).splitlines()[0])
    if infra["qdrant"]:
        try:
            gap = lore_acl_gap(env)
            smoke.check(
                "lore corpus visible to retrieval (all points carry access_scope)",
                not any(gap.values()),
                "" if not any(gap.values()) else f"missing: {gap} -> chisa dev backfill-lore-acl",
            )
        except DevError as error:
            smoke.check("lore corpus visible to retrieval", False, str(error))
    health = http_status(f"{BACKEND_URL}/health")
    smoke.check("backend /health", health == 200)
    status, body = http_json("GET", f"{BACKEND_URL}/ready", timeout=10)
    services = body.get("services", {}) if isinstance(body, dict) else {}
    smoke.check(
        "backend /ready (postgres, redis, qdrant, llm config)",
        status == 200 and bool(services) and all(services.values()),
        ",".join(k for k, v in services.items() if not v) or "all true",
    )
    smoke.check("worker running", is_running("worker"))
    web = http_status(FRONTEND_URL + "/") == 200
    smoke.check("frontend serves the app", web)
    base = BACKEND_URL
    if web and smoke.check(
        "frontend proxies /api to backend",
        http_status(FRONTEND_URL + "/api/v1/auth/capabilities") == 200,
    ):
        base = FRONTEND_URL

    secrets_seen = list(secrets)
    subject = ""
    token = ""
    if health == 200:
        status, session = http_json("POST", f"{base}/api/v1/auth/anonymous-session")
        ok = status == 200 and isinstance(session, dict) and "access_token" in session
        smoke.check("anonymous web session issued", ok)
        if ok:
            token = str(session["access_token"])
            subject = str(session["subject_id"])
            secrets_seen.append(token)
            say("  ... sending one real chat request (calls the configured LLM, may take a minute)")
            started = time.monotonic()
            status, reply = http_json(
                "POST",
                f"{base}/api/v1/chat",
                {"message": "Xin chao Chisa, ban la ai?"},
                {"Authorization": f"Bearer {token}"},
                timeout=240,
            )
            text = reply.get("response", "") if isinstance(reply, dict) else ""
            # Fallback replies (LLM error, output-safety rejection) carry emotions=null;
            # only a completed pipeline returns the emotion state.
            real = isinstance(reply, dict) and bool(reply.get("emotions"))
            smoke.check(
                "chat completes end to end (not blocked by quota, real LLM answer, not a fallback)",
                status == 200 and bool(str(text).strip()) and real,
                f"HTTP {status}, {len(str(text))} chars, {time.monotonic() - started:.0f}s"
                + ("" if real else ", FALLBACK reply (see `chisa dev logs backend`)"),
            )
            status, _ = http_json(
                "DELETE",
                f"{base}/api/v1/chat/clear/{subject}",
                headers={"Authorization": f"Bearer {token}"},
                timeout=60,
            )
            smoke.check("smoke-test conversation erased", status in (200, 202), f"HTTP {status}")

    if is_running("discord"):
        discord_log = (LOG_DIR / "discord.log").read_text(encoding="utf-8", errors="replace")
        smoke.check("discord bot logged in", "Discord bot login completed" in discord_log)
        bot_subject = str(uuid.uuid4())
        workload = mint_workload_token(env, bot_subject, ["chat:write", "chat:clear"])
        secrets_seen.append(workload)
        status, reply = http_json(
            "POST",
            f"{BACKEND_URL}/api/v1/chat",
            {"message": "Xin chao tu Discord smoke test"},
            {"Authorization": f"Bearer {workload}"},
            timeout=240,
        )
        text = reply.get("response", "") if isinstance(reply, dict) else ""
        real = isinstance(reply, dict) and bool(reply.get("emotions"))
        smoke.check(
            "discord workload JWT -> Core -> chat (real answer, not a fallback)",
            status == 200 and bool(str(text).strip()) and real,
            f"HTTP {status}" + ("" if real else ", FALLBACK reply"),
        )
        http_json(
            "DELETE",
            f"{BACKEND_URL}/api/v1/chat/clear/{bot_subject}",
            headers={"Authorization": f"Bearer {workload}"},
            timeout=60,
        )
    else:
        say("  [skip] discord not running (start with `chisa dev start --discord`)")

    leaks = []
    for path in sorted(LOG_DIR.glob("*.log")) if LOG_DIR.is_dir() else []:
        text = path.read_text(encoding="utf-8", errors="replace")
        leaks += [path.name for secret in secrets_seen if secret in text]
    smoke.check("no secret value found in .dev/logs", not leaks, ", ".join(sorted(set(leaks))))

    say()
    if smoke.failures:
        say("SMOKE TEST FAILED: " + "; ".join(smoke.failures))
        return 1
    say("SMOKE TEST PASSED")
    return 0


# ── Entry point ──────────────────────────────────────────────────────────


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="chisa dev", description="Chisa development stack")
    sub = parser.add_subparsers(dest="command", required=True)

    def start_flags(p: argparse.ArgumentParser) -> None:
        p.add_argument("--discord", action="store_true", help="also start the Discord bot")
        p.add_argument("--no-frontend", action="store_true")
        p.add_argument("--no-worker", action="store_true")
        p.add_argument("--no-backup", action="store_true", help="skip the pre-migration pg_dump")

    start_flags(sub.add_parser("start", help="start everything and wait until ready"))
    start_flags(sub.add_parser("restart", help="stop the apps, then start again"))
    stop = sub.add_parser("stop", help="stop the apps (infrastructure keeps running)")
    stop.add_argument(
        "--infra", action="store_true", help="also stop Postgres/Redis/Qdrant (data kept)"
    )
    sub.add_parser("status", help="show infrastructure, migrations and app state")
    logs = sub.add_parser("logs", help="show scrubbed service logs")
    logs.add_argument("service", nargs="?", choices=APP_SERVICES)
    logs.add_argument("-n", "--lines", type=int, default=30)
    logs.add_argument("-f", "--follow", action="store_true")
    sub.add_parser("test", help="run the system smoke test against the running stack")
    migrate = sub.add_parser("migrate", help="start infra if needed and run Alembic")
    migrate.add_argument("--no-backup", action="store_true")
    sub.add_parser("bootstrap", help="create the Qdrant aliases needed by the runtime")
    sub.add_parser(
        "backfill-lore-acl",
        help="mark legacy dev lore points access_scope=public so retrieval can see them",
    )
    check = sub.add_parser("check", help="validate the development environment only")
    check.add_argument("--discord", action="store_true")
    return parser


COMMANDS: dict[str, Callable[[argparse.Namespace, str], int]] = {
    "start": cmd_start,
    "restart": cmd_restart,
    "stop": cmd_stop,
    "status": cmd_status,
    "logs": cmd_logs,
    "test": cmd_test,
    "migrate": cmd_migrate,
    "bootstrap": cmd_bootstrap,
    "check": cmd_check,
    "backfill-lore-acl": cmd_backfill_lore_acl,
}


def main(argv: list[str], python: str | None = None) -> int:
    # Logs can contain any Unicode; never let a legacy console codepage crash the CLI.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")
    args = build_parser().parse_args(argv)
    try:
        return COMMANDS[args.command](args, python or sys.executable)
    except DevError as error:
        say(f"[error] {error}")
        return 1
    except subprocess.TimeoutExpired as error:
        say(f"[error] timed out running {Path(str(error.cmd[0])).name}")
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
