import json
import re
from typing import Any
from app.shared.utils.logger import get_logger

log = get_logger(__name__)


def robust_parse_json(raw: str) -> dict[str, Any]:
    """
    Robustly parses raw text from LLM into a JSON dictionary.
    Handles:
    - Native reasoning / Chain-of-Thought (CoT) text preceding JSON
    - Markdown codeblocks ```json ... ```
    - Extra text surrounding JSON objects
    - Plain text responses (wraps into {"response": text})
    """
    if not raw or not raw.strip():
        return {}

    raw_cleaned = raw.strip()

    # 1. Direct json.loads
    try:
        parsed = json.loads(raw_cleaned)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        pass

    # 2. Extract markdown codeblock ```json ... ``` or ``` ... ```
    codeblock_matches = re.findall(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", raw_cleaned, re.IGNORECASE)
    for codeblock in reversed(codeblock_matches):
        try:
            parsed = json.loads(codeblock.strip())
            if isinstance(parsed, dict) and ("response" in parsed or "summary" in parsed):
                return parsed
        except Exception:
            pass

    # 3. Find all JSON objects {...} in raw_cleaned
    # Iterate in reverse to prefer the final JSON response payload
    candidates = re.findall(r"\{[\s\S]*?\}", raw_cleaned)
    for candidate in reversed(candidates):
        try:
            parsed = json.loads(candidate.strip())
            if isinstance(parsed, dict) and ("response" in parsed or "user_sentiment" in parsed or "summary" in parsed):
                return parsed
        except Exception:
            pass

    # 4. Try substring between first '{' and last '}'
    start = raw_cleaned.find('{')
    end = raw_cleaned.rfind('}')
    if start != -1 and end != -1 and end > start:
        candidate = raw_cleaned[start:end + 1]
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            pass

    # 5. Fallback: Strip reasoning tags (<think>...</think>) & markdown, wrap clean text in {"response": text}
    clean_text = re.sub(r"<think>[\s\S]*?</think>", "", raw_cleaned, flags=re.IGNORECASE).strip()
    clean_text = re.sub(r"```[\s\S]*?```", "", clean_text).strip()

    if "Phản hồi từ LLM" in clean_text:
        clean_text = clean_text.split("Phản hồi từ LLM")[-1].strip()

    if clean_text:
        log.warning("Could not parse JSON object from LLM output. Wrapping text into response key.", raw_preview=raw_cleaned[:150])
        return {"response": clean_text}

    return {}
