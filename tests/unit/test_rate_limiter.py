from types import SimpleNamespace

from app.interface.middlewares.rate_limiter import RateLimitMiddleware


def _request(headers: dict[str, str], client_ip: str = "127.0.0.1") -> SimpleNamespace:
    return SimpleNamespace(
        headers=headers,
        client=SimpleNamespace(host=client_ip),
    )


def test_rate_limit_key_prefers_explicit_user_header():
    request = _request({"X-User-ID": "discord:123"})

    assert RateLimitMiddleware._extract_user_key(request) == "uid:discord:123"


def test_rate_limit_key_uses_first_forwarded_ip_without_reading_body():
    request = _request({"X-Forwarded-For": "203.0.113.7, 10.0.0.4"})

    assert RateLimitMiddleware._extract_user_key(request) == "ip:203.0.113.7"


def test_rate_limit_key_falls_back_to_client_ip():
    request = _request({}, client_ip="192.0.2.8")

    assert RateLimitMiddleware._extract_user_key(request) == "ip:192.0.2.8"
