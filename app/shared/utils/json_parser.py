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

    # 4.5. Heuristic Regex field extraction for malformed JSON with unescaped quotes inside strings
    extracted_obj = {}
    resp_match = re.search(
        r'["\']response["\']\s*:\s*["\']([\s\S]*?)["\']\s*,\s*["\'](?:sentiment|sentiment_analysis|user_sentiment|chisa_sentiment|summary|intensity|reasoning)["\']',
        raw_cleaned
    )
    if not resp_match:
        resp_match = re.search(r'["\']response["\']\s*:\s*["\']([\s\S]*?)["\']\s*\}', raw_cleaned)

    if resp_match:
        extracted_resp = resp_match.group(1).strip()
        if extracted_resp:
            extracted_obj["response"] = extracted_resp

    sent_match = re.search(r'["\'](?:sentiment|sentiment_analysis)["\']\s*:\s*(\{[\s\S]*?\})', raw_cleaned)
    if sent_match:
        try:
            sent_obj = json.loads(sent_match.group(1).strip())
            if isinstance(sent_obj, dict):
                extracted_obj["sentiment"] = sent_obj
                extracted_obj["sentiment_analysis"] = sent_obj
        except Exception:
            pass

    if extracted_obj and "response" in extracted_obj:
        return extracted_obj

    # 5. Fallback: Strip reasoning tags (<think>...</think>) & markdown, wrap clean text in {"response": text}
    clean_text = re.sub(r"<think>[\s\S]*?</think>", "", raw_cleaned, flags=re.IGNORECASE).strip()
    clean_text = re.sub(r"```[\s\S]*?```", "", clean_text).strip()

    if "Phản hồi từ LLM" in clean_text:
        clean_text = clean_text.split("Phản hồi từ LLM")[-1].strip()

    # Drop single punctuation/syntax fragments (e.g. "{", "}", "{}", "[]", "null")
    if clean_text in ("{", "}", "{}", "[]", '""', "null", "None", ""):
        return {}

    # If clean_text starts with "{" and has "response": key, do not leak raw JSON structure
    if clean_text.startswith("{") and ('"response"' in clean_text or "'response'" in clean_text):
        m = re.search(r'["\']response["\']\s*:\s*["\']?([^"\'\}\n]+)', clean_text)
        if m and m.group(1).strip():
            return {"response": m.group(1).strip()}
        return {}

    if clean_text:
        log.warning("Could not parse JSON object from LLM output. Wrapping text into response key.", raw_preview=raw_cleaned[:150])
        return {"response": clean_text}

    return {}
