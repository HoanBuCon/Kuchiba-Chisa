import pytest
from app.shared.utils.json_parser import robust_parse_json


def test_parse_valid_json():
    raw = '{"response": "Chào Senpai!", "sentiment_analysis": {"intensity": 0.5, "valence": 0.2, "primary_emotion": "calm_warmth"}}'
    result = robust_parse_json(raw)
    assert result.get("response") == "Chào Senpai!"
    assert result.get("sentiment_analysis", {}).get("primary_emotion") == "calm_warmth"


def test_parse_json_with_unescaped_quotes():
    raw = '{"response": "S-senpai... em xin lỗi, nhưng..."duyệt" không nằm trong danh sách phân tích của em lúc này đâu ạ. Em thật sự rất quý Senpai...", "sentiment_analysis": {"intensity": 0.4, "valence": -0.1, "primary_emotion": "melancholic_care"}}'
    result = robust_parse_json(raw)
    assert "S-senpai... em xin lỗi, nhưng..." in result.get("response", "")
    assert '"duyệt"' in result.get("response", "") or 'duyệt' in result.get("response", "")
    assert result.get("sentiment_analysis", {}).get("primary_emotion") == "melancholic_care"


def test_parse_truncated_single_brace():
    raw = "{"
    result = robust_parse_json(raw)
    assert result == {}


def test_parse_empty_or_syntax_fragment():
    assert robust_parse_json("") == {}
    assert robust_parse_json("   ") == {}
    assert robust_parse_json("}") == {}
    assert robust_parse_json("{}") == {}
    assert robust_parse_json("[]") == {}
    assert robust_parse_json("null") == {}


def test_parse_markdown_codeblock():
    raw = "Here is the response:\n```json\n{\"response\": \"Em hiểu rồi ạ!\", \"sentiment_analysis\": {\"intensity\": 0.3, \"valence\": 0.5, \"primary_emotion\": \"cheerful_joy\"}}\n```"
    result = robust_parse_json(raw)
    assert result.get("response") == "Em hiểu rồi ạ!"
    assert result.get("sentiment_analysis", {}).get("primary_emotion") == "cheerful_joy"


def test_parse_with_thinking_tags():
    raw = "<think>Senpai đang hỏi thăm</think>{\"response\": \"Dạ em đây ạ!\", \"sentiment_analysis\": {\"intensity\": 0.2, \"valence\": 0.1, \"primary_emotion\": \"calm_warmth\"}}"
    result = robust_parse_json(raw)
    assert result.get("response") == "Dạ em đây ạ!"
