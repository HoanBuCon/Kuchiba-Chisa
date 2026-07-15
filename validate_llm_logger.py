import asyncio
import os
import shutil
import json
from datetime import datetime

# Clean up before testing
log_dir = "logs_test_telemetry"
if os.path.exists(log_dir):
    shutil.rmtree(log_dir)

# Override settings temporarily before importing llm_logger
os.environ["LLM_LOG_FILE"] = f"{log_dir}/llm_api.jsonl"
os.environ["LLM_LOG_MAX_BYTES"] = "500" # Very small to force rotation quickly
os.environ["LLM_LOG_BACKUP_COUNT"] = "2"

from app.config.settings import invalidate_settings_cache
invalidate_settings_cache()
from app.config.settings import settings
print(f"Setting: LLM_LOG_FILE={settings.LLM_LOG_FILE}")
print(f"Setting: LLM_LOG_MAX_BYTES={settings.LLM_LOG_MAX_BYTES}")

# Now import logger, which will initialize and create the directory
from app.infrastructure.logging.llm_logger import llm_telemetry_logger, _write_log_sync
from app.domain.interfaces.llm_provider import StructuredPrompt, LLMResponse

print(f"Directory exists: {os.path.exists(log_dir)}")

# Create dummy payload
prompt = StructuredPrompt(
    system="You are a bot",
    history=[],
    user_message="Hello",
    response_schema={"type": "object"}
)
response = LLMResponse(
    raw_content="{}",
    parsed={},
    input_tokens=10,
    output_tokens=20,
    model="test-model",
    finish_reason="stop"
)

# Call write_log_sync multiple times to trigger rotation
for i in range(10):
    _write_log_sync(prompt, response, q_idx=i, t_idx=i)

# Verify files
files = sorted(os.listdir(log_dir))
print(f"Log files created: {files}")

# Verify JSON
for f in files:
    path = os.path.join(log_dir, f)
    with open(path, "r", encoding="utf-8") as f_in:
        for line in f_in:
            if line.strip():
                try:
                    data = json.loads(line)
                    assert "timestamp" in data
                    assert "model" in data
                except Exception as e:
                    print(f"Invalid JSON in {f}: {line}")
                    raise e
print("All lines are valid JSON")

# Clean up
if os.path.exists(log_dir):
    shutil.rmtree(log_dir)
