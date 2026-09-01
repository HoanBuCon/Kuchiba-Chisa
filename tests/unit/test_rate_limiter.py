from types import SimpleNamespace

from app.config.settings import settings
from app.domain.value_objects.principal import PrincipalContext
from app.interface.middlewares.rate_limiter import RateLimitMiddleware


def _principal(subject_id: str, tenant_id: str | None = None) -> PrincipalContext:
    return PrincipalContext(
        subject_id=subject_id,
        tenant_id=tenant_id,
        channel_id=None,
        source="web",
        kind="user",
        scopes=frozenset({"chat:write"}),
    )


def test_rate_limit_key_is_stable_for_verified_principal_and_route():
    principal = _principal("user-a", "tenant-a")

    first = RateLimitMiddleware._rate_limit_key(principal, "POST", "/api/v1/chat")
    second = RateLimitMiddleware._rate_limit_key(principal, "POST", "/api/v1/chat")

    assert first == second
    assert "user-a" not in first
    assert "tenant-a" not in first


def test_rate_limit_key_changes_for_a_different_verified_principal():
    first = RateLimitMiddleware._rate_limit_key(_principal("user-a"), "POST", "/api/v1/chat")
    second = RateLimitMiddleware._rate_limit_key(_principal("user-b"), "POST", "/api/v1/chat")

    assert first != second


def test_rate_limit_key_includes_tenant_and_route_scope():
    principal = _principal("user-a", "tenant-a")

    tenant_key = RateLimitMiddleware._rate_limit_key(
        _principal("user-a", "tenant-b"), "POST", "/api/v1/chat"
    )
    route_key = RateLimitMiddleware._rate_limit_key(principal, "DELETE", "/api/v1/chat/clear")

    assert tenant_key != RateLimitMiddleware._rate_limit_key(principal, "POST", "/api/v1/chat")
    assert route_key != RateLimitMiddleware._rate_limit_key(principal, "POST", "/api/v1/chat")
    assert RateLimitMiddleware._rate_limit_key(
        principal, "GET", "/api/v1/chat/history/user-a"
    ) == RateLimitMiddleware._rate_limit_key(
        principal, "GET", "/api/v1/chat/history/user-b"
    )


def test_untrusted_peer_cannot_spoof_forwarded_client_ip(monkeypatch):
    monkeypatch.setattr(settings, "TRUSTED_PROXY_CIDRS", "10.0.0.0/8")
    limiter = RateLimitMiddleware(app=SimpleNamespace())
    request = SimpleNamespace(
        client=SimpleNamespace(host="198.51.100.20"),
        headers={"X-Forwarded-For": "203.0.113.10"},
    )

    assert limiter._trusted_client_ip(request) == "198.51.100.20"


def test_trusted_proxy_can_supply_valid_client_ip_for_anomaly_bucket(monkeypatch):
    monkeypatch.setattr(settings, "TRUSTED_PROXY_CIDRS", "10.0.0.0/8,fd00::/8")
    limiter = RateLimitMiddleware(app=SimpleNamespace())
    request = SimpleNamespace(
        client=SimpleNamespace(host="10.1.2.3"),
        headers={"X-Forwarded-For": "203.0.113.10, 10.1.2.3"},
    )
    assert limiter._trusted_client_ip(request) == "203.0.113.10"
    assert limiter._ip_anomaly_key("203.0.113.10") != limiter._ip_anomaly_key("203.0.113.11")


def test_anonymous_session_key_uses_only_trusted_network_address(monkeypatch):
    monkeypatch.setattr(settings, "TRUSTED_PROXY_CIDRS", "10.0.0.0/8")
    limiter = RateLimitMiddleware(app=SimpleNamespace())
    request = SimpleNamespace(
        client=SimpleNamespace(host="198.51.100.20"),
        headers={"X-Forwarded-For": "203.0.113.10", "X-User-ID": "attacker-a"},
    )

    client_ip = limiter._trusted_client_ip(request)
    assert client_ip == "198.51.100.20"
    assert limiter._anonymous_session_key(client_ip) == limiter._anonymous_session_key(
        "198.51.100.20"
    )
